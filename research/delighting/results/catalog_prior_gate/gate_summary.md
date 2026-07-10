# Catalog prior gate

A score near 1 means broad low-frequency variation is anomalously high for the presumed material family and the sheet-prior should be considered. A score near 0 means leave the sheet alone or require manual/provenance labeling.

## Suncatcher sheet conditions

| sample | family | score | z_lowfreq | z_chroma | z_detail | lowfreq_cv | highfreq_std |
|---|---|---:|---:|---:|---:|---:|---:|
| green_raw | Textured/Baroque | 0.84 | 1.3 | -0.4 | 0.8 | 0.611 | 0.564 |
| green_relit | Textured/Baroque | 0.66 | 0.8 | -0.4 | 0.8 | 0.477 | 0.558 |
| green_prior | Textured/Baroque | 0.14 | -0.9 | -0.7 | -0.0 | 0.087 | 0.341 |
| orange_raw | Textured/Baroque | 0.54 | 0.4 | -0.3 | 0.3 | 0.400 | 0.432 |
| orange_relit | Textured/Baroque | 0.22 | -0.2 | 0.5 | 0.0 | 0.258 | 0.353 |
| orange_prior | Textured/Baroque | 0.10 | -1.1 | -0.4 | -0.5 | 0.050 | 0.216 |

## Catalog self-check

| category | n | median score | p75 score | flagged >0.50 | flagged >0.70 |
|---|---:|---:|---:|---:|---:|
| Cathedral | 699 | 0.29 | 0.41 | 15% | 6% |
| Opalescent | 356 | 0.33 | 0.45 | 21% | 10% |
| Wispy/Streaky | 163 | 0.28 | 0.45 | 21% | 10% |
| Textured/Baroque | 138 | 0.28 | 0.48 | 21% | 9% |
| English Muffle | 17 | 0.38 | 0.43 | 18% | 12% |
| Ring Mottle | 8 | 0.24 | 0.39 | 25% | 0% |

## Read

- The raw and fixed suncatcher sheets should score high if report 013's background-leak diagnosis is right.
- The sheet-prior outputs should score low; otherwise the prior did not remove the suspicious broad variation.
- High catalog false-positive rates mean this gate is not yet ship-safe. It is a research triage signal.
