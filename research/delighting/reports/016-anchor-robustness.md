# Report 016 — Anchor robustness under class-prior error

Date: 2026-07-09. Branch `research/delighting-anchor` (off `research/delighting-corpus`).
Code: `extract.py` (sanity gate + continuous anchor), `eval_class_injection.py`,
`corpus/spotcheck_anchor.py`. Artifacts: `results/class_injection/`. Data: synthetic v2
(26 samples, 5 recipes, authored GT; read-only from the `research/delighting-datav2`
worktree), the 9-sheet real library, and 10 catalog-corpus swatches from report 015's
backlit-verified subset. No PR — reports are the deliverable.

**Why this iteration exists.** The pipeline's absolute T scale (and with it the haze
baseline and every relight) hangs on `T_ANCHOR[class]` — and the class is unreliable in
the wild. Report 015 measured the VLM prior at **30.6%** against catalog metadata
(barely above chance), and a case-by-case audit of its confusions shows the *metadata*
is itself noisy marketing taxonomy at class boundaries (§4 has two literal examples:
a "dark-opaque" registry row whose photo is a front-lit iridescent coating, another
whose photo is a *white* tile). Neither side can be trusted, so a class error is not an
edge case — it is the expected operating condition. Under the class anchor a class
error is silently also a *brightness* error, up to 0.95/0.20 = **4.75x**, report 003's
own documented failure mode #1. Report 015 additionally caught a *within*-class
catastrophic failure: a texture-free saturated swatch drove `T_anchor_k` to 880 and
collapsed T to black. This iteration makes the anchor degrade gracefully instead of
failing hard, in two independent layers: a cheap sanity gate (§2) and a continuous,
image-statistics anchor with the class prior demoted to regularizer (§3).

## 1. Headline — class-error injection (THE table)

`eval_class_injection.py`: every synthetic-v2 sample extracted under **all four**
class priors; extracted T scored against authored GT. Cells are `T_mae (lum-ratio)`
where lum-ratio = extracted/GT mean T luminance — "how many times too bright/dark the
sheet comes out". `*` marks the correct (oracle) class column.

### Current class anchor

| recipe (oracle) | as opalescent | as wispy | as cathedral-clear | as dark-opaque |
|---|---|---|---|---|
| cathedral-amber (cathedral-clear) | 0.200 (1.00x) | 0.214 (1.15x) | 0.146 (0.97x) * | **0.507 (0.20x)** |
| cathedral-green (cathedral-clear) | 0.210 (1.01x) | 0.269 (1.18x) | 0.144 (1.01x) * | **0.439 (0.21x)** |
| dark-opaque (dark-opaque) | **0.482 (3.29x)** | **0.574 (3.83x)** | **0.474 (3.51x)** | 0.058 (0.74x) * |
| streaky-mix (wispy) | 0.198 (0.85x) | 0.136 (1.02x) * | 0.246 (0.83x) | **0.632 (0.17x)** |
| wispy-white (wispy) | 0.159 (0.82x) | 0.122 (0.89x) * | 0.167 (0.89x) | **0.720 (0.19x)** |

### Continuous anchor (this report)

| recipe (oracle) | as opalescent | as wispy | as cathedral-clear | as dark-opaque |
|---|---|---|---|---|
| cathedral-amber (cathedral-clear) | 0.200 (1.00x) | 0.214 (1.15x) | 0.146 (0.97x) * | 0.198 (0.73x) |
| cathedral-green (cathedral-clear) | 0.206 (1.00x) | 0.254 (1.16x) | 0.138 (0.99x) * | 0.218 (0.63x) |
| dark-opaque (dark-opaque) | 0.207 (1.90x) | 0.233 (2.12x) | 0.182 (1.86x) | 0.064 (0.99x) * |
| streaky-mix (wispy) | 0.218 (0.81x) | 0.159 (0.95x) * | 0.272 (0.76x) | **0.433 (0.46x)** |
| wispy-white (wispy) | 0.159 (0.82x) | 0.122 (0.89x) * | 0.167 (0.89x) | 0.310 (0.68x) |

