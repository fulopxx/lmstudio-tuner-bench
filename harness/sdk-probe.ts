// Probe: which load settings does the official SDK really apply on the installed LM Studio?
//
//   cd harness && node sdk-probe.ts
//
// Loads a tiny model with different settings through @lmstudio/sdk, reads the applied configuration
// back, measures VRAM growth and decode speed, and checks that LM Studio's per-model config files stay
// untouched. Every step has a timeout, nothing is retried, only models loaded here are unloaded.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { LMStudioClient } from "@lmstudio/sdk";

const MODEL = "llama-3.2-1b-instruct";
const IDENTIFIER = "bench-sdk";
const LOAD_TIMEOUT_MS = 120_000;
const PREDICT_TIMEOUT_MS = 120_000;
const MIN_FREE_MIB = 3500;
const MAX_UTIL = 30;
const LMS = join(homedir(), ".lmstudio", "bin", "lms.exe");
const APP_DIR = join(homedir(), ".lmstudio", "apps", "bionic", ".internal");
const CONFIG_DIR = join(APP_DIR, "user-concrete-model-default-config");

/** LM Studio writes the port of its own API (not the one of `lms server start`) into this file. */
function apiBaseUrl(): string {
  const { host, port } = JSON.parse(readFileSync(join(APP_DIR, "http-server.json"), "utf8"));
  return `ws://${host}:${port}`;
}

const threads = (n: number) => ({
  enabled: true,
  disabledParameters: [],
  overrideParameters: [{ key: "--threads", value: String(n) }],
  excludeAllConfig: false,
});
const base = { flashAttention: true, maxParallelPredictions: 1 };
const q8 = { llamaKCacheQuantizationType: "q8_0" as const, llamaVCacheQuantizationType: "q8_0" as const };
const fp16 = { llamaKCacheQuantizationType: false as const, llamaVCacheQuantizationType: false as const };

const CASES = [
  { id: "gpu-fp16", config: { ...base, ...fp16, contextLength: 32768, gpu: { ratio: "max" as const } } },
  { id: "gpu-q8", config: { ...base, ...q8, contextLength: 32768, gpu: { ratio: "max" as const } } },
  { id: "gpu-half", config: { ...base, ...fp16, contextLength: 4096, gpu: { ratio: 0.5 } } },
  { id: "cpu-t2", config: { ...base, ...fp16, contextLength: 4096, gpu: { ratio: "off" as const },
                            llamaCppArgumentsOverride: threads(2) } },
  { id: "cpu-t8", config: { ...base, ...fp16, contextLength: 4096, gpu: { ratio: "off" as const },
                            llamaCppArgumentsOverride: threads(8) } },
];

const run = (file: string, args: string[], timeout = 60_000) =>
  execFileSync(file, args, { encoding: "utf8", timeout, stdio: ["ignore", "pipe", "pipe"] });

const lms = (...args: string[]) => run(LMS, args);

function gpu() {
  const [used, total, util] = run("nvidia-smi", ["--query-gpu=memory.used,memory.total,utilization.gpu",
    "--format=csv,noheader,nounits"], 15_000).trim().split(",").map(Number);
  return { used, total, util };
}

function snapshot(dir: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const entry of readdirSync(dir, { withFileTypes: true, recursive: true })) {
    if (!entry.isFile()) continue;
    const path = join(entry.parentPath, entry.name);
    out[path] = createHash("sha256").update(readFileSync(path)).digest("hex");
  }
  return out;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const median = (v: number[]) => [...v].sort((a, b) => a - b)[Math.floor(v.length / 2)];
const prompt = (tag: string) =>
  `Run id ${tag}.\n` +
  Array.from({ length: 60 }, (_, i) =>
    `${i}. The sensor node ${i} reports temperature ${20 + (i % 17)} C, voltage ` +
    `${(3 + (i % 5) / 10).toFixed(1)} V and status code ${(i * 7) % 101}.`).join("\n") +
  "\n\nSummarize the data above in a short paragraph.";

