// Model backends behind one interface (decision H6): LM Studio through the SDK, and a scripted one for tests.
import type { ChatMessageData, LLM, LLMTool } from "@lmstudio/sdk";
import { Chat } from "@lmstudio/sdk";
import type { Sampling, ScriptedReply } from "./spec.ts";

export interface ToolCall {
  id?: string;
  name: string;
  arguments?: Record<string, unknown>;
  raw?: string; // the model's raw argument text, when the backend has it
}

export type Message =
  | { role: "system" | "user"; text: string }
  | { role: "assistant"; text: string; toolCalls: ToolCall[] }
  | { role: "tool"; text: string; toolCallId?: string; toolName: string };

export interface ToolDef {
  name: string;
  description: string;
  parameters: Record<string, unknown>; // JSON schema
}

export interface RoundResult {
  text: string; // everything the model produced, reasoning included
  answer: string; // text without the reasoning part
  reasoningChars: number;
  toolCalls: ToolCall[];
  toolCallFailures: { error: string; raw?: string }[];
  stopReason: string;
  promptTokens?: number;
  outputTokens?: number;
  ttftS?: number;
  tokensPerSecond?: number;
}

export interface RoundOptions {
  signal: AbortSignal;
  maxTokens: number;
  sampling: Sampling;
}

export interface ModelBackend {
  startTask(taskId: string, attempt: number): void;
  round(history: Message[], tools: ToolDef[], opts: RoundOptions): Promise<RoundResult>;
}

function toChatData(history: Message[]): ChatMessageData[] {
  return history.map((m): ChatMessageData => {
    if (m.role === "assistant") {
      return {
        role: "assistant",
        content: [
          ...(m.text ? [{ type: "text" as const, text: m.text }] : []),
          ...m.toolCalls.map((c) => ({
            type: "toolCallRequest" as const,
            toolCallRequest: { id: c.id, type: "function" as const, name: c.name, arguments: c.arguments },
          })),
        ],
      };
    }
    if (m.role === "tool") {
      return { role: "tool", content: [{ type: "toolCallResult", content: m.text, toolCallId: m.toolCallId, name: m.toolName }] };
    }
    return { role: m.role, content: [{ type: "text", text: m.text }] };
  });
}

/** One prediction round through the SDK: respond() with rawTools, tool calls collected from the callbacks. */
export class LmsSdkBackend implements ModelBackend {
  private readonly model: LLM;
  constructor(model: LLM) {
    this.model = model;
  }

  startTask(): void {}

  async round(history: Message[], tools: ToolDef[], opts: RoundOptions): Promise<RoundResult> {
    const toolCalls: ToolCall[] = [];
    const toolCallFailures: { error: string; raw?: string }[] = [];
    const rawTools: LLMTool[] = tools.map((t) => ({
      type: "function", function: { name: t.name, description: t.description, parameters: t.parameters as never },
    }));
    const result = await this.model.respond(Chat.from({ messages: toChatData(history) }), {
      rawTools: rawTools.length ? { type: "toolArray", tools: rawTools } : { type: "none" },
      // every sampling value explicitly (FA-20); a missing one would fall back to LM Studio's default
      temperature: opts.sampling.temperature,
      ...(opts.sampling.topP !== undefined ? { topPSampling: opts.sampling.topP } : {}),
      ...(opts.sampling.topK !== undefined ? { topKSampling: opts.sampling.topK } : {}),
      ...(opts.sampling.minP !== undefined ? { minPSampling: opts.sampling.minP } : {}),
      ...(opts.sampling.repeatPenalty !== undefined ? { repeatPenalty: opts.sampling.repeatPenalty } : {}),
      contextOverflowPolicy: "stopAtLimit", // FA-13: overflow must show as a stop reason, not be truncated silently
      maxTokens: opts.maxTokens,
      signal: opts.signal,
      onToolCallRequestEnd: (_callId, info) => {
        const r = info.toolCallRequest;
        toolCalls.push({ id: r.id, name: r.name, arguments: r.arguments, raw: info.rawContent });
      },
      onToolCallRequestFailure: (_callId, error) => {
        toolCallFailures.push({ error: error.message, raw: (error as { rawContent?: string }).rawContent });
      },
    });
    const s = result.stats;
    return {
      text: result.content,
      answer: result.nonReasoningContent,
      reasoningChars: result.reasoningContent.length,
      toolCalls,
      toolCallFailures,
      stopReason: s.stopReason,
      promptTokens: s.promptTokensCount,
      outputTokens: s.predictedTokensCount,
      ttftS: s.timeToFirstTokenSec,
      tokensPerSecond: s.tokensPerSecond,
    };
  }
}

/** Replays fixed replies per task; honours the abort signal like the real backend (stop reason userStopped). */
export class ScriptedBackend implements ModelBackend {
  private replies: ScriptedReply[] = [];
  private next = 0;
  private readonly script: Record<string, ScriptedReply[] | ScriptedReply[][]>;

  constructor(script: Record<string, ScriptedReply[] | ScriptedReply[][]>) {
    this.script = script;
  }

  /** A task's script is one reply list for every attempt, or one list per attempt (the last one repeats). */
  startTask(taskId: string, attempt: number): void {
    const s = this.script[taskId] ?? [];
    const perAttempt = s.length > 0 && Array.isArray(s[0]);
    this.replies = perAttempt ? (s as ScriptedReply[][])[Math.min(attempt, s.length) - 1] : (s as ScriptedReply[]);
    this.next = 0;
  }

  async round(_history: Message[], tools: ToolDef[], opts: RoundOptions): Promise<RoundResult> {
    const reply = this.replies[this.next++] ?? { text: "(no scripted reply left)" };
    if (reply.delayMs) {
      const stopped = await new Promise<boolean>((resolve) => {
        const timer = setTimeout(() => resolve(false), reply.delayMs);
        opts.signal.addEventListener("abort", () => { clearTimeout(timer); resolve(true); }, { once: true });
      });
      if (stopped) return this.result("", "", [], [], "userStopped");
    }
    if (opts.signal.aborted) return this.result("", "", [], [], "userStopped");
    const allowed = new Set(tools.map((t) => t.name));
    // like a real model without tools offered, a scripted call is then plain text
    const calls = (reply.toolCalls ?? []).filter(() => allowed.size > 0)
      .map((c, i) => ({ id: `call-${this.next}-${i}`, name: c.name, arguments: c.arguments, raw: JSON.stringify(c.arguments ?? {}) }));
    const answer = reply.text ?? "";
    const text = (reply.reasoning ? `<think>${reply.reasoning}</think>` : "") + answer;
    return this.result(text, answer, calls, reply.failure ? [reply.failure] : [],
      reply.stopReason ?? (calls.length ? "toolCalls" : "eosFound"), reply.reasoning?.length ?? 0);
  }

  private result(text: string, answer: string, toolCalls: ToolCall[], failures: { error: string; raw?: string }[],
    stopReason: string, reasoningChars = 0): RoundResult {
    return { text, answer, reasoningChars, toolCalls, toolCallFailures: failures, stopReason };
  }
}
