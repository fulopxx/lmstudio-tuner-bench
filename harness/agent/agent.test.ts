// Offline tests of the agent harness with the scripted backend (no GPU, no LM Studio):  npm test
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { ScriptedBackend } from "./backend.ts";
import { LIMIT_NOTE, runAttempt } from "./loop.ts";
import { checkSpec, DEFAULT_LIMITS, type Limits, type MockToolSpec, type RunSpec, type ScriptedReply,
  type TaskSpec } from "./spec.ts";
import { argumentProblems, mockResponse, runTool } from "./tools.ts";
import { MemoryTrace } from "./trace.ts";

const LOOKUP: MockToolSpec = {
  description: "Look up the status of an order by its id.",
  parameters: { type: "object", properties: { order_id: { type: "string" } }, required: ["order_id"] },
  rules: [
    { when: { order_id: { equals: "A" } }, result: "shipped" },
    { when: { order_id: { equals: "B" } }, error: "service unavailable" },
    { when: { order_id: { equals: "SLOW" } }, result: "late", delayMs: 2000 },
    { when: { order_id: { equals: "P" } }, sequence: [{ result: "pending" }, { result: "pending" }, { result: "done" }] },
  ],
  default: { error: "order not found", errorKind: "not_found" },
};
const COUNT: MockToolSpec = {
  description: "Count items.",
  parameters: { type: "object", properties: { n: { type: "integer" }, unit: { type: "string", enum: ["kg", "pcs"] } },
    required: ["n"] },
  default: { result: "ok" },
};
const MOCKS = { mock_lookup: LOOKUP, count: COUNT };

function sandbox(): string {
  const dir = mkdtempSync(join(tmpdir(), "harness-test-"));
  writeFileSync(join(dir, "notes.txt"), "marker: BLUE-HERON-17\n");
  return dir;
}

async function attempt(replies: ScriptedReply[], task: Partial<TaskSpec> = {}, limits: Partial<Limits> = {},
  stop = new AbortController().signal) {
  const t: TaskSpec = { id: "t", prompt: "What is the marker?", tools: ["read_file", "mock_lookup", "count"], ...task };
  const trace = new MemoryTrace();
  const out = await runAttempt({ run: "r", task: t, attempt: 1, limits: { ...DEFAULT_LIMITS, ...limits }, mocks: MOCKS,
    backend: new ScriptedBackend({ t: replies }), trace, sandbox: sandbox(), stop,
    sampling: { temperature: 0.7, topP: 0.8 }, meta: { model: "m", contextLength: 8192 } });
  return { out, events: trace.events, kinds: trace.events.map((e) => e.event) };
}

const results = (events: Record<string, unknown>[]) => events.filter((e) => e.event === "tool_result");

test("tool call, result back to the model, final answer; run metadata in task_start", async () => {
  const { out, events, kinds } = await attempt([
    { toolCalls: [{ name: "read_file", arguments: { path: "notes.txt" } }] },
    { text: "The marker is BLUE-HERON-17.", reasoning: "the file says so" },
  ]);
  assert.equal(out.status, "done");
  assert.equal(out.answer, "The marker is BLUE-HERON-17.");
  assert.deepEqual(kinds, ["task_start", "prediction", "tool_call", "tool_result", "prediction", "task_end"]);
  const start = events[0];
  assert.equal(start.model, "m");
  assert.deepEqual(start.sampling, { temperature: 0.7, topP: 0.8 });
  assert.equal(typeof start.toolSchemaHash, "string");
  assert.equal(typeof events[1].duration_s, "number");
  assert.equal(events[2].call_seq, 0);
  assert.equal(events[3].call_seq, 0);
  assert.equal(events[3].ok, true);
  assert.equal(events[4].reasoningChars, "the file says so".length);
});

test("unknown tool and invalid arguments go back as errors with their kind", async () => {
  const { out, events } = await attempt([
    { toolCalls: [{ name: "delete_file", arguments: { path: "x" } }, { name: "read_file", arguments: {} }] },
    { text: "I could not read it." },
  ]);
  assert.equal(out.status, "done");
  const calls = events.filter((e) => e.event === "tool_call");
  assert.deepEqual(calls.map((c) => [c.known, c.valid]), [[false, false], [true, false]]);
  assert.deepEqual(results(events).map((r) => r.errorKind), ["unknown_tool", "invalid_arguments"]);
  assert.equal((calls[1].problems as { code: string }[])[0].code, "missing_required");
});

test("a tool not offered for the task counts as unknown", async () => {
  const { events } = await attempt([{ toolCalls: [{ name: "mock_lookup", arguments: { order_id: "A" } }] }, { text: "ok" }],
    { tools: ["read_file"] });
  assert.equal(results(events)[0].errorKind, "unknown_tool");
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
  assert.deepEqual(predictions.map((e) => (e.toolsOffered as string[]).length), [3, 3, 0]);
  assert.ok(events.some((e) => e.event === "limit_hit" && e.limit === "rounds"));
  assert.ok(LIMIT_NOTE.length > 0);
});

