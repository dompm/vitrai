# Report 010 - Material-v2 representation reset

Date: 2026-07-09. Code: `generate_synthetic.py` @ this commit.

## 0. TL;DR

The old `T,h` representation is useful, but it is not ambitious enough to be
the final Vitrai glass material.

It can make a sheet more capture-invariant: remove shadows, normalize
background color, and render the same tint under a new light. But it cannot
explain the thing that makes real stained glass feel alive: surface relief,
small refractions, view-dependent glints, and the local warping of whatever sits
behind the glass.

The synthetic renderer already had a surface bump, but it was an untracked
Blender noise node. That meant the rendered photos looked more glass-like while
the exported ground truth taught downstream models to ignore the bump. This was
a representation leak.

I changed the generator to start a **Material-v2** contract:

- `T` - RGB transmittance
- `h` - haze / diffusion
- `height` - scalar surface relief
- `normal` - derived normal map for app-facing preview/shading
- `mark_mask` - existing handwriting/label mask
- `bump_distance_m` - physical-ish scale metadata for the Blender bump node

Status: the generator parses cleanly. I could not render a Blender smoke sample
in this environment because `blender` is not on the command path, so the first
actual v2 sample render is still pending.

## 1. Is `T,h` good?

Yes, as a **de-lighting base layer**.

No, as the full material.

`T,h` is a good answer to the user pain:

> "The same sheet should not change color because the upload photo had a shadow
> or a different background."

It is not a good enough answer to:

> "The preview should feel like real glass."

The current product preview target is essentially:

```text
preview = illum * T * (h + (1 - h) * controlled_background)
```

That target rewards color/de-lighting invariance, but it has no channel for
hammered texture, rolled relief, lensing, or glossy response. If a model
predicts perfect `T,h`, the preview can still look flatter than the uploaded
photo because the uploaded photo contains surface physics that `T,h` has no
place to store.

This explains the "why does the target have lines but still looks less like real
glass?" observation: the lines probe haze, but they do not create glass relief.

## 2. The representation bug

Before this change, synthetic photos used Blender surface bump like this:

```text
procedural Noise Texture -> Bump -> Principled BSDF normal
```

But the dataset exported only:

```text
gt_T, gt_h, gt_mark_mask
```

So a neural inverse renderer trained on the dataset had a hidden contradiction:

- input photo: contains hammered/lensing effects from bump
- supervised output: has no bump channel
- preview target: cannot render bump

The network can only explain that signal as wrong `T`, wrong `h`, or nuisance
variation to suppress. That is exactly the wrong pressure if the product wants
delightful glass.

## 3. Material-v2 change

`generate_synthetic.py` now creates recipe-specific relief maps:

- cathedral glass: stronger hammered relief
- dark opaque: smaller, dense relief
- streaky mix: smoother relief aligned with the pull/streak direction
- wispy white: mixed broad and fine relief

The same height texture now drives Blender's `Bump` node and is exported as
ground truth:

```text
tex_height.exr
tex_normal.exr
gt_height.exr / gt_height.png
gt_normal.exr / gt_normal.png
meta.json.material_v2
```

This makes the synthetic data internally consistent: if a rendered photo bends
or sparkles because of relief, the dataset now has a target channel where that
relief can live.

## 4. App-facing renderer target

The end state should not be "predict more maps because research likes maps." The
maps only matter if the app can render something users feel.

A practical 2D Material-v2 preview target can stay cheap:

```text
normal = normals_from_height(height)
offset = eta_scale * normal.xy * clear_factor
B2 = sample(controlled_background, uv + offset)
diffuse = illum * T * (h + (1 - h) * B2)
spec = fresnel(normal, view, light) * roughness_term
preview_v2 = diffuse + spec
```

Where:

- `clear_factor = 1 - h`, so clear cathedral glass bends the background most.
- `h` still diffuses the background for opalescent/wispy glass.
- `height/normal` creates the local warping and highlight structure.
- `T` remains the color transport anchor.

This should be good enough for the 2D preview panel and also closer to the 3D
lamp material, where the normal map can feed the actual shader.

## 5. Neural implication

GlassNet-zero in report 009 learned `T,h`. Material-v2 changes the high-risk
question:

> Can a learned inverse renderer recover the sheet's color, diffusion, and
> surface relief from one casual photo well enough that the app can relight and
> re-background it?

That is harder. It is also more product-correct.

Possible neural outputs:

```text
T_rgb, h, height, source_shadow, source_background_leakage, confidence
```

The model does not need perfect metrology. It needs a plausible, stable relief
field that survives relighting and makes the preview look like glass instead of
a colored transparency.

## 6. Next experiment

The next bold experiment should render a v2 dataset and judge the renderer, not
only the maps:

1. Render 50-100 material seeds per class with `material_v2` channels.
2. Hold out entire material identities, not only lighting variations.
3. Train a class-conditioned GlassNet-v2 to predict `T,h,height`.
4. Add a Material-v2 preview-invariance benchmark:
   - target: `gt_T, gt_h, gt_height` rendered into controlled preview
   - baseline: raw copied pixels
   - v1: predicted/extracted `T,h`
   - v2: predicted `T,h,height`
5. Judge by:
   - preview MAE to synthetic target
   - clean/shadow preview gap
   - height/normal plausibility contact sheets
   - human "does this look like glass?" ranking against the app preview

The risk is that single-photo height inference is underconstrained. The reason
to try anyway is that a plausible class-conditioned relief prior may be enough
for product delight, even if it is not the exact microscope-correct surface.

## 7. Verification

Done:

- `python3 -m py_compile research/delighting/generate_synthetic.py` with a temp
  bytecode cache path.

Not done:

- Blender sample render. `blender` was not available on the command path in this
  environment, so v2 render files are not yet visually verified.

