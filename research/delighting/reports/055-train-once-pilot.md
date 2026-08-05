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

**Completed 17 999 / 18 000 steps in 16.6 h** (59 657 s, 3.31 s/step wall). 721 logged
steps, checkpoints every 250, immortal snapshots every 2 000. Curves:
`results/055/curves.png` (small multiples, one panel per channel — the channels differ by an
order of magnitude and a shared axis would flatten all but one).

Bands are the mean of the first 5 % vs the last 5 % of logged steps:

| channel | first 5 % | last 5 % | change | min |
|---|---|---|---|---|
| **T (latent MSE)** | **0.8142** | **0.1218** | **−85 %** | 0.0229 |
| h | 0.2791 | 0.0319 | −89 % | 0.0008 |
| σ_s (all logged) | 0.1109 | 0.0345 | −69 % | 0.0000 |
| **σ_s (supervised draws only)** | **0.1864** | **0.0494** | **−74 %** | — |
| B | 0.2549 | 0.0923 | −64 % | 0.0000 |
| shadow | 0.4819 | 0.0659 | −86 % | 0.0076 |
| mark | 0.3477 | 0.0136 | −96 % | 0.0004 |
| conf | 0.3432 | 0.1893 | **−45 %** | 0.0377 |
| total | 7.3477 | 1.3172 | −82 % | 0.2386 |

**The 040 regression check passes.** T declines monotonically in trend and all 721 logged
values are distinct — under the severed-gradient bug this curve was bit-for-bit constant.
Quartile means 0.382 → 0.167 → 0.128 → 0.128: most of the learning happens in the first
half, and T is flat (not still falling) over the last quarter.

**The 048 σ_s drift is resolved.** σ_s must be read on *supervised* draws only: with bs 1 and
only 62 % of samples carrying `gt_sigma_s`, the `has_sigma_s` gate makes the loss exactly
0.0000 on the other 37 % of steps, which drags a naive average toward zero at both ends. On
the 455 supervised draws σ_s falls 0.1864 → 0.0494 (−74 %). Quartiles 0.135 → 0.068 → 0.050
→ 0.058 — down decisively, with a slight uptick in the final quarter worth watching but
nothing like the 048 random-init climb.

**conf is the weak head, and structurally so.** It improves least (−45 %) and plateaus by
the second quartile (0.229 → 0.211 → 0.186 → 0.185). The cause is mechanical: `conf` is
supervised against its own decoded-T error, and the decode is `need_T`-gated to logging
steps — so **conf received supervision on ~721 of 18 000 steps (4 %)**, a 25× smaller
training signal than every other head. This is not a tuning accident; it is a coupling
between the logging cadence and the supervision cadence, and §7 shows it has consequences.

### The B non-finite entry — diagnosed

The lead's read described "a transient inf band around steps 500–2000". The log is more
specific: **exactly one** non-finite value in the whole run, `B = inf` at **step 1650**
(and, through the weighted sum, `total` that step). No other channel and no other step is
affected.

Cause, traced to the data: of the 135 training samples, exactly one has non-finite pixels in
its `gt_B.exr` — `baroque-rolling-wave__seed6014__light9026` (from the old-style
`render_pilot_v1` root), with **26 non-finite pixels**, and a maximum *finite* value of
**65 248.0**. That number is the tell: it sits just under 65 504, the largest representable
half-float, so the AOV was written in **fp16 and the brightest background pixels overflowed
to `inf` on write**. It is a render-export precision artifact, not bad math in the loss and
not a masking bug — the mask is applied correctly, but no mask can help when the *ground
truth itself* is infinite inside the valid region.

It did no damage, and the reason is worth recording: the B loss is an L1 on `log1p`, so the
forward value is `|log1p(pred) − log1p(inf)| = inf`, but the derivative of `|·|` needs only
the *sign* of that difference. The gradient reaching the prediction is therefore finite
(`−1 · 1/(1+pred)`), and the infinity never enters the backward path. Confirmed empirically:
the final adapter has **0 non-finite values across all 1 727 432 parameters** (weights
min −0.741, max 1.472, mean 0.0001, std 0.024), and B recovers immediately after the step.
The logged `inf` is a *reporting* artifact of the loss value only.

