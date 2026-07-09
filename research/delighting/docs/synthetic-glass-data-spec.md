# Synthetic glass-sheet dataset — implementation spec (Blender/bpy)

Handoff spec for generating synthetic benchmark data for the Vitraux glass de-lighting research
(repo `dompm/vitrai`, branch `research/delighting`). The extractor under test takes a single
"photo" of a backlit glass sheet and recovers per-pixel material maps. Your job: render
photo-like images where those maps are **known by construction**.

## The material model (must match the extractor's world-view)

The extractor recovers exactly two per-pixel fields:

- **T(x)** — RGB transmittance in [0,1]: fraction of backlight passing through at each point.
- **h(x)** — haze/diffusion in [0,1]: h=1 fully diffusing (milky opal — glows, background
  invisible), h=0 clear (background visible sharply through the tint).

Light model the extractor assumes: `L(x) ≈ T(x) · [h(x)·⟨B⟩(x) + (1−h(x))·B(x)]` where B is the
backlight/background radiance and ⟨B⟩ its diffuse average. Build the Blender material to be an
honest physical realization of this: a thin sheet whose shader mixes a sharp refraction/
transparent lobe with a diffuse-transmission (translucent) lobe, weighted by h, both attenuated
by T.

## Non-negotiable design rule: textures first, shader second

Do NOT build glass from procedural shader nodes and then try to recover ground truth from the
node graph. Instead:

1. **Generate T and h as image textures first** (numpy or Blender texture bake, saved as 16-bit
   PNG or EXR). Procedural recipes below.
2. Plug those exact images into the shader (UV-mapped to the sheet plane).
3. Ground truth = those files, by construction. No inference, no baking-from-render.

## Glass recipes (start with these five)

| name | T recipe | h |
|---|---|---|
| cathedral-green | uniform (0.15, 0.55, 0.20) + low-amplitude large-scale noise ±10% | 0.02 uniform |
| cathedral-amber | uniform (0.75, 0.45, 0.08), same noise | 0.02 uniform |
| dark-opaque | uniform (0.03, 0.035, 0.03) ± a little | 0.3 uniform |
| streaky-mix | two-tone: bands of (0.9,0.9,0.95) and (0.3,0.5,0.8), stretched noise mask | h follows the mask: 0.9 in milky bands, 0.05 in clear |
| wispy-white | mostly (0.85,0.87,0.92) with grey wisps (0.55) via stretched/turbulent noise | 0.5–0.95 correlated with the wisps |

Also give every sheet a **hammered surface**: noise-driven bump/normal on the front face
(amplitude randomized, sometimes zero). This is realism, not ground truth — we do not recover
normals in this phase.

## Scene

- Thin sheet (e.g. 30×30 cm plane with ~3 mm solidify, or single plane with thin-walled
  refraction) held vertically ~10–50 cm inside a window opening.
- **Backlight = HDRI environment (IBL)** visible through the window. Use several outdoor HDRIs
  (polyhaven etc.), randomize rotation and exposure (±2 EV).
- Window frame geometry (dark mullions/crossbars) so part of the background is dark — this is
  the real-world "almost black pixels behind clear glass" trap; we want it in the data.
- Dim interior on the camera side (indoor HDRI or a dark room with one weak light) so the front
  face picks up mild reflections.
- Camera: handheld-like — small random tilt/offset per shot, sheet filling ~80–95% of frame,
  all four sheet corners visible. Resolution 1536² or thereabouts.

## Contaminants (each individually toggleable, each with a GT mask when applicable)

1. **Hotspot**: sun position in the HDRI near the frame, or a small bright area light behind
   the sheet. Toggle + rough position in metadata.
2. **Shadow caster**: an irregular blob/hand-proxy mesh between backlight and sheet, casting a
   soft shadow onto it. Render each such frame **twice: with and without the caster, nothing
   else changed** → export `gt_shadow_mask.png` as |with−without| thresholded. This pair is the
   training/eval data for the hand-shadow problem — highest-value item in the whole dataset.
3. **Grease-pencil mark**: dark scribble decal (texture with alpha) on the front surface;
   export its alpha as `gt_mark_mask.png`.

## Rendering & color management (where naive setups silently break)

- Cycles; transmission + transparent bounces ≥ 16; denoiser on.
- **View transform: `Standard`, NOT Filmic/AgX** — the extractor assumes an approximately
  gamma-encoded photo, and Filmic/AgX tone-curves destroy the multiplicative light model.
  Export both `photo.png` (sRGB 8-bit) and `photo_linear.exr` (32-bit, scene-referred).
- No camera exposure randomization beyond the HDRI EV shifts already specified; note the final
  effective exposure in metadata.
- No motion blur, no DoF (phase 1).

## Output contract (per sample)

```
synthetic/<glass_name>__<lighting_id>[__shadow|__clean]/
  photo.png            # sRGB render, the extractor's input
  photo_linear.exr     # linear render (optional consumer)
  gt_T.png             # 16-bit, the exact texture fed to the shader
  gt_h.png             # 16-bit, same
  gt_mark_mask.png     # if mark present
  gt_shadow_mask.png   # if shadow pair
  meta.json            # glass_name, class label (cathedral-clear/wispy/opalescent/dark-opaque),
                       # hdri name+rotation+EV, camera pose, toggles, blender version, seed
```

Everything seeded and reproducible: one CLI entry point like
`blender -b -P generate.py -- --out DIR --seed N --count M`.

## Scale & priorities

Phase 1 (this handoff): 5 glass recipes × 2 lightings + 2 shadow-pairs + 2 mark variants ≈
**15–20 renders**. That's enough for extractor evaluation. Do not generate hundreds until the
pipeline is validated. (Phase 2, only if a model gets trained on this: same generator, big N,
plus true volumetric scattering for opal glass — phase 1's translucent-lobe approximation of
haze is acceptable and documented.)

## Validation checks (run before calling it done)

1. **Uniform-backlight sanity**: render one sheet against a pure white uniform world (strength
   1.0, no frame). The linear render divided by the white level must ≈ gt_T within a few
   percent in high-h regions and everywhere for cathedral recipes. If it doesn't, the shader
   isn't realizing the model.
2. **h extremes**: h=0 region must show the background checkered HDRI sharply; h≈1 region must
   show none of it.
3. **Energy**: no glass pixel brighter (linear) than the unoccluded backlight beside it.
4. Shadow pair: pixel-identical outside the shadow region.

## Known limitation to state in your README

Cycles thin-glass + translucent mix is an idealization: real rolled glass has volumetric
scattering, ream/striations, and correlated color-haze structure the recipes only approximate.
This dataset certifies extractor *correctness* (does it recover known maps under known
corruptions), not real-photo fidelity — real photo pairs remain the final benchmark.
