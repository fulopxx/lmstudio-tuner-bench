# Az agent-próbálkozások hibataxonómiája

[English](failure_taxonomy.md)

Taxonómia 1. verzió (2026-11-26). Követelmények és indokok: [követelmények](requirements.hu.md), 3. pont (FA-30–FA-39).
A gépileg olvasható forrás a `runner/failures.py` `CATEGORIES` szótára; teszt ellenőrzi, hogy minden alábbi azonosító
egyezik vele. Állapot: megvalósítva, szintetikus és két rögzített élő trace-en tesztelve; teljes feladatkészleten még
nem használtuk, és a heurisztikus szabályokat még nem vetettük össze kézi átnézéssel (FA-37).

## Hogyan kap kategóriát egy próbálkozás

Csak a sikertelen próbálkozás kap kategóriát. Mindegyik pontosan egy **elsődleges** kategóriát kap alkóddal, a
**bizonyítékkal** (a trace-esemény sorszáma és a szabály neve), a többi találat **mellékkategóriaként** jelenik meg.
A sikeres próbálkozásokon is lehetnek **jelzők**.

| Szint | Kategóriák | Melyik nyer |
|---|---|---|
| Szerkezeti | `infra_error` > `context_overflow` > `output_truncated` > `format_invalid` | rögzített sorrend |
| Viselkedési | `no_tool_when_needed`, `wrong_tool`, `wrong_arguments`, `unnecessary_tool`, `loop`, `incomplete_chain` | az a találat, amelynek első bizonyítéka a legkorábban van a trace-ben; egyezésnél ez a sorrend |
| Kimeneti | `limit_silent` > `ignored_tool_error` > `wrong_result` > `unclassified` | rögzített sorrend, csak ha nincs viselkedési találat |

A viselkedési szabály indoka: a hibák egymásból következnek (a rossz argumentum tool-hibát ad, a modell ismétli a
hívást, a körkorlát megállítja). A rögzített sorrend az utolsó láncszemet jelentené, az időrend az elsőt mutatja.

**Csendes vagy hangos.** Egy bukás *csendes*, ha a felhasználó nem veheti észre: a futás rendben véget ért, a válasz
nem üres, nem kérdés, és nincs benne egyik problémaszó sem (error, unable, timed out, limit, not found és hasonlók;
lista a `PROBLEM_SIGNALS`-ban). A szerkezeti bukások mindig hangosak. A csendes bukások aránya a riport vezető száma:
a funkcionális biztonság nem detektált hibájának felel meg. A szabály heurisztikus.

**Mit feltételez a mérés.** Az alapértelmezett system prompt kéri, hogy a modell hiányzó adatnál használjon toolt, és
szóljon, ha egy tool hibázik; a körkorlát elérésekor a harness felszólítja a modellt, hogy válaszoljon, és jelezze, ha a
válasz hiányos. A `limit_silent` és az `ignored_tool_error/not_reported` ezért azt méri, követi-e a modell ezeket az
utasításokat; a trace rögzíti a system promptot.

## Kategóriák (FMEA-szemlélet)

Az ellenintézkedések lehetséges ellenintézkedések, **nem mértük** őket (a 19. feladat méri majd). Megbízhatóság:
*szabály* = a trace szerkezete dönti el; *heurisztikus* = szövegillesztéstől függ.

