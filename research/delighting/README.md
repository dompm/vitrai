# De-lighting research: single-photo glass material extraction

**Status: research, not product code.** Goal: from ONE casual photo of a glass
sheet held against a light source, extract per-pixel material maps for PBR
rendering in Vitraux:

- `T(x)` — RGB transmittance (glass color with the photo's illumination removed)
- `h(x)` — haze / diffusion fraction (1 = milky opal, 0 = clear glass showing
  the background)

A ship/no-ship decision is made on the reports in `reports/`. Current state:
`001-classical-baseline.md` (baseline), `002-iteration.md` (mark-inpaint fix,
contrast recovery, 9-sheet library batch, pair harness), `003-absolute-scale.md`
(class-prior absolute-transmittance anchor so dark glass renders dark),
`004-hotspot.md` (backlight-hotspot recovery; VLM class default + anchor logging),
`007-full-recipe-eval.md` (ground-truth extractor eval across all 5 synthetic
recipes), and `008-preview-invariance.md` (product-shaped raw-copy vs material
relight benchmark). `009-glassnet-zero.md` starts the high-risk neural
inverse-rendering track. `010-material-v2-representation.md` starts a bolder
representation reset for surface relief / normals. `011-artist-material-review-prototype.md`
adds a standalone artist-facing comparison prototype. `012-artist-feedback-readout.md`
turns the first artist readout into the "make it beautiful, but keep it honest"
research rule. `014-catalog-constrained-sheet-prior.md` uses manufacturer catalog
images to sanity-check a sheet-level prior for the right-side glass panel.
`015-catalog-prior-gate.md` adds a first catalog-statistics gate so prior cleanup
is provenance-aware rather than automatic. `016-learned-prior-gate-negative.md`
records that a first synthetic-positive learned gate under-calls the real
suncatcher failure and should not distract from inverse rendering.
`017-catalog-leak-cleaner.md` turns the catalog into weak clean-material
supervision for a neural leakage-field cleaner; it improves brightness
consistency modestly but does not solve chroma/background separation.
`018-luma-leakage-field.md` splits luma correction from chroma correction.
`019-luma-quotient-prior.md` shows a simple log-luminance quotient beats the
weak neural luma cleaner, so learned cleanup must beat that baseline.
`020-initial-bets-audit.md` resets the high-risk track toward test-time
optimization and explicit transparent-background disentanglement.
`021-differentiable-sheet-inverse.md` starts that renderer path: oracle known
background plus displacement recovers clean material well, while learned
background from one image reconstructs but remains ambiguous.
`022-two-frame-background-ambiguity.md` tests shared `T,D` over two unknown
backgrounds; it helps only marginally, so extra frames need stronger B/D/T
priors or motion constraints.
`023-known-motion-background-constraint.md` adds a known-shift shared-background
constraint; it reduces background leakage in `T` sharply but still needs a
material scale/color prior. `024-height-field-displacement-prior.md` tests a
height-derived displacement state: cold-start height is worse than free flow,
but oracle-initialized height gives the best `T/B/D`, so relief is a promising
state only if it can be initialized or inferred. `025-integrable-flow-projection.md`
projects free-flow displacement into a height-field warm start; it improves
geometry/leakage modestly but still leaves a material-scale gap.
`026-curl-regularized-flow.md` moves integrability into the optimizer; soft curl
regularization is the strongest non-oracle renderer result so far.

## Layout

```
extract.py        pipeline + CLI (single file and batch/folder mode)
vlm_classify.py   Track C: glass-class prior + mark localization via `claude` CLI
contact_sheet.py  build one grid image over a batch (original|T|h|relit warm|cool)
register_pair.py  cross-lighting validation (M3): register two photos, compare maps
eval_preview_invariance.py  product preview eval: raw RGB copy vs T/h relight
train_glassnet_zero.py  tiny PyTorch neural inverse-rendering baseline
generate_synthetic.py  Blender/Cycles synthetic data generator; now exports Material-v2 height/normal GT
sheet_texture_prior.py  high-risk prior: preserve hammered relief while suppressing sheet-photo contamination
catalog_texture_audit.py  compare priors against scraped manufacturer catalog texture statistics
catalog_prior_gate.py  score whether a sheet should receive catalog-prior assistance
learned_prior_gate.py  negative/limited learned gate probe using catalog negatives + synthetic leaks
train_catalog_leak_cleaner.py  weak neural cleaner trained from catalog sheets with synthetic leakage
luma_quotient_prior.py  deterministic quotient baseline that falsifies weak learned luma cleanup
differentiable_sheet_inverse.py  tiny renderer/optimizer for T + background B + displacement D
differentiable_sheet_twoframe.py  two-observation identifiability test for shared T,D and learned B_i
differentiable_sheet_motion.py  known-shift shared-background inverse-rendering test
differentiable_sheet_heightfield.py  height-field displacement prior vs free-flow D test
differentiable_sheet_integrable_projection.py  free-flow warm start projected to integrable relief
differentiable_sheet_curl_regularized.py  soft curl/integrability prior for free-flow D
prototypes/       standalone research demos for feedback sessions
benchmark/        fixed eval inputs (easy + difficult); benchmark/library/ = 9 app swatches
results/          committed panels, T/h maps, metrics; results/library/ = the 9-sheet batch
reports/          numbered experiment reports (honest; decision documents)
```

## Usage

```sh
# single photo (class prior given)
python3 extract.py photo.jpg --glass-class wispy --out results --debug

# crop the glass region first (original-pixel corners)
python3 extract.py photo.jpg --corners 122,980,2938,3876 --glass-class wispy

# batch: run a whole folder; per-file corners/mark_region/class_override from
# folder/manifest.json. Class DEFAULTS to the claude-CLI classifier; a manifest
# class_override or --class beats it. Add --no-vlm to skip the classifier.
python3 extract.py ~/Downloads/new-eval-photos --out results

# handwriting removal: --mark-region is 'none', 'unknown' (global conservative
# detector, default), or a 3x3 grid cell where a SKU/price mark sits
python3 extract.py photo.jpg --glass-class wispy --mark-region bottom-right

# contact sheet over a whole batch (one grid image, MAE label per row)
python3 contact_sheet.py benchmark/library results/library results/library/contact_sheet.jpg

# cross-lighting validation (M3): two photos of the SAME sheet, different light
python3 register_pair.py A.jpg B.jpg --class wispy \
    --corners-a TL_x,TL_y,TR_x,TR_y,BR_x,BR_y,BL_x,BL_y --corners-b ...
# omit corners to auto-register via ORB (needs similar framing)

# product preview benchmark: compare copied capture pixels to controlled T/h relight
python3 eval_preview_invariance.py --data synthetic_data --out results/preview_invariance

# high-risk neural baseline (requires torch in the ignored .venv)
./.venv/bin/python train_glassnet_zero.py --data synthetic_data --out results/glassnet_zero_classcond

# synthetic Material-v2 data (requires Blender on PATH)
blender -b --python generate_synthetic.py -- --out synthetic_data_v2 --count 100 --light-variations 3

# artist-facing Material-v2 comparison demo; open the file in a browser
open prototypes/material-v2-artist-demo.html

# catalog-constrained sheet-prior audit; registry currently lives in the main workspace
python3 catalog_texture_audit.py \
  --registry /Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/glass_swatch_registry.json

# first-pass gate: should the sheet-prior be offered/applied?
python3 catalog_prior_gate.py

# learned gate probe; useful negative result, not a product model
python3 learned_prior_gate.py

# weak neural leakage-field cleaner; outputs baseline and smooth-residual result folders
./.venv/bin/python train_catalog_leak_cleaner.py --steps 900
./.venv/bin/python train_catalog_leak_cleaner.py \
  --out results/catalog_leak_cleaner_smooth --steps 900 --smooth-residual 33
./.venv/bin/python train_catalog_leak_cleaner.py \
  --out results/catalog_leak_cleaner_luma --steps 900 --smooth-residual 33 --output-mode luma

# quotient baseline every learned luma cleanup now has to beat
python3 luma_quotient_prior.py

# high-risk renderer sweep: explicit T + B + displacement inverse problem
python3 differentiable_sheet_inverse.py --sweep \
  --out results/differentiable_sheet_inverse_sweep_joint

# two-frame ambiguity test: shared T,D over two learned backgrounds
python3 differentiable_sheet_twoframe.py --sweep \
  --out results/differentiable_sheet_twoframe_sweep

# known-shift motion constraint: shared T,D,B across two shifted observations
python3 differentiable_sheet_motion.py --sweep \
  --out results/differentiable_sheet_motion_sweep

# height-field displacement prior: physical relief state vs free optical flow
python3 differentiable_sheet_heightfield.py --sweep \
  --out results/differentiable_sheet_heightfield_sweep

# project free-flow displacement into an integrable height-field warm start
python3 differentiable_sheet_integrable_projection.py --sweep \
  --out results/differentiable_sheet_integrable_projection_sweep

# soft integrability prior inside free-flow optimization
python3 differentiable_sheet_curl_regularized.py --sweep \
  --out results/differentiable_sheet_curl_regularized_sweep
```

manifest.json format (keys are filenames inside the folder):

```json
{ "sheet1.jpg": { "class_override": "wispy", "corners": [122, 980, 2938, 3876],
                  "mark_region": "bottom-right" } }
```

`class_override` is an explicit human class choice (only present when a human set
it); omit it to let the VLM classify. `mark_region` is human-only (the VLM
hallucinates marks); omit for the conservative global detector.

Outputs per photo: `<name>_T.png`, `<name>_h.png`, `<name>_panel.png`
(original | T | h | self-recon | error x5 | relit warm | relit cool),
`<name>_metrics.json`, and with `--debug` a `<name>_debug.png` with all
intermediate masks/fields.

Requires: `/usr/bin/python3` with numpy, pillow, scipy, opencv-python-headless.
Class classification shells out to the `claude` CLI by default (results cached in
`.vlm_cache.json`, not committed); `--no-vlm` disables it for offline runs.

## Benchmark

- **easy_amber.jpg** — amber hammered swatch from the app's default library
  (`frontend/public/assets/glass/amber.jpg`, label cropped off). Shot on a light
  table under relatively even backlight; class `cathedral-clear`.
- **difficult_wispy.jpg** — wispy white/clear sheet held by hand against a
  window (crop of `PXL_20260508_165112222 (1).jpg`). Known contaminants: hand
  shadow (top), sunset warmth (top), green lawn (bottom), grease-pencil
  "9000-81" (bottom-right), specular sheen; class `wispy`.

Method details, metric definitions, failure analysis and the keyed open-problem
list live in `reports/001-classical-baseline.md`.
