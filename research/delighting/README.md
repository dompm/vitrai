# De-lighting research: single-photo glass material extraction

**Status: research, not product code.** Goal: from ONE casual photo of a glass
sheet held against a light source, extract per-pixel material maps for PBR
rendering in Vitraux:

- `T(x)` — RGB transmittance (glass color with the photo's illumination removed)
- `h(x)` — haze / diffusion fraction (1 = milky opal, 0 = clear glass showing
  the background)

A ship/no-ship decision is made on the reports in `reports/`. Current state:
`reports/001-classical-baseline.md` (Track A classical pipeline + Track C VLM
class prior).

## Layout

```
extract.py        pipeline + CLI (single file and batch/folder mode)
vlm_classify.py   Track C: glass-class prior via `claude` CLI (multiple-choice)
benchmark/        fixed eval inputs (easy + difficult case, manifest.json)
results/          committed panels, T/h maps, metrics for the benchmark
reports/          numbered experiment reports (honest; decision documents)
```

## Usage

```sh
# single photo (class prior given)
python3 extract.py photo.jpg --glass-class wispy --out results --debug

# crop the glass region first (original-pixel corners)
python3 extract.py photo.jpg --corners 122,980,2938,3876 --glass-class wispy

# batch: run a whole folder; per-file class/corners from folder/manifest.json,
# missing classes resolved by --vlm (claude CLI) or default
python3 extract.py ~/Downloads/new-eval-photos --vlm --out results
```

manifest.json format (keys are filenames inside the folder):

```json
{ "sheet1.jpg": { "glass_class": "wispy", "corners": [122, 980, 2938, 3876] } }
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
