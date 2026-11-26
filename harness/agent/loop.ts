// The tool loop for one task attempt: rounds, limits, stop, and a trace of every step.
import type { Message, ModelBackend, ToolCall } from "./backend.ts";
import type { Limits, TaskSpec } from "./spec.ts";
import { DEFAULT_SYSTEM } from "./spec.ts";
import { argumentProblems, runTool, TOOL_DEFS, type ToolOutcome } from "./tools.ts";
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
  task: TaskSpec;
  attempt: number;
  limits: Limits;
  backend: ModelBackend;
  trace: Trace;
  sandbox: string;
  stop: AbortSignal; // set by the core's stop command
  temperature: number;
}

export const LIMIT_NOTE = "[harness] The tool limit for this task is reached. Answer the user now without tools, " +
  "and say if the answer is incomplete.";

/** Runs a tool with its own timeout; a timeout or stop ends it with an error result, never an exception. */
async function toolWithTimeout(call: ToolCall, p: AttemptParams, signal: AbortSignal):
  Promise<{ outcome: ToolOutcome; timedOut: boolean }> {
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  signal.addEventListener("abort", onAbort, { once: true });
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<"timeout">((done) => { timer = setTimeout(() => done("timeout"), p.limits.toolTimeoutMs); });
  try {
    const run = runTool(call, { sandbox: p.sandbox, mock: p.task.mock ?? {}, maxChars: p.limits.maxToolResultChars,
      signal: controller.signal });
    const first = await Promise.race([run, timeout]);
    if (first === "timeout") {
      controller.abort();
      return { outcome: { ok: false, content: `error: the tool did not answer within ${p.limits.toolTimeoutMs / 1000} s`,
        truncated: false, bytes: 0 }, timedOut: true };
    }
    return { outcome: first, timedOut: false };
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", onAbort);
  }
}

export async function runAttempt(p: AttemptParams): Promise<AttemptOutcome> {
  const started = Date.now();
  const tools = p.task.tools.map((name) => TOOL_DEFS[name]);
  const history: Message[] = [
    { role: "system", text: p.task.system ?? DEFAULT_SYSTEM },
    { role: "user", text: p.task.prompt },
  ];
  const wall = new AbortController();
  const wallTimer = setTimeout(() => wall.abort(), p.limits.wallTimeMs);
  const signal = AbortSignal.any([p.stop, wall.signal]);
  const out: AttemptOutcome = { status: "done", answer: "", rounds: 0, toolCalls: 0, limitsHit: [], seconds: 0 };
  p.backend.startTask(p.task.id);
  p.trace.write("task_start", { task: p.task.id, attempt: p.attempt, tools: p.task.tools, limits: p.limits,
    prompt: p.task.prompt });

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
      let r;
      try {
        r = await p.backend.round(history, offered, { signal, maxTokens: p.limits.maxTokensPerRound,
          temperature: p.temperature });
      } catch (e) {
        if (stopped()) break;
        throw e;
      }
      p.trace.write("prediction", {
        round, toolsOffered: offered.map((t) => t.name), text: r.text, answer: r.answer, reasoningChars: r.reasoningChars,
        stopReason: r.stopReason, promptTokens: r.promptTokens ?? null, outputTokens: r.outputTokens ?? null,
        ttftS: r.ttftS ?? null, tokensPerSecond: r.tokensPerSecond ?? null,
        toolCalls: r.toolCalls.length, toolCallFailures: r.toolCallFailures,
      });
      out.answer = r.answer;
      if (r.stopReason === "userStopped" && stopped()) break;
      for (const f of r.toolCallFailures) {
        p.trace.write("tool_call", { round, parsed: false, error: f.error, raw: f.raw ?? null });
      }
      if (!r.toolCalls.length) break; // final answer (also when a call could not be parsed: no repair in M1)

      history.push({ role: "assistant", text: r.answer, toolCalls: r.toolCalls });
      for (const call of r.toolCalls) {
        out.toolCalls++;
        const def = (p.task.tools as string[]).includes(call.name) ? TOOL_DEFS[call.name as keyof typeof TOOL_DEFS] : undefined;
        const problems = def ? argumentProblems(def, call.arguments) : [`unknown tool: ${call.name}`];
        p.trace.write("tool_call", { round, parsed: true, id: call.id ?? null, name: call.name,
          arguments: call.arguments ?? null, raw: call.raw ?? null, valid: problems.length === 0, problems });
        const t0 = Date.now();
        let outcome: ToolOutcome;
        let timedOut = false;
        if (problems.length) {
          outcome = { ok: false, content: `error: ${problems.join("; ")}`, truncated: false, bytes: 0 };
        } else {
          ({ outcome, timedOut } = await toolWithTimeout(call, p, signal));
        }
        if (timedOut) {
          out.limitsHit.push("tool_timeout");
          p.trace.write("limit_hit", { limit: "tool_timeout", value: p.limits.toolTimeoutMs, name: call.name });
        }
        p.trace.write("tool_result", { round, id: call.id ?? null, name: call.name, ok: outcome.ok,
          content: outcome.content, truncated: outcome.truncated, bytes: outcome.bytes, seconds: (Date.now() - t0) / 1000 });
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
