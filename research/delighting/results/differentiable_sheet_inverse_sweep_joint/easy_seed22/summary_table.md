# Differentiable sheet inverse summary

Synthetic known-ground-truth test for explicit background/refraction representation.

| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw RGB trap | 0.0069 | 0.1528 | 0.8104 | 0.180 | 0.981 | 1.75 | 0.00/0.00 |
| low-T/no-displacement (known B) | 0.0046 | 0.0070 | 0.0000 | 0.068 | 0.136 | 1.75 | 0.00/0.00 |
| low-T + displacement (known B) | 0.0017 | 0.0053 | 0.0000 | 0.065 | 0.051 | 1.27 | 0.73/0.56 |
| low-T + displacement + learned B | 0.0011 | 0.1037 | 0.2402 | 0.090 | 0.331 | 1.97 | 0.10/-0.00 |

Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.
The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.
