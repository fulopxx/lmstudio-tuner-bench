# Feladatlista és döntések

[English](roadmap.md)

Utolsó frissítés: 2026-11-26. Cél: a letöltött helyi modellek optimalizálása és összehasonlítása a saját hardveren,
a saját felhasználási esetekre, LM Studióval.

## 1. Feladatok

Állapot: **kész** (futtatással igazolt), **részben**, **folyamatban**, **nyitott**.

| # | Feladat | Állapot |
|---|---|---|
| 1 | Sebesség- és memóriaoptimalizálás (kontextus, GPU-offload, flash attention, batch, KV-kvantálás, szálak) | részben (a 2026-11-26-i tiszta sweepek kiértékelve, az ajánlott beállítások rögzítve; nyitott: a VRAM határán lévő esetek, kitöltött context, a KV-kvantálás minőségi hatása, presetek; lásd 9. pont) |
| 2 | Smoke teszt | kész |
| 3 | Élő státusz, szünet, leállítás, folytatás megadott lépéstől | részben (lásd 6. pont) |
| 4 | Kijelölhető modellek, új letöltések kezelése (modellregiszter, automatikus felvétel) | részben (kézi lista a rácsfájlban) |
| 5 | Tesztcsomag-szűrés modellképesség szerint (pl. képleírás csak vision modellen) | nyitott |
| 6 | Minőségcsomagok: kódolás; git-kezelés; magyar nyelv; képfelismerés, képleírás; alkalmazás-screenshot alapú döntés és magyarázat; játék- és 3D-tervezés (Unreal, Blender); kiberbiztonság | nyitott |
| 7 | MCP / tool-használat: formátum, tool-választás, paraméterek, eredmény feldolgozása, többlépéses lánc, párhuzamos hívás; utasításkövetés három részletességi szinten (cél, számozott lépések, egy lépés egyszerre) | részben (egyetlen tool-próba a smoke-ban) |
| 8 | Tool-timeout viselkedés mint **modellképesség**: nem próbálkozik végtelenül, idő után leáll és jelez a felhasználónak | nyitott (eddig csak a mérőrendszer saját timeoutjai vannak kész) |
| 9 | Skill-használat: megfelelő skill kiválasztása, lépések és tiltások betartása | nyitott |
| 10 | Szűk körű frontier pontozás a döntő körben | nyitott (döntés függőben) |
| 11 | Webes felület és dashboard; egyszerű Excel-értékelő táblázat Excel-grafikonokkal | nyitott |
| 12 | Böngésző GPU-használatának jelzése és mérése | nyitott |
| 13 | Gitre megosztható projekt | részben (még nincs kiadva) |
| 14 | Másodlagos NiceGUI irányítófelület | nyitott, alacsony prioritás |
| 15 | Kétnyelvű (angol elsődleges, magyar) dokumentáció és felület nyelvváltással | részben (dokumentumok kész, felület nincs) |
| 16 | Agent harness: kis tool loop (fájl, keresés, git, shell) sandboxban, megszakítással, helyreállítással és kontextuskezeléssel (lásd 7. pont) | nyitott |
| 17 | Hibaelemzés: teljes trace futásonként, FMEA-jellegű hibataxonómia, trace-alapú diagnosztika, riport modellenként (lásd 7. pont) | nyitott |
| 18 | A hivatalos LM Studio SDK kipróbálása a telepített verzión; ha működik, kiváltja a config fájlok módosítását | kész |
| 19 | Modellenkénti tool-call eltérések és javítási módszerek (retry, séma-kényszerítés, grammar) | nyitott |
| 20 | Rögzített, reprodukálható eval-feladatkészlet pass/fail ellenőrzéssel és ismételt futásokkal | nyitott |
| 21 | Megszakítás- és helyreállítás-tesztek: leállítás tool-hívás közben, félbehagyott kimenet, folytatás | nyitott |
| 22 | Kontextuskezelés mérése: vágás, összegzés, tool-eredmény méretkorlát, viselkedés növekvő kontextusnál | nyitott |
| 23 | Vizsgálat: biased-e egy modell? Tényezők, tesztpromptok, mérés modellenként (lásd 8. pont) | nyitott (még nem vizsgált) |
| K | **Külön feladat:** agent skillek (pl. session-export) átvitele úgy, hogy LM Studióban kompatibilisen működjenek | nyitott (még nem vizsgált) |

