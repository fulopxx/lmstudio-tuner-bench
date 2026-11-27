# Követelmények és tervezett munka

[English](requirements.md)

Mit kell tudniuk a tervezett részeknek. A feladatszámok a [roadmapre](roadmap.hu.md) vonatkoznak, az állapotok is ott
vannak.

## Hogyan írjuk a követelményeket

2026-11-27-től érvényes az új követelményekre; a meglévőket a 26. feladat nézi át ezek szerint. Az IREB CPRE
Foundation Level, az ISO/IEC/IEEE 29148 és az ISO 26262-8 6. pontjának minőségi szempontjai alapján.

**Minden követelmény**

| Szempont | Jelentés | Ellenőrzés |
|---|---|---|
| Szükséges | Nélküle egy igény vagy egy ismert hiba fedetlen maradna | Az indok oszlop megnevezi az igényt, a döntést vagy a megfigyelést |
| Egyértelmű | Csak egyféleképpen olvasható; nincs benne „gyors”, „robusztus”, „felhasználóbarát”, „stb.”, „lehetőség szerint” | Számok mértékegységgel, megnevezett mezők, felsorolások |
| Egyszeres (atomi) | Egy állítás; nincs két kötelezettséget összekötő „és” | Két azonosítóra bontjuk, ha két teszt kellene hozzá |
| Ellenőrizhető | Teszt, átnézési lépés vagy mérés megmutatja, hogy teljesül | Az ellenőrzés oszlop ki van töltve (lásd lent) |
| Megvalósítható | Az ismert környezettel és függőségekkel elérhető | Az ismeretlenek nyitott pontként szerepelnek, nem követelményként |
| Ellentmondásmentes | Nem mond ellent más követelménynek vagy döntésnek | Ütközésnél előbb döntünk, csak utána marad meg mindkettő |
| Teljes | Megadja a feltételt, a szereplőt vagy komponenst és az elvárt eredményt | Forma: „Ha <feltétel>, a <komponens> <tesz> <eredmény>”, ahol van feltétel |
| Megoldásrészletektől mentes | Mit és miért; a hogyant csak ott, ahol maga a hogyan a döntés | A megvalósítási részletek az architektúra-dokumentumba kerülnek |

**A követelmények összessége** komponensenként rendezett, ismétlés nélküli, stabil azonosítójú (egy azonosítót soha
nem használunk újra; az elvetett követelmény „visszavonva” megjegyzéssel megtartja az azonosítóját), kétnyelvű, mindkét
nyelven azonos azonosítókkal, és tesztekre visszakövethető (25. feladat).

**Forma.** Területenként egy táblázat az azonosító, követelmény, indok, és a 26. feladattól kezdve az ellenőrzés
(`teszt`, `élő`, `átnézés` vagy `mérés`) oszloppal. A kötelezettséget a „kell” / „must” jelöli; a „should” nem
használatos. Az állapotok a roadmapben maradnak.

## 1. Felület

- Indítás, szünet, folytatás, leállítás; élő státusz.
- Nézetek: Pareto-pontdiagram (VRAM–sebesség, méret = kontextus), modell × tesztcsomag hőtérkép, radar 2–4 modellre,
  szűrhető táblázat Excel-exporttal.
- Agent-nézetek (az adat a core-ból, lásd FA-43 és FA-47): hibakategória-hőtérkép (modell × kategória), a bukások
  összetétele (halmozott oszlop, treemap vagy sunburst szint, kategória és alkód szerint), a csendes bukások aránya
  modellenként, elsődleges → másodlagos kategóriák (Sankey); próbálkozásonként a körök és tool-hívások idővonala és
  egy lépésnézet a bizonyíték-esemény kiemelésével.
- Méréskor figyelmeztetés: a böngésző VRAM-ot és GPU-t használ.
- Böngésző-többlet mérése rögzített konfiguráción: dashboard zárva / nyitva gyorsítással / nyitva gyorsítás nélkül.
  Legyen benne offloadolt konfiguráció is (gyorsítás nélkül a CPU terhelése nő). A folyamatonkénti VRAM kiolvasásának
  módja ellenőrizendő (`nvidia-smi` ezen a gépen `N/A`-t ad).
- Az eredménysor rögzítse, hogy mérés közben nyitva volt-e a dashboard.
- A lefordított frontend mellékelhető legyen, hogy a használathoz ne kelljen Node.js.
- Nyelvváltás angol és magyar között; a szövegek nyelvi fájlokban, az angol az alapértelmezett.

## 2. Tesztelés (tervezett)

- Python logika és FastAPI: `pytest` (a meglévő `unittest` tesztek futtathatók vele).
- React komponensek: Vitest + React Testing Library.
- Végpontok közötti: Playwright, hamis futtatóval és rögzített mintaeredményekkel, GPU nélkül. Mérés közben nem fut.
- GPU-s élő tesztek külön, kézzel indítva (`tests\live_control_test.py`).

## 3. Agent harness és hibaelemzés: kezdeti követelmények

Vázlat, a G lépés előtt részletezendő.

### Harness

