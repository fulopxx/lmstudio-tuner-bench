# Feladatlista és döntések

[English](roadmap.md)

Utolsó frissítés: 2026-11-26. Cél: a letöltött helyi modellek optimalizálása és összehasonlítása a saját hardveren,
a saját felhasználási esetekre, LM Studióval.

## 1. Feladatok

Állapot: **kész** (futtatással igazolt), **részben**, **folyamatban**, **nyitott**.

| # | Feladat | Állapot |
|---|---|---|
| 1 | Sebesség- és memóriaoptimalizálás (kontextus, GPU-offload, flash attention, batch, KV-kvantálás, szálak) | részben (a próbasweep 56/56 lefutott és a `bench evaluate` kiértékelte; a tiszta sweep hátravan, a számok nem véglegesek) |
| 2 | Smoke teszt | kész |
| 3 | Élő státusz, szünet, leállítás, folytatás megadott lépéstől | részben (lásd 6. pont) |
| 4 | Kijelölhető modellek, új letöltések kezelése (modellregiszter, automatikus felvétel) | részben (kézi lista a rácsfájlban) |
| 5 | Tesztcsomag-szűrés modellképesség szerint (pl. képleírás csak vision modellen) | nyitott |
| 6 | Minőségcsomagok: kódolás; git-kezelés; magyar nyelv; képfelismerés, képleírás; alkalmazás-screenshot alapú döntés és magyarázat; játék- és 3D-tervezés (Unreal, Blender); kiberbiztonság | nyitott |
| 7 | MCP / tool-használat: formátum, tool-választás, paraméterek, eredmény feldolgozása, többlépéses lánc, párhuzamos hívás; utasításkövetés három részletességi szinten (cél, számozott lépések, egy lépés egyszerre) | részben (egyetlen tool-próba a smoke-ban) |
| 8 | Tool-timeout viselkedés mint **modellképesség**: nem próbálkozik végtelenül, idő után leáll és jelez a felhasználónak | nyitott (eddig csak a mérőrendszer saját timeoutjai vannak kész) |
| 9 | Skill-használat: megfelelő skill kiválasztása, lépések és tiltások betartása | nyitott |
| 10 | Szűk körű frontier pontozás a döntő körben | döntés nyitott |
| 11 | Webes felület és dashboard; egyszerű Excel-értékelő táblázat Excel-grafikonokkal | nyitott |
| 12 | Böngésző GPU-használatának jelzése és mérése | nyitott |
| 13 | Gitre megosztható projekt | részben (még nincs kiadva) |
| 14 | Másodlagos NiceGUI irányítófelület | nyitott, alacsony prioritás |
| 15 | Kétnyelvű (angol elsődleges, magyar) dokumentáció és felület nyelvváltással | részben (dokumentumok kész, felület nincs) |
| 16 | Agent harness: kis tool loop (fájl, keresés, git, shell) sandboxban, megszakítással, helyreállítással és kontextuskezeléssel (lásd 7. pont) | nyitott |
| 17 | Hibaelemzés: teljes trace futásonként, FMEA-jellegű hibataxonómia, trace-alapú diagnosztika, riport modellenként (lásd 7. pont) | nyitott |
| 18 | A hivatalos LM Studio SDK kipróbálása a telepített verzión; ha működik, kiváltja a config fájlok módosítását | nyitott |
| 19 | Modellenkénti tool-call eltérések és javítási módszerek (retry, séma-kényszerítés, grammar) | nyitott |
| 20 | Rögzített, reprodukálható eval-feladatkészlet pass/fail ellenőrzéssel és ismételt futásokkal | nyitott |
| 21 | Megszakítás- és helyreállítás-tesztek: leállítás tool-hívás közben, félbehagyott kimenet, folytatás | nyitott |
| 22 | Kontextuskezelés mérése: vágás, összegzés, tool-eredmény méretkorlát, viselkedés növekvő kontextusnál | nyitott |
| K | **Külön feladat:** agent skillek (pl. session-export) átvitele úgy, hogy LM Studióban kompatibilisen működjenek | még nem vizsgált |

### Tervezett fejlesztések

- Eredményformátum: sémaverzió és hardver-ujjlenyomat (GPU, driver, LM Studio és runtime verzió).
- Döntő kör: több ismétlés; a kontextus és a KV-kvantálás hatásának szétválasztása.
- Modellenként ajánlott preset, összevetve a jelenlegi LM Studio-beállításokkal. Alkalmazás csak megerősítés után.
- Később: speculative decoding és mintavételi paraméterek hangolása.

## 2. Sorrend

### M1 mérföldkő: első publikus kiadás

Az M1 az első: egy vékony, végigmenő szelet, amely működik. Az alábbi A–L táblázat az utána következő munkára vonatkozik.

