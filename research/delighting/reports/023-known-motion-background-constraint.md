# Report 023 - Known motion helps background separation, but not enough

Date: 2026-07-10. Code: `differentiable_sheet_motion.py`.

## 0. Why this follows report 022

Report 022 tested two observations of the same sheet over two unrelated learned
backgrounds:

```text
obs1 = render(T, B1, D)
obs2 = render(T, B2, D)
```

Sharing `T,D` helped only marginally. The per-frame backgrounds were too free,
so the optimizer still found a wrong-but-renderable factorization.

This report tests a stronger constraint:

```text
obs1 = render(T, B, D)
obs2 = render(T, B, D + known_shift)
```

Now the background is shared. The second frame is not a random extra image; it is
a known relative motion cue. If the same background must explain two shifted
observations, maybe the optimizer can separate background structure from
material more aggressively.

## 1. Setup

Synthetic truth:

- one clean glass material `T`;
- one background `B`;
- one displacement/refraction field `D`;
- two observations with a known background sampling shift:

```text
shift0 = (0, 0)
shift1 = (19, -11) px
```

The renderer:

```text
obs_i(x) = T(x) * (ambient + leak * sample(B, x + D(x) + shift_i))
```

The optimizer knows `shift_i` but not `T`, `B`, or `D`.

## 2. Methods

### 2.1 Single-frame learned B

Same learned-background optimizer as report 021:

```text
infer T, B, D from obs1
```

This is the one-frame ambiguity baseline.

### 2.2 Two-frame shared B with known shift

Optimize:

```text
shared T
shared B
shared D
known shifts for frame 1 and frame 2
```

This is a tighter factorization than report 022 because `B` cannot be different
for each frame.

## 3. Sweep

Four seeds:

| parameter | value |
|---|---:|
| ambient | 0.12 |
| leak | 0.88 |
| max displacement | 10 px |
| image size | 144 px |
| shift | `(19, -11)` px |
| seeds | 41, 42, 43, 44 |

Results:

- `results/differentiable_sheet_motion_sweep/sweep_summary.md`
- `results/differentiable_sheet_motion_sweep/sweep_metrics.json`
- `results/differentiable_sheet_motion_sweep/seed41/contact.jpg`

## 4. Result

| method | T MAE mean | T MAE std | B MAE mean | preview CV mean | T-bg corr mean | disp EPE mean |
|---|---:|---:|---:|---:|---:|---:|
| single-frame learned B | 0.1158 | 0.0025 | 0.1957 | 0.111 | 0.337 | 3.53 |
| two-frame shared B with known shift | 0.1018 | 0.0030 | 0.1660 | 0.129 | 0.033 | 3.27 |

Known motion helps:

- `T MAE` improves by about 12%;
- `B MAE` improves by about 15%;
- displacement EPE improves slightly;
- most importantly, `T-bg high-frequency correlation` collapses from 0.337 to
  0.033.

But it does not solve the material:

- `T MAE` is still around 0.10;
- preview CV gets worse;
- recovered `T` is still globally biased/dark.

## 5. Visual read

`results/differentiable_sheet_motion_sweep/seed41/contact.jpg`

What changes:

- the motion-constrained `T` has much less visible window-bar leakage;
- the shared `B` is closer to a real background than the single-frame `B`;
- the displacement map is less line-following than the single-frame version.

What does not change enough:

- recovered `T` is still not close to the clean material;
- global color/scale ambiguity remains;
- the optimizer can still trade material darkness against background brightness.

## 6. Interpretation

Known motion is qualitatively different from report 022's unrelated two-frame
case.

Report 022:

```text
two free backgrounds -> barely improves T
```

Report 023:

```text
one shared background + known motion -> strongly reduces background leakage
```

That says motion constraints carry real information. They do not fully identify
the material, but they attack the correct failure mode: background structure
entering `T`.

## 7. Why T is still wrong

The remaining ambiguity is mostly scale/color:

```text
T dark, B bright
T bright, B dark
```

Both can reconstruct the observations. Known motion makes it harder for
high-frequency bars to live in `T`, but it does not set the absolute material
transmittance or color scale.

This connects back to the main team's anchor/scale work: even in the high-risk
renderer, material scale needs either a physical prior, a capture condition, or a
known reference.

## 8. Consequence

The next serious renderer should combine:

```text
known/estimated motion
+ shared B
+ height-field-constrained D
+ material color/scale prior
```

Known motion alone is not enough, but it is the first learned-`B` result that
meaningfully reduces the right leakage metric.

## 9. Next experiments

### 9.1 Add material scale prior

Use a weak prior on mean transmittance/color, perhaps from glass class or catalog
statistics, and see whether known motion can then recover `T` scale.

### 9.2 Constrain D as a height field

The current `D` is free optical flow. A real sheet's displacement should come
from relief/normal gradients. This may reduce line-following artifacts.

### 9.3 Estimate motion

This report assumes known shift. Next: initialize or optimize the shift. If the
motion can be estimated from the two observations, the capture requirement is
less artificial.

### 9.4 Distill after optimization

Do not train a feed-forward model yet. First make the optimizer produce good
states. Then distill.

## 10. Decision

Known motion is worth pursuing.

The hierarchy after reports 021-023:

```text
known B + D                 -> strong material recovery
two unrelated unknown B_i    -> barely helps
shared unknown B + known shift -> reduces leakage, but T scale remains wrong
```

So the next bold bet should not be "more frames" in general. It should be:

```text
motion-constrained multi-frame inverse rendering with material scale and
height-field priors
```

That is a real research direction, not cleanup.

## 11. Files

- `differentiable_sheet_motion.py`
- `results/differentiable_sheet_motion_sweep/sweep_summary.md`
- `results/differentiable_sheet_motion_sweep/sweep_metrics.json`
- `results/differentiable_sheet_motion_sweep/seed41/contact.jpg`
