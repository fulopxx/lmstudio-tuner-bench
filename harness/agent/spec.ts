// Run spec sent by the core on the first stdin line (decision H1), and its validation.

export const SCHEMA_VERSION = 1;
export const TOOL_NAMES = ["read_file", "mock_lookup"] as const;
export type ToolName = (typeof TOOL_NAMES)[number];

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

export interface MockEntry {
  result?: string;
  error?: string;
  delayMs?: number;
}

export interface TaskSpec {
  id: string;
  prompt: string;
  system?: string;
  fixtures?: string; // folder below fixturesRoot, copied into the sandbox
  tools: ToolName[];
  mock?: Record<string, MockEntry>; // mock_lookup table: order id -> entry
  limits?: Partial<Limits>;
}

/** One scripted model reply (offline tests): text, tool calls, or a tool call the parser could not read. */
export interface ScriptedReply {
  text?: string;
  reasoning?: string;
  toolCalls?: { name: string; arguments?: Record<string, unknown> }[];
  failure?: { error: string; raw?: string };
  delayMs?: number;
}

export type BackendSpec =
  | { type: "lmstudio"; identifier: string; apiFile?: string }
  | { type: "scripted"; replies: Record<string, ScriptedReply[]> }; // task id -> replies in order

export interface RunSpec {
  schemaVersion: number;
  run: string;
  backend: BackendSpec;
  tasks: TaskSpec[];
  repeats: number;
  limits?: Partial<Limits>;
  temperature?: number;
  outDir: string; // absolute; traces/ and sandbox/ are created below it
  fixturesRoot?: string; // absolute
}

export const DEFAULT_SYSTEM =
  "You are an assistant with tools. Use a tool when the answer depends on data you do not have. " +
  "If a tool fails, tell the user what failed instead of guessing.";

/** Returns the problems of a spec; an empty list means it can run. */
export function checkSpec(spec: RunSpec): string[] {
  const problems: string[] = [];
  if (spec.schemaVersion !== SCHEMA_VERSION) problems.push(`schemaVersion must be ${SCHEMA_VERSION}`);
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
  const ids = new Set<string>();
  for (const t of spec.tasks ?? []) {
    if (!t.id || !/^[A-Za-z0-9_-]+$/.test(t.id)) problems.push(`task id '${t.id}': letters, digits, - and _ only`);
    if (ids.has(t.id)) problems.push(`task id '${t.id}' is not unique`);
    ids.add(t.id);
    if (!t.prompt) problems.push(`task ${t.id}: prompt missing`);
    for (const name of t.tools ?? []) {
      if (!(TOOL_NAMES as readonly string[]).includes(name)) problems.push(`task ${t.id}: unknown tool ${name}`);
    }
    if (t.fixtures && (t.fixtures.includes("..") || /^[\\/]|^[A-Za-z]:/.test(t.fixtures))) {
      problems.push(`task ${t.id}: fixtures must be a relative folder name`);
    }
  }
  return problems;
}

export function limitsFor(spec: RunSpec, task: TaskSpec): Limits {
  return { ...DEFAULT_LIMITS, ...spec.limits, ...task.limits };
}
