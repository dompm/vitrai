# Report 017 - Catalog leak cleaner: weak neural prior, not material recovery

Date: 2026-07-09. Code: `train_catalog_leak_cleaner.py`.

## 0. TL;DR

I switched the catalog from "judge" to "teacher".

Instead of training another contamination gate, I used manufacturer catalog
sheets as weak clean-material examples. Each crop is deliberately contaminated
with distorted transmitted-background structure, smooth exposure rolloff,
chromatic leakage, window/railing bars, and occasional glare. A tiny residual
U-Net then tries to recover the original catalog crop.

This is closer to the high-risk inverse-rendering story:

```text
observed sheet = physical glass material + leaked background/capture field
learned cleaner = estimate/remove the leakage while preserving measured relief
```

The result is useful but not yet shippable:

- synthetic held-out cleanup improves about 20%;
- real suncatcher luminance consistency improves modestly;
- the learned cleaner is still far behind the hand sheet prior;
- color/chroma disentanglement remains weak.

## 1. Two representations tested

Both use the same training data and model size.

| variant | idea |
|---|---|
| `catalog_leak_cleaner` | generic residual image-to-image cleanup |
| `catalog_leak_cleaner_smooth` | smooth residual only: measured high-frequency relief stays from the source; the network can edit broad leakage fields |

The smooth-residual version is the more product-shaped representation. It treats
the network as a low-frequency leakage estimator, not a painter.

## 2. Synthetic held-out

Smooth-residual run:

| metric | contaminated | neural | change |
|---|---:|---:|---:|
| RGB MAE | 0.0425 | 0.0342 | 19.5% lower |
| low-frequency MAE | 0.0393 | 0.0314 | 20.0% lower |
| high-frequency MAE | 0.0069 | 0.0070 | 1.7% worse |
| detail energy ratio | 1.000 target | 1.459 | too high |

The model learns the synthetic leakage task, but the detail ratio is a warning:
even when the residual is smooth, the output can retain too much contaminated
texture/contrast relative to the clean target.

## 3. Real suncatcher benchmark

Position sensitivity, lower is better:

| condition | mean dE | luminance CV | hue std deg |
|---|---:|---:|---:|
| raw | 8.98 | 0.407 | 1.5 |
| raw + neural | 8.02 | 0.327 | 1.6 |
| fixed `T/h` | 10.12 | 0.318 | 1.7 |
| fixed `T/h` + neural | 9.24 | 0.261 | 2.1 |
| hand sheet prior | 1.90 | 0.060 | 0.3 |

Interpretation:

- applying the cleaner directly to the raw photo helps perceptual dE more;
- applying it after fixed `T/h` helps luminance consistency more;
- neither placement gets close to the hand sheet prior;
- the hue score getting worse after `T/h + neural` means the learned model is
  mostly correcting brightness fields, not reliably separating material chroma
  from leaked background chroma.

## 4. Visual read

`results/catalog_leak_cleaner_smooth/suncatcher_sheet_contact.jpg` is the most
important contact sheet. The neural columns visibly nudge the broad field, but
the dark green window/garden-scale blob remains. The hand prior removes it much
more aggressively.

That is the right failure mode for this experiment: the learned cleaner is less
likely to airbrush real relief, but it is too timid for the hard cathedral sheet.

## 5. Decision

Keep the representation idea:

```text
measured high-frequency relief + learned smooth leakage field
```

Do not treat catalog-only supervision as enough for material recovery. It lacks
the real ambiguity we care about: a single uploaded sheet image where broad
variation may be real wispy glass, leaked background, camera exposure, or all
three.

Next high-risk step:

- train the smooth-field model on better positives: real cross-lighting pairs,
  real sheet-over-background captures, or a renderer that reproduces hammered
  cathedral background displacement;
- split luminance leakage from chroma leakage explicitly, because the current
  model improves brightness before it understands color;
- make the output a provenance-labeled assistive prior, not a silent replacement
  for the uploaded sheet.

## 6. Files

- `train_catalog_leak_cleaner.py`
- `results/catalog_leak_cleaner/summary_table.md`
- `results/catalog_leak_cleaner/metrics.json`
- `results/catalog_leak_cleaner_smooth/summary_table.md`
- `results/catalog_leak_cleaner_smooth/metrics.json`
