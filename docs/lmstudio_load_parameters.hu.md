# LM Studio load paraméterek: mi állítható hol

[English](lmstudio_load_parameters.md)

Megfigyelve 2026-11-25/26-án, LM Studio 1.2.0 (build 2), CUDA 13 llama.cpp 2.83.0 runtime, RTX 2070 (8 GB). Forrás: a
hivatalos SDK, a `lms load --help`, REST-próbák (az egyszeri `runner/probe_*.py` scriptek, azóta törölve, a
git-előzményben elérhetők) és a LM Studio UI által mentett per-modell default config fájlok. Futtatással igazolt,
kivéve ahol jelölve van. Más verziók eltérően viselkedhetnek.

## Áttekintés

| Út | GPU-offload arány, KV-kvantálás, CPU-szálak | Használja-e az eszköz |
|---|---|---|
| Hivatalos TypeScript SDK | igen (a szálak llama.cpp argumentum-felülírással) | **igen**, a sweep futtató minden loadja |
| `lms load` (CLI) | csak GPU-offload | csak a smoke teszt (`bench/core/smoke.py`) |
| REST `POST /api/v1/models/load` | nem találtunk kulcsot | nem (a sweep a REST-et csak generálásra használja) |
| Per-modell default config fájl | igen | nem (korábbi módszer) |

## 1. Hivatalos TypeScript SDK (jelenlegi módszer)

`@lmstudio/sdk` 2.1.0, LM Studio 1.2.0. A futtató a `harness/load-model.ts` scriptet hívja; a sweep beállításainak
leképezése a load configra a `harness/load-config.ts` fájlban van.

### Kapcsolódás

- Az SDK automatikus portkeresése nem talált kapcsolatot, az `lms server start` portja pedig nem fogadja a
  WebSocketjét (HTTP 200). A működő portot a `~/.lmstudio/apps/bionic/.internal/http-server.json` fájlból olvassuk;
  ez **belső fájl**, más telepítésen eltérhet (az `LMS_API_FILE` környezeti változóval felülírható).
- Az alkalmazásnak futnia kell.
- Egy `channelUnknown` kommunikációs figyelmeztetés jelent meg az egyik load/predikció közben; az eredményeken nem
  látszott hatása. Figyelni kell az SDK és az alkalmazás verziói közti protokolleltérésre.
- A generálás és a mérés a HTTP-szerveren megy. A szerver az utoljára használt portot veszi elő; az `lms server status`
  kimenetéből kell kiolvasni, nem szabad az 1234-et feltételezni.

### Mért hatás

`harness/sdk-probe.ts` próba, 2026-11-26: Llama-3.2-1B, flash attention be, 1 párhuzamos predikció, bemelegítő és 2
mért futás. A LM Studio per-modell config fájljai **nem** módosultak (bájtra ellenőrizve).

| Eset | Beállítás | VRAM-növekedés | decode t/s |
|---|---|---|---|
| gpu-fp16 | GPU max, 32k, KV-kvantálás ki | 2490 MiB | 177,1 |
| gpu-q8 | GPU max, 32k, K és V `q8_0` | 2003 MiB | 164,6 |
| gpu-half | GPU ratio 0,5, 4k | 998 MiB | 29,4 |
| cpu-t2 | GPU ki, 4k, `--threads 2` | 308 MiB | 9,9 |
| cpu-t8 | GPU ki, 4k, `--threads 8` | 115 MiB | 15,5 |

- A `gpu.ratio`, a `llamaKCacheQuantizationType` és a `llamaVCacheQuantizationType` érvényesül; az értékek egyeznek a 3.
  pontban lévő, config fájlos mérésekkel.
- CPU-szálak: a load configban nincs külön mező, de a `llamaCppArgumentsOverride` `--threads` paramétere érvényesül (a
  decode-sebesség ugyanúgy eltér, mint a config fájllal).
- Az explicit értékek felülírták a mentett per-modell alapértékeket (mentve: KV-kvantálás ki, 6 szál). A UI-ban
  beállított modelleknek vannak ilyen mentett alapértékeik, ezért a futtató minden általa vezérelt beállítást
  explicit megad.

### Alkalmazott konfiguráció

A `getLoadConfig()` visszaadja az alkalmazott konfigurációt, a KV-típusokkal és az argumentum-felülírással együtt. A
futtató összeveti a kéréssel, és bármilyen eltérésnél hibásnak jelöli a jobot.

