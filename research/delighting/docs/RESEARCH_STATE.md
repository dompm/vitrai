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
cathedral-amber, dark-opaque, streaky-mix, wispy-white; report 017 adds three dark-family recipes
(dark-deep, dark-ruby, dark-slate) to widen the absolute-scale anchor's dark-end calibration. As of
Intern-track report 010 (`010-material-v2-representation.md` — do not confuse with the same-numbered
main-track `010-neural-shadow.md`), the generator starts
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
- 010 (`010-neural-shadow.md`; number collides with the Intern track's own report 010 below —
  each track numbers its own reports independently and several numbers coincide throughout this
  doc) neural cast-shadow removal, hybrid on top of the classical extractor: report 008's isolated
  failure (a cast shadow darkens `I` but not `L`, so `T ≈ I/L` reads the shadow as fake dark
  transmittance, and cathedral loses to a raw-pixel copy inside the shadow) is fixed by a small
  U-Net (234k params) that detects the shadow and lifts `T` back toward its shadow-free value,
  blended by the predicted mask so non-shadow pixels pass through unchanged. Held-out
  lighting/seeds: cathedral inside-shadow preview MAE 71.9 (raw) / 56.9 (classical) -> **14.0**
  (classical+neural); non-shadow regions unchanged (23.6->23.1). GO decision for cast-shadow
  removal as a hybrid stage; retrained on the fixed extractor's T in report 012 below.
- 012 (branch `research/delighting-datav2`) generator realism: full mullion grid -> partial
  border-edge occluders (20% of samples, params in meta.json); data v2 regenerated (validation gate
  unchanged at the report-006 floors); the report-010 shadow U-Net retrained on the FIXED
  extractor's T. Held-out v2: inside-shadow 48.2->15.9 overall, dark-opaque 46.4->17.9 (beats the
  v1 net run OOD on the same sample, 23.3) -- but only after a documented dark-opaque
  train-coverage top-up: the first same-scale retrain drew zero pair-detectable dark-glass shadows
  and silently lost the skill (46.4->46.4). Occluder over-fire largely fixed on dark glass (fire
  ~100%->0-6%, lift 0.43->0.01); still fires on an occluder behind CLEAR glass (98%, lift 0.56) --
  chroma-cue mask is the next step.
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
- 015 (branch `research/delighting-corpus`) characterized the ~3,200-image catalog corpus:
  82.8% metadata-classifiable, lighting geometry NOT uniformly backlit (per-manufacturer
  triage), VLM class prior only 30.6% accurate at scale, and the extractor breadth test
  found a catastrophic anchor blowup (`T_anchor_k`=880 on a texture-free saturated swatch).
- 016 (branch `research/delighting-anchor`) made the absolute-scale anchor robust to class
  error, in two layers. (1) Sanity gate, default-on: k outside (0.05, 5.0) means the T
  assembly degenerated (conf collapse -> diffusion fill from nothing -> T==0); rebuild T
  from R, re-anchor, flag `anchor_fallback`. Zero regressions; the k=880 corpus case goes
  recon MAE 83 -> 0.5. (2) Continuous anchor (`--anchor continuous`): class-free
  image-statistics estimate of the absolute scale (fit only on synthetic GT), class prior
  demoted to regularizer via an adaptive log-space blend. Class-error injection eval
  (every synthetic sample under all 4 priors, `eval_class_injection.py`): wrong-class
  T-MAE 0.399 -> 0.226, worst brightness error 9.73x -> 3.80x, dark-as-cathedral
  3.5x-too-bright -> 1.9x, correct-class cost +0.005 and the real 9-sheet library
  visually unchanged. Metrics now always carry `anchor_scale_disagree` (image-vs-class
  target ratio; >2 = review flag — caught two corpus registry-noise images with zero
  library false positives). Recommendation: gate everywhere; continuous anchor as default
  for VLM/metadata-classed runs, class anchor for human-verified manifests. Wrong-class
  h/assembly corruption remains open (the anchor fixes scale only); the estimator's dark
  end is calibrated by one recipe family (more dark seeds = highest-value data add — see
  report 017 below, which adds three). **Sign-off landed** (commit `896c2d7`): `--anchor`
  now defaults to `auto` — `continuous` when the class came from the VLM/fallback path,
  `class` when a human set it via `--class`/manifest `class_override` — implementing this
  report's recommendation exactly; the gate stays default-on everywhere as before.
