# lmstudio-tuner-bench

[English](README.md)

Helyi LLM modellek mérése és összehasonlítása LM Studióval, a saját hardvereden, kétféleképpen:

- **Load-paraméter sweep:** mely load beállításokkal (context, GPU-offload, KV cache, batch, szálak) fut egy modell a
  leggyorsabban a GPU-don úgy, hogy a memória is elég.
- **Agent harness:** mennyire megbízhatóan használ toolokat egy modell rögzített feladatokon. A harness az a program a
  modell körül, amely ágenssé teszi: toolokat ad neki, futtatja a ciklust (a modell toolt kér, a harness lefuttatja és
  visszaadja az eredményt), korlátokat tart, és minden lépést naplóz, hogy a hibák utólag elemezhetők legyenek.

> Nem hivatalos eszköz, nem áll kapcsolatban az LM Studio fejlesztőivel.
> Korai állapot: egyetlen gépen próbáltuk.

## Motiváció

Rengeteg modellt letöltöttem, aztán a saját gépemen szerettem volna tudni, melyik mit tud, mire tudom jól használni,
és hogyan futtathatom optimalizálva. Ezt kézzel kideríteni egy halom fejfájáshoz vezetett. A LM Studio tud
automatikusan load beállítást választani, de nem találtam benne beépített lehetőséget arra, hogy sok modellt és
beállítást a saját feladataimon, módszeresen mérjek és hasonlítsak össze, ezért kezdtem el megépíteni.

## Mire használható

Már elérhető:

- **Sebesség- és memóriasweep.** Minden modellt lefuttat egy load-konfigurációs rácson, méri a prompt- és
  decode-sebességet és a VRAM-ot, és bírja a megszakításokat: szünet, leállítás, folytatás (gépújraindítás után is),
  automatikus várakozás, amíg a GPU foglalt.
- **Kiértékelés.** A lefutott sweep konfigurációit becsült válaszidő szerint rangsorolja, modellenként és
  contexthosszanként beállítást ajánl, és figyelmeztet az instabil vagy memóriahiányos eredményekre.
- **Agent-feladatok futtatása.** Egy feladatkészletet futtat egy modellen a harnessen át: toolok eldobható sandboxban,
  kör- és időkorlátok, minden lépésről trace. Minden próbálkozást a feladat pass/fail szabályai szerint ellenőriz,
  például hogy a megfelelő toolt hívta-e, és hogy a válasz tartalmazza-e a várt adatokat.
- **Próbák (haladó).** Kis scriptek, amelyek kiderítik, mit tud valójában a telepített LM Studio, például a
  speculative decodingot (draft modellek, MTP) vagy a tool-hívásokat az SDK-n át.

Tervben ([roadmap](docs/roadmap.hu.md)): minőségi
tesztcsomagok (kódolás, magyar nyelv, képfelismerés, tool-használat), speculative decoding mint sweep-dimenzió és
webes dashboard.

## Követelmények

