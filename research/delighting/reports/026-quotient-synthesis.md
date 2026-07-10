# 026 — Cross-track synthesis: stress-testing the intern's luma-quotient finding

Date: 2026-07-10. Branch `research/delighting-026` (off `research/delighting` @ `369fa43`, i.e.
after main-track reports 022-025). Code touched: `extract.py` (new `--illum {classical,quotient}`
flag, `luminance_envelope_quotient`, `estimate_illumination`/`extract_maps`/`process`/`main`
threading — additive, default path unchanged), `report_026_grid.py` (new, the four-condition/
four-instrument grid harness). Artifacts: `results/luma_quotient_prior_026/` (Task A refresh),
`results/quotient_synthesis_026/` (Task C grid + library contact sheets). Data: `render_022`
(13 recipes/26 samples) and `render_023_holdout` (seeds 800-812/26 samples), both found
pre-rendered read-only in other worktrees (per the task's pointer — no re-render needed). No PR —
reports are the deliverable.

**Credit up front**: the finding under test here is the intern track's. Report 019
(`019-luma-quotient-prior.md`, `luma_quotient_prior.py`) found that a deterministic,
chroma-preserving log-luminance quotient —

```text
output = input * exp(-alpha * (smooth_logY - median_smooth_logY))
```

— beats both the classical fixed-`T/h` extractor and two learned catalog-cleanup networks on the
real tutorial suncatcher's position-sensitivity benchmark, at `alpha=1.0`. This report does not
replace that idea; it re-measures it against the current pipeline, wires it into the classical
extractor as an optional stage, and scores the result — including where the classical model does
things the quotient structurally cannot — the same standard the intern's own report 019 §2
demanded of the learned cleaners it falsified.

## 0. TL;DR

- **Task A (refresh)**: re-running her exact benchmark with the CURRENT (post-023/025) extractor
  shows the classical baseline improved substantially but the quotient's win holds. Fixed `T/h`
  dE 10.12 (stale) → **9.30** (current) — closes ~72% of the raw-vs-relit dE gap and pulls hue_std
  from 1.7 to **1.2** (now better than raw's 1.5) — but classical STILL does not beat raw-copy's
  dE (9.30 vs 8.98). The quotient at `alpha=1.0` also improves (dE 3.18 → **2.38**) and remains far
  ahead of both raw and classical. **Neither 023 nor 025 touched the see-through-background
  problem the quotient is implicitly working around; the classical fixes closed color-constancy
  and anchor bugs, not this.**
- **Task B (hybrid)**: `extract.py --illum {classical,quotient}` (default `classical`, byte-
  identical to every prior report — verified to 15 decimals on all 9 library sheets). `quotient`
  mode swaps ONLY `estimate_illumination`'s smooth envelope for report 019's log-luminance
  quotient; chroma fit, marks, haze, and the absolute anchor are the exact same downstream code.
- **Task C (grid)**: the hybrid does **not** dominate broadly. On the real suncatcher (both
  sheets cathedral-clear, haze≈0, chroma fit inert) hybrid ≈ quotient-alone, both dramatically
  ahead of classical/raw (dE 2.45 / 2.44 vs 9.30 / 8.98). But on the 13-recipe synthetic suite
  spanning every glass class, hybrid **regresses** classical on macro-averaged T_mae (0.148 vs
  0.108), badly regresses haze (h_mae 0.403 vs 0.154 — 2.6x worse), regresses preview-invariance
  fidelity (27.8 vs 18.2 sRGB/255), and regresses cross-lighting invariance (0.148 vs 0.093) —
  because the downstream haze/anchor machinery was implicitly tuned against the classical
  envelope's percentile-based absolute referencing, and the quotient's median-recentered
  referencing breaks that assumption everywhere haze/chroma actually engage (i.e., everywhere
  except cathedral-clear).
- **quotient-alone** (no material model at all, applied directly to the raw photo, given the SAME
  generous single-scalar exposure-match hack raw-copy already gets in every eval here) is a
  genuinely strong **fast preview normalizer**: it beats classical on macro preview-invariance
  (15.6 vs 18.2) and macro cross-lighting invariance (0.082 vs 0.093), and — with an oracle scale
  it cannot produce itself — often beats classical's T-shape accuracy too (dark-family
  especially: dark-ruby 0.009 vs 0.040, dark-slate 0.038 vs 0.130). It also has a real, disclosed
  failure mode: on one cathedral-blue sample its own median luminance sits near zero, and a
  single global oracle-scale gain overshoots by 30x (T_mae 4.32) — the flat-median-scale trick is
  not robust without class/channel-aware handling, which is exactly the kind of hand-holding a
  real anchor exists to avoid needing.
- **Verdict**: quotient and material model serve **different product surfaces**, not one
  dominating the other. Quotient-alone is closer to a fast, deterministic preview-consistency
  filter — cheap, chroma-preserving, no haze, no absolute scale, cannot relight beyond an
  exposure hack. The classical/hybrid material model is the only one of the four conditions that
  produces `h`, an absolute anchor, mark removal, and a haze-driven relight formula — the things a
  normalizer fundamentally cannot do (§5). The specific **hybrid** integration tested here (a
  clean envelope swap) is not the right depth of integration for a shared solution: it inherits
  the quotient's benefit only where downstream calibration doesn't care (cathedral-clear, which
  happens to be the real suncatcher's own class) and inherits its liabilities everywhere the
  classical extractor's haze/anchor logic actually does work.

## 1. Task A — refresh the baseline: does 023/025 close the dE gap?

`luma_quotient_prior.py` unmodified, re-run in this worktree (which already contains 023's
saturation-collapse/anchor fixes and 025's haze-units fix — confirmed: `git merge-base
--is-ancestor <her-019-commit> <023's-fix-commit>` returns true, i.e. her report 019 numbers were
measured against a pre-023 `extract.py`). Output: `results/luma_quotient_prior_026/`.

| condition | dE (stale, report 019) | dE (current, report 026) | lumCV (stale) | lumCV (current) | hue (stale) | hue (current) |
|---|---:|---:|---:|---:|---:|---:|
| raw | 8.98 | 8.98 | 0.407 | 0.407 | 1.5 | 1.5 |
| fixed `T/h` | 10.12 | **9.30** | 0.318 | **0.306** | 1.7 | **1.2** |
| quotient `a=0.25` | 8.30 | 7.36 | 0.255 | 0.245 | 1.7 | 1.1 |
| quotient `a=0.50` | 6.42 | 5.59 | 0.189 | 0.180 | 1.7 | 1.2 |
| quotient `a=0.75` | 4.68 | 3.80 | 0.120 | 0.113 | 1.7 | 1.1 |
| quotient `a=1.00` | 3.18 | **2.38** | 0.056 | **0.051** | 1.7 | **1.1** |
| hand sheet prior | 1.90 | 1.97 | 0.060 | 0.059 | 0.3 | 0.3 |

Reading it straight: **023/025 did close a large fraction of the gap, but not the finding.**
Fixed `T/h`'s dE-vs-raw gap shrinks from 1.14 (stale) to 0.32 (current) — a ~72% reduction — and
its hue_std actually flips from worse-than-raw (1.7 vs 1.5) to better-than-raw (1.2 vs 1.5). This
is exactly what report 023's saturation-collapse fix should do (it targeted color-constancy, and
hue is the axis that fix most directly touches). But classical STILL does not beat raw-copy on
dE, and the quotient's improvement (3.18 → 2.38, still ~74% lower than classical) tracks the SAME
direction as classical's own improvement — both extractors got better at the same time, on the
same underlying photos, which is consistent with 023/025 fixing real, general bugs (color
constancy, haze units) rather than something specific to this benchmark. The quotient's win is
not an artifact of a stale, buggy classical baseline. Note (her prior's) hand sheet prior is
essentially unchanged (1.90→1.97) since it's built directly from `relit`'s own high-frequency
residual, not from any of the axes 023/025 fixed.

Methodology note for §3 below: this refresh reproduces her exact harness (quotient applied on top
of `relit`, restricted to the sheet's `interior` crop). Task C's grid instead applies quotient
conditions directly to the RAW photo and at whole-image scope (matching how the classical/hybrid
extractor already treats the same photos) for a fair four-way comparison — see §3.1's numbers,
which differ slightly (2.44/2.45 vs 2.38) for that reason, not a discrepancy.

## 2. Task B — the hybrid: `extract.py --illum {classical,quotient}`

`estimate_illumination(lin, glass_class, W, illum="classical")` now branches on a new `illum`
parameter. `illum="quotient"` swaps ONLY the line that builds the smooth luminance envelope:

```python
env = luminance_envelope_quotient(Y) if illum == "quotient" else luminance_envelope(Y)
```

`luminance_envelope_quotient` is report 019's math, reframed as a positive scalar field to divide
out of the input (the same role `luminance_envelope`'s percentile-filter envelope plays):

```text
out = in * exp(-alpha * (low - median(low)))  =  in / exp(alpha * (low - median(low)))
                                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                                        this ratio IS the "env" swapped in
```

`QUOTIENT_ALPHA = 1.0` (her winning value); `QUOTIENT_SIGMA_FRAC = 0.0243` generalizes her fixed
`sigma=34px` (tuned at the suncatcher harness's 1400px working resolution: 34/1400 = 0.0243) to
`extract.py`'s own configurable `--size`, so the blur radius stays proportional. Everything after
that line — the milky-pixel chroma polynomial fit (still only for wispy/opalescent), mark
detection/removal, `estimate_haze`, `assemble_T`, the absolute anchor (`T_ANCHOR`/continuous) — is
the exact same code, unconditionally, for both `illum` values.

`quotient_alone` (used only in the eval harness, not part of `extract.py`'s pipeline) reuses the
identical `luminance_envelope_quotient` helper applied directly to the raw photo with no
downstream steps at all — so quotient-alone and hybrid are provably the same core removal,
integrated at two different depths, not two different formulas.

**Default-path byte-identity, verified not assumed**: `extract.py benchmark/library --no-vlm`
(the default `--illum classical`) reproduces report 025's shipped `h_mean` to 15 decimal places on
all 9 sheets (amber 0.060011998866325, black 0.261509469089380, ..., white 0.467521020159542 —
exact matches). The new flag and helper function are pure additions; `git diff --stat extract.py`
is 82 insertions / 13 deletions, all inside the new parameter threading, none of it on a path that
executes when `--illum` is omitted.

## 3. Task C — the four-condition grid

Four conditions, scored identically wherever the instrument permits:

| condition | what it is |
|---|---|
| `raw` | the untouched photo |
| `quotient_alone` | report 019's removal applied directly to the raw photo — no chroma fit beyond what falls out of dividing by a luminance-only field, no haze, no absolute anchor |
| `classical` (current T,h) | the shipped extractor, `--illum classical` (post-023/025) |
| `hybrid` | `--illum quotient` — classical pipeline, quotient-built envelope |

### 3.1 Real-suncatcher position sensitivity (her instrument, `report_026_grid.py`)

Both sheets are cathedral-clear (haze≈0, chroma-fit branch inert) — the only real end-to-end asset
this project has.

| condition | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| raw | 8.98 | 0.407 | 1.5 |
| quotient-alone (a=1.0) | 2.44 | 0.073 | 1.2 |
| current T,h (classical) | 9.30 | 0.306 | 1.2 |
| hybrid (quotient illum) | **2.45** | **0.072** | **1.2** |

Hybrid ≈ quotient-alone here, both far ahead of classical/raw — unsurprising given §2's design:
for cathedral-clear, chroma is inert and haze is near-zero regardless of illum mode, so hybrid's
extra machinery barely perturbs the quotient's own removal. **This is also the ONLY real-photo
instrument available, and it happens to be the one glass class where the hybrid's liabilities
(below) don't engage** — a scoping caveat, not a flaw in the measurement.

### 3.2 Synthetic per-pixel GT accuracy (`render_022` + `render_023_holdout`, 13 recipes, 26 samples)

Macro-average across the 13 recipes (unweighted):

| condition | T_mae | h_mae |
|---|---:|---:|
| raw (unscaled) | 0.320 | n/a |
| quotient-alone (unscaled) | 0.330 | n/a |
| quotient-alone (oracle-scaled*) | 0.185 (0.101 excl. one outlier†) | n/a — no haze channel exists |
| classical (current T,h) | **0.108** | **0.154** |
| hybrid | 0.148 | 0.403 |

\* oracle-scaled = a single global gain per sample matched to that sample's own GT median — a
disclosed cheat quotient-alone cannot reproduce without ground truth at inference time; reported
as an upper bound on what a hypothetical future calibration step could buy it, not a claim it can
do this itself.
† `cathedral-blue__seed808__light3441`: quotient-alone's own median (across all pixels/channels)
sits at 0.0078 (R channel median 0.0016 on a strongly blue-tinted recipe) — a single global gain
matched to that near-zero denominator explodes (`T_mae` 4.32 on that one sample, dragging the
recipe mean to 1.19). This is a failure of the flat-median-scale heuristic specifically, not of
the underlying removal; it is exactly the "which channel/pixel population defines the true clear
level" ambiguity `T_ANCHOR`/the continuous anchor exist to resolve properly.

Per-recipe (T_mae `classical` / `hybrid` / `quotient-alone-oracle-scaled`, h_mae `classical` /
`hybrid`):

| recipe | T classical | T hybrid | T q-alone(oracle) | h classical | h hybrid |
|---|---:|---:|---:|---:|---:|
| cathedral-amber | 0.116 | 0.138 | 0.095 | 0.041 | 0.030 |
| cathedral-blue | 0.137 | 0.131 | 1.191† | 0.030 | 0.030 |
| cathedral-green | 0.175 | 0.229 | 0.144 | 0.026 | 0.030 |
| cathedral-red | 0.131 | 0.222 | 0.237 | 0.028 | 0.030 |
| dark-deep | 0.092 | **0.031** | **0.010** | 0.155 | **0.678** |
| dark-opaque | 0.059 | 0.088 | 0.045 | 0.119 | **0.670** |
| dark-ruby | 0.040 | 0.028 | **0.009** | 0.057 | **0.765** |
| dark-slate | 0.130 | 0.141 | **0.038** | 0.261 | **0.823** |
| dark-textured | 0.028 | 0.038 | 0.028 | 0.101 | **0.648** |
| saturated-opalescent | 0.105 | 0.150 | 0.164 | 0.287 | 0.301 |
| streaky-fine-texture | 0.154 | 0.169 | **0.076** | 0.289 | 0.275 |
| streaky-mix | 0.164 | 0.318 | 0.224 | 0.312 | 0.327 |
| wispy-white | 0.074 | 0.236 | 0.146 | 0.302 | **0.635** |

The haze column is the headline break: **every dark-family and wispy recipe's h_mae explodes
under hybrid** (dark-ruby 0.057→0.765, dark-slate 0.261→0.823, wispy-white 0.302→0.635), while
cathedral's h_mae is untouched (as expected — its haze branch barely depends on the fitted R at
all). Diagnosis (verified directly, one dark-ruby sample): under `illum=classical`, `R`'s p99 is
~1.0 pre-anchor (the percentile envelope's whole point is to normalize the sheet's clear level to
~1, so `T_ANCHOR`'s pct/target convention and `estimate_haze`'s absolute-brightness thresholds
(`smoothstep(Y, 0.70, 0.92)`, the milkiness cue) see the sheet at the scale they were tuned
against). Under `illum=quotient`, `R`'s p99 sits at exactly the clip ceiling (0.1999...) with a
much lower median (0.055 vs classical's 0.118) — the quotient recenters to the sheet's OWN median
log-luminance, not to an assumed "clear/fully-transmitting" percentile reference, so the SAME
downstream haze/anchor code (tuned against the classical convention) reads a differently-scaled,
differently-shaped `R` and its milkiness/brightness cues misfire. The anchor still "works" in the
sense that `k` recalibrates to hit the class target (dark-ruby k: 0.2 classical vs 3.5 hybrid),
but haze's absolute-threshold cues are not scale-corrected the same way, and they break.

### 3.3 Preview-invariance uniform-target (relight fidelity; sRGB/255, lower=better)

quotient-alone here gets the exact same single-scalar `exposure_match` hack already given to
raw-copy in `eval_preview_invariance.py` (a percentile-luminance gain matched to the target) — it
has no absolute anchor either, so without this hack it would be scored against an arbitrary
luminance level. **This is the "exposure hack" the task brief asked to be disclosed, not hidden**:
quotient-alone's preview fidelity is exactly as anchor-free as raw-copy's; it just starts from a
flatter, more consistent field.

Macro-average:

| condition | MAE (sRGB/255) |
|---|---:|
| raw (exposure-matched) | 29.9 |
| quotient-alone (exposure-matched) | **15.6** |
| classical (current T,h) | 18.2 |
| hybrid | 27.8 |

quotient-alone beats classical here on the macro-average — driven mostly by the dark family,
where classical's continuous-anchor extrapolation is a known weak spot (report 023 §6.2 already
flagged this as pre-existing, not new): dark-deep classical 36.9 vs quotient-alone 7.3, dark-ruby
16.9 vs 6.9, dark-slate 27.9 vs 12.1. Classical wins clearly on wispy-white (8.0 vs 18.4) and
dark-opaque (10.9 vs 10.0, close) — cases where haze genuinely matters and quotient-alone has
none. Hybrid is close to raw-copy on average (27.8 vs 29.9) and is the worst condition on several
recipes (wispy-white 56.7, streaky-fine-texture 42.9, streaky-mix 41.6) — the broken haze from
§3.2 directly degrades the relit preview here, since `render_preview` multiplies by
`(h + (1-h)*B)` and an inflated `h` washes the controlled backdrop's structure into a flatter,
wrong-looking preview.

### 3.4 Cross-lighting invariance (same authored glass, N lightings; pairwise field MAE)

Macro-average:

| condition | invariance (lower=better) |
|---|---:|
| raw | 0.095 |
| quotient-alone | **0.082** |
| classical | 0.093 |
| hybrid | 0.148 |

quotient-alone is the most invariant condition on average — a deterministic, class-free transform
with no per-photo fitted state is a hard thing to beat on THIS metric almost by construction.
Hybrid is the least invariant by a wide margin on exactly the classes where §3.2 found broken
haze (saturated-opalescent 0.190 vs classical 0.070, streaky-mix 0.313 vs 0.116,
streaky-fine-texture 0.268 vs 0.090) — the haze estimate's misfiring is itself unstable
lighting-to-lighting, compounding the accuracy break into an invariance break too.

### 3.5 Library default-path check

`extract.py benchmark/library --illum classical` (the default) is confirmed byte-identical to
report 025 (§2 above) — the flag-gated design means nothing changes unless explicitly requested.
For illustration (not required, since the default doesn't move), `--illum quotient`'s effect on
the 9-sheet library is substantial and worth seeing:

| sheet | class | classical h_mean | hybrid h_mean | classical T_mean | hybrid T_mean |
|---|---|---:|---:|---|---|
| black | dark-opaque | 0.262 | **0.593** | [0.038, 0.045, 0.033] | [0.023, 0.028, 0.022] |
| white | opalescent | 0.468 | 0.443 | [0.536, 0.558, 0.581] | [0.409, 0.432, 0.451] |
| amber/blue/green/orange/pink/red/turquoise | cathedral-clear | 0.060 (all) | 0.060 (all) | e.g. red [0.700,0.009,0.024] | e.g. red [0.326,0.005,0.012] |

`black.jpg`'s haze estimate breaks exactly as §3.2 predicted (0.26 → 0.59 — a real black-opaque
sheet reading as nearly as milky as `white.jpg`, clearly wrong). Every cathedral tile ALSO comes
out roughly 40-55% dimmer under hybrid (e.g. red 0.700→0.326, orange 0.775→0.442) — the anchor
still lands near its class target numerically, but the pre-anchor statistic it's scaling from
differs enough between illum modes that the shipped `T_ANCHOR`/continuous-anchor constants (fit
exclusively against the classical envelope's convention, reports 003-023) are simply untested
for the quotient path. Position-sensitivity dispersion metrics (§3.1) don't notice a uniform
dimming; a real product surface would. Contact sheets: `results/quotient_synthesis_026/
library_classical_contact.jpg`, `library_hybrid_contact.jpg`.

## 4. Reading the grid together

The pattern across §3.1-3.4 is consistent, not contradictory:

- **Cathedral-clear (the real suncatcher's own class)**: hybrid ≈ quotient-alone, both far ahead
  of classical. Nothing downstream (chroma fit, haze) engages differently between illum modes for
  this class, so the quotient's benefit passes through cleanly.
- **Every other class (dark-family, wispy, opalescent)**: hybrid is worse than classical on T_mae,
  much worse on h_mae, worse on preview-invariance, and much worse on cross-lighting invariance.
  The quotient's median-recentered envelope is not a drop-in replacement for the classical
  envelope's percentile-based absolute referencing, and the haze/anchor code downstream was tuned
  against the latter, not the former.
- **quotient-alone**, evaluated fairly (same exposure-match hack raw-copy gets, oracle scale
  disclosed as a cheat where used) is a strong, honest **normalizer**: it wins or ties classical on
  3 of 4 instruments' macro-averages (preview-invariance, cross-lighting invariance, and T-shape
  accuracy once given a scale) — genuinely humbling for the classical extractor's hand-tuned
  complexity on non-cathedral classes, similar in spirit to the intern's own report 019 finding
  about the neural cleaners. It is NOT competitive on haze at all, because it has none.

## 5. What a normalizer can and cannot do vs a material model (honest semantics)

**What the quotient (alone or as the hybrid's envelope) fundamentally cannot do**, regardless of
tuning:

1. **No absolute scale.** `exp(-alpha*(low-median))` is defined relative to the photo's OWN
   median log-luminance — it has no notion of "what should a fully-transmitting patch of THIS
   class of glass look like." That is exactly the ambiguity `T_ANCHOR`/the continuous anchor
   exist to resolve (reports 003, 016, 017, 020, 023). §3.2's cathedral-blue outlier and §3.5's
   library dimming are both this same gap surfacing in two different places.
2. **No haze/diffusion channel.** There is no `h` at all in quotient-alone, and the hybrid's `h`
   is actively harmed (§3.2/3.4) because haze estimation depends on brightness/texture cues
   calibrated against the classical envelope. A normalizer cannot represent "milky opal that
   glows and hides the background" as a distinct physical quantity — it can only flatten
   brightness.
3. **No background separation.** The quotient removes a SMOOTH field; whatever leaked
   see-through structure survives at coarser-than-`sigma` scale survives untouched, same as
   classical `T`'s own known residual (report 013's "north-star hard case"). Task A's refresh
   confirms this directly: 023/025 improved color-constancy and anchor calibration, not this axis,
   and the quotient doesn't touch it either — it just doesn't make it visibly worse for
   cathedral-clear glass, which is why report 019's celebrated real-photo win is measured
   entirely on that one class.
4. **No hotspot handling.** `luminance_envelope`'s `max(base, peak)` (report 004) exists
   specifically to track a compact backlight hotspot that a broad percentile filter would
   over-smooth. The quotient's single Gaussian-blur-of-log has no equivalent — a strong local
   hotspot would leak into the flattened output, or a small `sigma` tuned to catch it would
   over-flatten real texture at that same scale. Not exercised by either the real suncatcher
   (diffuse garden backlight, no hotspot) or the synthetic recipes used here (uniform HDRI
   backlight) — an untested gap, not a measured one.
5. **No relight beyond an exposure hack.** §3.3 shows quotient-alone needs the identical
   generous single-scalar gain raw-copy already gets to be scored on ANY absolute preview target.
   It cannot be re-lit under a new controlled backdrop the way `render(T, h, illum_rgb, bg)` can,
   because it never separates the glass's own transmittance from the backlight it happened to be
   photographed against.

**What the classical/hybrid material model does that a normalizer cannot**, confirmed by this
report specifically: an absolute anchor calibrated against a class prior AND real-photo evidence
(823/025's units-corrected haze target, 023's cathedral T_ANCHOR refit); a real `h` that drives a
physically-motivated relight blend; mark detection/removal; a sanity-gated anchor fallback for
degenerate extractions (report 016). None of these exist for quotient-alone by construction, and
the hybrid's attempt to keep them while swapping only the envelope shows they are not
cleanly separable from the classical envelope's specific convention — they were tuned as one
system, not independently composable stages, at least not without a re-tuning pass this report did
not attempt (flagged in §6).

## 6. Verdict

**The hybrid does not dominate.** It wins decisively on the one real-world instrument available
(§3.1), but that instrument's glass class happens to be exactly the one where the hybrid's
liabilities don't engage — it is not evidence the hybrid generalizes, and §3.2-3.4's 13-recipe
synthetic suite shows it clearly regressing classical everywhere haze and chroma correction
actually matter.

**Quotient and material model serve different product surfaces.** Quotient-alone is a legitimate
candidate for a **fast, deterministic preview-consistency filter**: cheap (one Gaussian blur in
log-luminance space), chroma-preserving, no class prior needed, and — per this report's grid —
competitive with or better than the full classical pipeline's T-shape accuracy, preview
invariance, and cross-lighting invariance on a 13-recipe synthetic suite, PROVIDED it is given the
same scale/exposure accommodation raw-copy already receives and is not asked to produce haze,
absolute color, or a relightable material. The classical/hybrid material model remains the only
surface that can produce `h`, an absolute anchor, and a real relight — the **full relight**
surface, not the fast-preview one.

The specific hybrid integration built here (a clean, minimal envelope swap) is not the right
depth to unify the two: it inherits the quotient's benefit only where downstream haze/anchor
calibration doesn't care, and inherits its cost everywhere that calibration does. A future
attempt at a real hybrid would need one of: (a) re-fit `T_ANCHOR`/`ANCHOR_*`/haze-formula
constants specifically against the quotient-envelope's convention (a real retuning pass, not
attempted here — flagged, not done, same overfitting-guard discipline as reports 009/017/022/023);
or (b) use the quotient as a complementary SIGNAL (e.g., a confidence/consistency check on the
classical envelope, or a fallback when the classical envelope's anchor gate fires) rather than a
wholesale replacement of it.

## 7. Honest limits

1. **Only one real-photo instrument exists, and both its sheets are cathedral-clear** — the
   quotient's real-world win (both hers and this report's hybrid) is unverified on any real
   milky/opalescent/dark-family photo. The synthetic 13-recipe suite is the only evidence for
   those classes, and it points the opposite direction.
2. **The "oracle-scale" cheat used in §3.2 is disclosed, not defensible as a product path.** A
   single global median-ratio gain is itself fragile (the cathedral-blue outlier) — a real
   deployment of quotient-alone with any absolute-scale ambition would need its own anchor,
   which reintroduces exactly the class-prior/continuous-anchor machinery the classical model
   already has.
3. **No re-tuning of `estimate_haze`/`T_ANCHOR`/`ANCHOR_*` for the quotient-envelope convention
   was attempted.** §3.2/3.4's hybrid regressions are diagnosed (the percentile-vs-median
   referencing mismatch, §3.2) but not fixed — fixing them is a real, separate research pass, not
   a one-line change, and doing it without dedicated held-out data would repeat the exact
   overfitting mistake this report series has repeatedly guarded against (009 §2.1, 017, 022 §6,
   023 §6.1).
4. **`QUOTIENT_SIGMA_FRAC`'s generalization from her fixed 34px is a principled scaling choice,
   not independently validated against a second real photo at a different working resolution** —
   the real suncatcher benchmark happens to run at exactly her original 1400px scale end-to-end
   (unaffected), so this report cannot confirm the generalization holds at `extract.py`'s own
   default `--size 700` on a DIFFERENT real sheet.
5. **Hotspot behavior (§5 item 4) is untested, not just unimplemented** — neither available
   instrument exercises a compact backlight hotspot, so the quotient's known structural gap there
   (no `max(base,peak)` equivalent) has no measurement, only a design-level flag.
6. **Preview-invariance's `raw`/`quotient_alone` exposure-match hack is generous by the same
   amount to both** (report 022/023's own convention) — the comparison between them is fair, but
   neither is being scored the way classical/hybrid are (their own anchor, no post-hoc gain
   correction), so §3.3's macro-average is not an apples-to-apples ranking across all four
   conditions simultaneously, only within the {raw, quotient-alone} and {classical, hybrid} pairs
   separately. Flagged, not resolved — a genuinely fair four-way comparison would need a single
   shared absolute-scale convention none of the four naturally share.

## 8. Files

- `extract.py` — `--illum {classical,quotient}`, `luminance_envelope_quotient`, threaded through
  `estimate_illumination`/`extract_maps`/`process`/`main`. Default path verified byte-identical.
- `report_026_grid.py` — the four-condition/four-instrument grid harness (new).
- `results/luma_quotient_prior_026/` — Task A refresh (her exact harness, current extractor):
  `metrics.json`, `summary_table.md`, `sheet_contact.jpg`.
- `results/quotient_synthesis_026/` — Task C: `instrument{1,2,3,4}_*.json`, `grid_summary.json`,
  `library_default_path_check.json`, `library_classical_contact.jpg`,
  `library_hybrid_contact.jpg`.