### Tervezett fejlesztések

- Eredményformátum: sémaverzió és hardver-ujjlenyomat (GPU, driver, LM Studio és runtime verzió).
- Modellenként ajánlott preset, összevetve a jelenlegi LM Studio-beállításokkal. Alkalmazás csak megerősítés után.
- Később: speculative decoding és mintavételi paraméterek hangolása.

## 2. Sorrend

### M1 mérföldkő: első publikus kiadás

Az M1 az első: egy vékony, végigmenő szelet, amely működik. Az alábbi A–L táblázat az utána következő munkára vonatkozik.

| M1 lépés | Tartalom | Állapot |
|---|---|---|
| 1 | SDK-próba a telepített LM Studión (18. feladat) | kész |
| 2 | Tiszta sweep, kiértékelés, ajánlott beállítás modellenként | kész |
| 3 | Repó előkészítése, licenc, publikus kiadás | folyamatban |
| 4 | Minimális TypeScript harness: 1–2 tool (fájlolvasás és mock, shell nélkül), timeout, megszakítás, trace | nyitott |
| 5 | 10–20 rögzített feladat, ismételt futások, hibakategória-riport | nyitott |
| 6 | Eredménytábla a README-ben | nyitott |

M1 után: webes dashboard, minőségcsomagok, kontextuskezelés mérése, NiceGUI.

### Teljes sorrend

| Lépés | Tartalom | Állapot |
|---|---|---|
| A | Próbasweep kiértékelése, döntő kör | kész (a próbasweep és a tiszta sweepek kiértékelve) |
| B | Repó előkészítése, dokumentumok angol és magyar változata | részben (kétnyelvű dokumentumok készek; a publikus kiadás hátravan) |
| C | Core és CLI szétválasztása, eredményformátum verzióval, modellregiszter | nyitott |
| D | `docs/architecture.md` véglegesítése: adatformátumok, vezérlési interfész | részben (vázlat kész) |
| E | HTML dashboard és Excel-export (D után) | nyitott |
| F | Webes vezérlőfelület | nyitott |
| G | Agent harness: tool loop, sandbox, trace log, CLI | nyitott |
| H | Tool-calling, timeout- és utasításkövetés-csomag a harnessen futtatva | nyitott |
| I | Hibaelemzés: kategóriák és modellenkénti riport | nyitott |
| J | Minőségcsomagok | nyitott |
| L | NiceGUI másodlagos felület (alacsony prioritás) | nyitott (alacsony prioritás) |
| K | Skill-átvitel (külön feladat) | nyitott (külön feladat) |

Az E–F és a G–J párhuzamosan haladhat. A webes felület **tervezése** (nézetek, drótváz) kód nélkül korábban is
elkezdhető.

## 3. Döntések

| Téma | Döntés |
|---|---|
| Per-modell LM Studio config-fájlok | Nem módosulnak; a futtató az SDK-val tölt be |
| Hibakezelés | Hibás lépést nem próbál újra magától; két egymást követő timeout után megszakítás; foglalt GPU esetén szünet, 90 s-onként újraellenőrzés és automatikus folytatás (a kézi szünet megmarad) |
| Frontend | React + Vite + TypeScript, Mantine, Apache ECharts |
| Backend | FastAPI, csak `127.0.0.1` |
| Statisztika | Medián és szórás, Pareto-front, állítható súlyozott pontszám, bootstrap bizalmi intervallum; páros bírálatnál Elo / Bradley–Terry. ML/DL nem szükséges |
| Nyelv | Az angol az elsődleges, mindenből készül magyar változat is (dokumentumok, README, felület). A GitHub angol README-je linkel a magyarra |
| Fájlnév-konvenció | `név.md` angol, `név.hu.md` magyar; a PDF-ek ugyanígy |
| Magyar szóhasználat | Az angolul elterjedt vagy jó magyar megfelelő nélküli szakkifejezés angolul marad, főleg a felületen |
| Kód | Angol kód, angol kommentek |
| Agent harness | Saját modul hibaelemzéssel, kezdettől TypeScriptben. Az első változatban nincs shell tool |
| LM Studio elérés | Load a hivatalos TypeScript SDK-val (igazolt); CPU-szálak a llama.cpp argumentum-felülírással; a sweep futtató ezt használja |
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

