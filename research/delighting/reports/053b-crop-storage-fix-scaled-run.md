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

## Pre-flight fixes (lead's foundation/ review — required before any training run)

1. **CRITICAL — the 040 gradient fixes never reached trunk.** `backbone.decode()` still
   wrapped the VAE in `torch.no_grad()` and `train.py`'s T loss was pixel-space through it —
   T's supervision was SEVERED (the exact 040 bug, live on trunk; T only moved as a side
   effect of the aux heads). Ported all three 040 commits onto this branch (drift-aware —
   the 8-channel σ_s AuxHead and phone-ISP loader are preserved): `a5577a2` (diagnosis),
   `36bc550` (latent-space T supervision — MSE vs `z_T_hat` with the shadow-upweighting
   adaptive-pooled to latent res; the durable fix), `f6bd8c1` (`need_T` opt-in decode —
   decode only on logging steps; conf gets no supervision on skipped steps). Also ported
   `test_grad_flow.py` (per-head isolation test, extended to 7 heads incl. σ_s) and wired
   it UNCONDITIONALLY at the top of `train_loop` — not just the Modal entrypoint.
   **Acceptance evidence**: preflight passes with nonzero grads for EVERY head
   (T grad_norm 0.60; h 26.2; σ_s 28.2; B 32.7; shadow 47.9; mark 115.2; conf 109.6);
   **mutation-verified** (detaching z_T_hat in the output makes the test fail naming
   exactly `['T']`); 20-step tiny smoke on the pilot data shows the T loss MOVING
   (0.1241 → 0.1003 → 0.1065 — under the bug it was bit-identical for 100+ steps).
2. **HIGH — unbounded loader cache.** `GlassDelightDataset._cache` grew without bound
   (~30-40 MB work-res components/sample × a 268-468-sample pilot ≈ 10-19 GB RAM). Now a
   bounded LRU (`cache_size=64` ≈ 2.2 GB cap, `OrderedDict` with move-to-end/evict-oldest).
   Verified: 20 loads at cap 8 → cache holds exactly 8.
3. **MEDIUM — eval never saw a phone-processed input.** `eval_foundation` ran the test set
   on CLEAN linear renders only — undermining the 053 realism premise — and never measured
   the held-out `wide_edge` preset. Now every test photo also runs through EACH ISP preset
   (deterministic per-sample rng); metrics are reported per-preset (`report["per_preset"]`
   + a table section), the held-out device broken out (✋), and the clean row kept as the
   headline for continuity with all pre-053b numbers.
4. **LOW — non-square crop_view draws could crash collate.** The sheet path used
   `c=min(crop,H,W)`; a user-crop homography can shrink the grid below `crop`, and
   `np.stack` dies on mixed sizes mid-run. Sheet draws are now exactly `self.crop`
   (reflect-pad + `valid=0` in the pad — the patch-path policy). Verified: 12/12 draws at
   512² under crop_view.

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

## SCALED_RUN_RESULTS

**Final set: 348 samples (68 original + 280 net new; one disk-guard-interrupted partial
dir, `wispy-white__seed740__light4661`, deleted — no meta.json, mid-write when the guard
fired). This is 74% of the planned 468 (348/468) and 87% of the seed-range target (280/324
new samples from the planned 200 seeds × 2 lightings) — the disk guard did its job:
it stopped the farm CLEANLY at 09:56 on 2026-07-19 when free space hit 1.8 GB, exactly per
its design, and no partial/corrupt sample beyond the one deleted above survived. Decision
(lead, after the multi-day gap): stop here — 348 is a perfectly adequate deployment-pilot
size; do not resume rendering.**

### Composition

- **17/17 recipes** covered, reasonably balanced (18–24 samples/recipe — the 4 lightest
  are the four newest report-037 taxa: confetti-shard, fracture-streamer, ring-mottle at
  18, baroque-rolling-wave at 20 — `--cover-recipes` cycles evenly but the run stopped
  mid-cycle).
- **174 unique seeds** (500–739 of the planned 500–799 range) × up to 2 light variations;
  **23 distinct HDRIs**.
- **Shadow 31%** (107/348; target 0.3 — on target). **Front light 66%** (230/348; target
  0.7 — slightly under, sampling noise at this size). Specular + dim interior 100% (deploy
  default, unconditional).
- **Background depth mix**: 0.1 m ×84 · 0.5 m ×70 · 2 m ×64 · ∞/HDRI-only ×130 (70 by roll
  + 60 pre-existing "no-bg-roll" from validate-adjacent early samples).
- **Capture geometry**: tilt_scale_crop 226 · perspective_rectified 122.
- **Storage**: mean **60.6 MB/sample**, max 90 MB — comfortably inside the ≤100 MB budget
  and close to the 053b fix's ~59 MB/sample projection (the lazy-crop fix holds at scale).
  Total on disk: **20 G** for 348 samples.
- **Holdout partition** (dataset.py rules, precedence seed→recipe→hdri→geometry): train 84
  · seed%5 70 · recipe-family 62 · hdri 78 · geometry 54 → **264/348 test (76%)**. Still
  over-covers held-out families for eyeball purposes, as noted in 053's original pilot
  stats — same rebalancing note applies at full 20k scale (lower `--perspective-prob`,
  render more seeds so the fixed-fraction reservations shrink as a share of the whole).

### Per-stage timing (for pricing the future cloud run)

Aggregated from the scaled run's raw `[TIMING]` stage prints (`_farm/shard0_try1/log.txt`,
9163 stage calls; the farm-level `timings_pid*.json`/`farm_summary.json` never got written
because the disk guard killed the process before `dump_timings` could run — this is the
honest raw-log reconstruction, not a rounded summary file):

| stage | total (of 372 main_render calls started) | share | avg/call |
|---|---|---|---|
| `gt_render` | 24085s | 68.6% | 8.57s (n=2809 — ~7.5 GT channels rendered per sample) |
| `main_render` | 10324s | 29.4% | 27.75s |
| `image_encode_io` | 454s | 1.3% | 0.12s |
| `texture_authoring` | 243s | 0.7% | 1.05s |
| `scene_build` | 11s | 0.0% | — |
| `hdri_load`/`hdri_download` | 0.3s | 0.0% | — |

**Implied per-sample wall cost ≈ 94s** (stage-sum / main_render count), consistent with the
clean-pace measurement taken mid-run (76–139s/sample, median ~76s — the 94s here includes
the 372 main_render STARTS vs 281 samples actually COMPLETED, i.e. counts some in-flight
work at the disk-guard kill). **`gt_render` dominates at 69%** — the AOV/GT-v3 export
(`--gt-b --gt-aov`) is the single biggest cost lever for the cloud run's per-sample price;
`--no-tex-dump`/`--exr-codec DWAA` control storage but not render time. Pricing a cloud
20k run: ~94s × 20000 ≈ 522 GPU-hours at this per-sample rate (single-stream; the farm's
multi-shard overlap, per `docs/RENDER_AT_SCALE.md`, should cut wall time well below that on
a multi-GPU node — no multi-shard data collected this run, since disk (not GPU idle time)
was the binding constraint locally).

### Boards + backup

Boards refreshed over the full 348 (`board_overview.jpg` samples 40 of 348 evenly spread
across all 17 recipes for legibility; `board_crop_workflow.jpg`/`board_shadows.jpg` keep
their per-recipe/shadow-only representative caps). `pilot_053_out` (20 G, 348 samples)
copied to `gdrive:vitrai-lab-backup/pilot_053_deployment` via `rclone copy` before this
report was finalized (lab backup-before-cleanup-eligible policy).
