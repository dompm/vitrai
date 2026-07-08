# Report 004 — Backlight-hotspot recovery (+ two process decisions)

Date: 2026-07-08. Code: `extract.py` @ this commit. Panels: `results/library/`.
Worktree `.claude/worktrees/delight-003` on `research/delighting`; main checkout
untouched. Last iteration before the validation-photo pairs land.

Read 001–003 first. This iteration targets the one quality defect left standing
after 003: the **backlight-hotspot leak** — blue's bright cyan patch (p95 was the
worst in the set) and red's milder version — plus two process decisions the
maintainer made after the 003 review.

## 1. The leak and its cause

For cathedral-clear glass `T = R = I / L`, so any error in the illumination `L`
lands directly in `T`. The illumination envelope is a broad 95th-percentile
filter (window 35 % of the frame) followed by a heavy blur. A **compact backlight
hotspot** — the defocused bright blob of the light source behind the sheet — is a
smooth bright bump much narrower than that window, so the broad envelope averages
it down: `L` is too low at the hotspot, `R = I/L` runs hot, and the excess
brightness leaks into `T` as a false bright patch. Confirmed on the debug maps:
`L` peaked top-center while the bright patches in `R` sat where the hotspot
actually was (blue bottom-center / mid-right), i.e. `L` did not follow the peak.

## 2. Fix — a second, tight-window envelope, combined by max

Add a peak-tracking envelope alongside the broad one and take the pixelwise max:

```
base = blur( percentile_95( Y, window = 0.35·dim ) )        # unchanged
peak = blur( percentile_98( Y, window = 0.15·dim ), small )  # tracks compact peaks
L    = max(base, peak)
```

The key property is **compactness selectivity**: the tight-window 98th percentile
exceeds the broad 95th *only* where brightness is concentrated on a scale smaller
than the broad window — a hotspot. Over a broad uniform region (even a bright
glass color the class prior says to keep) the two envelopes agree, so
`peak - base ≈ 0` and `L` is unchanged. Measured directly: the median `L` gain is
**1.000** on every sheet — the correction touches only the ~top percentile of
pixels (the hotspot), never the bulk of the glass. That is what lets it fix blue
without darkening the eight sheets or fighting the tint/illuminant class prior
(OP-4/OP-5): it is not a brightness change, it is a *localized* one.

Chosen `(percentile 98, window 0.15·dim)` by sweep. A tighter window (0.10) was
worse on every sheet (blue MAE 2.97 → 3.09, green 0.52 → 0.55): too tight and the
peak envelope starts tracking individual bright texture glints rather than the
hotspot blob. The white-top-hat and smoothness-gated variants I tried first
either barely dented the peak (the top-hat's own blur spread it out) or were
zeroed because the hammered glass texture survives downsampling and reads as
"not smooth" — the max-of-two-envelopes is the simplest thing that actually works.

## 3. Result — blue and red improved, nothing else broke

**Before/after: `results/library/hotspot_before_after.jpg`** (blue and red,
original | 003 T | 004 T). Blue's cyan patches (bottom-center and the mid-right
blob) are visibly dimmer and the field reads as a more uniform blue; red's bright
central patch is reduced. Texture is fully preserved. The mid-right blob in blue
is weaker but not gone — this is progress, not a total cure.

Full library, self-recon MAE / p95, 003 → 004 (all improved, none regressed):

| sheet | class | MAE 003 | MAE 004 | p95 003 | p95 004 | raw_p99 |
|---|---|---|---|---|---|---|
| green | cathedral-clear | 0.64 | **0.52** | 3.5 | 2.7 | 1.38 |
| black | dark-opaque | 0.78 | **0.46** | 4.4 | 1.9 | 1.46 |
| turquoise | cathedral-clear | 1.71 | **1.29** | 10.1 | 7.0 | 1.52 |
| pink | cathedral-clear | 2.11 | **1.75** | 13.7 | 11.7 | 2.95 |
| amber | cathedral-clear | 2.12 | **1.96** | 11.9 | 11.2 | 1.95 |
| orange | cathedral-clear | 2.11 | **2.07** | 11.7 | 11.6 | 2.68 |
| red | cathedral-clear | 2.95 | **2.59** | 15.7 | 14.6 | 4.44 |
| blue | cathedral-clear | 3.45 | **2.97** | 23.4 | 20.7 | 5.06 |
| white | opalescent | 3.98 | **3.50** | 16.1 | 16.1 | 1.14 |

