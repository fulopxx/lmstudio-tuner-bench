// The tool loop for one task attempt: rounds, limits, stop, and a trace of every step.
import { createHash } from "node:crypto";
import type { Message, ModelBackend, RoundResult, ToolCall } from "./backend.ts";
import type { Limits, MockToolSpec, RunMeta, Sampling, TaskSpec } from "./spec.ts";
import { DEFAULT_SYSTEM, HARNESS_VERSION } from "./spec.ts";
import { argumentProblems, fail, runTool, toolDefs, type ArgumentProblem, type ToolOutcome } from "./tools.ts";
import type { Trace } from "./trace.ts";

export type AttemptStatus = "done" | "limit" | "aborted" | "error";

export interface AttemptOutcome {
  status: AttemptStatus;
  answer: string;
  rounds: number;
  toolCalls: number;
  limitsHit: string[];
  seconds: number;
  error?: string;
}

export interface AttemptParams {
  run?: string;
  task: TaskSpec;
  attempt: number;
  limits: Limits;
  mocks: Record<string, MockToolSpec>;
  backend: ModelBackend;
  trace: Trace;
  sandbox: string;
  stop: AbortSignal; // set by the core's stop command
  sampling: Sampling;
  meta?: RunMeta;
}

export const LIMIT_NOTE = "[harness] The tool limit for this task is reached. Answer the user now without tools, " +
  "and say if the answer is incomplete.";

const sha = (s: string) => createHash("sha256").update(s).digest("hex").slice(0, 16);

/** Runs a tool with its own timeout; a timeout or stop ends it with an error result, never an exception. */
async function toolWithTimeout(call: ToolCall, p: AttemptParams, signal: AbortSignal, counts: Map<string, number>):
  Promise<{ outcome: ToolOutcome; timedOut: boolean }> {
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  signal.addEventListener("abort", onAbort, { once: true });
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<"timeout">((done) => { timer = setTimeout(() => done("timeout"), p.limits.toolTimeoutMs); });
  try {
    const run = runTool(call, p.mocks, { sandbox: p.sandbox, maxChars: p.limits.maxToolResultChars,
      signal: controller.signal, callCounts: counts });
    const first = await Promise.race([run, timeout]);
    if (first === "timeout") {
      controller.abort();
      return { outcome: fail(`the tool did not answer within ${p.limits.toolTimeoutMs / 1000} s`, "timeout"),
        timedOut: true };
    }
    return { outcome: first, timedOut: false };
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", onAbort);
  }
}

