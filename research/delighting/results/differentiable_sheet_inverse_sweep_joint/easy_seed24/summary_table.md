# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0068 | 0.1530 | 0.8124 | 0.185 | 0.981 | 1.65 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0047 | 0.0077 | 0.0000 | 0.063 | 0.215 | 1.65 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0017 | 0.0056 | 0.0000 | 0.068 | 0.124 | 1.21 | 0.67/0.62 |
| low-T + displacement + learned B | 0.0011 | 0.1053 | 0.2481 | 0.085 | 0.279 | 1.76 | 0.05/0.23 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
