# GT_SPEC — ground-truth channel specification & production size budget

Report 032, WP-C. Companion to `RENDER_AT_SCALE.md` (per-sample disk is a
first-class scaling constraint) and `MATERIAL_MODEL_V3.md` (what the learned
bets need banked). This document is the authoritative list of every file a
`generate_synthetic.py` sample writes: **semantics, units, encoding (sRGB vs
linear, stated per file — the report-025 lesson), and per-channel measured
size**, plus the production-run pruning/compression decision.

Status legend: **[shipped]** exported by the generator today; **[spec]**
specified here for the 20k production run, wiring called out in §4.

> **Report 037 update:** every §1e channel and both §3 levers are now
> **[shipped]** as working flags (`--no-tex-dump`, `--exr-codec`, `--gt-b`,
> `--gt-aov`); §4 has the wiring/verification results and §6 the Blender-5
> reader/mechanism findings discovered during the wiring (multilayer-only
> File Output node; the renderer samples the *file-backed* sRGB-shaped
> texture — a mechanism correction to the report-025 note).

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
| `tex_mark_mask.exr` | authored **dark** grease-pencil/marker mark coverage (report 037 item B narrowed this to dark-only — white marks moved to `tex_mark_white`) | BW; `Non-Color`. | 28.3 MB |
| `tex_mark_white.exr` | authored **white** grease-pencil/paint-pen mark coverage — report 037 item B. Disjoint from `tex_mark_mask` (each authored mark is one color; see `generate_marks`). | BW; `Non-Color`. | 28.3 MB |
| `tex_mark_index.exr` | authored per-mark instance id, **normalized** `id / MAX_MARKS` (`MAX_MARKS=4`) — report 037 item B. NOT a raw integer: report 025's sRGB-shape bake is only verified for `[0,1]` inputs, so raw ids (which can exceed 1) are avoided. Decode: `round(srgb_to_lin(pixel) * MAX_MARKS)`; `0` = no mark. | BW; `Non-Color`. | 28.3 MB |
| `tex_height.exr` | authored surface relief height (unitless [0,1]) | BW; `Non-Color`. Report 032: now includes micro-event donuts (seeds/bubbles) baked into relief. | 28.3 MB |
| `tex_normal.exr` | app-facing tangent normal from height | RGB; `Linear Rec.709` (packed `n*0.5+0.5`). Regenerable from `tex_height`. | 28.3 MB |
| `tex_sigma_s.exr` | authored forward-scatter PSF width σ_s (MMv3 G1, report 043 item 1) — drives the one transmission lobe's Roughness (the graded LOCAL background blur; replaces the 037 opal-stopgap second lobe). `h` is now the OUTPUT_CONTRACT §0 compatibility projection `a_glow + (1−a_glow)·σ_s`, not an independent field. | BW; `Non-Color`; sRGB-shaped on disk (025 caveat). | 28.3 MB |
| `tex_a_glow.exr` | authored diffuse self-glow / opal opacity a_glow (MMv3 G1, report 043 item 1) — weight of a dedicated Translucent-BSDF mix (true Lambertian transmission). Zero everywhere except the opal family (`decompose_haze`). | BW; `Non-Color`; sRGB-shaped on disk. | 28.3 MB |

**All nine are regenerable exactly from `(recipe, seed)`** — the authoring is a
pure deterministic function (`author_glass_arrays`), verified byte-stable in
`RENDER_AT_SCALE.md` §5. Report 032's five totaled **141.7 MB — 58% of a
242 MB sample** and carry no information the seed + code don't; the two new
mark channels and the two report-043 MMv3 channels add ~4×28.3 MB pre-prune
(negligible after `--no-tex-dump`, which deletes all nine, same as the other
five). This is the single biggest prune.

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
| `gt_mark_mask.exr` / `.png` | **dark**-mark coverage in camera space (report 037: narrowed from "any mark" to dark-only) | BW. | 0.01 / 0.02 MB |
| `gt_mark_white.exr` / `.png` | **white**-mark coverage in camera space — report 037 item B. Disjoint from `gt_mark_mask`. | BW. | 0.01 / 0.02 MB |
| `gt_mark_index.exr` / `.png` | per-mark instance id in camera space, normalized `id/MAX_MARKS` — report 037 item B, texture-space per-mark GT (see §1e's `gt_index_B` row for why marks can't use an object-index AOV). Decode: `round(srgb_to_lin(pixel) * 4)`. Verified round-trip on a real render: clean id clusters recovered, small AA-edge noise at mark boundaries (same soft-edge behavior as `gt_mark_mask`). | BW. | 0.01 / 0.02 MB |
| `gt_height.exr` / `.png` | surface relief in camera space | BW; sRGB-shaped. | 9.0 / 3.4 MB |
| `gt_normal.exr` / `.png` | relief normal in camera space | RGB (packed). | 26.0 / 9.9 MB |
| `gt_sigma_s.exr` / `.png` | forward-scatter PSF width σ_s in camera space (MMv3 G1, report 043 item 1) | BW; sRGB-shaped. | 7.6 / 3.1 MB (DWAA, wispy-white — structured field; near-flat recipes compress far smaller) |
| `gt_a_glow.exr` / `.png` | opal self-glow opacity a_glow in camera space (MMv3 G1, report 043 item 1). Round-trip verified on a real render: `srgb_to_lin(gt_h) == a_glow + (1−a_glow)·σ_s` to DWAA tolerance (mean residual 1.4e-4). | BW; sRGB-shaped. | 7.9 / 3.0 MB (same caveat) |

