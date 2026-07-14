# Report 043 — MMv3 physics upgrade (σ_s/a_glow split, gt_veil isolation, taxa color grounding)

Branch `research/delighting-043-mmv3`. The last generator iteration before the 20k
production render: every change here is a default-behavior physics change (not
flag-gated), justified below against the docs/MATERIAL_MODEL_V3.md spec and measured
before/after. Items land as separate commits with isolated evidence.

**Landed: items 1, 2, 3. Not attempted: item 4 (rendered-vs-authored saturation
drift) — stretch, deliberately dropped to keep 1–3 fully validated (§6).**

Review board: `results/043/board_043.jpg` (before | after | real exemplar per item).

## 1. Item 1 — scatter PSF: split `h` into `(σ_s, a_glow)` (MMv3-G1)

### Physics

The report-037 opal stopgap mixed a second, near-fully-diffuse Principled lobe in
at a hard-capped weight (0.6·h) for the two opal recipes. Two BSDFs mixed at a
single shading point are not a spatial blur: Cycles either samples the primary
(still fairly directional) lobe or jumps to the near-diffuse one, and for an
environment light at infinity the diffuse lobe integrates the WHOLE hemisphere —
the global mean of the background, not a local neighborhood. There is no dial
between "sharp" and "hemisphere average": a sharp occluder edge behind milky glass
gets locally *dimmed toward the global mean*, never *blurred wider* — the
razor-edge artifact this iteration was briefed to kill.

GGX transmission roughness, by contrast, IS a continuous local blur: roughness σ
samples a cone of directions around the ideal refraction direction, which for a
background at distance d maps to a disc of nearby background positions (a real
PSF whose width grows monotonically with roughness, approaching full diffusion as
σ→1). That is exactly MATERIAL_MODEL_V3.md's own limit statement ("the binary
h-mix becomes the σ_s→∞ / a_glow limit"). So the implementation:

