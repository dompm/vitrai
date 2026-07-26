# 055 — The train-once pilot: one deployment-data fine-tune, judged zero-shot

Date: 2026-07-26. Branch `research/delighting-055-train-once` (off the PR #139 / 053b head
`68bd49f`). Executes the external dataset review's prescribed next step.

The reviewer (`docs/external/053-dataset-capture-review.md`) ended with a specific
instruction and a specific gate:

> Do not render 20k yet. Make a roughly 1k-image "deployment pilot" [...] **Train once, then
> evaluate zero-shot on untouched cropped phone photos and the real cross-capture pairs.
> Only scale if it improves registered consistency without flattening texture and its
> confidence reliably identifies clear-glass failures.**

Report 053/053b built the pilot. This report trains on it once and scores those three
clauses. It ends with an explicit SCALE / DO-NOT-SCALE-YET recommendation.

---

## 1. What was actually trained (and the two honest deviations)

| | |
|---|---|
| backbone | `prs-eth/marigold-iid-appearance-v1-1`, frozen; LoRA r=8 on attention + trainable 8-channel AuxHead |
| trainable params | **1,727.4 k** (of ~950 M) |
| optimiser | AdamW lr 1e-4, wd 1e-4, cosine to 0, grad-clip 2.0 |
| steps / batch / crop | **18 000 / bs 1 / 512²** |
| diet | two-view: cropped sheet (`crop_view=True`) + native-res detail patches (`patch_prob=0.2`) |
| augmentation | full phone-ISP presets, loader-side, train presets only (`wide_edge` held out) |
| device | Apple M4, MPS, fp32, `caffeinate -i`, detached |

### Deviation 1 — batch size 1, not 2 (a memory finding worth recording)

This M4 has **16 GB unified memory**, and that, not step count, is the binding constraint.
Compute cost measured directly (forward+backward on random tensors, no data loading):

| config | s/step (`need_T=False`) | peak torch alloc |
|---|---|---|
| bs1 crop256 | 1.1–1.6 | 3.70 G |
| bs2 crop256 | 1.4–2.6 | 3.70 G |
| bs1 crop384 | 2.2–2.4 | 3.69 G |
| **bs1 crop512** | **4.2–5.9** | **3.63 G** |
| bs2 crop512 | first `need_T=True` step: **490 s** | thrashed |

`bs2 @ 512` is not viable here: the VAE **decode's own** activations blow the budget and the
machine swaps — precisely the failure mode report 040's `need_T` gating was introduced to
avoid. Crop 512 was kept (the reviewer explicitly wants whole-sheet context; 512 of the 768
work grid is ⅔ of the sheet) and the batch dropped to 1 instead.

A second measurement worth keeping: **the data loader is not the bottleneck** — 0.21 s per
cold sample (pilot), 0.35 s (old-style), 0.03–0.05 s warm through the LRU-64 cache. An early
probe that appeared to show ~260 s/step was a *concurrent 20 GB rclone restore* driving swap
to 13.6 G of 14.3 G. Nothing large may copy while this trains; that is a 50× penalty.

### Deviation 2 — the second data root is only partially restored

`render_pilot_v1` was to be restored from Drive for volume. The copy sustained only
~2 GB/h (and threw transient 401s mid-copy), so finishing it meant a ~7 h stall before
training could begin. Judgement call: launched on what had landed — **110 of ~476 sample
dirs (6.1 G of 20 G)** — rather than spend a day of schedule on off-domain data.

### Domain mix as trained

| root | train | test | carries |
|---|---|---|---|
| `pilot_053_out` (deployment, 053b) | **84** | 264 | `crop_sim` geometry, detail patches, `gt_sigma_s` |
| `render_pilot_v1` (pre-043, partial) | **51** | 59 | — none of the three |
| **combined** | **135** | **323** | |

**Read the σ_s curve against this**: `render_pilot_v1` predates report 043, so it carries no
`gt_sigma_s` at all. Only **84 of 135 (62 %)** of training samples supervise σ_s, and the
crop-geometry and detail-patch halves of the reviewer's two-view diet come *only* from the
84 pilot samples. The 51 old-style samples add identity volume for T/h/B/shadow/mark and
nothing else.

Holdout is unchanged and multi-axis (EVAL_PROTOCOL §3b-ext): 323 of 458 samples are test by
seed (91), reserved recipe family (67), reserved HDRI (111) or reserved capture geometry
(54), plus the loader-side `wide_edge` device preset that training never draws.

### A wiring bug found before launch

`train_loop` had only half-wired the 053b two-view diet: `patch_prob` defaulted **on** but
`crop_view` defaulted **off**, so the "sheet" half of the diet was the *full uncropped
render* — not the simulated user crop the entire 053 pilot exists to model. Fixed and
defaulted to `True` (commit `03acc90`); `eval_foundation` got the matching switch so the
held-out set is scored in the same geometry it was trained in.

---

## 2. Preflight — gradient flow, per head

Run standalone before launch (and again unconditionally inside `train_loop`). Every head's
loss must reach at least one trainable parameter; the report-040 bug class is a *frozen
submodule's forward pass severing an upstream trainable path*, invisible to a plain
forward+backward smoke test.

| head | tiny backbone | **marigold-iid (as trained)** |
|---|---|---|
| T | 0.600367 | **78.4448** |
| h | 26.156 | 29.4304 |
| σ_s | 28.1534 | 43.0074 |
| B | 32.6868 | 42.6575 |
| shadow | 47.8571 | 85.653 |
| mark | 115.178 | 276.537 |
| conf | 109.649 | 103.051 |

**PASS — all 7 heads on both backbones.** Raw output: `results/055/grad_preflight.txt`.

---

## 3. Training curves

TBD — filled from `results/055/train/train_log.jsonl` + `results/055/curves.png`.

---

## 4. Held-out synthetic evaluation

TBD — per-preset table vs the frozen baseline ladder.

---

## 5. Zero-shot on real photos

TBD — the CTO's 15 untouched Pixel captures, model beside the classical extractor.

---

## 6. Real cross-capture consistency

TBD — 164 registrable pairs / 79 products.

---

## 7. The three-clause scale criterion

TBD.

---

## 8. Recommendation

TBD.