- TypeScriptben készül; a LM Studióval a hivatalos SDK-n át beszél, ha a próba (18. feladat) sikeres.
- A modellt tool loopban futtatja. Az első változatban csak fájlolvasás és mock toolok vannak (a mock toolok
  determinisztikus teszteket adnak); a keresés, git és shell a sandbox-döntés után jön.
- Minden eldobható sandbox mappában fut; alapértelmezetten hálózat nélkül.
- Korlátok: timeout tool-hívásonként, maximális lépésszám feladatonként, nincs végtelen újrapróbálás; korlát elérésekor
  a felhasználó jelzést kap.
- Megszakítás és folytatás; tiszta helyreállítás tool-hibából és érvénytelen modellkimenetből.
- Kontextuskezelés: beszélgetési előzmény, tool-eredmények, mi történik a kontextus betelésekor.
- Mint minden funkció, először CLI-ből használható.

### Hibaelemzés

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

### Interfész a core felé (döntve és megvalósítva 2026-11-26)

| ID | Döntés | Indok |
|---|---|---|
| H1 | A core modellenként és feladatcsomagonként egy `node harness/run-tasks.ts` processt indít. A spec az első stdin-sor (JSON); az utolsó stdout-sor `RESULT:`, utána JSON összegzés | Ugyanaz a minta, mint a loadernél; a hiba egy processen belül marad; Windowson egyszerű. Elvetve: hosszú életű JSON-RPC process, HTTP |
| H2 | A harness nem tölt be modellt; a meglévő loader által betöltött modell `identifier`-ét kapja | Egy betöltési út, a meglévő ellenőrzésekkel |
| H3 | A leállítás további stdin-sorként érkezik (`{"cmd":"stop"}`), és `AbortSignal`-t vált ki; a trace `aborted` eseményt kap. Türelmi idő után a core leállítja a processt | Windowson nincs megbízható jelzés gyermekprocessnek |
| H4 | Trace: feladat-futásonként JSONL, `schema_version` mezővel; események: `task_start`, `prediction` (nyers szöveg, tokenek, idők), `tool_call` (nyers és értelmezett argumentumok, validálási hiba), `tool_result` (méret, hiba, időtartam), `limit_hit`, `error`, `task_end` | Hozzáfűzhető, sérült utolsó sor mellett is olvasható |
| H5 | A pass/fail ellenőrzés és a hibák kategorizálása a Python core-ban fut, a trace és a sandbox megtartott végállapota alapján; a harness csak végrehajt és naplóz | A logika a core-ban van, és a CLI-ből elérhető |
| H6 | Saját tool loop egy `ModelBackend` interfész mögött: `LmsSdkBackend` (egy predikciós kör `respond()` és `rawTools` használatával) és `ScriptedBackend` (determinisztikus offline tesztek GPU nélkül) | Az érvénytelen tool-hívást nyersen kell naplózni; a `.act()` értelmezhetetlen hívásnál kivételt dob. Az egykörös tool-hívás az SDK 2.1.0 típusaiban megvan; rövid élő ellenőrzés még kell |
| H7 | M1 hatókör: `read_file` (útvonal a sandboxon belül feloldva, méretkorlát) és `mock_lookup` (determinisztikus, beállítható késleltetéssel és hibával a timeout-esetekhez); korlát tool-hívásra, körszámra és teljes időre; feladatonként eldobható sandbox mappa a fixture-ök másolatával; nincs shell; CLI parancs: `bench agent run` | Vékony M1 szelet; a shell-parancsok sandbox-döntése várhat |

**A H6 élő ellenőrzése (2026-11-26, `harness/tools-probe.ts`, három modell, 4k context, temperature 0):**

- A `respond()` a `rawTools` mezővel egy körre működik: ha a modell a várt tool-hívás formátumot használja, a
  callbackek sorrendben érkeznek (start, név, argumentum-darabok, end az értelmezett kéréssel és a nyers
  argumentumokkal), a leállás oka `toolCalls`. A tool eredményét `tool` üzenetként visszaküldve helyes végső válasz jön.
- Egy 7B-s kódmodell a tool-hívást JSON-ként, kódblokkban írta ki. Az SDK nem ismerte fel: nincs tool-hívás callback, a
  leállás oka `eosFound`. A próbálkozás csak a nyers szövegben látszik; ez megerősíti, hogy a harnessnek a nyers
  kimenetet is naplóznia kell, és hogy kellenek a javítási módszerek (19. feladat). Egy 1B-s modell nem hívott toolt,
  és az adat nélkül válaszolt.
- Egyszerű összeadáshoz egyik modellnek sem kellett tool, és egyik sem hívott.
- Az `AbortSignal` általi megszakítás `userStopped` leállási okkal és a részleges szöveggel zárja a predikciót,
  kivétel nélkül.
- A `content` a gondolkodó modellek gondolatmenetét is tartalmazza; a harnessnek a `nonReasoningContent` mezőt kell
  használnia. Gondolatmenet közbeni megszakítás után egy belső LM Studio elválasztó szöveg jelent meg a `content`-ben.
- `onToolCallRequestFailure` callbacket nem láttunk.

