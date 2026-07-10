# Report 020 — Per-sheet scale pooling + dim-capture sat_lit fix

Date: 2026-07-09. Branch `research/delighting-020` (off `research/delighting` @ `c245c90`,
report 017's landing point). Code: `extract.py` (`estimate_anchor_scale_sheet`, `extract_maps`/
`process`/`main` threaded `sheet_t_img`/multi-photo CLI + manifest `sheet_id` grouping,
`anchor_features` adaptive `sat_lit` fallback, refit `ANCHOR_FEAT_MU/SD/COEF`), `eval_cross_lighting.py`
(new `continuous_persheet` design), `eval_class_injection.py` (new `continuous_persheet` design,
grouped by `(label, seed)`). Artifacts: `results/per_sheet_scale/`, `results/anchor_persheet_refit/`.
Data: synthetic v2 (35 samples, 8 recipes — the same widened set report 017 built, read-only from
the `research/delighting-datav2` worktree, including its own dark-opaque seed-47 top-up), plus a
fresh re-render of report 017's three dark-family recipes (`dark-deep`/`dark-ruby`/`dark-slate`,
1 seed x 3 lightings each — report 017's renders were gitignored and not preserved; re-rendered
here with `generate_synthetic.py`, verified to reproduce report 017's measured GT p99 to 3
significant figures), the 9-sheet real library. No PR — reports are the deliverable.

## 0. TL;DR

Report 017 closed with two measured, named follow-ups. Both are fixed here, and — this is the
headline — **they compound**: fixing #2 (sat_lit) alone would have shipped a regression, but
fixing #1 (per-sheet pooling) absorbs it and the combination beats the report 017 baseline on
every axis measured.

1. **Per-sheet scale mode** (`estimate_anchor_scale_sheet`, median of per-photo `t_img`):
   dark-opaque cross-lighting invariance **T 0.280 (per-photo continuous, reproduced exactly)
   -> 0.045 (per-sheet pooled)** — within 25% of the class-anchored floor (0.036), recovering
   94% of the gap the continuous anchor opened in report 017. Every other recipe moves the same
   direction or is unchanged; nothing regresses. Single-photo behaviour is byte-identical
   (median of one element is that element; verified at the function, `extract_maps`, and full
   CLI/library level).
2. **sat_lit dim-capture fix** (adaptive percentile-relative fallback, exactly when the old
   absolute gate is degenerate): dark-ruby's tint goes from **invisible (sat_lit = 0.0, identical
   to neutral dark-deep) to visible (sat_lit = 0.66-0.71 vs dark-deep's 0.06-0.20)** — the
   estimator can now tell a strongly-tinted dark sheet from a neutral one. Real library and every
   non-degenerate synthetic recipe are untouched (feature values byte-identical; 0 of 26
   non-dark-family samples change). **Refit required** (the feature definition changed): shipped,
   and the 9-sheet real library's T/h PNGs on the **default (class-anchor) path stay
   byte-identical** (18/18 md5 match) — the fix only ever touches inputs to the continuous-anchor
   blend, never the class-anchor path's actual pixels.
3. **Honest cost, disclosed and resolved**: sat_lit's fix ALONE (no pooling) is a mixed bag —
   dark-ruby's own correct-class T-MAE gets slightly worse (0.043->0.058), the injection eval's
   worst wrong-class ratio gets worse (3.90x->5.22x), and LORO worst-case gets worse
   (3.37x->3.47x), all driven by the SAME mechanism: one particular dark-ruby lighting whose
   per-photo estimate is unusually far from the group (t_img 0.300 vs siblings 0.154/0.120,
   true GT 0.132). **Per-sheet pooling is exactly the fix for this**: median-pooling that one
   outlier photo against its own siblings drops the anchor target back near truth, and the
   fully-combined system (shipped) posts **worst wrong-class ratio 3.90x -> 3.30x** and **LORO
   worst-case 3.37x -> 2.28x** — better than report 017 on both counts it would otherwise have
   cost.

## 1. Task A — per-sheet scale mode

### 1.1 Mechanism

`extract.estimate_anchor_scale_sheet(lins)`: given several photos of the SAME physical sheet,
call the existing per-photo `estimate_anchor_scale` on each and take the **median**. Not a mean —
even a log-space/geometric one. Justification (measured, not just argued, in SS1.4 below): the
estimator's own documented failure mode is that a single unlucky photo (specular hotspot, bad
crop, underexposure) can push one photo's raw-statistics reading far from the sheet's true scale
while its siblings agree; the median tolerates up to `floor((N-1)/2)` such outliers without being
dragged toward them, at zero extra machinery — no per-photo confidence/precision model exists to
justify inverse-variance weighting (there is no ground truth to calibrate one against, and the
016/017 ethos is not to invent an unmeasured knob). Because the feature->t_img map is a monotonic
sigmoid, taking the median of the final `t_img` values is exactly equal to taking it in feature-
or log-space — no separate log-space bookkeeping needed. **N=1 is the identity**: pooling is
strictly additive, never a behaviour change when only one photo is given.

