# Report 038 — Foundation-model prototype scaffolding (Bet 2)

Date: 2026-07-12. Branch `research/delighting-038` (off `research/delighting`).
Code: `foundation/` (`verify_backbone.py`, `backbone.py`, `dataset.py`, `train.py`,
`eval_foundation.py`, `modal_app.py`), `docs/FOUNDATION_RUNBOOK.md`. No PR, no cloud
spend, no large training — everything below was built and run on the M4 (MPS).

## 0. Goal & TL;DR

Make the first cloud fine-tune of report-027 **Bet 2** (stand on a pretrained latent-
diffusion dense predictor and fine-tune it to emit our OUTPUT_CONTRACT state, rather than
training GlassNet from scratch) a **config change, not a project**. Build + locally
smoke-test the whole loop now, so when the maintainer's Modal account exists and the
iter-037 GT-v3 data lands, launching is one command.

**Done, verified locally:**
- **Backbone verified runnable** (report-028's lesson applied — weights checked before
  building): `prs-eth/marigold-iid-appearance-v1-1` (Apache-2.0) downloads (~4.8 GB),
  loads, and forwards on MPS. Fallback `prs-eth/marigold-depth-v1-0` (Apache-2.0) too.
- **Full loop runs end-to-end on the M4**: data → holdout-enforced crops → LoRA+head
  train → save → eval-through-frozen-instruments → baseline-ladder table + gate.
- **Modal app import-checks with no account** (guarded); the SAME `train_loop` runs
  locally and on `@app.function(gpu="A100-80GB")` — no forked training code.

## 1. Backbone verification (deliverable 1)

Ran `verify_backbone.py --download` on the M4. Results (`results/038_backbone/
verification.json`):

| candidate | model id | license | download | load (MPS) | params | UNet in/out | forward |
|---|---|---|---|---|---|---|---|
| **PRIMARY** | `prs-eth/marigold-iid-appearance-v1-1` | **Apache-2.0** | ~4.8 GB, OK | 14.5 s | VAE 83.7M / UNet **866M** | 12 / 8 | 21.2 s (2-step, 256²) ✓ |
| FALLBACK | `prs-eth/marigold-depth-v1-0` | Apache-2.0 | ~3.0 GB, OK | ✓ | VAE 83.7M / UNet 866M | 8 / 4 | ✓ |

Choice rationale: Marigold-IID is the intrinsic-image-decomposition (albedo + material)
variant — the closest published thing to "emit our `T,h`", and exactly the Marigold-
Intrinsic / RGB↔X line report 027 §Bet 2 names. It is a fine-tuned SD2 (VAE + single
UNet), Apache-2.0, and diffusers-native. Marigold-depth is the smaller, single-modality
fallback (geometry prior; kept because its in=8/out=4 shape is the simplest and it is the
most-proven diffusers pipeline). `backbone.py` handles both via generalised in/out-channel
logic (fill the non-RGB input latents with zeros; read the primary intrinsic from the
first output latent block).

Beyond the pipeline forward, a **full `FoundationDelighter` train step on the REAL
backbone was verified on the M4** (`results/038_backbone/real_backbone_step.json`,
`marigold-depth`, cache-only, no re-download): LoRA injects (1.73 M trainable params =
LoRA + AuxHead on the 866M UNet), and one forward+backward at 256² runs on MPS — load
8.2 s, forward 1.9 s, backward 3.6 s, grads flow to **all 278 trainable tensors**, T out
(1,3,256,256). So the real-backbone code path is proven end-to-end, not just the off-the-
shelf pipeline. The **smoke *training* still uses the `tiny` stand-in** (a few hundred
steps through the 866M UNet on MPS is slow and the whole point is "no large training");
the real backbone is reserved for the A100 run, and the scaffold now proves the identical
code path forwards+backwards on both.

## 2. Architecture (deliverable 3)