Benchmark: wispy 0.79 → **0.64** (p95 3.22), easy_amber 2.19 → **2.03**. The
correction helps every sheet because compact bright bumps exist on all of them at
some scale; it helps blue/red most because their hotspots are largest.

**Blue is still the weakest** (MAE 2.97, p95 20.7 — down from 24.6 at 002 but
still top of the set). Its `raw_p99` = 5.06 (§5) confirms residual outliers above
the clear level: a heavily-hammered "glue-chip" sheet with the strongest hotspot,
the hardest case in the library. Further gain would need the gradient-domain
illumination solve deferred since 001, which is more than this last-iteration
scope warrants.

## 4. DECISION 1 — VLM class is the default; manifest class is an explicit override

Implemented. In batch mode the class is resolved: `--class` (whole run) →
manifest **`class_override`** (per-file, explicit human choice) → **VLM
classifier (the default)** → `'wispy'` fallback. The manifest field was renamed
`glass_class → class_override` so a value there now *means* "a human chose this",
and there is no silent hard-coded default that can beat the classifier — that is
exactly what misclassified `white.jpg` in 002. `--no-vlm` disables the classifier
for offline/reproducible runs. Verified: with no override the VLM is called and
returns `opalescent` for white; `--no-vlm` falls back to `wispy`.

Mark localization stays **human-only** (manifest `mark_region` / `--mark-region`,
else the conservative global detector) — the VLM hallucinated a mark on the clean
black swatch (003), so it does not drive removal.

*Side note, not fixed here:* on a single file with no manifest, the global mark
detector ("unknown") over-fires on opal/milky texture (flagged 30 % of white as
marks in a smoke test). Harmless for the library (manifest sets `mark_region:
none`) but worth a `mark_region` default of `none` for milky classes when the new
eval photos arrive.

## 5. DECISION 2 — log the anchor per sheet (and what it actually reveals)

Implemented, with an honest correction to the premise. `metrics.json` now carries
`T_anchor_k` and `T_raw_p99`. **`k` turns out class-constant** (0.95 / 0.10 /
0.80) — because the illumination envelope already normalizes each sheet's clear
level to ~1 before the anchor, and `assemble_T` clips T to [0,1] so its p99
saturates; `k = target / 1.0`. So `k` alone does not show within-class variation.

The signal the maintainer actually wanted is **`T_raw_p99`** — the p99 of the
transmittance *before* that clip, i.e. how far the brightest transmitting pixels
sit above the envelope's clear level. It varies sharply and tracks exactly the
thing we care about:

`blue 5.06 > red 4.44 > pink 2.95 > orange 2.68 > amber 1.95 > turquoise 1.52 >
black 1.46 > green 1.38 > white 1.14`

The two worst-recon sheets (blue, red) top the list — `T_raw_p99` is a
cheap per-sheet flag for "residual hotspot / specular outliers, or a possible
misclass". (Anchoring `k` on this un-clipped value instead would reintroduce
outlier sensitivity — blue's raw peak of 5 would crush its clear glass to ~19 %
— which is exactly why the clip is there; hence a separate diagnostic rather than
a changed anchor.)

## 6. Constraint check

"Don't break the 8 clean sheets or the wispy case." All 8 non-blue library sheets
improved or held; wispy improved (0.79 → 0.64); the median-`L` = 1.000 measurement
shows the envelope change is localized to hotspots, not a global shift. No
regression found. `register_pair.py` re-smoke-tested (ORB 400 inliers,
T-agreement 6.1/255) after the `extract_maps` return-dict additions.

## 7. Ship read + status

The 003 verdict holds and improves: black correct and dark, white opalescent, and
now the backlight-hotspot leak that made blue/red the weakest sheets is
meaningfully reduced with no cost elsewhere. All 9 library sheets relight
plausibly; blue remains the hardest but is no longer conspicuous. Against
"reproduce the easy case faithfully", the library passes.

Per instructions, this is the last planned iteration before the user's validation
photos arrive. Remaining open items (blue's residual hotspot → gradient-domain
illumination; OP-1 hand-shadow; the milky-class mark-detector default) are all
either diminishing-returns or blocked on the `~/Downloads` cross-lighting pairs,
for which `register_pair.py` is ready. **Stopping here** — not inventing new work.
