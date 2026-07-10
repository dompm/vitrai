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
**v1 / current extractor:** two per-pixel fields: **T(x)** = RGB transmittance in [0,1];
**h(x)** = haze/diffusion (1 = milky opal that glows and hides the background, 0 = clear glass
showing the background sharply). Light model: `L(x) ≈ T(x)·[h·⟨B⟩ + (1−h)·B]`, B =
backlight/background. IOR hardcoded 1.5.

**v2 / high-risk representation reset:** keep `T,h`, but add **height/normal** so the app can render
surface relief, local background warping, and glints. The synthetic generator now emits `gt_height`
and `gt_normal`, and uses the same height texture to drive Blender bump. This is the current bet for
making the final app preview feel like glass rather than a capture-invariant flat transparency.

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
**Learned track — high-risk active:** `train_glassnet_zero.py` proved a tiny class-conditioned U-Net
can learn held-out-lighting invariance on the current synthetic data. Next version should predict
Material-v2 channels (`T,h,height`) and be evaluated on held-out material identities.

## Synthetic ground-truth data (Blender/Cycles)
Textures-first (T,h authored as images, fed to shader → GT by construction), `Standard` view transform,
shadow on/off pairs (for the hand-shadow problem OP-1), mullion/frame toggle, multi-lighting per seed.
Generator: `../generate_synthetic.py` (now in-house via `bpy` in a uv env). 5 recipes: cathedral-green,
cathedral-amber, dark-opaque, streaky-mix, wispy-white. As of report 010, the generator starts
Material-v2 by exporting authored `height` and derived `normal` maps, and using that height to drive
Blender bump. **Caveat:** Cycles glass is cleaner than real rolled glass — synthetic certifies method
*correctness*, real photos remain the fidelity benchmark.

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
### Main track (classical + hybrid; reports/ files)
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
- 013 (branch `research/delighting-suncatcher`) FIRST real end-to-end product test: the app's
  tutorial pair (real backlit suncatcher photo + the two hammered-cathedral sheet photos + GT
  piece polygons). `suncatcher_bench.py` reimplements ResultPanel compositing and compares
  raw-copy vs de-light+relight. Provenance caveat (maintainer-confirmed): pattern is DIFFERENT
  physical glass than the sheets and has its own baked light → absolute color is style-distance,
  not accuracy; primary metric is cross-piece consistency + lighting-position sensitivity (no
  true reference needed). Split verdict, along the difficulty axes: de-lighting flattens the
  tiles (interior pixel-CV −22/−33%) and improves brightness-consistency at the product level
  (position-sensitivity luminance-CV −22% agg), but does NOT improve perceptual Lab color
  consistency (slightly worse) — the residual is transmitted garden bokeh + relief in
  transmissive cathedral glass, i.e. the ill-posed see-through-background separation
  (difficulty 2), now confirmed on REAL glass not just Cycles. Biggest gap = learned T·B
  separation, not solder/illuminant. Capture ask to make fidelity testable: shoot one sheet,
  cut a piece from a known region, assemble+backlight, shoot the result.

### Intern track (Mira/Codex — high-risk neural; numbering overlaps main-track reports, kept as-is)
- 009 high-risk neural track begins (`train_glassnet_zero.py` + persona doc): a tiny class-conditioned
  U-Net trained on the current synthetic data beats raw/classical on a held-out-lighting split
  (GlassNet preview MAE 1.3-6.7 vs classical 11.6-42.6), but this is **not** new-sheet
  generalization because sibling lightings of the same material are in training. Treat as a promising
  signal for learned cross-lighting invariance, not a solved product model.
- 010 representation reset: `T,h` is a useful base layer but insufficient for realistic glass because
  it has no place for surface relief/lensing/glints. `generate_synthetic.py` now exports
  Material-v2 `gt_height`/`gt_normal` and uses the same height texture for Blender bump. Syntax
  verified; Blender sample render still pending because Blender is not on this environment's path.
- 011 artist-facing prototype: `prototypes/material-v2-artist-demo.html` shows copied pixels vs
  `T,h` relight vs relief/normal relight with controls for glass class, background, relief, haze,
  glints, and light angle. Purpose is qualitative artist readout before the research over-optimizes
  for clean maps and loses the feel of glass.
- 012 artist feedback readout: relief/normal rendering feels directionally right, but the product
  must answer "is this derived from the real sheet, or invented?" Prototype now exposes `Relief
  Source` / `Truth Check`; research should add a relief provenance/confidence signal.
