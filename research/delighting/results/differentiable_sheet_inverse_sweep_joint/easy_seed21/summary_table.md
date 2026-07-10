# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0069 | 0.1518 | 0.8113 | 0.157 | 0.979 | 1.67 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0044 | 0.0063 | 0.0000 | 0.067 | 0.108 | 1.67 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0018 | 0.0051 | 0.0000 | 0.066 | 0.069 | 1.24 | 0.69/0.49 |
| low-T + displacement + learned B | 0.0011 | 0.1042 | 0.2481 | 0.075 | 0.214 | 1.72 | 0.40/0.01 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
