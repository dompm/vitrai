# Report 020 - Initial high-risk bets audit

Date: 2026-07-10.

This is a reset note after reports 017-019 drifted too far into cleanup/product
framing. The role of this track is not to be the careful product path. It is to
try the bets that might make the current representation obsolete.

## Bet A - GlassNet tiny inverse renderer

Status: **partially tested**.

Report 009 trained a tiny class-conditioned U-Net on the existing synthetic data
and scored it with preview-invariance. It beat raw/classical on held-out lighting.

What it proved:

- learned inverse rendering is viable on the toy synthetic distribution;
- preview-invariance is the right metric to keep using;
- the network can learn relightable maps better than hand heuristics when the
  generator supplies ground truth.

What it did **not** prove:

- held-out material generalization;
- real glass transfer;
- refraction/background disentanglement.

Verdict: Bet A deserves a v2 with many materials and real held-out material
splits, but it is not the boldest next move by itself.

## Bet B - Test-time neural optimization

Status: **not tested yet**.

This is the most unspent bet.

Idea:

```text
initialize from current extractor or quotient
optimize per-sheet fields T, relief/displacement, B, illumination
force a renderer to reconstruct the uploaded photo
regularize so background leakage does not collapse into T
```

This can be slow and ugly. That is acceptable here. If a per-sheet optimizer
produces better material maps in minutes, we can distill it later. If it fails,
it will tell us which variables are unobservable from one casual photo.

Verdict: **next bold candidate**.

## Bet C - Transparent background disentanglement

Status: **grazed, not solved**.

Reports 014-019 attacked symptoms:

- catalog prior says broad low-frequency variation is suspicious;
- learned catalog cleaner improves synthetic leakage but underperforms simple
  quotient math;
- luma quotient crushes brightness inconsistency but cannot separate chroma or
  geometry.

What is missing is the actual representation:

```text
observed RGB = render(T, relief/displacement, background B, illumination L)
```

For hammered cathedral glass, `B` is not noise. It is the distorted scene behind
the sheet. The model must predict it or marginalize it.

Verdict: Bet C is still open. The quotient result says the next version must
include explicit background/refraction, not just cleanup.

## Bet D - Confidence-driven hybrid path

Status: **parked**.

This is useful later, but it is too product-shaped for the current role. It can
wait until one of the bolder inverse-rendering paths has real signal.

## Representation bet from reports 010-012

Status: **promising but under-tested**.

Material-v2 added height/normal channels and an artist-facing relief prototype.
For this reset, ignore the feedback/product readout and keep the technical
claim:

```text
T,h alone cannot explain hammered glass.
Need relief/normal/displacement so the renderer can produce lensing, glints,
and background distortion.
```

Verdict: combine Material-v2 with Bet B/C. The next model should not only de-light
color; it should infer a relief/displacement field that explains why the
background is warped.

## Next move

Stop training catalog cleanup models.

Build a tiny **differentiable sheet renderer** experiment:

1. Use a crop of the real green/orange sheet or synthetic catalog-like texture.
2. Create a known clean `T`, known relief/displacement, and known background `B`.
3. Render an observed sheet with warped background leakage.
4. Optimize/predict `T + displacement + B` back from the observation.
5. Score not by pretty cleanup, but by whether moving a piece across the sheet
   samples stable material while the background layer is kept separate.

This is the high-risk path: if it works, it gives Vitrai a representation that
Illustrator-style pixel copying cannot touch.
