# Report 025 - Integrable projection gets halfway from free flow to relief

Date: 2026-07-10. Code: `differentiable_sheet_integrable_projection.py`.

## 0. Why this follows report 024

Report 024 tested a stronger physical representation for refraction:

```text
D(x) = scale * grad(H(x))
```

The result was split:

- cold-start height-field optimization was worse than free optical flow;
- oracle-initialized height-field optimization was better than free optical flow.

That says relief is a promising latent state, but not something the current
test-time optimizer can discover from noise.

So the next question is obvious:

```text
Can free flow find an easy displacement first, then be projected into a physical
height-field state without using ground truth?
```

This is the first non-oracle bridge from the expressive-but-nonphysical renderer
to a relief-first material representation.

## 1. Hypothesis

Free optical flow has two useful properties:

- it is easy to optimize;
- it can absorb local background distortion that helps reconstruct the sheet.

It also has one serious weakness:

- it can be non-integrable and locally arbitrary in a way a real glass surface is
  not.

A real height field has no arbitrary curl. If we project the fitted flow onto the
closest integrable field, we may keep the useful refractive component while
discarding some nonphysical background-edge overfit.

The optimistic hypothesis:

```text
free-flow D -> integrable projection -> height-field refinement
beats free-flow D on T/B recovery and leakage.
```

The pessimistic hypothesis:

```text
free-flow D is already contaminated by background bars.
Projection just turns that contamination into a plausible-looking height map.
```

Both are plausible. The contact sheets are especially important here.

## 2. Method

Same renderer and capture setup as reports 023-024:

```text
obs_i(x) = T(x) * (ambient + leak * sample(B, x + D(x) + shift_i))
```

with two known shifts:

```text
shift_0 = (0, 0)
shift_1 = (19, -11) px
```

The experiment has three methods.

### 2.1 Two-frame free-flow D

Baseline from report 023:

```text
learn T
learn B
learn free 2-channel D
```

### 2.2 Height-field from projected free-flow

A staged method:

```text
1. learn free-flow D_free
2. solve H_proj = argmin_H ||grad(H) - D_free||^2
3. initialize height-field optimizer from H_proj
4. refine T, B, H, and global refraction scale
```

The projection is solved in the Fourier domain as a least-squares periodic
Poisson problem. It keeps the curl-free component of `D_free` and discards
non-integrable flow.

This method does not use ground-truth height.

### 2.3 Oracle-height init

Same control as report 024:

```text
initialize H from height_truth
initialize scale from best fit to D_truth
refine T, B, H, scale
```

This is still unfair. It gives an upper bound for what a good relief initializer
might unlock.

## 3. Sweep

Four seeds:

| parameter | value |
|---|---:|
| ambient | 0.12 |
| leak | 0.88 |
| max displacement | 10 px |
| image size | 144 px |
| shift | `(19, -11)` px |
| seeds | 61, 62, 63, 64 |

Outputs:

- `results/differentiable_sheet_integrable_projection_sweep/sweep_summary.md`
- `results/differentiable_sheet_integrable_projection_sweep/sweep_metrics.json`
- `results/differentiable_sheet_integrable_projection_sweep/seed61/contact.jpg`

## 4. Result

| method | T MAE mean | T MAE std | B MAE mean | preview CV mean | T-bg corr mean | disp EPE mean | height corr mean | scale mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| two-frame free-flow D | 0.1026 | 0.0016 | 0.1703 | 0.133 | 0.111 | 3.55 | 0.000 | 0.00 |
| height-field from projected free-flow | 0.1017 | 0.0022 | 0.1634 | 0.144 | 0.084 | 3.01 | 0.340 | 1.60 |
| height-field oracle init | 0.0985 | 0.0031 | 0.1493 | 0.145 | 0.064 | 2.36 | 0.778 | 1.84 |

Projected free-flow improves several metrics:

- `T MAE`: `0.1026 -> 0.1017` (small);
- `B MAE`: `0.1703 -> 0.1634` (clearer);
- `T-bg high-frequency correlation`: `0.111 -> 0.084`;
- `disp EPE`: `3.55 px -> 3.01 px`;
- recovered height correlation becomes nonzero: `0.340`.

But it does not reach oracle height:

- oracle `T MAE`: `0.0985`;
- oracle `B MAE`: `0.1493`;
- oracle `disp EPE`: `2.36 px`;
- oracle height correlation: `0.778`.

