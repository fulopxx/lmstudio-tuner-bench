# LM Studio load parameters: what can be set where

[Magyar](lmstudio_load_parameters.hu.md)

Observed on 2026-11-25/26 with LM Studio 1.2.0 (build 2), runtime CUDA 13 llama.cpp 2.83.0, RTX 2070 (8 GB). Sources:
`lms load --help`, REST probes (`runner/probe_*.py`) and per-model default config files saved by the LM Studio UI.
Verified by running unless stated otherwise. Other versions may behave differently.

## Three control paths

| Path | Can set | Limits |
|---|---|---|
| `lms load` (CLI) | `--gpu` (off / max / 0..1), `-c` context, `--parallel`, speculative decoding (`--speculative-draft-*`), `--estimate-only`, `--identifier` | No switch for flash attention, batch sizes, threads or KV quantization (from the help text) |
| REST `POST /api/v1/models/load` | `context_length`, `eval_batch_size`, `physical_batch_size`, `parallel`, `flash_attention`, `offload_kv_cache_to_gpu`, `num_experts`, `context_checkpoints`, `lazy_mode`, speculative fields, `echo_load_config` | Strict schema: unknown keys are rejected with HTTP 400. No key found for GPU offload ratio, KV quantization, CPU threads, mmap or keep-in-memory (about 50 name variants tried) |
| Per-model default config file: `~\.lmstudio\apps\bionic\.internal\user-concrete-model-default-config\<publisher>\<repo>\<model>.gguf.json` | GPU offload ratio, KV quantization, threads and the other keys listed below | Internal, undocumented format. The benchmark edits it only temporarily, with backup and byte-exact restore (`runner/config_store.py`) |

## Fourth path: the official SDK (not tried yet)

Added 2026-11-26. The load config schema in the source of the official TypeScript SDK
([`LLMLoadModelConfig.ts`](https://github.com/lmstudio-ai/lmstudio-js/blob/main/packages/lms-shared-types/src/llm/LLMLoadModelConfig.ts),
`main` branch) lists, among others: `gpu.ratio`, `llamaKCacheQuantizationType`, `llamaVCacheQuantizationType`
(`f32`, `f16`, `q8_0`, `q4_0`, `q4_1`, `iq4_nl`, `q5_0`, `q5_1`), `flashAttention`, `evalBatchSize`,
`physicalBatchSize`, `useUnifiedKvCache`, `keepModelInMemory`, `tryMmap` and `llamaCppArgumentsOverride`. No CPU
thread field was found. **Not verified by running:** the installed LM Studio version may not support everything in the
current source. If it works, most config file edits become unnecessary.

## Default config keys (read from files saved by the UI)

| UI row | Key | Value format |
|---|---|---|
| CPU Thread Pool Size | `llm.load.llama.cpuThreadPoolSize` | number |
| K Cache Quantization Type | `llm.load.llama.kCacheQuantizationType` | `{"checked": true/false, "value": "q8_0"}` |
| V Cache Quantization Type | `llm.load.llama.vCacheQuantizationType` | `{"checked": true/false, "value": "q8_0"}` |
| Unified KV Cache | `llm.load.useUnifiedKvCache` | true/false |
| Context Length | `llm.load.contextLength` | number |
| GPU Offload | `llm.load.llama.acceleration.offloadRatio` | 0..1 |
| Flash Attention | `llm.load.llama.flashAttention` | true/false |
| Physical Batch Size | `llm.load.llama.physicalBatchSize` | number |
| Automatic Optimize | `llm.load.llama.autoFit` | true/false |

Only the type value `q8_0` has been seen; other possible values would come from the UI drop-down.

## Do the config file values apply to REST loads? Yes

The REST `echo_load_config` response does not include threads or KV quantization, so this was checked by measurement.

**Validation sweep (2026-11-26, `configs/validate.json`):** Llama-3.2-1B, 2 measured runs plus warm-up, prompt of about
1540 tokens. The values written by the script took effect:

| Config | VRAM increase | decode t/s | prompt t/s |
|---|---|---|---|
| GPU, 32k, fp16 KV | 2527 MiB | 179.8 | 8090 |
| GPU, 32k, q8_0 KV | 2004 MiB | 165.8 | 8497 |
| offload 0, 4k, 2 threads | 147 MiB | 11.0 | 2202 |
| offload 0, 4k, 8 threads | 130 MiB | 15.4 | 2209 |

- KV quantization: 523 MiB difference (theory about 450 MiB), with a control measurement.
- GPU offload ratio: takes effect.
- Threads: decode speed differs (11.0 vs 15.4 t/s), so it takes effect.
- The high prompt speed at offload 0 is probably because the CUDA runtime still processes the prompt partly on the GPU
  (inference, not verified).
- The config folder was byte-identical before and after the run.

## Other observations

- Defaults of a loaded model according to the REST echo (Llama-3.2-1B): eval batch 2048, physical batch 512,
  parallel 4, flash attention on, KV cache offloaded to GPU.
- Saved per-model defaults (e.g. a context length) exist for models configured in the UI, so a benchmark should always
  pass parameters explicitly.
- The LM Studio server reuses its last port; read it from `lms server status` instead of assuming 1234.

## Not verified

- Whether CLI `lms load` applies the config file values.
- The format of `lms load --engine-config-file` (may be meant for custom engines).
- How `llama.cpp Arguments Override` is stored.
- Whether the path is the same on other installations. `bionic` is probably LM Studio's "Bionic" application, which the
  company mentions on its website (inference, not verified in the documentation). On the development machine the
  folder content matched the settings shown in the UI.