- 014 catalog-constrained sheet prior: using the real suncatcher sheet photos and 1,381 scraped
  manufacturer catalog sheets, a sheet-level prior that keeps high-frequency hammered relief while
  suppressing low/mid-frequency contamination reduces position sensitivity from raw 8.98 dE /
  0.407 lum-CV and fixed `T/h` 10.12 dE / 0.318 lum-CV to 1.90 dE / 0.060 lum-CV. Catalog audit
  says the tuned green prior keeps Textured/Baroque-level texture (50th percentile high-frequency)
  while dropping low-frequency variation to a normal Cathedral range. This is promising but must be
  class-gated/provenance-labeled because it can over-flatten true wisps/streaks.
- 015 catalog prior gate: a first robust-statistics gate scores whether broad low-frequency variation
  looks anomalous for the presumed material family. Suncatcher scores are green raw 0.84, green fixed
  `T/h` 0.66, green prior 0.14; orange raw 0.54, orange fixed `T/h` 0.22, orange prior 0.10.
  Catalog false positives are still too high at a 0.50 threshold (15-21% by category), but 0.70 is a
  useful conservative "offer/try prior assistance" signal and creates the provenance hook the artist
  feedback asked for.
- 016 learned prior gate: catalog negatives + synthetic leak positives train to test AUC 0.844, but
  under-call the real green suncatcher sheet (green raw 0.51, fixed `T/h` 0.33). Decision: useful
  negative result; do not sink time into catalog classifiers until positives look more like real
  cathedral see-through/background leakage.
- 017 catalog leak cleaner: switched the catalog from judge to weak clean-material teacher. A tiny
  neural cleaner trained on catalog crops with synthetic transmitted-background leakage improves
  synthetic held-out MAE by ~20% and nudges the real suncatcher in the right direction. Best variant
  is a smooth-residual representation: measured high-frequency relief stays from the uploaded sheet,
  the network edits only broad leakage fields. On the real tutorial benchmark: raw+neural improves
  dE 8.98 -> 8.02, fixed `T/h`+neural improves luminance-CV 0.318 -> 0.261, but the hand sheet
  prior is still far stronger (1.90 dE / 0.060 lum-CV). Verdict: keep "measured relief + learned
  smooth leakage field"; catalog-only supervision is not enough, especially for chroma leakage.
- 018 luma-only leakage field: added `--output-mode luma`, where the network may only apply a smooth
  scalar exposure field (`output = input * field`) and cannot repaint hue/chroma. It is weaker than
  RGB smooth-field cleanup (after fixed `T/h`: lum-CV 0.318 -> 0.291 instead of 0.261), but keeps hue
  stable (1.7 -> 1.7 instead of RGB smooth-field's 2.1). Product read: this is a safer default assist
  for "uneven backlight/background brightness" because it preserves uploaded glass color provenance.


## Open problems / next
- **OP-1 hand shadow** — needs the shadow ground-truth pair; learned removal likely.
- **High-contrast background separation** for transmissive glass — the north-star hard case.
- Add the **consistency** metric to the eval (same seed across lightings).
- Keep **preview-invariance** as a first-class product metric next to `T/h` ground-truth MAE.
- For GlassNet: generate many material seeds per class, then evaluate a held-out-material split;
  current neural result only proves held-out-lighting consistency.
- Render a v2 synthetic batch and add a Material-v2 preview metric that scores background
  displacement/highlight realism, not only color/haze.
- Run the Material-v2 artist prototype with at least one stained-glass maker and turn feedback into
  renderer acceptance criteria: how much relief, what kind of glint, what backgrounds matter, and
  whether the preview helps choose glass.
- Add provenance/confidence to Material-v2: sheet-derived vs plausible prior vs artist tuned. Do not
  let a prettier invented relief map masquerade as measured glass.
- Use the scraped manufacturer catalog as a weak material prior: learn which spatial variation is
  likely real sheet texture vs capture/background leakage, especially for cathedral/hammered glass.
- For learned leakage/prior strength, use the smooth-field representation from report 017 and train
  on better positives from real cross-lighting/capture pairs or synthetic renders that reproduce
  garden/window leakage through hammered cathedral glass.
- Split luminance leakage from chroma leakage explicitly: report 018 suggests a safe luma head can
  run with weak supervision, but any chroma head needs confidence and better paired/rendered data.
- **Real photos still un-shot:** cross-lighting pairs + a shadow/no-shadow pair (the final benchmark).
- Relight side (2D compositor + 3D lamp PBR) — spiked earlier, shelved; returns once extraction is
  good enough.
