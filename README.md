<table border="0" cellspacing="0" cellpadding="0">
  <tr>
    <td><img src="frontend/public/vitrai_logo.svg" width="56" /></td>
    <td valign="middle"><h1>&nbsp;VITRAI</h1></td>
  </tr>
</table>

A stained-glass planning web app — segment pattern pieces from a photo using SAM2, then map real glass sheet textures onto each piece.

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
