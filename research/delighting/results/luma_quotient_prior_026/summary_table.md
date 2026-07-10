# Luma quotient prior summary

Deterministic low-frequency luminance quotient. Preserves uploaded chroma and high-frequency relief.

## Position sensitivity

| condition | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| raw | 8.98 | 0.407 | 1.5 |
| fixed T/h | 9.30 | 0.306 | 1.2 |
| luma quotient a=0.25 | 7.36 | 0.245 | 1.1 |
| luma quotient a=0.50 | 5.59 | 0.180 | 1.2 |
| luma quotient a=0.75 | 3.80 | 0.113 | 1.1 |
| luma quotient a=1.00 | 2.38 | 0.051 | 1.1 |
| hand sheet prior | 1.97 | 0.059 | 0.3 |

## Neural comparison

| model after fixed `T/h` | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| luma neural | 9.34 | 0.291 | 1.7 |
| RGB smooth neural | 9.24 | 0.261 | 2.1 |

## Read

- This is a prior, not measured ground truth. It is plausible for hammered/cathedral sheets and dangerous for true wisps/streaks.
- If it beats the luma neural cleaner, the learned model should spend capacity on confidence/chroma/geometry rather than exposure correction.
