// Pure parts of the speculative decoding probe (no SDK import, testable alone).
import { toSdkConfig, type SweepSettings } from "./load-config.ts";

export const STEPS = ["P1", "P2", "P3", "P4", "P5", "P6"] as const;
export type Step = (typeof STEPS)[number];

export interface ProbePlan {
  target: string; // model key of the main model
  draft: string; // model key of a draft model of the same family
  mtp: string[]; // model keys of models with built-in MTP heads (may be empty)
  incompatible?: { target: string; draft: string }; // a pair expected to be rejected (SD-01)
  contextLength: number;
  repeats: number; // measured predictions per prompt, after one warm-up
  maxTokens: number;
  minFreeMib: number;
  maxUtil: number;
  loadTimeoutMs: number;
  predictTimeoutMs: number;
}

export const PLAN_DEFAULTS = {
  contextLength: 4096, repeats: 3, maxTokens: 200, minFreeMib: 5692, maxUtil: 30,
  loadTimeoutMs: 360_000, predictTimeoutMs: 300_000,
};

/** Fills defaults and rejects a plan that cannot run; returns the list of problems. */
export function validatePlan(raw: Record<string, unknown>): { plan: ProbePlan; problems: string[] } {
  // the checks below cover what the cast assumes
  const plan = { ...PLAN_DEFAULTS, mtp: [], ...(raw as Partial<ProbePlan>) } as ProbePlan;
  const problems: string[] = [];
  for (const key of ["target", "draft"] as const) {
    if (typeof plan[key] !== "string" || plan[key].trim() === "" || plan[key].includes("<")) {
      problems.push(`${key}: model key missing`);
    }
  }
  if (!Array.isArray(plan.mtp) || plan.mtp.some((m) => typeof m !== "string" || m.includes("<"))) {
    problems.push("mtp: must be a list of model keys");
  }
  if (plan.target === plan.draft) problems.push("draft must differ from target");
  for (const key of ["contextLength", "repeats", "maxTokens", "loadTimeoutMs", "predictTimeoutMs"] as const) {
    if (!Number.isInteger(plan[key]) || plan[key] <= 0) problems.push(`${key}: positive integer expected`);
  }
  return { plan, problems };
}

export function parseSteps(arg: string | undefined): Step[] {
  if (!arg) return [];
  const steps = arg.split(",").map((s) => s.trim().toUpperCase());
  const bad = steps.filter((s) => !(STEPS as readonly string[]).includes(s));
  if (bad.length) throw new Error(`unknown step(s): ${bad.join(", ")}; known: ${STEPS.join(", ")}`);
  return STEPS.filter((s) => steps.includes(s));
}

/** Load settings shared by every case: full offload, f16 KV, one parallel prediction. */
export function baseSettings(contextLength: number): SweepSettings {
  return {
    context_length: contextLength, offload_ratio: 1, flash_attention: true, eval_batch_size: 2048,
    physical_batch_size: 512, parallel: 1, offload_kv_cache_to_gpu: true, unified_kv: true, threads: 8,
    kv_quant: null,
  };
}

export type SpecMode = "off" | "draft" | "mtp" | "omit";

/** Load config for a mode; "omit" leaves the speculative fields out to see what LM Studio fills in. */
export function loadConfig(contextLength: number, mode: SpecMode, draft?: string): Record<string, unknown> {
  const config: Record<string, unknown> = { ...toSdkConfig(baseSettings(contextLength)) };
  if (mode === "draft") {
    if (!draft) throw new Error("draft mode needs a draft model");
    Object.assign(config, { speculativeDraftSimple: true, speculativeDraftModel: draft });
  } else if (mode === "mtp") {
    config.speculativeDraftMtp = true;
  } else if (mode === "omit") {
    delete config.speculativeDraftMtp;
    delete config.speculativeDraftSimple;
  }
  return config;
}

/** The speculative fields of an applied load config (read back from LM Studio). */
export function speculativeFields(applied: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(applied).filter(([k]) => k.toLowerCase().includes("speculative")));
}

/** Requested speculative fields whose applied value differs. */
export function speculativeMismatches(requested: Record<string, unknown>, applied: Record<string, unknown>): string[] {
  return Object.entries(speculativeFields(requested))
    .filter(([k, v]) => JSON.stringify(applied[k]) !== JSON.stringify(v))
    .map(([k, v]) => `${k}: ${JSON.stringify(applied[k])} != ${JSON.stringify(v)}`);
}

export interface DraftStats {
  usedDraftModelKey?: string;
  totalDraftTokensCount?: number;
  acceptedDraftTokensCount?: number;
  rejectedDraftTokensCount?: number;
  ignoredDraftTokensCount?: number;
}

/**
 * SD-05: acceptance rate = accepted / generated draft tokens, draft share = accepted / output tokens.
 * A missing input gives null ("n/a"), never an estimate.
 */
export function draftRatios(stats: DraftStats, outputTokens: number | undefined) {
  const accepted = stats.acceptedDraftTokensCount;
  const total = stats.totalDraftTokensCount;
  const round = (v: number) => Math.round(v * 1000) / 1000;
  return {
    acceptanceRate: accepted !== undefined && total ? round(accepted / total) : null,
    draftShare: accepted !== undefined && outputTokens ? round(accepted / outputTokens) : null,
  };
}

export const median = (v: number[]) => {
  if (!v.length) return null;
  const s = [...v].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

/** Index of the first differing character of two outputs (SD-09), or null when they are equal. */
export function firstDifference(a: string, b: string): number | null {
  if (a === b) return null;
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  return i;
}

/** Workload prompts; the first line is unique per call so the prompt cache cannot help. */
export const PROMPTS = {
  code: (tag: string) =>
    `Request ${tag}.\nWrite a Python module with a function parse_csv_line(line: str) -> list[str] that handles ` +
    `quoted fields, escaped quotes and empty fields, followed by five pytest test functions. Code only.`,
  synthetic: (tag: string) =>
    `Run id ${tag}.\n` +
    Array.from({ length: 60 }, (_, i) =>
      `${i}. The sensor node ${i} reports temperature ${20 + (i % 17)} C, voltage ` +
      `${(3 + (i % 5) / 10).toFixed(1)} V and status code ${(i * 7) % 101}.`).join("\n") +
    "\n\nSummarize the data above in a short paragraph.",
};
export type PromptKind = keyof typeof PROMPTS;
