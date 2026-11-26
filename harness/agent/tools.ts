// Tools: the built-in read_file inside the sandbox, declarative mock tools (FA-01, FA-02) and argument checks (FA-03).
import { readFileSync, realpathSync, statSync } from "node:fs";
import { resolve, sep } from "node:path";
import type { ToolCall, ToolDef } from "./backend.ts";
import type { ErrorKind, Matcher, MockResponse, MockToolSpec, ParamSchema } from "./spec.ts";

export const READ_FILE: ToolDef = {
  name: "read_file",
  description: "Read a text file from the working folder and return its content.",
  parameters: {
    type: "object",
    properties: { path: { type: "string", description: "Path relative to the working folder" } },
    required: ["path"],
  },
};

/** The definitions offered to the model for a task, in the task's order. Unknown names are left out (checked earlier). */
export function toolDefs(names: string[], mocks: Record<string, MockToolSpec>): ToolDef[] {
  return names.flatMap((name): ToolDef[] => {
    if (name === "read_file") return [READ_FILE];
    const m = mocks[name];
    return m ? [{ name, description: m.description, parameters: m.parameters as Record<string, unknown> }] : [];
  });
}

export interface ArgumentProblem {
  code: "missing_required" | "wrong_type" | "not_in_enum" | "unknown_argument";
  argument: string;
  message: string;
}

function typeOf(v: unknown): string {
  if (Array.isArray(v)) return "array";
  if (v === null) return "null";
  if (typeof v === "number") return Number.isInteger(v) ? "integer" : "number";
  return typeof v;
}

function typeMatches(expected: string, v: unknown): boolean {
  const actual = typeOf(v);
  return actual === expected || (expected === "number" && actual === "integer");
}

/** Checks arguments against the schema subset: required, type, enum, and arguments the schema does not know. */
export function argumentProblems(schema: Record<string, unknown> | ParamSchema,
  args: Record<string, unknown> | undefined): ArgumentProblem[] {
  const s = schema as ParamSchema;
  const props = s.properties ?? {};
  const given = args ?? {};
  const problems: ArgumentProblem[] = [];
  for (const name of s.required ?? []) {
    if (given[name] === undefined || given[name] === null || given[name] === "") {
      problems.push({ code: "missing_required", argument: name, message: `argument '${name}' is required` });
    }
  }
  for (const [name, value] of Object.entries(given)) {
    const p = props[name];
    if (!p) {
      problems.push({ code: "unknown_argument", argument: name, message: `unknown argument '${name}'` });
      continue;
    }
    if (value === undefined || value === null) continue;
    if (p.type && !typeMatches(p.type, value)) {
      problems.push({ code: "wrong_type", argument: name,
        message: `argument '${name}' must be of type ${p.type}, got ${typeOf(value)}` });
    } else if (p.enum && !p.enum.some((e) => JSON.stringify(e) === JSON.stringify(value))) {
      problems.push({ code: "not_in_enum", argument: name,
        message: `argument '${name}' must be one of ${JSON.stringify(p.enum)}` });
    }
  }
  return problems;
}

export interface ToolContext {
  sandbox: string;
  maxChars: number;
  signal: AbortSignal;
  callCounts: Map<string, number>; // per attempt: matching calls per tool and rule, for `sequence`
}

export interface ToolOutcome {
  ok: boolean;
  content: string; // what goes back to the model
  truncated: boolean;
  bytes: number;
  errorKind?: ErrorKind;
}

export const fail = (content: string, errorKind: ErrorKind): ToolOutcome =>
  ({ ok: false, content: `error: ${content}`, truncated: false, bytes: 0, errorKind });

function readFile(path: string, ctx: ToolContext): ToolOutcome {
  const root = realpathSync(ctx.sandbox);
  let full: string;
  try {
    full = realpathSync(resolve(root, path)); // resolves links too, so a link cannot point outside
  } catch {
    return fail(`file not found: ${path}`, "not_found");
  }
  if (full !== root && !full.startsWith(root + sep)) return fail(`path is outside the working folder: ${path}`, "outside_sandbox");
  if (!statSync(full).isFile()) return fail(`not a file: ${path}`, "not_found");
  const text = readFileSync(full, "utf8");
  const truncated = text.length > ctx.maxChars;
  return { ok: true, content: truncated ? text.slice(0, ctx.maxChars) + "\n[truncated]" : text, truncated,
    bytes: Buffer.byteLength(text) };
}

function matches(m: Matcher, value: unknown): boolean {
  if ("any" in m) return value !== undefined;
  if ("equals" in m) return JSON.stringify(m.equals) === JSON.stringify(value);
  return m.one_of.some((x) => JSON.stringify(x) === JSON.stringify(value));
}

/** The response of a mock tool for these arguments: first matching rule, `sequence` by call count, else the default. */
export function mockResponse(name: string, spec: MockToolSpec, args: Record<string, unknown> | undefined,
  counts: Map<string, number>): MockResponse {
  const given = args ?? {};
  const rules = spec.rules ?? [];
  for (let i = 0; i < rules.length; i++) {
    const r = rules[i];
    if (!Object.entries(r.when ?? {}).every(([k, m]) => matches(m, given[k]))) continue;
    if (r.sequence?.length) {
      const key = `${name}#${i}`;
      const n = counts.get(key) ?? 0;
      counts.set(key, n + 1);
      return r.sequence[Math.min(n, r.sequence.length - 1)];
    }
    return r;
  }
  return spec.default;
}

async function runMock(call: ToolCall, spec: MockToolSpec, ctx: ToolContext): Promise<ToolOutcome> {
  const r = mockResponse(call.name, spec, call.arguments, ctx.callCounts);
  if (r.delayMs) {
    await new Promise<void>((done) => {
      const timer = setTimeout(done, r.delayMs);
      ctx.signal.addEventListener("abort", () => { clearTimeout(timer); done(); }, { once: true });
    });
    if (ctx.signal.aborted) return fail("cancelled", "cancelled");
  }
  if (r.error !== undefined) return fail(r.error, r.errorKind ?? "mock_error");
  const content = r.result ?? "";
  const truncated = content.length > ctx.maxChars;
  return { ok: true, content: truncated ? content.slice(0, ctx.maxChars) + "\n[truncated]" : content, truncated,
    bytes: Buffer.byteLength(content) };
}

/** Runs one call that already passed the name and argument checks. Never throws. */
export async function runTool(call: ToolCall, mocks: Record<string, MockToolSpec>, ctx: ToolContext): Promise<ToolOutcome> {
  try {
    if (call.name === "read_file") return readFile(String(call.arguments?.path), ctx);
    const spec = mocks[call.name];
    if (spec) return await runMock(call, spec, ctx);
    return fail(`unknown tool: ${call.name}`, "unknown_tool");
  } catch (e) {
    return fail(String((e as Error).message ?? e), "mock_error");
  }
}
