
### design = class

| recipe (oracle) | as opalescent | as wispy | as cathedral-clear | as dark-opaque |
|---|---|---|---|---|
| cathedral-amber (cathedral-clear) | 0.200 (1.00x) | 0.214 (1.15x) | 0.146 (0.97x) * | 0.507 (0.20x) |
| cathedral-green (cathedral-clear) | 0.210 (1.01x) | 0.269 (1.18x) | 0.144 (1.01x) * | 0.439 (0.21x) |
| dark-opaque (dark-opaque) | 0.482 (3.29x) | 0.574 (3.83x) | 0.474 (3.51x) | 0.058 (0.74x) * |
| streaky-mix (wispy) | 0.198 (0.85x) | 0.136 (1.02x) * | 0.246 (0.83x) | 0.632 (0.17x) |
| wispy-white (wispy) | 0.159 (0.82x) | 0.122 (0.89x) * | 0.167 (0.89x) | 0.720 (0.19x) |

### design = continuous

| recipe (oracle) | as opalescent | as wispy | as cathedral-clear | as dark-opaque |
|---|---|---|---|---|
| cathedral-amber (cathedral-clear) | 0.200 (1.00x) | 0.214 (1.15x) | 0.146 (0.97x) * | 0.198 (0.73x) |
| cathedral-green (cathedral-clear) | 0.206 (1.00x) | 0.254 (1.16x) | 0.138 (0.99x) * | 0.218 (0.63x) |
| dark-opaque (dark-opaque) | 0.207 (1.90x) | 0.233 (2.12x) | 0.182 (1.86x) | 0.064 (0.99x) * |
| streaky-mix (wispy) | 0.218 (0.81x) | 0.159 (0.95x) * | 0.272 (0.76x) | 0.433 (0.46x) |
| wispy-white (wispy) | 0.159 (0.82x) | 0.122 (0.89x) * | 0.167 (0.89x) | 0.310 (0.68x) |

### summary: mean T_mae (mean lum-ratio error)

| design | correct class | wrong class | worst wrong-class lum-ratio |
|---|---|---|---|
| class | 0.107 | 0.399 | 9.73x |
| continuous | 0.112 | 0.226 | 3.80x |
