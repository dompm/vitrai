# Review: generate_synthetic.py (commit 247cef2) — Vitraux de-lighting research

Reviewer: research lead. Verdict: **solid implementation, one MAJOR physics bug (streaky-mix),
two MODERATE fixes, then regenerate.** The non-negotiables mostly pass.

## What passes (spec non-negotiables)

- **Textures-first ground truth** ✓ — numpy → float-buffer images → shader; and GT is re-rendered
  camera-aligned via emission-override. That refinement is *better* than the spec (pixel-space GT,
  exactly what the eval needs). Keep it.
- **`Standard` view transform** ✓, `photo.png` + `photo_linear.exr` ✓.
- **Shadow pairs** ✓ — only the caster toggles between `with_shadow_`/`without_shadow_`; the
  edge-gripping finger mask is a realism win. (Occluder visible *through* clear glass is fine —
  that's what a real hand behind glass does.)
- Colorspace handling is internally consistent (T linear, h/mark Non-Color in the material).
- Single-plane thin glass avoiding the solidify double-attenuation — good catch, keep the comment.
- Haze as transmission roughness: accepted as the phase-1 realization (rough refraction ≈ diffusion).

## Findings, ranked

1. **MAJOR — streaky-mix energy diversion is wrong physics.** `Transmission Weight = 1 − 0.8·h`
   sends up to 80% of the energy in milky streaks to the *front-lit diffuse reflection* lobe. Under
   backlight (the only strong light in the scene) those streaks render dark, while `gt_T` says 0.9
   and `gt_h` says "milky glow". Real opal glows by *transmitted* diffusion. This recipe will fail
   the spec's uniform-backlight validation check #1 by construction. **Fix: delete the
   Transmission-Weight branch entirely; let roughness carry haze for all recipes uniformly.**
   All streaky-mix samples in the current batch are invalid; the other recipes are unaffected.
2. **MODERATE — smudge noise contaminates ground truth.** Rendered roughness = `h + smudge(0–0.2)`
   but `gt_h` exports h alone → a built-in GT error floor of up to 0.2 exactly where h is small.
   Either add the smudge field into `gt_h` (it IS haze) or drop the smudge node.
3. **MODERATE — window mullions were removed.** The dark-occluder trap ("almost black pixels are
   the frame behind clear glass, not the glass") is one of the two real-photo confounders this
   dataset exists to probe. Restore frame geometry as a toggle, on for ~a third of samples,
   recorded in meta.json. The thin bare-HDRI border you added is worth keeping (it's a physical
   scale anchor) — do both.
4. **MINOR — GT PNGs are 8-bit.** Spec asked 16-bit; matters most for dark-opaque (T≈0.03).
   One-line change (`color_depth = '16'`).
5. **MINOR — document that `gt_h.png`/`gt_T.png` come out sRGB-encoded** (the view transform
   applies to the emission render). The eval consumer must decode sRGB; state it in a README next
   to the data (or render GTs with the display device set to None/Raw and document *that*).
6. **PROCESS — validate before scaling.** A 50×3 batch was launched before the `--validate`
   uniform-backlight check was run. Run validation on all five recipes first (post-fix), regenerate
   the phase-1 quantity (15–20 samples incl. shadow pairs and mullion-on samples), and only then
   scale. Also: `venv/`, `test*.png/exr`, and `synthetic_data/` are sitting untracked in the shared
   worktree — add a `.gitignore` under research/delighting/ for them.

## After fixes

Regenerate, run `--validate`, and drop the dataset under `research/delighting/benchmark/synthetic/`
(or leave in `synthetic_data/` and say so) — the extractor's batch mode + eval will consume it from
there. Report the validation numbers (uniform-backlight T agreement per recipe) with the dataset.
