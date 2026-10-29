# Vitrai

A browser-based CAD and virtual composition studio for stained glass artists.

**Live Studio: [vitrai.dominiquepiche.com](https://vitrai.dominiquepiche.com/)**

Stained glass is an unforgiving craft: once an expensive sheet of variegated art glass is cut, there is no undo button. Vitrai bridges digital vector design and physical fabrication—turning the stressful guesswork of pattern scaling, texture placement, and 3D assembly into digital confidence.

---

## What you can do

### ✏️ Draft & Trace
- **Vector CAD:** Draw panels from scratch on a clean canvas with the Pen tool, snap to 45° angles, and drag segments into smooth Bézier curves.
- **Photo Tracing:** Import photos of existing patterns or sketches. Outline pieces instantly with on-device AI (SAM2) or trace manually over the image.
- **Dimensional Calibration:** Set physical measurements (inches or centimeters) using a reference ruler so your project is locked to real-world scale.

### 🎨 Material Auditioning
- **Real Glass Inventory:** Add photos of your actual glass sheets and calibrate their physical dimensions.
- **Texture Flow:** Drag, rotate, and position pieces over glass sheets to align grain, wisps, and variegation before making a single cut.
- **Live Colorway Preview:** See your design come to life with authentic textures and light transmission.

### 🏮 3D Lampshade Studio
- **Parametric Silhouette:** Drag profile handles to shape lampshades from geometric cones to classic flared forms.
- **Automatic Unrolling:** Vitrai calculates and unrolls faceted tiers into flat pattern pieces automatically.
- **Concurrent Symmetry:** Work on one facet while Vitrai replicates matching pieces around the shade in real time.
- **Interactive 3D Assembly:** Spin, inspect, and preview the finished lamp rendered with physical glass materials.

### 📐 Fabrication Prep
- **Smart Pack & Nesting:** Automatically nest pattern pieces onto glass sheets with configurable cutting margins to minimize expensive scrap.
- **Solder & Came Lines:** Preview how your finished piece will look with adjustable solder bead and lead came widths.
- **1:1 Scale Multi-Page Printing:** Export printable pattern sheets tiled across standard printer pages (Letter/A4) at exact 1:1 physical dimensions.

---

## Local & Private by Design

- **Runs 100% Client-Side:** No artwork or photos are ever uploaded to a server.
- **On-Device AI:** SAM2 inference runs entirely in your browser via WebAssembly and WebGPU (ONNX Runtime Web).
- **No Accounts Required:** Open the studio and start creating immediately.
- **Offline Persistence:** Work is automatically saved in your browser's Origin Private File System (OPFS).

---

## Development

```bash
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:5173/` in your browser.

To run the unit test suite or the Playwright browser regression checks, see [docs/testing.md](docs/testing.md).
