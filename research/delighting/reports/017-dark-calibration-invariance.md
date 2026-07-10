# Report 017 — Dark-end anchor calibration + cross-lighting invariance metric

Date: 2026-07-09. Branch `research/delighting-017` (off `research/delighting` @ `896c2d7`).
Code: `generate_synthetic.py` (3 new dark-family recipes), `extract.py` (`anchor_features` split
out, refit `ANCHOR_*` constants), `fit_anchor.py` (new — refit/LORO harness), `eval_cross_lighting.py`
(new — capture-invariance metric), `eval_synthetic.py` (`CLASS_MAP` additions),
`eval_class_injection.py` (`--data` repeatable), `docs/RESEARCH_STATE.md` (coherence pass).
Artifacts: `results/anchor_dark_calibration/`, `results/cross_lighting/`. Data: synthetic v2
(26 samples, 5 recipes, read-only from the `research/delighting-datav2` worktree), 9 new
dark-family renders (this report; gitignored like all renders), the 9-sheet real library.
No PR — reports are the deliverable.

## 0. TL;DR

Report 016's named follow-up: the continuous anchor's dark end was calibrated by ONE recipe
family (dark-opaque, GT p99 ≈ 0.216), so leave-that-recipe-out could not predict dark at all
(**LORO worst 4.29x** — reproduced exactly by this report's refit harness before touching
anything). Three new dark-family recipes (`dark-deep` ~T 0.055 very-dark neutral, `dark-ruby`
~T 0.13 dark-tinted/strongly-colored, `dark-slate` ~T 0.31 medium-dark) bracket the original
recipe from both sides. Refit on the widened 8-recipe/35-sample set (floor `T_LO` lowered
0.10 → 0.04 — dark-deep's authored GT sits below the old floor, i.e. the old model literally
could not represent it):

- **LORO worst-case 4.29x → 3.37x**, and — more meaningfully — held-out dark predictions now
  actually land **dark** (before: hold out dark-opaque and it predicts 0.88-0.92, "bright
  glass"; after: 0.09-0.73, with every NEW dark recipe held out landing ≤ 2.6x worst).
- Class-error injection on the widened set: worst wrong-class brightness error
  **4.15x (old fit) → 3.90x (new fit)**, dark-deep wrong-class 3.4x → **2.1x**, dark-ruby up to
  3.6x → ≤ 2.6x; the original 5 recipes' cells move at noise level (±0.001-0.004 T-MAE). The
  new darks also expose the class anchor brutally: dark-deep under a bright wrong class is
  **16.5x** too bright (the 016 ceiling was 9.7x) — the widened set is genuinely harder, not
  padding.
- **Under the CORRECT class the continuous anchor now beats the class anchor** on the widened
  set (mean T-MAE 0.103 vs 0.107): `T_ANCHOR["dark-opaque"] = 0.20` is one point for a whole
  darkness family (deep 0.055 / opaque 0.216 / ruby 0.13 / slate 0.31), and the image statistics
  resolve within-class darkness the class label cannot.
- **Zero real-photo regression**: the 9-sheet library is byte-identical under the default
  (manifest/class) path, and 8/9 pixel-identical under forced `--anchor continuous` (blue.jpg
  moves 0.002 mean T luminance). black.jpg's image estimate improves (t_img 0.281 → 0.236 vs
  its human-verified target 0.20).

Second deliverable (long-queued): `eval_cross_lighting.py`, the CAPTURE-INVARIANCE metric —
same authored glass under N lightings, extracted independently; pairwise mean-abs-difference of
the maps. Headline finding (§2): under the oracle class the dark family is beautifully invariant
(T 0.02-0.06) and **cathedral glass is capture-DEPENDENT beyond its own accuracy error**
(invariance 0.18-0.20 > GT-error 0.14-0.15 — the T·B background leak varies per lighting); under
the vlm-free continuous path, **per-lighting variance of the scale estimate breaks invariance on
mid/dark glass** (dark-opaque 0.036 → 0.280) — an honest cost of the continuous anchor that the
accuracy-centric injection eval structurally cannot see.