**Report 043 size delta + reader caveat**: the two new GT channels cost
**+19 MB measured** on a production-shaped wispy-white sample (65 MB → 84 MB,
`--no-tex-dump --exr-codec DWAA --gt-b --gt-aov`) — still ≤100 MB (§3 target)
but a +29% delta at 20k scale (~+380 GB); if the budget tightens, `gt_h` is
now redundant with (σ_s, a_glow) via the §0 projection and is the natural
prune (kept for OUTPUT_CONTRACT compatibility). Reader caveat discovered
while verifying (pre-existing, NOT introduced by 043): **BW single-channel
EXRs written with `--exr-codec DWAA` are not cv2-readable** (`cv2.imread`
returns None for the DWAA+Y-channel combination — affects `gt_h`,
`gt_height`, `gt_sigma_s`, `gt_a_glow`, mark channels on any DWAA dataset);
read them via `extract.load_aov_exr` (OpenEXR package, works on both plain
and multilayer files) and decode with `srgb_to_lin` as usual.

**Report 037 item B (mark overhaul)**: `generate_marks()` (replaces the old
`generate_scribble_mask`) authors 1–4 marks per sample, each an anti-aliased
(smoothstep distance-field, not a fixed-sigma blur) stroke in one of 4 shape
families (scribble / straight+kink / dot / crossing tick), one of 2 colors
(dark marker or white grease-pencil/paint-pen, recipe-weighted — white is the
majority on the dark family since a real dark marker is illegible there, the
reverse on light/clear recipes), with random thickness. **Finding during
verification**: a plain reflective BSDF for the white marker renders BLACK,
not white — measured directly (dark-deep, seed 7): white-mark pixels averaged
0.055 photo luminance vs 0.247 background (i.e. darker than the glass itself).
Root cause: the scene's front hemisphere is deliberately near-unlit (`DarkWall`
wall_gray=0 without `--specular`), so an opaque reflector there renders black
regardless of base color — the dark marker "worked" only by coincidence (dark
base + no light = dark result, same as light base + no light). Fixed with a
modest constant self-emission added to the white marker's BSDF (Emission
color (0.85,0.83,0.77) strength 0.6, `ShaderNodeAddShader`) so it reads
reliably bright (0.69 measured post-fix on the same pixels) regardless of
scene front-lighting, while still responding to a real front light source
(a future `--specular`/IBL pass) additively rather than being capped.

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

**Report 037 item D additions**: `camera_pose.jitter` (`loc_x/loc_z/rot_x/
rot_z`) — the per-sample camera-randomization draw, previously applied but
never recorded (so nobody could audit how much pose variety a given sample
actually got); the range itself widened from ±0.02 m/±0.05 rad to
±0.045 m/±0.09 rad. `frame_occluders[].material` — the window-frame material
family (`dark_wood`/`black_metal`/`weathered_wood`/`white_trim`/
`brushed_aluminum`, see `FRAME_MATERIAL_FAMILIES`), alongside the existing
`darkness` field (now an approximate luminance of the chosen material's base
color, not a raw uniform draw — kept for backward-compat naming). Note: half
the material families are near-black (preserving the original dark-
occluder-through-clear-glass audit trait), but `white_trim`/`weathered_wood`/
`brushed_aluminum` are meaningfully LIGHTER than before — widening what the
occluder trap actually exercises (a bright occluder behind clear/light glass
is a different, also-real capture scenario, not just decoration).

### 1e. Production GT — [shipped, report 037] behind `--gt-b` / `--gt-aov`

