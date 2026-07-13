# Interaction performance baseline

Captured from production commit `adb59c6` before the interaction refactor.

## Production build

- Main JavaScript: 695.80 kB raw / 212.44 kB gzip.
- CSS: 30.01 kB raw / 5.93 kB gzip.
- SAM worker: 364.34 kB.
- ONNX WASM: 21,279.20 kB.
- Production build succeeds and warns that the main JavaScript chunk exceeds 500 kB.

## Pointer-path work counts

These counts are deterministic consequences of the existing handlers and are the
guardrail used for before/after comparison. A five-second gesture at 60 pointer
events per second represents approximately 300 movement events.

| Interaction | Work per movement before refactor | Approximate five-second count |
| --- | --- | ---: |
| Glass-piece drag | One `updatePieceTransform`, complete pieces-array map, project replacement, and App/panel reconciliation | 300 project writes/maps |
| Glass-piece rotation | Same durable project update path as drag | 300 project writes/maps |
| Pen hover | One complete vertex scan; additional length/alignment scans after a draft starts; up to five React state setters | 300+ full geometry scans and up to 1,500 setters |
| Pencil stroke | One growing immutable point-array copy and panel render | 300 copies/renders |
| Pan | One React `setPan` and owning-panel render | 300 panel renders |
| Ctrl-wheel/pinch zoom | React `setZoom` plus `setPan` and owning-panel render | Up to 600 setters |

## Geometry scaling reference

The existing Pen scan was sampled synthetically using the same flatten-and-scan
shape. Mean time for one scan was approximately 0.034/0.067/0.151/0.578 ms for
25/100/250/500 six-vertex pieces, and 0.266/1.566/3.227/5.799 ms for the same
piece counts at 96 vertices. This excludes React reconciliation and Konva draws.

## Behavior cases

`pnpm test:interaction` locks deterministic fixture generation, vertex snapping,
horizontal/vertical alignment, Shift alignment, equal-length matching, canvas
edge/fraction snapping, and fixed Pencil simplification outputs.

The real app type-check has eight pre-existing errors in App, GlassLibraryDialog,
ResultPanel, SheetPanel, and Tutorial files. Phase 0 adds no new errors.