| M1 lépés | Tartalom | Állapot |
|---|---|---|
| 1 | SDK-próba a telepített LM Studión (18. feladat) | nyitott |
| 2 | Tiszta sweep, kiértékelés, ajánlott beállítás modellenként | folyamatban |
| 3 | Repó előkészítése, licenc, publikus kiadás | folyamatban |
| 4 | Minimális TypeScript harness: 1–2 tool (fájlolvasás és mock, shell nélkül), timeout, megszakítás, trace | nyitott |
| 5 | 10–20 rögzített feladat, ismételt futások, hibakategória-riport | nyitott |
| 6 | Eredménytábla a README-ben | nyitott |

M1 után: webes dashboard, minőségcsomagok, kontextuskezelés mérése, NiceGUI.

### Teljes sorrend

| Lépés | Tartalom |
|---|---|
| A | Próbasweep kiértékelése, döntő kör |
| B | Repó előkészítése, dokumentumok angol és magyar változata |
| C | Core és CLI szétválasztása, eredményformátum verzióval, modellregiszter |
| D | `docs/architecture.md` véglegesítése: adatformátumok, vezérlési interfész |
| E | HTML dashboard és Excel-export (D után) |
| F | Webes vezérlőfelület |
| G | Agent harness: tool loop, sandbox, trace log, CLI |
| H | Tool-calling, timeout- és utasításkövetés-csomag a harnessen futtatva |
| I | Hibaelemzés: kategóriák és modellenkénti riport |
| J | Minőségcsomagok |
| L | NiceGUI másodlagos felület (alacsony prioritás) |
| K | Skill-átvitel (külön feladat) |

Az E–F és a G–J párhuzamosan haladhat. A webes felület **tervezése** (nézetek, drótváz) kód nélkül korábban is
elkezdhető.

## 3. Döntések

| Téma | Döntés |
|---|---|
| Per-modell LM Studio config-fájlok | A mérés ideiglenesen írhatja, mentéssel és visszaállítással |
| Hibakezelés | Nincs automatikus újrapróbálás; két egymást követő timeout után megszakítás; foglalt GPU esetén szünet |
| Frontend | React + Vite + TypeScript, Mantine, Apache ECharts |
| Backend | FastAPI, csak `127.0.0.1` |
| Statisztika | Medián és szórás, Pareto-front, állítható súlyozott pontszám, bootstrap bizalmi intervallum; páros bírálatnál Elo / Bradley–Terry. ML/DL nem szükséges |
| Nyelv | Az angol az elsődleges, mindenből készül magyar változat is (dokumentumok, README, felület). A GitHub angol README-je linkel a magyarra |
| Fájlnév-konvenció | `név.md` angol, `név.hu.md` magyar; a PDF-ek ugyanígy |
| Magyar szóhasználat | Az angolul elterjedt vagy jó magyar megfelelő nélküli szakkifejezés angolul marad, főleg a felületen |
| Kód | Angol kód, angol kommentek |
| Agent harness | Saját modul hibaelemzéssel, kezdettől TypeScriptben. Az első változatban nincs shell tool |
| LM Studio elérés | Először a hivatalos SDK; nem dokumentált config fájl csak ott, ahol az SDK nem elég |
| Fókusz | A projekt megkülönböztetője a hibataxonómia és a trace-alapú diagnosztika; a sebességmérés az alap |
| Licenc | MIT |
| CLI-paritás | A terminálos változat elsőbbséget élvez: mindent tudnia kell, a grafikus felületek nem tudhatnak többet. Új funkció először a core-ban és a CLI-ben jelenik meg |
| GUI-réteg | Vékony réteg a core felett, saját mérési és értékelési logika nélkül; a grafikonok mögötti adat a CLI-ből is elérhető. Teszt ellenőrzi, hogy minden API-műveletnek van CLI-párja |
| Webes fejlesztés | A D lépés után indul, a `web/` mappában; előbb a core interfészét egyeztetjük |

## 4. Követelmények a felülethez

- Indítás, szünet, folytatás, leállítás; élő státusz.
- Nézetek: Pareto-pontdiagram (VRAM–sebesség, méret = kontextus), modell × tesztcsomag hőtérkép, radar 2–4 modellre,
  szűrhető táblázat Excel-exporttal.
- Méréskor figyelmeztetés: a böngésző VRAM-ot és GPU-t használ.
- Böngésző-többlet mérése rögzített konfiguráción: dashboard zárva / nyitva gyorsítással / nyitva gyorsítás nélkül.
  Legyen benne offloadolt konfiguráció is (gyorsítás nélkül a CPU terhelése nő). A folyamatonkénti VRAM kiolvasásának
  módja ellenőrizendő (`nvidia-smi` ezen a gépen `N/A`-t ad).
