# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0000 | 0.1560 | 0.8104 | 0.220 | 0.984 | 2.55 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0061 | 0.0118 | 0.0000 | 0.071 | 0.230 | 2.55 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0018 | 0.0073 | 0.0000 | 0.065 | 0.161 | 1.84 | 0.62/0.52 |
| low-T + displacement + learned B | 0.0011 | 0.1101 | 0.2129 | 0.111 | 0.357 | 2.88 | 0.06/0.05 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
