# Catalog leak cleaner summary

Tiny residual U-Net trained on clean-ish manufacturer sheets with synthetic transmitted-background leakage.

## Synthetic held-out

| metric | contaminated | neural | change |
|---|---:|---:|---:|
| RGB MAE | 0.0425 | 0.0341 | 19.9% lower |
| low-frequency MAE | 0.0393 | 0.0315 | 19.7% lower |
| high-frequency MAE | 0.0069 | 0.0073 | -4.8% lower |
| detail energy ratio | 1.000 target | 1.344 | closer is better |

## Real suncatcher position sensitivity

| condition | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| raw | 8.98 | 0.407 | 1.5 |
| raw_neural | 7.85 | 0.358 | 1.4 |
| relit | 10.12 | 0.318 | 1.7 |
| relit_neural | 9.36 | 0.285 | 1.5 |
| prior | 1.90 | 0.060 | 0.3 |

## Read

- `raw_neural` applies the learned cleaner directly to the raw sheet photo; `relit_neural` applies it after fixed `T/h` extraction.
- `prior` is the earlier hand sheet-level prior. It remains the consistency ceiling but can over-flatten true sheet variation.
- A useful neural result is not only lower dE/CV; it must also keep high-frequency texture near the source. See `suncatcher.sheet_metrics` in `metrics.json`.
