# Report 009 — GlassNet-zero: first neural inverse-rendering swing

Date: 2026-07-09. Code: `train_glassnet_zero.py` @ this commit. This is the
first explicitly high-risk neural track experiment after the Codex research
persona pivot in `docs/CODEX_RESEARCH_PERSONA.md`.

## 0. TL;DR

I installed PyTorch into the ignored research venv and trained a tiny CPU U-Net
on the existing synthetic glass data. This is **not product-ready** and not even
a fair "new user sheet" test yet. It is a deliberately small probe:

> Can a learned inverse-rendering prior remove capture lighting/background from
> the controlled Vitrai preview better than raw pixels or the classical
> extractor?

Answer:

- **Without class conditioning:** mixed. It beat classical on cathedral-green
  and wispy-white, but failed dark-opaque badly.
- **With glass-class conditioning:** extremely strong on the held-out-lighting
  split: GlassNet preview MAE **1.3-6.7** vs classical **11.6-42.6** across all
  five held-out samples.
- **Important caveat:** the split holds out a lighting/capture of a material
  whose sibling lighting is in training. This tests cross-lighting material
  consistency, **not new-sheet generalization**. The next test must hold out
  material identities once the generator produces enough seeds per class.

This is exactly the kind of signal the high-risk track is for: not reliable
enough to ship, too promising to ignore.

## 1. Setup

Script:

```
research/delighting/train_glassnet_zero.py
```

Inputs:

- existing `synthetic_data/` from reports 006-008;
- clean and with-shadow photo variants;
- ground-truth `T` and `h`;
- synthetic shadow mask estimated from clean vs shadow photo;
- held-out one clean/shadow pair per recipe.

Model:

- tiny U-Net-ish CNN;
- input = photo RGB;
- class-conditioned run adds one-hot class planes;
- output = `T RGB`, `h`, and shadow/source-contamination proxy.

Loss:

- L1 on `T,h`;
- small BCE term on shadow mask;
- tiny smoothness regularizer;
- evaluation uses the **preview-invariance** target from report 008:
  render predicted `T,h` into a controlled warm preview scene.

Hardware:

- local Mac CPU only. Installed Torch wheel did not expose MPS in this venv.
- 700 training steps took under a minute at 384 px / 96 px crops.
- `.pt` weights are ignored; summaries/contact sheets are committed.

## 2. Unconditioned run

Output: `results/glassnet_zero/`

| recipe | n | raw MAE | classical MAE | GlassNet MAE | raw shadow gap | classical shadow gap | GlassNet shadow gap | T MAE | h MAE |
|---|---|---|---|---|---|---|---|---|---|
| cathedral-amber | 1 | 44.2 | 22.9 | 26.2 | 0.9 | 1.3 | 0.5 | 0.149 | 0.335 |
| cathedral-green | 1 | 44.5 | 27.2 | 7.7 | 0.8 | 1.3 | 0.1 | 0.052 | 0.055 |
| dark-opaque | 1 | 18.6 | 42.6 | 80.8 | 1.3 | 1.0 | 1.7 | 0.507 | 0.129 |
| streaky-mix | 1 | 46.0 | 18.2 | 19.3 | 1.5 | 1.7 | 0.4 | 0.146 | 0.098 |
| wispy-white | 1 | 52.8 | 11.6 | 10.3 | 0.9 | 1.3 | 0.6 | 0.076 | 0.145 |

Read:

- It learned a useful de-backgrounding prior on cathedral-green.
- It was competitive on wispy-white.
- It catastrophically over-brightened dark-opaque. That is unsurprising: with no
  class prior and tiny data, the network regressed toward "bright transmissive
  glass."

## 3. Class-conditioned run

Output: `results/glassnet_zero_classcond/`

| recipe | n | raw MAE | classical MAE | GlassNet MAE | raw shadow gap | classical shadow gap | GlassNet shadow gap | T MAE | h MAE |
|---|---|---|---|---|---|---|---|---|---|
| cathedral-amber | 1 | 44.2 | 22.9 | 1.5 | 0.9 | 1.3 | 0.0 | 0.012 | 0.003 |
| cathedral-green | 1 | 44.5 | 27.2 | 1.3 | 0.8 | 1.3 | 0.0 | 0.010 | 0.005 |
| dark-opaque | 1 | 18.6 | 42.6 | 5.7 | 1.3 | 1.0 | 0.0 | 0.023 | 0.004 |
| streaky-mix | 1 | 46.0 | 18.2 | 6.7 | 1.5 | 1.7 | 0.0 | 0.024 | 0.155 |
| wispy-white | 1 | 52.8 | 11.6 | 3.7 | 0.9 | 1.3 | 0.0 | 0.042 | 0.054 |

Read:

- Glass-class prior matters enormously. This mirrors the classical pipeline's
  own dependence on VLM/human class.
- On this split, the network learned to ignore capture shadows/background almost
  completely. Shadow gap rounds to 0.0 for all held-out samples.
- The contact sheet shows the net producing clean controlled previews rather
  than copied source photos.

## 4. Why this is promising

This experiment is closer to the product dream than a pretty RGB enhancement:
the network predicts `T,h` and is judged by rendering those maps into a new
preview. That means the learned track can plug into Vitrai's renderer instead of
becoming a one-off image filter.

The class-conditioned result suggests a path where Vitrai uses:

1. a VLM/human class prior;
2. a learned inverse-renderer trained on synthetic + real glass;
3. the existing classical extractor as a fallback and teacher;
4. preview-invariance as the product metric.

## 5. Why this is not yet proof

The split is too easy:

- held-out samples are different lightings of synthetic materials whose sibling
  lightings are in training;
- there are only 17 valid sample directories;
- class-conditioned channels let the model learn class recipes almost directly;
- synthetic materials are cleaner than real rolled glass;
- no JPEG/phone-camera degradation or real photos are in the neural training loop.

So the honest claim is:

> A tiny neural model can learn cross-lighting material invariance on the current
> synthetic setup and can beat the classical extractor in controlled preview
> score when class-conditioned.

The dishonest claim would be:

> We solved single-photo glass delighting.

We did not.

## 6. Next high-risk moves

1. **Generate real diversity.** Render at least 50-100 material seeds per class,
   not just light variations. Then evaluate held-out material identities.
2. **Train with preview loss.** Current loss is map L1. Add differentiable
   preview-invariance loss directly: render predicted `T,h` over controlled
   backgrounds and optimize that.
3. **Add source-background head.** Predict source background/leakage `B` so
   cathedral-clear has somewhere to put window/lawn/mullion content that is not
   `T`.
4. **Distill classical extractor.** Use classical maps as noisy pseudo-labels on
   real app glass photos, while synthetic data anchors absolute scale.
5. **Class prior robustness.** Compare human class, VLM class, and predicted
   class. Class conditioning helps only if the class is right.
6. **Cloud/GPU threshold.** Do not ask for cloud yet. Ask after the held-out
   material split exists; then we can estimate a real training budget.

## 7. Files

- `docs/CODEX_RESEARCH_PERSONA.md` — high-risk neural inverse-rendering persona.
- `train_glassnet_zero.py` — tiny neural baseline/training harness.
- `results/glassnet_zero/summary_table.md` — unconditioned run.
- `results/glassnet_zero/contact_holdout.jpg` — unconditioned visual.
- `results/glassnet_zero_classcond/summary_table.md` — class-conditioned run.
- `results/glassnet_zero_classcond/contact_holdout.jpg` — class-conditioned visual.
