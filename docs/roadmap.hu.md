# Feladatlista és döntések

[English](roadmap.md)

Utolsó frissítés: 2026-11-26. Cél: a letöltött helyi modellek optimalizálása és összehasonlítása a saját hardveren,
a saját felhasználási esetekre, LM Studióval.

Kapcsolódó dokumentumok: [követelmények](requirements.hu.md) (felület, tesztelés, agent harness, speculative decoding,
bias-vizsgálat) és [mérési megállapítások](findings.hu.md).

## 1. Feladatok

Állapot: ✅ **kész** (futtatással igazolt), 🟡 **részben**, 🔵 **folyamatban**, ⚪ **nyitott**.

| # | Feladat | Állapot |
|---|---|---|
| 1 | Sebesség- és memóriaoptimalizálás (kontextus, GPU-offload, flash attention, batch, KV-kvantálás, szálak) | 🟡 részben (a 2026-11-26-i tiszta sweepek kiértékelve, az ajánlott beállítások rögzítve; nyitott: a VRAM határán lévő esetek, kitöltött context, a KV-kvantálás minőségi hatása, presetek; lásd [megállapítások](findings.hu.md)) |
| 2 | Smoke teszt | ✅ kész |
| 3 | Élő státusz, szünet, leállítás, folytatás megadott lépéstől | 🟡 részben (lásd 4. pont) |
| 4 | Kijelölhető modellek, új letöltések kezelése (modellregiszter, automatikus felvétel) | 🟡 részben (kézi lista a rácsfájlban) |
| 5 | Tesztcsomag-szűrés modellképesség szerint (pl. képleírás csak vision modellen) | ⚪ nyitott |
| 6 | Minőségcsomagok: kódolás; git-kezelés; magyar nyelv; képfelismerés, képleírás; alkalmazás-screenshot alapú döntés és magyarázat; játék- és 3D-tervezés (Unreal, Blender); kiberbiztonság | ⚪ nyitott |
| 7 | MCP / tool-használat: formátum, tool-választás, paraméterek, eredmény feldolgozása, többlépéses lánc, párhuzamos hívás; utasításkövetés három részletességi szinten (cél, számozott lépések, egy lépés egyszerre) | 🟡 részben (egyetlen tool-próba a smoke-ban) |
| 8 | Tool-timeout viselkedés mint **modellképesség**: nem próbálkozik végtelenül, idő után leáll és jelez a felhasználónak | ⚪ nyitott (eddig csak a mérőrendszer saját timeoutjai vannak kész) |
| 9 | Skill-használat: megfelelő skill kiválasztása, lépések és tiltások betartása | ⚪ nyitott |
| 10 | Szűk körű frontier pontozás a döntő körben | ⚪ nyitott (döntés függőben) |
| 11 | Webes felület és dashboard; egyszerű Excel-értékelő táblázat Excel-grafikonokkal | ⚪ nyitott |
| 12 | Böngésző GPU-használatának jelzése és mérése | ⚪ nyitott |
| 13 | Gitre megosztható projekt | 🟡 részben (még nincs kiadva) |
| 14 | Másodlagos NiceGUI irányítófelület | ⚪ nyitott, alacsony prioritás |
| 15 | Kétnyelvű (angol elsődleges, magyar) dokumentáció és felület nyelvváltással | 🟡 részben (dokumentumok kész, felület nincs) |
| 16 | Agent harness: kis tool loop (fájl, keresés, git, shell) sandboxban, megszakítással, helyreállítással és kontextuskezeléssel (lásd [követelmények](requirements.hu.md), 3. pont) | 🟡 részben (M1 harness: fájlolvasás és mock toolok, korlátok, leállítás, trace; keresés, git, shell, helyreállítás és kontextuskezelés nyitott) |
| 17 | Hibaelemzés: teljes trace futásonként, FMEA-jellegű hibataxonómia, trace-alapú diagnosztika, riport modellenként (lásd [követelmények](requirements.hu.md), 3. pont) | 🟡 részben (1. verziós taxonómia és szabályalapú kategorizáló bizonyítékkal; a modellenkénti riport nyitott) |
| 18 | A hivatalos LM Studio SDK kipróbálása a telepített verzión; ha működik, kiváltja a config fájlok módosítását | ✅ kész |
| 19 | Modellenkénti tool-call eltérések és javítási módszerek (retry, séma-kényszerítés, grammar) | ⚪ nyitott |
| 20 | Rögzített, reprodukálható eval-feladatkészlet pass/fail ellenőrzéssel és ismételt futásokkal | ⚪ nyitott |
| 21 | Megszakítás- és helyreállítás-tesztek: leállítás tool-hívás közben, félbehagyott kimenet, folytatás | ⚪ nyitott |
| 22 | Kontextuskezelés mérése: vágás, összegzés, tool-eredmény méretkorlát, viselkedés növekvő kontextusnál | ⚪ nyitott |
| 23 | Vizsgálat: biased-e egy modell? Tényezők, tesztpromptok, mérés modellenként (lásd [követelmények](requirements.hu.md), 4. pont) | ⚪ nyitott (még nem vizsgált) |
| 24 | Speculative decoding mint optimalizálási dimenzió: draft modell és MTP a kikapcsolt spekulációval összevetve, feladattípusonként (lásd [követelmények](requirements.hu.md), 5. pont) | 🔵 folyamatban (a 0. fázis kész; az 1. fázis nyitott) |
| 25 | Követelmény-traceability: a tesztek megnevezik az általuk lefedett követelmény-azonosítókat; egy script elkészíti a mátrixot (követelmény → tesztek → offline, élő, nem lefedett), és hibát jelez ismeretlen vagy a két nyelvben eltérő azonosítónál | ⚪ nyitott |
| 26 | Követelményminőség: a meglévő követelmények átnézése a [követelmények](requirements.hu.md) írási szabályai szerint, az ellenőrzés oszlop felvétele | ⚪ nyitott |
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
| 3 | Repó előkészítése, licenc, publikus kiadás | 🔵 folyamatban |
| 4 | Minimális TypeScript harness: 1–2 tool (fájlolvasás és mock, shell nélkül), timeout, megszakítás, trace | ✅ kész (2026-11-26: `bench agent run`, élőben 4/4 példafeladat egy modellen; a Ctrl+C leállítás csak offline tesztelve) |
| 5 | 10–20 rögzített feladat, ismételt futások, hibakategória-riport | 🔵 folyamatban (a feladatkészlet, a riport és az első élő futás 2026-11-27-én kész, 4 modell × 20 feladat × 5; a kézi átnézés után 2. verziós taxonómia; nyitott: a publikált táblához a tíz ismétléses futás, és a kézi átnézés maradéka) |
| 6 | Eredménytábla a README-ben | ⚪ nyitott |

