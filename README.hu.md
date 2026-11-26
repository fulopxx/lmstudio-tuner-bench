# lmstudio-tuner-bench

[English](README.md)

Helyi LLM modellek sebesség- és memóriamérése, valamint load paramétereinek hangolása LM Studióval, a saját
hardvereden. Minőségi tesztcsomagok és webes dashboard tervben vannak ([roadmap](docs/roadmap.hu.md)).

> Nem hivatalos eszköz, nem áll kapcsolatban az LM Studio fejlesztőivel.
> Korai állapot: egyetlen gépen próbáltuk.

## Motiváció

Rengeteg modellt letöltöttem, aztán a saját gépemen szerettem volna tudni, melyik mit tud, mire tudom jól használni,
és hogyan futtathatom optimalizálva. Ezt kézzel kideríteni egy halom fejfájáshoz vezetett. A LM Studio tud
automatikusan load beállítást választani, de nem találtam benne beépített lehetőséget arra, hogy sok modellt és
beállítást a saját feladataimon, módszeresen mérjek és hasonlítsak össze, ezért kezdtem el megépíteni.

## Követelmények

- Windows, NVIDIA GPU (`nvidia-smi`)
- LM Studio az `lms` CLI-vel (1.2.0-val tesztelve)
- Python (3.15.2-vel tesztelve), külső csomag nélkül
- Microsoft Edge, csak a dokumentumok PDF-exportjához

**Ismert korlát:** a KV-kvantálás, a szálszám és a GPU-offload a LM Studio nem dokumentált, per-modell config
fájljain keresztül állítható. A mappa útvonala a `runner\config_store.py`-ban rögzített, és más telepítésen eltérhet.
Részletek: [load paraméterek](docs/lmstudio_load_parameters.hu.md). A hivatalos SDK a jelek szerint ezek többségét
elérhetővé teszi; még nincs kipróbálva.

## Futtatás

PowerShellben, a projekt mappájából. Egyik terminálban a futtatás (élő napló), a másikban a vezérlés.

| Parancs | Mit csinál |
|---|---|
| `.\bench run --dry-run` | Listázza a jobokat, nem indít semmit |
| `.\bench run` | Elindítja a gyors sweepet (lásd [A modellek kiválasztása](#a-modellek-kiválasztása)) |
| `.\bench run --models qwen3-8b,qwen2.5-coder-7b-instruct` | Csak a megadott modellek |
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

## Viselkedés

- Szünetben és leállításkor a modell kikerül a GPU-ról, a saját indítású szerver leáll, a config fájlok visszaállnak.
- A `--now` a következő ellenőrzési ponton hat. A folyamatban lévő modellbetöltést nem szakítja meg, megvárja
  (legfeljebb 240 s).
- Foglalt GPU vagy más által betöltött modell esetén a futás magától szünetel, és csak `resume` parancsra folytatódik.
- Hibás lépést nem próbál újra magától. Két egymást követő timeout után a futás megszakad.
- Ha a runtime vagy a driver verziója megváltozik, nem folytatja (`--allow-env-change` kell).
- A per-modell config fájlokat csak a load idejére módosítja. Megszakadt futás után a következő indítás először
  visszaállít. Mérés közben ne módosítsd a modellbeállításokat a LM Studio felületén.

## A modellek kiválasztása

A `configs\quick.json` minta modellistát tartalmaz. A saját listádhoz másold `configs\quick.local.json` néven, és ott
szerkeszd a `models` listát; ezt a fájlt a program automatikusan használja, és a git nem követi. A modellkulcsokat az
`lms ls` mutatja.

## Mappák

`configs\` rácsok · `runner\` scriptek · `results\` nyers eredmények · `report\` táblázatok · `state\` futásállapot ·
`backups\` config-mentések · `docs\` dokumentáció · `tools\` segédeszközök · `tests\` tesztek

## Tesztek

```
python tests\test_config_store.py     # offline
python tests\test_sweep_logic.py      # offline
python tests\test_evaluate.py         # offline
python tests\live_control_test.py     # GPU-t használ (kis modell, pár perc): pause / stop / resume
```

## Licenc

[MIT](LICENSE)

---

*AI-asszisztencia használatával készül.*
