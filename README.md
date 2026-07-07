# Vitrai

A Stained Glass CAD & Virtual Composition Studio — plan, draft, and assemble your designs with real-world glass textures at exact 1:1 scale entirely in the browser.

**App: [vitrai.dominiquepiche.com](https://vitrai.dominiquepiche.com/)**

Runs entirely in the browser (no backend). SAM2 inference runs on-device via WebAssembly/WebGPU (ONNX Runtime Web).

## Getting started

```bash
cd frontend
pnpm install
pnpm dev
```

Then open `http://localhost:5173/`.

## Core Features

- **AI Segmenter (SAM2)** — Draw bounding boxes or click prompt points to auto-segment a pattern photo into smooth vector pieces.
- **Vector CAD Canvas** — Draft custom stained glass panels from scratch. Place vertices, snap lines to 45° angles, and drag straight lines into bezier curves.
- **3D Lamp Assembly** — Construct complex rotational assemblies. Define lampshade silhouettes, assign symmetry properties, and interactively preview how your flat pieces wrap around a 3D mold.
- **Glass Sheet Nesting** — Import photos of your real glass sheets, set their scales, and map textures to pieces. Use **Smart Pack** to automatically nest pieces on sheets with cutting gap tolerances.
- **True Scale Printing** — Calibrate real-world size dimensions on any pattern. Export multi-page PDFs at exact 1:1 physical size.
- **OPFS Persistence** — Locally autosaves work offline in the browser's origin private file system.

## Tech Stack

- React + TypeScript + Vite + Konva.js
- `onnxruntime-web` (WebAssembly & WebGPU) for SAM2 AI inference
- Three.js for 3D Lamp projection
- OPFS for local project persistence
- Cloudflare Pages for hosting (COOP/COEP headers required for SharedArrayBuffer)

## Deployment

The app is a static build. Deploy `frontend/dist/` anywhere that supports custom response headers. The `frontend/public/_headers` file configures COOP/COEP for Cloudflare Pages.

```bash
cd frontend
pnpm build
```