## 1. Task A — dark-end anchor calibration

### 1.1 Three new recipes

`generate_synthetic.py`'s `create_glass_textures` gained `dark-deep`, `dark-ruby`, `dark-slate`,
following the existing per-recipe convention (flat authored base color + small additive low-freq
noise, flat haze `h`); `generate_relief_height` folds them into the existing dark-opaque hammered
relief statistics (same family of dense rolled glass, not a different surface finish).

**Calibration method — measured, not assumed.** The naive expectation is that `gt_T.exr` equals
the authored linear `base_color`. It does not: measuring the existing `dark-opaque` recipe
(authored `[0.03, 0.035, 0.03]`) against the real v2 renders gives GT p99 ≈ 0.216, and
`cathedral-green` (authored `[0.15, 0.55, 0.20]`) gives GT mean `[0.425, 0.75, 0.49]` — in both
cases matching `srgb_encode(authored)` to within noise (`srgb_encode(0.04) = 0.221` vs measured
dark-opaque max 0.219; `srgb_encode([0.15,0.55,0.20]) = [0.424, 0.767, 0.485]`). Reproduced in
this environment with a fresh `--validate` render of the unmodified dark-opaque recipe (gt_T mean
`[0.188, 0.206, 0.188]`, matching the historical v2 data). This is an existing, self-consistent
convention of the whole pipeline — every prior report's `T_ANCHOR`/GT numbers are in the same
units, nothing changes — but it means choosing a target **rendered** darkness for a new recipe
requires inverting that transform. Base colors below are `srgb_decode(target)`, verified by an
actual render before spending the full lighting batch:

| recipe | authored linear base_color | intended rendered p99 | measured rendered p99 |
|---|---|---|---|
| dark-deep  | `[0.0039, 0.0039, 0.0041]` | ~0.05 (neutral)  | **0.055** (mean `[0.050,0.050,0.052]`) |
| dark-ruby  | `[0.0143, 0.0023, 0.0027]` | ~0.12-0.13 (R-dominant, strong chroma) | **0.132** (mean `[0.125,0.032,0.037]`, ~4x R:G) |
| dark-slate | `[0.0593, 0.0660, 0.0732]` | ~0.30 (B-dominant, mild tint) | **0.312** (mean `[0.268,0.288,0.304]`) |
| dark-opaque (existing, unchanged) | `[0.03, 0.035, 0.03]` | — | 0.216 |

All three land on target on the first render — itself confirmation the transform is real and
consistent, not a dark-opaque one-off. (`p99` is the flattened-array percentile, `T_ANCHOR`'s own
convention: `np.percentile(T_HxWx3, 99)` mixes channels, so for a tinted recipe it tracks the
dominant channel, not luminance — accounted for in dark-ruby's per-channel targets.)

**Validation gate** (`check_validation.py`, uniform-backlight `--validate` renders):

| recipe | MAE (linear 0-1) | context |
|---|---|---|
| dark-deep | 0.0013 | existing recipes pass at 0.006-0.039 (report 006) |
| dark-ruby | 0.0019 | PASS |
| dark-slate | 0.0096 | PASS |
| dark-opaque (re-verified unchanged) | 0.0046 | PASS, matches report 006's 0.0059 |

**Full renders:** 1 seed × 3 HDRI lightings per new recipe (`sunflowers_1k.hdr`, same
lighting-variation convention as v2) = 9 new samples. Widened tuning set: 35 samples, 8 recipes,
GT p99 spanning 0.055-0.95 with the dark half no longer a single point.

### 1.2 LORO refit (`fit_anchor.py`)

`fit_anchor.py` reimplements report 016's fit (ridge lam=2.0 in logit space on
`extract.anchor_features` — now split out of `estimate_anchor_scale` so fit and inference share
the exact feature code) plus a leave-one-recipe-out harness. **Sanity check: fitting on the
original 26 samples reproduces the shipped `ANCHOR_*` constants to 6 significant figures and the
016 LORO baseline exactly (4.29x)** — the harness is faithful, the before/after is apples-to-apples.

