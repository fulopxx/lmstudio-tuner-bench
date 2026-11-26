// JSONL trace per task attempt (decision H4). Each line is complete on its own, so a killed run leaves a readable file.
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { TRACE_SCHEMA_VERSION } from "./spec.ts";

export type TraceEventType =
  | "task_start" | "prediction" | "tool_call" | "tool_result" | "limit_hit" | "error" | "task_end";

export interface Trace {
  write(event: TraceEventType, data: Record<string, unknown>): void;
}

export class FileTrace implements Trace {
  private seq = 0;
  readonly path: string;
  constructor(path: string) {
    this.path = path;
    mkdirSync(dirname(path), { recursive: true });
  }
  write(event: TraceEventType, data: Record<string, unknown>): void {
    appendFileSync(this.path, JSON.stringify({ schema_version: TRACE_SCHEMA_VERSION, seq: this.seq++,
      t: new Date().toISOString(), event, ...data }) + "\n");
  }
}

/** Keeps events in memory (tests). */
export class MemoryTrace implements Trace {
  readonly events: Record<string, unknown>[] = [];
  write(event: TraceEventType, data: Record<string, unknown>): void {
    this.events.push({ seq: this.events.length, event, ...data });
  }
}
