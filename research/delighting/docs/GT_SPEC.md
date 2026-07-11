# GT_SPEC — ground-truth channel specification & production size budget

Report 032, WP-C. Companion to `RENDER_AT_SCALE.md` (per-sample disk is a
first-class scaling constraint) and `MATERIAL_MODEL_V3.md` (what the learned
bets need banked). This document is the authoritative list of every file a
`generate_synthetic.py` sample writes: **semantics, units, encoding (sRGB vs
linear, stated per file — the report-025 lesson), and per-channel measured
size**, plus the production-run pruning/compression decision.

Status legend: **[shipped]** exported by the generator today; **[spec]**
specified here for the 20k production run, wiring called out in §4.

Measured footprint is from a real 1536² sample (`cathedral-green`, seed 42),
`du`/`ls -l` byte sizes. Production config = shadow pair + 5 GT channels.

## 1. The channels

### 1a. Authored textures `tex_*` — [shipped], **PRUNE for production (§3)**

Written by `save_numpy_to_image()` (float EXR, always — the `.png` names are
rewritten to `.exr`). These are the *authored* numpy arrays, before rendering.

| file | semantics | units / encoding | size |
|---|---|---|---:|
| `tex_T.exr` | authored transmittance color T (pre-render) | RGB; colorspace tag `Linear Rec.709`, but **the bytes on disk are sRGB-shaped** relative to the authored linear array (report 025: `img.save()` bakes an sRGB-shaped encode into the file regardless of format; the in-memory datablock the shader consumes is correct). Decode with `srgb_to_lin` for external readers. | 28.3 MB |
| `tex_h.exr` | authored haze/roughness scalar h | BW; `Non-Color`; sRGB-shaped on disk (same 025 caveat). | 28.3 MB |
| `tex_mark_mask.exr` | authored grease-pencil/paint mark coverage | BW; `Non-Color`. | 28.3 MB |
| `tex_height.exr` | authored surface relief height (unitless [0,1]) | BW; `Non-Color`. Report 032: now includes micro-event donuts (seeds/bubbles) baked into relief. | 28.3 MB |
| `tex_normal.exr` | app-facing tangent normal from height | RGB; `Linear Rec.709` (packed `n*0.5+0.5`). Regenerable from `tex_height`. | 28.3 MB |

**All five are regenerable exactly from `(recipe, seed)`** — the authoring is a
pure deterministic function (`author_glass_arrays`), verified byte-stable in
`RENDER_AT_SCALE.md` §5. They are **141.7 MB — 58% of a 242 MB sample** and
carry no information the seed + code don't. This is the single biggest prune.

### 1b. Rendered ground truth `gt_*` — [shipped]

Rendered by `render_ground_truths()` as a samples=1 emission passthrough of the
authored texture, camera-aligned to the photo, view transform `Raw`. Each
channel renders once and saves EXR (32-bit) + PNG (16-bit) from the one result
(the render-eff GT-dedup). **All `gt_*` are sRGB-shaped-encoded relative to
authored units** (report 025; `Raw` does not bypass it) — external readers
decode with `extract.srgb_to_lin`.

| file | semantics | units / encoding | size |
|---|---|---|---:|
| `gt_T.exr` / `.png` | transmitted color T in camera space (the primary supervised target; T calibration 003–023) | RGB; EXR 32-bit / PNG 16-bit; sRGB-shaped. | 25.3 / 9.4 MB |
| `gt_h.exr` / `.png` | haze/roughness in camera space | BW; sRGB-shaped. | 1.6 / 0.06 MB |
| `gt_mark_mask.exr` / `.png` | mark coverage in camera space | BW. | 0.01 / 0.02 MB |
| `gt_height.exr` / `.png` | surface relief in camera space | BW; sRGB-shaped. | 9.0 / 3.4 MB |
| `gt_normal.exr` / `.png` | relief normal in camera space | RGB (packed). | 26.0 / 9.9 MB |

### 1c. Photos — [shipped]

Rendered by `render_sample()`, full Cycles path trace (samples=64), view
transform `Standard`.

| file | semantics | units / encoding | size |
|---|---|---|---:|
| `without_shadow_photo.png` | the capture, no hand shadow | RGB **sRGB** (Standard view transform), 8-bit. | 1.8 MB |
| `without_shadow_photo_linear.exr` | same, scene-linear | RGB **linear**, 32-bit. This is what `check_validation.py` compares to `gt_T.exr`. | 25.1 MB |
| `with_shadow_photo{,_linear}` | shadow-pair variant (production) | same encodings. | +~27 MB |
| `hand_mask.{png,exr}` | shadow-caster mask (production) | BW `Non-Color`. | small |

### 1d. `meta.json` — [shipped]

Recipe/class label, HDRI name+rotation+EV, camera pose, `has_frame` +
`frame_occluders` params (the dark-occluder-through-clear-glass audit trail),
`has_shadow`, `bump_distance_m`, IOR, blender version, seed. ~0.7 KB.

### 1e. Proposed production GT — [spec], see §4 for wiring