- Windows, NVIDIA GPU (`nvidia-smi`)
- LM Studio az `lms` CLI-vel (1.2.0-val tesztelve)
- Python (3.15.2-vel tesztelve), külső csomag nélkül
- Node.js 24 vagy újabb (26.13.0-val tesztelve) és a LM Studio SDK: futtasd a `harness\` mappában az
  `npm.cmd ci --ignore-scripts` parancsot
- Microsoft Edge, csak a dokumentumok PDF-exportjához

**Ismert korlát:** a modellek a hivatalos LM Studio SDK-val töltődnek be, az SDK API-portját pedig egy belső LM Studio
fájlból olvassuk (`~\.lmstudio\apps\bionic\.internal\http-server.json`), ami más telepítésen eltérhet (a
`LMS_API_FILE` környezeti változóval felülírható). Az alkalmazásnak futnia kell. Részletek:
[load paraméterek](docs/lmstudio_load_parameters.hu.md).

## Használat

PowerShellben, a projekt mappájából.

### Telepítés friss klónból

A Python-rész csak a standard könyvtárat használja, ezért nincs `requirements.txt`, és nem kell virtuális környezet.
A harness csomagjai pontos verzióval rögzítve vannak a `harness\package-lock.json` fájlban; az `npm ci` pontosan
ezeket telepíti.

```powershell
git clone https://github.com/fulopxx/lmstudio-tuner-bench.git
cd lmstudio-tuner-bench
cd harness; npm.cmd ci --ignore-scripts; cd ..
python -m unittest discover -s tests
```

Az utolsó sor az offline teszteket futtatja (nem kell hozzá GPU és LM Studio). A harness csomagjai nélkül a harnesst
indító tesztek üzenettel kimaradnak, a `bench agent run` pedig leáll, és kiírja a futtatandó parancsot.

### Gyors kezdés

| Parancs | Mit csinál |
|---|---|
| `.\bench agent run --scripted tests\agent_scripted.json` | A példa agent-feladatokat scriptelt modellválaszokkal futtatja: nem kell hozzá GPU és LM Studio, a teljes utat megmutatja (az egyik scriptelt válasz szándékosan elbukik) |
| `.\bench run --dry-run` | Listázza a gyors sweep jobjait, nem indít semmit |

### Sebesség- és memóriasweep

Egyik terminálban a futtatás (élő napló), a másikban a vezérlés.

| Parancs | Mit csinál |
|---|---|
| `.\bench run` | Elindítja a gyors sweepet (lásd [A modellek kiválasztása](#a-modellek-kiválasztása)) |
| `.\bench run --models qwen3-8b,qwen2.5-coder-7b-instruct` | Csak a megadott modellek |
| `.\bench run --grid configs\quick.json` | Megadott rácsfájl (modellek és konfigurációk), itt a minta |
| `.\bench status --watch` | Élő státusz (3 s-onként frissül, a Ctrl+C csak a nézetből lép ki) |
| `.\bench status --jobs` | Minden job sorszámmal és állapottal |
| `.\bench pause` | Szünet az aktuális job után |
| `.\bench pause --now` | Szünet azonnal, a félbehagyott job újramérésre kerül |
| `.\bench resume` | Folytatás (szünetből, vagy leállítás / újraindítás után) |
| `.\bench resume --from 12` | A 12. jobtól mindent újramér |
| `.\bench resume --redo-failed` | A hibás és timeoutos jobokat is újraméri |
| `.\bench stop` / `.\bench stop --now` | Kilépés, később folytatható |
| `.\bench evaluate` | A lefutott sweepet becsült válaszidő szerint rangsorolja és riportot ír (offline) |
| `.\bench evaluate --in-tokens 8000 --out-tokens 300` | Ugyanez más input / output arányra |

Viselkedés:

- Szünetben és leállításkor a modell kikerül a GPU-ról, a saját indítású szerver leáll.
- A `--now` a következő ellenőrzési ponton hat. A folyamatban lévő modellbetöltést nem szakítja meg, megvárja
  (legfeljebb 240 s).
- Foglalt GPU vagy más által betöltött modell esetén a futás magától szünetel, 90 s-onként újra ellenőriz, és
  folytatódik, amint a gép felszabadult (`--busy-retry <másodperc>`, `0` esetén `resume` parancsra vár). A
  `bench pause` paranccsal kért szünet magától sosem ér véget.
- Hibás lépést nem próbál újra magától. Két egymást követő timeout után a futás megszakad.
- Ha a runtime vagy a driver verziója megváltozik, nem folytatja (`--allow-env-change` kell).
- Figyelmeztetést ír ki, ha a kiválasztott GGUF runtime-nak nincs GPU-támogatása, pedig a rács a GPU-ra offloadol.
- A LM Studio per-modell beállításfájljai nem módosulnak. A futtató a saját modelljét `bench-sweep` néven tölti be; ha
  egy megszakadt futás után bent maradt, a következő indítás eltávolítja.

### Agent-feladatok

| Parancs | Mit csinál |
|---|---|
| `.\bench agent run --model qwen3-8b` | A példafeladatokat (`tasks\examples.json`) futtatja egy modellen, és ellenőrzi a válaszokat |
| `.\bench agent run --model qwen3-8b --repeats 3 --only file-marker` | Kiválasztott feladatok, mindegyik többször |
| `.\bench agent run --model qwen3-8b --tasks <fájl> --context 16384` | Másik feladatfájl, másik contexthossz |
| `.\bench agent run --models qwen3-8b,qwen3.5-4b-mtp --tasks tasks\m1.json` | Az M1 feladatkészlet (20 feladat) több modellen, egymás után |
| `.\bench agent report` | A legutóbbi futás riportja: sikerarány intervallummal, hibakategóriák, leghosszabb megbízható lánc (offline) |
| `.\bench agent show <run> chain-3a-2` | Egy próbálkozás lépései, kijelölve a kategóriáról döntő trace-eseményt (offline) |

A feladatfájl feladatonként megadja a promptot, a modell által használható toolokat (`read_file`, `mock_lookup`), egy
opcionális mappát, amelynek fájljai a feladat sandboxába másolódnak, a mock tool válaszait (azonosítónként eredmény,
hiba vagy késleltetés) és az ellenőrzéseket, például:

```json
{ "id": "file-marker", "prompt": "What is the marker written in the file notes.txt?", "fixtures": "notes",
  "tools": ["read_file", "mock_lookup"], "checks": { "tool_called": "read_file", "answer_contains": ["BLUE-HERON-17"] } }