**M1 megvalósítás (2026-11-26):** a `bench agent run` (`runner/agent.py`, `harness/run-tasks.ts`, `harness/agent/`)
megvalósítja a H1–H7 döntéseket. A megvalósítás által rögzített további részletek:

- A feladatfájlok (`tasks/*.json`, `schema_version` 1) feladatonként tartalmazzák: prompt, opcionális system prompt,
  fixture mappa, toolok, mock táblázat (azonosítónként eredmény, hiba, késleltetés), korlát-felülírások és deklaratív
  ellenőrzések: `answer_contains`, `answer_contains_any`, `tool_called`, `tool_not_called` (`*` bármely toolra),
  `mentions_failure`. Az ellenőrzések a végső választ kis- és nagybetűtől függetlenül vizsgálják; hívottnak csak az SDK
  által értelmezett tool-hívás számít.
- Alapértelmezett korlátok: 6 tool-kör, tool-hívásonként 10 s, próbálkozásonként 180 s, tool-eredményenként 8000
  karakter, körönként 2048 token. A körkorlát elérésekor a modell még egy kört kap toolok nélkül, egy megjegyzéssel,
  hogy válaszoljon a felhasználónak; a próbálkozás `limit` állapottal zárul.
- Az ismeretlen tool vagy az érvénytelen argumentum hibaeredményként megy vissza a modellnek; az SDK által nem
  értelmezett tool-hívás nyersen naplózódik, és lezárja a próbálkozást (M1-ben nincs javítás).
- Egy próbálkozás sikeres, ha `done` vagy `limit` állapottal ért véget, és minden ellenőrzése teljesül.
- A scriptelt backend offline futtatja a teljes utat (`bench agent run --scripted <fájl>`); ezt használják a Python
  tesztek.

Első élő futás a négy példafeladattal (fájlolvasás, rendelés lekérdezése, tool-hiba, tool-timeout), temperature 0
mellett: egy 8B-s gondolkodó modell 4-ből 4-et teljesített; egy 7B-s kódmodell 0-t, mert minden tool-hívást szövegként
írt ki.

A LM Studio Bionic alkalmazás headless asszisztens béta API-ját (az 1.2.1 kiadási jegyzetében szerepel) M1-ben nem
használjuk; a telepített verzió 1.2.0.

### Hibaelemzési terv az M1 5. lépéséhez (elfogadva 2026-11-26)

Az M1 5. lépése méréssé teszi a harnesst: rögzített feladatkészlet, ismételt próbálkozások és egy riport, amely
megmondja, miért bukik el egy modell. A tervet elfogadás előtt függetlenül átnézettük; az átnézés megállapításai
alább beépültek, minden követelmény mellett az indokkal, hogy a döntések később újra vizsgálhatók legyenek.

A lépés két részből áll. **5a, alapok:** élő előpróba a mintavételre, kiegészítő trace-mezők, v2 feladatformátum
deklaratív mock toolokkal, a kategorizáló és a taxonómia-dokumentum. **5b, mérés:** a 20 feladatos készlet
referenciamegoldásokkal, a riport és az élő futások. A bontás miatt a kategorizáló szintetikus és meglévő élő
trace-eken ellenőrizhető, mielőtt a feladatokba munka kerül.

**Feladatformátum (v2, saját sémaverzióval)**

| ID | Követelmény | Indok |
|---|---|---|
| FA-01 | A mock toolok a feladatfájlban vannak megadva (`toolsets`: név, leírás, paraméterséma, válaszszabályok); a feladatok névvel hivatkoznak rájuk. A `read_file` beépített tool marad | Új toolok és feladatok kódváltozás nélkül |
| FA-02 | Válaszszabályok: az első illeszkedő nyer (argumentumfeltétel: `equals`, `one_of`, `any`); egy szabály hívásszám szerint is válaszolhat (`sequence`, a „pending” és az átmeneti hiba feladathoz); alapértelmezett válasz kötelező. Sablonnyelv nincs | Determinisztikus, átnézhető tool-viselkedés |
| FA-03 | A tool-argumentumok egy sémarészhalmaz (`type`, `enum`, `required`) szerint ellenőrződnek, új függőség nélkül; a stringként küldött szám `wrong_type`, nem csendes átalakítás | A kis modellek gyakran tévesztik a típust; ez adat, nem zaj |
| FA-04 | Az `expected_calls` rendezett részsorozat argumentumillesztőkkel: a minimális hívássornak szerepelnie kell, a többlethívás megengedett, csak jelölődik. A `forbidden_tools` a próbálkozást elbuktató hívásokat sorolja fel | A pontos egyezés büntetné a hibából való visszatérést és az ártalmatlan többlethívást (a BFCL v3 ezért tért át a részsorozat-illesztésre) |
| FA-05 | A helyes válaszhoz szükséges értékek egyedi, kitalálhatatlan tokenek; láncoknál a következő argumentum az előző eredményből jön | Helyes válasz nem jöhet létre a tool-hívások nélkül; a sorrendet az adat kényszeríti ki, nem az ellenőrzés |
| FA-06 | `answer_not_contains` (tiltólista) a kulcsszavas ellenőrzések mellett | Egy „error” szó állhat kitalált eredmény mellett; a modell számára ismeretlen érték biztos jele a kitalálásnak |
| FA-07 | A `limit` állapottal záruló próbálkozás bukás, kivéve ha a feladat elfogadja | Különben a körkorlátig ismétlő, majd a harness megjegyzése után válaszoló modell sikeresnek látszik |
| FA-08 | Minden feladathoz van scriptelt referenciamegoldás, amely átmegy, és legalább egy scriptelt válasz, amely a várt kategóriával bukik | A feladatot és a kategorizálót együtt teszteli |

