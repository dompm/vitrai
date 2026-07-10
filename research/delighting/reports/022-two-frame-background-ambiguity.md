# Report 022 - Two frames alone do not break the background ambiguity

Date: 2026-07-10. Code: `differentiable_sheet_twoframe.py`.

## 0. Question

Report 021 found a clean split:

- if the background `B` is known, optimizing `T + displacement D` works well;
- if `B` is learned from one image, the renderer reconstructs the image but
  recovered `T` remains contaminated.

The obvious next idea is:

```text
take two observations of the same sheet over different backgrounds
share T and D
learn per-frame B1 and B2
```

If the same `T,D` must explain two different observations, maybe the optimizer
can no longer hide background structure inside `T`.

This report tests that idea.

## 1. Setup

The renderer is the same as report 021:

```text
obs_i(x) = T(x) * (ambient + leak * sample(B_i, x + D(x)))
```

Synthetic ground truth:

- one shared clean material map `T`;
- one shared displacement field `D`;
- two different backgrounds `B1`, `B2`;
- two observations `obs1`, `obs2`.

`B2` is not just a tiny perturbation. It is shifted, tinted, and given a diagonal
dark structure so the two frames contain distinct background evidence.

## 2. Methods

### 2.1 Single-frame learned B

Run the report-021 learned-background optimizer independently on frame 1 and
frame 2.

For comparison, the reported `T` is from frame 1. This is the baseline that
already failed in report 021.

### 2.2 Two-frame shared T,D learned B

Optimize:

```text
shared low-resolution T
shared displacement D
per-frame backgrounds B1, B2
```

Loss:

```text
reconstruct obs1 + reconstruct obs2
+ smoothness priors on T, B1, B2, D
```

The expectation: shared `T,D` should be harder to corrupt because two different
backgrounds must agree on the same material.

## 3. Sweep

I ran four seeds at a default hard-ish setting:

| parameter | value |
|---|---:|
| ambient | 0.12 |
| leak | 0.88 |
| max displacement | 10 px |
| image size | 144 px |
| seeds | 31, 32, 33, 34 |

Results live in:

- `results/differentiable_sheet_twoframe_sweep/sweep_summary.md`
- `results/differentiable_sheet_twoframe_sweep/sweep_metrics.json`
- `results/differentiable_sheet_twoframe_sweep/seed31/contact.jpg`

## 4. Result

| method | T MAE mean | T MAE std | B MAE mean | preview CV mean | disp EPE mean |
|---|---:|---:|---:|---:|---:|
| single-frame learned B | 0.1161 | 0.0003 | 0.2000 | 0.102 | 3.52 |
| two-frame shared T,D learned B | 0.1128 | 0.0006 | 0.1965 | 0.106 | 3.39 |

Two frames help only a little:

- `T MAE` improves by about 3%;
- `B MAE` improves by about 2%;
- displacement improves slightly;
- preview CV is slightly worse.

This is not the breakthrough.

## 5. Visual read

`results/differentiable_sheet_twoframe_sweep/seed31/contact.jpg` is the clearest
view.

What it shows:

- ground-truth `T` is a clean green material field;
- observations contain warped window/diagonal background structure;
- single-frame learned `B` absorbs a glass/background mixture;
- two-frame learned `B1/B2` are slightly more coherent but still contaminated;
- two-frame `T` remains too dark and not clean enough.

The optimizer uses the extra frame to improve reconstruction and background
slightly, but not enough to identify the true factorization.

## 6. Why two frames were not enough

The factorization remains too flexible:

```text
T * warped(B1) and T * warped(B2)
```

Even with shared `T,D`, per-frame `B_i` can adapt to whatever structure the
shared material fails to explain. Because both `T` and `B_i` are images with
smoothness priors, the optimizer still finds a visually plausible but physically
wrong division of responsibility.

The issue is not that two-frame is a bad idea. The issue is that this two-frame
version has no strong prior saying:

```text
B_i should look like a plausible background,
T should look like a plausible glass sheet,
D should look like plausible rolled-glass relief
```

Smoothness alone is not enough.

## 7. Interpretation

Report 021 gave a positive oracle result:

```text
known B + learned D -> clean T
```

Report 022 gives a negative identifiability result:

```text
two unknown B_i + shared T,D -> still ambiguous
```

Together they are more useful than either alone:

- explicit `B,D` is the right representation;
- the inference problem needs extra information;
- extra frames may help, but only with stronger priors or constraints.

## 8. What to try next

### 8.1 Known-pattern or semi-known background

A cutting mat, calibration grid, printed checker, or light-table pattern could
make `B` partially known. Report 021 says that once `B` is known, the
displacement representation works.

### 8.2 Background prior

Use a pretrained image prior or a small learned prior for `B_i`. The optimizer
should not be free to make `B` look like tinted glass texture.

### 8.3 Relief prior

Parameterize `D` as gradients of a height field instead of arbitrary 2D flow.
The current displacement map can form unnatural line-following fields. A
height-derived normal/displacement prior may reduce the factorization freedom.

### 8.4 Multi-frame with motion model

Instead of two unrelated backgrounds, model the second frame as a known or
estimated sheet/background shift:

```text
same B, shifted sheet, shared T,D
```

That may provide stronger correspondence constraints than two independent
backgrounds.

## 9. Decision

Do not claim two captures solve the problem.

Claim this instead:

```text
The renderer representation is validated under oracle B, but unknown B remains
ambiguous even with two frames unless B/D/T get stronger priors or motion
constraints.
```

This is still the right high-risk direction. The next experiment should make
one variable less free:

- known/semi-known `B`;
- height-field-constrained `D`;
- background natural-image prior;
- or a motion model tying the two frames together.

## 10. Files

- `differentiable_sheet_twoframe.py`
- `results/differentiable_sheet_twoframe_sweep/sweep_summary.md`
- `results/differentiable_sheet_twoframe_sweep/sweep_metrics.json`
- `results/differentiable_sheet_twoframe_sweep/seed31/contact.jpg`
