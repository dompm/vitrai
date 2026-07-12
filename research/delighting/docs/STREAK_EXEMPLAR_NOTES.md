# Streaky/Wispy exemplar notes (report 039)

Measured, exemplar-first characterization of the real Wispy/Streaky corpus, written
BEFORE re-authoring the streak recipe family. The maintainer rejected the prior
(3rd) streak version against real Oceanside/Wissmach swatches: ours read as soft
pastel cloud-mottle; real streaky glass is **liquid** — long curving glossy marbled
swirls, sharp filament edges coexisting with smooth gradients, strong tonal range,
saturated color pairs. This document is the grounding those recipes are rebuilt on.

Scripts: `corpus/streak_exemplars_039.py` (30-sheet curated variety + per-sheet
metrics + contact sheet), `corpus/streak_color_pairs_039.py` (color-pair
distribution over ALL 152 clean, non-iridescent Wispy/Streaky sheets). Artifacts in
`results/039/`. Corpus (`clean_manifest.json`, 158 Wispy/Streaky wispy-class sheets)
read-only via the frontend symlink, reports 015/021 convention.

## 1. The variety (contact sheet `results/039/exemplar_contact_sheet.jpg`)

30 sheets hand-picked to span the maintainer's named variety. Four sub-families
emerge, and the rebuild targets all four rather than the pastel middle:

- **white-on-color (woc, n=14)** — Oceanside "X + White Wispy" / Bullseye "X, White
  2-Color Mix": a bright milky pull sweeping through a **saturated** color body.
  `oceanside-of83896s.jpg` (Navy Blue+White): L\*50 32, within-sheet L\* range **49**,
  chroma p95 42, coherence 0.47, edge-bimodality 9.0. `oceanside-of3591s.jpg`
  (Red+White): C\* p95 65. These are the maintainer's flagship "white-on-blue /
  white-on-red".
- **multi-color flame (n=8)** — Oceanside Fusers Reserve (Phoenix, Fiesta, Antelope
  Canyon, Aurora, Tiger Eye): the most dramatic, long glossy flowing swirls of 2-4
  colors. `oceanside-ofr72.jpg` (Fiesta): L\* range **58**, coherence **0.71**,
  Δab between color modes **41**. `oceanside-ofr93.jpg` (Antelope Canyon): C\* p95 71.
- **subtle / color-on-white (cow, n=5)** — "Clear+White Wispy", "Cream", "Pale
  Amber": the low-drama end (L\* 77, C\* 16). Our OLD recipes looked like ONLY this
  group — that is the rejection.
- **dramatic dark-pair (n=5)** — deep two-tone (Navy/Royal, Charcoal/White, Lotus):
  strong tonal contrast, lower coherence where the pull curls tightly.

Photo caveats found on the sheet (excluded from grounding): `Phoenix` tile is a
folded-sheet product shot on black (edge geometry, not a flat swatch); `Charcoal+
White Mix` is mostly black; `Clear+White Wispy` shows window reflections (front-lit
contamination). Iridescent/dichroic/luminescent-named sheets (6 of 158) are excluded
from the color aggregate per report 021's convention.

## 2. What makes real streaky glass read as LIQUID (measured)

Per-sheet medians over the curated set (`results/039/exemplar_summary.json`), center
70% crop, 256px:

| statistic | real overall | woc | flame | what it means for authoring |
|---|---:|---:|---:|---|
| L\* median | 51 | 55 | 48 | mid, NOT the L\*84 of the old washed recipe |
| L\* range (p95-p5) within sheet | 32 | 32 | **47** | strong tonal range in ONE sheet — bright pull over dark body |
| C\* median | 37 | 41 | 33 | **saturated**, not pastel (old recipe C\*15) |
| C\* p95 | 47 | 47 | 50 | the color pull gets very saturated |
| structure-tensor coherence | 0.49 | 0.48 | **0.62** | directional flow, not isotropic mottle (old recipe 0.11) |
| edge bimodality (grad p99/p50) | 6.8 | 8.0 | 5.5 | sharp filament/lamination edges COEXIST with smooth blends |
| color-pair Δab (2-means on a\*b\*) | 16 | 15 | 22 | two distinct color modes |
| hf_energy_frac | 0.018 | 0.018 | 0.018 | fine detail (long-standing synthetic gap, §4) |

The four liquidity signals, in priority order:

1. **Flow coherence.** Real streaks are long pulls spanning most of the sheet with a
   coherent direction and gentle curl (coherence 0.49; flame 0.62). The old recipe's
   isotropic fine-detail overlay dragged coherence to 0.11 — this is the single
   biggest "cloud-mottle vs liquid" difference.