**Trace és futási metaadatok**

| ID | Követelmény | Indok |
|---|---|---|
| FA-10 | A `task_start` rögzíti a futás- és próbálkozásazonosítót, a modellkulcsot, a contexthosszt, a ténylegesen elküldött mintavételi beállításokat, a system promptot, a felkínált tool-sémák hash-ét, a feladatfájl hash-ét és a harness verzióját | Egy trace önmagában is újraértékelhető legyen |
| FA-11 | A `prediction` rögzíti a kezdetét és a hosszát; a `tool_call` és a `tool_result` saját hívás-sorszámot kap a modell (esetleg hiányzó) hívásazonosítója mellett; a `tool_result` `errorKind` mezőt kap (`not_found`, `outside_sandbox`, `invalid_arguments`, `unknown_tool`, `timeout`, `mock_error`, `cancelled`) | A kategorizáló ne hibaszöveget illesszen; a kör hossza ma nem olvasható ki |
| FA-12 | Külön sémaverzió a feladatfájlnak és a trace-nek | Más-más időpontban változnak |
| FA-13 | A harness a context határán megállást kér a LM Studiótól (`contextOverflowPolicy: stopAtLimit`) | A többi beállítás csendben csonkol, ami elrejtené a kontextus-túlcsordulást |
| FA-14 | Marad a lapos eseménysor, span-fa egyelőre nincs. A fenti mezők miatt a későbbi export OpenTelemetry GenAI spanekbe veszteségmentes (próbálkozás → `invoke_agent`, predikció → `chat`, tool-hívás és eredmény → `execute_tool`, `errorKind` → `error.type`) | Egy ügynök és három szint mellett a span-fa nem ad semmit; a span lezáráskor íródik, így megszakított futásnál elveszne; a konvenció még fejlesztés alatt áll |

**Mintavétel**

| ID | Követelmény | Indok |
|---|---|---|
| FA-20 | Modellcsaládonként mintavételi profil (temperature, top_p, top_k, min_p, repeat penalty, forrás-URL) egy konfigurációs fájlban, tartalék temperature 0,7; a `--temperature` felülírja; a harness minden értéket explicit küld | Ma csak a temperature megy át, a többi a LM Studio alapértéke, így az eredmény nem reprodukálható. A modellkártyák eltérnek (a Qwen3 ellenzi a greedy dekódolást) |
| FA-21 | A feladatkészlet megírása előtt élő próba: egy feladat, öt próbálkozás 0-nál nagyobb temperature-rel; eltérnek-e a kimenetek? | A seed load-paraméter; ha az ismétlések azonosak lennének, az ismétlés semmit nem mérne |

**Kategóriák és prioritás**

| ID | Követelmény | Indok |
|---|---|---|
| FA-30 | Kevés felső szintű kategória, a részletek alkódként (lista a [hibataxonómiában](failure_taxonomy.hu.md)); minden sikertelen próbálkozás pontosan egy elsődleges kategóriát kap, a további találatok mellékesek | Modellenként 100–200 próbálkozás túl vékonyan oszlana el sok kategória között |
| FA-31 | Három szint: szerkezeti (rögzített sorrend), viselkedési (az a detektor nyer, amelynek első bizonyítéka a legkorábban van a trace-ben), kimeneti (rögzített sorrend, csak ha nincs viselkedési találat) | A rögzített globális sorrend téved a következmény-láncoknál (rossz argumentum → tool-hiba → ismétlés → körkorlát); az ok az időrendből látszik |
| FA-32 | Minden találathoz bizonyíték tartozik: trace-fájl, esemény-sorszám, szabálynév | Ettől lesz a riport diagnosztika |
| FA-33 | A szöveges tool-hívás (a válaszban szövegként leírt hívás, amely egy felkínált tool nevét hívásformában tartalmazza) `format_invalid/text_tool_call`, nem „nem hívott toolt” | Élőben megfigyelve: egy ilyen válaszhoz egyáltalán nincs tool-hívás esemény |
| FA-34 | `unclassified` azokra a bukásokra, amelyeket egy szabály sem magyaráz; az aránya a taxonómia lefedettségét méri | Nélküle az utolsó kategória gyűjtővé válik |
| FA-35 | A bukások csendes (a felhasználó nem veheti észre: rossz eredmény, kitalált érték, elhallgatott korlát) és hangos osztályba is sorolódnak | A riport vezető száma; a funkcionális biztonság nem detektált hibájának felel meg |
| FA-36 | Mellékjelzők a sikeres próbálkozásokon is: `recovered_error`, `redundant_calls`, `parallel_calls`, `reasoning_leak`, `sandbox_escape_attempt` | A helyreállás a 19. feladat kiindulási adata; a gondolatmenet-szivárgás hamis sikert okozhat |
| FA-37 | A heurisztikus szabályok jelölve vannak; egy kb. 50 sikertelen próbálkozásos kézi átnézéssel mért egyezésük publikus | A kulcsszavas szabályoknak vannak hamis pozitív és negatív találatai |
| FA-38 | A kategóriák egy gépileg olvasható forrásban vannak (azonosító, szint, csendes vagy hangos, megbízhatóság); teszt ellenőrzi, hogy minden azonosító szerepel az angol és a magyar taxonómia-dokumentumban | A kód és a dokumentumok összhangban maradnak |
| FA-39 | Ha egy modell szinte minden bukása `format_invalid`, a riport kimondja, hogy a többi képessége nem volt mérhető | A nullák félrevezetők lennének |

