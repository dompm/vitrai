# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0000 | 0.1673 | 0.8124 | 0.276 | 0.986 | 3.89 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0085 | 0.0237 | 0.0000 | 0.086 | 0.427 | 3.89 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0020 | 0.0114 | 0.0000 | 0.073 | 0.128 | 2.90 | 0.56/0.51 |
| low-T + displacement + learned B | 0.0011 | 0.1200 | 0.1929 | 0.117 | 0.221 | 4.42 | 0.07/0.22 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
