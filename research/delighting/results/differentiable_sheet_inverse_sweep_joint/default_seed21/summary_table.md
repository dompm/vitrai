# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0000 | 0.1546 | 0.8113 | 0.183 | 0.983 | 2.43 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0058 | 0.0106 | 0.0000 | 0.068 | 0.258 | 2.43 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0017 | 0.0063 | 0.0000 | 0.064 | 0.071 | 1.61 | 0.75/0.62 |
| low-T + displacement + learned B | 0.0011 | 0.1112 | 0.2244 | 0.087 | 0.333 | 2.42 | 0.48/0.10 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
