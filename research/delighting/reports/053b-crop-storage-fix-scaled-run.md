# 053b — Crop-storage fix (lazy GT warps) + the scaled deployment run

Date: 2026-07-16. Branch `research/delighting-053b` (off `research/delighting` @ `5cc53f6`,
which includes 053/PR #138). Follow-up to `reports/053-deployment-capture-realism.md` after the
lead's post-merge audit.

---

## The problem (report-053 storage claim was WRONG)

Report 053 claimed "≤80 MB/sample — inside the ≤100 MB budget". That measured the **render
only**. `crop_sim.py` then materialized a cropped duplicate of EVERY GT channel into
`<sample>/crop/` (~150 MB/sample), so the pilot actually averaged **~176 MB/sample (max 231 MB;
12 G for 68 samples)** — measured by the lead. At that rate the ~1k plan needs ~176 G against
~29 G free disk. **This section supersedes the 053 storage claim** (053 report carries a
pointer amendment).

## The fix — GT crops are LAZY now

1. **`crop_sim.py`** materializes ONLY: the cropped photo sheet(s) (`crop/*_shadow_photo.png`),
   the detail patches (photo + small GT patches, warped in memory), and the 3×3 homography +
   `capture_geometry` in `meta.json`. No cropped GT duplicates. `warp_channel()` is exported as
   THE single warp convention (LINEAR continuous / NEAREST labels, BORDER_REPLICATE).
2. **`foundation/dataset.py`**: `GlassDelightDataset(crop_view=True)` serves the cropped view by
   lazily warping photo + every GT channel at load time from the stored homography — applied in
   FILE space (before nonlinear decodes like `srgb_to_lin`), so it reproduces exactly what the
   old materialized files contained. Old samples without `crop_sim` meta load unwarped.
3. **Equivalence proven before deleting anything** (`verify_lazy_crop_053b.py`, committed): on
   the 68 pilot samples carrying BOTH representations —
   **68/68 samples, 986 channel files, ALL BIT-EXACT** (integer PNGs exact as required; float
   EXRs measured maxdiff 0.000e+00 — cv2 wrote full float32, so even the 2e-3 tolerance was
   unneeded); loader `crop_view` wiring maxdiff 0.0 on T and photo. Exit 0.
   (One excluded file, documented in the test: `crop/hand_mask.exr` was the shadow-caster's
   512² TEXTURE spuriously warped by the 053 pass with the 1536-grid homography — never a
   training channel, meaningless output, deleted with the rest.)
4. **Retro-slim executed after the test passed**: deleted 918 redundant files from the 68
   `crop/` dirs → pilot **12 G → 4.0 G** (~8 G freed; ~59 MB/sample all-in), disk 30 G → 39 G
   free.

## Addendum — the patch view (CTO catch: patches were emitted, never consumed)

The reviewer's training diet is "**both the full cropped sheet and local detail patches**", but
053 only ever wired the sheet path — `dataset.py` had zero references to `patches/`. Fixed:

- `GlassDelightDataset(patch_prob=0.2)` (configurable): with that probability a `sample_crop`
  draw serves a **native-resolution detail patch** (photo + registered gt_T/gt_h/gt_sigma_s/
  mark from `<sample>/patches/`) instead of a 512² window of the 768-work-res sheet. Patches
  carry the fine texture (seed bubbles, streak edges — the σ_s signal) that the 768 downsample
  destroys. Decode conventions mirror the sheet loaders exactly. B/veil have no patch files →
  zero-filled with `has_B/has_veil` False (the pre-GT-v3 contract). `out["view"]` tags each
  draw `"sheet"`/`"patch"`.
- **Size adaptation choice**: patches (320²) smaller than the crop window (512²) are
  **reflect-padded to crop size with `valid=0` in the pad**. Why this over serving native 320:
  it keeps every draw the same shape (no mixed-size batch collation burden on train.py), the
  reflect content keeps input statistics glass-like instead of black borders, and the valid
  mask guarantees the pad contributes zero loss — so no statistics are distorted where it
  matters (the loss). When crop < patch, the patch is randomly cropped down instead.
- **Holdout unchanged**: a patch inherits its sample's split (drawn from the already
  split-filtered index).
- **Unit-tested** (`verify_lazy_crop_053b.py::patch_view_check`): patch↔sheet registration
  bit-exact on 15 patches (patch gt_T == the recorded window of the lazily-warped sheet);
  78 loader patch draws load at the right shape; split respected on train AND test.

## The scaled run (NOT 1k locally — plainly)

Per the lead's launch plan: with the honest ~80 MB/sample render cost and ≥5 GB headroom
required, this disk supports ~200 additional identities, not ~500. **We are NOT rendering 1k
locally; the 20k (and the 1k, beyond this set) was always a cloud job.** Launched:

```
render_farm.py --out pilot_053_out --seed 600 --total 200 --shards 1 --light-variations 2 \
  --hdri-dir hdri_pack --deploy-scene --cover-recipes --gt-b --gt-aov --no-tex-dump \
  --exr-codec DWAA --shadow-prob 0.3
```

= seeds 600–799 × 2 lightings = **400 samples**, joining the existing 68 → a **~468-sample
deployment set**. A detached disk guard (`/tmp/diskguard053b.sh`, 60 s poll) stops the farm
cleanly if free space drops under 5 G.

After the render: the FIXED `crop_sim.py` over the new samples (photos+patches only), board
refresh, and `rclone copy` of the full `pilot_053_out` to
`gdrive:vitrai-lab-backup/pilot_053_deployment` (lab backup-before-cleanup policy).

<!-- SCALED_RUN_RESULTS: filled after completion -->
