# Architektúra

[English](architecture.md)

Utolsó frissítés: 2026-11-26. **Állapot: vázlat** (a véglegesítés a roadmap D lépése). A "Jelenlegi" részek a meglévő
kódot írják le, a "Cél" és "Tervezett" részek még nincsenek megvalósítva. A feladatlista: `docs/roadmap.hu.md`.

## 1. Alapelvek

- **CLI-paritás:** a webes és bármely más grafikus felület nem tudhat többet a CLI-nél. Új funkció először a core-ban
  és a CLI-ben jelenik meg.
- **Vékony felület:** mérés, állapotkezelés, értékelés és számítás (pl. Pareto-front, pontszám) a core-ban van.
- **Kevés függőség:** a core csak a Python standard könyvtárát használja; külső csomag a felületekhez, az exporthoz és
  a TypeScript harnesshez (hivatalos LM Studio SDK) kerülhet be.
- **Biztonságos futás:** minden külső lépésnek időkorlátja van; nincs automatikus újrapróbálás; foglalt GPU esetén
  szünet; csak a futás által betöltött modell kerül eltávolításra; a LM Studio config-fájlok visszaállnak.
- **Helyi:** a webes szerver csak `127.0.0.1`-en figyel.
- **Kétnyelvűség (tervezett):** az angol az elsődleges, a magyar teljes értékű második nyelv. A felületek szövegei
  nyelvi fájlokból jönnek (nincs beégetett szöveg), a nyelv váltható. A kód, a kommentek, az azonosítók és az
  adatformátumok mezőnevei angolok, és nem fordulnak.

## 2. Jelenlegi felépítés

| Fájl | Szerep |
|---|---|
| `bench.cmd` | Rövid parancs a sweep futtatóhoz |
| `runner/sweep.py` | CLI, futtató, állapot- és vezérléskezelés, riport (egy fájlban) |
| `runner/smoke.py` | Smoke teszt és közös segédfüggvények (parancsfuttatás, HTTP, streamelt mérés, VRAM-mintavétel) |
| `runner/evaluate.py` | A sweep eredményeinek kiértékelése: becsült válaszidő, figyelmeztetések, ajánlások |
| `runner/config_store.py` | Per-modell config-fájlok mentése, ideiglenes írása, visszaállítása |
| `runner/probe_*.py` | Egyszeri felderítő scriptek (REST-kulcsok, KV-kvantálás) |
| `configs/*.json` | Mérési rácsok: modellista, alapértékek, konfigurációk |
| `tools/export_docs.py` | A `docs` Markdown fájljainak (angol és magyar) PDF-exportja |
| `tests/` | Offline tesztek és egy GPU-t használó élő vezérlési teszt |

## 3. Cél felépítés (tervezett)

```
bench/
  core/   környezet, LM Studio kliens, config-tár, tervező, futtató, eredménytár, értékelés
  cli/    parancsok; minden funkció itt elérhető
  api/    FastAPI, a core vékony burkolata
harness/  TypeScript: agent tool loop, sandbox, toolok, trace log
web/      React + Vite + TypeScript, Mantine, ECharts
```

Az agent harness feladatokat futtat egy betöltött modellen és trace-t ír; a core-ban lévő hibaelemzés a trace-ekből
kategóriákat és riportot készít. A core-hoz kapcsolódó interfészét (processhatár és trace-formátum) a roadmap G lépése
előtt kell meghatározni. Követelmények: a roadmap 7. pontja.

```
core  ->  CLI
core  ->  FastAPI  ->  React
core  ->  NiceGUI (alacsony prioritás)
```

## 4. Fájlalapú interfészek (jelenlegi)

A futtató és a vezérlő parancsok külön folyamatok, fájlokon át kommunikálnak.

| Fájl | Tartalom |
|---|---|
| `state/status.json` | `run`, `state`, `phase`, `phase_since`, `reason`, `total`, `started`, `job_started`, `current` (`n`, `model`, `config`), `heartbeat`, `pid` |
| `state/control.json` | `cmd` (`run` / `pause` / `stop`), `now`, `ts` |
| `state/latest.txt` | A legutóbbi futás azonosítója |
| `state/runs/<run>/plan.json` | `grid`, `jobs` (`n`, `id`, `model`, `config`, `settings`), `options`, `env` (runtime, driver) |
| `results/sweep_<run>.jsonl` | Soronként egy feladat eredménye; azonos `job_id` esetén az utolsó sor érvényes |
| `report/sweep_<run>.md` | Táblázatos riport |
| `backups/active.json` | A még vissza nem állított config-fájlok naplója |

