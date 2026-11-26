# LM Studio load paraméterek: mi állítható hol

[English](lmstudio_load_parameters.md)

Megfigyelve 2026-11-25/26-án, LM Studio 1.2.0 (build 2), CUDA 13 llama.cpp 2.83.0 runtime, RTX 2070 (8 GB). Forrás:
`lms load --help`, REST-próbák (`runner/probe_*.py`) és a LM Studio UI által mentett per-modell default config fájlok.
Futtatással igazolt, kivéve ahol jelölve van. Más verziók eltérően viselkedhetnek.

## Három vezérlési út

| Út | Mit tud | Korlát |
|---|---|---|
| `lms load` (CLI) | `--gpu` (off / max / 0..1), `-c` kontextus, `--parallel`, speculative decoding (`--speculative-draft-*`), `--estimate-only`, `--identifier` | Nincs flash attention, batch, szál vagy KV-kvantálás kapcsoló (a help szövege alapján) |
| REST `POST /api/v1/models/load` | `context_length`, `eval_batch_size`, `physical_batch_size`, `parallel`, `flash_attention`, `offload_kv_cache_to_gpu`, `num_experts`, `context_checkpoints`, `lazy_mode`, speculative mezők, `echo_load_config` | Szigorú séma: ismeretlen kulcsot HTTP 400-zal elutasít. GPU-offload arányra, KV-kvantálásra, CPU-szálakra, mmap-re és keep-in-memory-ra nem találtunk kulcsot (kb. 50 névvariáns) |
| Per-modell default config fájl: `~\.lmstudio\apps\bionic\.internal\user-concrete-model-default-config\<publisher>\<repo>\<modell>.gguf.json` | GPU-offload arány, KV-kvantálás, szálak és a lent felsorolt többi kulcs | Belső, nem dokumentált formátum. A benchmark csak ideiglenesen módosítja, mentéssel és bájtpontos visszaállítással (`runner/config_store.py`) |

## Negyedik út: a hivatalos SDK (még nincs kipróbálva)

Hozzáadva 2026-11-26. A hivatalos TypeScript SDK forrásában a load config séma
([`LLMLoadModelConfig.ts`](https://github.com/lmstudio-ai/lmstudio-js/blob/main/packages/lms-shared-types/src/llm/LLMLoadModelConfig.ts),
`main` branch) többek között ezeket tartalmazza: `gpu.ratio`, `llamaKCacheQuantizationType`,
`llamaVCacheQuantizationType` (`f32`, `f16`, `q8_0`, `q4_0`, `q4_1`, `iq4_nl`, `q5_0`, `q5_1`), `flashAttention`,
`evalBatchSize`, `physicalBatchSize`, `useUnifiedKvCache`, `keepModelInMemory`, `tryMmap` és
`llamaCppArgumentsOverride`. CPU-szál mezőt nem találtunk. **Futtatással nem igazolt:** a telepített LM Studio verzió
nem feltétlenül tud mindent, ami a mai forrásban van. Ha működik, a config fájlok módosítása nagyrészt szükségtelen.

## Default config kulcsok (a UI által mentett fájlokból)

| UI-sor | Kulcs | Érték formátuma |
|---|---|---|
| CPU Thread Pool Size | `llm.load.llama.cpuThreadPoolSize` | szám |
| K Cache Quantization Type | `llm.load.llama.kCacheQuantizationType` | `{"checked": true/false, "value": "q8_0"}` |
| V Cache Quantization Type | `llm.load.llama.vCacheQuantizationType` | `{"checked": true/false, "value": "q8_0"}` |
| Unified KV Cache | `llm.load.useUnifiedKvCache` | true/false |
| Context Length | `llm.load.contextLength` | szám |
| GPU Offload | `llm.load.llama.acceleration.offloadRatio` | 0..1 |
| Flash Attention | `llm.load.llama.flashAttention` | true/false |
| Physical Batch Size | `llm.load.llama.physicalBatchSize` | szám |
| Automatic Optimize | `llm.load.llama.autoFit` | true/false |

Csak a `q8_0` típusértéket láttuk; a többi lehetséges érték a UI legördülőjéből derül ki.

## Érvényesülnek-e a config fájl értékei REST loadnál? Igen

A REST `echo_load_config` válasz nem tartalmazza a szálszámot és a KV-kvantálást, ezért méréssel ellenőriztük.

**Ellenőrző sweep (2026-11-26, `configs/validate.json`):** Llama-3.2-1B, 2 mért futás és bemelegítő, kb. 1540 tokenes
prompt. A script által írt értékek érvényesültek:

| Config | VRAM-növekedés | decode t/s | prompt t/s |
|---|---|---|---|
| GPU, 32k, fp16 KV | 2527 MiB | 179,8 | 8090 |
| GPU, 32k, q8_0 KV | 2004 MiB | 165,8 | 8497 |
| offload 0, 4k, 2 szál | 147 MiB | 11,0 | 2202 |
| offload 0, 4k, 8 szál | 130 MiB | 15,4 | 2209 |

- KV-kvantálás: 523 MiB különbség (elmélet kb. 450 MiB), kontrollméréssel.
- GPU-offload arány: érvényesül.
- Szálszám: a decode-sebesség eltér (11,0 és 15,4 t/s), tehát érvényesül.
- Offload 0 mellett a magas prompt-sebesség valószínűleg abból jön, hogy a CUDA runtime a promptot részben így is a
  GPU-n dolgozza fel (következtetés, nem ellenőrzött).
- A config mappa a futás előtt és után bájtra azonos volt.

## További megfigyelések

- A betöltött modell alapértékei a REST echo szerint (Llama-3.2-1B): eval batch 2048, physical batch 512, parallel 4,
  flash attention be, KV cache a GPU-n.
- A UI-ban beállított modelleknek van mentett alapértékük (pl. kontextushossz), ezért a benchmark mindig explicit
  paraméterekkel töltsön be.
- A LM Studio szerver az utoljára használt portot veszi elő; az `lms server status` kimenetéből kell kiolvasni, nem
  szabad az 1234-et feltételezni.

## Nem ellenőrzött

- Hogy a CLI `lms load` alkalmazza-e a config fájl értékeit.
- Az `lms load --engine-config-file` formátuma (lehet, hogy egyedi motorokhoz való).
- A `llama.cpp Arguments Override` mentési formátuma.
- Más telepítésen azonos-e az útvonal. A `bionic` valószínűleg a LM Studio "Bionic" alkalmazása, amelyet a cég a
  weboldalán említ (következtetés, dokumentációban nem ellenőrzött). A fejlesztői gépen a mappa tartalma egyezett a
  UI-ban látott beállításokkal.
