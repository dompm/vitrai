# Report 010 — Neural cast-shadow removal (hybrid on top of the classical extractor)

Date: 2026-07-09. Code: `neural/` @ this commit (`prepare_data.py`, `model.py`,
`train.py`, `eval_neural.py`, `common.py`). Data: the synthetic with/without-shadow
pairs (snapshot-copied read-only, gitignored). Trained on Apple M4 / MPS.
Deliverables: `neural/results/neural_eval_{test,train}.json`,
`neural/results/neural_contact_test.jpg`, this report. **No PR.**

## 0. TL;DR — GO

The single failure report 008 isolated: a **cast shadow darkens `I` but not `L`,
so `T ≈ I/L` reads the shadow as fake dark transmittance**, and inside the shadow
the classical material-relight loses to a raw pixel copy on cathedral glass.

A small U-Net (234k params) that runs as a **post-process on the classical
extractor** — detect the shadow, lift `T` back to its shadow-free value, blend by
the predicted mask so non-shadow pixels are untouched — fixes exactly this, and it
**generalizes to held-out lighting/seeds (unseen shadows)**:

| inside-shadow preview MAE (sRGB/255), HELD-OUT | raw-copy | classical | **classical + neural** |
|---|---|---|---|
| **cathedral (the target class)** | 71.9 | 56.9 | **14.0** |
| all shadowed samples (n=4) | 68.1 | 48.2 | **20.9** |

Non-shadow regions do **not** degrade (all-valid MAE 23.6 → 23.1). The win
condition — neural `<` uncorrected classical inside shadow on held-out data,
without hurting non-shadow — is met **decisively on cathedral**, the class report
008 flagged. This is a GO for cast-shadow removal as a hybrid stage.

## 1. Setup

- **Problem framing (from RESEARCH_STATE OP-1 + report 008 §3).** Not a full
  inverse renderer — a narrow, well-posed sub-problem with perfect supervision:
  the synthetic generator renders with/without-shadow pairs of the *identical*
  sheet + camera, so the clean render is a pixel-aligned shadow-free target.
- **Model.** `neural/model.py`: compact 3-level U-Net, base=16 (234k params).
  - Input (6ch): the with-shadow photo (linear RGB) + the classical extractor's
    `T` for that photo.
  - Output: a shadow-mask logit + a bounded residual correction to `T`.
  - Inference blends by the predicted mask: `T_final = (1-m)·T_ws + m·T_pred`, so
    where the model sees no shadow the classical `T` passes through **exactly**.
    This is what structurally guarantees "no non-shadow degradation."
- **Supervision.** Mask ← the with/without photo luminance difference (the same
  `detect_shadow` the eval uses). Corrected `T` ← the classical extractor's `T`
  from the **clean** photo (`T_ns`) — i.e. the net's only job is to make the
  shadowed material match the shadow-free material (shadow-invariance), not to fix
  classical's other biases. Loss is L1 in an approx-sRGB space, weighted 13× inside
  the shadow, plus mask BCE (rare-class `pos_weight`). The pair-derived mask is a
  train/eval signal only; **at inference the net sees the single with-shadow photo
  — no leakage.**
- **Split (generalization, not memorization).** Held-out test = 5 samples whose
  **lighting ids are entirely absent from training**, so the test shadow shapes
  are genuinely unseen. Cathedral (green, both seeds 42 & 43) supplies the two
  primary test samples; one each of streaky / wispy / dark-opaque monitor the
  non-cathedral / no-harm side. Train = the other 12 sheets. 512-px working res,
  shadow-weighted random 192-px crops + flips, 2500 steps (~8.5 min on M4/MPS).

## 2. Held-out results (unseen lighting/seeds)

`eval_neural.py --split test`, reusing `eval_preview_invariance`'s controlled-preview
methodology. Preview MAE in sRGB/255. "IN" = inside detected cast shadow; "OUT" =
valid non-shadow pixels.

| sample | shadow % | IN raw | IN classical | **IN neural** | OUT classical | OUT neural |
|---|---|---|---|---|---|---|
| cathedral-green seed42 light7527 | 4.3 | 87.1 | 71.8 | **16.2** | 19.2 | 19.1 |
| cathedral-green seed43 light1262 | 3.1 | 56.6 | 42.0 | **11.8** | 24.1 | 24.1 |
| dark-opaque seed44 light8879 | 2.1 | 45.7 | 64.7 | **41.3** | 43.7 | 42.2 |
| streaky-mix seed45 light7995 | 0.1 | 138.7 | 16.6 | 14.0 | 19.0 | 18.9 |
| wispy-white seed46 light6553 | 6.2 | 83.0 | 14.4 | 14.5 | 12.1 | 11.1 |

