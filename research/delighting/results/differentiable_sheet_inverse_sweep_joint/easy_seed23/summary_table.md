# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0068 | 0.1531 | 0.8134 | 0.185 | 0.980 | 1.99 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0048 | 0.0082 | 0.0000 | 0.073 | 0.187 | 1.99 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0018 | 0.0059 | 0.0000 | 0.071 | 0.095 | 1.51 | 0.60/0.55 |
| low-T + displacement + learned B | 0.0011 | 0.1051 | 0.2472 | 0.084 | 0.340 | 2.03 | 0.15/0.15 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
