# Feladatlista és döntések

[English](roadmap.md)

Utolsó frissítés: 2026-11-27. Cél: a letöltött helyi modellek optimalizálása és összehasonlítása a saját hardveren,
a saját felhasználási esetekre, LM Studióval.

Kapcsolódó dokumentumok: [követelmények](requirements.hu.md) (felület, tesztelés, agent harness, speculative decoding,
bias-vizsgálat, feladatkészletek, core és eredményformátum, vezérlő interfész) és [mérési megállapítások](findings.hu.md).

## 1. Feladatok

Állapot: ✅ **kész** (futtatással igazolt), 🟡 **részben**, 🔵 **folyamatban**, ⚪ **nyitott**.

| # | Feladat | Állapot |
|---|---|---|
| 1 | Sebesség- és memóriaoptimalizálás (kontextus, GPU-offload, flash attention, batch, KV-kvantálás, szálak) | 🟡 részben (a 2026-11-26-i tiszta sweepek kiértékelve, az ajánlott beállítások rögzítve; nyitott: a VRAM határán lévő esetek, kitöltött context, a KV-kvantálás minőségi hatása, presetek; lásd [megállapítások](findings.hu.md)) |
| 2 | Smoke teszt | ✅ kész |
| 3 | Élő státusz, szünet, leállítás, folytatás megadott lépéstől | 🟡 részben (lásd 4. pont) |
| 4 | Kijelölhető modellek, új letöltések kezelése (modellregiszter, automatikus felvétel) | 🟡 részben (modellregiszter a `bench models` parancsokkal és az új letöltések jelzése, 2026-11-27; új modellek automatikus felvétele futás közben nyitott) |
| 5 | Tesztcsomag-szűrés modellképesség szerint (pl. képleírás csak vision modellen) | 🟡 részben (`--where` képességszűrő a futásokhoz, 2026-11-27; a szükséges képességeiket deklaráló tesztcsomagok nyitottak, lásd követelmények TS-01) |
| 6 | Minőségcsomagok: kódolás; git-kezelés; magyar nyelv; képfelismerés, képleírás; alkalmazás-screenshot alapú döntés és magyarázat; játék- és 3D-tervezés (Unreal, Blender); kiberbiztonság | ⚪ nyitott |
| 7 | MCP / tool-használat: formátum, tool-választás, paraméterek, eredmény feldolgozása, többlépéses lánc, párhuzamos hívás; utasításkövetés három részletességi szinten (cél, számozott lépések, egy lépés egyszerre) | 🟡 részben (M1 feladatkészlet, élőben mérve négy modellen: tool-választás, argumentumok, hiba- és eredménykezelés, legfeljebb négylépéses láncok, toolt nem igénylő feladatok; nyitott: párhuzamos hívás, a három utasításszint, valódi MCP szerver) |
| 8 | Tool-timeout viselkedés mint **modellképesség**: nem próbálkozik végtelenül, idő után leáll és jelez a felhasználónak | 🟡 részben (M1 feladatok tool-timeouttal és átmeneti hibával: jelzi-e a modell a problémát, vagy újrapróbálja; a végtelen próbálkozás `loop`-ként látszik; a modell által magának szabott korlátot nem mérjük) |
| 9 | Skill-használat: megfelelő skill kiválasztása, lépések és tiltások betartása | ⚪ nyitott |
| 10 | Szűk körű frontier pontozás a döntő körben | ⚪ nyitott (döntés függőben) |
| 11 | Webes felület és dashboard; egyszerű Excel-értékelő táblázat Excel-grafikonokkal | ⚪ nyitott |
| 12 | Böngésző GPU-használatának jelzése és mérése | ⚪ nyitott |
| 13 | Gitre megosztható projekt | ✅ kész (2026-11-27 óta publikus a GitHubon) |
| 14 | Másodlagos NiceGUI irányítófelület | ⚪ nyitott, alacsony prioritás |
| 15 | Kétnyelvű (angol elsődleges, magyar) dokumentáció és felület nyelvváltással | 🟡 részben (dokumentumok kész, felület nincs) |
| 16 | Agent harness: kis tool loop (fájl, keresés, git, shell) sandboxban, megszakítással, helyreállítással és kontextuskezeléssel (lásd [követelmények](requirements.hu.md), 3. pont) | 🟡 részben (M1 harness: fájlolvasás és mock toolok, korlátok, leállítás, trace; keresés, git, shell, helyreállítás és kontextuskezelés nyitott) |
| 17 | Hibaelemzés: teljes trace futásonként, FMEA-jellegű hibataxonómia, trace-alapú diagnosztika, riport modellenként (lásd [követelmények](requirements.hu.md), 3. pont) | 🟡 részben (2. verziós taxonómia, szabályalapú kategorizáló bizonyítékkal, modellenkénti riport intervallumokkal, kézi átnézés kész; nyitott: átmenetgráf, értékek eredete, LLM-bíró) |
| 18 | A hivatalos LM Studio SDK kipróbálása a telepített verzión; ha működik, kiváltja a config fájlok módosítását | ✅ kész |
| 19 | Modellenkénti tool-call eltérések és javítási módszerek (retry, séma-kényszerítés, grammar) | ⚪ nyitott |
| 20 | Rögzített, reprodukálható eval-feladatkészlet pass/fail ellenőrzéssel és ismételt futásokkal | ✅ kész (M1 feladatkészlet, 2026-11-27: 20 feladat referenciamegoldással, ismételt futások; további készletek a 6. feladattal jönnek) |
| 21 | Megszakítás- és helyreállítás-tesztek: leállítás tool-hívás közben, félbehagyott kimenet, folytatás | ⚪ nyitott |
| 22 | Kontextuskezelés mérése: vágás, összegzés, tool-eredmény méretkorlát, viselkedés növekvő kontextusnál | ⚪ nyitott |
| 23 | Vizsgálat: biased-e egy modell? Tényezők, tesztpromptok, mérés modellenként (lásd [követelmények](requirements.hu.md), 4. pont) | ⚪ nyitott (még nem vizsgált) |
| 24 | Speculative decoding mint optimalizálási dimenzió: draft modell és MTP a kikapcsolt spekulációval összevetve, feladattípusonként (lásd [követelmények](requirements.hu.md), 5. pont) | 🔵 folyamatban (a 0. fázis kész; az 1. fázis nyitott) |
| 25 | Követelmény-traceability: a tesztek megnevezik az általuk lefedett követelmény-azonosítókat; egy script elkészíti a mátrixot (követelmény → tesztek → offline, élő, nem lefedett), és hibát jelez ismeretlen vagy a két nyelvben eltérő azonosítónál | ⚪ nyitott |
| 26 | Követelményminőség: a meglévő követelmények átnézése a [követelmények](requirements.hu.md) írási szabályai szerint, az ellenőrzés oszlop felvétele | ⚪ nyitott |
| 27 | Modellek statisztikai összehasonlítása: feladatszintű intervallumok (bootstrap a feladatokon), feladatonként párosított különbség „gyakorlatilag egyenértékű” kimenettel, `pass@k`, és egy „futassunk még?” tanácsadó, amely megbecsüli a futásidőt, és megmondja, hogy több ismétlés vagy több feladat szűkítené-e az eredményt. A Wilson-intervallum függetlennek veszi a próbálkozásokat; a tíz ismétléses M1 futáson a feladatszintű intervallumok kb. kétszer szélesebbek voltak (2026-11-27, [megállapítások](findings.hu.md)) | ⚪ nyitott (a publikálás után) |
| 28 | Csak olvasó MCP szerver a mérési eredményekhez: vékony réteg a core felett, minden tool egy CLI-parancsnak felel meg; először stdio transport, MCP Inspectorral kipróbálva. Az SDK verzióját felvétel előtt ellenőrizzük, a tulajdonos telepíti rögzített verzióval. Az MCP-n kiszolgált mock toolok a 7. feladathoz tartoznak | ⚪ nyitott (a publikálás után) |
| 29 | Modellismertető: egy jól átlátható dokumentum minden addig tesztelt modellről, benne minden, amit tudunk és mértünk róla (képességek a forrásukkal: LM Studio vagy modellkártya; modellkártya-adatok; mintavételi profil; saját címkék; sebesség és ajánlott load-beállítás; agent- és minőségeredmények a bizonytalanságukkal), hogy egy adott problémára kiolvasható legyen belőle, melyik modelleket ajánljuk, és ha van ilyen, melyik a legjobb. A core állítja elő a regiszterből és az eredményekből, először a CLI mutatja | ⚪ nyitott (a cél 2026-11-27-én rögzítve; a követelmények még megírandók) |
| K | **Külön feladat:** agent skillek (pl. session-export) átvitele úgy, hogy LM Studióban kompatibilisen működjenek | ⚪ nyitott (még nem vizsgált) |