| Kategória | Hibamód | Hatás | Detektálás | Megbízhatóság | Lehetséges ellenintézkedés (nem mért) |
|---|---|---|---|---|---|
| `infra_error` | A harness vagy az SDK hibázott, a próbálkozást leállították, kihagyták, vagy a trace-ének nincs vége | A modellről nem mond semmit; a modell pontszámába nem számít | `error`, `aborted`, `skipped` állapot; `error` esemény; hiányzó `task_end` | szabály | Környezet javítása; újrafuttatás |
| `context_overflow` | A beszélgetés nem fér a contextbe | Levágott vagy hiányzó válasz | `contextLengthReached` leállási ok (a harness a határon megállást kér a LM Studiótól) | szabály | Nagyobb context; kisebb tool-eredmények; az előzmény összegzése |
| `output_truncated` | Elfogyott egy kör tokenkerete | Hiányzó vagy részleges válasz | `maxPredictedTokensReached` leállási ok | szabály | Nagyobb körönkénti keret; gondolkodási keret; nem gondolkodó mód |
| `format_invalid` | A modell toolt próbált hívni, de a hívás nem lett felismerve | Nem fut tool; úgy látszik, mintha a modell figyelmen kívül hagyta volna a toolokat | Az SDK értelmezhetetlen hívást jelzett; vagy egy tool-hívás nélküli válasz hívásformában nevez meg egy felkínált toolt (`"name": "<tool>"`, `<function=<tool>`, `<tool_call>`) | heurisztikus (szöveges forma), szabály (SDK-jelzés) | A szöveges hívás értelmezése (javítás); grammar vagy séma-kényszerítés; jobb chat template |
| `no_tool_when_needed` | A modell egy szükséges tool hívása nélkül válaszolt | Kitalált válasz vagy visszakérdezés | Nincs értelmezett hívás, pedig a feladat hívást vár | szabály | Erősebb tool-utasítás a system promptban; kötelező toolválasztás |
| `wrong_tool` | Nem létező, csali vagy tiltott tool hívása | Rossz adat; tiltott toolnál nem kívánt művelet | Hívás ismeretlen toolra; hívás egy `forbidden_tools` bejegyzésre; a várt hívásokon kívüli tool, miközben a várt lánc nem teljes | szabály | Világosabb tool-leírások; kevesebb felkínált tool; megerősítés romboló toolok előtt |
| `wrong_arguments` | Jó tool, rossz argumentumokkal | Tool-hiba vagy rossz adat | A sémaellenőrzés elbukott (hiányzó, rossz típusú, enumon kívüli vagy ismeretlen argumentum); vagy a következő várt hívás nem illeszkedő argumentumokkal történt | szabály | Séma-kényszerítés; példák a tool-leírásban; típuskonverzió a toolban |
| `unnecessary_tool` | Tool-hívás, pedig nem kellett | Költség, késés; mellékhatások | Hívás egy `no_tool_needed` jelölésű feladatban | szabály | Utasítás a közvetlen válaszra, ha lehetséges |
| `loop` | Ugyanaz a hívás ismétlődik, vagy a körkorlát állítja meg a modellt | Elvesztegetett idő; nincs saját válasz | Ugyanaz a név és argumentum legalább `loop_threshold`-szor (alapból 3); körkorlát olyan feladatban, amely nem fogadja el | szabály | Visszajelzés ismételt hívásnál; alacsonyabb körkorlát világos üzenettel |
| `incomplete_chain` | A modell egy többlépéses lánc vége előtt megállt | Részeredmény végeredményként | A várt hívások egy valódi előtagja megtörtént, és az utolsó körben nincs hívás | szabály | Előbb a lépések megtervezése; a cél felidézése minden tool-eredmény után |
| `limit_silent` | Korlát teljesült, és a válasz nem mondja meg | A felhasználó megbízik egy hiányos válaszban | `limit_hit` esemény, és a válaszban nincs a feladat egyik hibaszava (vagy a problémaszavak egyike) sem | heurisztikus | Egyértelmű korlátüzenet; a válasz ellenőrzése a korlát említésére |
| `ignored_tool_error` | Egy tool hibázott, és a válasz figyelmen kívül hagyja | Kitalált eredmény vagy hiányzó figyelmeztetés | `ok = false` tool-eredmény, és a válasz a feladat tiltólistájának egy értékét tartalmazza, vagy egyik hibaszót sem | `fabricated`: szabály; `not_reported`: heurisztikus | Utasítás a tool-hibák jelzésére; strukturált hibaeredmények |
| `wrong_result` | A lépések jók voltak, a válasz rossz | Hibás információ tényként | A várt hívások megtörténtek (vagy nem kellett tool, és nem is volt hívás), és egy válaszellenőrzés elbukik | szabály | A tool-eredmény idézésének kérése; válaszformátum |
| `unclassified` | Sikertelen, és egy szabály sem magyarázza | Rés a taxonómiában | Nincs más találat | szabály | A trace átnézése; a taxonómia bővítése |

### Alkódok

