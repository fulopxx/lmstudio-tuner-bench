// Loads one model through the LM Studio SDK and exits; the model stays loaded.
//
//   echo '{"model": "<path>", "identifier": "<id>", "settings": {...}, "timeoutMs": 240000}' | node load-model.ts
//
// On success the last stdout line is "RESULT:" followed by JSON (loaded path, applied config, load
// time, mismatches, application version). Any failure exits non-zero with the message on stderr.
// Nothing is retried.
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { LMStudioClient } from "@lmstudio/sdk";
import { mismatches, toSdkConfig, type SweepSettings } from "./load-config.ts";

const fail = (e: unknown): never => {
  process.stderr.write(String((e as Error)?.message ?? e).slice(0, 800) + "\n");
  process.exit(1);
};
process.on("unhandledRejection", fail);

/** LM Studio writes the port of its own API (not the one of `lms server start`) into this file. */
function apiBaseUrl(): string {
  const file = process.env.LMS_API_FILE
    ?? join(homedir(), ".lmstudio", "apps", "bionic", ".internal", "http-server.json");
  const { host, port } = JSON.parse(readFileSync(file, "utf8"));
  return `ws://${host}:${port}`;
}

try {
  const request = JSON.parse(readFileSync(0, "utf8")) as {
    model: string; identifier: string; settings: SweepSettings; timeoutMs: number;
  };
  const config = toSdkConfig(request.settings);
  const client = new LMStudioClient({ baseUrl: apiBaseUrl() });
  const started = Date.now();
  const model = await client.llm.load(request.model, {
    identifier: request.identifier, config, verbose: false, signal: AbortSignal.timeout(request.timeoutMs),
  });
  const loadSeconds = (Date.now() - started) / 1000;
  const applied: Record<string, unknown> = { ...(await model.getLoadConfig()) };
  delete applied.promptTemplate;
  const info = await model.getModelInfo();
  // version of the application that served this load; recorded only, so a failure here is not an error
  const app = await client.system.getLMStudioVersion().then((v) => `${v.version}+${v.build}`, () => null);
  await client[Symbol.asyncDispose]();
  process.stdout.write("\nRESULT:" + JSON.stringify({
    path: info.path, identifier: info.identifier, loadSeconds, applied, mismatches: mismatches(config, applied), app,
  }) + "\n", () => process.exit(0));
} catch (e) {
  fail(e);
}