export async function runAttempt(p: AttemptParams): Promise<AttemptOutcome> {
  const started = Date.now();
  const tools = toolDefs(p.task.tools, p.mocks);
  const system = p.task.system ?? DEFAULT_SYSTEM;
  const history: Message[] = [{ role: "system", text: system }, { role: "user", text: p.task.prompt }];
  const wall = new AbortController();
  const wallTimer = setTimeout(() => wall.abort(), p.limits.wallTimeMs);
  const signal = AbortSignal.any([p.stop, wall.signal]);
  const out: AttemptOutcome = { status: "done", answer: "", rounds: 0, toolCalls: 0, limitsHit: [], seconds: 0 };
  const counts = new Map<string, number>();
  let callSeq = 0;
  p.backend.startTask(p.task.id, p.attempt);
  // FA-10: everything needed to re-evaluate this trace on its own
  p.trace.write("task_start", {
    run: p.run ?? null, task: p.task.id, attempt: p.attempt, model: p.meta?.model ?? null,
    contextLength: p.meta?.contextLength ?? null, taskFile: p.meta?.taskFile ?? null,
    taskFileHash: p.meta?.taskFileHash ?? null, harnessVersion: HARNESS_VERSION, sampling: p.sampling,
    limits: p.limits, system, prompt: p.task.prompt, tools: tools.map((t) => t.name),
    toolSchemaHash: sha(JSON.stringify(tools)),
  });

  const stopped = (): boolean => {
    if (!signal.aborted) return false;
    if (p.stop.aborted) {
      out.status = "aborted";
    } else {
      out.status = "limit";
      out.limitsHit.push("wall_time");
      p.trace.write("limit_hit", { limit: "wall_time", value: p.limits.wallTimeMs });
    }
    return true;
  };

  try {
    let finalRound = false; // after the round limit: one more round without tools
    while (true) {
      if (stopped()) break;
      const offered = finalRound ? [] : tools;
      const round = out.rounds++;
      const tStart = new Date();
      let r: RoundResult;
      try {
        r = await p.backend.round(history, offered, { signal, maxTokens: p.limits.maxTokensPerRound,
          sampling: p.sampling });
      } catch (e) {
        if (stopped()) break;
        throw e;
      }
      p.trace.write("prediction", {
        round, t_start: tStart.toISOString(), duration_s: (Date.now() - tStart.getTime()) / 1000,
        toolsOffered: offered.map((t) => t.name), text: r.text, answer: r.answer, reasoningChars: r.reasoningChars,
        stopReason: r.stopReason, promptTokens: r.promptTokens ?? null, outputTokens: r.outputTokens ?? null,
        ttftS: r.ttftS ?? null, tokensPerSecond: r.tokensPerSecond ?? null,
        toolCalls: r.toolCalls.length, toolCallFailures: r.toolCallFailures,
        ...(r.applied ? { applied: r.applied } : {}),
      });
      out.answer = r.answer;
      if (r.stopReason === "userStopped" && stopped()) break;
      for (const f of r.toolCallFailures) {
        p.trace.write("tool_call", { round, call_seq: callSeq++, parsed: false, error: f.error, raw: f.raw ?? null });
      }
      if (!r.toolCalls.length) break; // final answer (also when a call could not be parsed: no repair in M1)

      history.push({ role: "assistant", text: r.answer, toolCalls: r.toolCalls });
      for (const call of r.toolCalls) {
        out.toolCalls++;
        const seq = callSeq++;
        const def = tools.find((t) => t.name === call.name);
        const problems: ArgumentProblem[] = def ? argumentProblems(def.parameters, call.arguments) : [];
        const valid = !!def && problems.length === 0;
        p.trace.write("tool_call", { round, call_seq: seq, parsed: true, id: call.id ?? null, name: call.name,
          arguments: call.arguments ?? null, raw: call.raw ?? null, known: !!def, valid, problems });
        const t0 = Date.now();
        let outcome: ToolOutcome;
        let timedOut = false;
        if (!def) {
          outcome = fail(`unknown tool: ${call.name}`, "unknown_tool");
        } else if (!valid) {
          outcome = fail(problems.map((x) => x.message).join("; "), "invalid_arguments");
        } else {
          ({ outcome, timedOut } = await toolWithTimeout(call, p, signal, counts));
        }
        if (timedOut) {
          out.limitsHit.push("tool_timeout");
          p.trace.write("limit_hit", { limit: "tool_timeout", value: p.limits.toolTimeoutMs, name: call.name, call_seq: seq });
        }
        p.trace.write("tool_result", { round, call_seq: seq, id: call.id ?? null, name: call.name, ok: outcome.ok,
          errorKind: outcome.errorKind ?? null, content: outcome.content, truncated: outcome.truncated,
          bytes: outcome.bytes, seconds: (Date.now() - t0) / 1000 });
        history.push({ role: "tool", text: outcome.content, toolCallId: call.id, toolName: call.name });
      }
      if (finalRound) break; // a call although no tools were offered: it is not run again
      if (out.rounds >= p.limits.maxRounds) {
        out.status = "limit";
        out.limitsHit.push("rounds");
        p.trace.write("limit_hit", { limit: "rounds", value: p.limits.maxRounds });
        history.push({ role: "user", text: LIMIT_NOTE });
        finalRound = true;
      }
    }
  } catch (e) {
    out.status = "error";
    out.error = String((e as Error)?.message ?? e).slice(0, 800);
    p.trace.write("error", { source: "harness", message: out.error });
  } finally {
    clearTimeout(wallTimer);
  }
  out.seconds = (Date.now() - started) / 1000;
  p.trace.write("task_end", { task: p.task.id, attempt: p.attempt, status: out.status, answer: out.answer,
    rounds: out.rounds, toolCalls: out.toolCalls, limitsHit: out.limitsHit, seconds: out.seconds,
    ...(out.error ? { error: out.error } : {}) });
  return out;
}