So the projection is not a breakthrough. It is a bridge.

## 5. Visual read

See:

```text
results/differentiable_sheet_integrable_projection_sweep/seed61/contact.jpg
```

The projected-height method:

- removes some of the most arbitrary free-flow speckle;
- produces a smoother, more surface-like displacement map;
- slightly cleans the material/background split;
- still inherits visible structure from the original free-flow fit.

The projected height is not clean glass relief. It has large blobs and some
scene-correlated shapes. That means the pessimistic hypothesis is partly true:
if free flow is contaminated, its integrable projection is contaminated too.

The oracle-height control is still visibly better. It keeps the height map closer
to the true relief and gives a cleaner background/material split.

## 6. Interpretation

Report 024 said:

```text
height-field is a good state but a bad cold start
```

Report 025 refines that:

```text
free-flow projection is a usable non-oracle warm start, but too weak to close the
gap to real relief.
```

This matters because it suggests a staged inverse renderer is viable:

```text
easy expressive fit
-> physical projection
-> constrained refinement
```

That is more promising than optimizing height from noise, and more physical than
leaving arbitrary flow in the final material state.

However, the material win is small. The biggest improvements are geometric and
leakage-adjacent:

- lower displacement error;
- lower `T` correlation with background;
- better `B` recovery.

The absolute `T` error barely moves. That is consistent with the earlier
diagnosis: motion and relief help separate geometry/background leakage, but they
do not fix the global transmittance/color scale ambiguity.

## 7. What this supports

This supports a renderer architecture where `D_free` is not the final material
state. It is an intermediate optimizer variable.

A plausible pipeline:

```text
1. Fit free T/B/D to get an easy reconstruction.
2. Decompose/project D into a physical relief component.
3. Refit T/B with D constrained by relief.
4. Apply a material scale/color prior.
5. Distill the whole process into a feed-forward model only after the optimizer
   produces good states.
```

That path feels more like neural inverse rendering than image cleanup. Good. That
is the lane this intern track is supposed to occupy.

## 8. What this does not support

It does not support shipping a height map inferred by plain projection and
pretending it is measured glass relief.

The height correlation is only `0.340`. The projected map is useful, but it is
not faithful enough to be treated as ground truth.

It also does not support spending much effort polishing the current projection
as if it will solve material recovery alone. The remaining `T` error is too
large, and the preview CV remains higher than free flow.

## 9. Next bets

### 9.1 Add an integrability/curl penalty during free-flow optimization

Instead of:

```text
fit free flow, then project it
```

try:

```text
fit D with a soft curl penalty
```

This may keep the optimization easy while discouraging nonphysical local flow
before contamination becomes baked in.

### 9.2 Robust projection

The current projection trusts every free-flow vector equally. A better version
should downweight vectors near high-contrast background edges, where free flow is
most likely to be explaining scene structure instead of glass relief.

Possible weights:

- high residual uncertainty;
- high background-gradient regions;
- high disagreement across shifted frames;
- low confidence in the material/background split.

### 9.3 Relief prior

Projection only enforces integrability. It does not know what manufactured glass
relief looks like. A learned prior over `H` or normals could push projected
height away from scene bars and toward rolled-glass statistics.

This is where synthetic Blender relief and scraped catalog texture may become
useful, but only if the target is relief plausibility rather than luma cleanup.

### 9.4 Add material scale/color prior

The geometric improvements are now real but small. To move `T MAE`, pair this
with the scale/color prior that report 023 already asked for.

The next serious test should probably be:

```text
motion + projected/integrable relief + material scale prior
```

## 10. Decision

Keep the staged projection path.

Do not expect it to solve delighting alone.

The next high-risk renderer direction should be one of:

```text
free-flow with curl/integrability regularization
```

or:

```text
projected relief + material scale prior
```

My current preference is the curl-regularized free-flow experiment. It directly
tests whether the useful part of projection can be baked into the optimizer
instead of bolted on afterward.

## 11. Files

- `differentiable_sheet_integrable_projection.py`
- `results/differentiable_sheet_integrable_projection_sweep/sweep_summary.md`
- `results/differentiable_sheet_integrable_projection_sweep/sweep_metrics.json`
- `results/differentiable_sheet_integrable_projection_sweep/seed61/contact.jpg`