const result: Record<string, unknown> = { model: MODEL, started: new Date().toISOString(), cases: [] };
// The SDK may reject a promise of its own (e.g. connection loss): stop cleanly instead of crashing.
process.on("unhandledRejection", (e) => {
  console.error("ABORTED (unhandled rejection):", String((e as Error)?.message ?? e).slice(0, 600));
  try {
    if (lms("ps").includes(IDENTIFIER)) lms("unload", IDENTIFIER);
  } finally {
    process.exit(1);
  }
});
let client: LMStudioClient | undefined;
let exitCode = 1;

try {
  if (!lms("ps").includes("No models are currently loaded") && lms("ps").trim() !== "") {
    throw new Error("a model is already loaded; unload it first (this script will not unload it)");
  }
  const g = gpu();
  if (g.total - g.used < MIN_FREE_MIB || g.util > MAX_UTIL) {
    throw new Error(`GPU not idle: ${g.total - g.used} MiB free, ${g.util}% busy`);
  }
  const before = snapshot(CONFIG_DIR);
  // The SDK's automatic port discovery did not find LM Studio, and the port of `lms server start`
  // does not accept the SDK's WebSocket, so the port is read from LM Studio's own file.
  result.baseUrl = apiBaseUrl();
  client = new LMStudioClient({ baseUrl: result.baseUrl as string });

  for (const c of CASES) {
    const row: Record<string, unknown> = { id: c.id, requested: c.config };
    (result.cases as unknown[]).push(row);
    console.log(`== ${c.id}`);
    try {
      await sleep(2000);
      const vramBefore = gpu().used;
      const t0 = Date.now();
      const model = await client.llm.load(MODEL, {
        identifier: IDENTIFIER, config: c.config, verbose: false, signal: AbortSignal.timeout(LOAD_TIMEOUT_MS),
      });
      try {
        row.loadSeconds = (Date.now() - t0) / 1000;
        await sleep(2000);
        row.vramDeltaMiB = gpu().used - vramBefore;
        const applied: Record<string, unknown> = { ...(await model.getLoadConfig()) };
        delete applied.promptTemplate;
        row.applied = applied;
        const speeds: number[] = [];
        for (let i = 0; i < 3; i++) { // first one is the warm-up
          const answer = await model.respond([{ role: "user", content: prompt(`${c.id}-${i}-${Date.now()}`) }],
            { maxTokens: 150, temperature: 0, signal: AbortSignal.timeout(PREDICT_TIMEOUT_MS) });
          const { tokensPerSecond, predictedTokensCount, promptTokensCount } = answer.stats;
          if (tokensPerSecond === undefined) throw new Error("no tokensPerSecond in the prediction stats");
          if (i > 0) speeds.push(tokensPerSecond);
          row.lastRun = { predictedTokensCount, promptTokensCount };
        }
        row.runs = speeds.map((v) => Math.round(v * 100) / 100);
        row.decodeTokS = Math.round(median(speeds) * 100) / 100;
        row.status = "ok";
        console.log(`   vram +${row.vramDeltaMiB} MiB | decode ${row.decodeTokS} t/s (runs ${row.runs})`);
      } finally {
        await model.unload();
      }
    } catch (e) {
      row.status = "fail";
      row.error = String((e as Error).message ?? e).slice(0, 600);
      console.log(`   FAIL: ${row.error}`);
      if (/abort|timeout/i.test(String(row.error))) throw new Error("timeout; stopping without retry");
    }
  }
  const after = snapshot(CONFIG_DIR);
  result.configFilesUnchanged = JSON.stringify(before) === JSON.stringify(after);
  console.log("LM Studio config files unchanged:", result.configFilesUnchanged);
  exitCode = (result.cases as { status?: string }[]).every((r) => r.status === "ok") ? 0 : 2;
} catch (e) {
  result.aborted = String((e as Error).message ?? e);
  console.error("ABORTED:", result.aborted);
} finally {
  try {
    await client?.[Symbol.asyncDispose]();
    if (lms("ps").includes(IDENTIFIER)) lms("unload", IDENTIFIER);
  } catch (e) {
    console.error("cleanup problem:", String(e));
  }
  const dir = join(import.meta.dirname, "..", "results");
  mkdirSync(dir, { recursive: true });
  const file = join(dir, `sdk_probe_${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}.json`);
  writeFileSync(file, JSON.stringify(result, null, 1));
  console.log("result file:", file);
  process.exit(exitCode);
}