### Tervezett fejlesztések

- Eredményformátum: sémaverzió és hardver-ujjlenyomat (GPU, driver, LM Studio és runtime verzió).
- Modellenként ajánlott preset, összevetve a jelenlegi LM Studio-beállításokkal. Alkalmazás csak megerősítés után.
- Később: mintavételi paraméterek hangolása.
- M1 után (17. feladat): sok próbálkozás összesített tool-átmenet gráfja (élvastagság = gyakoriság; ciklusok és a
  helyes lánctól való letérések), modell, feladat és kategória szerint szűrhetően, a core DOT-exportjával.

## 2. Sorrend

### M1 mérföldkő: első publikus kiadás

Az M1 az első: egy vékony, végigmenő szelet, amely működik. Az alábbi A–L táblázat az utána következő munkára vonatkozik.

| M1 lépés | Tartalom | Állapot |
|---|---|---|
| 1 | SDK-próba a telepített LM Studión (18. feladat) | ✅ kész |
| 2 | Tiszta sweep, kiértékelés, ajánlott beállítás modellenként | ✅ kész |
| 3 | Repó előkészítése, licenc, publikus kiadás | ✅ kész (2026-11-27: titkok, személyes adatok és útvonalak ellenőrzése a git-előzménnyel együtt, telepítés friss klónból, publikus repó, `v0.1.0` kiadás) |
| 4 | Minimális TypeScript harness: 1–2 tool (fájlolvasás és mock, shell nélkül), timeout, megszakítás, trace | ✅ kész (2026-11-26: `bench agent run`, élőben 4/4 példafeladat egy modellen; a Ctrl+C leállítás csak offline tesztelve) |
| 5 | 10–20 rögzített feladat, ismételt futások, hibakategória-riport | ✅ kész (2026-11-27: feladatkészlet, riport, élő futások 4 modell × 20 feladat × 5 és × 10, a bukások kézi átnézése, 2. verziós taxonómia) |
| 6 | Eredménytábla a README-ben | ✅ kész (2026-11-27, tíz ismétléses M1 futás) |

