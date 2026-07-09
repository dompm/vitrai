# Report 015 - Catalog prior gate

Date: 2026-07-09. Code: `catalog_prior_gate.py`, updated
`catalog_texture_audit.py`.

## 0. TL;DR

Report 014 showed a sheet-level prior can make the real suncatcher sheets far
more position-consistent, but applying that prior everywhere would be dangerous.

This report adds a first gate:

> Does this sheet have anomalously high broad low-frequency variation for its
> presumed manufacturer-style family, without chroma evidence that the variation
> is true material?

On the suncatcher sheets, the score behaves as hoped:

| sample | score |
|---|---:|
| green raw | **0.84** |
| green fixed `T/h` | **0.66** |
| green sheet prior | 0.14 |
| orange raw | 0.54 |
| orange fixed `T/h` | 0.22 |
| orange sheet prior | 0.10 |

This means the gate asks for help on the contaminated sheet photo, still sees
some remaining issue after fixed `T/h`, and stands down once the prior removes
the suspicious broad variation.

## 1. Gate definition

The gate uses the catalog audit distribution from 1,381 manufacturer sheets. For
a presumed material family, it computes robust z-scores:

- `z_lowfreq` - broad low-frequency variation;
- `z_lum` - total luminance variation;
- `z_chroma` - chroma variation, often real material in wispy/streaky glass;
- `z_detail` - high-frequency texture, often hammered relief to preserve.

The score is high when low-frequency variation is high, but chroma/detail do not
strongly argue that the variation is the material itself.

For the tutorial hammered cathedral sheets, the closest catalog family is treated
as `Textured/Baroque` for gate calibration even though the extractor class remains
`cathedral-clear`.

## 2. Result

Full suncatcher table:

| sample | family | score | z_lowfreq | z_chroma | z_detail | lowfreq_cv | highfreq_std |
|---|---|---:|---:|---:|---:|---:|---:|
| green raw | Textured/Baroque | 0.84 | 1.3 | -0.4 | 0.8 | 0.611 | 0.564 |
| green fixed `T/h` | Textured/Baroque | 0.66 | 0.8 | -0.4 | 0.8 | 0.477 | 0.558 |
| green prior | Textured/Baroque | 0.14 | -0.9 | -0.7 | -0.0 | 0.087 | 0.341 |
| orange raw | Textured/Baroque | 0.54 | 0.4 | -0.3 | 0.3 | 0.400 | 0.432 |
| orange fixed `T/h` | Textured/Baroque | 0.22 | -0.2 | 0.5 | 0.0 | 0.258 | 0.353 |
| orange prior | Textured/Baroque | 0.10 | -1.1 | -0.4 | -0.5 | 0.050 | 0.216 |

Read:

- `green_raw` is a strong prior-assist candidate.
- `green_relit` still scores moderately high, matching report 013's finding that
  fixed `T/h` did not remove the garden/window residual.
- both prior outputs score low, which is what we want if the prior cleaned up the
  suspicious variation.
- `orange_raw` is borderline, and fixed `T/h` is enough to push it below the
  assist threshold. That matches the visual: the orange sheet is less badly
  contaminated than green.

## 3. Catalog self-check

The gate is not yet safe as an automatic product rule:

| category | n | median score | flagged >0.50 | flagged >0.70 |
|---|---:|---:|---:|---:|
| Cathedral | 699 | 0.29 | 15% | 6% |
| Opalescent | 356 | 0.33 | 21% | 10% |
| Wispy/Streaky | 163 | 0.28 | 21% | 10% |
| Textured/Baroque | 138 | 0.28 | 21% | 9% |
| English Muffle | 17 | 0.38 | 18% | 12% |
| Ring Mottle | 8 | 0.24 | 25% | 0% |

At a 0.50 threshold, false positives are too common. At 0.70, the gate is more
conservative and still catches the worst green raw sheet. This points to a
product shape:

- score > 0.70: show/try catalog-prior assistance;
- 0.45-0.70: offer artist-tuned cleanup or warn that the photo is lighting-heavy;
- below 0.45: leave the sheet mostly sheet-derived.

## 4. Why this matters

This is the missing honesty layer for the high-risk prior:

```text
sheet photo -> fixed T/h -> catalog gate -> optional prior -> provenance label
```

The gate creates a place for uncertainty. Instead of always making the sheet
prettier, Vitrai can say:

> This preview is mostly sheet-derived, but broad lighting/background variation
> was reduced using a catalog prior.

That is much more aligned with the artist feedback from report 012.

## 5. Next move

The hand-built gate should become learned:

1. use catalog rows as "real material variation" negatives;
2. use synthetic/augmented photos with pasted background gradients/bokeh as
   contamination positives;
3. train a small classifier or calibration head for `prior_strength`;
4. feed `prior_strength` into Material-v2 rendering and provenance UI.

## 6. Files

- `catalog_prior_gate.py`
- `results/catalog_prior_gate/gate_summary.md`
- `results/catalog_prior_gate/gate_metrics.json`
- updated `results/catalog_texture_audit/metrics.json` with compact per-image
  catalog rows for downstream gate experiments.

