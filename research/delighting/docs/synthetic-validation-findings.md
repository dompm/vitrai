# Validation findings — synthetic generator (commit b9e5bb8) + the relaunched batch

Reviewer: research lead. TL;DR: **all 6 review fixes landed correctly, but the validation run does
NOT clear the gate — it covered only 1 recipe and its 15.6% MAE is a validation-scene artifact
(front-surface reflection veil), not a pass. The 300-render batch is not wasted; let it finish.
Fix the validation scene + coverage before declaring the generator verified.**

## Confirmed good
- All 6 items from the prior review are fixed in b9e5bb8: streaky-mix energy-diversion branch
  DELETED (transmission hardcoded 1.0 for all recipes) — corroborated by a live render where milky
  streaks now transmit (~0.31 mean) instead of going dark; smudge node removed; mullions restored as
  a 33% toggle recorded in meta; GT 16-bit; GT rendered under `Raw` view transform (correctly scoped —
  `Standard` restored right after); `--validate` + `.gitignore` added.

## Problem 1 — validation coverage is 1 recipe, not 5
`validate_data/` contains only cathedral-green (and just 1 usable sample). The recipe we most needed
to confirm — **streaky-mix** (the one that was physically broken) — and **dark-opaque** (where 16-bit
GT matters, T≈0.03) were never validated. The code fix gives high confidence, but the gate wasn't
actually exercised on them. Re-run `--validate` across all 5 recipes.

## Problem 2 — the 15.6% MAE is the validation scene, not the glass
Diagnosed on cathedral-green: the rendered photo is BRIGHTER than gt_T and desaturated, non-uniformly
by channel (ratio exr/gt ≈ R 1.49, G 1.10, B 1.39). That is an **additive ~+0.15 white veil**, not a
Fresnel transmission loss (which would darken, ~uniformly). Cause: validate mode surrounds the scene
with uniform white on BOTH sides, so the glass front surface reflects the white environment into the
camera. It hits the dark channels (R,B) hardest — exactly the observed pattern.
- Fix: in `--validate`, make the CAMERA side dark (black world/backdrop in front of the glass, white
  backlight only behind) so the intended identity `photo ≈ T × backlight` holds. Then cathedral should
  fall to low single-digit %, and streaky-mix becomes the real acceptance test.
- Note: the white backlight strength also reads slightly hot (gt G max 0.83 vs exr 0.91 even before the
  veil) — confirm world strength is exactly 1.0 so the linear render is directly comparable to gt_T.

## Problem 3 (the substantive one) — this veil sets the extractor's noise floor
The same front-surface reflection exists in the real HDRI renders and in real photos. Our extractor
model `L = T·(h·⟨B⟩ + (1−h)·B)` has **no front-reflection term**, so when we later score extracted T
against gt_T, part of the error will be this veil — not extractor failure. Decide the scoring
convention now (my recommendation in bold):
- **(a) Score against a purpose-rendered "clean transmission" target: uniform backlight, black camera
  side, no bump-reflection — i.e. the effective transmittance the extractor can actually recover.**
  Author gt_T stays as the material label; the clean render is the scoring reference.
- (b) Keep authored gt_T and report a measured veil-tolerance band.
- (c) Add a reflection term to the extractor model (bigger scope; revisit only if the data shows we
  need it).
I'd take (a) for phase 1 — it's the honest definition and gives a clean number.

## The relaunched 300-render batch
NOT invalidated — the HDRI renders are the actual dataset and legitimately include surface reflection.
Let it finish. This only means the *validation gate* hasn't truly been cleared yet, so hold off on
calling the generator "verified" until Problems 1–2 are addressed and re-run.