M1 után: webes dashboard, minőségcsomagok, kontextuskezelés mérése, NiceGUI.

### Teljes sorrend

| Lépés | Tartalom | Állapot |
|---|---|---|
| A | Próbasweep kiértékelése, döntő kör | ✅ kész (a próbasweep és a tiszta sweepek kiértékelve) |
| B | Repó előkészítése, dokumentumok angol és magyar változata | ✅ kész (kétnyelvű dokumentumok; 2026-11-27 óta publikus) |
| C | Core és CLI szétválasztása, eredményformátum verzióval, modellregiszter | ✅ kész (2026-11-27: [követelmények](requirements.hu.md), 7. pont: C1 csomagszerkezet, C2 core függvények, C3 eredményformátum és gépfüggő beállítások, C4 modellregiszter) |
| D | `docs/architecture.md` véglegesítése: adatformátumok, vezérlési interfész | ✅ kész (2026-11-27: [architektúra](architecture.hu.md), 10. pont, vezérlő interfész és adatformátumok; [követelmények](requirements.hu.md), 8. pont) |
| D2 | A vezérlő interfész a core-ban és a CLI-ben ([követelmények](requirements.hu.md), 8. pont, IF-01–IF-23), az E előtt | 🔵 folyamatban (a D2a 2026-11-27-én kész, offline tesztekkel: `bench/core/runstate.py`, `state/runs/<id>/` sweep- és agent-futásnál, `state/active.json` zár; az élő ellenőrzés sweeppel 2026-11-27-én sikeres: sweep közben elutasított agent-futás, szünet, folytatás, leállítás és `resume --from` futásonkénti állapottal, a végén felszabaduló zár. A D2b 2026-11-27-én kész, offline tesztekkel: minden előrehaladás-sor a `progress.log`-ban, minden kérés forrása (`cli`, `web`, `runner`) a `control.json`-ban és a `bench status` kimenetében, `bench stop` agent-futásra a vezérlőfájlon át; az élő ellenőrzés 2026-11-27-én sikeres (`20261127_220023` agent-futás, `qwen3-1.7b`: zár és saját állapot, elutasított sweep és szünet, a leállítás 0,47 s alatt jutott el a harnessig, `stopped` állapot, felszabadult zár, nem maradt betöltött modell). A D2c 2026-11-27-én kész, offline tesztekkel: `--json` minden parancson, egy dokumentum `schema_version` 1 mezővel, a hibák JSON-ként, változatlan kilépési kóddal, az előrehaladás a standard erroron; az `evaluate` és az `agent report` strukturált adatot is visszaad. A terv 2026-11-27-én elfogadva: D2a futásonkénti állapot és egyszerre egy GPU-futás, IF-10, IF-11, IF-13; D2b előrehaladás-napló, a kérés forrása, agent-leállítás vezérlőfájlon át, IF-12, IF-14, IF-15; D2c `--json`, IF-01; D2d `bench check`, `bench runs`, `bench close` (az állapotgép-változást előbb a tulajdonos látja), IF-20–IF-22; D2e sémaverziók, IF-23. Az IF-02–IF-04 API-követelmények az API-val jönnek) |
| E | HTML dashboard és Excel-export (D után) | ⚪ nyitott |
| F | Webes vezérlőfelület | ⚪ nyitott |
| G | Agent harness: tool loop, sandbox, trace log, CLI | 🟡 részben (M1 harness: tool loop, sandbox, trace, `bench agent`; a keresés, git és shell toolok nyitottak) |
| H | Tool-calling, timeout- és utasításkövetés-csomag a harnessen futtatva | 🟡 részben (tool-hívás és timeout az M1 feladatkészletben; az utasításkövetés nyitott) |
| I | Hibaelemzés: kategóriák és modellenkénti riport | ✅ kész (2. verziós taxonómia és modellenkénti riport, 2026-11-27) |
| J | Minőségcsomagok | ⚪ nyitott |
| L | NiceGUI másodlagos felület (alacsony prioritás) | ⚪ nyitott (alacsony prioritás) |
| K | Skill-átvitel (külön feladat) | ⚪ nyitott (külön feladat) |

