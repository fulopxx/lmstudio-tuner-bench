// Probe: does a model loaded through the SDK stay loaded after the loading process is gone?
//
//   cd harness && node sdk-persist.ts
//
// A child process loads the tiny model and exits, once after closing the SDK client ("dispose") and once
// abruptly ("exit"). The parent then checks whether the model is still loaded, whether the load settings
// survived and whether the HTTP server can generate with it. Timeouts everywhere, no retries.
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { LMStudioClient } from "@lmstudio/sdk";

const MODEL = "llama-3.2-1b-instruct";
const IDENTIFIER = "bench-persist";
const CONFIG = {
  contextLength: 8192, gpu: { ratio: "max" as const }, flashAttention: true, maxParallelPredictions: 1,
  llamaKCacheQuantizationType: "q8_0" as const, llamaVCacheQuantizationType: "q8_0" as const,
};
const LMS = join(homedir(), ".lmstudio", "bin", "lms.exe");
const APP_DIR = join(homedir(), ".lmstudio", "apps", "bionic", ".internal");

const newClient = () => {
  const { host, port } = JSON.parse(readFileSync(join(APP_DIR, "http-server.json"), "utf8"));
  return new LMStudioClient({ baseUrl: `ws://${host}:${port}` });
};

if (process.argv[2] === "child") {
  const client = newClient();
  await client.llm.load(MODEL, {
    identifier: IDENTIFIER, config: CONFIG, verbose: false, signal: AbortSignal.timeout(120_000),
  });
  if (process.argv[3] === "dispose") await client[Symbol.asyncDispose]();
  process.exit(0);
}

const run = (file: string, args: string[], timeout = 60_000) => {
  const p = spawnSync(file, args, { encoding: "utf8", timeout });
  if (p.error) throw p.error;
  return { code: p.status, text: `${p.stdout}${p.stderr}` };
};
const lms = (...args: string[]) => run(LMS, args);
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const gpu = () => {
  const [used, total, util] = run("nvidia-smi", ["--query-gpu=memory.used,memory.total,utilization.gpu",
    "--format=csv,noheader,nounits"], 15_000).text.trim().split(",").map(Number);
  return { used, total, util };
};

const result: Record<string, unknown> = { model: MODEL, started: new Date().toISOString(), modes: [] };
let startedServer = false;
let exitCode = 1;

try {
  if (!lms("ps").text.includes("No models are currently loaded")) {
    throw new Error("a model is already loaded; unload it first (this script will not unload it)");
  }
  const g = gpu();
  if (g.total - g.used < 3500 || g.util > 30) throw new Error(`GPU not idle: ${g.used} MiB used, ${g.util}% busy`);

  for (const mode of ["dispose", "exit"]) {
    const row: Record<string, unknown> = { mode };
    (result.modes as unknown[]).push(row);
    const before = gpu().used;
    const child = run(process.execPath, [import.meta.filename, "child", mode], 180_000);
    if (child.code !== 0) throw new Error(`child (${mode}) failed: ${child.text.slice(0, 600)}`);
    await sleep(8000);
    row.stillLoaded = lms("ps").text.includes(IDENTIFIER);
    row.vramDeltaMiB = gpu().used - before;
    console.log(`== ${mode}: still loaded after exit: ${row.stillLoaded}, vram +${row.vramDeltaMiB} MiB`);
    if (!row.stillLoaded) continue;

    const client = newClient();
    try {
      const applied = await (await client.llm.model(IDENTIFIER)).getLoadConfig();
      row.applied = { contextLength: applied.contextLength, kv: applied.llamaKCacheQuantizationType,
                      parallel: applied.maxParallelPredictions };
    } finally {
      await client[Symbol.asyncDispose]();
    }
    row.stillLoadedAfterSecondClient = lms("ps").text.includes(IDENTIFIER);

    if (/not running/i.test(lms("server", "status").text)) {
      lms("server", "start");
      startedServer = true;
      await sleep(3000);
    }
    const port = /port\s+(\d+)/.exec(lms("server", "status").text)?.[1];
    if (!port) throw new Error("cannot read the HTTP server port");
    const response = await fetch(`http://127.0.0.1:${port}/v1/chat/completions`, {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: AbortSignal.timeout(60_000),
      body: JSON.stringify({ model: IDENTIFIER, messages: [{ role: "user", content: "Say OK." }],
                             max_tokens: 8, temperature: 0 }),
    });
    const body = await response.json() as { choices?: { message?: { content?: string } }[]; model?: string };
    row.http = { status: response.status, model: body.model, content: body.choices?.[0]?.message?.content };
    console.log(`   settings: ${JSON.stringify(row.applied)} | HTTP ${response.status} via model ${body.model}`);

    lms("unload", IDENTIFIER);
    await sleep(3000);
    row.unloadedByCli = !lms("ps").text.includes(IDENTIFIER);
    console.log(`   unloaded by lms CLI: ${row.unloadedByCli}`);
  }
  exitCode = 0;
} catch (e) {
  result.aborted = String((e as Error).message ?? e);
  console.error("ABORTED:", result.aborted);
} finally {
  try {
    if (lms("ps").text.includes(IDENTIFIER)) lms("unload", IDENTIFIER);
    if (startedServer) lms("server", "stop");
    result.finalPs = lms("ps").text.trim().split("\n")[0];
  } catch (e) {
    console.error("cleanup problem:", String(e));
  }
  const dir = join(import.meta.dirname, "..", "results");
  mkdirSync(dir, { recursive: true });
  const file = join(dir, `sdk_persist_${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}.json`);
  writeFileSync(file, JSON.stringify(result, null, 1));
  console.log("result file:", file);
  process.exit(exitCode);
}
