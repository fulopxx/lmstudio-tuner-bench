// Probe: single-round tool calls with respond() + rawTools (harness decision H6, before implementation).
//
//   cd harness && node tools-probe.ts --models llama-3.2-1b-instruct,qwen3-8b
//
// Per model: C1 a tool call is expected (what the callbacks, the result and the stats show), C2 the tool result is
// sent back and a final answer is expected, C3 no tool is needed, C4 an abort during the prediction. Every step
// has a timeout, nothing is retried, only the model loaded here is unloaded. Results: results/tools_probe_<time>.json.
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { parseArgs } from "node:util";
import { Chat, LMStudioClient, type ChatMessageData, type LLM, type LLMTool, type ToolCallRequest } from "@lmstudio/sdk";
import { toSdkConfig } from "./load-config.ts";
import { baseSettings } from "./spec-probe-lib.ts";

const IDENTIFIER = "bench-tools";
const LMS = join(homedir(), ".lmstudio", "bin", "lms.exe");
const APP_DIR = join(homedir(), ".lmstudio", "apps", "bionic", ".internal");
const LOAD_TIMEOUT_MS = 360_000;
const PREDICT_TIMEOUT_MS = 180_000;
const MIN_FREE_MIB = 5692;
const MAX_UTIL = 30;

const { values: args } = parseArgs({ options: { models: { type: "string" }, context: { type: "string" } } });
const models = (args.models ?? "llama-3.2-1b-instruct").split(",").map((m) => m.trim()).filter(Boolean);
const contextLength = Number(args.context ?? 4096);

const run = (file: string, argv: string[], timeout = 60_000) =>
  execFileSync(file, argv, { encoding: "utf8", timeout, stdio: ["ignore", "pipe", "pipe"] });
const lms = (...argv: string[]) => run(LMS, argv);
const msg = (e: unknown) => String((e as Error)?.message ?? e).slice(0, 800);

function apiBaseUrl(): string {
  const file = process.env.LMS_API_FILE ?? join(APP_DIR, "http-server.json");
  const { host, port } = JSON.parse(readFileSync(file, "utf8"));
  return `ws://${host}:${port}`;
}
function gpu() {
  const [used, total, util] = run("nvidia-smi", ["--query-gpu=memory.used,memory.total,utilization.gpu",
    "--format=csv,noheader,nounits"], 15_000).trim().split(",").map(Number);
  return { used, total, util };
}

const TOOLS: LLMTool[] = [
  {
    type: "function",
    function: {
      name: "read_file",
      description: "Read a text file from the working folder and return its content.",
      parameters: { type: "object", properties: { path: { type: "string", description: "Relative path" } },
        required: ["path"] },
    },
  },
  {
    type: "function",
    function: {
      name: "mock_lookup",
      description: "Look up the status of an order by its id.",
      parameters: { type: "object", properties: { order_id: { type: "string" } }, required: ["order_id"] },
    },
  },
];
const FILE_CONTENT = "release: 4.2.1\nowner: build team\nmarker: BLUE-HERON-17\n";
const SYSTEM = "You are an assistant with tools. Use a tool when the answer depends on data you do not have.";

/** Collects every callback of one prediction, in order, with the time since the start. */
function recorder() {
  const t0 = Date.now();
  const events: Record<string, unknown>[] = [];
  const at = () => (Date.now() - t0) / 1000;
  const requests: ToolCallRequest[] = [];
  let fragments = 0;
  return {
    events, requests, fragmentCount: () => fragments,
    callbacks: {
      onPredictionFragment: () => { fragments++; },
      onToolCallRequestStart: (callId: number, info: { toolCallId?: string }) =>
        events.push({ t: at(), ev: "start", callId, toolCallId: info.toolCallId ?? null }),
      onToolCallRequestNameReceived: (callId: number, name: string) => events.push({ t: at(), ev: "name", callId, name }),
      onToolCallRequestArgumentFragmentGenerated: (callId: number, content: string) =>
        events.push({ t: at(), ev: "argFragment", callId, content }),
      onToolCallRequestEnd: (callId: number, info: { toolCallRequest: ToolCallRequest; rawContent: string | undefined }) => {
        requests.push(info.toolCallRequest);
        events.push({ t: at(), ev: "end", callId, toolCallRequest: info.toolCallRequest, rawContent: info.rawContent ?? null });
      },
      onToolCallRequestFailure: (callId: number, error: Error & { rawContent?: string }) =>
        events.push({ t: at(), ev: "failure", callId, error: msg(error), rawContent: error.rawContent ?? null }),
    },
  };
}

async function predict(model: LLM, chat: Chat, row: Record<string, unknown>, signal?: AbortSignal) {
  const rec = recorder();
  const t0 = Date.now();
  try {
    const result = await model.respond(chat, {
      rawTools: { type: "toolArray", tools: TOOLS }, temperature: 0, maxTokens: 400,
      signal: signal ?? AbortSignal.timeout(PREDICT_TIMEOUT_MS), ...rec.callbacks,
    });
    Object.assign(row, {
      seconds: (Date.now() - t0) / 1000, content: result.content, nonReasoningContent: result.nonReasoningContent,
      reasoningChars: result.reasoningContent.length, stopReason: result.stats.stopReason,
      predictedTokens: result.stats.predictedTokensCount ?? null,
    });
  } catch (e) {
    row.seconds = (Date.now() - t0) / 1000;
    row.error = msg(e);
  }
  row.events = rec.events;
  row.fragments = rec.fragmentCount();
  row.toolCallRequests = rec.requests;
  return rec.requests;
}

