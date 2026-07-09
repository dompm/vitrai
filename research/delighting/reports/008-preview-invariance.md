# Report 008 — Preview-invariance benchmark: raw RGB copy vs material relight

Date: 2026-07-09. Code: `eval_preview_invariance.py` @ this commit. Data:
existing `synthetic_data/` from report 007. Deliverables:
`results/preview_invariance/summary.json`, `summary_table.md`, and per-recipe
contact sheets.

## 0. Why this benchmark exists

The app problem is not only "can we recover ground-truth `T,h`?" It is:

> When an artist drags a cut piece over a glass sheet, does the preview look like
> the same physical glass in a controlled stained-glass render, or does it look
> like copied pixels from a particular phone photo?

Reports 005/007 score per-pixel material accuracy. This report adds a
product-shaped metric that compares two ways of producing the final preview:

1. **Raw-copy baseline** — use the captured photo as the texture. To make this a
   generous baseline, the script exposure-matches the raw photo to the target
   preview with one global luminance gain. It still keeps the source background,
   frame/mullions, HDRI color, and cast shadows.
2. **Material relight** — extract `T,h` from the photo and render those maps into
   the same controlled preview scene.

The target is rendered from authored synthetic ground truth:

```
preview = illum * T * (h + (1-h) * controlled_background)
```

The controlled background is a warm neutral workbench with soft lead-like grid
lines. Uniform white was deliberately avoided because it collapses the haze term:
`T*(h+(1-h)*1) = T`, making `h` invisible to the preview metric.

Metric units below are sRGB MAE on a 0-255 scale.

## 1. Results

Command:

```
python3 research/delighting/eval_preview_invariance.py \
  --data research/delighting/synthetic_data \
  --out research/delighting/results/preview_invariance \
  --size 700
```

| recipe | n | raw MAE | material MAE | raw shadow gap | material shadow gap | raw shadow inside | material shadow inside | raw p95 | material p95 |
|---|---|---|---|---|---|---|---|---|---|
| cathedral-amber | 2 | 39.8 | 22.3 | 2.1 | 2.5 | 44.4 | 55.8 | 99.7 | 79.1 |
| cathedral-green | 7 | 36.4 | 22.8 | 2.0 | 2.5 | 46.9 | 59.8 | 92.5 | 76.9 |
| dark-opaque | 2 | 18.9 | 42.9 | 0.9 | 0.6 | 31.5 | 23.6 | 39.7 | 53.6 |
| streaky-mix | 4 | 46.6 | 18.2 | 2.3 | 1.3 | 64.1 | 21.2 | 93.1 | 46.1 |
| wispy-white | 2 | 65.6 | 15.8 | 1.7 | 1.7 | 27.0 | 19.3 | 103.1 | 32.1 |

Aggregate:

- All samples: raw-copy MAE **40.6**, material-relight MAE **23.2**.
- Excluding dark-opaque, where the current extractor is known too-dark: raw-copy
  MAE **43.5**, material-relight MAE **20.6**.
- Inside detected cast-shadow regions, non-cathedral classes improve from raw
  **48.9** to material **21.0**. Cathedral classes get worse inside shadows
  because the extractor still reads the cast shadow as lower transmittance.

## 2. What the contact sheets show

**Wispy-white is the clearest product win.** Raw-copy looks like a dim phone
photo; material-relight becomes a warm milky pane over a controlled background.
The target is still softer/cleaner than the extracted render, but the user-facing
experience has moved from "photo pasted into a shape" toward "translucent glass
in a scene." This is the strongest evidence that `T,h` is the right product
abstraction.

**Streaky-mix also wins strongly.** The material preview removes most of the
capture background and shadow dependence. Remaining error is the same issue from
report 007: the extractor neutralizes blue-white tint and over-hazes some clear
streaks.

**Cathedral is improved but not solved.** Material-relight is much closer to the
controlled target than raw-copy, but because cathedral-clear currently trusts
`R = I/L`, some source HDRI background and relief/lensing texture still lands in
`T`. Inside cast shadows, the material route is worse than raw-copy: the shadow
becomes a fake dark patch in transmittance. This is exactly the app limitation
the benchmark was meant to expose.

**Dark-opaque fails the material route.** Raw-copy beats material-relight because
the current absolute transmittance anchor extracts dark glass too dark
(`T_mean_ext` was already reported in 007 as about 0.08 vs gt 0.19). For dark
opaque, the immediate product risk is not source-background bleed; it is
over-dark relighting.

## 3. Product interpretation

This benchmark reframes the research target:

> Optimize for controlled-preview invariance, not only for per-pixel `T,h`
> reconstruction.

That matters because an extractor can be imperfect yet still product-useful if
the final preview becomes stable, relightable, and less dependent on the capture
photo. Conversely, a numerically plausible `T` can fail the user if a hand
shadow becomes a permanent dark streak in every cut piece.

The current classical pipeline is already good enough to justify a product spike
for **opalescent/wispy/streaky glass preview relighting**. It is not yet safe as
a universal replacement for raw texture display:

- dark-opaque needs a corrected absolute-scale anchor;
- cathedral-clear needs source-background/shadow separation before we promise
  stable material maps;
- shadow handling should be measured locally, not only by whole-image averages.

## 4. Next research moves

1. **Make preview-invariance a first-class eval.** Future extractor changes
   should report this table alongside `eval_synthetic.py`; it is closer to the
   Vitrai product promise than raw `T_mae`.
2. **Shadow-aware loss / mask.** Use synthetic with/without-shadow pairs to train
   or tune a shadow detector. The right output may be a confidence mask plus
   inpainted `T`, not a pure local correction.
3. **Class-specific product gates.** Ship material relight experimentally for
   wispy/opalescent classes first; keep raw display or a hybrid blend for
   dark-opaque and cathedral until their failure modes improve.
4. **Learned clear-glass separation.** For cathedral, the hard case is not
   exposure; it is transparent glass over structured backgrounds. The product
   metric should supervise a learned prior to remove source background while
   preserving glass relief that should remain visible.

## 5. Files

- `eval_preview_invariance.py` — benchmark harness.
- `results/preview_invariance/summary.json` — machine-readable per-sample and
  per-recipe metrics.
- `results/preview_invariance/summary_table.md` — compact table.
- `results/preview_invariance/contact_*.jpg` — visual rows:
  raw clean | raw shadow | target | material clean | material shadow |
  raw error | material error | shadow mask.
