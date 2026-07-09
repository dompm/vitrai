# Glass de-lighting research — living state doc

Last updated 2026-07-09. This consolidates the research arc so any session (or teammate) can
resume. Companion docs in this folder: `synthetic-glass-data-spec.md` (the data-gen brief),
`synthetic-generator-review.md` / `synthetic-validation-findings.md` / `synthetic-generator-feedback-2.md`
(reviews of the generator). Numbered iteration reports live in `../reports/`.

## The problem & motivation
The app's core feature is previewing stained glass as realistically as possible (it already beats
flat-color tools by compositing real glass texture). Biggest limitation: when a user drags a glass
piece, the RGB copied over looks **different depending on the source photo's background & shadows** —
the capture lighting is baked into the sheet photo. Goal: **de-light** each sheet to a
capture-invariant intrinsic representation, then **relight** it in a controllable render (2D result +
3D lamp), so the same physical glass always previews consistently.

## Material model
Two per-pixel fields: **T(x)** = RGB transmittance in [0,1]; **h(x)** = haze/diffusion (1 = milky
opal that glows and hides the background, 0 = clear glass showing the background sharply).
Light model: `L(x) ≈ T(x)·[h·⟨B⟩ + (1−h)·B]`, B = backlight/background. IOR hardcoded 1.5.

## Success metric (refined)
The **primary** metric is CROSS-CAPTURE CONSISTENCY / invariance — the same glass under different
lighting must de-light to the same map — NOT just absolute accuracy vs ground truth. Being
consistently a little wrong still fixes the user's pain. Measured two ways: synthetic multi-lighting
(same seed, N lightings) and real cross-lighting photo pairs (`register_pair.py` T-agreement).

## Deployment reality (robustness target)
Users upload **phone photos** of glass that may be **fairly transmissive**, against **high-contrast
backgrounds**. The hard case (see-through structured background) is the one to get GOOD at, not route
around. Useful difficulty split:
- **(1) Shadow + brightness-gradient normalization** — tractable, classical method already does much
  of it; delivers most of the felt pain, esp. for opalescent/textured glass (the bulk of decorative
  glass). 
- **(2) See-through background separation** for transmissive glass — ill-posed (photo = T·B, 2
  unknowns/px, needs a prior); likely needs a learned method.

## Approach & status
**Track A — classical decomposition (baseline, works):** edge-aware illumination envelope + polynomial
chroma field; chroma-anomaly mark inpainting (diffusion-fill); class-modulated haze; absolute T scale
anchored by a class prior (per-image normalization was a gauge bug that made black glass glow — see
report 003). All 9 default-library sheets extract & relight plausibly.
**Track C — VLM class prior:** `claude` CLI multiple-choice classifier (classifier only, never numeric
regression — small models collapse numbers). Batch default; manifest = explicit human override.
**Learned track — not started:** the likely endgame for difficulty-(2); enabled by the synthetic data.

## Synthetic ground-truth data (Blender/Cycles)
Textures-first (T,h authored as images, fed to shader → GT by construction), `Standard` view transform,
shadow on/off pairs (for the hand-shadow problem OP-1), mullion/frame toggle, multi-lighting per seed.
Generator: `../generate_synthetic.py` (now in-house via `bpy` in a uv env). 5 recipes: cathedral-green,
cathedral-amber, dark-opaque, streaky-mix, wispy-white. **Caveat:** Cycles glass is cleaner than real
rolled glass — synthetic certifies method *correctness*, real photos remain the fidelity benchmark.

## Iteration results
- 001 classical baseline; 002 mark-inpaint + contrast + library batch + pair harness; 003 absolute
  T-scale anchor (black-glass glow fixed); 004 backlight-hotspot recovery + VLM-default/T_raw_p99 diag.
- 005 first per-pixel GT eval (only 2/5 recipes had rendered): cathedral-green T-MAE 0.167
  (= 0.03 tint + 0.13 background-bleed — the single-photo ambiguity, not mainly extractor error),
  h 0.08; streaky-mix T 0.115, h over-hazed. Shadow gap (OP-1) quantified: T corrupted ~0.31
  (clear) / ~0.08 (milky), localized. Streaky physics fix confirmed by eye.
- 006 validation coverage across all 5 recipes (in progress by synth-gen as of this writing).

## Open problems / next
- **OP-1 hand shadow** — needs the shadow ground-truth pair; learned removal likely.
- **High-contrast background separation** for transmissive glass — the north-star hard case.
- Finish rendering the 3 missing recipes → re-run `eval_synthetic.py` → answer the dark-opaque
  absolute-scale question and the wispy-white (opalescent money case) faithfulness.
- Add the **consistency** metric to the eval (same seed across lightings).
- **Real photos still un-shot:** cross-lighting pairs + a shadow/no-shadow pair (the final benchmark).
- Relight side (2D compositor + 3D lamp PBR) — spiked earlier, shelved; returns once extraction is
  good enough.