LORO before (original 5 recipes) vs after (8 recipes, shipped `T_LO=0.04` fit):

| held-out recipe | BEFORE pred range (gt) | BEFORE worst | AFTER pred range | AFTER worst |
|---|---|---|---|---|
| dark-opaque (gt 0.216) | 0.877-0.923 | **4.29x** | 0.198-0.729 | 3.37x |
| dark-deep (gt 0.055) | — (recipe is new) | — | 0.114-0.140 | 2.54x |
| dark-ruby (gt 0.132) | — | — | 0.086-0.179 | 1.54x |
| dark-slate (gt 0.312) | — | — | 0.180-0.505 | 1.74x |
| cathedral-amber | 0.815-0.953 | 1.11x | 0.819-0.948 | 1.10x |
| cathedral-green | 0.524-0.897 | 1.49x | 0.538-0.898 | 1.45x |
| streaky-mix | 0.344-0.870 | 2.70x | 0.344-0.884 | 2.70x |
| wispy-white | 0.732-0.918 | 1.30x | 0.719-0.922 | 1.32x |

The headline number (4.29x → 3.37x) understates the qualitative change: BEFORE, holding out the
only dark recipe left a fit with no dark evidence at all, and every held-out dark sample was
predicted ~0.9 ("this is bright glass") — the failure report 016 called "cannot predict dark at
all". AFTER, holding out any one dark recipe still leaves three others, and predictions land in
the dark range. The residual ~2-3.4x is the L·T gauge ambiguity (dim photo: dark glass or dim
backlight?), which no single-photo statistic removes — consistent with 016's stated limit.

**`T_LO` 0.10 → 0.04, decided on measurements, not preference.** dark-deep's GT (0.055) is below
the old floor — the old model could not represent it even in-sample (best possible 1.8x error).
Candidates compared on three axes: `T_LO=0.04` wins in-sample (mean ratio 1.44x vs 1.51x) and on
the real library — black.jpg t_img 0.236 (target 0.20; old fit 0.281), while the `T_LO=0.10`
REFIT pushed blue.jpg's t_img to 0.497 (1.9x disagreement vs its verified class — visible drift
under continuous) where the 0.04 refit keeps it at 0.611 ≈ the old fit's 0.620. `T_LO=0.10` wins
only the single worst LORO cell (3.25x vs 3.37x, one dark-opaque sample). Shipped: `T_LO=0.04`.
Trade acknowledged: the floor is also the protective bound report 016 cited for deceptive photos
under a correct class — worst-case adversarial drag with the 0.85 blend cap is now
`0.04^0.85·0.95^0.15 ≈ 0.06` where it used to be ≈ 0.14. The library shows no such case (§1.4),
but a dim-lit real photo of bright glass under a correct human class is the configuration to
watch when real cross-lighting pairs arrive.

### 1.3 Class-error-injection re-check (widened set, both fits, one pass)

Full tables in `results/anchor_dark_calibration/injection_widened_tables.md`; the run replicates
report 016's harness with the new recipes pooled in and an extra `continuous_oldfit` design so
old and new constants are scored in the same pass on the same extractions.

Worst cells (lum-ratio = extracted/GT mean T luminance):

