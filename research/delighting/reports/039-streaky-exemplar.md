# 039 — Exemplar-grounded rebuild of the streaky/wispy texture family

Branch `research/delighting-039`. Third streak attempt; the maintainer rejected the
prior version (reports 022/032's streak authoring) against real Oceanside/Wissmach
swatches with side-by-side evidence. Verdict: real Wispy/Streaky glass is **liquid**
(long curving glossy marbled swirls, sharp filament edges coexisting with smooth
gradients, strong tonal range, saturated color pairs); ours read as soft pastel
cloud-mottle, and `gt_h` rendered near-uniform white. This iteration studies the real
exemplars FIRST (docs/STREAK_EXEMPLAR_NOTES.md), then rebuilds authoring against the
measurements.

Scripts: `corpus/streak_exemplars_039.py`, `corpus/streak_color_pairs_039.py`,
`corpus/verify_streak_rebuild_039.py`, `corpus/preview_streak_T_039.py`,
`results/039/{build_board_039,forcedchoice_039}.py`. Artifacts in `results/039/`.
Recipe changes in `generate_synthetic.py`.

## TL;DR

- **Exemplar stats headline** (152 clean, non-iridescent Wispy/Streaky corpus sheets):
  real streaky glass sits at **L\* median 51**, **within-sheet L\* range 32** (flame
  sub-family 47), **C\* median 37** (p95 47), **flow coherence 0.49** (flame 0.62),
  **edge-bimodality (grad p99/p50) 6.8**. The two color modes: a LIGHT milky pull
  (L\* 66, C\* 25 — a *tinted* milky, not paper-white) and a DARK saturated color
  pull (L\* 47, C\* 28, p90 62), separated by ~14 L\*. The old streaky-mix was L\*84 /
  C\*15 — far too pale and washed, exactly the rejection.
- **gt_h uniformity root cause: the maintainer's hypothesis (023/025/037 haze retunes)
  is wrong** — those three reports all touched the *extractor's* `estimate_haze`
  (read-side); none changed authored `h`. The real causes are in authoring + the
  sRGB-on-write encode: streaky-fine-texture used a FLAT `h` (std 0); wispy-white
  FLOORED `h` at 0.5 (→ srgb 0.735 on disk, 55% of gt_h white); streaky-mix had
  authored contrast but the concave write-encode compressed it toward white.
- **Rebuild**: per-seed saturated color pairs sampled from the real distribution
  (`sample_streak_colors`); long coherent liquid pulls + hard lamination edges
  (`streak_selector` rewritten); structured haze (`streak_haze_field`) so gt_h keeps
  visible structure (std ~0.18, was ~0/floored). Rebuilt vs real: coherence
  0.11 → **0.55**, bimodality 4.5 → **6.1** (real 6.8), colors saturated, gt_h
  structured. Honest gap: `hf_energy_frac` still ~0.002 vs real 0.018 (§5).
- **Forced-choice VLM realism** (§4): detection rate FILL_DET% (chance 25%), N calls
  on FILL_MODEL, luminance-normalized lineups (so the test measures texture, not the
  corpus-vs-render exposure gap). Prior version baseline: FILL_BASELINE.
- **Review board** for the maintainer's eye: `results/039/review_board_039.jpg`
  (real exemplar | our render, per sub-family) — the final gate.
- **Validate gate**: FILL_VALIDATE. Appearance bands: FILL_BANDS.

## 1. Exemplars first (docs/STREAK_EXEMPLAR_NOTES.md)

Full measurement writeup in `docs/STREAK_EXEMPLAR_NOTES.md`. The four sub-families
(white-on-color, multi-color flame, subtle milky, dramatic dark-pair) and the
liquidity signals (flow coherence, edge bimodality, tonal range, saturated real color
pairs) are characterized there with cited exemplar files. Contact sheet:
`results/039/exemplar_contact_sheet.jpg` (30 sheets). Color-pair distribution over all
152 clean sheets: `results/039/color_pairs_summary.json`.

## 2. gt_h uniformity — measured root cause

`corpus/verify_streak_rebuild_039.py` re-derives each recipe's authored `h` (bpy
stubbed) and applies the same sRGB encode `save_numpy_to_image` bakes into every
`*.exr` on write (report 025's documented file-write encode). Before the rebuild:

| recipe (OLD) | authored h | on-disk gt_h (srgb) | reads as |
|---|---|---|---|
| streaky-fine-texture | `np.full(0.30)` — **std 0** | flat 0.584 | perfectly uniform |
| wispy-white | floor **0.5** + veils | floor 0.735, 55% >0.85 | mostly white |
| streaky-mix | 0.05..0.9 (std 0.30) | median 0.72, encode-compressed | washed toward white |

The fix (`streak_haze_field`) ties `h` to the streak structure with the *clear*
interstitial pushed genuinely low (clear_h 0.06 → srgb 0.29) well below the milky
pull (0.88 → srgb 0.94), plus fine texture. After: gt_h std ~0.18 with visible
flowing structure (preview `results/039/authored_T_preview.jpg`, gt_h rows).

## 3. Rebuild vs real bands (`results/039/rebuild_stats.json`)

`corpus/verify_streak_rebuild_039.py`, 5 seeds/recipe, authored-T measured on the
same metrics as the real exemplars:

| | L\*50 | L\*rng | C\*50 | C\*95 | coherence | bimodality | gt_h std |
|---|---:|---:|---:|---:|---:|---:|---:|
| REAL overall | 51 | 32 | 37 | 47 | 0.49 | 6.8 | — |
| streaky-mix (old) | 84 | — | 15 | — | 0.11 | — | ~0 (compressed) |
| streaky-mix (new) | 55 | 35 | 29 | 49 | **0.54** | **9.1** | **0.25** |
| streaky-fine-texture (new) | 52 | 26 | **37** | 49 | 0.57 | 5.4 | 0.11 |
| wispy-white (new) | 62 | 24 | 19 | 24 | 0.47 | 5.1 | 0.13 |

Coherence, bimodality, tonal range and chroma now land on the real bands
(streaky-fine-texture hits the real C\* median exactly; wispy-white is the subtle
end by design). Two fixes mattered beyond the color sampling: (a) the old isotropic
fine-detail overlay (coherence 0.11 = cloud-mottle) is gone, replaced by long
advected pulls (LIC length 150, fine cross-flow source); (b) `streak_selector` now
recenters the advected field by median/IQR instead of min-max — the old additive
lamination term had silently pushed the selector median to ~0.84, making every sheet
~80% light-mode (a big part of the rejection's 'washed colors'); pinning the median
at 0.5 gives every seed the real ~50/50 light/dark split (measured real light_frac
p50 = 0.5).

Appearance bands (021's grounding harness, `corpus/appearance_stats.py` re-derivation
at seed 42): streaky-mix L 55 / C 29, streaky-fine-texture L 52 / C 37, wispy-white
L 62 / C 19 vs real wispy class L 56.8 / C 28.5 — all inside the class band (old
streaky-mix was L 84.4 / C 15.0, old wispy-white L 89.1 / C 2.1, both outside).

## 4. Forced-choice realism test

FILL_SECTION_4

## 5. Honest gaps

1. **`hf_energy_frac` ~0.002-0.006 vs real 0.018.** A long-standing gap across ALL
   synthetic recipes (021 §3): smooth-edged advected streaks carry little energy in
   the outer FFT ring. The liquid *macro* structure is now correct; the finest
   micro-grain is still under-energized. Not fixed here.
2. **Domain gap in the forced-choice test.** The real corpus is bright backlit
   light-table photography; our renders are HDRI-ambient (the delighting dataset's
   deliberate "handheld capture" model). Lineups are luminance-normalized to stop the
   model cheating on exposure, but residual lighting-geometry differences remain — the
   test measures texture realism approximately, not perfectly.
3. **L\* runs ~10 points light** of the real median; a further pass could bias the
   color sampler darker, but the current values sit inside the real p25-75 and the
   visual read is right (review board).

## Reproduction

```
cd research/delighting
python3 corpus/streak_exemplars_039.py        # exemplar contact sheet + stats
python3 corpus/streak_color_pairs_039.py       # color-pair distribution (152 sheets)
python3 corpus/verify_streak_rebuild_039.py    # rebuilt vs real bands + gt_h
python3 corpus/preview_streak_T_039.py         # authored-T + gt_h preview
# board renders (mid-EV, mark-free):
for r in streaky-mix streaky-fine-texture wispy-white; do for s in 42 101 202; do
  BLENDER -b -P generate_synthetic.py -- --out results/039/board_renders --seed $s \
    --count 1 --light-variations 1 --recipe $r --hdri-dir hdri_pack \
    --no-tex-dump --exr-codec DWAA --fixed-ev 0.5 --no-marks; done; done
python3 results/039/build_board_039.py         # results/039/review_board_039.jpg
python3 results/039/forcedchoice_039.py --model sonnet --n 10
```

Corpus read-only via the frontend symlink (reports 015/021 convention). HDRI pack
copied from the af3208c1b80c6942c worktree (`hdri_pack/`, CC0, gitignored).
