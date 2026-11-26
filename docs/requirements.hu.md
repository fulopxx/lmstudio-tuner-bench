# Követelmények és tervezett munka

[English](requirements.md)

Mit kell tudniuk a tervezett részeknek. A feladatszámok a [roadmapre](roadmap.hu.md) vonatkoznak, az állapotok is ott
vannak.

## 1. Felület

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

### Nyitott

- A Python core és a TypeScript harness közötti interfész (processhatár, trace-formátum).
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
| SD-07 | Warm-up, legalább 3 ismétlés, medián és szórás; sebességhez temperature 0 és rögzített seed, plusz egy futás éles mintavétellel; naplózva az alkalmazás és a runtime verziója, a modellfájl hashe, a load konfiguráció | részben: nincs éles mintavételű futás, alkalmazásverzió és fájlhash |
| SD-08 | Igazolt, hogy a kért mód aktív (draft számlálók, log), a baseline-nál pedig hogy inaktív; különben a mérés érvénytelen | részben: az alkalmazott load konfigurációt összevetjük, az aktivitást nem |
| SD-09 | Minőségőr: greedy mintavétellel a kimenet összevetése a baseline-nal, az első eltérés riportálva (az eltérés önmagában nem hiba) | hiányzik: a kimeneteket nem tároljuk |
| SD-10 | Alapmérés egy párhuzamos predikcióval; magasabb concurrency külön dimenzió; vision modelleknél a kompatibilitás külön ellenőrizve | részben: csak egy párhuzamos predikció |
| SD-11 | Betöltési hiba, memóriahiány vagy timeout eredményként rögzül, és a sweep megy tovább | részben: így van, de két egymást követő timeout megszakítja a futást |
| SD-12 | Ajánlás modellenként és profilonként gyorsulással és memóriaárral; "kikapcsolva", ha a nyereség az állítható küszöb alatt van (induló érték: 1,10x) | részben: a kiértékelés ajánl, küszöb nélkül |
| SD-13 | A backendtől független eredményformátum (backend és runtime mező) | hiányzik |

A terhelésprofilok a rögzített feladatkészlettől (20. feladat) függnek. A fejlesztői gép 8 GB-os GPU-ja kevés helyet
hagy egy draft modellnek; először a tartalékkal beférő modellek jönnek.
