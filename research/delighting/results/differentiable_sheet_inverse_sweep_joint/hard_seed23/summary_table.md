# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0000 | 0.1667 | 0.8134 | 0.280 | 0.987 | 4.70 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0085 | 0.0220 | 0.0000 | 0.068 | 0.302 | 4.70 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0021 | 0.0109 | 0.0000 | 0.061 | 0.138 | 3.35 | 0.52/0.52 |
| low-T + displacement + learned B | 0.0011 | 0.1194 | 0.1938 | 0.122 | 0.315 | 4.77 | 0.26/0.20 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
