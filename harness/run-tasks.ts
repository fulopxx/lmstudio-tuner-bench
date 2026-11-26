// Agent harness entry point (decisions H1-H3): runs a task set on one loaded model and writes a trace per attempt.
//
//   node run-tasks.ts            first stdin line: run spec (JSON, see agent/spec.ts)
//                                further stdin lines: commands, {"cmd": "stop"}
//
// Progress lines go to stdout; the last stdout line is "RESULT:" followed by a JSON summary. The harness does not
// load or unload models and does not judge the answers; the core does both. Exit code 0 when every attempt ran
// (whatever its outcome), 1 when the spec is unusable or the harness itself failed.
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { LMStudioClient } from "@lmstudio/sdk";
import { LmsSdkBackend, ScriptedBackend, type ModelBackend } from "./agent/backend.ts";
import { runAttempt, type AttemptOutcome } from "./agent/loop.ts";
import { createSandbox } from "./agent/sandbox.ts";
import { checkSpec, limitsFor, type RunSpec } from "./agent/spec.ts";
import { FileTrace } from "./agent/trace.ts";

const stop = new AbortController();
let specLine: ((line: string) => void) | undefined;
const firstLine = new Promise<string>((resolve) => { specLine = resolve; });
const input = createInterface({ input: process.stdin });
let seenSpec = false;
input.on("line", (line) => {
  if (!seenSpec) {
    seenSpec = true;
    specLine!(line);
    return;
  }
  try {
    if (JSON.parse(line).cmd === "stop" && !stop.signal.aborted) {
      console.log("stop requested");
      stop.abort();
    }
  } catch {
    console.log(`ignored command line: ${line.slice(0, 80)}`);
  }
});
input.on("close", () => { if (!seenSpec) specLine!(""); });
// Ctrl+C in the console reaches this process too: stop like the stop command instead of dying without a result
process.on("SIGINT", () => {
  if (!stop.signal.aborted) {
    console.log("stop requested (Ctrl+C)");
    stop.abort();
  }
});

function finish(summary: Record<string, unknown>, code: number): never {
  process.stdout.write("\nRESULT:" + JSON.stringify(summary) + "\n", () => process.exit(code));
  return undefined as never;
}

let client: LMStudioClient | undefined;
try {
  const line = await firstLine;
  if (!line.trim()) throw new Error("no run spec on stdin");
  const spec = JSON.parse(line) as RunSpec;
  const problems = checkSpec(spec);
  if (problems.length) throw new Error("spec problems: " + problems.join("; "));

  let backend: ModelBackend;
  let app: string | null = null;
  if (spec.backend.type === "lmstudio") {
    const file = spec.backend.apiFile ?? process.env.LMS_API_FILE
      ?? join(homedir(), ".lmstudio", "apps", "bionic", ".internal", "http-server.json");
    const { host, port } = JSON.parse(readFileSync(file, "utf8"));
    client = new LMStudioClient({ baseUrl: `ws://${host}:${port}` });
    const loaded = await client.llm.listLoaded();
    if (!loaded.some((m) => m.identifier === (spec.backend as { identifier: string }).identifier)) {
      throw new Error(`model '${spec.backend.identifier}' is not loaded`);
    }
    backend = new LmsSdkBackend(await client.llm.model(spec.backend.identifier));
    app = await client.system.getLMStudioVersion().then((v) => `${v.version}+${v.build}`, () => null);
  } else {
    backend = new ScriptedBackend(spec.backend.replies);
  }

  const attempts: Record<string, unknown>[] = [];
  for (const task of spec.tasks) {
    for (let attempt = 1; attempt <= spec.repeats; attempt++) {
      const name = `${task.id}-${attempt}`;
      const tracePath = join(spec.outDir, "traces", `${name}.jsonl`);
      if (stop.signal.aborted) {
        attempts.push({ task: task.id, attempt, status: "skipped" });
        continue;
      }
      let outcome: AttemptOutcome;
      let sandbox: string | null = null;
      try {
        sandbox = createSandbox(spec.outDir, name, spec.fixturesRoot, task.fixtures);
        outcome = await runAttempt({ task, attempt, limits: limitsFor(spec, task), backend, sandbox,
          trace: new FileTrace(tracePath), stop: stop.signal, temperature: spec.temperature ?? 0 });
      } catch (e) {
        outcome = { status: "error", answer: "", rounds: 0, toolCalls: 0, limitsHit: [], seconds: 0,
          error: String((e as Error)?.message ?? e).slice(0, 800) };
      }
      attempts.push({ task: task.id, attempt, ...outcome, trace: tracePath, sandbox });
      console.log(`${name}: ${outcome.status} (${outcome.rounds} rounds, ${outcome.toolCalls} tool calls, ` +
        `${outcome.seconds.toFixed(1)} s)${outcome.error ? " " + outcome.error : ""}`);
    }
  }
  await client?.[Symbol.asyncDispose]();
  finish({ schemaVersion: spec.schemaVersion, run: spec.run, backend: spec.backend.type, app,
    stopped: stop.signal.aborted, attempts }, 0);
} catch (e) {
  try { await client?.[Symbol.asyncDispose](); } catch { /* already broken */ }
  finish({ error: String((e as Error)?.message ?? e).slice(0, 800) }, 1);
}
