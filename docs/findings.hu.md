# Mérési megállapítások

[English](findings.md)

A mérések általános eredményei. A load beállítások és ellenőrzésük: [load paraméterek](lmstudio_load_parameters.hu.md).
Nyitott pontok: [roadmap](roadmap.hu.md), 4. pont.

## Tiszta sweepek, 2026-11-26

Felülírják az ugyanaznapi, 56 jobos próbafutást, amely terhelt gépen futott.

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

## Speculative decoding próba (0. fázis), 2026-11-26

Ugyanaz a gép, 4k context, egyszeri próbafutások a LM Studio alapértelmezett 3 draft tokenjével; részletek a
[követelményekben](requirements.hu.md), 5. pont.

- A külön draft modell (1.5B Q8_0 egy 7B Q4 kódmodellhez) lassította a decode-ot (kódon −12%, a szintetikus prompton
  −44%), pedig kódon a draft tokenek 76%-a elfogadásra került. Valószínű ok (nem igazolt): ezen a GPU-n a decode-ot a
  memória-sávszélesség korlátozza, és a fő modell méretének kb. 40%-át kitevő draft modell többe kerül, mint amennyit
  megtakarít.
- A beépített MTP-fejek három modellen gyorsítottak (+4% és +33% között), VRAM-többlet nélkül.
- A spekuláció csak a loadnál kapcsolható; a REST chat végpont visszaadja a draft számlálókat.

## Agent-feladatok, az M1 készlet első élő futása, 2026-11-27

Ugyanaz a gép, 20 feladat, mindegyik öt próbálkozással, mintavétel a modellkártyák szerint; részletek a
[követelményekben](requirements.hu.md), 3. pont, és a [hibataxonómiában](failure_taxonomy.hu.md).

- A toolt hívó három modell a próbálkozások 90–96%-át teljesítette; öt ismétlésnél az intervallumaik átfednek.
- Egy 7B-s kódmodell 83 bukásából 74-ben szövegként írta ki a hívást; egy ilyen modellnél a feladatkészlet csak a
  formátumhibát méri.
- Egy átmeneti tool-hibát szinte egyik modell sem próbált újra: helyette jelezték a hibát a felhasználónak.
- A bukások kézi átnézése négy rést talált a kulcsszó-alapú szabályokban; egy ilyen kategorizálóhoz minden új
  feladatkészlet után kell ilyen átnézés.