```

Viselkedés:

- A modell `bench-agent` néven, jól mért beállításokkal (teljes offload, f16 KV cache) töltődik be, és a végén
  eltávolításra kerül. A futás nem indul el, ha más modell van betöltve, vagy a GPU foglalt.
- Korlátok próbálkozásonként (a feladatfájlban állíthatók): 6 tool-kör, tool-hívásonként 10 s, összesen 180 s. A
  körkorlát elérésekor a modell még egy kört kap toolok nélkül, hogy válaszolhasson a felhasználónak.
- Az ismeretlen tool vagy az érvénytelen argumentum hibaként megy vissza a modellnek. A modell által sima szövegként
  kiírt tool-hívás nem fut le; a trace-ben megmarad.
- A Ctrl+C megszakítja a futó predikciót vagy tool-hívást, a próbálkozást megszakítottként rögzíti, a hátralévőket
  kihagyja; a második Ctrl+C leállítja a harnesst. A modell mindkét esetben eltávolításra kerül.
- A mintavétel a modellcsalád profilját követi a `configs\sampling.json` fájlból (értékek a modellkártyákról); a
  `--temperature` felülírja a temperature-t. Alapból feladatonként öt próbálkozás.
- Minden sikertelen próbálkozás hibakategóriát kap, bizonyítékként a trace megfelelő eseményével, és csendesnek
  jelölődik, ha a válasz semmilyen jelét nem adja a hibának ([hibataxonómia](docs/failure_taxonomy.hu.md)).
- Eredmények: próbálkozásonként egy JSON sor a `results\agent_<run>.jsonl` fájlban; minden próbálkozás trace-e (minden
  predikció, tool-hívás és eredmény) és sandboxa a `results\agent\<run>\` mappában.

### Eredmények: az M1 agent-feladatkészlet

20 feladat (közvetlen és láncolt tool-hívás, argumentumkezelés, tool-hibák, korlátok, toolt nem igénylő feladatok),
mindegyik tíz próbálkozással, 2026-11-27-én, LM Studio 1.2.0-val, egy RTX 2070-en (8 GB), 8192-es contexttel,
mintavétel a modellkártyák szerint. Sikerarány 95%-os Wilson-intervallummal; a pass^10 annak becsült esélye, hogy egy
feladat mind a tíz próbálkozásban sikerül, a feladatokra átlagolva; egy lánchossz 80%-tól számít megbízhatónak. A
teljes riport: `bench agent report`.

| Modell | Sikeres | Arány (95% CI) | pass^10 | Csendes bukás | Leghosszabb megbízható lánc |
|---|---|---|---|---|---|
| `qwen3.5-9b-deepseek-v4-flash-mtp` | 189/200 | 94% (90–97%) | 0,85 | 0 | 4 |
| `qwen3.5-4b-mtp` | 186/200 | 93% (89–96%) | 0,85 | 3 | 4 |
| `qwen3-8b` | 180/200 | 90% (85–93%) | 0,90 | 0 | 3 |
| `qwen2.5-coder-7b-instruct` | 36/200 | 18% (13–24%) | 0,15 | 14 | 0 |

- Az első három modell intervalluma átfed: ez a készlet nem rangsorolja őket.
- A Wilson-intervallum függetlennek veszi a 200 próbálkozást, ezért csak az ismétlések közti szórást mutatja ezen a
  20 feladaton. Az ugyanazon feladaton tett próbálkozások erősen összefüggenek; a feladatok újramintavételezése kb.
  kétszer szélesebb intervallumot ad (az első modellnél 90–97% helyett 85–100%).
- A `qwen3-8b` az egyik négylépéses láncot egyszer sem fejezte be (0/10); egy átmeneti tool-hibát mindegyik modell
  többnyire jelzett a felhasználónak ahelyett, hogy újrapróbálta volna.
- A `qwen2.5-coder-7b-instruct` 164 bukásából 149-ben sima szövegként írta ki a tool-hívást, így nála a készlet főleg
  ezt a formátumhibát méri, a többi képességét nem.
- Egy gép, egy feladatkészlet, helyi beállítások: a számok ezt a környezetet írják le, nem általában a modelleket.

### Próbák (haladó)

A `harness\` mappából futnak. Modelleket töltenek be a GPU-ra, és JSON eredményt írnak a `results\` mappába.

| Parancs | Mit ellenőriz |
|---|---|
| `node spec-probe.ts --plan ..\configs\spec-probe.local.json --steps P1,P2` | Speculative decoding: load draft modellel és MTP-vel, draft statisztikák, sebesség a kikapcsolt spekulációhoz képest. Előbb másold le a `configs\spec-probe.example.json` fájlt; a `--dry-run` GPU nélkül ellenőrzi a tervet |
| `node tools-probe.ts --models qwen3-8b` | Tool-hívások az SDK-n át: mit küld a modell, a tool eredményének visszaküldése, megszakítás |

## A modellek kiválasztása

A `configs\quick.json` minta modellistát tartalmaz. A saját listádhoz másold `configs\quick.local.json` néven, és ott
szerkeszd a `models` listát; ezt a fájlt a program automatikusan használja, és a git nem követi. A modellkulcsokat az
`lms ls` mutatja. Bármely más rácsfájl a `--grid <fájl>` kapcsolóval futtatható. Az ismétlésszám, a prompthossz és a
timeoutok parancssori kapcsolók, nem a rács részei (`.\bench run --help`). Az agent-futás közvetlenül a modellkulcsot
kapja (`--model`).

## Mappák

| Mappa | Tartalom |
|---|---|
| `configs\` | Sweep rácsok (modellista, alapértelmezett load beállítások, az összehasonlítandó konfigurációk), az agent-futások mintavételi profiljai és a speculative decoding próba mintaterve |
| `runner\` | Python kód: a `bench` CLI, a sweep futtató az állapot- és vezérlőfájljaival, a kiértékelés, az agent-futás (betöltés, a harness indítása, a válaszok ellenőrzése) és a közös segédfüggvények |
| `harness\` | TypeScript kód a LM Studio SDK-ra építve: a két futás közös modellbetöltője, az agent harness (`run-tasks.ts` és `agent\`: tool loop, toolok, sandbox, trace) és a próbák. Ide kerülnek majd a keresés, git és shell toolok, sandbox-korlátozással |
| `tasks\` | Agent-feladatok az ellenőrzéseikkel, és a feladatonkénti sandboxba másolt fixture-fájlok |
| `tests\` | Offline tesztek (GPU nélkül) és egy GPU-t használó live vezérlési teszt |
| `tools\` | A dokumentumok PDF-exportja és az ábragenerátor |
| `docs\` | [Roadmap](docs/roadmap.hu.md), [követelmények](docs/requirements.hu.md), [architektúra](docs/architecture.hu.md), [megállapítások](docs/findings.hu.md), [hibataxonómia](docs/failure_taxonomy.hu.md) és [load paraméterek](docs/lmstudio_load_parameters.hu.md), angolul és magyarul |

Futás közben keletkeznek, a git nem követi őket:

| Mappa | Tartalom |
|---|---|
| `results\` | Nyers eredmények: sweep jobonként vagy agent-próbálkozásonként egy JSON sor, agent trace-ek és sandboxok, próbaeredmények |
| `report\` | Sweep táblázatok és kiértékelő riportok Markdownban |
| `state\` | Sweep tervek, élő státusz és a pause, resume, stop mögötti vezérlőfájl |
| `inventory\` | A smoke teszt által mentett modellista-pillanatképek |

## Tesztek

```
python -m unittest discover -s tests   # az összes offline Python-teszt egyszerre
cd harness; npm.cmd test; npm.cmd run typecheck; cd ..   # offline (TypeScript tesztek és típusellenőrzés)
python tests\test_agent.py           # offline (a harnesst is futtatja scriptelt modellválaszokkal)
python tests\test_sweep_logic.py      # offline
python tests\test_evaluate.py         # offline
python tests\test_stream_errors.py    # offline
python tests\live_control_test.py     # GPU-t használ (kis modell, pár perc): pause / stop / resume
```

## Licenc

[MIT](LICENSE)

---

*AI-asszisztencia használatával készül.*