| file | semantics | units / encoding | why (report) |
|---|---|---|---|
| `gt_B.exr` | **hidden-glass background render**: the scene with the glass sheet hidden, so the pure transmitted/lensed background `B` is a supervised layer | RGB scene-linear, 32-bit plain EXR (cv2-readable); rendered at `max(8, samples//4)` — converges fast with no glass transmission paths left. | MMv3 / report 027 Bet 1 needs explicit `(T, B, veil)` for its log-space `logT`/`logB` split. |
| `gt_veil.exr` (glossy AOV) | front-surface reflection veil `r_f·E_front` = Glossy Direct + Glossy Indirect (compositor Add) | RGB scene-linear, raw render units (NOT sRGB-shaped — this is a Cycles pass, not a texture write). Multilayer, read via `extract.load_aov_exr`. **NOT zero without `--specular`** — see §6 finding. | 029 gap G-4 / MMv3 G2; the term Bet 1 learns to strip. |
| `gt_index.exr` (object-index AOV, MAIN render) | **sheet-alpha mask** (pass_index 1). Measured: occluders/caster NEVER appear here — the full-frame glass is the camera's first hit and the index pass does not see through transmission. | float ids, `Non-Color`, multilayer. | sheet alpha (useful once camera jitter can expose sheet edges). |
| `gt_index_B.exr` (object-index AOV, gt_B render) | **occluder mask**: frame occluder = 2, shadow caster = 3, backlight/world = 0 — first-hit labels with the glass hidden. Written only when `--gt-b --gt-aov` both on. | float ids, `Non-Color`, multilayer. | occluder GT mask (029 gap G-6 trap audit). Mark masks stay texture-space (`gt_mark_mask`, plus report 037's per-mark index) — marks are baked into the material, not separate geometry, so they cannot appear in any object-index pass. |
| `gt_uv.exr` (UV AOV) | per-pixel sheet UV (X,Y; Z unused) | float, `Non-Color`, multilayer. | pixel↔authored-texture correspondence for assembled-pair (report 014). |
| `gt_depth.exr` (Z AOV) | camera depth, meters | float 32-bit, `Non-Color`, multilayer. Measured 0.394–0.407 m on the verification sample (glass at 0.4 m). | future 3D/lamp path, DoF. |

The AOVs (`gt_veil/index/uv/depth`) are **multilayer EXR passes off the single
existing main render** — near-zero extra render cost (render-eff: cost scales
with render *calls*, not passes; the compositor graph is attached for the one
canonical without-shadow render and detached immediately after). `gt_B` is one
extra reduced-sample render call (~8 s measured, samples=16 @1536²).

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
- **[shipped, report 037]** `--no-tex-dump`, `--exr-codec`, `--gt-b`,
  `--gt-aov` — all four flags implemented and verified (this iteration) against
  a real render, not just authored as a plan. Verification performed:
  - **Item-A validate gate**: 13/13 recipes, default flags (all new flags OFF),
    reproduce report 032 §5's committed MAE to the 4th decimal (max delta
    0.0001) — confirms the new code paths are byte-neutral when unused.
    `results/037/validate_gate_037_A.txt`.
  - **1-sample production-flag verification** (`cathedral-green` seed 500,
    `--no-tex-dump --exr-codec DWAA --gt-b --gt-aov`, no `--validate` so the
    shadow pair renders): all 6 new files (`gt_B`, `gt_veil`, `gt_index`,
    `gt_index_B`, `gt_uv`, `gt_depth`) write successfully; `tex_*.exr` (5
    files) confirmed absent post-run; every file decodes — plain EXRs via
    `cv2.imread`, the 4 multilayer AOVs via the new `extract.load_aov_exr`
    (requires the `OpenEXR` pip package, confirmed installed in both the
    project `.venv` and Blender's `PYTHONPATH` site-packages this iteration).
  - **Measured footprint**: production-shaped sample (shadow pair + all GT)
    = **56 MB**; validate-shaped sample (single light, no shadow pair) =
    **49 MB**. Both comfortably inside the ≤100 MB target and better than
    §3's ~60–90 MB projection.
  - **Unit sanity**: `gt_depth` measured 0.397–0.403 m (glass at 0.4 m,
    matches the 0.394–0.407 m range this doc already cited); `gt_index`
    (main render) reads uniformly 1.0 (sheet, no occluders in the
    `has_frame=false` verification sample — consistent with the "sheet-alpha
    only, occluders never appear here" note below); `gt_index_B` reads
    uniformly 0.0 (no occluders present ⇒ background label, consistent).
  - See §6 for a genuine finding (not just a mechanism note) surfaced during
    this verification: `gt_veil` is **not** zero without `--specular`.
  - Not yet done: an extractor smoke-run over `eval_synthetic.py`'s oracle
    harness with the new flags (item A's brief calls for a 1-sample render
    verification, which is complete; a full extractor pass is fleet-launch
    due-diligence, not blocking this report).

## 5. Encoding cheat-sheet (report-025, do not relitigate at read time)

- `photo.png` → **sRGB** 8-bit. `photo_linear.exr` → **scene-linear** 32-bit.
- Every `tex_*` and `gt_*` file → **sRGB-shaped on disk** relative to its
  authored/linear value (the `img.save()` / `Raw`-view-transform encode). Read
  them through `extract.srgb_to_lin`. The in-memory datablock the shader graph
  consumes is correct linear — the shape is a *file-write* phenomenon only.
- `tex_T`/`tex_normal`/`gt_T`/`gt_normal` carry a `Linear Rec.709` colorspace
  tag; `*_h`/`*_height`/`*_mark_mask` carry `Non-Color`. The tag describes intent;
  the bytes still need the 025 decode.

## 6. Report 037 findings (Blender-5 mechanism + a real data-quality gap)

**Multilayer-only File Output node.** Blender 5.0's compositor
`CompositorNodeOutputFile` node no longer supports the old "plain EXR, one
file per socket" mode — every output is `OPEN_EXR_MULTILAYER`, with channel
names like `gt_veil.R`/`.G`/`.B`. `cv2.imread` cannot parse this (confirmed:
returns `None`, even for a single-item multilayer file). The four new AOV
files (`gt_veil`, `gt_index`, `gt_uv`, `gt_depth`, and `gt_index_B`) therefore
need `extract.load_aov_exr` (backed by the `OpenEXR` pip package, not cv2).
Every other file in this doc (`tex_*`, `gt_T`/`gt_h`/`gt_height`/`gt_normal`/
`gt_mark_mask`, `gt_B`, `photo_linear`) is unaffected — still written via the
older `img.save()`/`save_render()` path, still a plain single-part EXR,
still cv2-readable.

**The disk write is load-bearing for rendering, not just export.** A
controlled probe (flat 0.09 texture, emission passthrough, samples=1, Raw
view transform) showed the renderer samples the *file-backed* image, not the
in-memory pixel buffer: the saved-EXR case rendered `0.3318 == srgb_encode
(0.09)`, while an unsaved datablock with an identical buffer and colorspace
tag rendered `0.0900` (raw). So the sRGB-shaped-on-disk convention this doc's
§5 describes for every `tex_*`/`gt_*` file is not an independent export-time
choice — it's *how the shader gets the right units at all*. This corrects
report 025's inference that "the in-memory datablock the shader consumes is
correct linear" (025's practical conclusion — decode files with
`srgb_to_lin` — still stands; only the mechanism explanation was wrong).
Practical consequence: `--no-tex-dump` cannot skip the `tex_*` save and
substitute an in-memory image — a first wiring attempt tried that and every
render silently changed units (cathedral-green validate MAE moved
0.0232 → 0.0142, caught by the gate). The shipped implementation still
writes `tex_*` to disk (the renderer needs the file) and deletes the files
*after* the sample's renders complete — the prune is real (§2/§3's 141.7 MB
is not written to the final dataset) but happens post-hoc, not by skipping
the write.

