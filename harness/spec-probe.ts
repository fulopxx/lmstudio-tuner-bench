// Probe: speculative decoding on the installed LM Studio (task 24, phase 0, steps P1-P6).
//
//   cd harness
//   node spec-probe.ts --plan ..\configs\spec-probe.local.json --dry-run        (no GPU: plan, cases, config hash)
//   node spec-probe.ts --plan ..\configs\spec-probe.local.json --steps P1,P2    (GPU)
//
// P1 baseline, speculation off | P2 draft model set at load | P3 draft model per prediction (`draftModel`)
// P4 REST chat endpoint with a draft model loaded | P5 MTP on and off | P6 persistence and an incompatible pair.
// Each load reads the applied config back; each prediction records speed and draft counters. Every step has a
// timeout, nothing is retried, a timeout stops the run. Only models loaded by this script are unloaded. The
// LM Studio per-model config folder is hashed before and after. Results: results/spec_probe_<time>.json.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { parseArgs } from "node:util";
import { LMStudioClient, type LLM } from "@lmstudio/sdk";
import {
  draftRatios, firstDifference, loadConfig, median, parseSteps, PROMPTS, speculativeFields,
  speculativeMismatches, validatePlan, type DraftStats, type ProbePlan, type PromptKind, type SpecMode, type Step,
} from "./spec-probe-lib.ts";

const IDENTIFIER = "bench-spec";
const LMS = join(homedir(), ".lmstudio", "bin", "lms.exe");
const APP_DIR = join(homedir(), ".lmstudio", "apps", "bionic", ".internal");
const CONFIG_DIR = join(APP_DIR, "user-concrete-model-default-config");

const { values: args } = parseArgs({
  options: { plan: { type: "string" }, steps: { type: "string" }, "dry-run": { type: "boolean" } },
});

function apiBaseUrl(): string {
  const file = process.env.LMS_API_FILE ?? join(APP_DIR, "http-server.json");
  const { host, port } = JSON.parse(readFileSync(file, "utf8"));
  return `ws://${host}:${port}`;
}

const run = (file: string, argv: string[], timeout = 60_000) =>
  execFileSync(file, argv, { encoding: "utf8", timeout, stdio: ["ignore", "pipe", "pipe"] });
const lms = (...argv: string[]) => run(LMS, argv);
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const msg = (e: unknown) => String((e as Error)?.message ?? e).slice(0, 800);

function gpu() {
  const [used, total, util] = run("nvidia-smi", ["--query-gpu=memory.used,memory.total,utilization.gpu",
    "--format=csv,noheader,nounits"], 15_000).trim().split(",").map(Number);
  return { used, total, util };
}

function snapshot(dir: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!existsSync(dir)) return out;
  for (const entry of readdirSync(dir, { withFileTypes: true, recursive: true })) {
    if (!entry.isFile()) continue;
    const path = join(entry.parentPath, entry.name);
    out[path] = createHash("sha256").update(readFileSync(path)).digest("hex");
  }
  return out;
}
const digest = (s: Record<string, string>) => createHash("sha256").update(JSON.stringify(s)).digest("hex");

/** Loaded models as LM Studio lists them; raw entries are kept, since the draft model's appearance is a question. */
function loadedModels(): { identifier?: string; modelKey?: string; [k: string]: unknown }[] {
  const out = lms("ps", "--json").trim();
  return out ? JSON.parse(out) : [];
}

/** Starts the HTTP server when needed and waits until it reports running; LM Studio reuses the last port. */
async function serverBase(): Promise<{ base: string | null; started: boolean }> {
  const status = () => JSON.parse(lms("server", "status", "--json")) as { running?: boolean; port?: number };
  let s = status();
  let started = false;
  if (!s.running) {
    lms("server", "start");
    started = true;
    for (let i = 0; i < 30 && !s.running; i++) {
      await sleep(1000);
      s = status();
    }
  }
  return { base: s.running && s.port ? `http://127.0.0.1:${s.port}` : null, started };
}

// ---------------------------------------------------------------------------------------------------------

const result: Record<string, unknown> = { started: new Date().toISOString(), cases: [] as unknown[] };
const cases = result.cases as Record<string, unknown>[];
const ownedKeys = new Set<string>(); // model keys this script caused to load (target, draft, mtp)
let client: LMStudioClient | undefined;
let serverStartedHere = false;
let exitCode = 1;
let plan: ProbePlan;

process.on("unhandledRejection", (e) => {
  console.error("ABORTED (unhandled rejection):", msg(e));
  cleanup().finally(() => process.exit(1));
});

