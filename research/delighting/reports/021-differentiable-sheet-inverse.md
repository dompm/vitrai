# Report 021 - Differentiable sheet inverse: the representation helps, the single-image background does not

Date: 2026-07-10. Code: `differentiable_sheet_inverse.py`.

## 0. Why this report exists

Reports 017-019 were useful, but they were not bold enough. They treated the
glass photo as something to clean. Report 019 in particular showed that a simple
log-luminance quotient can beat a weak neural luma cleaner. That is a strong
signal that the next research effort should not spend more time rediscovering
exposure correction.

This report returns to the actual high-risk bet:

```text
observed sheet = render(T, background B, relief/displacement D, illumination)
```

For cathedral/hammered glass, the background seen through the sheet is not
noise. It is a layer of the image. The current product path copies pixels, so
that layer becomes part of the material. The research question here is whether
an explicit renderer can keep it separate.

This is deliberately synthetic and known-ground-truth. That is the point. Before
touching real glass, the representation should prove it can recover a clean
material map when the true variables are known.

## 1. Hypothesis

The current `T/h + copied texture` representation is missing a variable:

```text
B(x): the scene/light field behind the glass
D(x): the relief/refraction displacement that warps B through the glass
```

If `B` and `D` are represented explicitly, then the optimizer should be able to
explain warped window/garden structure as background leakage instead of baking it
into `T`.

Minimal success condition:

- `T` error drops versus raw RGB copy;
- high-frequency correlation between recovered `T` and background structure
  drops;
- preview-position luminance variation drops;
- the renderer still reconstructs the observed sheet.

Harder success condition:

- the same holds when `B` is not given as an oracle and must be inferred.

## 2. Renderer

The toy renderer is intentionally small:

```text
warped_B(x) = sample(B, x + D(x))
observed(x) = T(x) * (ambient + leak * warped_B(x))
```

Where:

- `T` is RGB transmittance / clean material color;
- `B` is a background image with sky/leaves/brick/window bars;
- `D` is a 2D displacement field derived from a synthetic relief height map;
- `ambient` is a constant base backlight;
- `leak` controls how much background structure appears through the glass.

There is no neural network in this report. This is test-time optimization over
fields. That is intentional: the first question is whether the representation is
observable enough to optimize. If it works, a network can be trained or distilled
later.

## 3. Synthetic data

Each case creates:

- a green cathedral-like `T` map with weak chromatic material variation;
- a high-contrast background `B` with vertical/horizontal window bars;
- a displacement field `D` with hammered-glass-like local lensing;
- an observed sheet image where `B` is warped through `D` and multiplied by `T`.

The synthetic setup makes the trap obvious:

```text
raw observed RGB contains real material + warped background bars
```

If a method treats raw RGB as material, it can look fine in the original capture
but fails as a relightable sheet.

## 4. Methods compared

### 4.1 Raw RGB trap

Treat the observed RGB image as the material map `T`.

This is what pixel-copying does conceptually: the material includes whatever
window/garden/background happened to be behind the sheet.

It reconstructs the observed image trivially, but should score badly on true `T`.

### 4.2 Low-T / no-displacement, known B

Give the optimizer the true background `B`, but force `D = 0`.

This tests whether a smooth material prior plus known background is already
enough. It can remove much of the leakage, but it cannot explain warped bars.

### 4.3 Low-T + displacement, known B

Give the optimizer the true background `B`, optimize both:

```text
low-resolution T + displacement field D
```

This is the oracle-background version of the representation. It asks: if the
background layer is known, does explicit refraction/displacement help keep `T`
clean?

### 4.4 Low-T + displacement + learned B

Do not give the optimizer the true background. Optimize:

```text
low-resolution T + medium-resolution B + displacement field D
```

This is much closer to the real single-photo problem. It is also underdetermined:
many combinations of `T`, `B`, and `D` can reconstruct the same observed image.

This method is expected to expose the ambiguity.

## 5. Metrics

The important metrics are not "does the output look nice?"