| cell | class anchor | continuous OLD fit | continuous NEW fit |
|---|---|---|---|
| dark-deep as wispy (worst overall) | 0.761 (**16.5x**) | 0.120 (3.44x) | **0.054 (2.11x)** |
| dark-deep as opalescent | 0.700 (15.2x) | 0.118 (3.39x) | **0.053 (2.08x)** |
| dark-ruby as wispy | 0.642 (14.5x) | 0.112 (3.59x) | **0.074 (2.59x)** |
| dark-opaque as wispy (016's headline) | 0.574 (3.83x) | 0.233 (2.12x) | **0.225 (2.02x)** |
| dark-opaque as cathedral-clear | 0.474 (3.51x) | 0.182 (1.86x) | **0.178 (1.76x)** |
| streaky-mix as dark-opaque (016's worst leftover) | 0.632 (0.17x) | 0.433 (0.46x) | 0.429 (0.47x) |

Summary (all 35 samples × 4 assumed classes):

| design | correct-class mean T-MAE | wrong-class mean T-MAE | worst wrong-class lum-ratio |
|---|---|---|---|
| class anchor | 0.107 | 0.448 | **17.08x** |
| continuous, old fit | 0.109 | 0.198 | 4.15x |
| continuous, new fit | **0.103** | **0.190** | **3.90x** |

Three reads:
1. **Improvement without regression.** Every dark-family wrong-class cell improves under the new
   fit; the original five recipes' cells move by ±0.001-0.004 T-MAE (noise). The 016 win
   condition still holds and tightens slightly (dark-as-cathedral 1.86x → 1.76x).
2. **The correct-class advantage flips to the continuous anchor** (0.103 vs class 0.107): with a
   real darkness *spectrum* in the data, one fixed `T_ANCHOR["dark-opaque"] = 0.20` per class is
   itself a source of error (dark-deep under its correct class: 0.112 T-MAE / 3.45x too bright
   with the class anchor — the class anchor cannot know this sheet is 4x darker than the class
   target; the continuous anchor reads it from the photo, 0.050 / 2.13x).
3. **Streaky-as-dark stays the worst continuous cell** (0.429) — unchanged, as expected: that
   error is wrong-class h/assembly corruption, not scale; outside this iteration's reach
   (016 §5.2 still stands).

### 1.4 Real-photo regression checks

- **Default path (manifest classes → class anchor): the 18 library T/h map PNGs are
  byte-identical** (md5) before vs after the refit — the constants only enter this path as
  metrics (`anchor_t_img` / `anchor_scale_disagree`).
- **Forced `--anchor continuous`**: 8/9 sheets pixel-identical (t_img within the 1.5x trust band
  → blend returns the class target untouched); blue.jpg (016's only mover) shifts mean T
  luminance by 0.0019 — below visibility.
- t_img changes on the two 016 sentinel sheets: black.jpg 0.281 → 0.236 (closer to its verified
  0.20 target); white.jpg 0.930 → 0.933 (vs target 0.88) — the feature-hardening cases stay fixed.

## 2. Task B — cross-lighting (capture) invariance

`eval_cross_lighting.py`: for every (recipe, seed) group — same authored glass, N independent
lightings (HDRI rotation/EV draws) — extract T,h from each lighting independently and compute the
**pairwise mean-abs-difference** of the maps within the group. This is the product's primary
metric (RESEARCH_STATE "Success metric": same glass, different capture → same maps) measured
directly, per recipe, for the first time; the assembled-pair benchmark (report 014) covers
position-invariance, this covers capture-lighting-invariance, on all recipes. Two designs, both
real paths of the shipped `--anchor auto` default:

- **oracle** = correct class, class anchor (what a human-verified manifest gets);
- **continuous** = fallback class `wispy` + continuous anchor (what a vlm-free/unverified batch
  run gets — extract.py's own documented fallback, with the class source absent).

Per-recipe table (pair-weighted mean over seed-groups; GT-error columns = the same design's
accuracy vs authored ground truth, for context — invariance should sit at or below it):

| recipe | design | pairs | **invariance T** | invariance h | GT T-MAE | GT h-MAE |
|---|---|---|---|---|---|---|
| cathedral-amber | oracle | 6 | 0.200 | 0.006 | 0.146 | 0.088 |
| cathedral-amber | continuous | 6 | 0.153 | 0.294 | 0.214 | 0.213 |
| cathedral-green | oracle | 6 | 0.177 | 0.007 | 0.145 | 0.084 |
| cathedral-green | continuous | 6 | 0.133 | 0.246 | 0.256 | 0.192 |
| dark-deep | oracle | 3 | 0.026 | 0.088 | 0.111 | 0.143 |
| dark-deep | continuous | 3 | 0.016 | 0.114 | 0.054 | 0.332 |
| dark-opaque | oracle | 21 | **0.036** | 0.090 | 0.060 | 0.230 |
| dark-opaque | continuous | 21 | **0.280** | 0.318 | 0.236 | 0.290 |
| dark-ruby | oracle | 3 | 0.023 | 0.035 | 0.061 | 0.215 |
| dark-ruby | continuous | 3 | 0.051 | 0.251 | 0.074 | 0.247 |
| dark-slate | oracle | 3 | 0.059 | 0.104 | 0.153 | 0.090 |
| dark-slate | continuous | 3 | 0.265 | 0.260 | 0.148 | 0.427 |
| streaky-mix | oracle | 6 | 0.118 | 0.474 | 0.136 | 0.414 |
| streaky-mix | continuous | 6 | 0.169 | 0.474 | 0.160 | 0.414 |
| wispy-white | oracle | 6 | 0.117 | 0.118 | 0.122 | 0.137 |
| wispy-white | continuous | 6 | 0.117 | 0.118 | 0.122 | 0.137 |

Findings, in order of importance:

1. **Cathedral glass is capture-DEPENDENT beyond its own accuracy error** (oracle invariance T
   0.18-0.20 > GT-error 0.14-0.15). The transmitted background (T·B leak) is different under
   every lighting and lands in T differently each time — the same sheet does *not* de-light to
   the same map. This quantifies, per recipe, what reports 013/014 saw end-to-end: the
   north-star see-through separation is the invariance bottleneck, not just an accuracy one.
   By contrast the dark family under oracle is beautifully invariant (0.023-0.059, 2-4x below
   its GT-error) — opaque glass hides the background, so what's left is genuinely lighting-stable.
2. **The continuous anchor's per-lighting scale variance breaks invariance on mid/dark glass**:
   dark-opaque invariance T 0.036 (oracle/class) → 0.280 (continuous); dark-slate 0.059 → 0.265.
   Mechanism: t_img is estimated per photo, and a dim-lit vs bright-lit capture of the same dark
   sheet reads differently through the gauge ambiguity — each lighting gets its own absolute
   scale, so the group scatters. The class anchor is *constant per class*, so even when it is
   wrong it is CONSISTENTLY wrong — which is exactly what the invariance metric (and the user
   dragging glass into a preview) rewards. The injection eval structurally cannot see this: it
   scores each sample against GT independently, where averaging-right beats stable-but-off.
   **Product read: the `auto` default (896c2d7) stands** — for unverified batch runs the
   catastrophic-scale protection is worth more than group consistency, and for human-verified
   classes (the path a returning user's library lives on) the class anchor keeps its perfect
   per-class stability — but "stabilize t_img across captures of the same sheet" (e.g. snap to
   canonical levels, or estimate once per sheet identity rather than once per photo) is now a
   measured, motivated follow-up.
3. **Exception that proves the mechanism**: dark-deep improves under continuous (0.016 vs oracle
   0.026) — all three of its captures are uniformly *near-black*, so t_img saturates at the same
   low value every time; scale variance needs mid-range ambiguity to express itself. Wispy-white
   is identical by construction (fallback class IS wispy, t_img inside the trust band → the blend
   returns the class target — the regularizer working as designed).
4. **h invariance is class-driven**: under the oracle class, cathedral h is near-perfectly stable
   (0.006 — h is almost a class constant there); streaky-mix h invariance (0.474) exceeds even
   its large GT-error (0.414) — the haze assembly is the least lighting-stable part of the
   pipeline on streaky glass, consistent with the over-hazing recorded since report 007. Under
   the wrong fallback class, h is both wrong AND unstable (dark family 0.11-0.32) — wrong-class
   h corruption (016 §5.2) again, now with an invariance number attached.

## 3. Honest notes

1. **One seed per new recipe** (3 lightings each). The dark family now has 4 recipes / 19
   samples total, but only dark-opaque has multiple seeds; texture-seed diversity within the new
   recipes is untested. Cheap to extend with `--seed`/`--count` when needed.
2. **The refit's LORO 3.37x is not 1x**: the gauge ambiguity is intrinsic. The blend's trust
   band, not the estimator, remains the protection for healthy extractions; what changed is
   that a genuinely dark unseen material now degrades to ~2-3x instead of "predicted bright".
3. **`sat_lit` is blind exactly where chroma would help.** All 9 new dark captures have
   `sat_lit = 0` — the luminance gate (smoothstep 0.10-0.30) excludes every pixel of a dim
   photo, so dark-ruby's strong tint is invisible to the estimator, and ruby-vs-deep separation
   comes entirely from `log p95(Y)`. A saturation feature with a lower gate (or measured on the
   envelope-normalized R) is the obvious next feature-engineering step — not done here to keep
   this iteration's change surface at the constants-refit level (016's real-photo hardening
   lesson: every feature loosening must be re-audited against sensor noise at near-black, which
   needs the real corpus, not more Cycles).
4. **T_LO=0.04 weakens the deceptive-photo floor** (§1.2): worst-case adversarial drag under a
   correct class goes ≈0.14 → ≈0.06 at full blend. No library sheet triggers it; flagged for
   the real cross-lighting pair benchmark.
5. **The invariance eval's continuous column conflates two things** — the continuous anchor AND
   the wrong fallback class (h/assembly corruption). That is the honest composition of the real
   vlm-free path, but it means the 0.28 dark-opaque number is an upper bound on the anchor's own
   contribution; the class-anchor column isolates the anchor-free baseline. A third column
   (oracle class + continuous anchor) would decompose it — skipped for run-time, worth adding if
   the t_img-stabilization follow-up from §2 finding 2 is picked up.
6. **Renders are gitignored** (repo convention since report 005); the exact generator settings
   (recipe/seed/lightings) are in this report and reproducible with the commands below. The v2
   dataset remains read-only in its own worktree; nothing there was touched.

## Reproduction

```
cd research/delighting
# validate gate + full renders for one new recipe
PYTHONPATH=~/.local/lib/python3.11/site-packages <blender>/Contents/MacOS/Blender -b \
    --python-use-system-env -P generate_synthetic.py -- \
    --out <vdir> --validate --recipe dark-deep --seed 900 --count 1 --light-variations 1
python3 check_validation.py <vdir>
PYTHONPATH=... <blender> -b --python-use-system-env -P generate_synthetic.py -- \
    --out <dark_dir> --recipe dark-deep --seed 501 --count 1 --light-variations 3
# (dark-ruby: seed 502; dark-slate: seed 503)

# LORO before/after + shipped constants (T_LO chosen per section 1.2)
python3 fit_anchor.py --data <v2_dir> --data <dark_dir> \
    --recipes-before cathedral-green,cathedral-amber,dark-opaque,streaky-mix,wispy-white \
    --t-lo 0.04 --ship
# injection re-check and invariance table
python3 eval_class_injection.py --data <v2_dir> --data <dark_dir> --out /tmp/injection_017
python3 eval_cross_lighting.py --data <v2_dir> --data <dark_dir> --out /tmp/cross_lighting

# library regression (default path must stay byte-identical)
python3 extract.py benchmark/library --no-vlm --out /tmp/lib_check
```