- **σ_s drives the ONE transmission lobe's Roughness directly** (`create_glass_
  material`), uncapped — the opal family gets the headroom the stopgap reserved
  for its second lobe. Chosen over a measured-PSF/compositor approach because it
  is the physically-correct in-renderer scattering mechanism (energy-conserving,
  correct at occluder silhouettes and under HDRI lighting) rather than a
  screen-space approximation of one; the app-side differentiable model keeps the
  separable-Gaussian approximation per the spec.
- **a_glow is an independent Translucent-BSDF mix** — true Lambertian transmission,
  the "milky sheet glows and hides B" term that even Roughness=1 GGX transmission
  does not fully reach (multiple internal scattering). Zero for every non-opal
  recipe, so the mix is an exact no-op there.
- **Authoring**: `decompose_haze(h, recipe)` splits the calibrated per-recipe h
  (non-opal: σ_s = h, a_glow = 0 — byte-equivalent to the CTO-approved look;
  opal: σ_s = clip(1.15·h, 0, 0.92), a_glow = clip(0.35·h, 0, 0.35)); `h` itself
  is re-derived as the OUTPUT_CONTRACT §0 compatibility projection
  `h = a_glow + (1−a_glow)·σ_s` — existing (T, h) consumers keep working, and the
  projection identity round-trips through the render pipeline (measured residual
  mean 1.4e-4, DWAA tolerance).
- **GT**: `tex_/gt_sigma_s`, `tex_/gt_a_glow` exported on the same encode path as
  h (GT_SPEC §1a/1b updated).

### Evidence (`results/043/validate_gate_043_item1.txt`, board row A)

- **Razor-edge test** (wispy-white seed 601, black_metal frame occluder behind the
  sheet, production flags): 10–90% edge rise through the milky glass, 55 row
  profiles centered on the gt_B occluder edge — gt_B stays **1 px** sharp (GT
  intact); photo edge **29 px (before) → 58 px (after)**, wall held constant so
  the row isolates the shader. The edge now *widens* instead of just dimming.
- **Validate gate**: non-opal recipes reproduce committed baselines
  (cathedral-green 0.0262 = 037-final; streaky-mix 0.0115 = 039; dark-deep
  0.0030); the opal pair IMPROVES (wispy-white 0.0109 → **0.0075**,
  saturated-opalescent 0.0132 → **0.0062**) — the stopgap's second lobe was
  itself biasing uniform-backlight transmission away from gt_T.

### What did NOT work

- **Translucent fed with the squared T**: the Principled thin-sheet trick squares
  authored T so the node's internal sqrt cancels; Translucent has no such sqrt,
  so the first wiring rendered the glow at T² — wispy-white validate MAE blew up
  0.0109 → 0.1065. Caught by the gate, fixed by feeding tex_T unsquared
  (comment in `create_glass_material` records the measurement).
- **Honest caveat**: `decompose_haze` is a first-pass decomposition grounded on
  the existing per-recipe h calibration, NOT an independent corpus regrounding of
  (σ_s, a_glow) against real scatter statistics — that regrounding (the 021/022
  discipline MATERIAL_MODEL_V3.md demands before the channels are *trusted*)
  remains owed, flagged in the MMv3 status table.

## 2. Item 2 — gt_veil scene fix (MMv3-G2 support)

GT_SPEC §6 (report 037) measured `gt_veil` nonzero on 100% of pixels with
`--specular` OFF: the bump-mapped shading normal fans the glossy cone past the
5 m DarkWall's edges, and the fanned rays see the bright HDRI sky directly — a
real, large, undocumented veil in every dataset generated to date. Fix: the wall
is scene geometry whose only job is to occlude the front hemisphere; 5 m → 60 m
(subtends >168° from the glass, only negligible-weight grazing rays escape).
Shader untouched.

Isolated evidence (`results/043/veil_isolation_043_item2.txt`, board row B) —
shader held constant between the two states (item-1 tree vs item-1+2 tree):

| state | veil mean | median | p99 | pixels >1e-4 |
|---|---:|---:|---:|---:|
| wall 5 m | 0.25316 | 0.22986 | 0.54427 | 100.0% |
| wall 60 m | 0.00042 | 0.00000 | 0.00451 | 24.6% |

600x mean reduction, median exactly 0, residual max 0.019. `gt_veil` now measures
genuine front-surface reflection only; the `--specular` dim-interior path is
unaffected (a lit wall still reflects as designed — the fix removes the geometry
LEAK, not the veil mechanism). The authored `r_f(x)` field + front IBL of full G2
remain open (MMv3 status table updated).

## 3. Item 3 — exemplar-grounded colors for the four report-037 taxa

Report 037 authored the four new-taxa palettes as "plausible choices chosen for
corpus-hue diversity, not independently re-grounded" and flagged the grounding as
owed. This is that pass, by the report-039 method (STREAK_EXEMPLAR_NOTES.md):
measure the real corpus exemplars once (`corpus/taxa_exemplars_043.py` → 2-means
light/dark Lab modes per sheet → `results/043/taxa_exemplar_colors.json` + per-
taxon contact sheets), embed the measured distribution as constants
(`sample_taxa_colors()`), draw a real-grounded palette per seed. Structure
(Voronoi lines/cells, ring_mottle_blobs, rolling-wave relief) is untouched —
this item is colors only.

| taxon | real exemplar population (n) | measured | 037 authored | 043 change |
|---|---|---|---|---|
| ring-mottle | the literal Ring Mottle category — 8 Youghiogheny Mottle sheets | body L* 64–80, blobs a few L* darker, C* to 84, green/yellow-green/blue hues | dark amber/rose, body L*≈20 | **regrounded family**: light opalescent (base, blob) pairs sampled from the 8 measured mode pairs |
| fracture-streamer | 6 Bullseye Collage fracture/streamer sheets | base L* 85–95 / C* 0.5–4; lines = black/green/pink/white modes | base L*≈69 cool-grey; fixed near-black lines | base into the measured near-clear band; line color sampled from measured modes |
| confetti-shard | 13 Bullseye Collage shards-on-clear/white sheets | base L* 84–95; shards L* 33–59 / C* 15–43 on coordinated seasonal hue sets | uniform-random RGB per cell | per-seed 2–4 real hue anchors + per-cell jitter |
| baroque-rolling-wave | 87 colored Textured/Baroque cathedral sheets | hue mass amber 27% / green 17% / blue-purple 14%; L* 45–66, C* 22–52 | one fixed pale seafoam | per-seed body tint from the measured hue-mass/L/C distribution |

Authored-T Lab stats across seeds land inside the measured bands (e.g.
ring-mottle seed 42 → L* 64.6 / C* 75.5, the yu0074 green-mottle mode; confetti
seed 101 → L* 58 / C* 25 with shard p95 C* 40).

**VLM forced-choice (039 protocol, per-taxon lineups, luminance-normalized)**:
`results/043/forcedchoice_taxa_043.py` — 2x2 grid, 3 real exemplars of the
taxon + our render (position shuffled), `claude -p --model sonnet` asked to
spot the render. Results in
`results/043/forcedchoice_taxa_results_{before,after}.json` (12 lineups/tag,
3 per taxon, seed-43 lineup construction held identical between tags so the
before/after comparison isolates color):

| taxon | before (037 colors) | after (043 exemplar-grounded) |
|---|---:|---:|
| baroque-rolling-wave | 3/3 detected | 1/3 detected |
| fracture-streamer | 0/3 detected | 0/3 detected |
| confetti-shard | 3/3 detected | 3/3 detected |
| ring-mottle | 3/3 detected | 2/3 detected |
| **overall** | **9/12 = 75%** | **6/12 = 50%** (chance 25%) |

Detection dropped 75% → 50% — real, but not to chance, and the improvement is
concentrated in the two taxa whose color shift was largest (ring-mottle's
dark-amber→light-opalescent regrounding, baroque-rolling-wave's fixed pale
seafoam→measured hue-mass draw; board rows visually confirm both now land
much closer to their real exemplars). fracture-streamer was ALREADY at chance
before this pass (0/3 both tags) — its Voronoi line-network structure, not
color, was already selling it; item 3 correctly left it a no-op. confetti-shard
is the miss: still 3/3 both tags. Inspecting the lineups, the giveaway isn't
the shard hues (which now sample the measured seasonal sets) but structure —
our thin black Voronoi boundary lines read as a uniform grid, while the real
Bullseye sheets' streamer lines are sparse, thick, and irregular. Colors were
this item's explicit scope (see the "structure unchanged" note above); the
line-network geometry is now the flagged follow-up for confetti-shard
specifically, alongside the already-flagged ring-mottle haze regrounding.

**Honest caveats**: (a) ring-mottle keeps its 037 haze (h=0.22 flat) and its
dark-family mark weighting — colors were the scope; the haze/scatter regrounding
for the now-light opalescent family is follow-up. (b) exemplar populations are
small for ring-mottle (8) and fracture-streamer (6) — the sampler draws from
per-sheet measured modes with jitter rather than pretending a smooth
distribution. (c) product photos measure photographed appearance, not T; same
approximation as 021/039 (crop-center swatch, exposure-normalized comparisons).

## 4. Per-sample size delta (GT_SPEC updated)

Measured on production-shaped wispy-white samples (`--no-tex-dump --exr-codec
DWAA --gt-b --gt-aov`, shadow pair): **65 MB (before) → 84 MB (after), +19 MB**
= the two new GT channels (gt_sigma_s/gt_a_glow EXR+PNG; the tex_* copies are
deleted by `--no-tex-dump`). Still ≤100 MB (§3 target); at 20k ≈ +380 GB. If the
budget tightens, `gt_h` is now redundant (recoverable from σ_s/a_glow via the §0
projection) and is the natural prune — kept for OUTPUT_CONTRACT compatibility.
Reader caveat (pre-existing, documented now): BW single-channel EXRs under DWAA
are not cv2-readable; use `extract.load_aov_exr`.

## 5. Validation summary

- Item 1: razor-edge 29→58 px with gt_B at 1 px; validate gate green (non-opal
  byte-consistent, opal improved). Board row A.
- Item 2: veil mean 0.253→0.0004 with shader constant; histograms board row B.
- Item 3: authored-T stats inside measured exemplar bands; VLM forced-choice
  detection 75%→50% overall (chance 25%; §3 per-taxon table); per-taxon board
  rows C–F, all 8 renders (4 taxa × before/after) present alongside real
  exemplars.
- Machine rules kept: one Blender at a time (pgrep-gated, shared with the 045
  sibling), disk >10 GB free maintained, absolute-path git, main checkout
  untouched (corpus read-only).

## 6. What was not done

- **Item 4 (stretch)** — renderer-domain saturation drift: not investigated;
  items 1–3 consumed the iteration's render budget. The 039 finding stands as
  the open lead.
- Full-17-recipe validate sweep: gated on 5 representative recipes (2 opal, 2
  non-opal families, 1 streak); the remaining recipes share the non-opal
  σ_s == h identity path.
- (σ_s, a_glow) corpus regrounding + ring-mottle haze regrounding — named owed
  work, MMv3 status table.
- confetti-shard line-network geometry — the forced-choice miss (§3): still
  3/3 detected after the color regrounding, because the giveaway is the thin
  uniform-black Voronoi boundary grid, not shard hue. A sparse/thick/irregular
  streamer-line model (shared with fracture-streamer's T9 mechanism) is the
  fix; out of scope for a colors-only item.

## 7. Reproduction

```
cd research/delighting
# item 1+2 evidence sample (before = origin script):
BLENDER -b -P generate_synthetic.py -- --out OUT --recipe wispy-white --seed 601 \
  --count 1 --light-variations 1 --hdri-dir HDRIS \
  --no-tex-dump --exr-codec DWAA --gt-b --gt-aov
# validate gate:
BLENDER -b -P generate_synthetic.py -- --out OUT --seed 42 --count 1 \
  --light-variations 1 --validate --recipe {cathedral-green,dark-deep,streaky-mix,wispy-white,saturated-opalescent}
python3 check_validation.py OUT
# taxa grounding + previews + VLM:
python3 corpus/taxa_exemplars_043.py
BLENDER -b -P generate_synthetic.py -- --out OUT --recipe <taxon> --seed 42 \
  --count 1 --light-variations 1 --hdri-dir HDRIS --fixed-ev 0 --no-marks
python3 results/043/forcedchoice_taxa_043.py --tag after --renders OUT
# board:
python3 results/043/build_board_043.py
```