| metric | why it matters |
|---|---|
| `T MAE` | direct clean-material recovery against ground truth |
| `preview lum CV` | whether pieces sampled from different positions see stable material brightness |
| `T-bg highfreq corr` | whether background bars leaked into recovered `T` |
| `disp EPE` | displacement endpoint error in pixels |
| `renderer recon MAE` | whether the candidate state still recomposes the observed sheet |

The failure mode to watch:

```text
low renderer recon MAE + high T MAE = the optimizer explained the photo, not the material
```

That is exactly the bug a black-box image model can hide.

## 6. Sweep design

I ran 3 presets x 4 seeds:

| preset | ambient | leak | max displacement |
|---|---:|---:|---:|
| easy | 0.20 | 0.72 | 5.5 px |
| default | 0.16 | 0.84 | 8.0 px |
| hard | 0.10 | 0.90 | 13.0 px |

Each seed changes material noise, background noise, and relief/displacement.

Results live in:

- `results/differentiable_sheet_inverse_sweep_joint/sweep_summary.md`
- `results/differentiable_sheet_inverse_sweep_joint/sweep_metrics.json`
- per-case contact sheets under `results/differentiable_sheet_inverse_sweep_joint/<preset>_seed*/contact.jpg`

## 7. Aggregate results

### Easy

| method | T MAE mean | preview CV | T-bg highfreq corr | disp EPE |
|---|---:|---:|---:|---:|
| raw RGB trap | 0.1527 | 0.177 | 0.980 | 1.77 |
| low-T/no-displacement (known B) | 0.0073 | 0.068 | 0.161 | 1.77 |
| low-T + displacement (known B) | **0.0055** | **0.068** | **0.085** | **1.31** |
| low-T + displacement + learned B | 0.1046 | 0.083 | 0.291 | 1.87 |

### Default

| method | T MAE mean | preview CV | T-bg highfreq corr | disp EPE |
|---|---:|---:|---:|---:|
| raw RGB trap | 0.1558 | 0.213 | 0.984 | 2.57 |
| low-T/no-displacement (known B) | 0.0121 | 0.070 | 0.259 | 2.57 |
| low-T + displacement (known B) | **0.0074** | **0.068** | **0.127** | **1.79** |
| low-T + displacement + learned B | 0.1117 | 0.098 | 0.353 | 2.73 |

### Hard

| method | T MAE mean | preview CV | T-bg highfreq corr | disp EPE |
|---|---:|---:|---:|---:|
| raw RGB trap | 0.1666 | 0.267 | 0.986 | 4.17 |
| low-T/no-displacement (known B) | 0.0220 | 0.078 | 0.351 | 4.17 |
| low-T + displacement (known B) | **0.0111** | **0.066** | **0.156** | **3.02** |
| low-T + displacement + learned B | 0.1182 | 0.115 | 0.280 | 4.52 |

## 8. Readout

### 8.1 The representation helps when B is known

The oracle-background displacement method is consistently best.

Across all presets:

- it reduces `T MAE` by roughly 14x to 30x versus raw RGB trap;
- it beats known-B/no-displacement, especially as displacement gets stronger;
- it lowers `T-bg highfreq corr`, meaning background bars are less baked into
  the material;
- it recovers a meaningful displacement field, though not perfectly.

This validates the representation direction:

```text
T + B + D is more expressive than T alone
```

The improvement is largest in the hard preset, where no-displacement has `T MAE`
0.0220 and displacement drops it to 0.0111. That is the exact regime that matters
for hammered cathedral glass: background content is not merely dimmed; it is
warped.

### 8.2 The single-image learned-B version fails in the important way

The learned-B version reconstructs the observed sheet very well, but `T` remains
wrong:

| preset | learned-B T MAE | known-B+disp T MAE |
|---|---:|---:|
| easy | 0.1046 | 0.0055 |
| default | 0.1117 | 0.0074 |
| hard | 0.1182 | 0.0111 |

This is the ambiguity:

