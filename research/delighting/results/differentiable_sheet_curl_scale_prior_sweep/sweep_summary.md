# Curl + material prior inverse sweep

| method | T MAE mean | T MAE std | B MAE mean | recon MAE mean | preview CV mean | T-bg corr mean | disp EPE mean | mean RGB MAE | mean luma abs | n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 0.0981 | 0.0033 | 0.1525 | 0.0023 | 0.149 | 0.013 | 2.49 | 0.0977 | 0.1895 | 4 |
| luma-oracle | 0.0169 | 0.0014 | 0.0491 | 0.0022 | 0.067 | -0.026 | 2.37 | 0.0074 | 0.0012 | 4 |
| rgb-oracle | 0.0136 | 0.0006 | 0.0381 | 0.0021 | 0.073 | -0.044 | 2.45 | 0.0008 | 0.0013 | 4 |
| rgb-bright-biased | 0.0316 | 0.0008 | 0.0567 | 0.0022 | 0.066 | 0.096 | 2.45 | 0.0306 | 0.0497 | 4 |
| rgb-chroma-biased | 0.0291 | 0.0006 | 0.0677 | 0.0022 | 0.079 | -0.047 | 2.46 | 0.0271 | 0.0286 | 4 |