**Futások és riport (5b)**

| ID | Követelmény | Indok |
|---|---|---|
| FA-40 | A `bench agent run --models a,b,c` egymás után futtatja a modelleket; egy modell hibája rögzül, és a következő fut | Egy összehasonlító tábla |
| FA-41 | Ha a harness eredménysor nélkül ér véget, a core a trace-ekből építi fel a próbálkozásokat | Ma egy leállított harness minden eredményt elveszít |
| FA-42 | A futás időkorlátja a feladatokból, az ismétlésekből és a próbálkozási korlátból számolódik; a feladatfájl a futás mappájába másolódik; az eredménysorok a taxonómia verzióját is tartalmazzák | Lassú modellek; későbbi újraértékelés |
| FA-43 | A `bench agent report` a trace-ekből újraszámolja a kategóriákat, és Markdownt és JSON-t ír: modellenként és feladatonként sikerarány Wilson-intervallummal, kategóriák, medián kör és idő, pass^k, a csendes bukások aránya; emellett modell × kategória mátrix és az elsődleges → másodlagos kategóriapárok darabszáma, szövegesen | Kis mintához intervallum kell; a pass^k egy számban mutatja a megbízhatóságot |
| FA-44 | Leghosszabb megbízható lánc: lánchosszonként két feladat, mindegyik tíz próbálkozással; egy hossz akkor számít, ha a 20 próbálkozásból legalább 16 sikeres, és minden rövidebb hossz is számít | Egy feladat × 5 zajos és nem monoton (a ≥4/5 egy 60%-os modellt kb. minden harmadik esetben átenged) |
| FA-45 | Alapból öt ismétlés, publikált táblázathoz tíz | Az 5/5 Wilson-intervalluma 0,57–1,00 |
| FA-46 | Az ellenintézkedések „lehetséges ellenintézkedés (nem mért)” jelöléssel jelennek meg, amíg a 19. feladat nem méri őket | Mérés nélkül nincs állítás |
| FA-47 | A `bench agent show <run> <feladat-próbálkozás>` sorszámmal kiírja egy próbálkozás lépéseit (predikciók, tool-hívások argumentumokkal, eredmények hibafajtával, korlátok), és megjelöli a kategóriája bizonyíték-eseményét | A FA-37 kézi átnézéséhez olvasható trace-nézet kell; ugyanez az adat táplálja később a grafikus lépésnézetet |

**Az 5a állapota (2026-11-26).** Megvalósítva, offline tesztekkel lefedve: FA-01–FA-07, FA-10–FA-14, FA-20,
FA-30–FA-36, FA-38, FA-41 (felépítés a trace-ekből) és a FA-42-ből a feladatfájl másolata a futás mappájába; az
alapértelmezett ismétlésszám 5 lett (FA-45). FA-21, élőben: egy feladat öt próbálkozása egy 8B-s gondolkodó modellen
temperature 0,7 mellett öt különböző gondolatmenetet és azonos végső választ adott, tehát az ismétlés mér szórást.
Élő ellenőrzés 2026-11-27-én: a LM Studio által visszaadott predikciós konfiguráció
szerint a profil minden mintavételi értéke és a `stopAtLimit` érvényesült, és a trace ezt most rögzíti is (`applied` a
`prediction` eseményben); a négy példafeladatból a 8B-s gondolkodó modell 4-et teljesített, a 7B-s kódmodell mind a
négy bukása `format_invalid/text_tool_call` besorolást kapott.
Az 5b-re nyitott: FA-08 (a feladatkészlettel), FA-37, FA-39, FA-40, a FA-42 számolt időkorlátja, FA-43, FA-44, FA-46, FA-47.

**Feladatkészlet (5b), 20 feladat:** közvetlen, egy tool (2); toolválasztás közeli csalik között, köztük egy romboló
(2); pontos argumentumok: típusok, nehéz azonosító, hiányzó kötelező paraméter, ahol a visszakérdezés a helyes (3);
2, 3 és 4 lépéses láncok (1 + 2 + 2); tool-hiba, hiányzó fájl és egy átmeneti hiba, amely egy újrapróbálást indokol
(3); timeout tiltólistával (1); nem kell tool: tudás, a válasz már a promptban, a szükséges tool nincs felkínálva (3);
„pending, check again” tool, ahol a siker az önálló megállás egy hívás-kereten belül (1).

