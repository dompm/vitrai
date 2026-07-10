# Report 018 - Luma-only leakage field: safer, weaker, more honest

Date: 2026-07-09. Code: `train_catalog_leak_cleaner.py --output-mode luma`.

## 0. TL;DR

Report 017 showed that the learned catalog cleaner mostly helps brightness but
can drift hue/chroma. I tried a stricter representation:

```text
output = input * smooth_scalar_exposure_field
```

The network can reduce broad luminance leakage, but it cannot repaint glass
color. This is less powerful than RGB cleanup, but it is more honest.

## 1. Result

Synthetic held-out:

| metric | contaminated | luma neural | change |
|---|---:|---:|---:|
| RGB MAE | 0.0425 | 0.0371 | 12.8% lower |
| low-frequency MAE | 0.0393 | 0.0345 | 12.2% lower |
| high-frequency MAE | 0.0069 | 0.0069 | flat |
| detail energy ratio | 1.000 target | 1.360 | still high |

Real suncatcher position sensitivity:

| condition | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| raw | 8.98 | 0.407 | 1.5 |
| raw + luma neural | 8.40 | 0.387 | 1.4 |
| fixed `T/h` | 10.12 | 0.318 | 1.7 |
| fixed `T/h` + luma neural | 9.34 | 0.291 | 1.7 |
| hand sheet prior | 1.90 | 0.060 | 0.3 |

Comparison to report 017's RGB smooth-field model:

| model after fixed `T/h` | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| RGB smooth-field | 9.24 | 0.261 | 2.1 |
| luma-only field | 9.34 | 0.291 | 1.7 |

RGB smooth-field is more effective at brightness consistency. Luma-only is more
conservative and keeps hue stable.

## 2. Product read

This is not the most impressive cleanup. It is the more trustworthy cleanup.

For the right-side glass sheet panel, a luma-only assist could be presented as:

```text
remove uneven backlight / background brightness, preserve uploaded glass color
```

That is easier to explain and safer than silently changing chroma. The user can
then decide whether to apply a stronger learned/color prior when the confidence
is high.

## 3. Decision

Keep both heads conceptually:

- **safe luma head**: default assistive cleanup, preserves color provenance;
- **RGB/chroma head**: stronger, only with confidence or paired-data training;
- **hand/catalog prior**: ceiling/proposal, never silent ground truth.

The next useful neural model should be two-headed:

```text
luminance leakage field + optional chroma leakage field + confidence/provenance
```

Catalog-only supervision is enough to probe the luma head. It is not enough to
trust the chroma head.

## 4. Files

- `train_catalog_leak_cleaner.py`
- `results/catalog_leak_cleaner_luma/summary_table.md`
- `results/catalog_leak_cleaner_luma/metrics.json`
- `results/catalog_leak_cleaner_luma/suncatcher_sheet_contact.jpg`
