// Offline tests of the agent harness with the scripted backend (no GPU, no LM Studio):  npm test
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { ScriptedBackend } from "./backend.ts";
import { LIMIT_NOTE, runAttempt } from "./loop.ts";
import { checkSpec, DEFAULT_LIMITS, type Limits, type RunSpec, type ScriptedReply, type TaskSpec } from "./spec.ts";
import { argumentProblems, runTool, TOOL_DEFS } from "./tools.ts";
import { MemoryTrace } from "./trace.ts";

function sandbox(): string {
  const dir = mkdtempSync(join(tmpdir(), "harness-test-"));
  writeFileSync(join(dir, "notes.txt"), "marker: BLUE-HERON-17\n");
  return dir;
}

async function attempt(replies: ScriptedReply[], task: Partial<TaskSpec> = {}, limits: Partial<Limits> = {},
  stop = new AbortController().signal) {
  const t: TaskSpec = { id: "t", prompt: "What is the marker?", tools: ["read_file", "mock_lookup"], ...task };
  const trace = new MemoryTrace();
  const out = await runAttempt({ task: t, attempt: 1, limits: { ...DEFAULT_LIMITS, ...limits },
    backend: new ScriptedBackend({ t: replies }), trace, sandbox: sandbox(), stop, temperature: 0 });
  return { out, events: trace.events, kinds: trace.events.map((e) => e.event) };
}

test("tool call, result back to the model, final answer", async () => {
  const { out, events, kinds } = await attempt([
    { toolCalls: [{ name: "read_file", arguments: { path: "notes.txt" } }] },
    { text: "The marker is BLUE-HERON-17.", reasoning: "the file says so" },
  ]);
  assert.equal(out.status, "done");
  assert.equal(out.answer, "The marker is BLUE-HERON-17.");
  assert.equal(out.rounds, 2);
  assert.deepEqual(kinds, ["task_start", "prediction", "tool_call", "tool_result", "prediction", "task_end"]);
  const result = events.find((e) => e.event === "tool_result")!;
  assert.equal(result.ok, true);
  assert.match(String(result.content), /BLUE-HERON-17/);
  assert.equal(events[4].reasoningChars, "the file says so".length);
});

test("unknown tool and invalid arguments go back as errors, the loop goes on", async () => {
  const { out, events } = await attempt([
    { toolCalls: [{ name: "delete_file", arguments: { path: "x" } }, { name: "read_file", arguments: {} }] },
    { text: "I could not read it." },
  ]);
  assert.equal(out.status, "done");
  const calls = events.filter((e) => e.event === "tool_call");
  assert.deepEqual(calls.map((c) => c.valid), [false, false]);
  const results = events.filter((e) => e.event === "tool_result");
  assert.match(String(results[0].content), /unknown tool/);
  assert.match(String(results[1].content), /argument 'path'/);
});

test("a tool not offered for the task counts as unknown", async () => {
  const { events } = await attempt([{ toolCalls: [{ name: "mock_lookup", arguments: { order_id: "A" } }] }, { text: "ok" }],
    { tools: ["read_file"] });
  assert.match(String(events.find((e) => e.event === "tool_result")!.content), /unknown tool/);
});

test("an unparsed tool call is logged raw and ends the attempt (no repair in M1)", async () => {
  const { out, events } = await attempt([{ text: '{"name": "read_file"}', failure: { error: "bad json", raw: "{oops" } }]);
  assert.equal(out.status, "done");
  const call = events.find((e) => e.event === "tool_call")!;
  assert.equal(call.parsed, false);
  assert.equal(call.raw, "{oops");
});

test("round limit: one more round without tools, status limit", async () => {
  const loop = { toolCalls: [{ name: "read_file", arguments: { path: "notes.txt" } }] };
  const { out, events } = await attempt([loop, loop, { text: "Stopped: the tool limit was reached." }], {}, { maxRounds: 2 });
  assert.equal(out.status, "limit");
  assert.deepEqual(out.limitsHit, ["rounds"]);
  assert.equal(out.rounds, 3);
  const predictions = events.filter((e) => e.event === "prediction");
  assert.deepEqual(predictions.map((e) => (e.toolsOffered as string[]).length), [2, 2, 0]);
  assert.ok(events.some((e) => e.event === "limit_hit" && e.limit === "rounds"));
  assert.ok(LIMIT_NOTE.length > 0);
});