### Summary

| design | correct-class mean T_mae | wrong-class mean T_mae | worst wrong-class brightness error |
|---|---|---|---|
| class anchor (current) | 0.107 | 0.399 | **9.73x** (wispy-white as dark-opaque, dim-lit sample) |
| continuous anchor | 0.112 | **0.226** | **3.80x** |

The win condition from the brief — *dark-opaque misread as cathedral must NOT come out
~5x too bright* — holds: that cell goes **3.51x → 1.86x** too bright (T_mae 0.474 →
0.182), and the mirror error (cathedral misread as dark-opaque) goes 5x too dark
(0.20x) → 0.73x. Every dark↔bright confusion improves by 2–3x in scale error; the
opalescent↔wispy↔cathedral confusions were never scale-catastrophic (targets 0.88 vs
0.95) and are essentially unchanged — their wrong-class error is dominated by the h/
assembly paths, which this iteration deliberately did not touch (§5). Correct-class
cost is +0.005 mean T_mae, concentrated in dark-opaque samples under bright lighting
(0.058 → 0.064); the 9-sheet real library is *visually unchanged* under correct
classes (§4).

## 2. Layer 1 — the anchor sanity gate (shipped, default-on)

**Mechanism of the k=880 blowup, diagnosed:** on a texture-free, uniformly *saturated*
swatch under the opalescent/wispy prior, `assemble_T`'s saturation cue reads every
pixel as background bleed-through, confidence collapses to 0 everywhere,
`diffusion_fill` has no trusted source pixel, and T comes out **identically zero** —
so `k = target / max(p99(T), 1e-3)` hits the floor at 0.88/1e-3 = 880 and T stays
black (recon MAE 83/255). An out-of-band k is therefore a *symptom of a degenerate T
assembly*, not a fixable gain — clamping k alone would keep the black T.

**The gate** (`ANCHOR_K_MIN, ANCHOR_K_MAX = 0.05, 5.0` in `extract.py`): if k leaves
the band, rebuild T from the directly-observed R (the same assembly the
cathedral-clear path uses; R is never degenerate), re-anchor, clamp as a last resort,
and set `anchor_fallback` in the metrics for batch QA.

**Band choice, from data:** across every in-sample extraction available — 26
synthetic-v2 samples (oracle class), the 9-sheet library, the 2 benchmark singles, and
report 015's 57-image corpus subset — k spans **[0.20, 0.9614]**; the blowup sits at
880. The band gives ≥ 4x margin on both sides of every healthy value (report 015
suggested k > 5; verified — zero in-sample false positives). k ≈ class target in
healthy extractions because the illumination envelope normalizes each sheet's clear
level to ~1, so the band is really asking "is pre-anchor p99(T) within 4-5x of 1" —
class-agnostic and hard to trip legitimately. In the injection eval the gate fired in
**0 of 1,144** design cells, i.e. even wrong classes on clean photos don't trip it.

**Verification (zero regressions):** synthetic eval and library batch byte-identical
with the gate in place; the blowup case (`wissmach-wf40105.jpg`) goes recon MAE
**83.13 → 0.46** with a plausible saturated-red T instead of black (first row of the
contact sheet, `results/class_injection/corpus_spotcheck.jpg`).

## 3. Layer 2 — the continuous anchor (opt-in: `--anchor continuous`)

`estimate_anchor_scale(lin)` predicts the anchor target (the sheet's p99
transmittance, the exact statistic `T_ANCHOR` pins) from **three class-free
statistics of the raw linear photo**: `log p95(luminance)` (absolute brightness of
the brightest transmitting regions — the main scale cue), luminance-**gated** mean
saturation (only pixels bright enough for saturation to be signal — tinted cathedral
stays saturated even when dim; dense dark glass reads dim *and* desaturated), and the
lit-pixel fraction. Sigmoid-mapped ridge fit in logit space, tuned **only** on the 26
synthetic-v2 samples with authored GT. Accuracy: leave-one-sample-out mean scale ratio
1.45x, worst ~3x — vs the 4.75x a dark↔cathedral class flip costs the class anchor.