- A 2026-11-26-i 56 feladatos futás próbafutás volt terhelt gépen; a 9. pont sweepjei felülírják.
- Élőben nem próbált: `stop --now`, automatikus szünet foglalt GPU-nál és az utána következő automatikus folytatás
  (csak offline tesztek fedik le), generálás közben megszakadt kapcsolat (csak offline tesztek), Ctrl+C, betöltési
  timeout, `--redo-failed`. A gépújraindítás utáni folytatást 2026-11-26-án egyszer használtuk.
- A megosztott GPU-memóriába csordulás felismerése: a `near_vram_limit` jelző nem elég (a tiszta sweepben egy lassú
  konfiguráció a küszöbe alatt maradt). A kiértékelés `spill?` jelzője a sebességből következtet; a megosztott
  GPU-memóriát nem mérjük.
- A CLI `lms load` út és a default-config értékek viszonya nem mért.
- A sebességmérés csak szabad GPU-n érvényes.
- A 2026-11-26-i sweepek közben a `status --watch` többször „process gone” üzenetet adott, pedig a futás ment tovább. A
  nézet egy élő process késő heartbeatjénél már nem lép ki; hogy a heartbeat miért késett, ismeretlen (nem
  reprodukáltuk).
- Ugyanezen sweepek alatt egyszer a kijelző nem reagált tovább (a Windows szerint az `explorer.exe` a `dwm.exe`-re
  várt), miközben a futtató még írta a heartbeatjét; a gépet újra kellett indítani, és a `resume` folytatta a futást.
  Videódriver-reset vagy hardverhiba nem került a naplóba; az ok ismeretlen.
- A sweepekből még hiányzik: a contextet ténylegesen kitöltő promptok; mód arra, hogy a VRAM határán lévő
  konfigurációk összehasonlításakor a háttér VRAM-foglalása rögzített vagy kontrollált legyen.

