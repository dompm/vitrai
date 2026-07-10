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
- 006 validation coverage closed across all 5 recipes; generator passes uniform-backlight consistency.
- 007 full 5-recipe extractor eval: dark-opaque no longer blows out bright or magenta, but extractor
  runs dark-opaque too dark; wispy-white/opalescent is faithful; streaky-mix remains over-hazed and
  too neutral; cathedral carries relief/source-background texture in `T`.
- 008 product preview-invariance benchmark (`eval_preview_invariance.py`): raw copied pixels vs
  extracted `T,h` relit into a controlled warm preview. Material-relight wins strongly for
  wispy-white/streaky/cathedral overall (excluding dark-opaque: raw MAE 43.5 vs material MAE 20.6
  sRGB/255), but dark-opaque fails because `T` is too dark, and cathedral cast shadows become fake
  dark transmittance locally (inside-shadow material gap worse than raw).
- 009 (branch `research/delighting-classical`) fixed the two report-007/008 biases. `T_ANCHOR`:
  dark-opaque 0.10->0.20 (data-driven, gt p99≈0.216, deliberately conservative — not curve-fit) and
  opalescent 0.80->0.88 (no direct synthetic GT, justified by the closely-related wispy-white
  evidence); cathedral-clear/wispy anchors left unchanged (measured already correctly calibrated;
  moving them would overfit one recipe at another's expense — see report for the luminance table).
  Preview-invariance headline: **dark-opaque flips from a raw-copy loss (42.9) to a material-relight
  win (16.5 vs raw 18.9)**, with no other recipe regressing. Color-constancy (streaky-mix's blue):
  partially fixed (milkiness-fit weight cutoff + sheet-relative desaturation in `assemble_T`); the
  remaining gap was traced to the same single-photo `T·B` background-separation ambiguity as OP-1/
  the north-star hard case below, not a tunable color-constancy parameter — four other candidate
  fixes were tested and rejected as one-sided trades against wispy-white (see report 009 §2.1).

- 012 (branch `research/delighting-datav2`) generator realism: full mullion grid → partial
  border-edge occluders (20% of samples, params in meta.json); data v2 regenerated (validation gate
  unchanged at the report-006 floors); shadow U-Net retrained on the FIXED extractor's T. Held-out
  v2: inside-shadow 48.2→15.9 overall, dark-opaque 46.4→17.9 (beats the v1 net run OOD on the same
  sample, 23.3) — but only after a documented dark-opaque train-coverage top-up: the first
  same-scale retrain drew zero pair-detectable dark-glass shadows and silently lost the skill
  (46.4→46.4). Occluder over-fire largely fixed on dark glass (fire ~100%→0–6%, lift 0.43→0.01);
  still fires on an occluder behind CLEAR glass (98%, lift 0.56) — chroma-cue mask is the next step.
- 014 (branch `research/delighting-assembled`) the ASSEMBLED-PAIR BENCHMARK — the
  purest end-to-end metric, simulated entirely in Blender so the flat sheet CAPTURE
  and a 2×2 leaded ASSEMBLED piece are the SAME authored glass (new
  `generate_assembled.py` `--assembled` mode; pieces = UV rects of the shared sheet
  texture, A↔C correspondence verified to MAE 1e-4). Two materials (cathedral-green
  transmissive, wispy-white opalescent), IBL_1 capture vs IBL_2 relight truth
  (rotated 90–135° + ±1EV). **Drag test (headline): wispy relit dispersion collapses
  to the grain floor (Lab dE 5.30→1.01 ≈ floor 0.92; lum-CV 0.141→0.050) — dragging
  opalescent glass becomes texture-only; cathedral relit halves lum-CV (0.292→0.140)
  but stays 16× above the floor** (see-through `T·B` residual, the north-star hard
  case, now visible with GT). **Honest negative: from the identity source, raw-copy
  BEATS delight+relight on absolute composite-vs-truth fidelity** (extractor adds
  reconstruction error, T-MAE cathedral 0.134 / wispy 0.036, while raw carries true
  pixels) — de-lighting's win is consistency/invariance, not absolute per-piece
  fidelity. The honest illuminant `<L_A>·2^ΔEV` (no B pixel used) leaves the
  HDRI-rotation colour unmodeled — that global term, not the extractor, dominates the
  absolute error (oracle-gain ceiling cuts wispy 23→4.3).

## Open problems / next
- **OP-1 hand shadow** — needs the shadow ground-truth pair; learned removal likely.
- **High-contrast background separation** for transmissive glass — the north-star hard case.
- Add the **consistency** metric to the eval (same seed across lightings).
- Keep **preview-invariance** as a first-class product metric next to `T/h` ground-truth MAE.
- **Real photos still un-shot:** cross-lighting pairs + a shadow/no-shadow pair (the final benchmark).
- Relight side (2D compositor + 3D lamp PBR) — spiked earlier, shelved; returns once extraction is
  good enough.
