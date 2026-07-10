# Luma quotient prior summary

Deterministic low-frequency luminance quotient. Preserves uploaded chroma and high-frequency relief.

## Position sensitivity

| condition | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| raw | 8.98 | 0.407 | 1.5 |
| fixed T/h | 10.12 | 0.318 | 1.7 |
| luma quotient a=0.25 | 8.30 | 0.255 | 1.7 |
| luma quotient a=0.50 | 6.42 | 0.189 | 1.7 |
| luma quotient a=0.75 | 4.68 | 0.120 | 1.7 |
| luma quotient a=1.00 | 3.18 | 0.056 | 1.7 |
| hand sheet prior | 1.90 | 0.060 | 0.3 |

## Neural comparison

| model after fixed `T/h` | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| luma neural | 9.34 | 0.291 | 1.7 |
| RGB smooth neural | 9.24 | 0.261 | 2.1 |

## Read

- This is a prior, not measured ground truth. It is plausible for hammered/cathedral sheets and dangerous for true wisps/streaks.
- If it beats the luma neural cleaner, the learned model should spend capacity on confidence/chroma/geometry rather than exposure correction.