**Nem része az M1-nek:** nyelvváltás mint kategória, kötelező párhuzamos hívás, prompt injection a tool-eredményben,
csonkolt nagy tool-eredmény (22. feladat), FMEA kockázati pontszám (helyette mért gyakoriság és a csendes / hangos
osztály), az ellenintézkedések automatikus kiválasztása, a 14B-s modell kötelező sora.

### Nyitott

- Hogyan korlátozza a sandbox a modell által generált shell-parancsokat. Ezt az első ilyen parancs futtatása előtt el
  kell dönteni.
- A LM Studio API-portjának megtalálása az SDK-hoz belső fájl nélkül.

## 4. Vizsgálat: biased-e egy modell?

23. feladat. Állapot: nem vizsgált; az alábbiakból ebben a projektben semmit nem reprodukáltunk.

**Kérdés.** Másként viselkedik-e egy modell, ha csak egy olyan részlet változik, amelynek nem kellene számítania?
Milyen tényezők váltják ezt ki, és hogyan tér el modellek, modellcsaládok, illetve eredeti és módosított
("uncensored") változatok között?

### Szakaszok

1. Kutatás: milyen tényezők mentén lehetnek bias-esek a modellek (például megrendelő, cél, nemzetiség, politikai téma),
   milyen kimenetben jelenik meg (elutasítás, tartalom és hangnem, minőség, a generált kód biztonsága), és milyen
   mérési módszerek publikáltak.
2. Tesztpromptok tényezőnként: csak az adott tényezőben eltérő készletek, semleges kontrollokkal és kimenettípusonként
   metrikával; az első futás előtt átnézve.
3. Mérés modellenként.
4. Riport modellenként.

### Általános követelmények

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
- A generált kód csak elszigetelt sandboxban futhat; ez a 3. pont sandbox-döntésétől függ.
- A Hirundo-eredmények egy 30B modellre vonatkoznak; a fejlesztői gép 8 GB-os GPU-jára férő kisebb modellekről nem
  mondanak semmit.

## 5. Speculative decoding

24. feladat. Állapot: nem próbált; mérés még nem történt.

**Cél.** A speculative decoding önálló optimalizálási dimenzió: modellenként és feladattípusonként mérjük a gyorsulást
és az erőforrásárat ugyanazon konfiguráció kikapcsolt spekulációs változatához képest, majd beállítást ajánlunk, amely
lehet a "kikapcsolva" is.

### Mit tudunk a telepített verzióról

A `@lmstudio/sdk` 2.1.0 típusdefinícióiból és korábbi megfigyelésekből; spekulatív load futtatásával semmit nem
igazoltunk.

- Load config (experimental jelöléssel): `speculativeDraftMtp` (beépített multi-token prediction fejek),
  `speculativeDraftSimple` a `speculativeDraftModel` mezővel (külön draft modell), `speculativeDraftMaxTokens`,
  `speculativeDraftMinTokens`, `speculativeDraftMinContinueProbability`. A sweep futtató az első kettőt `false`
  értékkel küldi, és ezek megjelennek a load után visszaolvasott konfigurációban.
- Az SDK-n át kért predikció elfogadja a `draftModel` mezőt, és közli a `usedDraftModelKey`, `totalDraftTokensCount`,
  `acceptedDraftTokensCount`, `rejectedDraftTokensCount` és `ignoredDraftTokensCount` értékeket.
- Az `lms load` listáz `--speculative-draft-*` kapcsolókat, és a REST load hívás elfogad speculative mezőket
  ([load paraméterek](lmstudio_load_parameters.hu.md)).