Follow-up worth doing (not blocking): write GT AOVs as full float32, or clamp `gt_B` on
load. One sample in 135 is harmless; at 20 k scale the same fp16 ceiling would hit far more
samples and each one silently wastes a step.

---

## 4. Held-out synthetic evaluation

TBD — per-preset table vs the frozen baseline ladder.

---

## 5. Zero-shot on real photos — the section to look at

All 15 of the CTO's Pixel captures, none of them ever seen in training and none of them
rendered. Panels: `results/055/real/<name>_panel.jpg` and the stacked
`board_real_zeroshot.jpg`; per-photo numbers in `real_stats.json`. Each row is

`photo crop | model T | model σ_s | model conf | checker relit by model σ_s | classical T | classical h`

so the model sits beside the frozen classical extractor **on the identical crop**. Crops are
the sheet interior only, verified by eye before any model ran (`crop_check.jpg`); the two
photos using the lead's measured corner rects (`231242267`, `231625820`) do include a little
wood and a fingertip at the edges — left visible rather than re-cropped.

**These panels do not support scaling.** Two representative reads:

- `231821794` (cathedral-clear, the CLEAR case): the photo has obvious vertical relief, tonal
  falloff and a blue marker scribble. The model's T is a **flat, featureless cream field** —
  relief gone, scribble gone, tonality gone. Classical T keeps all three. The model's conf
  over that same region is a **uniform mid-grey** — it does not flag the failure anywhere.
- `165038844` (wispy, strongly backlit against a window): dramatic navy/white swirls in the
  photo become a **soft turquoise wash** in the model's T — most of the structure gone *and*
  the hue displaced toward cyan. Classical T is imperfect (blown highlights, blobby fills)
  but plainly retains the swirl structure.

The pattern holds across the set: model T maps are smooth, desaturated, low-frequency fields.

**Do not read global std as a texture measure.** Model-T std over classical-T std is mean
1.24 / median 0.97, and on the two dark-opaque sheets it reaches 2.2–2.7 — but that is the
model *adding low-frequency colour variation* where classical returns a nearly flat map, not
the model preserving fine texture. The band-limited instrument in §6 is the measurement that
actually answers clause 2.

**Confidence carries almost no information on real photos.** Across all 15 captures, mean
conf spans **0.471 – 0.552 — a total spread of 0.080** — with p10 ≈ 0.50 everywhere:

| class | n | mean conf | model/classical T-std |
|---|---|---|---|
| wispy | 6 | 0.539 | 1.03 |
| opalescent | 6 | 0.546 | 1.10 |
| dark-opaque | 2 | 0.507 | 2.46 |
| cathedral-clear | 1 | 0.532 | 0.97 |

Confidence is essentially the constant ≈0.54 regardless of glass class, capture, or how
wrong T is — including on the clear-glass sheet where T failed hardest. That is clause 3
failing on exactly the case the reviewer named, and §3 explains the mechanism: the head was
trained on 4 % of steps.

### Why the flattening is partly structural

Worth stating plainly, because it shapes the fix. Report 040's durable repair moved T's
supervision **into latent space** (MSE against `z_T_hat`). That restored the severed
gradient — the whole reason the run is trustworthy — but the supervised quantity is now a
**64×64 latent** for a 512×512 crop. Pixel-space T is never in the loss at all; it is
produced by the *frozen* VAE decoder at inference. Fine texture that survives neither the 8×
latent downsample nor a frozen general-purpose decoder has nothing in the objective pulling
it back. Some of what these panels show is therefore designed in, not a training failure —
and it will not be fixed by more data, which is the central reason §8 lands where it does.

---

## 6. Real cross-capture consistency

TBD — 164 registrable pairs / 79 products.

---

## 7. The three-clause scale criterion

TBD.

---

## 8. Recommendation

TBD.
