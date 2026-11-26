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
