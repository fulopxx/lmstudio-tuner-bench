// The M1 tools (decision H7): read_file inside the sandbox and a deterministic mock lookup.
import { readFileSync, realpathSync, statSync } from "node:fs";
import { resolve, sep } from "node:path";
import type { ToolCall, ToolDef } from "./backend.ts";
import type { MockEntry, ToolName } from "./spec.ts";

export const TOOL_DEFS: Record<ToolName, ToolDef> = {
  read_file: {
    name: "read_file",
    description: "Read a text file from the working folder and return its content.",
    parameters: {
      type: "object",
      properties: { path: { type: "string", description: "Path relative to the working folder" } },
      required: ["path"],
    },
  },
  mock_lookup: {
    name: "mock_lookup",
    description: "Look up the status of an order by its id.",
    parameters: { type: "object", properties: { order_id: { type: "string" } }, required: ["order_id"] },
  },
};

export interface ToolContext {
  sandbox: string;
  mock: Record<string, MockEntry>;
  maxChars: number;
  signal: AbortSignal;
}

export interface ToolOutcome {
  ok: boolean;
  content: string; // what goes back to the model
  truncated: boolean;
  bytes: number;
}

const fail = (content: string): ToolOutcome => ({ ok: false, content: `error: ${content}`, truncated: false, bytes: 0 });

/** Missing or non-string required arguments; the call is then not executed. */
export function argumentProblems(def: ToolDef, args: Record<string, unknown> | undefined): string[] {
  const required = (def.parameters.required as string[] | undefined) ?? [];
  return required.filter((k) => typeof args?.[k] !== "string" || (args[k] as string) === "")
    .map((k) => `argument '${k}' must be a non-empty string`);
}

function readFile(path: string, ctx: ToolContext): ToolOutcome {
  const root = realpathSync(ctx.sandbox);
  let full: string;
  try {
    full = realpathSync(resolve(root, path)); // resolves links too, so a link cannot point outside
  } catch {
    return fail(`file not found: ${path}`);
  }
  if (full !== root && !full.startsWith(root + sep)) return fail(`path is outside the working folder: ${path}`);
  if (!statSync(full).isFile()) return fail(`not a file: ${path}`);
  const text = readFileSync(full, "utf8");
  const truncated = text.length > ctx.maxChars;
  return { ok: true, content: truncated ? text.slice(0, ctx.maxChars) + "\n[truncated]" : text, truncated,
    bytes: Buffer.byteLength(text) };
}

async function mockLookup(orderId: string, ctx: ToolContext): Promise<ToolOutcome> {
  const entry = ctx.mock[orderId];
  if (!entry) return fail(`order not found: ${orderId}`);
  if (entry.delayMs) {
    await new Promise<void>((done) => {
      const timer = setTimeout(done, entry.delayMs);
      ctx.signal.addEventListener("abort", () => { clearTimeout(timer); done(); }, { once: true });
    });
    if (ctx.signal.aborted) return fail("cancelled");
  }
  if (entry.error) return fail(entry.error);
  const content = entry.result ?? "";
  return { ok: true, content, truncated: false, bytes: Buffer.byteLength(content) };
}

/** Runs one call that already passed the name and argument checks. Never throws. */
export async function runTool(call: ToolCall, ctx: ToolContext): Promise<ToolOutcome> {
  try {
    if (call.name === "read_file") return readFile(String(call.arguments?.path), ctx);
    if (call.name === "mock_lookup") return await mockLookup(String(call.arguments?.order_id), ctx);
    return fail(`unknown tool: ${call.name}`);
  } catch (e) {
    return fail(String((e as Error).message ?? e));
  }
}