2. **Edge bimodality.** In one sheet you see BOTH razor-sharp lamination/filament
   boundaries AND smooth color gradients (grad p99/p50 ≈ 7). Not uniformly soft.
3. **Tonal range.** A bright milky pull (L\* ~66) over a saturated darker body (L\*
   ~47) gives a within-sheet L\* range of 30-58. The old near-white recipe had no
   dark body to contrast against.
4. **Saturated color pairs from the real palette** (§3).

## 3. Real color-pair distribution (`results/039/color_pairs_summary.json`, n=152)

Per sheet, 2-means split into a LIGHT (milky/white pull) mode and a DARK (saturated
color) mode:

| mode | L\* p25 / p50 / p75 | C\* p25 / p50 / p75 |
|---|---|---|
| light (milky pull) | 53 / **66** / 78 | 14 / **25** / 41 |
| dark (color pull) | 31 / **47** / 64 | 16 / **28** / 42 (p90 **62**) |

- **L\* separation** between the two modes: p50 **14**, p75 23, p90 31.
- The light mode is a **tinted milky (C\* ~25), not paper-white** — a key correction:
  the old recipe used a near-pure-white [0.9,0.9,0.95] light pull (C\*~2).
- **Dark-mode hue mass** (chroma-weighted): amber 30-60° (strongest), yellow-green
  60-90°, green 120-150°, blue/purple 270-300°, red 0-30°. This is the real streaky
  palette the rebuild samples from — not invented pastels.

## 4. The gt_h uniformity root cause (maintainer's measured problem)

The maintainer measured streaky-mix's `gt_h` rendering near-uniform white and
hypothesized reports 023/025/037's haze retunes flattened it. **That hypothesis is
wrong** — 023/025/037 all touched the *extractor's* `estimate_haze` (read-side); none
changed authored `h`. The real causes are three, in the authoring + write path
(`corpus/verify_streak_rebuild_039.py`, srgb-encoded gt_h stats):

1. **streaky-fine-texture used a FLAT `h = np.full(..., 0.30)`** (021 §5 flat-haze
   target) — std 0, literally zero haze structure. The clearest "lost contrast" case.
2. **wispy-white FLOORED `h` at 0.5.** Every `*.exr` is sRGB-encoded on write
   (`save_numpy_to_image`, documented in report 025): 0.5 → 0.735 on disk. Floor
   0.735 + veils above → 55% of gt_h pixels read >0.85 (white).
3. **streaky-mix's h had real authored contrast** (0.05..0.9, std 0.30) but the
   concave sRGB write-encode lifts the whole field (0.05→0.25, median 0.47→0.72) and
   compresses the milky-vs-clear contrast toward the bright end.

Fix (rebuild, §5): `streak_haze_field()` ties `h` to the streak structure — milky
pulls hazy, saturated interstitial genuinely CLEAR (clear_h pushed to 0.06 → srgb
0.29, well below milky 0.88 → srgb 0.94) plus fine texture — so the on-disk gt_h
keeps visible structure (measured gt_h std 0.18, was ~0 / floored).

## 5. Authoring targets handed to the rebuild

- Sample a **saturated** color pair per seed from §3 (streaky-mix at the dramatic
  end: dark C\* 36-54, light a tinted milky C\* 14-26; L\* separation ~14-20).
- Long coherent pulls: LIC advection length ~150 on a fine cross-flow source
  (`base_scale` ~16) → coherence ~0.55, matching real; gentle curl for the swirl.
- Bimodal edges: keep smooth advected veils AND hard lamination lines (streak
  selector `lam` boosted) → grad p99/p50 ~6, matching real ~7.
- Thin curved filaments (existing `filament_layer`) — the single strongest streaky
  cue in the exemplars.
- Structured `h` via `streak_haze_field` — never flat, never floored.
- **Honest residual:** `hf_energy_frac` stays ~0.002-0.006 vs real 0.018. This is a
  long-standing gap across ALL synthetic recipes (021 §3) — smooth-edged advected
  streaks carry little energy in the outer FFT ring. The liquid *macro* structure is
  now right; the finest micro-grain is still under-energized. Flagged, not hidden.

## Reproduction

```
cd research/delighting
python3 corpus/streak_exemplars_039.py     # contact sheet + per-sheet + summary
python3 corpus/streak_color_pairs_039.py   # color-pair distribution (all 152)
python3 corpus/verify_streak_rebuild_039.py# rebuilt recipes vs real bands + gt_h
python3 corpus/preview_streak_T_039.py     # authored-T + gt_h preview montage
```
