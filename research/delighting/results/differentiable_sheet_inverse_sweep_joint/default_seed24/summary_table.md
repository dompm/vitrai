# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0000 | 0.1564 | 0.8124 | 0.223 | 0.984 | 2.40 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0064 | 0.0128 | 0.0000 | 0.066 | 0.297 | 2.40 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0018 | 0.0084 | 0.0000 | 0.072 | 0.142 | 1.71 | 0.61/0.66 |
| low-T + displacement + learned B | 0.0011 | 0.1131 | 0.2254 | 0.097 | 0.373 | 2.64 | 0.04/0.22 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
