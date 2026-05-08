# Vitraux — Web App Plan

## Goal
Build a web app where you import a stained-glass **pattern image** and **glass sheet photos**, then:

- Define/auto-detect **piece regions** on the pattern
- Assign each piece to a glass sheet
- **Drag/rotate/scale** the glass texture per piece and see the result clipped into the pattern (2D “UV mapping”)

## Core product decisions (v1)
- **Piece creation UX**: **box prompts first** (draw a rectangle around a piece ? preview mask ? accept).
- **Segmentation engine**: start with **SAM via a Python service** (fast to iterate, good tooling).
- **Rendering/UI**: **WebGL/canvas** with polygon clipping + transforms (PixiJS or Konva; Pixi tends to be smoother for textured clipping).

## Data model (what we store)
- **Project**
  - `patternImage` (original + cropped version)
  - `patternTransform` (crop/scale/rotate so coordinates are stable)
- **Pieces** (array)
  - `id`
  - `maskRLE` or `polygon` (plus holes if needed)
  - `bbox`
  - `promptHistory` (box coords; optional points later)
- **GlassSheets** (array)
  - `id`, `image`, optional `usableMask`
- **Assignments**
  - `pieceId -> glassSheetId`
  - `textureTransform` (2D affine: translate/rotate/scale)
  - optional `opacity/color` tweaks

## Phase 1 — App skeleton + rendering (prove the “UV” UX)
- **Pattern workspace**
  - Display pattern image
  - Load a few hardcoded polygons (for now) and render them as selectable overlays
- **Texture-in-piece rendering**
  - Assign one glass image to one polygon
  - Implement per-piece transform handles (drag/rotate/scale)
  - Clip texture to polygon with a crisp outline
- **Persistence**
  - Save/load project JSON locally (later: cloud)

**Done when** you can convincingly “wrap” a glass photo into pieces and manipulate it.

## Phase 2 — Piece extraction with SAM box prompts (human-in-the-loop)
- **Pattern import + crop tool**
  - User crops to stained-glass area; store transform
- **Box prompt tool**
  - User drags a box on pattern ? backend returns SAM mask + preview overlay
  - Accept ? create a new piece
- **Polygon generation**
  - Mask ? contour(s) ? polygon + simplify (tunable tolerance)
  - Keep ability to re-run simplification without losing mask

**Done when** you can create a full set of pieces from a pattern with reasonable effort.

## Phase 3 — Glass sheet management + assignment workflow
- Import multiple glass sheet images
- Glass sheet “workspace view” (pan/zoom)
- Piece inspector:
  - Assign glass sheet
  - Duplicate assignment settings to other pieces
- Quality-of-life:
  - Snap rotation (e.g. 15°)
  - Show scale in real units later (optional)

**Done when** you can fully populate a pattern with real glass textures.

## Phase 4 — Automation upgrades (reduce manual work)
- **Line-first auto piece proposals** (connected components / watershed on solder lines)
  - Generate candidate pieces automatically
  - User reviews: accept/merge/split
- **SAM refinement**
  - Optional negative/positive clicks to fix tricky edges
- **Adjacency graph**
  - Enables “match veins across neighbors” helpers later

**Done when** most patterns need only a little cleanup.

## Technical architecture (practical v1)
- **Frontend**: React + Vite + PixiJS (or Konva)
- **Backend**: FastAPI (Python) hosting SAM inference
- **Models**: SAM (start with a standard checkpoint; optimize later)
- **Geometry**: OpenCV contours + Shapely simplify (with guardrails for holes/multiple contours)

## Milestones (fast path)
- **M1 (1–2 days)**: pattern view + polygon clipping + transforms + save/load JSON
- **M2 (2–4 days)**: crop tool + box prompt ? SAM mask preview ? accepted pieces
- **M3 (1–2 days)**: glass sheet library + assignment UI
- **M4 (later)**: auto-detection + refinement tools