- Függőségi figyelmeztetés a `harness/` mappában: az `npm audit` a
  [GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) jelzést adja (memóriakimerítés a 4.6.6 alatti
  `zod`-ban), amelyet az `@lmstudio/sdk` 2.1.0 hoz be, mert `zod ^3.22.4`-et vár. Helyi használatban alacsony
  kockázatúnak értékeltük (csak a rendelkezésre állást érinti; a bemenet a helyi szervertől és a modellkimenetből jön,
  ezért a tool-paraméterek méretét korlátozni kell). Ne futtasd az `npm audit fix --force` parancsot (visszaléptetné az
  SDK-t), és ne kényszeríts zod 4-et (a jelzések szerint eltöri az SDK-t). Upstream már jelezték
  ([lmstudio-js 362. issue](https://github.com/lmstudio-ai/lmstudio-js/issues/362)); minden SDK-frissítéskor újra
  ellenőrizni.

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
- A LM Studio API-portjának megtalálása az SDK-hoz belső fájl nélkül.

## 8. Vizsgálat: biased-e egy modell?

23. feladat. Állapot: nem vizsgált; az alábbiakból ebben a projektben semmit nem reprodukáltunk.

**Kérdés.** Másként viselkedik-e egy modell, ha csak egy olyan részlet változik, amelynek nem kellene számítania?
Milyen tényezők váltják ezt ki, és hogyan tér el modellek, modellcsaládok, illetve eredeti és módosított
("uncensored") változatok között?

**Szakaszok**

1. Kutatás: milyen tényezők mentén lehetnek bias-esek a modellek (például megrendelő, cél, nemzetiség, politikai téma),
   milyen kimenetben jelenik meg (elutasítás, tartalom és hangnem, minőség, a generált kód biztonsága), és milyen
   mérési módszerek publikáltak.
2. Tesztpromptok tényezőnként: csak az adott tényezőben eltérő készletek, semleges kontrollokkal és kimenettípusonként
   metrikával; az első futás előtt átnézve.
3. Mérés modellenként.
4. Riport modellenként.

**Általános követelmények**

- A tényezők, promptok és metrikák az első futás előtt rögzítve; legalább két semleges megfogalmazás, hogy a
  megfogalmazás saját zaja becsülhető legyen.
- Lehetőleg objektív metrikák. Ahol a kimenetet pontozni kell, írott pontozási szempontrendszer és a pontozó saját
  bias-ának ellenőrzése (a pontozó modell is lehet bias-es).
- Statisztika bizalmi intervallummal és többszörös összehasonlítás korrekciójával.

A csak szöveges tesztek a rögzített feladatkészlettől (20. feladat) függnek; a generált kódot futtató tesztekhez a
harness és a hibaelemzés (16. és 17. feladat) is kell. Ütemezés: M1 után.

### Első ismert eset: a megrendelőtől függő kódbiztonság

Azonos kódolási feladatnál változik-e a támadható kód aránya, ha csak a megadott megrendelő vagy cél tér el? A
kiberbiztonsági minőségcsomaghoz (6. feladat) illeszkedik.

**Publikált állítások**

- [Hirundo, 2026-10-21](https://www.hirundo.io/blog/qwen3-coder-vulnerabilities), Qwen3-Coder-30B-A3B-Instruct, a
  system promptban egyetlen kifejezés változik, egy feladat (BaxBench SecretStorage), temperature 0,6, jellemzően
  190 generált alkalmazás personánként, detektálás exploitok futtatásával. Az amerikai védelmi beszállítónak írt
  alkalmazások 70%-a volt támadható, a kínainak írtak 59%-a (p = 0,03). Hongkongi demokráciapárti szervezet esetén
  28%-kal (relatív) gyakoribb volt a más felhasználók titkait kiszivárogtató alkalmazás, mint semleges promptnál
  (p = 0,024).
- [CrowdStrike, 2025-11-20](https://www.crowdstrike.com/en-us/blog/crowdstrike-researchers-identify-hidden-vulnerabilities-ai-coded-software/),
  DeepSeek-R1: politikailag érzékeny kifejezést tartalmazó promptnál több súlyos sérülékenység (itt csak keresési
  összefoglalóból ismert).

**A Hirundo-tanulmány korlátai.** Gyártói tanulmány (a cég árulja az ellenszert), nem lektorált. A bemutatott feladat
tizenegy átnézett közül emelkedett ki. Kb. tíz összehasonlításnál a 0,03 körüli p értékek nem élnék túl a többszörös
tesztelés korrekcióját. A blogbejegyzés nem linkeli a vizsgálat promptjait, kódját és nyers adatait. A szerzők nem
állítják, hogy tudnák, szándékos-e a hatás.

**Egy saját mérés további követelményei**

- Több kódolási feladat, az első futás előtt kiválasztva.
- Detektálás exploit tesztek futtatásával; a statikus elemzés egyedül nem elég (a tanulmány szerint 1840
  alkalmazásból a statikus elemzés 2-t jelzett, a támadások 1144-et törtek fel).
- Mintaszám: egy 59% / 70% különbség 80%-os erővel való kimutatásához feltételenként kb. 300 minta kell (saját
  becslés, egy összehasonlítás, 5% szignifikancia).
- A generált kód csak elszigetelt sandboxban futhat; ez a 7. pont sandbox-döntésétől függ.
- A Hirundo-eredmények egy 30B modellre vonatkoznak; a fejlesztői gép 8 GB-os GPU-jára férő kisebb modellekről nem
  mondanak semmit.

## 9. Mérési megállapítások (tiszta sweepek, 2026-11-26)

Egy gép (RTX 2070, 8 GB), 132 job 7B–14B modelleken, mind sikeres, jobonként 3 ismétlés, kb. 1800 és 6000 tokenes
promptok. Egyik prompt sem töltötte ki a 16k contextet, és a kimenet minőségét nem mértük.

- Ahol a teljes GPU-offload a megosztott memóriába csordulás nélkül befért, minden részleges offload lassabb volt (csak
  12–14B modelleken mértük). Ahol a VRAM túlcsordult, a részleges offload gyakran gyorsabb volt.
- Ahol a modell befér, az `f16` KV decode-ban ugyanolyan gyors vagy legfeljebb kb. 9%-kal gyorsabb volt, mint a `q8_0`.
- Az 512-es és a 2048-as eval batch befér modellnél alig különbözött; a VRAM határán néha megduplázta a
  decode-sebességet.
- A VRAM határán a sebesség a más programok VRAM-foglalásától függ: ugyanaz a konfiguráció az egyik futásban 34, a
  másikban 6 t/s decode-ot adott (a prompt hossza is eltért).
- A hosszabb prompttal a decode a befér modelleknél is 4–22%-kal lassabb volt; az ok (valószínűleg a prompt hossza) nem
  igazolt.
