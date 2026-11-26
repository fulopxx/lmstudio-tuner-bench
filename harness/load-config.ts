// Mapping between the sweep's load settings and the LM Studio SDK load config (no SDK import, testable alone).

export interface SweepSettings {
  context_length: number;
  offload_ratio: number; // 0 = CPU only, 1 = everything on the GPU
  flash_attention: boolean;
  eval_batch_size: number;
  physical_batch_size: number;
  parallel: number;
  offload_kv_cache_to_gpu: boolean;
  unified_kv: boolean;
  threads: number;
  kv_quant: string | null;
}

/** Every setting the sweep controls is set explicitly, so saved per-model defaults cannot leak in. */
export function toSdkConfig(s: SweepSettings) {
  const kv = (s.kv_quant ?? false) as "q8_0" | "q4_0" | false;
  return {
    autoFit: false,
    contextLength: s.context_length,
    gpu: { ratio: s.offload_ratio >= 1 ? ("max" as const) : s.offload_ratio <= 0 ? ("off" as const) : s.offload_ratio },
    flashAttention: s.flash_attention,
    evalBatchSize: s.eval_batch_size,
    physicalBatchSize: s.physical_batch_size,
    maxParallelPredictions: s.parallel,
    offloadKVCacheToGpu: s.offload_kv_cache_to_gpu,
    useUnifiedKvCache: s.unified_kv,
    llamaKCacheQuantizationType: kv,
    llamaVCacheQuantizationType: kv,
    // there is no thread field in the load config; the llama.cpp argument override sets it
    llamaCppArgumentsOverride: {
      enabled: true,
      disabledParameters: [] as string[],
      overrideParameters: [{ key: "--threads", value: String(s.threads) }],
      excludeAllConfig: false,
    },
    speculativeDraftMtp: false,
    speculativeDraftSimple: false,
  };
}

/** Names of the requested settings that the applied config does not reflect. */
export function mismatches(requested: ReturnType<typeof toSdkConfig>, applied: Record<string, unknown>): string[] {
  const wrong: string[] = [];
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  for (const [key, value] of Object.entries(requested)) {
    if (key === "gpu") {
      const ratio = (applied.gpu as { ratio?: unknown } | undefined)?.ratio;
      if (!same(ratio, requested.gpu.ratio)) wrong.push(`gpu.ratio: ${ratio} != ${requested.gpu.ratio}`);
    } else if (!same(applied[key], value)) {
      wrong.push(`${key}: ${JSON.stringify(applied[key])} != ${JSON.stringify(value)}`);
    }
  }
  return wrong;
}