async function cleanup() {
  try {
    await client?.[Symbol.asyncDispose]();
  } catch { /* closing a broken connection is not a result */ }
  try {
    for (const m of loadedModels()) {
      const id = String(m.identifier ?? "");
      if (id === IDENTIFIER || ownedKeys.has(String(m.modelKey ?? "")) || ownedKeys.has(id)) lms("unload", id);
    }
    result.leftAfterCleanup = loadedModels().map((m) => m.identifier);
    if (serverStartedHere) lms("server", "stop");
  } catch (e) {
    console.error("cleanup problem:", msg(e));
  }
}

async function load(modelKey: string, config: Record<string, unknown>, row: Record<string, unknown>) {
  ownedKeys.add(modelKey);
  if (typeof config.speculativeDraftModel === "string") ownedKeys.add(config.speculativeDraftModel);
  await sleep(2000);
  const vramBefore = gpu().used;
  const t0 = Date.now();
  const model = await client!.llm.load(modelKey, {
    identifier: IDENTIFIER, config, verbose: false, signal: AbortSignal.timeout(plan.loadTimeoutMs),
  });
  row.loadSeconds = (Date.now() - t0) / 1000;
  await sleep(2000);
  row.vramBeforeMiB = vramBefore;
  row.vramDeltaMiB = gpu().used - vramBefore;
  const applied: Record<string, unknown> = { ...(await model.getLoadConfig()) };
  row.appliedSpeculative = speculativeFields(applied);
  row.speculativeMismatches = speculativeMismatches(config, applied);
  row.loadedModels = loadedModels(); // does a draft model show up as a separate entry?
  return model;
}

interface Measured { kind: PromptKind; i: number; text: string; [k: string]: unknown }

/** One warm-up and `repeats` measured predictions per prompt kind; the warm-up is not stored. */
async function measure(model: LLM, row: Record<string, unknown>, draftModel?: string) {
  const runs: Measured[] = [];
  for (const kind of Object.keys(PROMPTS) as PromptKind[]) {
    for (let i = 0; i <= plan.repeats; i++) {
      const tag = i === 0 ? `warmup-${Date.now()}` : `${kind}-${i}`; // same tags across cases for SD-09
      const answer = await model.respond([{ role: "user", content: PROMPTS[kind](tag) }], {
        maxTokens: plan.maxTokens, temperature: 0, ...(draftModel ? { draftModel } : {}),
        signal: AbortSignal.timeout(plan.predictTimeoutMs),
      });
      if (i === 0) continue;
      const s = answer.stats as typeof answer.stats & DraftStats;
      runs.push({
        kind, i, text: answer.content,
        decodeTokS: s.tokensPerSecond ?? null, ttftS: s.timeToFirstTokenSec ?? null,
        promptTokens: s.promptTokensCount ?? null, outputTokens: s.predictedTokensCount ?? null,
        stopReason: s.stopReason, usedDraftModelKey: s.usedDraftModelKey ?? null,
        draftTotal: s.totalDraftTokensCount ?? null, draftAccepted: s.acceptedDraftTokensCount ?? null,
        draftRejected: s.rejectedDraftTokensCount ?? null, draftIgnored: s.ignoredDraftTokensCount ?? null,
        ...draftRatios(s, s.predictedTokensCount),
      });
    }
  }
  row.runs = runs;
  row.summary = Object.fromEntries((Object.keys(PROMPTS) as PromptKind[]).map((kind) => {
    const r = runs.filter((x) => x.kind === kind);
    const num = (k: string) => r.map((x) => x[k]).filter((v): v is number => typeof v === "number");
    return [kind, {
      decodeTokS: median(num("decodeTokS")), ttftS: median(num("ttftS")),
      acceptanceRate: median(num("acceptanceRate")), draftShare: median(num("draftShare")),
      draftCountersPresent: r.some((x) => x.draftTotal !== null),
    }];
  }));
  console.log("   ", JSON.stringify(row.summary));
}

/** SD-09: compare each greedy output with the baseline run of the same prompt and repeat index. */
function compareWith(baseline: Record<string, unknown> | undefined, row: Record<string, unknown>) {
  const base = (baseline?.runs ?? []) as Measured[];
  row.firstDifferenceVsBaseline = ((row.runs ?? []) as Measured[]).map((r) => {
    const b = base.find((x) => x.kind === r.kind && x.i === r.i);
    return { kind: r.kind, i: r.i, firstDifference: b ? firstDifference(b.text, r.text) : "n/a" };
  });
}

