// Run spec sent by the core on the first stdin line (decision H1), and its validation.

export const SPEC_SCHEMA_VERSION = 2; // the run spec on stdin
export const TRACE_SCHEMA_VERSION = 2; // the JSONL trace lines (FA-12)
export const HARNESS_VERSION = "0.2.0";
export const BUILTIN_TOOLS = ["read_file"] as const;

export interface Limits {
  maxRounds: number; // prediction rounds that may use tools; one more round without tools follows a hit
  toolTimeoutMs: number;
  wallTimeMs: number; // whole task attempt
  maxToolResultChars: number;
  maxTokensPerRound: number;
}

export const DEFAULT_LIMITS: Limits = {
  maxRounds: 6, toolTimeoutMs: 10_000, wallTimeMs: 180_000, maxToolResultChars: 8000, maxTokensPerRound: 2048,
};

/** JSON schema subset understood by the argument validator (FA-03). */
export interface ParamSchema {
  type?: "string" | "integer" | "number" | "boolean" | "object" | "array";
  enum?: unknown[];
  description?: string;
  properties?: Record<string, ParamSchema>;
  required?: string[];
  items?: ParamSchema;
}

export type ErrorKind =
  | "not_found" | "outside_sandbox" | "invalid_arguments" | "unknown_tool" | "timeout" | "mock_error" | "cancelled";

/** What a mock tool answers: a result text, or an error (with its kind), optionally after a delay. */
export interface MockResponse {
  result?: string;
  error?: string;
  errorKind?: ErrorKind; // default mock_error
  delayMs?: number;
}

export type Matcher = { equals: unknown } | { one_of: unknown[] } | { any: true };

/** First matching rule wins (FA-02); `sequence` answers by the number of matching calls so far (last entry repeats). */
export interface MockRule extends MockResponse {
  when?: Record<string, Matcher>;
  sequence?: MockResponse[];
}

/** A declarative mock tool (FA-01). */
export interface MockToolSpec {
  description: string;
  parameters: ParamSchema; // type "object" with properties
  rules?: MockRule[];
  default: MockResponse;
}

export interface TaskSpec {
  id: string;
  prompt: string;
  system?: string;
  fixtures?: string; // folder below fixturesRoot, copied into the sandbox
  tools: string[]; // names of built-in tools or of entries in RunSpec.tools
  limits?: Partial<Limits>;
}

export interface Sampling {
  temperature: number;
  topP?: number;
  topK?: number;
  minP?: number;
  repeatPenalty?: number;
  source?: string;
}

/** One scripted model reply (offline tests): text, tool calls, or a tool call the parser could not read. */
export interface ScriptedReply {
  text?: string;
  reasoning?: string;
  toolCalls?: { name: string; arguments?: Record<string, unknown> }[];
  failure?: { error: string; raw?: string };
  delayMs?: number;
  stopReason?: string; // e.g. maxPredictedTokensReached, contextLengthReached
}

export type BackendSpec =
  | { type: "lmstudio"; identifier: string; apiFile?: string }
  | { type: "scripted"; replies: Record<string, ScriptedReply[] | ScriptedReply[][]> }; // per task: one list, or one per attempt

export interface RunMeta {
  model?: string;
  contextLength?: number;
  taskFile?: string;
  taskFileHash?: string;
}

export interface RunSpec {
  schemaVersion: number;
  run: string;
  backend: BackendSpec;
  tools?: Record<string, MockToolSpec>;
  tasks: TaskSpec[];
  repeats: number;
  limits?: Partial<Limits>;
  sampling?: Sampling;
  meta?: RunMeta;
  outDir: string; // absolute; traces/ and sandbox/ are created below it
  fixturesRoot?: string; // absolute
}

export const DEFAULT_SYSTEM =
  "You are an assistant with tools. Use a tool when the answer depends on data you do not have. " +
  "If a tool fails, tell the user what failed instead of guessing.";

export const DEFAULT_SAMPLING: Sampling = { temperature: 0.7 };

function checkMock(name: string, t: MockToolSpec): string[] {
  const problems: string[] = [];
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) problems.push(`tool name '${name}': letters, digits and _ only`);
  if ((BUILTIN_TOOLS as readonly string[]).includes(name)) problems.push(`tool '${name}' is built in`);
  if (!t.description) problems.push(`tool ${name}: description missing`);
  if (t.parameters?.type !== "object") problems.push(`tool ${name}: parameters must be an object schema`);
  if (!t.default) problems.push(`tool ${name}: default answer missing`);
  return problems;
}

/** Returns the problems of a spec; an empty list means it can run. */
export function checkSpec(spec: RunSpec): string[] {
  const problems: string[] = [];
  if (spec.schemaVersion !== SPEC_SCHEMA_VERSION) problems.push(`schemaVersion must be ${SPEC_SCHEMA_VERSION}`);
  if (!spec.run) problems.push("run id missing");
  if (!spec.outDir) problems.push("outDir missing");
  if (!Number.isInteger(spec.repeats) || spec.repeats < 1) problems.push("repeats must be a positive integer");
  if (!Array.isArray(spec.tasks) || !spec.tasks.length) problems.push("no tasks");
  const b = spec.backend;
  if (b?.type === "lmstudio") {
    if (!b.identifier) problems.push("backend.identifier missing");
  } else if (b?.type === "scripted") {
    if (!b.replies) problems.push("backend.replies missing");
  } else {
    problems.push("backend.type must be lmstudio or scripted");
  }
  for (const [name, t] of Object.entries(spec.tools ?? {})) problems.push(...checkMock(name, t));
  const known = new Set<string>([...BUILTIN_TOOLS, ...Object.keys(spec.tools ?? {})]);
  const ids = new Set<string>();
  for (const t of spec.tasks ?? []) {
    if (!t.id || !/^[A-Za-z0-9_-]+$/.test(t.id)) problems.push(`task id '${t.id}': letters, digits, - and _ only`);
    if (ids.has(t.id)) problems.push(`task id '${t.id}' is not unique`);
    ids.add(t.id);
    if (!t.prompt) problems.push(`task ${t.id}: prompt missing`);
    for (const name of t.tools ?? []) if (!known.has(name)) problems.push(`task ${t.id}: unknown tool ${name}`);
    if (t.fixtures && (t.fixtures.includes("..") || /^[\\/]|^[A-Za-z]:/.test(t.fixtures))) {
      problems.push(`task ${t.id}: fixtures must be a relative folder name`);
    }
  }
  return problems;
}

export function limitsFor(spec: RunSpec, task: TaskSpec): Limits {
  return { ...DEFAULT_LIMITS, ...spec.limits, ...task.limits };
}
