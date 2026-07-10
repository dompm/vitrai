# Report 026 - Curl-regularized flow is the first strong non-oracle relief win

Date: 2026-07-10. Code: `differentiable_sheet_curl_regularized.py`.

## 0. Why this follows report 025

Report 025 tested:

```text
free-flow D -> project D to integrable height -> height-field refinement
```

That helped, but only modestly:

```text
T MAE  0.1026 -> 0.1017
B MAE  0.1703 -> 0.1634
EPE    3.55   -> 3.01
```

The projection was useful, but it happened after the free-flow optimizer had
already fit a contaminated displacement field. If the easy free-flow stage
absorbs background bars, the projection inherits those mistakes.

This report tests the more direct idea:

```text
Keep free-flow optimization, but penalize non-integrable flow while fitting.
```

In other words: do not wait until after the fit to ask for a relief-like
displacement. Make the optimizer prefer relief-like flow from the start.

## 1. Physics intuition

A scalar height field produces displacement from local slope:

```text
D(x) = scale * grad(H(x))
```

Gradient fields are curl-free:

```text
curl(D) = dD_y/dx - dD_x/dy = 0
```

Report 024 showed that hard height-field optimization from noise is too brittle.
Report 025 showed that projecting free flow onto a curl-free component helps.

So the hypothesis here is:

```text
A soft curl penalty may keep the optimization benefits of free flow while
discouraging displacement patterns that no real glass surface can produce.
```

This is a better compromise than either extreme:

- not arbitrary optical flow forever;
- not cold-start height from noise;
- not oracle relief.

## 2. Renderer

Same two-frame known-motion renderer:

```text
obs_i(x) = T(x) * (ambient + leak * sample(B, x + D(x) + shift_i))
```

with:

```text
shift_0 = (0, 0)
shift_1 = (19, -11) px
```

The optimizer learns:

```text
T
B
D as a free two-channel displacement field
```

The loss adds:

```text
lambda_curl * mean(abs(curl(D / max_disp)))
```

on top of the previous reconstruction, `T` TV, `B` TV, displacement TV,
displacement Laplacian, and displacement magnitude terms.

## 3. Sweep

Four seeds:

| parameter | value |
|---|---:|
| ambient | 0.12 |
| leak | 0.88 |
| max displacement | 10 px |
| image size | 144 px |
| shift | `(19, -11)` px |
| seeds | 71, 72, 73, 74 |
| curl weights | `0, 0.03, 0.10, 0.30` |

Outputs:

- `results/differentiable_sheet_curl_regularized_sweep/sweep_summary.md`
- `results/differentiable_sheet_curl_regularized_sweep/sweep_metrics.json`
- `results/differentiable_sheet_curl_regularized_sweep/seed71/contact.jpg`

## 4. Result

| method | curl w | recon MAE mean | T MAE mean | B MAE mean | preview CV mean | T-bg corr mean | disp EPE mean | curl abs mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| curl 0 | 0.0000 | 0.00188 | 0.1033 | 0.1675 | 0.125 | 0.045 | 3.31 | 0.04418 |
| curl 0.03 | 0.0300 | 0.00207 | 0.1011 | 0.1620 | 0.132 | 0.040 | 2.81 | 0.00886 |
| curl 0.1 | 0.1000 | 0.00222 | 0.0993 | 0.1571 | 0.143 | 0.042 | 2.69 | 0.00389 |
| curl 0.3 | 0.3000 | 0.00238 | 0.0990 | 0.1565 | 0.147 | 0.026 | 2.72 | 0.00255 |

The headline:

```text
curl 0.3 beats baseline on T, B, T-background leakage, and displacement.
```

Against baseline:

- `T MAE`: `0.1033 -> 0.0990` (~4.1% improvement);
- `B MAE`: `0.1675 -> 0.1565` (~6.6% improvement);
- `T-bg high-frequency correlation`: `0.045 -> 0.026`;
- `disp EPE`: `3.31 px -> 2.72 px`;
- `curl abs`: `0.04418 -> 0.00255`;
- reconstruction MAE worsens only from `0.00188 -> 0.00238`.

This is the strongest non-oracle result in the renderer sequence so far.

## 5. Comparison to reports 024-025

Report 024:

```text
cold height-field D        T MAE 0.1074
oracle height-field D      T MAE 0.0992
```

Report 025:

```text
projected free-flow height T MAE 0.1017
oracle height-field D      T MAE 0.0985
```

Report 026:

```text
curl-regularized free-flow T MAE 0.0990
```

This is important. Curl-regularized free flow nearly reaches the oracle-height
`T` result from report 025 without using ground-truth height.

It does not beat oracle on background recovery:

```text
report 025 oracle B MAE 0.1493
report 026 curl 0.3 B MAE 0.1565
```

But it is much closer than projected height was, and it avoids the cold-start
height failure from report 024.

