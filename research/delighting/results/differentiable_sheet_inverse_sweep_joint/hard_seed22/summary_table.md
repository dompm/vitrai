# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0000 | 0.1671 | 0.8104 | 0.280 | 0.987 | 4.14 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0081 | 0.0231 | 0.0000 | 0.094 | 0.357 | 4.14 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0020 | 0.0121 | 0.0000 | 0.065 | 0.166 | 3.09 | 0.51/0.47 |
| low-T + displacement + learned B | 0.0011 | 0.1162 | 0.1781 | 0.128 | 0.319 | 4.83 | 0.09/0.05 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
