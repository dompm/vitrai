
### design = class

| recipe (oracle) | as opalescent | as wispy | as cathedral-clear | as dark-opaque |
|---|---|---|---|---|
| cathedral-amber (cathedral-clear) | 0.200 (1.00x) | 0.214 (1.15x) | 0.146 (0.97x) * | 0.507 (0.20x) |
| cathedral-green (cathedral-clear) | 0.210 (1.01x) | 0.269 (1.18x) | 0.144 (1.01x) * | 0.439 (0.21x) |
| dark-deep (dark-opaque) | 0.700 (15.21x) | 0.761 (16.46x) | 0.717 (16.38x) | 0.112 (3.45x) * |
| dark-opaque (dark-opaque) | 0.482 (3.29x) | 0.574 (3.83x) | 0.474 (3.51x) | 0.058 (0.74x) * |
| dark-ruby (dark-opaque) | 0.569 (12.89x) | 0.642 (14.48x) | 0.524 (10.66x) | 0.061 (2.24x) * |
| dark-slate (dark-opaque) | 0.426 (2.45x) | 0.525 (2.88x) | 0.427 (2.38x) | 0.152 (0.50x) * |
| streaky-mix (wispy) | 0.198 (0.85x) | 0.136 (1.02x) * | 0.246 (0.83x) | 0.632 (0.17x) |
| wispy-white (wispy) | 0.159 (0.82x) | 0.122 (0.89x) * | 0.167 (0.89x) | 0.720 (0.19x) |

### design = continuous

| recipe (oracle) | as opalescent | as wispy | as cathedral-clear | as dark-opaque |
|---|---|---|---|---|
| cathedral-amber (cathedral-clear) | 0.200 (1.00x) | 0.214 (1.15x) | 0.146 (0.97x) * | 0.197 (0.73x) |
| cathedral-green (cathedral-clear) | 0.207 (1.01x) | 0.256 (1.16x) | 0.139 (0.99x) * | 0.214 (0.64x) |
| dark-deep (dark-opaque) | 0.053 (2.08x) | 0.054 (2.11x) | 0.049 (2.10x) | 0.050 (2.13x) * |
| dark-opaque (dark-opaque) | 0.199 (1.79x) | 0.225 (2.02x) | 0.178 (1.76x) | 0.069 (1.00x) * |
| dark-ruby (dark-opaque) | 0.070 (2.46x) | 0.074 (2.59x) | 0.044 (1.91x) | 0.043 (1.90x) * |
| dark-slate (dark-opaque) | 0.163 (1.19x) | 0.148 (1.26x) | 0.180 (1.13x) | 0.125 (0.65x) * |
| streaky-mix (wispy) | 0.219 (0.80x) | 0.160 (0.95x) * | 0.274 (0.76x) | 0.429 (0.47x) |
| wispy-white (wispy) | 0.159 (0.82x) | 0.122 (0.89x) * | 0.167 (0.89x) | 0.312 (0.68x) |

### design = continuous_oldfit

| recipe (oracle) | as opalescent | as wispy | as cathedral-clear | as dark-opaque |
|---|---|---|---|---|
| cathedral-amber (cathedral-clear) | 0.200 (1.00x) | 0.214 (1.15x) | 0.146 (0.97x) * | 0.198 (0.73x) |
| cathedral-green (cathedral-clear) | 0.206 (1.00x) | 0.254 (1.16x) | 0.138 (0.99x) * | 0.218 (0.63x) |
| dark-deep (dark-opaque) | 0.118 (3.39x) | 0.120 (3.44x) | 0.111 (3.42x) | 0.112 (3.45x) * |
| dark-opaque (dark-opaque) | 0.207 (1.90x) | 0.233 (2.12x) | 0.182 (1.86x) | 0.064 (0.99x) * |
| dark-ruby (dark-opaque) | 0.105 (3.41x) | 0.112 (3.59x) | 0.083 (2.64x) | 0.061 (2.24x) * |
| dark-slate (dark-opaque) | 0.135 (1.24x) | 0.115 (1.32x) | 0.155 (1.17x) | 0.125 (0.62x) * |
| streaky-mix (wispy) | 0.218 (0.81x) | 0.159 (0.95x) * | 0.272 (0.76x) | 0.433 (0.46x) |
| wispy-white (wispy) | 0.159 (0.82x) | 0.122 (0.89x) * | 0.167 (0.89x) | 0.310 (0.68x) |

### summary: mean T_mae (mean lum-ratio error)

| design | correct class | wrong class | worst wrong-class lum-ratio |
|---|---|---|---|
| class | 0.107 | 0.448 | 17.08x |
| continuous | 0.103 | 0.190 | 3.90x |
| continuous_oldfit | 0.109 | 0.198 | 4.15x |
