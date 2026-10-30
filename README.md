# Vitrai

A stained-glass planning web app — segment pattern pieces from a photo using SAM2, then map real glass sheet textures onto each piece.

**App: [vitrai.dominiquepiche.com](https://vitrai.dominiquepiche.com/)**

Editing and SAM2 inference run entirely in the browser via WebGPU (ONNX Runtime Web). The built-in glass library reads public images from R2 through a Pages Function; user projects stay on-device.

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

## Tech

- React + TypeScript + Vite
- `onnxruntime-web` (WebGPU) for SAM2 inference
- OPFS for local project persistence
- Cloudflare Pages for hosting (COOP/COEP headers required for SharedArrayBuffer)

## Deployment

Cloudflare Pages builds from the `frontend` root with output directory `dist`. The `public/_headers` file configures COOP/COEP; `functions/glass/[[path]].js` serves the approved glass images from an R2 binding named `GLASS_BUCKET`. Bind it to the `vitrai-glass` bucket in both Production and Preview, then redeploy. No R2 API keys belong in the frontend.

Production uses `/glass/releases/8ad3855dc24cbcfc`; local Vite development uses the public R2 development URL from `frontend/.env`. The committed registry is the approved catalog, not a generator output to rebuild from vendor websites. When publishing new image bytes, use a new immutable release prefix and update the production URL and Function's allowed prefix together. `_routes.json` limits Function invocations to `/glass/*` so editor assets remain static requests.

```bash
cd frontend
pnpm build
```
