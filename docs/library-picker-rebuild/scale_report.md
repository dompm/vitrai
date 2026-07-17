# Bullseye texture-scale audit

Part of the consolidated **library release**. Reproducible: `python scripts/scale_audit.py`
(venv `~/Documents/fastbook/.venv`, has cv2+SIFT). Sidecar: `scale_audit.json`.
Boards: `scale_boards/`. Detectors: `scripts/scale_audit_lib.py`.

## The bug

Bullseye product galleries share **one photo set** across the cart size variants
(10x10 / 17x20 half / 35x20 full). The library builder stamps `real_world_width_in`
from the *cart* size — 10.0in for the `-1010` variant — onto whichever gallery image
the picker chose. But the picker frequently chose a **zoomed detail or macro crop**
that shows only a few inches of glass, not a full sheet. The app scales textures by
`pxPerUnit = original_width_px / real_world_width_in`, so a macro that really spans
~3in but is stamped 10in tiles **~3x too coarse** at physical scale. Verified by the
lead on 000100-0051-F; reproduced here (SIFT `_01`→`_03` scale 0.31, 305 inliers).

## What the whole-sheet photo actually is

The whole-sheet studio shot is a **fixed studio sample**, not a per-product sale
size: measured aspect (w/h) is a very tight **1.326** (median; p10–p90 1.318–1.331)
across 361 cleanly-measured products, matching *none* of the sale sizes (10x10=1.0,
half=1.176, full=1.75).

**Two calibration checks were run (lead-requested), both negative for a cleaner anchor:**

1. **Rotation / tilt — rejected.** The 1.326 is *not* a studio-tilt artifact on a
   17x20 (1.176) sheet. Fitting the sheet as a rotated rectangle (`cv2.minAreaRect`)
   gives a **rectified** aspect of **1.327** (identical to the axis-aligned bbox) with
   **median tilt ~0°** across all 361 — the sample genuinely has a ~1.327 physical
   aspect.
2. **Reeded-rib physical anchor — consistent but not closable.** The 8 reeded
   products share one physical roller: 5/6 measurable whole-sheets converge on
   **~80–83 ribs across the full sheet width** (rib period 12.7–13.2px; strong
   agreement). But converting ribs→inches needs a ribs/inch reference, and none is
   obtainable: Bullseye publishes no rib pitch, and the 2x2in **Color Sample** photos
   (a known physical size) are unusable — each product's sample `_02` is a *generic
   multi-sample stock photo* (wrong SKUs) and its `_01` is a sub-2in full-bleed macro
   (no visible sample edge). So the rib work confirms internal consistency (one
   roller, one sample size) but cannot pin the absolute.

Its **absolute** long side therefore remains **not recoverable from these images**.
We adopt `SAMPLE_LONG_IN = 10.0in` as a documented assumption (anchored to the 10x10
convention + the geometric short-side ≤ 20in bound → short side 7.54in). **Every
relative correction below is independent of this constant**; a single global retune
of `SAMPLE_LONG_IN` rescales all Bullseye scales together if a physical reference
(a published rib pitch, or an in-frame shipping-label measurement) lands. **← flag for CTO.**

**Candidate sample identity (UNVERIFIED, lead-noted).** The confirmed 1.327 aspect is
within rolled-edge tolerance of **4:3 (1.333)** — consistent with a **metric 40×30cm
studio blank (15.75×11.8in)**, a very common product-photography format. If that is the
truth, `SAMPLE_LONG_IN ≈ 15.75`, not 10.0 — **a 1.57× shift on every Bullseye scale**.
We do **not** switch the constant on this speculation; we record it so one physical
measurement adjudicates instantly. The ~80–83 ribs/sheet then implies a rib pitch of:

| hypothesis | SAMPLE_LONG_IN | implied reeded rib pitch |
|---|---:|---:|
| 10x10 convention (current) | 10.0in | ~3.1 mm |
| 40×30cm studio blank | 15.75in | ~4.9 mm |

