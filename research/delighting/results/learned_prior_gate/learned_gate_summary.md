# Learned prior gate

| metric | value |
|---|---:|
| train AUC | 0.852 |
| test AUC | 0.844 |
| test accuracy @0.50 | 0.769 |
| clean false positive @0.50 | 0.256 |
| clean false positive @0.70 | 0.100 |
| synthetic leak true positive @0.50 | 0.794 |
| synthetic leak true positive @0.70 | 0.556 |

## Suncatcher scores

| sample | learned score | lowfreq_cv | highfreq_std | chroma_mad |
|---|---:|---:|---:|---:|
| green_raw | 0.51 | 0.611 | 0.564 | 0.020 |
| green_relit | 0.33 | 0.477 | 0.558 | 0.019 |
| green_prior | 0.06 | 0.087 | 0.341 | 0.000 |
| orange_raw | 0.25 | 0.400 | 0.432 | 0.026 |
| orange_relit | 0.10 | 0.258 | 0.353 | 0.081 |
| orange_prior | 0.04 | 0.050 | 0.216 | 0.023 |

## Coefficients

| feature | weight |
|---|---:|
| bias | 0.007 |
| lum_cv | 0.711 |
| lowfreq_cv | 0.316 |
| highfreq_std | -0.208 |
| highfreq_p95 | 0.085 |
| chroma_mad | -0.247 |
| sat_mean | -0.498 |
| low_to_high | 1.046 |
| low_minus_chroma | 0.246 |
| z_lum | -0.093 |
| z_lowfreq | -0.108 |
| z_chroma | 0.053 |
| z_detail | -0.311 |
