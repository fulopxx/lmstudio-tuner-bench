// Offline test of the settings mapping:  node --test load-config.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { mismatches, toSdkConfig, type SweepSettings } from "./load-config.ts";

const settings: SweepSettings = {
  context_length: 8192, offload_ratio: 1, flash_attention: true, eval_batch_size: 2048,
  physical_batch_size: 512, parallel: 1, offload_kv_cache_to_gpu: true, unified_kv: true, threads: 6,
  kv_quant: "q8_0",
};

test("maps offload ratio, KV quantization and threads", () => {
  const c = toSdkConfig(settings);
  assert.equal(c.gpu.ratio, "max");
  assert.equal(c.llamaKCacheQuantizationType, "q8_0");
  assert.deepEqual(c.llamaCppArgumentsOverride.overrideParameters, [{ key: "--threads", value: "6" }]);
  assert.equal(toSdkConfig({ ...settings, offload_ratio: 0 }).gpu.ratio, "off");
  assert.equal(toSdkConfig({ ...settings, offload_ratio: 0.75 }).gpu.ratio, 0.75);
  assert.equal(toSdkConfig({ ...settings, kv_quant: null }).llamaVCacheQuantizationType, false);
});

test("reports settings that were not applied", () => {
  const requested = toSdkConfig(settings);
  assert.deepEqual(mismatches(requested, { ...requested, extra: 1 }), []);
  const wrong = mismatches(requested, { ...requested, contextLength: 4096, gpu: { ratio: 0.5 } });
  assert.equal(wrong.length, 2);
});