async function runCase(id: Step, label: string, fn: (row: Record<string, unknown>) => Promise<void>) {
  const row: Record<string, unknown> = { step: id, label };
  cases.push(row);
  console.log(`== ${id} ${label}`);
  try {
    await fn(row);
    row.status ??= "ok";
  } catch (e) {
    row.error = msg(e);
    // a capability the engine refuses is a result (SD-01), not a failure of the probe
    row.status = /capability gap|must be configured at load time/i.test(row.error as string) ? "unsupported" : "fail";
    console.log(`   ${String(row.status).toUpperCase()}: ${row.error}`);
    if (/abort|timeout/i.test(row.error as string)) throw new Error("timeout; stopping without retry");
  } finally {
    try {
      if ((await client!.llm.listLoaded()).some((m) => m.identifier === IDENTIFIER)) await client!.llm.unload(IDENTIFIER);
    } catch (e) {
      row.unloadProblem = msg(e); // the final cleanup tries again with `lms unload`
    }
  }
  return row;
}

async function measuredCase(step: Step, label: string, modelKey: string, mode: SpecMode, opts: {
  draftPerPrediction?: string; baseline?: Record<string, unknown>;
} = {}) {
  return runCase(step, label, async (row) => {
    const config = loadConfig(plan.contextLength, mode, plan.draft);
    row.model = modelKey;
    row.mode = mode;
    row.requestedSpeculative = speculativeFields(config);
    if (opts.draftPerPrediction) {
      row.draftPerPrediction = opts.draftPerPrediction;
      ownedKeys.add(opts.draftPerPrediction);
    }
    const model = await load(modelKey, config, row);
    await measure(model, row, opts.draftPerPrediction);
    if (opts.baseline) compareWith(opts.baseline, row);
  });
}

/** P4: is there anything about drafting in the REST chat responses? Raw responses are stored. */
async function restCase() {
  return runCase("P4", "REST chat with a draft model loaded", async (row) => {
    row.model = plan.target;
    await load(plan.target, loadConfig(plan.contextLength, "draft", plan.draft), row);
    const server = await serverBase();
    serverStartedHere ||= server.started;
    if (!server.base) throw new Error("the HTTP server did not report running within 30 s");
    const body = (stream: boolean) => JSON.stringify({
      model: IDENTIFIER, temperature: 0, max_tokens: 64, stream,
      ...(stream ? { stream_options: { include_usage: true } } : {}),
      messages: [{ role: "user", content: PROMPTS.code(`rest-${stream}`) }],
    });
    const post = (stream: boolean) => fetch(`${server.base}/v1/chat/completions`, {
      method: "POST", headers: { "content-type": "application/json" }, body: body(stream),
      signal: AbortSignal.timeout(plan.predictTimeoutMs),
    });
    row.restNonStream = await (await post(false)).json();
    const events = (await (await post(true)).text()).split("\n").filter((l) => l.startsWith("data:"));
    row.restStreamLastEvents = events.slice(-3).map((l) => l.slice(5).trim());
    const all = JSON.stringify(row.restNonStream) + row.restStreamLastEvents;
    row.draftFieldsInRest = /draft|specul/i.test(all);
    console.log("    draft fields in REST:", row.draftFieldsInRest);
  });
}

async function persistenceCases() {
  // after a draft load: does a later load that omits the speculative fields inherit anything?
  await runCase("P6", "draft load, then reload with the speculative fields omitted", async (row) => {
    row.model = plan.target;
    const first: Record<string, unknown> = {};
    await load(plan.target, loadConfig(plan.contextLength, "draft", plan.draft), first);
    row.first = first;
    await client!.llm.unload(IDENTIFIER);
    const second: Record<string, unknown> = {};
    await load(plan.target, loadConfig(plan.contextLength, "omit"), second);
    row.second = second;
    row.inherited = Object.entries(second.appliedSpeculative as Record<string, unknown>)
      .some(([k, v]) => k === "speculativeDraftSimple" ? v === true : k === "speculativeDraftModel" ? !!v : false);
    console.log("    draft settings inherited:", row.inherited);
  });
  // switching from a draft model to MTP (an earlier release note mentions a draft model that stuck)
  for (const mtp of plan.mtp.slice(0, 1)) {
    await runCase("P6", `draft load, then MTP load of ${mtp}`, async (row) => {
      const first: Record<string, unknown> = {};
      await load(plan.target, loadConfig(plan.contextLength, "draft", plan.draft), first);
      await client!.llm.unload(IDENTIFIER);
      const second: Record<string, unknown> = {};
      await load(mtp, loadConfig(plan.contextLength, "mtp"), second);
      row.first = first;
      row.second = second;
    });
  }
  if (plan.incompatible) {
    const pair = plan.incompatible;
    await runCase("P6", `incompatible pair ${pair.target} + ${pair.draft}`, async (row) => {
      row.model = pair.target;
      const config = { ...loadConfig(plan.contextLength, "draft", pair.draft) };
      ownedKeys.add(pair.draft);
      try {
        const model = await load(pair.target, config, row);
        row.loadAccepted = true;
        const answer = await model.respond([{ role: "user", content: "Say OK." }],
          { maxTokens: 8, temperature: 0, signal: AbortSignal.timeout(plan.predictTimeoutMs) });
        row.stats = answer.stats;
      } catch (e) {
        row.loadAccepted = false;
        row.rejection = msg(e); // the expected outcome; recorded, not a failure
        if (/abort|timeout/i.test(row.rejection as string)) throw e;
      }
    });
  }
}