### 1.2 Product entry points (both wired into `extract.py`, not just the eval harness)

1. **Multi-file CLI**: `extract.py PHOTO1 PHOTO2 PHOTO3 --class C --out DIR` — several explicit
   paths on the command line = one sheet group. All photos share one class (a physical sheet has
   one class) and one pooled scale; each still gets its own output maps. A single path (file or
   folder) is the original single-photo/batch behaviour, unchanged.
2. **Manifest `sheet_id`** (batch/folder mode): an optional new per-file manifest key. Files
   sharing a `sheet_id` are pooled; files without one (every existing manifest, including the
   9-sheet library's) are solo groups of size 1 — the identity case, so existing manifests are
   unaffected by construction, not just by testing.

Both thread through a new `sheet_t_img=None` parameter on `extract_maps`/`process`: when given, it
replaces the photo's own `estimate_anchor_scale(lin)` call; when `None` (the default), behaviour
is exactly report 016/017.

### 1.3 Evaluation harnesses extended (not just the product code)

- `eval_cross_lighting.py`: new `continuous_persheet` design — identical to `continuous` (fallback
  class `wispy`, `anchor='continuous'`) except `t_img` is pooled across every lighting in the
  `(recipe, seed)` group before any of them is extracted. The synthetic multi-lighting groups
  ARE "several photos of the same sheet" — no new data needed.
- `eval_class_injection.py`: samples now grouped by `(label, seed)` first (same grouping), each
  group's per-photo `t_img` values pooled once, and a `continuous_persheet` design added
  alongside `class`/`continuous` in every table.

### 1.4 Results

**Cross-lighting invariance, dark-opaque (the headline number)** — pair-weighted mean over both
seed-groups (seed44 x4 lightings + seed47 x6 lightings = 21 pairs), reproducing report 017's own
harness exactly before changing anything:

| design | anchor model | invariance T |
|---|---|---|
| oracle (class-anchored) | -- | 0.036 (this re-render; 017 reported 0.036) |
| continuous, per-photo | OLD (017 shipped) | **0.280** (reproduces 017's 0.280 to 3 sig figs) |
| continuous, per-photo | NEW (Task B refit) | 0.266 |
| **continuous_persheet (pooled)** | OLD (Task A alone) | **0.049** |
| **continuous_persheet (pooled)** | **NEW (shipped, A+B)** | **0.045** |

Per-recipe full table (both old and new anchor model rows) is in
`results/per_sheet_scale/cross_lighting_table.md`; headline read: **every recipe's
`continuous_persheet` invariance is <= its `continuous` invariance**, dark/mid recipes move the
most (dark-slate 0.275->0.040, dark-ruby 0.092->0.030, dark-opaque seed44 0.351->0.058, seed47
0.231->0.039), bright recipes are flat-to-slightly-better (cathedral-green 0.147->0.132,
streaky-mix 0.203->0.118 with the OLD model), and wispy-white is bit-for-bit identical (fallback
class IS wispy — the blend returns the class target regardless of pooling, exactly as designed).
**`h` invariance is unchanged between `continuous` and `continuous_persheet` for every recipe** —
by construction, since pooling only replaces the scalar anchor target `k`, never touches `h`; the
wrong-class `h` corruption documented in 016 SS5.2 / 017 finding 4 is exactly as before, untouched
by this report.

**Class-injection re-check** (35 samples x 4 assumed classes; full tables in
`results/per_sheet_scale/injection_tables.md`, 017-equivalent baseline in
`results/per_sheet_scale/baseline_017equiv/injection_tables.md`):

| design | anchor model | correct-class T-MAE | wrong-class T-MAE | worst wrong-class ratio |
|---|---|---|---|---|
| class | -- | 0.107 | 0.448 | 17.08x |
| continuous, per-photo | OLD (017 baseline, reproduced exactly) | 0.103 | 0.190 | 3.90x |
| continuous, per-photo | NEW (Task B alone) | 0.105 | 0.187 | 5.22x *(regression, see SS2.3)* |
| continuous_persheet | OLD (Task A alone) | 0.098 | 0.161 | 3.30x |
| **continuous_persheet** | **NEW (shipped, A+B)** | **0.098** | **0.153** | **3.30x** |

Task A alone (pooling, unchanged anchor model) already beats the 017 baseline on every column.
Combined with Task B it is unchanged-to-better again. The single worst continuous cell in the
NEW-per-photo row (dark-ruby's light2760, t_img 0.300 vs its own siblings' 0.154/0.120, GT 0.132)
is exactly fixed by pooling: the group's pooled t_img for that sheet is 0.154 (the median),
`5.22x` worst -> back to `3.30x` (in fact the SAME worst cell as the OLD-model pooled run,
confirming pooling — not the refit — is what buys the robustness here).

**LORO** (`fit_anchor.py`'s leave-one-recipe-out harness, extended with the same
per-sheet-group median pooling applied to the held-out recipe's own predictions):

| model | pooling | LORO worst-case |
|---|---|---|
| OLD (017 shipped) | per-photo (017's own number) | 3.37x |
| OLD | **per-sheet (Task A alone)** | **2.39x** |
| NEW (Task B refit) | per-photo (Task B alone) | 3.47x *(regression, see SS2.3)* |
| **NEW** | **per-sheet (shipped, A+B)** | **2.28x** |

Per-sheet pooling is the dominant driver of the LORO improvement (3.37x->2.39x with the OLD model
alone); Task B's refit does not cost anything once pooling is applied (2.39x->2.28x, slightly
better). **LORO unchanged-or-better holds for the shipped combination** (2.28x vs 017's 3.37x).

### 1.5 Product code sanity checks

- `estimate_anchor_scale_sheet([lin])` (N=1) returns bit-identical output to
  `estimate_anchor_scale(lin)` (verified directly).
- `extract_maps(..., sheet_t_img=None)` produces identical arrays to the no-parameter call
  (verified directly), and passing a sample's own `anchor_t_img` back in as `sheet_t_img`
  reproduces its own `T` map exactly (verified directly).
- Single-FILE CLI invocation (`extract.py PHOTO --class C --anchor class ...`) against the
  pre-020 `extract.py`: byte-identical (`md5` match on `_T.png`/`_h.png`) for a real library
  sheet under its manifest class/anchor.
- Manifest-mode batch run with **no** `sheet_id` (the 9-sheet library, unmodified manifest):
  **18/18 T/h PNGs byte-identical** (md5) against the pre-020 `extract.py` — this is also the
  Task B library-byte-identity gate (SS2.4), satisfied by the same run.
- Manifest-mode batch run **with** a synthetic `sheet_id` grouping 3 dark-slate lightings:
  pooled `t_img` printed = 0.2283 = `median([0.2283, 0.1830, 0.5217])`, matches by hand.
- Multi-file CLI smoke test on 3 dark-ruby lightings: pooled `t_img` = 0.1544 =
  `median([0.154, 0.300, 0.120])`, each photo still gets its own `_T.png`/`_h.png`/`_panel.jpg`.

## 2. Task B — sat_lit dim-capture fix

### 2.1 Mechanism

`anchor_features`'s luminance gate for `sat_lit` (`smoothstep(Y, 0.10, 0.30)`) is an ABSOLUTE
luminance band. Report 017 measured it reading exactly 0 on all 9 dark-family renders — no pixel
in a sufficiently dim photo ever crosses 0.10 luminance, so a strongly-tinted dark sheet
(dark-ruby) and a neutral one (dark-deep) were statistically indistinguishable on this feature,
exactly where tint would help separate them.

Fix: when the absolute gate is degenerate (`wlit.sum() <= 1` — the SAME condition the old code
already used to just return `0.0`), fall back to a gate relative to THIS photo's OWN brightest
pixels: percentile band `(p80, p97)` of the photo's own luminance distribution (shown insensitive
to the exact percentile choice: 0.182/0.199/0.175/0.195 for (80,97)/(90,99)/(70,95)/(85,99.5) on
the same degenerate dark-opaque sample). `lit_frac` (the third feature) deliberately KEEPS the
absolute gate — reading near-zero there on a dim capture is itself real signal ("how much of the
sheet transmits at all"), and making it adaptive would destroy exactly the information this fix
recovers for `sat_lit`.

On any capture where the absolute gate was already non-degenerate, this is a no-op: same code
path, same numbers as 016/017.

### 2.2 Before/after on the dark family

| sample | OLD sat_lit | NEW sat_lit |
|---|---|---|
| dark-deep (3 lightings, near-neutral authored tint) | 0.0, 0.0, 0.0 | 0.063, 0.106, 0.203 |
| dark-ruby (3 lightings, ~4:1 R:G authored tint) | 0.0, 0.0, 0.0 | **0.659, 0.693, 0.705** |
| dark-slate (3 lightings, mild B-dominant tint) | 0.0, 0.0, 0.0 | 0.0*, 0.100, 0.163 |
| dark-opaque (4 of 10 dimmest lightings) | 0.0 (x4) | 0.158-0.315 |

*one dark-slate lighting (light1530) is still non-degenerate under the OLD gate and unchanged by
construction (its `wlit.sum() > 1` already).

Exactly **12 of 35** samples change (all in the dark family: dark-deep 3/3, dark-ruby 3/3,
dark-slate 2/3, dark-opaque 4/10); **0 of the 22 cathedral/streaky/wispy samples** change, and
**0 of the 9-sheet real library's `anchor_features`** change (checked directly on
black/white/blue/amber/green.jpg — none is degenerate under the old gate). Dark-ruby's tint is
now clearly the highest of the three new dark recipes, correctly ranking "strongly tinted" above
dark-deep/dark-slate's near-neutral values — the estimator can now use tint as a cue exactly where
report 017 found it blind.

### 2.3 Refit, and the honest cost when shipped WITHOUT per-sheet pooling

The feature definition changed, so `fit_anchor.py`'s ridge-in-logit-space refit was re-run on the
same 35-sample/8-recipe set (T_LO/T_HI unchanged at 0.04/0.98); only `sat_lit`'s mu/sd/coefficient
move (0.238821->0.339133, 0.221127->0.197783, 1.28039->1.55464) — the other two features and their
coefficients move by noise. Shipped:
```
ANCHOR_FEAT_MU = np.array([-1.98505, 0.339133, 0.241629])
ANCHOR_FEAT_SD = np.array([1.16796, 0.197783, 0.327259])
ANCHOR_COEF = np.array([0.0933926, 1.55464, 0.260738, 0.476681])
```
Correct-class T-MAE, isolating Task B (per-photo, no pooling) against the OLD-model per-photo
baseline:

| recipe | OLD correct-class (ratio) | NEW correct-class (ratio) |
|---|---|---|
| cathedral-amber | 0.146 (0.97x) | 0.146 (0.97x) unchanged |
| cathedral-green | 0.139 (0.99x) | 0.136 (0.97x) noise-level |
| dark-deep | 0.050 (2.13x) | **0.034 (1.74x) improved** |
| dark-opaque | 0.069 (1.00x) | 0.070 (0.96x) noise-level |
| dark-ruby | 0.043 (1.90x) | **0.058 (2.19x) worse** |
| dark-slate | 0.125 (0.65x) | 0.126 (0.67x) noise-level |
| streaky-mix | 0.160 (0.95x) | **0.178 (0.92x) worse** |
| wispy-white | 0.122 (0.89x) | 0.122 (0.89x) unchanged |

Bright recipes (cathedral/wispy) are unaffected or marginally better; streaky-mix (a "bright"
recipe in this report's sense — GT p99 ~ 0.92) picks up a small, disclosed cost (+0.018 T-MAE,
still under 1x ratio). dark-ruby's OWN correct-class accuracy gets WORSE despite its wrong-class
robustness improving — the same mechanism as SS1.4's worst-cell regression: with `sat_lit` now
strongly informative and correlated with brightness across the bright in-sample recipes, but only
ONE recipe in this small dataset exercising "dark AND saturated", the fitted coefficient
extrapolates too aggressively on dark-ruby's own held-out-feeling corner of feature space. This is
real and would be a straightforwardly bad trade **shipped in isolation** — it is only acceptable
here because report 020's other half (per-sheet pooling) is shipped in the same commit and
overcorrects it (SS1.4: worst-cell 5.22x->3.30x, LORO 3.47x->2.28x, both better than 017).

### 2.4 Library byte-identity (016's rule, applied to Task B's constant change)

The refit moves shipped constants (`ANCHOR_FEAT_MU/SD/COEF`), so per 016's rule this gates on the
9-sheet real library staying byte-identical on the **default** path. It does, trivially by
construction and confirmed by direct diff: manifest-driven runs use `class_override` ->
`anchor='class'` (report 016 `auto` resolution), and the class-anchor path never calls
`estimate_anchor_scale`/`anchor_features` to set `T` — only to compute the `anchor_t_img` /
`anchor_scale_disagree` QA metrics. **18/18 T/h PNGs (md5) identical** between the pre-020
`extract.py` and this report's shipped version on `extract.py benchmark/library --no-vlm`. (The
QA metric numbers in the JSON sidecar DO change for the two library sheets whose photos are dim
enough to have been degenerate — none are, per SS2.2 — so even those numbers are unchanged; the
library's `anchor_t_img` values are identical to 017's.)

## 3. Honest notes

1. **Task B alone is not a safe ship.** SS2.3's LORO/worst-cell regressions are real; this report
   ships Task B only in combination with Task A, and that combination is what is validated end to
   end. A future change to the anchor's fit should re-run both the LORO and injection-worst
   checks together, not either alone.
2. **The percentile fallback band (80, 97) is a reasonable, not uniquely-correct, choice** — shown
   insensitive to nearby alternatives (SS2.1) but not swept exhaustively.
3. **Per-sheet pooling needs sheet identity as input** — the manifest `sheet_id` key or explicit
   multi-file CLI grouping. This report adds the mechanism and both entry points; deciding how the
   product UI/upload flow assigns `sheet_id` (e.g. "these 3 photos are of the piece I'm about to
   cut") is a product decision out of this report's scope.
4. **One seed per new dark recipe**, same limitation as report 017 (dark-opaque's two seed groups,
   4 and 6 lightings, are the only ones with real group-size diversity for the pooling test).
5. **`T_LO`/`T_HI`/blend constants (`ANCHOR_BLEND_TAU0/TAU1/WMAX`) are unchanged** — this report
   only refits the regression coefficients that respond to the changed `sat_lit` feature.
6. **Renders are gitignored** (repo convention); report 017's own dark-family renders were not
   preserved between sessions, so this report re-rendered them from `generate_synthetic.py`'s
   existing recipe code (unchanged since 017) and verified the GT p99 values match 017's
   measurements to 3 significant figures before running any evaluation.
7. **`estimate_anchor_scale_sheet` pools SCALE only.** It does not address 016 SS5.2 / 017 finding
   4's wrong-class `h`/assembly corruption, and does not change `h` invariance at all (SS1.4) — a
   sheet with a wrong fallback class still gets unstable, wrong `h` per lighting; that remains
   exactly as open as before.

## Reproduction

```
cd research/delighting
# re-render the dark family (report 017's recipes, unchanged)
PYTHONPATH=~/.local/lib/python3.11/site-packages <blender> -b --python-use-system-env \
    -P generate_synthetic.py -- --out dark_calibration_data/dark-deep  --recipe dark-deep  --seed 501 --count 1 --light-variations 3
# (dark-ruby: --seed 502, dark-slate: --seed 503)

# refit (Task B) + LORO before/after
python3 fit_anchor.py --data <v2_dir> \
    --data dark_calibration_data/dark-deep --data dark_calibration_data/dark-ruby --data dark_calibration_data/dark-slate \
    --recipes-before cathedral-green,cathedral-amber,dark-opaque,streaky-mix,wispy-white \
    --t-lo 0.04 --out results/anchor_persheet_refit --ship

# injection re-check (class / continuous / continuous_persheet)
python3 eval_class_injection.py --data <v2_dir> --data dark_calibration_data/dark-deep \
    --data dark_calibration_data/dark-ruby --data dark_calibration_data/dark-slate --out results/per_sheet_scale

# cross-lighting invariance re-check (oracle / continuous / continuous_persheet)
python3 eval_cross_lighting.py --data <v2_dir> --data dark_calibration_data/dark-deep \
    --data dark_calibration_data/dark-ruby --data dark_calibration_data/dark-slate --out results/per_sheet_scale

# library regression (default path must stay byte-identical)
python3 extract.py benchmark/library --no-vlm --out /tmp/lib_check

# multi-photo entry point smoke test (product code, not just eval)
python3 extract.py photo1.jpg photo2.jpg photo3.jpg --class dark-opaque --anchor continuous --out /tmp/sheet_out
```