- Az eredménysor rögzítse, hogy mérés közben nyitva volt-e a dashboard.
- A lefordított frontend mellékelhető legyen, hogy a használathoz ne kelljen Node.js.
- Nyelvváltás angol és magyar között; a szövegek nyelvi fájlokban, az angol az alapértelmezett.

## 5. Tesztelés (tervezett)

- Python logika és FastAPI: `pytest` (a meglévő `unittest` tesztek futtathatók vele).
- React komponensek: Vitest + React Testing Library.
- Végpontok közötti: Playwright, hamis futtatóval és rögzített mintaeredményekkel, GPU nélkül. Mérés közben nem fut.
- GPU-s élő tesztek külön, kézzel indítva (`tests\live_control_test.py`).

## 6. Nyitott műszaki pontok

- A 2026-11-26-i 56 feladatos futás próbafutás: közben más programok is futhattak és CPU-t terheltek, a számai nem
  véglegesek. Tiszta, teljes sweep később, üres gép mellett.

- Élőben nem próbált: `stop --now`, automatikus szünet foglalt GPU-nál, Ctrl+C, folytatás gépújraindítás után,
  betöltési timeout, `--redo-failed`.
- A megosztott GPU-memóriába csordulás felismerése: a mostani `near_vram_limit` jelző valószínűleg nem elég (a futó
  sweep részeredményeiben van olyan sebességesés, amelyet nem jelzett; ok még nem igazolt).
- A CLI `lms load` út és a default-config értékek viszonya nem mért.
- A sebességmérés csak szabad GPU-n érvényes.
- A tiszta sweephez: finomabb offload-lépések, valamint batch méret hosszabb context mellett a 12–14B modelleknél;
  a contexthossz és a KV-kvantálás szétválasztása; a contextet ténylegesen kitöltő promptok; legalább 3 ismétlés; a
  megosztott GPU-memória mérése a sebességből történő következtetés helyett.

## 7. Agent harness és hibaelemzés: kezdeti követelmények

Vázlat, a G lépés előtt részletezendő.

**Harness**

- TypeScriptben készül; a LM Studióval a hivatalos SDK-n át beszél, ha a próba (18. feladat) sikeres.
- A modellt tool loopban futtatja. Az első változatban csak fájlolvasás és mock toolok vannak (a mock toolok
  determinisztikus teszteket adnak); a keresés, git és shell a sandbox-döntés után jön.
- Minden eldobható sandbox mappában fut; alapértelmezetten hálózat nélkül.
- Korlátok: timeout tool-hívásonként, maximális lépésszám feladatonként, nincs végtelen újrapróbálás; korlát elérésekor
  a felhasználó jelzést kap.
- Megszakítás és folytatás; tiszta helyreállítás tool-hibából és érvénytelen modellkimenetből.
- Kontextuskezelés: beszélgetési előzmény, tool-eredmények, mi történik a kontextus betelésekor.
- Mint minden funkció, először CLI-ből használható.

**Hibaelemzés**

- Minden lépés naplózva: prompt, modellkimenet, tool-hívás, tool-eredmény, idő, tokenek.
- Hibakategóriák (első készlet): érvénytelen tool-hívás formátum, rossz tool, rossz paraméterek, figyelmen kívül
  hagyott tool-hiba, végtelen újrapróbálás vagy ciklus, korlát elérése a felhasználó értesítése nélkül, kontextus
  túlcsordulás, hibás eredmény helyes lépések ellenére.
- Minden kategória FMEA-jelleggel leírva: hibamód, hatás, detektálás, ellenintézkedés. A riport nem csak számol,
  hanem ellenintézkedést is javasol.
- Riport modellenként és feladatonként: sikerarány, kategóriák, a leghosszabb még megbízható lánc.
- A feladatok rögzítettek és reprodukálhatók, pass/fail ellenőrzéssel; a szórás miatt mindegyik többször fut.
- Modellenkénti tool-call formátumok összevetése: hol romlik el a JSON, és melyik javítás segít (retry,
  séma-kényszerítés, grammar).
- Megszakítás és helyreállítás esetei: leállítás tool-hívás közben, félbehagyott kimenet, folytatás.
- Második kör (M1 után): kontextus vágása és összegzése, tool-eredmény méretkorlát, viselkedés növekvő kontextusnál.

**Nyitott**

- A Python core és a TypeScript harness közötti interfész (processhatár, trace-formátum).
- Hogyan korlátozza a sandbox a modell által generált shell-parancsokat. Ezt az első ilyen parancs futtatása előtt el
  kell dönteni.
- Működik-e az SDK a telepített LM Studio verzióval, és lefedi-e a CPU-szálakat (a load config forrásában nem
  találtunk ilyen mezőt; a llama.cpp argumentum-felülírás talán megoldja).