| Kategória | Alkód | Jelentés |
|---|---|---|
| `infra_error` | `harness_error` | A harness hibát jelzett |
| | `aborted` | A felhasználó vagy a stop parancs leállította |
| | `skipped` | Nem futott le (a futás korábban leállt) |
| | `incomplete_trace` | A trace-ben nincs `task_end` (a harnesst leállították) |
| `output_truncated` | `reasoning_exhausted` | A keret a gondolatmenetre ment el, a válasz üres |
| | `max_tokens` | Maga a válasz lett levágva |
| `format_invalid` | `sdk_parse_failure` | Az SDK értelmezhetetlen hívást jelzett |
| | `text_tool_call` | A hívás szövegként került a válaszba |
| `no_tool_when_needed` | `asked_user` | A válasz kérdés |
| | `answered_without_data` | A modell az adat nélkül válaszolt |
| `wrong_tool` | `unknown_tool` | Nem felkínált toolnév |
| | `decoy` | Felkínált tool, amely nem vezet a válaszhoz |
| | `forbidden` | A feladat által tiltott tool |
| `wrong_arguments` | `missing_required` | Hiányzik egy kötelező argumentum |
| | `wrong_type` | Rossz típus (a stringként küldött szám is) |
| | `wrong_value` | Nem várt érték (enum- vagy ismeretlenargumentum-sértés is) |
| | `invented_value` | Olyan string érték, amely sem a promptban, sem korábbi tool-eredményben nem szerepel |
| `loop` | `identical_calls` | Ugyanaz a hívás ismétlődik |
| | `round_limit` | A körkorlát állította meg |
| `limit_silent` | `rounds`, `wall_time`, `tool_timeout` | Melyik korlát teljesült |
| `ignored_tool_error` | `fabricated` | A tiltólista egy értéke a válaszban |
| | `not_reported` | A hibát nem említi |
| `wrong_result` | `empty_answer` | Nincs válasz |
| | `partial` | A várt tények egy része hiányzik |
| | `wrong_value` | Más módon buknak a válaszellenőrzések |

### Jelzők

Minden próbálkozáson számolódnak, a sikereseken is.

| Jelző | Jelentés |
|---|---|
| `recovered_error` | Tool-hiba vagy érvénytelen hívás történt, és a próbálkozás mégis sikeres (a 19. feladat kiindulási adata) |
| `redundant_calls` | Ismételt azonos hívások, vagy több hívás a várt sorozatnál |
| `parallel_calls` | Egy körben több hívás (képesség, nem hiba) |
| `reasoning_leak` | Gondolatmenet vagy LM Studio elválasztó a válaszban; hamis sikert okozhat |
| `sandbox_escape_attempt` | A `read_file` a sandboxon kívüli útvonalat kapott |

## Kapcsolat a publikált felosztásokkal

Publikálás előtt a forrásokkal egyeztetendő; részben összefoglalókból származik.

| Itt | Publikált |
|---|---|
| `format_invalid` | BFCL: a hívásformátum AST- vagy végrehajtási eltérése |
| `wrong_tool/unknown_tool`, `wrong_tool/decoy` | Toolkiválasztási hallucináció (Xu et al., arXiv 2412.04141) |
| `wrong_arguments/invented_value` | Toolhasználati hallucináció (ugyanott) |
| `no_tool_when_needed/asked_user` hiányzó paraméteres feladatban | BFCL v3 „missing parameters” |
| `unnecessary_tool` | BFCL relevancia- / irrelevancia-felismerés |
| `loop/identical_calls` | MAST FM-1.3 lépésismétlés (Cemri et al., arXiv 2503.13657) |
| `loop/round_limit`, `limit_silent` | MAST FM-1.5 a leállási feltételek figyelmen kívül hagyása |
| `incomplete_chain` | MAST FM-3.1 idő előtti befejezés |

## Verziókezelés

Egy kategóriaazonosító, alkód vagy detektálási szabály változása emeli a taxonómia verzióját; az eredménysorok
rögzítik (`taxonomy_version`), és a `bench agent report` (tervezett, M1 5b) a trace-ekből számolja újra a
kategóriákat, így a régebbi futások újabb verzióval is újra besorolhatók.