- Nem ismert, hogy a méréshez használt REST chat végpont visszaad-e draft számlálókat.
- Dokumentáció: [LM Studio](https://lmstudio.ai/docs/app/advanced/speculative-decoding),
  [llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md). Az upstream llama.cpp több
  módszert kínál, mint amennyiről tudjuk, hogy LM Studión át elérhető.

### Fázisok

| Fázis | Tartalom | Kilépési feltétel |
|---|---|---|
| 0, próba | Load draft modellel és MTP-vel az SDK-ból; a konfiguráció visszaolvasása; draft statisztika SDK-n és a REST chat hívásban; VRAM-többlet; átmegy-e a beállítás a későbbi loadokba | Írásos képességtábla és döntés az MTP kapcsolásának módjáról |
| 1 | LM Studio: kikapcsolva, draft modell, MTP | Reprodukálható összehasonlítás legalább egy modellen |
| 2, opcionális | Közvetlen `llama-server` backend további módszerekhez (n-gram, EAGLE-3, DFlash és hasonlók) | Ugyanabba az eredményformátumba mérve; csak külön döntés után |

A draft modellek tanítása nincs a hatókörben. Draft modell letöltéséhez vagy harmadik féltől származó build
futtatásához minden esetben jóváhagyás kell.

### A 0. fázis próbaterve (elfogadva és lefuttatva 2026-11-26)

Határok: önálló próbascript (`harness/spec-probe.ts`), rácsintegráció nélkül, alkalmazás-, runtime- és SDK-frissítés
nélkül, a LM Studio beállításfájljai érintetlenek. Modellek: egy 7B-s kódmodell ugyanabból a családból származó kis
draft modellel, 4k contexttel (tartalék a 8 GB-os GPU-n), valamint a helyben elérhető MTP-s modellek; ezek
modellkártyáját előbb elolvassuk a használati megjegyzések miatt.

| Lépés | Tartalom | GPU |
|---|---|---|
| P0 | Próbascript, típusellenőrzés, a LM Studio config mappájának hash-e. Kész: `harness/spec-probe.ts` offline tesztekkel és `--dry-run` móddal; valódi típusellenőrzéshez TypeScript fordító kell, nincs telepítve | nem |
| P1 | Baseline kikapcsolt spekulációval: VRAM, decode-sebesség (bemelegítő és 3 futás), kódgeneráló és szintetikus prompttal | igen |
| P2 | Draft modell a loadnál: az alkalmazott konfiguráció visszaolvasása, VRAM-többlet, külön betöltött modellként látszik-e a draft, draft számlálók, sebesség | igen |
| P3 | Draft modell predikciónként (`draftModel`) baseline loadon: statisztika és sebesség | igen |
| P4 | Ugyanez a REST chat végponton: a nyers válaszmezők mentése, vannak-e draft számlálók | igen |
| P5 | MTP be- és kikapcsolva; a betöltési hiba indokolt "skipped" eredmény | igen |
| P6 | Beragadás: újratöltés a spekulációs mezők elhagyásával és visszaolvasás; váltás draftról MTP-re; a config mappa hash-ének összevetése; nem kompatibilis pár a hibaüzenetért (SD-01) | igen |
| P7 | Képességtábla ebbe a pontba; a megállapítások és a load paraméterek dokumentumának frissítése | nem |

Elfogadás: a P1–P6 minden kérdésének van állapota (igazolt, nem működik, blokkolt); minden eredmény rögzíti az
alkalmazás és a runtime verzióját és a háttér VRAM-foglalást; a config mappa változatlan; nem marad betöltött modell;
legfeljebb kb. egy óra GPU-idő. Minden GPU-s futás csak jóváhagyás után indul.

### A 0. fázis eredményei (2026-11-26, GPU-n futtatva)

Bionic 1.2.0, RTX 2070 8 GB, 4k context, teljes offload, f16 KV, temperature 0, bemelegítő és promptonként 3 futás 200
kimeneti tokennel. A próba nyers eredményei helyben maradnak.

| Kérdés | Eredmény | Állapot |
|---|---|---|
| Draft modell a loadnál (`speculativeDraftSimple` + `speculativeDraftModel`) | A kért módon érvényesül, és visszaolvasható. LM Studio alapértékek: 3 maximális draft token, minimum 0, folytatási valószínűség 0 | igazolt |
| Draft modell predikciónként (`draftModel`) | A motor elutasítja: a speculative decodingot a loadnál kell beállítani | ebben a verzióban nem működik |
| MTP a loadnál (`speculativeDraftMtp`) | Érvényesül, visszaolvasható; vannak draft számlálók | igazolt |
| Draft számlálók az SDK-ban | `usedDraftModelKey`, total, accepted, rejected; az `ignoredDraftTokensCount` nem jön vissza | igazolt |
| Draft számlálók a REST chat végponton | `stats` objektum (`draft_model`, `total_draft_tokens_count`, `accepted_draft_tokens_count`, `rejected_draft_tokens_count`) a nem streamelt válaszban és `stream_options.include_usage` mellett az utolsó streamelt chunkban | igazolt |
| Draft modell az `lms ps` listában | Nem szerepel; csak a fő modell látszik, a költség csak a VRAM-ban jelenik meg | igazolt |
| VRAM-többlet | Draft modell (1.5B, Q8_0): kb. +1,2 GiB. MTP be és ki: nincs különbség (a fejek valószínűleg mindkét esetben betöltődnek; következtetés) | igazolt, egy-egy méréssel |
| Beragadás | Egy későbbi load, amely elhagyja a spekulációs mezőket, kikapcsolt állapotot kap; draft load után MTP load nem hagy draft modellt; a per-modell config mappa változatlan | igazolt |
| Nem kompatibilis pár | Egy 1B-s Llama fő modell 1.5B-s Qwen drafttal betölt és válaszol, a `usedDraftModelKey` ki van töltve, számlálók nincsenek. A LM Studio nem utasítja el | igazolt; az SD-01-hez saját kompatibilitás-ellenőrzés kell |
| Greedy kimenet a baseline-hoz képest | Bekapcsolt spekulációval a futások többsége 20–800 karakter után eltér; az okot nem vizsgáltuk | megfigyelt |

Decode-sebesség, 3 futás mediánja (kódprompt / szintetikus prompt), mindegyik az alapértelmezett 3 maximális draft
tokennel:

| Összeállítás | Ki, t/s | Be, t/s | Változás | Elfogadási arány |
|---|---|---|---|---|
| 7B kódmodell + ugyanabból a családból 1.5B Q8_0 draft | 63,4 / 60,6 | 55,8 / 34,2 | −12% / −44% | 0,76 / 0,36 |
| 4B modell, beépített MTP-fej | 78,5 / 77,1 | 96,4 / 96,5 | +23% / +25% | 0,70 / 0,72 |
| 9B finomhangolt modell, az alapmodellből átültetett MTP-fejjel | 50,3 / 49,0 | 54,8 / 65,3 | +9% / +33% | 0,54 / 0,72 |
| 0.8B modell, beépített MTP-fej | 156,9 / 152,1 | 163,5 / 179,0 | +4% / +18% | 0,51 / 0,66 |

Ezek egyszeri próbafutások, nem az SD-02–SD-07 szerinti összehasonlítás.

**Döntés (a 0. fázis kilépési feltétele):** a spekuláció csak a loadnál kapcsolható, az SDK load mezőivel: MTP a
`speculativeDraftMtp`, draft modell a `speculativeDraftSimple` és a `speculativeDraftModel` mezővel. Az 1. fázis
megtarthatja a mostani loadert, és a REST végponton mérhet, amely visszaadja a számlálókat. Az 1. fázis újdonságai: a
maximális draft token végigmérése (a modellkártyák 2–6-ot javasolnak), kompatibilitás-ellenőrzés a draft párokra
(tokenizer), kisebb draft modellek.

### Követelmények

A "Ma" oszlop a jelenlegi sweep futtatót írja le.

| ID | Követelmény | Ma |
|---|---|---|
| SD-01 | Képességfelderítés modellenként: van-e MTP, mely draft modellek kompatibilisek, runtime verzió. A nem támogatott kombináció indokolt "skipped" eredmény, nem hiba | hiányzik |
| SD-02 | Minden spekulatív konfiguráció egy "kikapcsolt" méréshez kapcsolódik azonos modellel, kvantálással, contexttel, offloaddal és mintavétellel; a sorrend váltakozik | részben: van baseline konfiguráció, kapcsolat nélkül; rögzített sorrend |
| SD-03 | Konfigurációs tér a rácsból: módszer, draft modell és kvantálása, maximális és minimális draft token, valószínűségi küszöb, draft offload. A maximális draft token előbb durván (1, 3, 6), majd a legjobb körül finomítva | részben: a rács bővíthető, a loader mindig kikapcsolja a spekulációt |
| SD-04 | Metrikák: decode-sebesség, első token ideje, teljes idő, VRAM- és RAM-csúcs, betöltési idő, draft számlálók, gyorsulás a baseline-hoz. A hiányzó érték "n/a", soha nem becslés | részben: nincs draft számláló, generálásonkénti teljes idő, RAM és gyorsulás |
| SD-05 | Két külön mező: elfogadási arány (elfogadott / generált draft token) és draft-hányad (elfogadott draft token / kimeneti token) | hiányzik |
| SD-06 | Terhelésprofilok, profilonkénti eredménnyel: kódgenerálás, meglévő szöveg vagy kód szerkesztése, matek és reasoning, folyószöveg, agent- és JSON-kimenet, hosszú context. A mostani ismétlődő szintetikus prompt valószínűleg túlbecsülné az elfogadást | hiányzik |
| SD-07 | Warm-up, legalább 3 ismétlés, medián és szórás; sebességhez temperature 0 és rögzített seed, plusz egy futás éles mintavétellel; naplózva az alkalmazás és a runtime verziója, a modellfájl hashe, a load konfiguráció | részben: nincs éles mintavételű futás és fájlhash; az alkalmazás verziója rögzül |
| SD-08 | Igazolt, hogy a kért mód aktív (draft számlálók, log), a baseline-nál pedig hogy inaktív; különben a mérés érvénytelen | részben: az alkalmazott load konfigurációt összevetjük, az aktivitást nem |
| SD-09 | Minőségőr: greedy mintavétellel a kimenet összevetése a baseline-nal, az első eltérés riportálva (az eltérés önmagában nem hiba) | hiányzik: a kimeneteket nem tároljuk |
| SD-10 | Alapmérés egy párhuzamos predikcióval; magasabb concurrency külön dimenzió; vision modelleknél a kompatibilitás külön ellenőrizve | részben: csak egy párhuzamos predikció |
| SD-11 | Betöltési hiba, memóriahiány vagy timeout eredményként rögzül, és a sweep megy tovább | részben: így van, de két egymást követő timeout megszakítja a futást |
| SD-12 | Ajánlás modellenként és profilonként gyorsulással és memóriaárral; "kikapcsolva", ha a nyereség az állítható küszöb alatt van (induló érték: 1,10x) | részben: a kiértékelés ajánl, küszöb nélkül |
| SD-13 | A backendtől független eredményformátum (backend és runtime mező) | hiányzik |

A terhelésprofilok a rögzített feladatkészlettől (20. feladat) függnek. A fejlesztői gép 8 GB-os GPU-ja kevés helyet
hagy egy draft modellnek; először a tartalékkal beférő modellek jönnek.
