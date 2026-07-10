# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0000 | 0.1563 | 0.8134 | 0.226 | 0.984 | 2.89 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0064 | 0.0130 | 0.0000 | 0.076 | 0.253 | 2.89 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0018 | 0.0075 | 0.0000 | 0.071 | 0.133 | 2.02 | 0.63/0.60 |
| low-T + displacement + learned B | 0.0011 | 0.1125 | 0.2218 | 0.097 | 0.351 | 2.98 | 0.21/0.14 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