test("tool timeout gives an error result of kind timeout and a limit event", async () => {
  const { out, events } = await attempt([
    { toolCalls: [{ name: "mock_lookup", arguments: { order_id: "SLOW" } }] },
    { text: "The lookup timed out." },
  ], {}, { toolTimeoutMs: 100 });
  assert.equal(out.status, "done");
  assert.deepEqual(out.limitsHit, ["tool_timeout"]);
  const result = results(events)[0];
  assert.equal(result.ok, false);
  assert.equal(result.errorKind, "timeout");
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

test("scripted stop reason and per-attempt replies", async () => {
  const { events } = await attempt([{ text: "", reasoning: "long thinking", stopReason: "maxPredictedTokensReached" }]);
  assert.equal(events.find((e) => e.event === "prediction")!.stopReason, "maxPredictedTokensReached");
  const b = new ScriptedBackend({ t: [[{ text: "first" }], [{ text: "second" }]] });
  const opts = { signal: new AbortController().signal, maxTokens: 10, sampling: { temperature: 0 } };
  b.startTask("t", 2);
  assert.equal((await b.round([], [], opts)).answer, "second");
  b.startTask("t", 5); // beyond the list: the last one repeats
  assert.equal((await b.round([], [], opts)).answer, "second");
});

test("read_file stays inside the sandbox and truncates", async () => {
  const dir = sandbox();
  mkdirSync(join(dir, "sub"));
  const outside = mkdtempSync(join(tmpdir(), "harness-outside-"));
  writeFileSync(join(outside, "secret.txt"), "secret");
  const ctx = { sandbox: dir, maxChars: 6, signal: new AbortController().signal, callCounts: new Map() };
  const read = (path: string) => runTool({ name: "read_file", arguments: { path } }, {}, ctx);
  assert.equal((await read("notes.txt")).truncated, true);
  assert.equal((await read(join(outside, "secret.txt"))).errorKind, "outside_sandbox");
  assert.equal((await read("sub")).errorKind, "not_found");
  assert.equal((await read("missing.txt")).errorKind, "not_found");
  try {
    symlinkSync(join(outside, "secret.txt"), join(dir, "link.txt"));
    assert.equal((await read("link.txt")).errorKind, "outside_sandbox");
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code !== "EPERM") throw e; // Windows may need a privilege for links
  }
});

test("mock rules: first match, error kinds, default, sequence by call count", async () => {
  const ctx = { sandbox: sandbox(), maxChars: 100, signal: new AbortController().signal, callCounts: new Map() };
  const look = (order_id: string) => runTool({ name: "mock_lookup", arguments: { order_id } }, MOCKS, ctx);
  assert.deepEqual(await look("A"), { ok: true, content: "shipped", truncated: false, bytes: 7 });
  const b = await look("B");
  assert.equal(b.content, "error: service unavailable");
  assert.equal(b.errorKind, "mock_error");
  assert.equal((await look("Z")).errorKind, "not_found");
  assert.deepEqual([(await look("P")).content, (await look("P")).content, (await look("P")).content, (await look("P")).content],
    ["pending", "pending", "done", "done"]);
  const counts = new Map<string, number>();
  assert.equal(mockResponse("mock_lookup", LOOKUP, { order_id: "P" }, counts).result, "pending");
  assert.equal(mockResponse("mock_lookup", LOOKUP, { order_id: "P" }, counts).result, "pending");
  assert.equal(mockResponse("mock_lookup", LOOKUP, { order_id: "P" }, new Map()).result, "pending"); // fresh attempt
});

test("argument validator: required, type, enum, unknown argument", () => {
  const codes = (args: Record<string, unknown>) => argumentProblems(COUNT.parameters, args).map((p) => p.code);
  assert.deepEqual(codes({ n: 3, unit: "kg" }), []);
  assert.deepEqual(codes({ n: "3" }), ["wrong_type"]); // a number sent as a string is not converted
  assert.deepEqual(codes({ n: 2.5 }), ["wrong_type"]);
  assert.deepEqual(codes({ n: 1, unit: "box" }), ["not_in_enum"]);
  assert.deepEqual(codes({ unit: "kg", extra: 1 }), ["missing_required", "unknown_argument"]);
});

test("spec check", () => {
  const ok: RunSpec = { schemaVersion: 2, run: "r", repeats: 1, outDir: "x", backend: { type: "scripted", replies: {} },
    tools: MOCKS, tasks: [{ id: "a", prompt: "p", tools: ["read_file", "mock_lookup"] }] };
  assert.deepEqual(checkSpec(ok), []);
  assert.ok(checkSpec({ ...ok, tasks: [{ id: "a b", prompt: "", tools: ["shell"] }] }).length >= 3);
  assert.equal(checkSpec({ ...ok, tasks: [{ id: "a", prompt: "p", tools: [], fixtures: "../up" }] }).length, 1);
  assert.equal(checkSpec({ ...ok, repeats: 0 }).length, 1);
  assert.equal(checkSpec({ ...ok, schemaVersion: 1 }).length, 1);
  assert.equal(checkSpec({ ...ok, tools: { ...MOCKS, read_file: COUNT } }).length, 1);
});
