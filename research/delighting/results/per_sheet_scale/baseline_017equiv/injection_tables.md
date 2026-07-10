
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

### design = continuous_persheet

| recipe (oracle) | as opalescent | as wispy | as cathedral-clear | as dark-opaque |
|---|---|---|---|---|
| cathedral-amber (cathedral-clear) | 0.200 (1.00x) | 0.214 (1.15x) | 0.146 (0.97x) * | 0.185 (0.75x) |
| cathedral-green (cathedral-clear) | 0.210 (1.01x) | 0.269 (1.18x) | 0.144 (1.01x) * | 0.191 (0.68x) |
| dark-deep (dark-opaque) | 0.051 (2.05x) | 0.053 (2.08x) | 0.048 (2.07x) | 0.048 (2.08x) * |
| dark-opaque (dark-opaque) | 0.150 (1.61x) | 0.158 (1.75x) | 0.127 (1.57x) | 0.051 (0.81x) * |
| dark-ruby (dark-opaque) | 0.057 (2.15x) | 0.060 (2.27x) | 0.030 (1.67x) | 0.042 (1.90x) * |
| dark-slate (dark-opaque) | 0.079 (0.73x) | 0.058 (0.81x) | 0.109 (0.67x) | 0.152 (0.50x) * |
| streaky-mix (wispy) | 0.198 (0.85x) | 0.136 (1.02x) * | 0.246 (0.83x) | 0.398 (0.51x) |
| wispy-white (wispy) | 0.159 (0.82x) | 0.122 (0.89x) * | 0.167 (0.89x) | 0.298 (0.70x) |

### summary: mean T_mae (mean lum-ratio error)

| design | correct class | wrong class | worst wrong-class lum-ratio |
|---|---|---|---|
| class | 0.107 | 0.448 | 17.08x |
| continuous | 0.103 | 0.190 | 3.90x |
| continuous_persheet | 0.098 | 0.161 | 3.30x |