So a tape measure on **either** the rib pitch of any physical reeded sheet **or** the
size of any studio-style sample closes it (see the release checklist's deferred item).

## What the field means (registry semantics)

`real_world_{width,height}_in` describes **the swatch IMAGE's physical footprint**
(inches of real glass spanned by the image), because the app needs inches-per-pixel
(`pxPerUnit = original_width_px / real_world_width_in`). It is **not** the cart
variant's purchasable sheet size — that is separate product metadata. **The original
bug was exactly this conflation**: the builder stamped the 10x10 cart size onto a
macro image that spans ~3in of glass. Corrected values (and nulls) here always refer
to the image footprint.

## Why we don't just "measure" the macro footprint

The detail-shot → whole-sheet bridge does **not** hold at scale (all tried on the
verified iridescent products):

| method | result |
|---|---|
| SIFT `_03`→`_02` / `_01`→`_02` | ≤9 good matches, **0 RANSAC inliers** — whole-sheet too zoomed-out / sheen-shifted |
| multi-scale template match (NCC) | peak ~0.08 (noise) |
| FFT texture-period ratio | dominated by iridescent colour blobs, not ripple |

So a per-product **point estimate** of a macro's footprint is not defensible (the
lead's "≤6.2in" was a sound upper *bound*). The fix is therefore **pick the right
image**, not measure the wrong one — the whole-sheet shot has a well-defined scale,
and a crop *within* it is exact by pixel ratio (no cross-image bridging needed).

## Results (423 Bullseye products)

| confidence tier | n | registry action |
|---|---:|---|
| `A_wholesheet_pick` (measurable whole-sheet) | 213 | keep width; **make height aspect-consistent** (10 square 10x10 stamps fixed) |
| `A_wholesheet_lowconf` (whole-sheet, near-white unmeasurable) | 15 | keep dims, low confidence |
| `C_detail_crop` (partial crop) | 111 | **null** the 99 still carrying the ~10in stamp; flag re-pick |
| `C_macro_fullbleed` (interior macro) | 84 | **null** (known-wrong ~10in); flag re-pick |

- **183 rows nulled** (`real_world_{width,height}_in = null`) — never keep a
  known-wrong 10.0; **240 kept** measured/plausible dims.
- **198 rows flagged `needs_repick: true`** (registry) with per-product targets in
  the sidecar (`recommendation`, `repick_real_world_width_in`, `repick_note`).
- Whole-sheet detected for **388/423 (91%)**, cleanly measurable for **361 (85%)**.

### Iridized products (117, keyed off striker-pivot's `iridized` flag)

Per the lead's transmission-mode + split-backdrop refinements (the app preview is
backlit, so a black-backed *reflection* crop misreads transmitted colour, and a crop
across a split black/white backdrop fabricates two-tone glass):

- **14 `irid_reflection_pick`** — swatch taken from the black/reflection region → bad
  colour, must be re-picked to the transmission (white) side.
- **91 `irid_needs_transmission`** — not a clean transmission whole-sheet pick →
  recommend transmission-side re-pick.
- **0 `crop_spans_seam`** on current crop_boxes (seam-straddling crops were not found;
  the reflection-side crops like 001101-0044-F sit entirely on the dark half).

## Limitations (honest)

- **Absolute scale** is a single documented assumption (see above), not measured.
- **Near-white / clear glass on white backdrop** defeats segmentation: 35 products
  have no detectable whole-sheet and 15 whole-sheet picks are unmeasurable (~12% of
  the catalog, low confidence — dims mostly kept, flagged). See `board_06`/`board_07`.
- For **all-macro iridized products** with no true studio shot, the whole-sheet
  "anchor" can itself be a detail shot — the null correction still holds, but the
  re-pick target for those is only as good as the gallery.
- Thumbnails in the boards can render the white studio backdrop shifted (a viewer
  colour-management artifact); **detection is pixel-based** (corner pixels are true
  255/255/255) and unaffected.

## Recommendation & what shipped here

1. **Registry (this PR):** 183 known-wrong dims nulled, 10 whole-sheet heights made
   aspect-consistent, 198 `needs_repick` flags. Only Bullseye rows touched; every
   other row byte-identical. Frontend made null-safe (`GlassLibraryDialog.tsx`:
   fallback width + "scale TBD" label).
2. **Pick preference (implemented, gated):** `preferred_gallery_image()` in
   `build_swatch_library.py` encodes the measured-better rule (whole-sheet;
   transmission side for iridized). `SCALE_AWARE_REPICK = False` until the release's
   **image-hosting** item lands — activating it re-picks images, which regenerates the
   gitignored `catalog_images` crops (the exact gitignored-asset gap that forced the
   #141 revert).
3. **Future work (out of scope, lead-noted):** for clear/near-clear iridized glass the
   honest white-side crop is low-information; rendered swatches (material maps over a
   standard backdrop) are the eventual fix.
