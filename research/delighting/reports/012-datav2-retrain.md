# Report 012 — Data v2 (realistic border occluders) + shadow-net retrain on fixed T

Date: 2026-07-09. Branch: `research/delighting-datav2` (off
`research/delighting-combined`). Code: `generate_synthetic.py` (occluder fix, this
report), `neural/` with env-overridable paths (`NEURAL_DATA_SNAPSHOT`,
`NEURAL_CACHE`, `NEURAL_WEIGHTS`, `NEURAL_CACHE_ORIG/FIX`). Data:
`synthetic_data_v2/` (gitignored), Blender 5.0.1 macOS arm64, Cycles/Metal.
Deliverables: this report, `neural/results_v2/`, occluder examples under
`results/datav2/`. **No PR.**

## 0. TL;DR

TODO

## 1. Generator realism fix (maintainer decision)

The `has_frame` trap existed to plant **dark occluders visible THROUGH clear
glass that must not end up in `T`**. The old realization — a full dark
window-mullion grid behind the whole pane — was over-aggressive vs real
captures. Replaced with **partial frame edges entering from the image
border(s)**, like a real photo of a sheet held near a window edge:

- 1 border (70%) or 2 borders (30%), chosen at random among top/bottom/left/right;
- reach into the frame randomized (8–35% of the visible half-extent), inner
  edge jittered so it is not perfectly flush;
- near-black albedo, randomized 0.005–0.02;
- frequency lowered 33% → **20%** of samples;
- all params recorded in `meta.json` (`frame_occluders: [{border, thickness,
  reach_frac, darkness}]`).

**Bug found while implementing:** the natural constant to anchor the bars to —
the glass plane's half-size (0.25 m) — is NOT the visible image border. The
camera's default 50 mm lens sees only ±0.144 m × ±0.096 m at the glass depth
(the glass is deliberately oversized so it bleeds off all four edges). Bars
anchored to the plane's own size sat almost entirely outside the frame. The fix
computes the true visible frustum box from the camera's `angle_x/angle_y` at
the occluder's depth. Verified visually (committed examples in
`results/datav2/occluder_example_*.jpg`).

## 2. Validation gate (v2 generator, all 5 recipes)

```
blender -b --python-use-system-env -P generate_synthetic.py -- \
    --validate --count 5 --light-variations 1 --out validate_data_check_v2
.venv/bin/python check_validation.py validate_data_check_v2
```

| recipe          | v2 MAE   | report-006 reference (v1) | verdict |
|-----------------|----------|---------------------------|---------|
| cathedral-green | 0.021753 | 0.021753 | PASS — Fresnel floor |
| cathedral-amber | 0.025792 | 0.025792 | PASS |
| dark-opaque     | 0.005914 | 0.005914 | PASS |
| streaky-mix     | 0.026904 | 0.026901 | PASS |
| wispy-white     | 0.038579 | 0.038579 | PASS |

Identical to report 006 to ~1e-6 (same seeds; validate mode disables the frame,
so the occluder change is orthogonal by construction — this is a regression
check that the refactor did not disturb the physics path, and it didn't).

## 3. The v2 dataset

`--seed 42 --count 5 --light-variations 4` → **20 samples** (5 recipes × 4
lightings, each a with/without-shadow pair + camera-aligned `gt_T/gt_h/gt_mark`),
~40 min total on the M4. 4/20 samples (20%) carry the new border occluders:
cathedral-amber right-bar, dark-opaque left+bottom and top+bottom, streaky-mix
top+bottom. Held-out split (one unseen lighting per recipe, data-driven rule in
`neural/common.split`):

- cathedral-green light7527, cathedral-amber light9423, dark-opaque light9893
  (has occluders), streaky-mix light7995, wispy-white light6553.

**Dataset caveat found while caching:** the eval harness's `valid_mask`
heuristic (photo < 0.018 linear & authored glass brighter → presumed occluder,
excluded) over-fires on **dark-opaque under dim lighting draws** — up to 47% of
pixels on light9893 — because genuinely dark glass under low EV dips below the
threshold. Pre-existing harness logic (reports 008–011 use the same rule), not
a v2 generator issue; it shrinks the scored region on dark samples.

## 4. Retrain on fixed-T (the report-011 follow-up)

TODO

## 5. Three-condition held-out eval on v2

TODO

## 6. Occluder over-fire check

TODO

## 7. Honest caveats

TODO

## 8. Files

TODO