| file | semantics | units / encoding | why (report) |
|---|---|---|---|
| `gt_B.exr` | **hidden-glass background render**: the scene with the glass sheet hidden, so the pure transmitted/lensed background `B` is a supervised layer | RGB scene-linear, 32-bit; converges fast → reduced samples OK. | MMv3 / report 027 Bet 1 needs explicit `(T, B, veil)` for its log-space `logT`/`logB` split. |
| `gt_veil.exr` (glossy AOV) | front-surface reflection veil `r_f·E_front` (the additive term) | RGB scene-linear. Free multilayer AOV off the MAIN render. | 029 gap G-4 / MMv3 G2; the term Bet 1 learns to strip. |
| `gt_index.exr` (object-index AOV) | integer object id: sheet alpha vs frame occluder vs mark decal vs background | integer/`Non-Color`. Free AOV. | occluder + mark GT masks (029 gap G-6, mark overhaul). |
| `gt_uv.exr` (UV AOV) | per-pixel sheet UV | RG `Non-Color`. Free AOV. | pixel↔authored-texture correspondence for assembled-pair (report 014). |
| `gt_depth.exr` (Z AOV) | camera depth | `Non-Color`. Free AOV. | future 3D/lamp path, DoF. |

The AOVs (`gt_veil/index/uv/depth`) are **multilayer EXR passes off the single
existing main render** — near-zero extra render cost (render-eff: cost scales
with render *calls*, not passes). `gt_B` is one extra reduced-sample render call.

## 2. Measured per-sample footprint (before)

```
tex_*.exr        (5 × 28.3)   141.7 MB   58%   [regenerable from seed]
gt_*.exr         (5)           61.9 MB   26%
gt_*.png         (5)           22.8 MB    9%
photo_linear.exr (1, validate) 25.1 MB   10%
photo.png + meta                1.8 MB    1%
----------------------------------------------
validate sample               242.3 MB
production (+ shadow pair)   ~ 270    MB   (matches RENDER_AT_SCALE.md's 273 MB)
```

20k × 273 MB = **5.5 TB**. Marketplace egress $10–90/TB ⇒ the transfer bill
($55–500) can exceed compute ($8–18) 10x. Bytes, not FLOPs, are the constraint.

## 3. Production pruning/compression decision (≤100 MB/sample target)

Two levers, both measurement-justified, implemented behind flags so research
purity runs are unaffected:

1. **Drop `tex_*.exr` (`--no-tex-dump`).** −141.7 MB. They are byte-regenerable
   from `(recipe, seed)` (RENDER_AT_SCALE §5) — the seed is in `meta.json`, so
   nothing is lost. Alone this takes 273 → **~131 MB**.
2. **DWAA-compress the remaining float EXRs (`--exr-codec DWAA`).** DWAA is a
   lossy-but-high-quality float codec; on these smooth emission/transmission
   renders it lands ~3–6x with no training-relevant precision loss above
   half-float. Projected on the `gt_*`/`photo_linear`/`gt_B` EXRs (≈112 MB raw):
   → **~20–35 MB**.

| config | per-sample | 20k total |
|---|---:|---:|
| current (uncompressed, tex dumped) | 273 MB | 5.5 TB |
| `--no-tex-dump` only | ~131 MB | 2.6 TB |
| `--no-tex-dump --exr-codec DWAA` | **~60–90 MB** | **1.2–1.8 TB** |

**Decision for the 20k run: `--no-tex-dump --exr-codec DWAA`**, plus the §1e GT.
Even after adding `gt_B` (~5 MB DWAA) and the four multilayer AOVs (~5–10 MB
DWAA total), the sample stays **≤100 MB** — a 3x reduction on the disk/egress
bill that RENDER_AT_SCALE named as the true scaling constraint.

Half-float (`color_depth=16`) on `gt_*`/`photo_linear` is an alternative/addition
to DWAA (another ~2x), acceptable everywhere the values sit in [0,1]; keep
32-bit for `gt_depth` (unbounded).

## 4. Wiring status

- **[shipped]** the §1a–1d channels, GT-dedup render, sRGB-shape encoding note.
- **[spec, this iteration authored the plan not the code]** `--no-tex-dump`,
  `--exr-codec DWAA`, `gt_B`, and the four multilayer AOVs. They are localized:
  the codec/no-tex flags gate `save_numpy_to_image` + `render.image_settings`;
  `gt_B` is one hidden-object reduced-sample render in `render_sample`'s scene;
  the AOVs are `view_layer.use_pass_*` toggles + a multilayer EXR output node.
  Each must re-pass the `--validate` gate (gt_T unchanged) and an extractor
  smoke-run before the fleet launches.

## 5. Encoding cheat-sheet (report-025, do not relitigate at read time)

- `photo.png` → **sRGB** 8-bit. `photo_linear.exr` → **scene-linear** 32-bit.
- Every `tex_*` and `gt_*` file → **sRGB-shaped on disk** relative to its
  authored/linear value (the `img.save()` / `Raw`-view-transform encode). Read
  them through `extract.srgb_to_lin`. The in-memory datablock the shader graph
  consumes is correct linear — the shape is a *file-write* phenomenon only.
- `tex_T`/`tex_normal`/`gt_T`/`gt_normal` carry a `Linear Rec.709` colorspace
  tag; `*_h`/`*_height`/`*_mark_mask` carry `Non-Color`. The tag describes intent;
  the bytes still need the 025 decode.
