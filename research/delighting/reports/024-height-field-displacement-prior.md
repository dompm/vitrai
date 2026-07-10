# Report 024 - Height-field displacement is a good state, but a bad cold start

Date: 2026-07-10. Code: `differentiable_sheet_heightfield.py`.

## 0. Why this question matters

The renderer track has been using three latent variables:

```text
T(x)  clean RGB transmittance / glass color
B(x)  background or backlight image behind the sheet
D(x)  2D displacement/refraction field
```

Reports 021-023 established a useful but incomplete picture:

- with a known background, `T + D` can recover the clean material very well;
- with one unknown background, `T/B/D` is not identifiable;
- with two shifted observations over one shared unknown background, known motion
  reduces the right leakage metric but still leaves `T` globally wrong.

That leaves a representation question.

The synthetic truth in these experiments is not arbitrary optical flow. The
displacement is generated from a scalar surface relief field:

```text
D_truth(x) = scaled_gradient(height_truth(x))
```

Real rolled / hammered / cathedral glass also behaves more like a relief field
than arbitrary per-pixel flow. So the free-flow optimizer in reports 021-023 may
be too permissive: it can explain away background bars with nonphysical local
warps, then let the remaining error drift into `T` or `B`.

This report asks:

```text
Does replacing free optical flow with a height-field displacement prior improve
material recovery?
```

This is not a product safety question. It is a representation bet. If the answer
is yes, Vitrai's future material state should probably include an actual relief
map, not only a corrected texture.

## 1. Hypothesis

The optimistic hypothesis:

```text
Constrain D(x) = scale * grad(H(x)).
This removes nonphysical flow degrees of freedom.
Therefore less background structure can leak into T.
```

The pessimistic hypothesis:

```text
The height-field constraint is physically better but harder to optimize.
Cold-start test-time fitting may get stuck by interpreting background edges as
relief edges.
```

Both outcomes are useful.

If height-field wins from a cold start, the next renderer should switch away from
free flow immediately.

If height-field only wins when initialized near the true relief, then the
representation is promising but needs a relief initializer: neural prior,
integrability projection, multiframe distortion cue, structured background, or
some capture protocol.

## 2. Renderer

Same two-frame known-motion setup as report 023:

```text
obs_i(x) = T(x) * (ambient + leak * sample(B, x + D(x) + shift_i))
```

where:

```text
shift_0 = (0, 0)
shift_1 = (19, -11) px
```

The optimizer knows the shifts. It does not know `T`, `B`, or `D`.

## 3. Compared representations

### 3.1 Free-flow baseline

This is report 023's stronger two-frame method:

```text
learn T
learn B
learn D as a free 2-channel displacement field
```

The displacement field is low-resolution and regularized, but each pixel can
move independently in `x/y` after upsampling.

This is expressive and easy for the optimizer. It is also nonphysical.

### 3.2 Cold-start height-field displacement

Replace free `D` with:

```text
learn T
learn B
learn scalar H
learn global scale s
D = s * grad(H) / rms(grad(H))
```

The RMS normalization keeps height amplitude and refraction scale from becoming
a gauge ambiguity. The learned scalar `s` controls how much the sheet refracts.

This is closer to a glass sheet: a surface has one height value, and refraction
comes from local slope.

The hard part is initialization. The cold-start version initializes `H` from
small noise. It sees only the two rendered RGB observations.

### 3.3 Oracle-height initialization

This is an unfair control:

```text
initialize H from height_truth
initialize scale from the least-squares best match to D_truth
then optimize T, B, H, scale
```

This is not a deployable method. It asks a more surgical question:

```text
If the optimizer starts in the right relief basin, is height-field D actually a
better material state?
```

If oracle-height initialization cannot beat free flow, the representation itself
is suspect. If it can beat free flow, the representation is alive and the missing
piece is initialization / inference.

## 4. Sweep

Four seeds:

| parameter | value |
|---|---:|
| ambient | 0.12 |
| leak | 0.88 |
| max displacement | 10 px |
| image size | 144 px |
| shift | `(19, -11)` px |
| seeds | 51, 52, 53, 54 |

Outputs:

- `results/differentiable_sheet_heightfield_sweep/sweep_summary.md`
- `results/differentiable_sheet_heightfield_sweep/sweep_metrics.json`
- `results/differentiable_sheet_heightfield_sweep/seed51/contact.jpg`

## 5. Result

| method | T MAE mean | T MAE std | B MAE mean | preview CV mean | T-bg corr mean | disp EPE mean | height corr mean | scale mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| two-frame free-flow D | 0.1029 | 0.0019 | 0.1631 | 0.127 | 0.029 | 3.25 | 0.000 | 0.00 |
| two-frame height-field D | 0.1074 | 0.0032 | 0.1842 | 0.129 | 0.132 | 4.12 | 0.294 | 3.20 |
| two-frame height-field D oracle init | 0.0992 | 0.0021 | 0.1464 | 0.146 | 0.030 | 2.23 | 0.796 | 1.69 |

The cold-start height-field prior loses:

- `T MAE` is worse than free flow: `0.1074` vs `0.1029`;
- `B MAE` is worse: `0.1842` vs `0.1631`;
- `T-bg high-frequency correlation` is much worse: `0.132` vs `0.029`;
- displacement EPE is worse: `4.12 px` vs `3.25 px`.

The oracle-initialized height-field wins modestly but consistently:

- `T MAE` improves from `0.1029` to `0.0992`;
- `B MAE` improves from `0.1631` to `0.1464`;
- displacement EPE improves from `3.25 px` to `2.23 px`;
- recovered height correlates with truth: `0.796` mean.