Az E–F és a G–J párhuzamosan haladhat. A webes felület **tervezése** (nézetek, drótváz) kód nélkül korábban is
elkezdhető.

A 24. feladat (speculative decoding): a rövid próba (0. fázis) az M1 4. lépése előtt, a beépítés az M1 után, a C
lépéssel együtt.

## 3. Döntések

### Mérés és futtató

| Téma | Döntés |
|---|---|
| Per-modell LM Studio config-fájlok | Nem módosulnak; a futtató az SDK-val tölt be |
| LM Studio elérés | Load a hivatalos TypeScript SDK-val (igazolt); CPU-szálak a llama.cpp argumentum-felülírással; a sweep futtató ezt használja |
| Hibakezelés | Hibás lépést nem próbál újra magától; két egymást követő timeout után megszakítás; foglalt GPU esetén szünet, 90 s-onként újraellenőrzés és automatikus folytatás (a kézi szünet megmarad) |
| Statisztika | Medián és szórás, Pareto-front, állítható súlyozott pontszám, bootstrap bizalmi intervallum; páros bírálatnál Elo / Bradley–Terry. ML/DL nem szükséges |
| Speculative decoding kapcsolása | Csak a loadnál, az SDK load mezőivel (`speculativeDraftMtp`; `speculativeDraftSimple` a `speculativeDraftModel` mezővel); mérés a REST-en, amely visszaadja a draft számlálókat (0. fázis, 2026-11-26) |
| Speculative decoding | A kikapcsolt spekuláció marad a baseline, és az is lehet az ajánlás; egyelőre csak LM Studio, második backendről (`llama-server`) később döntünk, ha az eredmények indokolják |

