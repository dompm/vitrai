# Report 027 - Curl plus a weak material mean prior collapses the T/B gauge

Date: 2026-07-10. Code: `differentiable_sheet_curl_scale_prior.py`.

## 0. Why this follows reports 023-026

The renderer sequence has been circling one core ambiguity:

```text
observed = T * (ambient + leak * warped_background)
```

Many wrong pairs of `T` and `B` reconstruct the same observation:

```text
T dark, B bright
T bright, B dark
```

Reports 023-026 attacked the geometry side:

- report 023: known motion reduced background leakage;
- report 024: hard height-field `D` was promising but brittle;
- report 025: projecting free-flow `D` into height helped modestly;
- report 026: curl-regularized free-flow gave the strongest non-oracle
  geometric/material result so far.

But even report 026 still sat near:

```text
T MAE ~0.099
```

The suspicion was that geometry was no longer the main blocker. The remaining
error was the material scale/color gauge.

This report tests that directly.

## 1. Question

If we keep the best current non-oracle renderer:

```text
two-frame known motion
+ shared unknown B
+ curl-regularized D
```

and add a weak prior on the mean material transmittance, does `T` become
identifiable?

This is not meant to be a final product prior. It is an identifiability
experiment:

```text
If a weak mean prior collapses the error, then the renderer path is missing a
scale/color anchor, not a totally different decomposition.
```

## 2. Method

Same synthetic setup:

```text
obs_i(x) = T(x) * (ambient + leak * sample(B, x + D(x) + shift_i))
```

with:

```text
shift_0 = (0, 0)
shift_1 = (19, -11) px
curl_weight = 0.30
```

The base method is report 026's curl-regularized optimizer.

The new loss term is:

```text
prior_weight * prior_loss(mean(T), target)
```

where `prior_weight = 0.25`.

## 3. Prior variants

### 3.1 none

No material mean prior. This is the curl-only baseline.

### 3.2 luma-oracle

The optimizer gets only the true mean luminance of the material:

```text
target = mean(luma(T_truth))
```

It does not get true RGB/chroma.

This tests whether a scalar brightness anchor is enough.

### 3.3 rgb-oracle

The optimizer gets the true mean RGB material transmittance:

```text
target = mean_rgb(T_truth)
```

This is an oracle ceiling for a class/catalog/user prior that predicts sheet
mean color accurately.

### 3.4 rgb-bright-biased

The optimizer gets a deliberately too-bright RGB prior:

```text
target = mean_rgb(T_truth) * [1.20, 1.12, 1.16]
```

This asks whether a wrong but nearby prior still helps.

### 3.5 rgb-chroma-biased

The optimizer gets a deliberately chroma-biased RGB prior:

```text
target = mean_rgb(T_truth) * [1.35, 0.92, 1.20]
```

This tests sensitivity to hue/class error.

## 4. Sweep

Four seeds:

| parameter | value |
|---|---:|
| ambient | 0.12 |
| leak | 0.88 |
| max displacement | 10 px |
| image size | 144 px |
| shift | `(19, -11)` px |
| seeds | 81, 82, 83, 84 |
| curl weight | 0.30 |
| prior weight | 0.25 |

Outputs:

- `results/differentiable_sheet_curl_scale_prior_sweep/sweep_summary.md`
- `results/differentiable_sheet_curl_scale_prior_sweep/sweep_metrics.json`
- `results/differentiable_sheet_curl_scale_prior_sweep/seed81/contact.jpg`

## 5. Result

| method | T MAE mean | T MAE std | B MAE mean | recon MAE mean | preview CV mean | T-bg corr mean | disp EPE mean | mean RGB MAE | mean luma abs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 0.0981 | 0.0033 | 0.1525 | 0.0023 | 0.149 | 0.013 | 2.49 | 0.0977 | 0.1895 |
| luma-oracle | 0.0169 | 0.0014 | 0.0491 | 0.0022 | 0.067 | -0.026 | 2.37 | 0.0074 | 0.0012 |
| rgb-oracle | 0.0136 | 0.0006 | 0.0381 | 0.0021 | 0.073 | -0.044 | 2.45 | 0.0008 | 0.0013 |
| rgb-bright-biased | 0.0316 | 0.0008 | 0.0567 | 0.0022 | 0.066 | 0.096 | 2.45 | 0.0306 | 0.0497 |
| rgb-chroma-biased | 0.0291 | 0.0006 | 0.0677 | 0.0022 | 0.079 | -0.047 | 2.46 | 0.0271 | 0.0286 |

This is a large effect.

Against no prior:

- luma oracle: `T MAE 0.0981 -> 0.0169`;
- RGB oracle: `T MAE 0.0981 -> 0.0136`;
- bright-biased RGB: `T MAE 0.0981 -> 0.0316`;
- chroma-biased RGB: `T MAE 0.0981 -> 0.0291`.

`B` also improves sharply:

- no prior: `B MAE 0.1525`;
- RGB oracle: `B MAE 0.0381`;
- biased priors: `B MAE ~0.057-0.068`.

Reconstruction does not get worse:

```text
recon MAE stays around 0.0021-0.0023
```

That is the key identifiability result. The wrong and right factorizations both
reconstruct the observations; the weak material prior selects the physically
correct gauge.