Preview CV gets worse for the oracle method (`0.146` vs `0.127`). I do not read
that as a win. The oracle height state is better on material/background recovery,
but still not a finished preview representation. It may recover real material
variation that raises the patch-CV metric, or it may leave a residual scale bias.
The contact sheet matters here more than any single scalar.

## 6. Visual read

See:

```text
results/differentiable_sheet_heightfield_sweep/seed51/contact.jpg
```

The free-flow method:

- reconstructs well;
- keeps background leakage in `T` fairly low;
- but its displacement map is visually arbitrary, with edge-like fragments that
  do not look like a sheet surface.

The cold-start height-field method:

- learns a height map that visibly follows background bars;
- pushes more background structure into `B`;
- leaves more scene-correlated texture in `T`;
- looks physically constrained in name, but not in behavior.

This is the dangerous failure mode: a "physical" parameterization can still
become a background-edge detector if the inverse problem is underconstrained.

The oracle-height method:

- keeps height much closer to the true relief;
- gives the best `T` and `B` metrics in the sweep;
- reduces displacement error strongly;
- still leaves material scale/color imperfect.

So the height-field state is useful when the relief basin is known. The cold
optimizer does not discover that basin reliably from two casual observations.

## 7. Interpretation

The result is not:

```text
height-field prior solves glass delighting
```

The result is:

```text
height-field prior is a better latent state if initialized well, but a worse
test-time optimizer if initialized from noise.
```

That distinction matters.

Free flow is "wrong" physically, but it is optimization-friendly. It can cheaply
absorb whatever local warp reduces reconstruction loss. Because report 023's
known motion already suppresses high-frequency leakage, free flow does not
catastrophically contaminate `T` in this setup.

Height-field displacement is "right" physically, but the cold-start objective has
too many explanations:

```text
background edge in obs
  -> could be a dark bar in B
  -> could be refraction from H
  -> could be dark material in T
```

The optimizer often chooses a bad hybrid: it draws relief around background bars,
then leaves a worse background/material split than free flow.

This is very relevant for real uploaded glass sheets. A user photo will usually
not provide clean relief supervision. If we simply add a height-field latent and
optimize it from RGB, the model may hallucinate "glass bumps" from window frames,
tree branches, or shadows. That would look more sophisticated in the renderer
while being less physically faithful.

## 8. What this falsifies

This report falsifies a naive version of the Material-v2 ambition:

```text
Just make D integrable / height-derived and the inverse problem becomes better.
```

No. The cold-start version is worse on every core metric in this sweep.

It also falsifies a simplistic anti-physics reaction:

```text
Height-field constraints are useless; free flow is enough.
```

Also no. With oracle relief initialization, height-field D gives the best `T`,
best `B`, and best displacement recovery.

The sharper statement is:

```text
Relief is a good representation, not a free inference solution.
```

## 9. Consequence for the renderer bet

The next renderer should not replace free flow with cold-start height and call it
physics.

Instead, the next bet should be:

```text
infer or initialize relief first,
then optimize the material/background split.
```

Possible relief initializers:

### 9.1 Project free flow onto an integrable height field

Run the easy free-flow optimizer first. Then find the scalar `H` whose gradient
best matches the free-flow displacement:

```text
H_init = argmin_H || grad(H) - D_free ||^2 + smoothness(H)
```

This keeps the optimization friendliness of free flow but forces the next stage
through a physically plausible relief bottleneck. It is the most direct next
experiment because it uses information already produced by the current renderer.

### 9.2 Learn a relief prior from synthetic/catalog texture

A neural prior or score model could learn what rolled glass relief looks like:

- blobbed cathedral waviness;
- hammered pebble scale;
- wispy/opal soft structure;
- manufacturing streaks that are material, not background.

This should not be a catalog cleanup model in disguise. The target would be
relief/normal plausibility, not luma correction.

### 9.3 Use multiframe distortion cues

Known motion helped report 023 because background structure moves relative to
the sheet. Relief should also impose consistent distortion across shifted
observations. A stronger multiframe model could estimate relief by matching the
same background seen through different local slopes.

### 9.4 Use a structured capture only as a research upper bound

A checkerboard/light-table capture would make relief easy, but product capture
should not depend on it yet. Still, structured capture is valuable as a truth
source for validating the representation and training a prior.

## 10. Relationship to material scale

Report 023 said known motion reduces leakage but leaves `T` globally biased/dark.
Report 024 does not remove that scale ambiguity.

Even oracle-height initialization only improves `T MAE` from `0.1029` to
`0.0992`. That is real, but not a breakthrough. The remaining problem is still:

```text
T dark, B bright
T bright, B dark
```

The height-field prior helps separate geometric background distortion from
material texture. It does not decide the absolute color/transmittance scale.

So the full renderer stack probably needs both:

```text
relief initializer / height prior
+ material scale-color prior
+ motion-constrained shared background
```

## 11. Decision

Keep the height-field representation alive.

Do not adopt cold-start height-field optimization as the main method.

The practical next step is not "height instead of flow." It is:

```text
free-flow warm start -> integrable height projection -> height-field refinement
```

If that fails, the problem is more likely the objective / missing scale prior
than the surface-relief state itself.

## 12. Files

- `differentiable_sheet_heightfield.py`
- `results/differentiable_sheet_heightfield_sweep/sweep_summary.md`
- `results/differentiable_sheet_heightfield_sweep/sweep_metrics.json`
- `results/differentiable_sheet_heightfield_sweep/seed51/contact.jpg`
