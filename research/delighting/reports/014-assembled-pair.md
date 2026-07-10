# Report 014 — The Assembled-Pair Benchmark: a Blender ground-truth relight test

Date: 2026-07-09. Branch: `research/delighting-assembled` (off
`research/delighting-datav2`). Code: `generate_assembled.py` (new `--assembled`
generator, importing from `generate_synthetic.py`), `assembled_bench.py`,
extractor `extract.py` @ the fixed classical (report 009). Deliverables:
`results/assembled/{panel_*, drag_*, metrics.json}`, this report. Renders
gitignored. **No PR.**

This is the maintainer's proposed purest end-to-end metric. Report 013 (the real
suncatcher) could only measure *consistency*, because its assets are **mismatched
glass** with no ground truth — its §6 named the missing capture exactly: "photograph
one real sheet, cut a real piece from a known region of it, assemble/backlight it,
and photograph the result." Report 014 **synthesises that capture entirely in
Blender**, so the flat sheet and the assembled piece are the SAME authored glass by
construction, and absolute relight fidelity becomes measurable.

## 0. TL;DR

- **New generator mode.** `generate_assembled.py` renders, for one authored glass
  material (the same T,h textures): **RENDER A** — the flat sheet "capture" under
  IBL_1 (the extractor's input); **RENDER B** — a 2×2 assembled leaded piece, four
  squares cut from KNOWN UV rects of that sheet, under IBL_2 (same HDRI rotated
  90–135° + EV shifted) = the RELIGHT TRUTH; **RENDER C** — the same assembled
  piece under IBL_1 (assembly-model control). Purity: NO hand shadows, NO border
  occluders, procedural bump disabled → rendered appearance == authored T,h. Two
  materials (cathedral-green = transmissive hard case, wispy-white = opalescent
  product case), two IBL_2 variants each.
- **Correspondence is exact.** RENDER-A sheet region vs RENDER-C assembled-piece
  region under the same IBL_1 match to **MAE 1e-4 (linear)** — far-field HDRI makes
  the grid displacement negligible, so the pieces are provably the same glass. The
  raw-copy compositing geometry contributes **0.04–0.13 sRGB/255** of error (i.e.
  none). This is the property the real suncatcher could not have.
- **DRAG test (the headline) — the win, split by material.** Re-sourcing a piece
  from 9 UV positions, luminance CV raw→relit→grain-floor:
  **wispy 0.141 → 0.050 → 0.027** (Lab dE **5.30 → 1.01 → 0.92**) — relit collapses
  to the grain floor; **dragging opalescent glass becomes texture-only.** Cathedral
  **0.292 → 0.140 → 0.0085**: relit *halves* the luminance dispersion but stays
  ~16× above the floor, because the transmitted see-through background cannot be
  separated from a single photo (the documented north-star hard case, now visible
  with ground truth).
- **Absolute relight fidelity — the honest negative.** From the identity source,
  **raw-copy BEATS delight+relight** on composite-vs-RENDER-B MAE for both
  materials and both lightings (e.g. wispy rot90 raw 4.6 vs relit 11.3; cathedral
  rot90 raw 15.4 vs relit 18.1). Reason: when you know the exact source region, raw
  copy carries the glass's TRUE pixels and only needs a light change, whereas the
  extractor adds its own T-reconstruction error (T-MAE vs authored: cathedral 0.134,
  wispy 0.036) on top. De-lighting is **not** an absolute-fidelity win here; its win
  is specifically CONSISTENCY (the drag test), which is the actual product pain.
- **The honest illuminant is the dominant absolute error, not the extractor.** The
  rule `I2_hat = <L_A>·2^ΔEV` (RENDER A's own recovered backlight × the known EV
  delta; uses **no** RENDER-B pixel) does not model the HDRI rotation's colour
  shift. An oracle per-channel gain fit to RENDER B (labelled cheating) cuts wispy's
  absolute MAE **23→4.3** — i.e. ~80% of the honest absolute error is the unmodeled
  global illuminant, shared equally by raw and relit.

## 1. Method

### 1.1 Generator (`generate_assembled.py`, `--assembled` mode)

Imports the material/HDRI/GT helpers from `generate_synthetic.py`. Per material it
builds two scenes with a **jitter-free** camera (so the pixel↔UV map is exact and
deterministic):

- **Flat scene** → RENDER A under IBL_1 + the aligned authored ground-truth maps
  (`gt_T/gt_h/gt_mark`, reused from `render_ground_truths`, in RENDER-A pixel space).
- **Assembled scene** → four coplanar square glass planes in a 2×2 grid, each with
  its mesh UVs set to a chosen sheet UV rect (so it samples exactly that region of
  the SHARED sheet texture — exact correspondence, no registration), plus thin
  near-black coplanar **lead** strips (a centre cross + border frame; the complement
  of the pieces, so each square keeps a clear HDRI backlight — a full backing plane
  would block transmission). RENDER B is rendered for each IBL_2 variant, RENDER C
  under IBL_1, by only re-setting the world node rotation/strength (no rebuild).

Canonical source UV = **identity mapping**: a piece sitting at grid slot (cx,cz) is
cut from the sheet region it sits over. So the assembled panel is literally *the
sheet with lead cut into it*, the purest possible correspondence. Every piece's UV
rect, its source (RENDER-A) and dest (assembled) pixel bboxes, the full projection,
and all lighting params are written to `meta.json`.

**Purity deviations from `generate_synthetic.py`, all deliberate (brief):** no
hand-shadow caster, no border occluder, and `create_glass_material(..., use_bump=
False)` — the procedural hammered bump is evaluated in per-object space, so it would
NOT correspond between the flat sheet and the pieces, and relief glints are a
lighting-dependent separate axis (like shadows). Off ⇒ rendered appearance == the
authored T,h by construction.

**One real bug found & fixed (verified empirically).** `cam.data.angle_y` is derived
from the default `sensor_height` (24 mm), not the render aspect, so it wrongly
implied a vertical half-FOV of 0.096 and clipped the panel. A square `sensor_fit=
AUTO` render actually shows a SQUARE world region; `projection()` now derives the
vertical extent from the horizontal FOV × pixel aspect. Post-fix, the A↔C
correspondence check (below) lands at 1e-4, confirming the geometry.

### 1.2 Pipeline under test (`assembled_bench.py`)

1. **Extract** T,h,L from RENDER A with the fixed classical extractor at the
   **oracle class** (cathedral-green→`cathedral-clear`, wispy-white→`wispy`; isolates
   extractor error from classifier error, as in `eval_synthetic.py`), in native
   RENDER-A pixel space.
2. **Composite** the four pieces app-style: sample the extracted maps at the KNOWN
   `src_bbox_px`, resize into each `dest_bbox_px`, fill the rest with flat dark lead.
3. **Relight** for IBL_2 with `I2_hat = <L_A>·2^(ev2−ev1)`, where `<L_A>` is the mean
   of the extractor's own recovered illumination field L, and `2^(ev2−ev1)` is the
   KNOWN EV delta from `meta.json`. **Uses no pixel of RENDER B.** The relit
   appearance is `I2_hat·T` (flat backlight B=1 folds haze out: `h+(1−h)·1 = 1`).
   The HDRI rotation's effect on backlight COLOUR is deliberately unmodeled — the
   documented honest limitation, quantified by the oracle ceiling below.
4. **Baseline RAW-COPY**: sample RENDER A's photo pixels at the same UV rects, same
   strips, same global EV match `2^(ev2−ev1)` (scalar). Grants raw the same EV
   knowledge as relit, so the ONLY thing measured is whether the capture's spatial
   lighting is baked in (raw) or removed and re-lit flat (relit).

**Metrics** (inside piece masks, eroded 10 px). (1) RELIGHT FIDELITY: composite-vs-
RENDER-B MAE, per condition; plus RENDER-C vs composite-under-IBL_1 for the
assembly-model split. (2) DRAG TEST: re-source each piece from a 3×3 grid of UV
positions; dispersion (luminance CV; Lab dE to centroid) of the piece-mean across
the 9, for raw / relit / GRAIN FLOOR (= the same dispersion of the AUTHORED gt_T
directly — the irreducible texture variation). (3) Panels.

**Oracle-global-gain ceiling** (attribution only, labelled cheating): a per-channel
least-squares gain fit to RENDER B. Reported to separate the unmodeled-global-
illuminant error from the structural (extractor/geometry) error.

## 2. Correspondence validation

Under the SAME IBL_1, RENDER-A at each piece's source bbox vs RENDER-C at its dest
bbox (eroded), linear MAE:

| piece | A src mean (RGB) | C dst mean (RGB) | MAE |
|---|---|---|---|
| TL | [0.154, 0.317, 0.197] | [0.154, 0.317, 0.197] | 0.0001 |
| TR | [0.130, 0.292, 0.197] | [0.130, 0.292, 0.197] | 0.0001 |
| BL | [0.125, 0.244, 0.098] | [0.125, 0.244, 0.098] | 0.0001 |
| BR | [0.107, 0.205, 0.075] | [0.107, 0.205, 0.075] | 0.0001 |

The pieces are the same glass as the flat sheet to numerical precision, and the
assembled grid's small world displacement does not change the far-field-HDRI
backlight. This is the guarantee the mismatched-glass suncatcher (report 013) could
not provide.

## 3. Relight fidelity — composite vs RENDER B (the truth)

Piece-mask MAE, sRGB/255. `honest` = the defensible pipeline (§1.2). `oracle` = the
cheating per-channel-gain ceiling (attribution). Lower is better.

| material | IBL_2 variant | raw honest | **relit honest** | raw oracle | relit oracle |
|---|---|---|---|---|---|
| cathedral-green | rot135, −1EV | 16.2 | **20.4** | 15.1 | 18.0 |
| cathedral-green | rot90, +1EV | 15.4 | **18.1** | 13.5 | 17.6 |
| wispy-white | rot135, −1EV | 23.0 | **24.1** | 4.3 | 6.0 |
| wispy-white | rot90, +1EV | 4.6 | **11.3** | 3.2 | 10.6 |

Assembly-model split (composite vs RENDER C, matched IBL_1): **raw-copy 0.04 / 0.13**
(cathedral / wispy) — pure geometry, essentially zero; **relit 7.5 / 7.6** — extractor
error + the intentional envelope flattening under matched light.

**Reading it honestly:**

- **Raw-copy beats delight+relight on absolute fidelity, everywhere.** With the
  identity source, raw copy carries the glass's TRUE pixels and only needs a light
  change; the extractor instead substitutes its imperfect T (T-MAE vs authored:
  cathedral **0.134** — the see-through background baked in, consistent with report
  005's 0.167; wispy **0.036** — faithful). Delight+relight is not a way to make an
  assembled piece look *more* like the truth when you already know exactly where it
  was cut from.
- **The unmodeled global illuminant dominates the absolute number.** wispy rot135
  honest 23.0 → oracle 4.3: ~80% of the error is that `<L_A>·2^ΔEV` carries IBL_1's
  average colour, not IBL_2's rotated-sky colour. It hits raw and relit almost
  equally (raw 23.0→4.3, relit 24.1→6.0), so it is a shared nuisance, not a
  raw-vs-relit discriminator. A real relight would set this illuminant from the
  target scene; here we honestly refuse to read it off the truth.
- **Even at the oracle ceiling, raw wins** (structural: raw carries real pixels,
  relit carries extracted T). The extractor is not accuracy-positive as a pure
  appearance reproducer on this metric.

## 4. Drag test — the maintainer's headline

Re-source one piece from a 3×3 grid of 9 sheet UV positions; dispersion of the
piece-mean across the 9. Win condition: **relit ≈ grain floor, raw well above.**

| material | measure | raw | **relit** | grain floor | verdict |
|---|---|---|---|---|---|
| wispy-white | luminance CV | 0.141 | **0.050** | 0.027 | relit ~2× floor, raw 5× |
| wispy-white | Lab dE (to centroid) | 5.30 | **1.01** | 0.92 | **relit == floor** |
| cathedral-green | luminance CV | 0.292 | **0.140** | 0.0085 | relit halves raw, 16× floor |
| cathedral-green | Lab dE | 9.84 | 10.33 | 0.28 | dE unmoved (see below) |

- **Opalescent (the product money case): the win lands.** The relit piece's
  perceptual dispersion across drag positions (dE 1.01) is **indistinguishable from
  the authored-texture floor (0.92)** and 5× below raw (5.30); luminance CV drops
  −65%. For the bulk of decorative glass, **de-lighting makes dragging texture-only**
  — exactly the maintainer's target, now demonstrated against ground truth.
- **Transmissive cathedral (the hard case): half a win.** De-lighting removes the
  smooth brightness envelope (luminance CV −52%, 0.292→0.140) but leaves the piece
  16× above the grain floor, and Lab dE does not improve (9.84→10.33). Both are the
  same single-photo `T·B` see-through-separation limit `RESEARCH_STATE.md` calls the
  north-star hard case: the extractor keeps the transmitted sky/field structure in
  T (it cannot know it is background), so dragging still swings green↔blue. The dE
  non-improvement is the report-013 effect (dE inflates with the deeper saturation
  of extracted T; the scale-free luminance CV tells the fairer story) plus the
  unremoved see-through residual.

## 5. Own-eyes read of the panels

- **`panel_wispy-white.jpg`** (truth | relit | raw, rot135/−1EV): all three read as
  one coherent milky leaded panel. Relit is slightly flatter and a touch greener,
  raw slightly warmer/more varied; both sit a notch dark vs the truth — that is the
  shared unmodeled-global-illuminant offset (the oracle-gain versions would close
  it). No collage tell.
- **`panel_cathedral-green.jpg`**: truth, relit and raw all show the transmitted
  landscape (sky top / horizon / green field) through the 2×2. Relit and raw are
  very close to the truth AND to each other here — precisely because the identity
  source makes raw a near-oracle. The relit is marginally flatter.
- **`drag_wispy-white.jpg`** is the money shot: the **raw** row swings visibly from
  greenish-yellow (sourced near the field) to blue-grey (near the sky) across the 9
  positions; the **relit** row is strikingly uniform, tracking the flat **grain-floor**
  row (which is the pure authored milky T). This single image is the product claim.
- **`drag_cathedral-green.jpg`** is the honest counter-image: the **grain-floor** row
  is a flat uniform mint-green (the glass really is one colour), yet BOTH the raw and
  relit rows swing green→blue across positions because the transmitted landscape
  lives in the pixels. Relit is a little less bright-variable; the colour swing
  survives. The see-through separation problem, made visible with ground truth.

## 6. Honest caveats

- **Absolute fidelity is measured from the identity source only.** There is no
  per-position ground truth for a *dragged* assembly (the truth B is built from the
  identity source), so consistency (drag variance), not fidelity, is what the drag
  test can measure — by design. The raw-copy fidelity advantage is real but scoped:
  it assumes you know the exact source region and keep its lighting.
- **Two materials, one sheet seed, two lightings each (n small).** Directional, not
  a distribution. Cathedral is deliberately the extreme see-through case; a more
  weakly-transmissive cathedral would sit between the two rows here.
- **The honest illuminant ignores HDRI-rotation colour** — the dominant absolute
  error (§3). This is a *relight-model* gap, not an extraction gap: a defensible
  next step is to estimate the target illuminant from the target scene (the app's 2D
  gradient light / 3D lamp), which this benchmark deliberately does not read from B.
- **Synthetic, one HDRI (sunflowers), Standard view transform, no bump/shadow.**
  Purity by construction; Cycles glass is cleaner than rolled glass. Real matched
  captures remain the ultimate benchmark — but this one now proves the *pipeline
  math* end-to-end, which no real asset on hand can.
- **Lead is drawn flat-dark in the composite** vs Cycles-shaded near-black lead in
  the truth; masked out of all metrics, a minor visual-only difference.

## 7. Verdict

Does the pipeline reproduce a relit assembled truth, and does dragging become
texture-only? **Dragging becomes texture-only for opalescent glass (relit dispersion
== grain floor), and half-way for transmissive cathedral (envelope removed,
see-through residual remains)** — the clean confirmation of the project's central
consistency claim, now against Blender ground truth rather than the mismatched real
suncatcher. But **de-lighting does not reproduce the assembled truth more accurately
than a raw pixel copy** when the source region is known: it trades the extractor's
reconstruction error for the capture's baked lighting, a win only in the
consistency/invariance sense the product actually needs, not in absolute per-piece
fidelity. The two facts are consistent: relit's value is that its error is the SAME
wherever you drag from (≈ grain floor), while raw's error is low at the true spot
and high everywhere else.

## 8. Files

- `generate_assembled.py` — the `--assembled` generator (RENDER A/B/C + GT, FOV-correct
  projection, per-piece UV rects, meta.json). Imports from `generate_synthetic.py`;
  the only edit there is a `use_bump` flag on `create_glass_material`.
- `assembled_bench.py` — extract → composite → honest relight → fidelity + drag +
  panels; oracle-gain attribution; self-documenting header.
- `results/assembled/panel_{cathedral-green,wispy-white}.jpg` — truth | relit | raw.
- `results/assembled/drag_{cathedral-green,wispy-white}.jpg` — one piece @9 positions,
  raw / relit / grain-floor rows.
- `results/assembled/metrics.json` — all fidelity, drag, assembly-control, oracle,
  T-accuracy numbers.
- Gitignored: `assembled_data/` (the EXR/PNG renders + textures), regenerated by the
  generator.

## 9. Environment / provenance

- **Blender 5.0.1** official macOS arm64 portable (`~/Applications/Blender-5.0.1.app`),
  headless Cycles on Apple M4 Metal, 96 samples + OpenImageDenoise, 1024² Standard
  view transform. scipy/requests via `PYTHONPATH=~/.local/lib/python3.11/
  site-packages` + `--python-use-system-env` (report-006 recipe).
- Bench side: `/usr/bin/python3` with numpy/opencv/scipy/pillow. Extractor run at
  native 1024² so T is in RENDER-A pixel space (bboxes are recorded in px).
