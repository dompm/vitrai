# foundation/ — Bet-2 foundation-model prototype scaffolding (iteration 038)

Turns report 027's **Bet 2** (fine-tune a pretrained latent-diffusion dense predictor —
Marigold / RGB↔X — to emit the OUTPUT_CONTRACT state, instead of training GlassNet from
scratch) into runnable code, so the first cloud fine-tune is a **config change, not a
project**. Everything here was built and smoke-tested on an M4 (MPS) with no cloud spend.

## Files

| file | deliverable | what it is |
|---|---|---|
| `verify_backbone.py` | 1 | downloads + loads the real backbone candidates, forwards on MPS, records model ids/licenses/params → `results/038_backbone/verification.json` |
| `backbone.py` | 3 | `FoundationDelighter`: frozen VAE + LoRA-adapted pretrained UNet (deterministic single-step) + trainable multi-channel `AuxHead`; `--backbone marigold-iid\|marigold-depth\|sd2\|tiny` |
| `dataset.py` | 2 | reads the generator's sample dirs → 512² crops with loader-side camera augmentations; **enforces the EVAL_PROTOCOL §3b identity holdout** (seed%5==0 / 800-812 never in train) |
| `train.py` | 3 | LoRA/adapter fine-tune loop; runs locally (`--smoke`) and is imported by the Modal app |
| `modal_app.py` | 3 | `@app.function(gpu="A100-80GB")` wrapper of the same `train_loop`; Volume + HF-Hub push; **imports without a Modal account** (guarded) |
| `eval_foundation.py` | 4 | runs a trained ckpt through the FROZEN instruments; emits the baseline-ladder table + continuation gate |

Companion docs: `../docs/FOUNDATION_RUNBOOK.md` (the real run), `../reports/038-foundation-scaffold.md`.

## Backbone (verified this iteration)

- **PRIMARY `prs-eth/marigold-iid-appearance-v1-1`** (Apache-2.0) — Marigold-IID
  intrinsic decomposition; downloads + loads + forwards on MPS (VAE 83.7M, UNet 866M,
  in=12/out=8, cross-attn 1024).
- **FALLBACK `prs-eth/marigold-depth-v1-0`** (Apache-2.0, in=8/out=4).
- `tiny` — randomly-initialised small VAE+UNet of the SAME diffusers classes, for the
  no-download local smoke test.

## Quick start (M4, no cloud)

```bash
PY=~/Documents/fastbook/.venv/bin/python           # torch 2.9.1 + MPS + diffusers/peft/OpenEXR
R022=<a worktree>/research/delighting/render_022    # v2 synthetic data (gitignored EXRs)

$PY foundation/verify_backbone.py --dry             # class-import + tiny forward on MPS
$PY foundation/dataset.py $R022                     # print the holdout partition
$PY foundation/train.py --smoke --data $R022 --out results/038_smoke
$PY foundation/eval_foundation.py --ckpt results/038_smoke/adapter.pt --backbone tiny \
     --data $R022 --out results/038_smoke/eval
$PY foundation/modal_app.py --selfcheck             # Modal import-check (no account)
```

Env: install into a torch venv — `pip install "diffusers>=0.39" "transformers>=4.40"
"peft>=0.19" safetensors huggingface_hub OpenEXR` (scipy optional, for the calibration
Spearman). The frozen colour helpers + family-2 texture instrument are imported from the
parent `research/delighting/` package (`extract.py`, `eval_texture_preservation.py`).