test("tool timeout gives an error result and a limit event", async () => {
  const { out, events } = await attempt([
    { toolCalls: [{ name: "mock_lookup", arguments: { order_id: "SLOW" } }] },
    { text: "The lookup timed out." },
  ], { mock: { SLOW: { result: "late", delayMs: 2000 } } }, { toolTimeoutMs: 100 });
  assert.equal(out.status, "done");
  assert.deepEqual(out.limitsHit, ["tool_timeout"]);
  const result = events.find((e) => e.event === "tool_result")!;
  assert.equal(result.ok, false);
  assert.match(String(result.content), /did not answer within/);
});

test("stop during a prediction ends the attempt as aborted", async () => {
  const stop = new AbortController();
  setTimeout(() => stop.abort(), 50);
  const { out, kinds } = await attempt([{ text: "slow", delayMs: 2000 }], {}, {}, stop.signal);
  assert.equal(out.status, "aborted");
  assert.equal(kinds.at(-1), "task_end");
});

test("wall time limit ends the attempt as limit", async () => {
  const { out, events } = await attempt([{ text: "slow", delayMs: 2000 }], {}, { wallTimeMs: 50 });
  assert.equal(out.status, "limit");
  assert.deepEqual(out.limitsHit, ["wall_time"]);
  assert.ok(events.some((e) => e.event === "limit_hit" && e.limit === "wall_time"));
});

test("read_file stays inside the sandbox and truncates", async () => {
  const dir = sandbox();
  mkdirSync(join(dir, "sub"));
  const outside = mkdtempSync(join(tmpdir(), "harness-outside-"));
  writeFileSync(join(outside, "secret.txt"), "secret");
  const ctx = { sandbox: dir, mock: {}, maxChars: 6, signal: new AbortController().signal };
  const read = (path: string) => runTool({ name: "read_file", arguments: { path } }, ctx);
  assert.equal((await read("notes.txt")).truncated, true);
  assert.match((await read("../" + "x")).content, /error/);
  assert.match((await read(join(outside, "secret.txt"))).content, /outside the working folder/);
  assert.match((await read("sub")).content, /not a file/);
  assert.match((await read("missing.txt")).content, /not found/);
  try {
    symlinkSync(join(outside, "secret.txt"), join(dir, "link.txt"));
    assert.match((await read("link.txt")).content, /outside the working folder/);
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code !== "EPERM") throw e; // Windows needs a privilege for links
  }
});

test("mock lookup: result, error, unknown id", async () => {
  const ctx = { sandbox: sandbox(), maxChars: 100, signal: new AbortController().signal,
    mock: { A: { result: "shipped" }, B: { error: "service unavailable" } } };
  const look = (order_id: string) => runTool({ name: "mock_lookup", arguments: { order_id } }, ctx);
  assert.deepEqual(await look("A"), { ok: true, content: "shipped", truncated: false, bytes: 7 });
  assert.equal((await look("B")).content, "error: service unavailable");
  assert.match((await look("C")).content, /not found/);
  assert.deepEqual(argumentProblems(TOOL_DEFS.mock_lookup, { order_id: 5 }), ["argument 'order_id' must be a non-empty string"]);
});

test("spec check", () => {
  const ok: RunSpec = { schemaVersion: 1, run: "r", repeats: 1, outDir: "x", backend: { type: "scripted", replies: {} },
    tasks: [{ id: "a", prompt: "p", tools: ["read_file"] }] };
  assert.deepEqual(checkSpec(ok), []);
  assert.ok(checkSpec({ ...ok, tasks: [{ id: "a b", prompt: "", tools: ["shell" as never] }] }).length >= 3);
  assert.ok(checkSpec({ ...ok, tasks: [{ id: "a", prompt: "p", tools: [], fixtures: "../up" }] }).length === 1);
  assert.ok(checkSpec({ ...ok, repeats: 0 }).length === 1);
});