## 6. Visual read

See:

```text
results/differentiable_sheet_curl_scale_prior_sweep/seed81/contact.jpg
```

The visual result is subtler than the metric headline.

The no-prior `T` is globally too dark/wrong. The prior versions move `T` much
closer to the clean green material.

But the amplified error tile still shows remaining local texture/detail
mismatch. The prior fixes the global gauge; it does not magically infer every
fine material fluctuation or relief detail.

That distinction matters:

```text
scale/color gauge: mostly solved by mean prior
fine texture/detail: still open
```

## 7. Interpretation

This is the cleanest answer so far to the renderer bet.

Reports 023-026 showed that geometry constraints are necessary:

```text
known motion
+ curl-regularized displacement
```

Report 027 shows they are not sufficient:

```text
without material mean prior: T MAE ~0.098
with weak material mean prior: T MAE ~0.014-0.017 oracle, ~0.03 biased
```

The inverse problem is not failing because the renderer cannot represent the
truth. It is failing because the renderer has a gauge freedom. Once the gauge is
anchored, the same optimizer recovers dramatically better `T` and `B`.

This explains why report 023's known motion helped leakage but left `T` globally
biased. It had information about motion, not absolute material scale.

It also explains why report 026's curl regularization helped but plateaued. It
made `D` more physical, but still did not decide how bright/colorful the glass
itself should be.

## 8. Why the biased priors matter

The oracle prior is not product-realistic. The biased priors are the more useful
stress test.

Even when the prior is wrong:

```text
T MAE ~0.03 instead of ~0.098
```

That means the prior does not have to be perfect to be valuable. It only has to
land in the right part of material-color space.

This is where manufacturer catalog data becomes relevant. Not as a cleanup
model, and not as an automatic truth source, but as a weak distribution over
expected sheet mean transmittance/chroma for a given glass family or detected
swatch.

The product-facing version might eventually be:

```text
sheet image + catalog/class prior + user override
```

but the research result is simpler:

```text
the inverse renderer needs a mean material anchor.
```

## 9. Relationship to the main team work

This high-risk track started by trying not to simply reproduce the classical
anchor work.

The result is funny but useful:

```text
the bold neural/inverse-rendering path still needs an anchor.
```

The difference is that the anchor is not the whole algorithm. It is the gauge
fix inside a richer renderer:

```text
motion + background + curl/refraction + material mean prior
```

That combination is much more ambitious than copying pixels or applying a smooth
field correction.

## 10. What is still unsolved

### 10.1 Fine material texture

The amplified error tiles still show local mismatch. Mean color does not recover
all true wisps, streaks, or local density variation.

### 10.2 Real prior source

Oracle mean RGB is not available in real uploads. Need a real prior source:

- catalog/manufacturer swatch statistics;
- class-conditioned synthetic prior;
- user-selected glass family;
- repeated sheet uploads;
- calibration capture;
- learned prior with uncertainty.

### 10.3 Prior confidence

A wrong prior still helps here, but a badly wrong prior could force the material
to the wrong family. The product/research system needs uncertainty:

```text
strong prior when confident
weak prior when unknown
user-visible override when ambiguous
```

### 10.4 Single-image case

This report still uses two known-shift observations. The final product may often
have one uploaded sheet photo. The renderer path now has a target, but the
capture assumptions are not solved.

## 11. Decision

The current best high-risk renderer recipe is:

```text
two-frame known/estimated motion
+ shared unknown background B
+ curl-regularized displacement D
+ weak mean material transmittance/color prior
```

This is the first result in the sequence that looks like a real path to
delighting transmissive textured glass, not just making a prettier cleanup.

Promote the material mean prior from "nice to have" to required for the renderer
track.

## 12. Next experiments

### 12.1 Replace oracle prior with catalog-derived prior

Use the scraped manufacturer corpus to estimate plausible mean RGB/luma for glass
families or nearest visual neighbors. Then rerun this exact experiment with:

```text
catalog prior mean
catalog prior uncertainty
```

The goal is not to trust catalog images blindly. It is to test whether a noisy
real-world prior lands close enough to the useful biased-prior regime.

### 12.2 Prior uncertainty sweep

Vary `prior_weight` and prior error magnitude. Find the region where wrong priors
still help and the region where they damage material identity.

### 12.3 Combine with curl-to-height projection

Now that curl-regularized `D` is cleaner, report 025's projection may work better
as a post-process:

```text
curl D + mean prior -> integrable projection -> height refinement
```

This could move from a good displacement field toward a renderable relief map.

### 12.4 Test harder material families

This synthetic material is green cathedral-like glass. Repeat with:

- amber;
- dark glass;
- milky/opal glass;
- streaky chroma mixtures;
- stronger background contrast.

The prior may be most important for dark glass, where scale errors become very
visible in the final preview.

## 13. Files

- `differentiable_sheet_curl_scale_prior.py`
- `results/differentiable_sheet_curl_scale_prior_sweep/sweep_summary.md`
- `results/differentiable_sheet_curl_scale_prior_sweep/sweep_metrics.json`
- `results/differentiable_sheet_curl_scale_prior_sweep/seed81/contact.jpg`
