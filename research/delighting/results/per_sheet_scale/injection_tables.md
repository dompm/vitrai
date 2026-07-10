
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
| cathedral-amber (cathedral-clear) | 0.200 (1.00x) | 0.214 (1.15x) | 0.146 (0.97x) * | 0.203 (0.72x) |
| cathedral-green (cathedral-clear) | 0.201 (0.99x) | 0.246 (1.14x) | 0.136 (0.97x) * | 0.230 (0.61x) |
| dark-deep (dark-opaque) | 0.043 (1.88x) | 0.044 (1.91x) | 0.040 (1.90x) | 0.034 (1.74x) * |
| dark-opaque (dark-opaque) | 0.174 (1.69x) | 0.200 (1.92x) | 0.156 (1.66x) | 0.070 (0.96x) * |
| dark-ruby (dark-opaque) | 0.111 (3.50x) | 0.116 (3.63x) | 0.086 (2.68x) | 0.058 (2.19x) * |
| dark-slate (dark-opaque) | 0.164 (1.22x) | 0.149 (1.30x) | 0.180 (1.17x) | 0.126 (0.67x) * |
| streaky-mix (wispy) | 0.234 (0.78x) | 0.178 (0.92x) * | 0.290 (0.74x) | 0.434 (0.46x) |
| wispy-white (wispy) | 0.159 (0.82x) | 0.122 (0.89x) * | 0.167 (0.89x) | 0.310 (0.68x) |

### design = continuous_persheet

| recipe (oracle) | as opalescent | as wispy | as cathedral-clear | as dark-opaque |
|---|---|---|---|---|
| cathedral-amber (cathedral-clear) | 0.200 (1.00x) | 0.214 (1.15x) | 0.146 (0.97x) * | 0.188 (0.74x) |
| cathedral-green (cathedral-clear) | 0.210 (1.01x) | 0.269 (1.18x) | 0.144 (1.01x) * | 0.199 (0.66x) |
| dark-deep (dark-opaque) | 0.038 (1.78x) | 0.039 (1.81x) | 0.036 (1.80x) | 0.024 (1.53x) * |
| dark-opaque (dark-opaque) | 0.121 (1.47x) | 0.123 (1.58x) | 0.101 (1.42x) | 0.052 (0.78x) * |
| dark-ruby (dark-opaque) | 0.083 (2.94x) | 0.089 (3.09x) | 0.063 (2.27x) | 0.061 (2.24x) * |
| dark-slate (dark-opaque) | 0.067 (0.78x) | 0.045 (0.86x) | 0.098 (0.71x) | 0.152 (0.50x) * |
| streaky-mix (wispy) | 0.198 (0.85x) | 0.136 (1.02x) * | 0.246 (0.83x) | 0.398 (0.51x) |
| wispy-white (wispy) | 0.159 (0.82x) | 0.122 (0.89x) * | 0.167 (0.89x) | 0.295 (0.70x) |

### summary: mean T_mae (mean lum-ratio error)

| design | correct class | wrong class | worst wrong-class lum-ratio |
|---|---|---|---|
| class | 0.107 | 0.448 | 17.08x |
| continuous | 0.105 | 0.187 | 5.22x |
| continuous_persheet | 0.098 | 0.153 | 3.30x |