- 017 (branch `research/delighting-017`, `017-dark-calibration-invariance.md` — number
  collides with the Intern track's catalog-leak-cleaner 017) widened the continuous
  anchor's dark-end calibration and added the long-queued capture-invariance metric.
  Three new dark recipes (`dark-deep` gt-p99 0.055, `dark-ruby` 0.13 strongly tinted,
  `dark-slate` 0.31) bracket dark-opaque (0.216); refit with floor T_LO 0.10->0.04
  (dark-deep sat below the old floor): LORO worst 4.29x -> 3.37x with held-out darks
  now predicted dark instead of ~0.9-bright; injection worst wrong-class brightness
  17.1x (class anchor on the new darks!) vs 4.15x (old fit) -> 3.90x (new), dark-deep
  wrong-class 3.4x -> 2.1x, original five recipes at noise level; the continuous anchor
  now BEATS the class anchor under the correct class on the widened set (0.103 vs 0.107
  T-MAE) because one T_ANCHOR point per class cannot span a darkness family; library
  byte-identical (default path), blue.jpg 0.002 luminance under forced continuous.
  NEW metric `eval_cross_lighting.py` (same authored glass, N lightings, pairwise map
  difference): dark family under oracle class is highly invariant (T 0.02-0.06);
  cathedral is capture-DEPENDENT beyond its accuracy error (0.18-0.20 vs 0.14-0.15
  GT-MAE — the T·B leak varies per lighting, the north-star problem now has an
  invariance number); honest cost found: per-photo t_img variance breaks group
  consistency on mid/dark glass under the vlm-free continuous path (dark-opaque
  invariance 0.036 class-anchored -> 0.280 continuous) — class anchor is consistently
  wrong, continuous is averagely right; `auto` default stands, but "estimate the scale
  once per sheet, not once per photo" is a measured follow-up.
- 020 (branch `research/delighting-020`, `020-per-sheet-scale.md`) closed both of 017's named
  follow-ups, and found they compound: `extract.estimate_anchor_scale_sheet` pools several
  photos of the SAME sheet's continuous-anchor `t_img` via MEDIAN (product entry points: a
  multi-file CLI call, or a manifest `sheet_id` key in batch mode; N=1 is the identity, so
  single-photo behaviour is byte-identical). Cross-lighting invariance recovers almost all the
  way to the class-anchored floor: dark-opaque T 0.280 (per-photo, reproduced) -> 0.045
  (per-sheet, shipped) vs oracle's 0.036. Separately, `sat_lit`'s luminance gate (blind on
  every dim capture per 017) gained an adaptive percentile fallback exactly when the old
  absolute gate is degenerate (12/35 samples, all dark-family; 0 library/bright-recipe
  features change) — dark-ruby's tint goes from indistinguishable-from-neutral (sat_lit 0.0)
  to clearly separated (0.66-0.71 vs dark-deep's 0.06-0.20); refit shipped, 9-sheet library
  byte-identical on the default path (18/18 md5). Honest finding: the sat_lit refit ALONE
  (no pooling) is a mixed bag — dark-ruby's own correct-class T-MAE worsens and both the
  injection worst-case (3.90x->5.22x) and LORO (3.37x->3.47x) regress, all traced to one
  outlier photo's per-photo estimate; per-sheet pooling exactly fixes this (the shipped
  combination posts worst-case 3.90x->3.30x and LORO 3.37x->2.28x, both BETTER than 017,
  not just recovered) — the two fixes were designed to be shipped together, not separately.

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
  stable (1.7 -> 1.7 instead of RGB smooth-field's 2.1). Research read: luma-only is a controlled
  ablation showing that brightness-field correction and chroma/background disentanglement are
  separate problems.
- 019 luma quotient falsification: a deterministic log-luminance quotient beats both neural cleanup
  runs on the real suncatcher (fixed `T/h` -> quotient alpha=1.0: dE 10.12 -> 3.18, lum-CV 0.318 ->
  0.056, hue unchanged at 1.7). This reframes reports 017-018 as a useful weak-neural failure: do
  not spend high-risk neural capacity rediscovering smooth exposure correction. The next model needs
  explicit background/refraction/chroma separation.
- 020 initial bets audit: Bet A (GlassNet) was partially tested on toy synthetic held-out lighting;
  Bet B (test-time neural optimization) is still untried; Bet C (transparent background
  disentanglement) has only been attacked indirectly through priors/quotients; Bet D is parked as
  too product-shaped for the current reset. Next bold move: differentiable sheet renderer with `T`,
  displacement/relief, background layer `B`, and renderer recomposition loss.
- 021 differentiable sheet inverse: first true Bet B/C renderer experiment. Synthetic known-GT sheet
  renderer uses `observed = T * (ambient + leak * warp(B, D))`. Across 3 presets x 4 seeds, oracle
  known-background + learned displacement strongly beats raw RGB and no-displacement on clean `T`
  recovery (hard preset T-MAE: raw 0.1666, known-B/no-D 0.0220, known-B+D 0.0111). But when `B` is
  also learned from one image, reconstruction stays excellent while `T` remains bad (hard T-MAE
  0.1182). Conclusion: the representation is right, but single-image `B` is not identifiable without
  extra constraints/prior/captures.

## Open problems / next
- **OP-1 hand shadow** — needs the shadow ground-truth pair; learned removal likely.
- **High-contrast background separation** for transmissive glass — the north-star hard case.
- ~~Add the **consistency** metric to the eval (same seed across lightings).~~ DONE, report 017
  (`eval_cross_lighting.py`).
- ~~Stabilize the continuous anchor's t_img across captures of the same sheet (per-sheet, not
  per-photo, scale estimation).~~ DONE, report 020 (`estimate_anchor_scale_sheet`, median
  pooling; dark-opaque invariance 0.280->0.045 vs oracle's 0.036). Follow-up opened there:
  the product needs a way to assign sheet identity to grouped uploads (manifest `sheet_id` /
  multi-file CLI exist as mechanism, but the upload-flow UX decision is open); wrong-class `h`
  corruption (016 SS5.2) is untouched by scale pooling and remains open.
- ~~Fix `sat_lit`'s dim-capture blindness (016 SS5.2 / 017 note 3).~~ DONE, report 020 (adaptive
  percentile fallback gate); only validated/shipped in combination with per-sheet pooling —
  see report 020 SS2.3/SS3.1 for why it is not a safe ship in isolation.
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
- Treat the luma quotient from report 019 as the baseline every learned cleanup must beat.
- Stop training catalog-only cleanup models; move to explicit transparent-background disentanglement.
- Bet B/C next after report 021: add extra information or priors that make `B` identifiable. Best
  candidates: two-frame shifted-background capture, stronger natural-image/background prior, or
  known-background/light-table synthetic curriculum before distillation.
- **Real photos still un-shot:** cross-lighting pairs + a shadow/no-shadow pair (the final benchmark).
- Relight side (2D compositor + 3D lamp PBR) — spiked earlier, shelved; returns once extraction is
  good enough.
