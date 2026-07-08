# De-lighting research: single-photo glass material extraction

**Status: research, not product code.** Goal: from ONE casual photo of a glass
sheet held against a light source, extract per-pixel material maps for PBR
rendering in Vitraux:

- `T(x)` — RGB transmittance (glass color with the photo's illumination removed)
- `h(x)` — haze / diffusion fraction (1 = milky opal, 0 = clear glass showing
  the background)

A ship/no-ship decision is made on the reports in `reports/`. Current state:
`reports/001-classical-baseline.md` (baseline) and `reports/002-iteration.md`
(mark-inpaint fix, contrast recovery, 9-sheet library batch, pair harness).

## Layout

```
extract.py        pipeline + CLI (single file and batch/folder mode)
vlm_classify.py   Track C: glass-class prior + mark localization via `claude` CLI
contact_sheet.py  build one grid image over a batch (original|T|h|relit warm|cool)
register_pair.py  cross-lighting validation (M3): register two photos, compare maps
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

# batch: run a whole folder; per-file class/corners/mark_region from folder/manifest.json,
# missing values resolved by --vlm (claude CLI) or defaults
python3 extract.py ~/Downloads/new-eval-photos --vlm --out results

# handwriting removal: --mark-region is 'none', 'unknown' (global conservative
# detector, default), or a 3x3 grid cell where a SKU/price mark sits
python3 extract.py photo.jpg --glass-class wispy --mark-region bottom-right

# contact sheet over a whole batch (one grid image, MAE label per row)
python3 contact_sheet.py benchmark/library results/library results/library/contact_sheet.jpg

# cross-lighting validation (M3): two photos of the SAME sheet, different light
python3 register_pair.py A.jpg B.jpg --class wispy \
    --corners-a TL_x,TL_y,TR_x,TR_y,BR_x,BR_y,BL_x,BL_y --corners-b ...
# omit corners to auto-register via ORB (needs similar framing)
```

manifest.json format (keys are filenames inside the folder):

```json
{ "sheet1.jpg": { "glass_class": "wispy", "corners": [122, 980, 2938, 3876],
                  "mark_region": "bottom-right" } }
```

Outputs per photo: `<name>_T.png`, `<name>_h.png`, `<name>_panel.png`
(original | T | h | self-recon | error x5 | relit warm | relit cool),
`<name>_metrics.json`, and with `--debug` a `<name>_debug.png` with all
intermediate masks/fields.

Requires: `/usr/bin/python3` with numpy, pillow, scipy, opencv-python-headless.
`--vlm` additionally shells out to the `claude` CLI (results cached in
`.vlm_cache.json`, not committed).

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
