# Vitrai

A stained-glass planning web app — segment pattern pieces from a photo using SAM2, then map real glass sheet textures onto each piece.

**App: [vitrai.dominiquepiche.com](https://vitrai.dominiquepiche.com/)**

Runs entirely in the browser (no backend). SAM2 inference runs on-device via WebGPU (ONNX Runtime Web).

## Getting started

```bash
cd frontend
pnpm install
pnpm dev
```

Then open `http://localhost:5173/`.

## Features

- **Segment pieces** — draw a bounding box or click prompt points; SAM2 produces a smooth polygon
- **Detect all** — auto-segment all pieces in the pattern at once
- **Glass sheets** — upload photos of your real glass; drag/rotate/scale the texture within each piece
- **Scale calibration** — set a real-world measurement on the pattern and each glass sheet for accurate sizing
- **Crop** — trim pattern or sheet edges
- **Export** — save the project as JSON; import it back later

## Glass swatch library data

The app ships a built-in library of ~1,270 real glass sheet swatches (Bullseye,
Oceanside, Wissmach, Youghiogheny). It has two parts:

- `frontend/public/assets/glass_swatch_registry.json` — the registry (metadata,
  image paths, physical calibration). **Committed to git**; the app's library
  dialog reads it at runtime.
- `frontend/public/assets/catalog_images/` — the swatch photos (~548 MB).
  **Gitignored, not committed.** On a clean checkout the library dialog opens and
  lists entries, but thumbnails show an "image not fetched" note until you run
  the build script below.

To fetch/refresh the images (and regenerate the registry) from the vendor
catalogs, run from the repo root:

```bash
pip install requests Pillow   # script dependencies
python3 scripts/build_swatch_library.py
```

The script scrapes the Bullseye and Stained Glass Express product feeds, scores
every gallery image with the vendored swatch-picker (`scripts/swatch_picker.py`)
to select genuine backlit sheet photos, applies watermark/border crops and
physical-size calibration, and writes the registry plus a diff report to
`docs/library-picker-rebuild/`. Re-runs are incremental: images are only
re-downloaded when the picked photo actually changes, and an anti-churn rule
keeps existing picks unless the picker's preference is decisive. Manual
per-SKU overrides (Reactive Cloud crop, white-on-white picker false positives)
are documented in the script itself.

Optionally set `VITE_SWATCH_CDN_URL` at build time to serve the catalog images
from an external host instead of `frontend/public/`.

## Tech

- React + TypeScript + Vite
- `onnxruntime-web` (WebGPU) for SAM2 inference
- OPFS for local project persistence
- Cloudflare Pages for hosting (COOP/COEP headers required for SharedArrayBuffer)

## Deployment

The app is a static build. Deploy `frontend/dist/` anywhere that supports custom response headers. The `frontend/public/_headers` file configures COOP/COEP for Cloudflare Pages.

```bash
cd frontend
pnpm build
```