```text
T * warped(B) has many factorizations
```

From one image, the optimizer can move structure between `T`, `B`, and `D` while
keeping the rendered image nearly unchanged. This is not a tuning bug. It is the
physics of the inverse problem.

### 8.3 Visual contact-sheet read

The clearest example is:

`results/differentiable_sheet_inverse_sweep_joint/default_seed21/contact.jpg`

What to look for:

- raw RGB trap `T` visibly contains the window bars;
- known-B/no-displacement removes most large background structure but leaves
  warped residuals;
- known-B+displacement produces the cleanest `T`;
- learned-B+displacement reconstructs the observed sheet but its recovered `B`
  and `D` borrow structure in odd ways, and `T` is still contaminated.

The hard example:

`results/differentiable_sheet_inverse_sweep_joint/hard_seed22/contact.jpg`

This shows the same result under stronger background leakage and displacement.
The oracle `B` path still helps. The learned `B` path still does not solve the
factorization.

## 9. What this proves

It proves a narrow but important thing:

```text
If the background layer is known or strongly constrained, explicit displacement
lets the renderer recover a much cleaner material map than raw RGB or no-D.
```

That supports the Material-v2 direction from report 010:

```text
T/h is not enough; relief/displacement belongs in the state.
```

It also supports Bet C:

```text
transparent-background disentanglement must be explicit
```

The renderer needs a place to put the scene behind the glass. Without that place,
the background becomes material.

## 10. What this does not prove

It does **not** prove that a casual single uploaded sheet photo contains enough
information to infer `B`.

In fact, the learned-B failure suggests the opposite: a single image is too
ambiguous unless we add more constraints.

Possible constraints:

- multiple captures of the same sheet with different backgrounds or shifts;
- a known/provided background image or light-table capture;
- strong natural-image prior for `B`;
- stronger material prior for `T`;
- small user action: move/tilt sheet slightly, capture two frames;
- use real product context: if the sheet is photographed over a cutting mat,
  table, hand, or window, infer a structured background class.

This is where a neural prior could matter. But it should predict the missing
variables, not just clean pixels.

## 11. Consequence for the research agenda

Stop treating "de-lighting" as image restoration.

The bold path is:

```text
observed sheet
  -> infer T, relief/displacement D, background/light layer B, illumination
  -> render back to the input
  -> render forward into Vitrai's preview
```

The next experiments should not be catalog-only cleaners. They should be:

1. **Known-B synthetic curriculum**
   Train or optimize on cases where `B` is known and prove `D` generalizes across
   material seeds and displacement strengths.

2. **Two-frame disentanglement**
   Render the same `T,D` over two shifted/different backgrounds and optimize a
   shared `T,D` with per-frame `B`. If this works, it argues for a capture
   workflow: move the sheet slightly, take two photos.

3. **Background-prior model**
   Add a pretrained/natural-image prior or a small generative prior for `B` and
   test whether learned-B stops collapsing into `T`.

4. **Relief-to-preview metric**
   Stop scoring only `T`. Score whether moving a piece across the sheet keeps
   material stable while background/refraction effects can be rerendered under
   a new preview background.

## 12. Decision

This report is a green light for the representation, not for the full inference
pipeline.

The win:

```text
T + known B + displacement D recovers clean material much better than raw RGB.
```

The hard failure:

```text
T + learned B + displacement D from one image reconstructs well but does not
recover clean T.
```

That is the fresh research direction. The missing piece is not another cleanup
heuristic. It is extra information or a stronger prior that makes `B` identifiable.

## 13. Files

- `differentiable_sheet_inverse.py`
- `results/differentiable_sheet_inverse_sweep_joint/sweep_summary.md`
- `results/differentiable_sheet_inverse_sweep_joint/sweep_metrics.json`
- `results/differentiable_sheet_inverse_sweep_joint/default_seed21/contact.jpg`
- `results/differentiable_sheet_inverse_sweep_joint/hard_seed22/contact.jpg`