Az eddigi SDK-s sweep futásokban (Llama-3.2-1B és Qwen3-8B, 2026-11-26) az alkalmazott értékek egyeztek, miközben
ezek a beállítások változtak: contexthossz (4k–32k), GPU-offload (0 és 1), flash attention, eval és physical batch
méret, CPU-szálak és KV-kvantálás (ki és `q8_0`). A párhuzamos predikciók száma, a KV cache GPU-ra helyezése és a
unified KV cache csak egy-egy értékkel szerepelt. Az egyező érték azt mutatja, hogy a beállítást elfogadta; mért hatás
csak a fenti táblázat beállításaira van dokumentálva.

### Speculative decoding beállítások

A load configban experimental mezők vannak a speculative decodinghoz (`speculativeDraftMtp`, `speculativeDraftSimple`,
`speculativeDraftModel`, valamint draft hossz- és valószínűségi korlátok). A sweep explicit kikapcsolja a spekulációt,
és ez a visszaolvasásban látszik. Draft modellel és MTP-vel 2026-11-26-án próbáltunk loadot (`harness/spec-probe.ts`):
a mezők érvényesülnek és visszaolvashatók, egy későbbi load nélkülük kikapcsolt állapotot kap, a predikciónkénti
`draftModel`-t a motor elutasítja (a spekulációt a loadnál kell beállítani). Eredmények: `docs/requirements.hu.md`, 5.
pont.

### A betöltött modell élettartama

A modell betöltve marad, miután a betöltő process megszűnt, az SDK-kliens lezárása és hirtelen kilépés után is
(`harness/sdk-persist.ts`, 8k context, `q8_0`). A beállítások megmaradnak, a HTTP-szerver az identifier alapján
generál a modellel, és az `lms unload` eltávolítja. Ezért elég egy rövid életű loader process; a megszakadt futás
után maradt modellt külön el kell takarítani.

## 2. CLI és REST

| Út | Mit tud | Korlát |
|---|---|---|
| `lms load` (CLI) | `--gpu` (off / max / 0..1), `-c` kontextus, `--parallel`, speculative decoding (`--speculative-draft-*`), `--estimate-only`, `--identifier` | Nincs flash attention, batch, szál vagy KV-kvantálás kapcsoló (a help szövege alapján) |
| REST `POST /api/v1/models/load` | `context_length`, `eval_batch_size`, `physical_batch_size`, `parallel`, `flash_attention`, `offload_kv_cache_to_gpu`, `num_experts`, `context_checkpoints`, `lazy_mode`, speculative mezők, `echo_load_config` | Szigorú séma: ismeretlen kulcsot HTTP 400-zal elutasít. GPU-offload arányra, KV-kvantálásra, CPU-szálakra, mmap-re és keep-in-memory-ra nem találtunk kulcsot (kb. 50 névvariáns) |

A betöltött modell alapértékei a REST echo szerint (Llama-3.2-1B): eval batch 2048, physical batch 512, parallel 4,
flash attention be, KV cache a GPU-n.

## 3. Per-modell default config fájlok (korábbi módszer)

> Belső, nem dokumentált formátum, amely verziónként változhat. Az eszköz ezeket a fájlokat nem módosítja. A korábban
> ezt végző script (`runner/config_store.py`) törölve, a git-előzményben elérhető.

Hely: `~\.lmstudio\apps\bionic\.internal\user-concrete-model-default-config\<publisher>\<repo>\<modell>.gguf.json`

### Kulcsok (a UI által mentett fájlokból)

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

### Történeti mérés: a fájl értékei REST loadnál is érvényesülnek

A REST `echo_load_config` válasz nem tartalmazza a szálszámot és a KV-kvantálást, ezért méréssel ellenőriztük, a
korábbi módszerrel: a fájlok megírása, majd REST load.

A 2026-11-26-i ellenőrző sweep (`configs/validate.json`; ugyanezt a rácsot ma a live vezérlési teszt használja, SDK-s
betöltéssel): Llama-3.2-1B, 2 mért futás és bemelegítő, kb. 1540 tokenes prompt. A script által írt értékek
érvényesültek:

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

## Nem ellenőrzött

- Az SDK load configjának azok a beállításai, amelyeket a sweep nem állít.
- Hogy a CLI `lms load` alkalmazza-e a config fájl értékeit.
- Az `lms load --engine-config-file` formátuma (lehet, hogy egyedi motorokhoz való).
- A `llama.cpp Arguments Override` mentési formátuma a config fájlban.
- Más telepítésen azonosak-e a belső útvonalak. A `bionic` valószínűleg a LM Studio "Bionic" alkalmazása, amelyet a
  cég a weboldalán említ (következtetés, dokumentációban nem ellenőrzött). A fejlesztői gépen a config mappa tartalma
  egyezett a UI-ban látott beállításokkal.