### Architektúra és felület

| Téma | Döntés |
|---|---|
| CLI-paritás | A terminálos változat elsőbbséget élvez: mindent tudnia kell, a grafikus felületek nem tudhatnak többet. Új funkció először a core-ban és a CLI-ben jelenik meg |
| GUI-réteg | Vékony réteg a core felett, saját mérési és értékelési logika nélkül; a grafikonok mögötti adat a CLI-ből is elérhető. Teszt ellenőrzi, hogy minden API-műveletnek van CLI-párja |
| Frontend | React + Vite + TypeScript, Mantine, Apache ECharts |
| Backend | FastAPI, csak `127.0.0.1` |
| Webes fejlesztés | A D lépés után indul, a `web/` mappában; előbb a core interfészét egyeztetjük |
| Agent harness | Saját modul hibaelemzéssel, kezdettől TypeScriptben. Az első változatban nincs shell tool |
| Harness interfész | Modellenként és feladatcsomagonként egy harness process, JSON spec a stdinen, `RESULT:` összegzés, JSONL trace; ellenőrzés és kategorizálás a core-ban; saját tool loop SDK-s és scriptelt backenddel (2026-11-26; [követelmények](requirements.hu.md), 3. pont) |
| Agent-eredmények nézetei | A táblázatokat és a gráfmodelleket a core állítja elő, a CLI exportálja (JSON; DOT, amikor az első gráfnézet készül); a felületek csak rajzolnak. Harmadik felület nincs (tkinter sem). Gráfkönyvtár (`networkx`) vagy a Graphviz bináris csak külön döntéssel, ha gráfalgoritmus kell (2026-11-26) |

### Nyelv és dokumentáció

| Téma | Döntés |
|---|---|
| Nyelv | Az angol az elsődleges, mindenből készül magyar változat is (dokumentumok, README, felület). A GitHub angol README-je linkel a magyarra |
| Fájlnév-konvenció | `név.md` angol, `név.hu.md` magyar; a PDF-ek ugyanígy |
| Magyar szóhasználat | Az angolul elterjedt vagy jó magyar megfelelő nélküli szakkifejezés angolul marad, főleg a felületen |
| Kód | Angol kód, angol kommentek |

### Projekt

| Téma | Döntés |
|---|---|
| Fókusz | A projekt megkülönböztetője a hibataxonómia és a trace-alapú diagnosztika; a sebességmérés az alap |
| Licenc | MIT |

## 4. Nyitott műszaki pontok

### Mérés