M1 után: webes dashboard, minőségcsomagok, kontextuskezelés mérése, NiceGUI.

### Teljes sorrend

| Lépés | Tartalom | Állapot |
|---|---|---|
| A | Próbasweep kiértékelése, döntő kör | ✅ kész (a próbasweep és a tiszta sweepek kiértékelve) |
| B | Repó előkészítése, dokumentumok angol és magyar változata | 🟡 részben (kétnyelvű dokumentumok készek; a publikus kiadás hátravan) |
| C | Core és CLI szétválasztása, eredményformátum verzióval, modellregiszter | ⚪ nyitott |
| D | `docs/architecture.md` véglegesítése: adatformátumok, vezérlési interfész | 🟡 részben (vázlat kész) |
| E | HTML dashboard és Excel-export (D után) | ⚪ nyitott |
| F | Webes vezérlőfelület | ⚪ nyitott |
| G | Agent harness: tool loop, sandbox, trace log, CLI | ⚪ nyitott |
| H | Tool-calling, timeout- és utasításkövetés-csomag a harnessen futtatva | ⚪ nyitott |
| I | Hibaelemzés: kategóriák és modellenkénti riport | ⚪ nyitott |
| J | Minőségcsomagok | ⚪ nyitott |
| L | NiceGUI másodlagos felület (alacsony prioritás) | ⚪ nyitott (alacsony prioritás) |
| K | Skill-átvitel (külön feladat) | ⚪ nyitott (külön feladat) |