const result: Record<string, unknown> = { started: new Date().toISOString(), contextLength, models: [] as unknown[] };
let client: LMStudioClient | undefined;
let exitCode = 1;

process.on("unhandledRejection", (e) => {
  console.error("ABORTED (unhandled rejection):", msg(e));
  try { if (lms("ps").includes(IDENTIFIER)) lms("unload", IDENTIFIER); } finally { process.exit(1); }
});

try {
  const loaded = lms("ps", "--json").trim(); // the plain `lms ps` text goes partly to stderr
  if (loaded && JSON.parse(loaded).length) throw new Error("a model is already loaded; unload it first");
  const g = gpu();
  result.gpuAtStart = g;
  if (g.total - g.used < MIN_FREE_MIB || g.util > MAX_UTIL) throw new Error(`GPU not idle: ${g.total - g.used} MiB free, ${g.util}% busy`);
  client = new LMStudioClient({ baseUrl: apiBaseUrl() });
  result.app = await client.system.getLMStudioVersion().then((v) => `${v.version}+${v.build}`, () => null);

  for (const key of models) {
    const m: Record<string, unknown> = { model: key, cases: {} };
    (result.models as unknown[]).push(m);
    const cases = m.cases as Record<string, Record<string, unknown>>;
    console.log(`== ${key}`);
    try {
      const model = await client.llm.load(key, {
        identifier: IDENTIFIER, config: toSdkConfig(baseSettings(contextLength)), verbose: false,
        signal: AbortSignal.timeout(LOAD_TIMEOUT_MS),
      });
      try {
        // C1: a tool call is expected
        const ask = "What is the marker in the file notes.txt?";
        const c1: Record<string, unknown> = {};
        cases.C1 = c1;
        const reqs = await predict(model, Chat.from([{ role: "system", content: SYSTEM }, { role: "user", content: ask }]), c1);
        console.log(`   C1 stop=${c1.stopReason} calls=${JSON.stringify(reqs)} ${c1.error ?? ""}`);

        // C2: send the tool result back (only if C1 produced a call)
        const c2: Record<string, unknown> = {};
        cases.C2 = c2;
        if (reqs.length) {
          const req = reqs[0];
          const messages: ChatMessageData[] = [
            { role: "system", content: [{ type: "text", text: SYSTEM }] },
            { role: "user", content: [{ type: "text", text: ask }] },
            { role: "assistant", content: [
              ...(c1.nonReasoningContent ? [{ type: "text" as const, text: String(c1.nonReasoningContent) }] : []),
              { type: "toolCallRequest", toolCallRequest: req }] },
            { role: "tool", content: [{ type: "toolCallResult", content: req.name === "read_file" ? FILE_CONTENT
              : `error: unknown tool ${req.name}`, toolCallId: req.id }] },
          ];
          await predict(model, Chat.from({ messages }), c2);
          c2.answerHasMarker = String(c2.content ?? "").includes("BLUE-HERON-17");
          console.log(`   C2 stop=${c2.stopReason} marker=${c2.answerHasMarker} ${c2.error ?? ""}`);
        } else {
          c2.skipped = "no tool call in C1";
        }

        // C3: no tool needed
        const c3: Record<string, unknown> = {};
        cases.C3 = c3;
        await predict(model, Chat.from([{ role: "system", content: SYSTEM }, { role: "user", content: "What is 17 + 25? Answer with the number only." }]), c3);
        console.log(`   C3 stop=${c3.stopReason} calls=${(c3.toolCallRequests as unknown[]).length} ${c3.error ?? ""}`);

        // C4: abort shortly after the prediction starts
        const c4: Record<string, unknown> = {};
        cases.C4 = c4;
        const controller = new AbortController();
        setTimeout(() => controller.abort(new Error("probe abort")), 300);
        await predict(model, Chat.from([{ role: "user", content: "Write a 300-word story about a lighthouse." }]), c4, controller.signal);
        console.log(`   C4 stop=${c4.stopReason ?? "-"} error=${c4.error ?? "-"} fragments=${c4.fragments}`);
        m.status = "ok";
      } finally {
        await model.unload();
      }
    } catch (e) {
      m.status = "fail";
      m.error = msg(e);
      console.log(`   FAIL: ${m.error}`);
      if (/timeout/i.test(String(m.error))) throw new Error("timeout; stopping without retry");
    }
  }
  exitCode = (result.models as { status?: string }[]).every((r) => r.status === "ok") ? 0 : 2;
} catch (e) {
  result.aborted = msg(e);
  console.error("ABORTED:", result.aborted);
} finally {
  try {
    await client?.[Symbol.asyncDispose]();
    if (lms("ps").includes(IDENTIFIER)) lms("unload", IDENTIFIER);
  } catch (e) {
    console.error("cleanup problem:", msg(e));
  }
  const dir = join(import.meta.dirname, "..", "results");
  mkdirSync(dir, { recursive: true });
  const file = join(dir, `tools_probe_${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}.json`);
  writeFileSync(file, JSON.stringify(result, null, 1));
  console.log("result file:", file);
  process.exit(exitCode);
}
