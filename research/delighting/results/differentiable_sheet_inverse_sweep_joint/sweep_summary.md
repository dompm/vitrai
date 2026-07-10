# Differentiable sheet inverse sweep

Multi-seed known-ground-truth sweep for explicit background/refraction representation.

| preset | method | T MAE mean | T MAE std | B MAE mean | preview CV mean | T-bg highfreq corr mean | disp EPE mean | n |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| default | low-T + displacement (known B) | 0.0074 | 0.0007 | 0.0000 | 0.068 | 0.127 | 1.79 | 4 |
| default | low-T + displacement + learned B | 0.1117 | 0.0012 | 0.2211 | 0.098 | 0.353 | 2.73 | 4 |
| default | low-T/no-displacement (known B) | 0.0121 | 0.0009 | 0.0000 | 0.070 | 0.259 | 2.57 | 4 |
| default | raw RGB trap | 0.1558 | 0.0007 | 0.8119 | 0.213 | 0.984 | 2.57 | 4 |
| easy | low-T + displacement (known B) | 0.0055 | 0.0003 | 0.0000 | 0.068 | 0.085 | 1.31 | 4 |
| easy | low-T + displacement + learned B | 0.1046 | 0.0007 | 0.2459 | 0.083 | 0.291 | 1.87 | 4 |
| easy | low-T/no-displacement (known B) | 0.0073 | 0.0007 | 0.0000 | 0.068 | 0.161 | 1.77 | 4 |
| easy | raw RGB trap | 0.1527 | 0.0005 | 0.8119 | 0.177 | 0.980 | 1.77 | 4 |
| hard | low-T + displacement (known B) | 0.0111 | 0.0007 | 0.0000 | 0.066 | 0.156 | 3.02 | 4 |
| hard | low-T + displacement + learned B | 0.1182 | 0.0015 | 0.1893 | 0.115 | 0.280 | 4.52 | 4 |
| hard | low-T/no-displacement (known B) | 0.0220 | 0.0016 | 0.0000 | 0.078 | 0.351 | 4.17 | 4 |
| hard | raw RGB trap | 0.1666 | 0.0008 | 0.8119 | 0.267 | 0.986 | 4.17 | 4 |

Read: compare methods within each preset. The displacement-aware optimizer should reduce T error and T-background correlation, not merely reconstruct RGB.