Az E–F és a G–J párhuzamosan haladhat. A webes felület **tervezése** (nézetek, drótváz) kód nélkül korábban is
elkezdhető.

24. feladat (speculative decoding): a rövid próba (0. fázis) az M1 4. lépése előtt, a beépítés az M1 után, a C
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

### Stabilitás és tesztelés

| Pont | Jelenlegi ismeret | Állapot |
|---|---|---|
| Élőben nem próbált (sweep) | `stop --now`; automatikus szünet foglalt GPU-nál és az utána következő automatikus folytatás (csak offline tesztek); generálás közben megszakadt kapcsolat (csak offline tesztek); Ctrl+C; betöltési timeout; `--redo-failed`; a GPU-támogatás nélküli runtime figyelmeztetése. A gépújraindítás utáni folytatást 2026-11-26-án egyszer használtuk | ⚪ nyitott |
| Élőben nem próbált (agent harness) | Valódi futás leállítása: Ctrl+C vagy a stop parancs, a harnesst leállító második Ctrl+C és az utána maradó trace; `--run-timeout`; körkorlát és próbálkozási időkorlát valódi modellel; az SDK által értelmezhetetlennek jelzett tool-hívás (`onToolCallRequestFailure`, még nem láttuk); egy megszakadt futás után bent maradt `bench-agent` eltávolítása; 1-nél több `--repeats`, 0-nál nagyobb temperature, 8192-től eltérő context; valódi modell próbálkozása a sandboxon kívüli olvasással. Az utolsó három kivételével offline tesztek lefedik. Az 5a lépésben új, csak offline: hívásszám szerinti mock-válasz (`sequence`); a próbálkozások felépítése a trace-ekből leállított harness után; a `stopAtLimit` által megállított valódi kontextus-túlcsordulás. Élőben kipróbálva 2026-11-27-én: a mintavételi profil és a `stopAtLimit` érvényesül (a LM Studio visszaadja őket, a trace rögzíti), és a kategorizáló valódi futásokon; élőben kipróbálva 2026-11-27-én: `--models` négy modellel, az M1 feladatkészlet, a `report` és a `show` valódi futáson | ⚪ nyitott |
| Késő heartbeat | A 2026-11-26-i sweepek közben a `status --watch` többször „process gone” üzenetet adott, pedig a futás ment tovább. A nézet egy élő process késő heartbeatjénél már nem lép ki; hogy a heartbeat miért késett, ismeretlen (nem reprodukáltuk) | 🟡 részben |
| Kijelző lefagyása | Ugyanezen sweepek alatt egyszer a kijelző nem reagált tovább (a Windows szerint az `explorer.exe` a `dwm.exe`-re várt), miközben a futtató még írta a heartbeatjét; a gépet újra kellett indítani, és a `resume` folytatta a futást. Videódriver-reset vagy hardverhiba nem került a naplóba; az ok ismeretlen | ⚪ nyitott |

### Függőségek

Függőségi figyelmeztetés a `harness/` mappában: az `npm audit` a
[GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) jelzést adja (memóriakimerítés a 4.6.6 alatti
`zod`-ban), amelyet az `@lmstudio/sdk` 2.1.0 hoz be, mert `zod ^3.22.4`-et vár. Helyi használatban alacsony
kockázatúnak értékeltük (csak a rendelkezésre állást érinti; a bemenet a helyi szervertől és a modellkimenetből jön,
ezért a tool-paraméterek méretét korlátozni kell). Ne futtasd az `npm audit fix --force` parancsot (visszaléptetné az
SDK-t), és ne kényszeríts zod 4-et (a jelzések szerint eltöri az SDK-t). Upstream már jelezték
([lmstudio-js 362. issue](https://github.com/lmstudio-ai/lmstudio-js/issues/362)); minden SDK-frissítéskor újra
ellenőrizni.