Eredménysor mezői sikeres feladatnál: `job_id`, `run`, `model`, `config`, `settings`, `model_path`, `runtime`,
`driver`, `status`, `load_s`, `echo`, `loaded_quant`, `loaded_publisher`, `vram_before_mib`, `vram_delta_mib`,
`runs`, `ttft_s`, `decode_tok_s`, `prompt_tok_s`, `vram_peak_mib`, `near_vram_limit`, `job_s`, `finished`.
Hibás sorban `error` szerepel, és a mérési mezők hiányozhatnak. A `status` értéke `ok`, `fail`, `timeout` vagy
`invalidated`.

## 5. Futási állapotok (jelenlegi)

![Futási állapotgráf](img/run_states.hu.svg)

| Állapot | Jelentés | Innen merre |
|---|---|---|
| `starting` | Előkészítés | `running`, `aborted` |
| `running` | Mérés folyik | `paused`, `stopped`, `done`, `aborted` |
| `paused` | Modell eltávolítva, configok visszaállítva | `running`, `stopped` |
| `stopped` | A felhasználó leállította | `resume` új folyamatot indít |
| `done` | Minden feladat lefutott | `resume --from` / `--redo-failed` új folyamatot indít |
| `aborted` | Hiba vagy két egymást követő timeout | `resume` új folyamatot indít |

A futtató akkor számít élőnek, ha a `heartbeat` 20 másodpercnél frissebb. Egyszerre egy futás lehet aktív. Ha a
process végállapot nélkül hal meg (kill, újraindítás), ezt az elavult heartbeat mutatja, és a `resume` új processt
indít, amely először visszaállítja a módosítva maradt config fájlokat. A gráfot a `tools/make_diagrams.py` generálja.

## 6. Parancsok és tervezett API

Az API-útvonalak javaslatok, még nincsenek megvalósítva.

| CLI (jelenlegi) | API (tervezett) |
|---|---|
| `bench run --dry-run` | `POST /plans` |
| `bench run` | `POST /runs` |
| `bench status`, `status --jobs` | `GET /runs/current`, `GET /runs/{id}/jobs` |
| `bench pause [--now]` | `POST /runs/current/pause` |
| `bench resume [--from N] [--redo-failed]` | `POST /runs/{id}/resume` |
| `bench stop [--now]` | `POST /runs/current/stop` |
| `bench evaluate [--run] [--in-tokens] [--out-tokens]` | `GET /runs/{id}/evaluation` |

## 7. Külső függések

| Függés | Mire |
|---|---|
| `lms.exe` | modellista, runtime-lista, szerver indítása és leállítása, modell eltávolítása |
| REST `POST /api/v1/models/load` | betöltés explicit paraméterekkel |
| REST `GET /api/v0/models/{id}` | a betöltött modell ellenőrzése |
| REST `POST /v1/chat/completions` | generálás és mérés |
| `nvidia-smi` | VRAM, GPU-kihasználtság, driver |
| LM Studio per-modell config mappa (`apps/bionic/...`) | KV-kvantálás, szálszám, GPU-offload; részletek: `docs/lmstudio_load_parameters.hu.md` |

## 8. Tervezett formátumváltozások

- `schema_version` minden tervben és eredménysorban.
- Hardver-ujjlenyomat: GPU neve, VRAM, LM Studio verzió, runtime, driver.
- Tesztcsomag-eredmények (minőség, tool-használat) a sebességmérés mellett.
- Jelző, hogy mérés közben nyitva volt-e a dashboard.
- Modellregiszter képességcímkékkel.

## 9. Nyitott kérdések

- Működik-e a hivatalos SDK (`@lmstudio/sdk`) a telepített LM Studio verzióval. Ha igen, a Python core hogyan
  használja loadhoz (a harness processen át vagy a Python SDK-val), kiváltva a config fájlok módosítását.
- A megosztott GPU-memóriába csordulás felismerése.
- Tesztrétegek véglegesítése (pytest, Vitest, Playwright).
- A gépfüggő beállítások konfigurációs fájljának helye és formátuma.