Aggregates (samples with a real shadow, >0.5%):

- **Inside shadow: classical 48.2 → neural 20.9** (raw-copy 68.1).
- **Cathedral inside shadow: classical 56.9 → neural 14.0** — a 4× reduction, and
  now *below* the class's own non-shadow error (~21), i.e. the shadow is no longer
  the dominant local error.
- Non-shadow (all valid): **23.6 → 23.1** — no degradation (marginally better).
- Predicted vs GT shadow area is well-calibrated on cathedral (4.7% vs 4.3%,
  2.9% vs 3.1%).

## 3. Not memorization — the same effect appears on train

`--split train` (12 sheets the model *did* see): inside-shadow classical **55.9 →
neural 26.3**; cathedral **73.7 → 28.6**. The improvement is the same order on both
splits — and the held-out cathedral number (14.0) is actually *better* than train
(28.6), because the two held-out cathedral shadows happen to fall on easier regions
(small-n noise). The takeaway is that the correction is a genuine learned operation,
not a memorized per-sheet lookup.

## 4. Honest caveats / diagnosis

- **dark-opaque wins but weakly (64.7 → 41.3).** Two compounding issues, neither
  the shadow model's core job: (a) report 008 already flags dark-opaque's classical
  `T` as too dark on an absolute-scale anchor, so the target `T_ns` is itself off;
  (b) the residual head occasionally adds a faint green tint on near-black glass
  (visible as green speckle in the contact sheet's `neu err` column). Still a net
  win, but dark-opaque should not ship on this alone until its scale anchor is fixed.
- **wispy is a no-op (14.4 → 14.5), as expected.** Report 008 showed milky/hazy
  glass already diffuses the shadow (small shadow gap), so there is little to
  correct; the model correctly leaves it alone. Good — it means the stage is safe
  to run on all classes, not just cathedral.
- **False-positive shadow firing on dark mullions/leads** (streaky/cathedral
  `pred mask` column). It's benign here: the correction target for those pixels is
  the shadow-free classical `T`, which keeps the leads dark, so lifting toward it
  barely moves them (OUT MAE unchanged). But on a real sheet with genuinely dark
  *glass* (not a shadow), this detector could over-lift — the mask learned "darker
  than its surround," which correlates with but is not identical to "shadow."
- **Tiny dataset (12 train / 5 test sheets, one shadow each).** The held-out
  numbers are trustworthy as a go/no-go signal but not as calibrated magnitudes;
  more seeds/lightings would tighten them. This is a PoC, per the brief.
- **Synthetic-only.** Cycles shadows are cleaner-edged than a real hand shadow on
  rolled glass. Correctness is demonstrated; real photos remain the fidelity bar.

## 5. Verdict & next moves

**GO.** Cast-shadow removal is a tractable, high-ROI neural stage that turns report
008's cathedral inside-shadow *loss* into a decisive win (56.9 → 14.0 held-out)
while structurally protecting non-shadow pixels. It is the right shape: a narrow
learned correction bolted onto the working classical extractor, not a replacement.

Next: (1) train the mask on a chroma/structure cue in addition to darkness to kill
the dark-glass false positive; (2) fix dark-opaque's absolute-scale anchor so its
target is trustworthy, then re-measure; (3) shoot a real hand-shadow pair and
confirm the sim-trained model transfers; (4) fold this stage behind the same
class-gate the product uses (run it for cathedral first).

## 6. Files

- `neural/common.py` — config, snapshot paths, the held-out split.
- `neural/prepare_data.py` — snapshot-copy + cache classical maps (with/without
  shadow) + GT + pair-derived shadow mask.
- `neural/model.py` — the compact U-Net + mask-gated blend.
- `neural/train.py` — MPS training on shadow-weighted crops.
- `neural/eval_neural.py` — held-out preview-invariance eval (raw / classical /
  neural), writes the JSON + contact sheet.
- `neural/results/neural_eval_test.json`, `neural_eval_train.json`,
  `neural_contact_test.jpg` (committed; downscaled).
- Gitignored: the `.venv`, the copied `data_snapshot/`, the `cache/`, the `.pt`
  weights.