try {
  if (!args.plan) throw new Error("--plan <file> is required");
  const checked = validatePlan(JSON.parse(readFileSync(args.plan, "utf8")));
  plan = checked.plan;
  const steps = parseSteps(args.steps);
  result.plan = plan;
  result.steps = steps;
  result.configFolderBefore = digest(snapshot(CONFIG_DIR));
  if (checked.problems.length) throw new Error("plan problems: " + checked.problems.join("; "));

  if (args["dry-run"]) {
    console.log("plan ok; steps:", steps.length ? steps.join(",") : "(none given)");
    for (const mode of ["off", "draft", "mtp", "omit"] as SpecMode[]) {
      console.log(`  ${mode}:`, JSON.stringify(speculativeFields(loadConfig(plan.contextLength, mode, plan.draft))));
    }
    console.log("config folder hash:", result.configFolderBefore);
    result.dryRun = true;
    exitCode = 0;
  } else {
    if (!steps.length) throw new Error("--steps is required (e.g. --steps P1,P2); use --dry-run to check the plan");
    if (loadedModels().length) throw new Error("a model is already loaded; unload it first (this script will not)");
    const g = gpu();
    result.gpuAtStart = g;
    if (g.total - g.used < plan.minFreeMib || g.util > plan.maxUtil) {
      throw new Error(`GPU not idle: ${g.total - g.used} MiB free, ${g.util}% busy`);
    }
    client = new LMStudioClient({ baseUrl: apiBaseUrl() });
    result.app = await client.system.getLMStudioVersion().then((v) => `${v.version}+${v.build}`, () => null);
    try { // recorded only; the output format of `lms runtime ls` is not parsed further
      result.runtimeList = lms("runtime", "ls").trim();
    } catch (e) {
      result.runtimeList = `n/a: ${msg(e)}`;
    }

    let baseline: Record<string, unknown> | undefined;
    if (steps.includes("P1") || steps.includes("P2") || steps.includes("P3")) {
      baseline = await measuredCase("P1", "baseline, speculation off", plan.target, "off");
    }
    if (steps.includes("P2")) await measuredCase("P2", "draft model at load", plan.target, "draft", { baseline });
    if (steps.includes("P3")) {
      await measuredCase("P3", "draft model per prediction", plan.target, "off",
        { draftPerPrediction: plan.draft, baseline });
    }
    if (steps.includes("P4")) await restCase();
    if (steps.includes("P5")) {
      if (!plan.mtp.length) console.log("== P5 skipped: no MTP model in the plan");
      for (const mtp of plan.mtp) {
        const off = await measuredCase("P5", `MTP off: ${mtp}`, mtp, "off");
        await measuredCase("P5", `MTP on: ${mtp}`, mtp, "mtp", { baseline: off });
      }
    }
    if (steps.includes("P6")) await persistenceCases();
    exitCode = cases.every((c) => c.status === "ok" || c.status === "unsupported") ? 0 : 2;
  }
} catch (e) {
  result.aborted = msg(e);
  console.error("ABORTED:", result.aborted);
} finally {
  if (client) await cleanup();
  result.configFolderAfter = digest(snapshot(CONFIG_DIR));
  result.configFolderUnchanged = result.configFolderBefore === result.configFolderAfter;
  console.log("LM Studio config folder unchanged:", result.configFolderUnchanged);
  if (!args["dry-run"]) {
    const dir = join(import.meta.dirname, "..", "results");
    mkdirSync(dir, { recursive: true });
    const file = join(dir, `spec_probe_${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}.json`);
    writeFileSync(file, JSON.stringify(result, null, 1));
    console.log("result file:", file);
  }
  process.exit(exitCode);
}
