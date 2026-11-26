# LM Studio load parameters: what can be set where

[Magyar](lmstudio_load_parameters.hu.md)

Observed on 2026-11-25/26 with LM Studio 1.2.0 (build 2), runtime CUDA 13 llama.cpp 2.83.0, RTX 2070 (8 GB). Sources:
the official SDK, `lms load --help`, REST probes (the one-off `runner/probe_*.py` scripts, since removed and available
in the git history) and per-model default config files saved by the LM Studio UI. Verified by running unless stated
otherwise. Other versions may behave differently.

## Overview

| Path | GPU offload ratio, KV quantization, CPU threads | Used by this tool |
|---|---|---|
| Official TypeScript SDK | yes (threads through a llama.cpp argument override) | **yes**, every load of the sweep runner |
| `lms load` (CLI) | GPU offload only | only by the smoke test (`runner/smoke.py`) |
| REST `POST /api/v1/models/load` | no key found | no (the sweep uses REST for generation only) |
| Per-model default config file | yes | no (earlier method) |

## 1. Official TypeScript SDK (current method)

`@lmstudio/sdk` 2.1.0 against LM Studio 1.2.0. The runner calls `harness/load-model.ts`; the mapping of the sweep
settings to the load config is in `harness/load-config.ts`.

### Connection

- The SDK's automatic port discovery failed, and the port of `lms server start` does not accept its WebSocket
  (HTTP 200). The working port is read from `~/.lmstudio/apps/bionic/.internal/http-server.json`, an **internal file**
  that may differ on other installations (override with the `LMS_API_FILE` environment variable).
- The application has to be running.
- One `channelUnknown` communication warning appeared during one load/prediction; results were not visibly affected.
  Watch for protocol mismatches between SDK and application versions.
- Generation and measurement use the HTTP server. It reuses its last port; read it from `lms server status` instead of
  assuming 1234.

### Measured effect

Probe `harness/sdk-probe.ts`, 2026-11-26: Llama-3.2-1B, flash attention on, 1 parallel prediction, warm-up plus 2
measured runs. LM Studio's per-model config files were **not** modified (checked byte for byte).

| Case | Settings | VRAM increase | decode t/s |
|---|---|---|---|
| gpu-fp16 | GPU max, 32k, KV quantization off | 2490 MiB | 177.1 |
| gpu-q8 | GPU max, 32k, K and V `q8_0` | 2003 MiB | 164.6 |
| gpu-half | GPU ratio 0.5, 4k | 998 MiB | 29.4 |
| cpu-t2 | GPU off, 4k, `--threads 2` | 308 MiB | 9.9 |
| cpu-t8 | GPU off, 4k, `--threads 8` | 115 MiB | 15.5 |

- `gpu.ratio`, `llamaKCacheQuantizationType` and `llamaVCacheQuantizationType` take effect; the values agree with the
  config file measurements in section 3.
- CPU threads: there is no dedicated field in the load config, but `llamaCppArgumentsOverride` with the parameter
  `--threads` takes effect (decode speed differs as with the config file).
- Explicit values took precedence over the saved per-model defaults (saved: KV quantization off, 6 threads). Models
  configured in the UI have such saved defaults, so the runner sets every setting it controls explicitly.

### Applied configuration

`getLoadConfig()` returns the applied configuration, including the KV types and the argument override. The runner
compares it with the request and fails the job on any difference.

In the SDK sweep runs so far (Llama-3.2-1B and Qwen3-8B, 2026-11-26) the applied values matched while these settings
were varied: context length (4k to 32k), GPU offload (0 and 1), flash attention, eval and physical batch size, CPU
threads and KV quantization (off and `q8_0`). Parallel predictions, KV cache offload and the unified KV cache were only
used with one value each. A matching value shows that the setting was accepted; a measured effect is documented only
for the settings in the table above.

### Speculative decoding settings

The load config has experimental fields for speculative decoding (`speculativeDraftMtp`, `speculativeDraftSimple`,
`speculativeDraftModel` and draft length and probability limits). The sweep switches speculation off explicitly, and the
read-back shows it. Loads with a draft model and with MTP were tried on 2026-11-26 (`harness/spec-probe.ts`): the fields
are applied and read back, a later load without them gets them off, and the per-prediction `draftModel` is refused
(speculation must be set at load). Results: `docs/requirements.md`, section 5.

### Model lifetime

A model stays loaded after the loading process is gone, both after closing the SDK client and after an abrupt exit
(`harness/sdk-persist.ts`, 8k context, `q8_0`). The settings survive, the HTTP server generates with the model by its
identifier, and `lms unload` removes it. A short-lived loader process is therefore enough; leftovers of a killed run
have to be cleaned up explicitly.

## 2. CLI and REST

| Path | Can set | Limits |
|---|---|---|
| `lms load` (CLI) | `--gpu` (off / max / 0..1), `-c` context, `--parallel`, speculative decoding (`--speculative-draft-*`), `--estimate-only`, `--identifier` | No switch for flash attention, batch sizes, threads or KV quantization (from the help text) |
| REST `POST /api/v1/models/load` | `context_length`, `eval_batch_size`, `physical_batch_size`, `parallel`, `flash_attention`, `offload_kv_cache_to_gpu`, `num_experts`, `context_checkpoints`, `lazy_mode`, speculative fields, `echo_load_config` | Strict schema: unknown keys are rejected with HTTP 400. No key found for GPU offload ratio, KV quantization, CPU threads, mmap or keep-in-memory (about 50 name variants tried) |

Defaults of a loaded model according to the REST echo (Llama-3.2-1B): eval batch 2048, physical batch 512, parallel 4,
flash attention on, KV cache offloaded to GPU.

## 3. Per-model default config files (earlier method)

> Internal, undocumented format that may change between versions. The tool does not edit these files. The script that
> did (`runner/config_store.py`) has been removed and is available in the git history.

Location: `~\.lmstudio\apps\bionic\.internal\user-concrete-model-default-config\<publisher>\<repo>\<model>.gguf.json`

### Keys (read from files saved by the UI)

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

### Historical measurement: file values apply to REST loads

The REST `echo_load_config` response does not include threads or KV quantization, so this was checked by measurement,
with the earlier method of writing the files before a REST load.

Validation sweep of 2026-11-26 (`configs/validate.json`; the live control test uses the same grid today, loading
through the SDK): Llama-3.2-1B, 2 measured runs plus warm-up, prompt of about 1540 tokens. The values written by the
script took effect:

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

## Not verified

- Load config settings of the SDK that the sweep does not set.
- Whether CLI `lms load` applies the config file values.
- The format of `lms load --engine-config-file` (may be meant for custom engines).
- How `llama.cpp Arguments Override` is stored in the config file.
- Whether the internal paths are the same on other installations. `bionic` is probably LM Studio's "Bionic"
  application, which the company mentions on its website (inference, not verified in the documentation). On the
  development machine the config folder content matched the settings shown in the UI.