**The class prior becomes a regularizer** (`blend_anchor_target`): if image estimate
and class target agree within 1.5x, the class target is used untouched (zero drift on
healthy extractions — this is why the library is unchanged); as disagreement grows to
3x, up to 85% of the log-space distance moves to the image estimate (never 100%: a
correct class can't be fully overridden by a deceptive photo). Constants picked from a
blend sweep on the injection eval (`results/class_injection/blend_sweep_tables.md`);
neighbors trade ±0.005 correct-class vs ∓0.02 wrong-class — the choice is flat, not
razor-tuned.

**Feature hardening — the measured trade at the heart of this design.** The tightest
*synthetic* fit (LOO mean 1.27x) uses raw p90-saturation and mean milkiness. Both are
Cycles artifacts in disguise, caught on real photos: sensor noise at near-black gives
the library's genuinely-black sheet `sat_p90 = 0.90` ("vividly tinted" → t_img 0.39),
and real hammered-opal surface relief kills milkiness' smoothness term (library
white.jpg milk 0.12 vs synthetic wispy ~0.5 → t_img 0.36 for a bright milky sheet —
which would re-darken exactly the sheet report 009's fix brightened). The gated
feature set fixes both real cases (white → 0.93, black → 0.28) at a measured synthetic
cost (LOO 1.27x → 1.45x, and the injection table's dark-opaque wrong-class cells are
~1.9-2.1x instead of the tighter fit's ~1.3-1.4x). Chosen deliberately: the brief's
goal is robustness in the wild, and the synthetic-only accuracy was measurably an
overfit to render cleanliness.

**Free QA signal in every mode:** `t_img` is now computed even under the class anchor,
and metrics carry `anchor_scale_disagree` = ratio between t_img and the class target.
On the library (all classes human-verified) the max is 1.53; the corpus registry-noise
images (§4) sit at ~4.7. A `> 2` threshold is a clean "class and photo disagree —
review" flag with zero library false positives.

## 4. Real-photo checks

**9-sheet library, correct classes, class vs continuous anchor:** 8 of 9 sheets
byte-similar (t_img within the 1.5x trust band, target unchanged — including
black.jpg: t_img 0.281 vs target 0.20, T stays near-black at 0.043 mean luminance);
blue.jpg moves −0.003 luminance (t_img 0.62, 1.53x, just past the band edge).
**No visible correct-class regression on real photos.**

**Corpus spot-check** (10 swatches from report 015's subset, incl. the k=880 blowup;
contact sheet + numbers in `results/class_injection/corpus_spotcheck.{jpg,json}`).
Each row: original, then relit-warm under metadata-class/class-anchor,
metadata/continuous, flipped-class/class-anchor, flipped/continuous:

- **The blowup (`wissmach-wf40105`)**: gate fires under both anchors; output is a
  plausible deep red (T lum 0.28) instead of black. Fixed by layer 1 alone.
- **Correctly-labeled, genuinely backlit swatches** (7 of 10): continuous ==
  class-anchor output under the metadata class, to the pixel or nearly (all t_img
  within/near the trust band). The regularizer design does what it promised.
- **Under the flipped class**, continuous rescues both directions on real photos:
  milky white flipped to dark-opaque comes out 0.70 T-lum instead of 0.19; a dark
  sheet flipped to cathedral comes out 0.18 instead of 0.29; the dark textured
  cathedral (`w18h`) flipped to dark-opaque 0.14 instead of 0.04.
- **The two movers under CORRECT metadata are metadata noise, audited by eye**:
  `wissmach-wblacki` ("dark-opaque" by the black-opal keyword rule) is actually a
  **front-lit photo of the iridescent rainbow coating** — no dark glass is visible in
  a single pixel; extraction is invalid under either anchor (report 015 failure mode
  1) and t_img=0.94 simply reports what the photo shows. `bullseye-0000130030ffull`
  ("dark-opaque" registry row) is a **white tile photographed on a black table** —
  t_img=0.94 is *more* faithful to the photo than the label. Both are exactly the
  `anchor_scale_disagree > 2` review case, and both get flagged.

## 5. Honest limits

1. **The gauge ambiguity is compressed, not removed.** "Dark glass under bright
   backlight" vs "bright glass under dim backlight" genuinely overlap in single-photo
   statistics; the estimator holds the error to ~2-3x where the class anchor fails by
   5-10x, but a dark-opaque sheet under the wrong class still comes out ~1.9-2.1x too
   bright (vs 0.99x under the correct class). Only an in-frame reference (or exposure
   metadata — still unexploited, OP-7) can do better.
2. **Streaky/wispy misread as dark-opaque remains the worst cell** (0.433, 0.46x):
   the anchor can only fix T's *scale*; under the dark-opaque prior the h and
   assemble_T paths also change (dark pixels become "the glass"), and those errors
   are class-conditional in ways no anchor can undo. Wrong-class h corruption is
   untouched by this iteration across the board — T-MAE improvements here are scale
   improvements only.
3. **The estimator's low end is calibrated by ONE dark recipe family** (2 seeds, gt
   p99 ≈ 0.216, authored "dim tinted, not near-black"). Leave-that-recipe-out and the
   fit cannot predict dark at all (LORO worst 4.2x) — the fitted floor (T_LO=0.10)
   and the blend are what protect genuinely-blacker real sheets, not the fit itself.
   More dark synthetic seeds (or real labeled darks) are the single highest-value
   data addition for this estimator.
4. **Front-lit / iridescent photos are garbage-in regardless of anchor** (report 015
   §2's triage still applies). The continuous anchor reads the photo; if the photo
   does not show transmitted light, neither anchor produces a meaningful T. The
   disagree flag at least surfaces these automatically now.
5. **Tuning-set size**: 26 renders, 5 recipes, one HDRI family. The blend sweep and
   feature choice are honest within that set (LOO/LORO reported), but the constants
   deserve a refit when synthetic v3 or real labeled photos exist.

## 6. Recommendation

- **The sanity gate should stay default-on everywhere** (it already is on this
  branch): zero measured regression anywhere, kills the one catastrophic in-corpus
  failure, and fired on nothing else across 1,144 injection cells.
- **The continuous anchor should become the default whenever the class comes from
  the VLM or catalog metadata** — i.e. every batch/corpus run: the class source is
  ~30% accurate there (report 015), the wrong-class T-MAE drops 43% (0.399 → 0.226)
  with worst-case brightness error 9.73x → 3.80x, and the real-photo checks show
  zero drift when the class happens to be right. For **human-verified classes**
  (library manifest, artist override) the class anchor is still marginally better
  (correct-class 0.107 vs 0.112) and semantically cleaner — keep `--anchor class` as
  the manifest/override path. Code default is left at `class` on this branch pending
  maintainer sign-off, since flipping it changes every downstream batch metric.
- **Always log `anchor_scale_disagree` and review anything > 2** (free, already in
  metrics in every mode): on real data it precisely flagged the two registry-noise
  images and nothing else.

## Reproduction

```
cd research/delighting
python3 eval_class_injection.py --data <synthetic_data_v2> --out results/class_injection
python3 eval_class_injection.py --data <synthetic_data_v2> --out /tmp/sweep --sweep   # blend tuning
python3 corpus/spotcheck_anchor.py        # needs the catalog_images symlink (report 015)
python3 extract.py benchmark/library --no-vlm [--anchor continuous] --out /tmp/lib
```