| Pont | Jelenlegi ismeret | Állapot |
|---|---|---|
| Megosztott GPU-memóriába csordulás | A `near_vram_limit` jelző nem elég (a tiszta sweepben egy lassú konfiguráció a küszöbe alatt maradt). A kiértékelés `spill?` jelzője a sebességből következtet; a megosztott GPU-memóriát nem mérjük | ⚪ nyitott |
| Kitöltött context | A sweepekben nincsenek a contextet ténylegesen kitöltő promptok | ⚪ nyitott |
| Háttér VRAM-foglalás | A sebességmérés csak szabad GPU-n érvényes. Hiányzik a mód arra, hogy a VRAM határán lévő konfigurációk összehasonlításakor a háttérfoglalás rögzített vagy kontrollált legyen | ⚪ nyitott |
| CLI `lms load` | A per-modell default config értékekhez való viszonya nem mért | ⚪ nyitott |
| Speculative decoding | A 0. fázis próbája 2026-11-26-án kész ([követelmények](requirements.hu.md), 5. pont): csak a loadnál kapcsolható, számlálók az SDK-ban és a REST-ben. Nyitott az 1. fázisra: a draft párok kompatibilitás-ellenőrzése, a maximális draft token, miért tér el a greedy kimenet a baseline-tól | ⚪ nyitott |
| Értékek eredete az agent-trace-ekben | Egy gráf arról, honnan származik egy argumentum- vagy válaszérték (prompt, korábbi tool-eredmények), kiválthatná a `wrong_arguments/invented_value` mögötti szövegkeresést, és megmutatná, hogyan jut el egy tool-hiba a válaszig. Az élek meghatározása bizonytalan, mert a modellek átfogalmazzák az értékeket; M1 után kipróbálandó | ⚪ nyitott |
| LLM-bíró a heurisztikus szabályokhoz | A kulcsszólisták soha nem teljesek: az első élő M1 futás négy rést mutatott (2026-11-27). Javaslat M1 utánra, a 10. feladat mellé: második vélemény csak a heurisztikus döntésekhez (jelezte-e a válasz a hibát vagy a korlátot, kitalált-e értéket), írott pontozási szempontrendszerrel és a mért modelltől eltérő bíró modellel, a futás után offline. A szabály marad az elsődleges döntés; a riport megmutatja, hol tér el a bíró és a szabály, és csak ezek az esetek mennek kézi átnézésre. Használat előtt a bírót kézi címkéken kalibráljuk (egyezési mutató, pl. Cohen-féle kappa); a saját bias-a ismert kockázat | ⚪ nyitott |
| Mintavételi profil mintái | A `configs/sampling.json` Qwen3-mintája nem ismeri a tizedes méretet (a `qwen3-1.7b` egy élő futásban a tartalék profilt kapta, 2026-11-27), a nem gondolkodó `Qwen3-4B-Instruct-2507` pedig a gondolkodó profilt kapná. Javítás a letöltések után: profilok a modellkártyák szerint, és teszt a modellkulcs → profil megfeleltetésre A letöltések után 2026-11-27-én újra átnézve: a `ministral-3-8b-instruct-2512` profilt kapott (a kártyája 0,1 alatti temperature-t kér, ezért az ismétlések alig térnek el); a `granite-3.3-8b-instruct` és a `phi-4-mini-instruct` a tartalék profilon marad, mert a kártyájuk nem ad mintavételi értéket. Mindkettő function callingot ír, amit a LM Studio nem jelöl: egy saját `tool_use` címke választja ki őket a `--where tool_use` szűrésnél. | ✅ kész (2026-11-27: a tizedes méret illeszkedik, profil a `Qwen3-4B-Instruct-2507` kártyája szerint, teszt a modellkulcs → profil megfeleltetésre; a 0.5B-s kódmodell kártyája 1,05-ös repeat penaltyt ír a 7B 1,1-ével szemben, 1,1 maradt, mert a 0.5B draft modellként szolgál) |
| Modellregiszter: új modellek dátum szerint | Két pillanatképpel az „új” jelzés a következő frissítéskor eltűnik. Javaslat (2026-11-27): modellenként `first_seen` dátum az előző pillanatkép helyett, `bench models list --new` és `--refresh` a `bench models new` helyett, frissítés a `--where` futások előtt, ha a LM Studio elérhető (különben a tárolt pillanatkép és figyelmeztetés); a `refresh` külön író művelet marad az API-hoz | ✅ kész (2026-11-27: `first_seen` modellenként, `bench models list --new` és `--refresh`, frissítés a `--where` futások előtt) |

### Stabilitás és tesztelés

