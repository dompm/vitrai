# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0000 | 0.1652 | 0.8113 | 0.231 | 0.985 | 3.95 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0077 | 0.0194 | 0.0000 | 0.065 | 0.318 | 3.95 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0019 | 0.0101 | 0.0000 | 0.064 | 0.193 | 2.74 | 0.59/0.45 |
| low-T + displacement + learned B | 0.0011 | 0.1174 | 0.1923 | 0.094 | 0.263 | 4.05 | 0.45/0.15 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