## 6. Visual read

See:

```text
results/differentiable_sheet_curl_regularized_sweep/seed71/contact.jpg
```

The curl-regularized displacement maps are still free-flow maps, not explicit
height maps. They do not look as clean as a real relief field.

But as the curl penalty increases:

- displacement becomes less speckled and less arbitrary;
- the `T` error tile visibly calms down on seed 71;
- background bars remain in `B`, where they belong;
- `T` carries less scene-shaped contamination.

The curl heatmap visualization is percentile-normalized per tile, so it can look
noisy even when mean curl drops by an order of magnitude. The table is the better
read for curl magnitude.

## 7. Interpretation

The core lesson:

```text
Soft physics inside the optimizer beats hard physics from a cold start.
```

Cold-start height-field optimization was too brittle because the model had to
discover both relief structure and material/background separation at once.

After-the-fact projection helped, but it projected an already-contaminated flow.

Curl regularization changes the optimization path. It lets the renderer use a
flexible `D`, but makes nonphysical swirl expensive while the material/background
split is still forming.

That seems to be exactly the right bias for this stage of the research.

## 8. Tradeoffs

### 8.1 Reconstruction gets slightly worse

The baseline reconstructs RGB best:

```text
curl 0 recon MAE   0.00188
curl 0.3 recon MAE 0.00238
```

This is acceptable. The goal is not to recreate the contaminated capture. The
goal is to infer material state that relights well. A small reconstruction cost
is a good trade if it keeps background structure out of `T`.

### 8.2 Preview CV increases

Preview luminance CV rises:

```text
0.125 -> 0.147
```

This needs care. It could mean:

- the method preserves more real material/relief variation;
- the method introduces low-frequency material bias;
- the metric is not fully aligned with perceptual realism.

I would not call this a product win yet. It is a material-recovery win on this
synthetic test.

### 8.3 Best curl weight is not settled

`curl 0.3` is best in this small sweep for `T`, `B`, and leakage. `curl 0.1` is
close and slightly better on displacement EPE.

Do not canonize `0.3`. It is a research setting, not a tuned parameter.

## 9. Why this matters for Vitrai

The app needs glass that looks like glass after relighting, not a photo pasted
through a mask.

That means the material representation should probably include some notion of
relief/refraction. But reports 024-025 show that explicit height maps are hard to
infer directly.

Curl-regularized flow gives a more practical intermediate representation:

```text
store or distill a displacement/refraction field that is biased toward physical
surface relief, even before a full height map is reliable.
```

For the final app, this could mean:

- the right-side sheet still shows the user their actual glass image;
- the extracted material state contains `T` plus a physically biased refraction
  field;
- the assembled preview can relight/refract a controlled background more
  consistently than copied RGB;
- a later neural model can distill curl-regularized optimization into a fast
  extractor.

This stays aligned with the product vision: better realism in the stained-glass
preview, especially for hammered/cathedral textures whose "bumps" matter.

## 10. Next experiments

### 10.1 Combine curl regularization with material scale/color prior

Curl regularization attacks geometry/background leakage. It still does not
resolve the global `T dark / B bright` ambiguity.

The next best renderer test is:

```text
known motion + curl-regularized D + weak material scale/color prior
```

This directly combines the two remaining pieces identified by reports 023-026.

### 10.2 Distill curl-regularized optimization

If the optimizer keeps winning, train a small network to predict:

```text
T
B or background residual
D with low curl / relief-like structure
```

from synthetic multi-frame or single-frame inputs. The optimizer becomes a
teacher, not the final product runtime.

### 10.3 Try a mixed curl + projection pipeline

The report 025 projection may work better if the source flow is already
curl-regularized:

```text
curl-regularized D -> integrable projection -> height-field refinement
```

This could close more of the gap to oracle height without needing ground-truth
relief.

### 10.4 Evaluate on harder background statistics

The current synthetic background has window bars and colored scene structure.
Next, vary:

- background spatial frequency;
- bar thickness;
- contrast;
- displacement amplitude;
- glass darkness/transmittance.

The curl prior may help most when the background is structured enough to tempt
free flow into nonphysical fits.

## 11. Decision

Promote curl-regularized displacement to the main high-risk renderer path.

The best current non-oracle representation is not:

```text
cold height-field D
```

or:

```text
free-flow D followed by projection
```

It is:

```text
free-flow D with a soft integrability/curl prior during optimization
```

This is the first result in the sequence that feels like a genuinely bolder
renderer direction rather than a cleanup variant.

## 12. Files

- `differentiable_sheet_curl_regularized.py`
- `results/differentiable_sheet_curl_regularized_sweep/sweep_summary.md`
- `results/differentiable_sheet_curl_regularized_sweep/sweep_metrics.json`
- `results/differentiable_sheet_curl_regularized_sweep/seed71/contact.jpg`