`FoundationDelighter` (`backbone.py`), a deterministic single-step reformulation of
Marigold (Garcia et al., "fine-tuning image-conditional diffusion is easier than you
think") so the loop is cheap enough to smoke-test and a full sampling schedule is off the
critical path:

```
photo --(frozen VAE encode)--> z_rgb
[z_rgb ; zeros] --(pretrained UNet + LoRA, fixed t)--> z_T_hat
z_T_hat --(frozen VAE decode)--> T                      (Marigold-faithful primary intrinsic)
[z_rgb ; z_T_hat] --(trainable AuxHead, learned x8 up)--> h, B, shadow, mark, conf
```

- Frozen VAE (Marigold recipe). UNet base weights frozen; a **LoRA adapter**
  (`to_q/k/v/out`) + the **AuxHead** are the only trainable params (110 k on `tiny`;
  order 10⁷ on the real UNet's attention). This is the report-brief's "frozen backbone +
  head only" first run.
- Multi-channel dense prediction (OUTPUT_CONTRACT §1 tier-1): T (VAE-decoded), and
  h/B/shadow/mark/**confidence** off the AuxHead. Confidence is trained to predict its own
  T error (`exp(−err/τ)`, err detached) — the §1d calibration signal.
- The compact artifact saved/pushed is **only** the LoRA+AuxHead (~0.4 MB on `tiny`); the
  frozen backbone is re-fetched by HF id, so a later agent needs the id + the small adapter.

## 3. Data pipeline (deliverable 2)

`dataset.py` reads the generator's sample dirs (`{recipe}__seed{N}__light{M}/`,
verified against `render_022` / `render_023_holdout` on disk) and yields augmented 512²
crops of the photo + OUTPUT_CONTRACT tier-1 GT channels.

- **Identity-holdout enforced in-loader (EVAL_PROTOCOL §3b).** `seed_is_test(seed) =
  (seed%5==0) or (seed in 800..812)`; in `split="train"` a test identity is NEVER
  returned. Verified: `render_022` → **20 train / 5 test** (seeds 700/705/710 held out);
  `render_023_holdout` → **25 test / 0 train** (the reserved 800-812 batch is never
  trainable). A `seed%5==0` render cannot leak into training by this construction.
- **Channels/units** match the frozen instruments: T = raw `gt_T.exr` (rendered units, the
  space every instrument scores — `eval_synthetic` does not `srgb_to_lin` it); h =
  `srgb_to_lin(gt_h)` (report 025 authored-linear); `gt_B`/`gt_veil` read **when present**
  (GT-v3; the multilayer `gt_veil` via a self-contained OpenEXR reader per report 037 §6);
  shadow mask from the with/without-shadow pair diff; mark from `gt_mark_mask`.
- **Loader-side camera augmentations** (consultant brief), applied to the INPUT photo only
  so every intrinsic target stays fixed → directly trains nuisance-invariance: exposure
  jitter (±0.7 stop), signal-dependent sensor noise, tone-map/gamma jitter, JPEG
  recompression (q35-95), plus crop + flips.
- Samples are read once, downsampled to a working grid, and cached in RAM (the 50 MB EXRs
  are the real cost; caching turned a >2 min/first-steps stall into a fast loop).

## 4. Smoke test (deliverable 5)

`train.py --smoke` (backbone `tiny`, {N} steps, 256² crops, bs 2, MPS) on the 20-identity
`render_022` train split, then `eval_foundation.py` on the 5 held-out test identities.

**Loss curve sanity** (`results/038_smoke/train_log.json`, 120 steps): total 3.886 →
2.948 (min 2.50); the mask/scatter/confidence heads decrease monotonically — h 0.382 →
0.105, shadow-BCE 0.767 → 0.321, mark-BCE 0.673 → 0.448, conf 0.498 → 0.299 — while the
VAE-decoded T loss stays noisy across batches (0.20 ± 0.08; a randomly-initialised tiny
VAE decoder is the weak link, expected). The loop optimises and the trained heads learn.

**Baseline-ladder table** (the loop's eval output; `results/038_smoke/eval/
baseline_ladder.md`, 5 held-out-identity test samples, 2 cross-lighting groups). Numbers
are BAD — a randomly-initialised `tiny` backbone, ~120 steps — and that is the point:
**the deliverable is the loop working, not the score.** Frozen rows read from
EVAL_PROTOCOL §5; only the foundation row is computed:

| route | invariance_T ↓ | T-MAE ↓ | h-MAE ↓ | fine retained-energy | Spearman(conf,−err) | ECE |
|---|---|---|---|---|---|---|
| raw copy | 0.0946 | — | — | — | — | — |
| luma quotient α=1 | 0.0815 | — | — | 1.24 | — | — |
| classical (frozen) | 0.0932 | 0.108 | 0.155 | 1.27 | — | — |
| flatten control (8σ) | — | — | — | 0.03 | — | — |
| **foundation (tiny, smoke)** | **0.0576** | 0.194 | 0.220 | **29.25** | −0.244 | 0.308 |

**Continuation gate: NO-GO (correct).** The tiny model's `invariance_T` (0.0576) nominally
"beats" classical and quotient — but that is a **degenerate artifact**, and the multi-
family gate catches exactly what the single primary number would have hidden: fine
retained-energy is **29.25** (vs a healthy ~1.2-1.3), tripping the **texture-hallucination
flag** (added this iteration as the symmetric upper bound to the flatten floor — report
012's "invented vs measured"), and T-MAE (0.194) is worse than classical (0.108) with an
anti-correlated confidence (Spearman −0.24). GO requires beating classical AND quotient on
the primary **with** retained-energy in the healthy band `[0.5, 2.5]` — the smoke model
fails the texture gate, so `GO = False`. This is the protocol working as designed: a
method that games one family is caught by another.

The continuation gate (`GO` iff the model beats classical AND quotient on the primary
`invariance_T` without the sub-floor flatten flag) correctly returns **NO-GO** for the
smoke run — exactly what an untrained tiny model should get. On the real run the same
table + gate decide whether the fine-tune is shippable per class family.

## 5. Modal app (deliverable 3, cloud) + runbook (deliverable 6)

`modal_app.py` wraps the shared `train_loop` as `@app.function(gpu="A100-80GB",
timeout=86400)` with a `vitraux-delight` Volume for data + checkpoints, a scoped HF token
Secret, and an end-of-run adapter push to a private HF repo (the durable artifact).
Critically it **imports on the M4 with no Modal account** — `modal` is behind a guard that
installs a no-op decorator stub, so `python modal_app.py --selfcheck` succeeds and the
deploy path is simply unavailable. Verified: `HAVE_MODAL=False`, import OK, one shared
training implementation.

`docs/FOUNDATION_RUNBOOK.md` is the exact sequence: maintainer's Modal steps (account +
budget cap + token + HF secret — agents never touch payment) → `modal volume put` the
GT-v3 render tree → `modal run --detach foundation/modal_app.py::train` → `modal app
logs <app-id>` monitor → adapter retrieval → `eval_foundation.py` gate.

**Estimated real-run cost** (COMPUTE_OPTIONS §5): one 30k-step LoRA fine-tune ≈ 18-24
A100-hours ≈ **$45-60** on Modal; an experimentation month ≈ **$150-300** (suggested
workspace cap $300). The sleeper cost is data egress — the 20k GT-v3 tree is ~1.2-1.8 TB
(GT_SPEC §2); upload once to the Volume, pull back only the ~0.4-2 MB adapter.

## 6. Honest risks / what is NOT wired

1. **The real backbone is large (866M UNet).** A single real-backbone LoRA train step at
   256² runs on the M4 (verified, §1), but a few-hundred-step run is slow and 512² eval on
   MPS OOMs (the tiny UNet's 64² self-attention already hits the 20 GB ceiling — the smoke
   eval runs at 256²); the real *training* run needs the A100. The local proof is the
   `tiny` full loop + the real-backbone single-step forward/backward — not a multi-step
   real-backbone train on the M4 (deliberately, per "no large training").
2. **`gt_B`/`gt_veil` supervision awaits the GT-v3 data.** The loader reads them when
   present and the B-loss activates per-sample on `has_B`, but `render_022/023` is v2 (no
   `gt_B`), so B/veil were exercised structurally, not learned. Report 037's finding that
   `gt_veil` is non-zero on 100% of existing data (front-surface reflection) means veil
   supervision is likely load-bearing, not optional.
3. **B is decoded by the AuxHead, not the frozen VAE.** Promoting B to a second VAE-decoded
   latent is the higher-fidelity real-run upgrade (a localized `backbone.py` change).
4. **Marigold's OOD risk stands (report 027 §Bet 2 risk).** These priors are trained on
   OPAQUE-scene intrinsics; thin transmissive glass is out of distribution (their
   albedo ≠ our T). The kill-check is the §5 gate on held-out identities — if the fine-tune
   can't beat classical+quotient without flattening, Bet 2 downgrades exactly as the memo
   says. The scaffold makes that test one command; it does not pre-judge it.
5. **No cross-capture consistency loss in training yet** (only in eval). Report 027 Bet 3's
   IC-Light / same-seed T-agreement loss is the highest-value training add once the
   frozen-backbone baseline is measured; the hook is flagged in `train.py`.

## 7. Files / provenance

- `foundation/*.py` — the six scaffold modules (§0). `docs/FOUNDATION_RUNBOOK.md`.
- `results/038_backbone/verification.json` — the real download/load/forward record.
- `results/038_smoke/{train_log.json, adapter.pt*, eval/baseline_ladder.md, eval/eval.json}`
  — the smoke evidence. (*`.pt` is gitignored; the loop regenerates it.)
- Env: torch 2.9.1 / MPS / M4; diffusers 0.39.0, transformers 4.57.6, peft 0.19.1,
  OpenEXR 3.4.13 in `~/Documents/fastbook/.venv`. Marigold weights in the HF cache
  (not committed). iter-037 GT-v3 format read from `origin/research/delighting-037`
  (`GT_SPEC.md` §1e/§6), whose branch was not touched.