| Pont | Jelenlegi ismeret | Állapot |
|---|---|---|
| Élőben nem próbált (sweep) | `stop --now`; automatikus szünet foglalt GPU-nál és az utána következő automatikus folytatás (csak offline tesztek); generálás közben megszakadt kapcsolat (csak offline tesztek); Ctrl+C; betöltési timeout; `--redo-failed`; a GPU-támogatás nélküli runtime figyelmeztetése. A gépújraindítás utáni folytatást 2026-11-26-án egyszer használtuk; `configs/machine.local.json` más mappában lévő LM Studióval (csak offline tesztek). A D2a lépés (csak offline tesztek): beragadt zár egy leállított (kill) futás után | ⚪ nyitott |
| Élőben nem próbált (agent harness) | Valódi futás leállítása: Ctrl+C (a vezérlőfájlon át történő leállítást, a `bench stop`-ot 2026-11-27-én élőben kipróbáltuk), a harnesst leállító második Ctrl+C és az utána maradó trace; `--run-timeout`; próbálkozási időkorlát valódi modellel; az SDK által értelmezhetetlennek jelzett tool-hívás (`onToolCallRequestFailure`, még nem láttuk); egy megszakadt futás után bent maradt `bench-agent` eltávolítása; 8192-től eltérő context; valódi modell próbálkozása a sandboxon kívüli olvasással. Az utolsó három kivételével offline tesztek lefedik. Az 5a lépésben új, csak offline: hívásszám szerinti mock-válasz (`sequence`); a próbálkozások felépítése a trace-ekből leállított harness után; a `stopAtLimit` által megállított valódi kontextus-túlcsordulás. Élőben kipróbálva 2026-11-27-én: a mintavételi profil és a `stopAtLimit` érvényesül (a LM Studio visszaadja őket, a trace rögzíti), és a kategorizáló valódi futásokon; élőben kipróbálva 2026-11-27-én: `--models` négy modellel, az M1 feladatkészlet, a `report` és a `show` valódi futáson; `--repeats` 5 és 10 a profilok temperature-értékeivel, és a körkorlát a tool nélküli záró körrel | ⚪ nyitott |
| Késő heartbeat | A 2026-11-26-i sweepek közben a `status --watch` többször „process gone” üzenetet adott, pedig a futás ment tovább. A nézet egy élő process késő heartbeatjénél már nem lép ki; hogy a heartbeat miért késett, ismeretlen (nem reprodukáltuk) | 🟡 részben |
| Kijelző lefagyása | Ugyanezen sweepek alatt egyszer a kijelző nem reagált tovább (a Windows szerint az `explorer.exe` a `dwm.exe`-re várt), miközben a futtató még írta a heartbeatjét; a gépet újra kellett indítani, és a `resume` folytatta a futást. Videódriver-reset vagy hardverhiba nem került a naplóba; az ok ismeretlen | ⚪ nyitott |
| Tesztek a harness függőségei nélkül | Friss klónban, a harness csomagjai nélkül a harnesst indító három Python-teszt broken pipe hibával bukott. Javítva 2026-11-27-én: üzenettel kimaradnak, a `bench agent run` a telepítő paranccsal áll le, és a README-ben van telepítési szakasz friss klónhoz (friss klónban ellenőrizve, a csomagokkal és nélkülük) | ✅ kész |
| Ismétlődő LM Studio belső útvonal | A LM Studio belső fájljainak útvonalát (`~\.lmstudio\...`, `lms.exe`) hat TypeScript-fájl külön állítja elő; a Python-kód a C3 lépés óta egy modulból olvassa (CR-15); egy közös beállítás megkönnyítené más telepítések kezelését. A publikálás után | ⚪ nyitott |

### Függőségek

Függőségi figyelmeztetés a `harness/` mappában: az `npm audit` a
[GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) jelzést adja (memóriakimerítés a 4.6.6 alatti
`zod`-ban), amelyet az `@lmstudio/sdk` 2.1.0 hoz be, mert `zod ^3.22.4`-et vár. Helyi használatban alacsony
kockázatúnak értékeltük (csak a rendelkezésre állást érinti; a bemenet a helyi szervertől és a modellkimenetből jön,
ezért a tool-paraméterek méretét korlátozni kell). Ne futtasd az `npm audit fix --force` parancsot (visszaléptetné az
SDK-t), és ne kényszeríts zod 4-et (a jelzések szerint eltöri az SDK-t). Upstream már jelezték
([lmstudio-js 362. issue](https://github.com/lmstudio-ai/lmstudio-js/issues/362)); minden SDK-frissítéskor újra
ellenőrizni.