**Finding: `gt_veil` is not zero without `--specular`, and the "veil-free"
assumption behind every dataset generated before this report is wrong.**
`docs/GT_SPEC.md` (pre-037) and the report-032 `--specular` code comment both
claimed the front-surface glossy lobe is "invisible" without `--specular`
because the interior `DarkWall` behind the camera is pure black
(`wall_gray=0.0`) — nothing bright to reflect. Measured on two independent
verification samples (`cathedral-green` seed 500, `dark-deep` seed 777, both
default flags i.e. `--specular` OFF): `gt_veil` is nonzero across
**100% of pixels** on both samples, and is **not small** — per-pixel veil
share of the total (transmission + veil) signal has median 40%
(cathedral-green) to 81% (dark-deep), with p99 up to 4.6x–10x the
transmitted signal (bright localized highlights). This is not a `--specular`
regression; `--specular` was never the thing gating this — the mechanism is
independent. Root cause (not yet fixed, flagged for the next iteration): the
glass surface's normal is bump-mapped (the "hammered/rolled relief" that
"affects glossy and transmitted lensing," `generate_synthetic.py` L1151), so
the reflection cone fans out well beyond the near-normal direction the
camera-aligned geometry assumes; combined with the finite 5×5 m `DarkWall`
plane sitting behind the camera, enough reflected rays miss the wall's edges
and see the bright HDRI sky/sun directly (Cycles' Glossy Direct pass
includes environment-light contributions reached via NEI/MIS, not just
geometry the wall would block for a *direct camera view*). Consequence:
**every synthetic sample generated to date (all recipes, `--specular` on or
off) carries a real, often large, unaccounted-for front-surface reflection**
— the extractor's "no veil" assumption, which report 032 §7 called out as
only really being stress-tested once MMv3-G2's front IBL lands, is *already*
being violated by the existing default scene, just not documented until now.
This is a data-quality finding, not a code bug in this report's `--gt-aov`
wiring (the channel faithfully exports whatever the shader produces); the
fix (enlarge/reshape the occluder so it fully blocks the bump-fanned
reflection cone, or accept the veil and rely on `gt_veil` for supervision)
is scene work for a future iteration, not landed here.
