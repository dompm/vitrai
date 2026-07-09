# Report 016 - Learned prior gate: useful, not enough

Date: 2026-07-09. Code: `learned_prior_gate.py`.

## 0. TL;DR

I tried to learn the catalog-prior gate from report 015 instead of hand-designing
it.

Training data:

- negatives: real manufacturer catalog sheets;
- positives: the same sheets with synthetic broad gradients, bokeh-like fields,
  and smooth color casts added.

The classifier separates the synthetic task reasonably:

| metric | value |
|---|---:|
| train AUC | 0.852 |
| test AUC | 0.844 |
| test accuracy @0.50 | 0.769 |
| clean false positive @0.50 | 0.256 |
| clean false positive @0.70 | 0.100 |
| synthetic leak true positive @0.50 | 0.794 |
| synthetic leak true positive @0.70 | 0.556 |

But it under-calls the real suncatcher green sheet:

| sample | learned score |
|---|---:|
| green raw | 0.51 |
| green fixed `T/h` | 0.33 |
| green prior | 0.06 |
| orange raw | 0.25 |
| orange fixed `T/h` | 0.10 |
| orange prior | 0.04 |

So the result is not a ship-shaped learned gate. It is a useful negative result:
synthetic contamination positives are not yet realistic enough to teach the real
cathedral see-through failure from report 013.

## 1. What worked

- The model learned a sensible broad signal: high total variation plus high
  low-frequency/texture ratio raises contamination probability.
- It correctly scores the prior outputs low.
- It has a conservative false-positive rate at threshold 0.70.

## 2. What failed

The real green sheet is the important case. The hand-built gate scored it 0.84
raw / 0.66 fixed `T/h`; the learned gate scores 0.51 / 0.33.

That means the synthetic leak augmentation is too generic. It creates broad
gradients and color casts, but the real failure is more specific:

```text
transmitted garden/window structure + hammered relief + green cathedral tint
```

The learned classifier sees the high hammered detail and treats it partly as
"real catalog texture", which is true, but misses that the broad structure is
still too high for the sheet.

## 3. Decision

Do not keep iterating on catalog classifiers right now. The catalog remains useful
as a guardrail and style prior, but the core research should return to inverse
rendering:

- model the see-through background residual directly;
- predict a provenance/confidence signal;
- keep relief/normal as first-class Material-v2 channels.

The next learned gate should be trained only after we have better positives:
real cross-lighting sheet photos, real hand-shadow pairs, or synthetic renders
whose background leakage looks like the suncatcher sheet.

## 4. Files

- `learned_prior_gate.py`
- `results/learned_prior_gate/learned_gate_summary.md`
- `results/learned_prior_gate/learned_gate_metrics.json`

