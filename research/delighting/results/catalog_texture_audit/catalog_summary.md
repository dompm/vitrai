# Catalog texture audit

Manufacturer catalog images are used here as a reality check for the sheet-level prior.
Lower `lowfreq_cv` means less broad lighting/background variation; `highfreq_std` is the retained local texture/relief signal.

## Catalog distribution

| category | n | lum_cv med | lowfreq_cv med | highfreq_std med | chroma_mad med | sat_mean med |
|---|---:|---:|---:|---:|---:|---:|
| Cathedral | 699 | 0.221 | 0.179 | 0.094 | 0.024 | 0.424 |
| Opalescent | 356 | 0.099 | 0.078 | 0.030 | 0.011 | 0.462 |
| Wispy/Streaky | 163 | 0.412 | 0.322 | 0.223 | 0.063 | 0.466 |
| Textured/Baroque | 138 | 0.503 | 0.301 | 0.343 | 0.047 | 0.539 |
| English Muffle | 17 | 0.268 | 0.189 | 0.163 | 0.032 | 0.508 |
| Ring Mottle | 8 | 0.306 | 0.183 | 0.181 | 0.046 | 0.404 |

## Suncatcher sheet conditions

| sample | lum_cv | lowfreq_cv | highfreq_std | chroma_mad | textured highfreq percentile | cathedral lowfreq percentile |
|---|---:|---:|---:|---:|---:|---:|
| green_raw | 0.946 | 0.611 | 0.564 | 0.020 | 77% | 90% |
| green_relit | 0.735 | 0.477 | 0.558 | 0.019 | 76% | 84% |
| green_prior | 0.344 | 0.087 | 0.341 | 0.000 | 50% | 32% |
| orange_raw | 0.606 | 0.400 | 0.432 | 0.026 | 66% | 78% |
| orange_relit | 0.404 | 0.258 | 0.353 | 0.081 | 51% | 63% |
| orange_prior | 0.207 | 0.050 | 0.216 | 0.023 | 21% | 25% |

## Read

- The sheet prior is valuable if it lowers low-frequency contamination while keeping high-frequency texture inside the real catalog range.
- If its high-frequency percentile collapses, it is too airbrushed; if its low-frequency percentile stays high, it did not solve the right problem.
- This audit is a style/provenance check, not proof that the exact physical sheet was recovered.
