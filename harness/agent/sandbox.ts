// A throwaway folder per task attempt with a copy of the task's fixtures; kept until the core has checked it.
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";

export function createSandbox(outDir: string, name: string, fixturesRoot?: string, fixtures?: string): string {
  const dir = join(outDir, "sandbox", name);
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  if (fixtures) {
    if (!fixturesRoot) throw new Error(`fixtures '${fixtures}' given but no fixturesRoot`);
    const source = join(fixturesRoot, fixtures);
    if (!existsSync(source)) throw new Error(`fixtures folder not found: ${source}`);
    cpSync(source, dir, { recursive: true, verbatimSymlinks: true });
  }
  return dir;
}
