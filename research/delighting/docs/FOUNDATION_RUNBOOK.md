# FOUNDATION_RUNBOOK — the real Bet-2 fine-tune, step by step

Iteration 038. Companion to `reports/038-foundation-scaffold.md`, `COMPUTE_OPTIONS.md`
(Modal patterns + cost), `EVAL_PROTOCOL.md` (the frozen gate), `GT_SPEC.md` (data
channels). This is the exact sequence to turn the scaffold in `foundation/` into the
first cloud fine-tune once (a) the maintainer's Modal account exists and (b) the iter-037
GT-v3 data (`gt_B`/`gt_veil` + the 20k production render) has landed. **The goal of 038
was that this run is a config change, not a project** — every command below already works
against the committed code; only the account and the data are new.

The scaffold verified locally this iteration (M4, MPS, no cloud spend): backbone
downloads + loads, dataset splits with holdout enforcement, train→save→eval loop runs on
a tiny stand-in AND the real Marigold weights load and forward. See report 038.

---

## 0. Preconditions (who does what)

| step | who | why |
|---|---|---|
| Modal account + payment + workspace budget cap | **maintainer only** | agents never touch payment (COMPUTE_OPTIONS §6) |
| `modal token new` on the Mac | **maintainer** | writes `~/.modal.toml`; keep the token out of any prompt |
| `modal secret create huggingface HF_TOKEN=hf_…` | **maintainer** | a **write-scoped, HF-only** token so the adapter can be pushed to a private repo |
| the 20k GT-v3 render exists locally or on a Volume | iter-037 / render fleet | the training data (`--no-tex-dump --exr-codec DWAA --gt-b --gt-aov`, GT_SPEC §3) |
| everything below | **agent**, headless | the config-change run |

## 1. Backbone (already decided + verified — report 038 §1)

- **PRIMARY: `prs-eth/marigold-iid-appearance-v1-1`** (Apache-2.0). Marigold-IID, the
  intrinsic-image-decomposition variant (albedo + material from one RGB) — the closest
  published thing to "emit our T,h" and exactly the RGB↔X / Marigold-Intrinsic line
  report 027 §Bet 2 names. Verified downloadable (~4.8 GB) and loads + forwards on MPS:
  VAE 83.7M, UNet 866M params, in=12/out=8 latents, cross-attn 1024.
- **FALLBACK: `prs-eth/marigold-depth-v1-0`** (Apache-2.0, ~3.0 GB, in=8/out=4). Same
  SD2 VAE+UNet backbone; use if the IID appearance repo is ever unavailable.
- `backbone.py` handles both (`--backbone marigold-iid|marigold-depth`) via generalised
  in/out-channel handling; the frozen VAE decodes the primary intrinsic latent to T and
  a trained AuxHead emits h/B/shadow/mark/conf.

## 2. Data upload (once)

```bash
modal volume create vitraux-delight
# ship the GT-v3 render tree (each sample dir = {recipe}__seed{N}__light{M}/)
modal volume put vitraux-delight  <local>/render_037_20k/  /render_037_20k
# (optional) the real 1,281-swatch corpus for the invariance loss later
modal volume put vitraux-delight  <local>/corpus/          /corpus
```

Holdout is enforced in-loader (`dataset.py`, EVAL_PROTOCOL §3b): any `seed%5==0` or
800-812 identity is silently excluded from the train split, so **it is safe to upload the
entire render tree** — the loader will never train on a reserved identity. Verify the
partition before launch:

```bash
python foundation/dataset.py /render_037_20k   # prints the train/test partition + gt_B availability
```

## 3. Launch (fire-and-forget)

```bash
modal run --detach foundation/modal_app.py::train \
    --backbone marigold-iid --steps 30000 --data-glob "/data/render_037_20k"
# note the returned app-id
```

`--detach` is the COMPUTE_OPTIONS §3 survival primitive: the run outlives this agent
session. `@app.function(gpu="A100-80GB", timeout=86400)` with a `vitraux-delight-ckpt`
Volume; the adapter is saved every `steps//10` and pushed to the private HF repo
`vitraux/delight-foundation-038` at the end (the durable artifact of record).

Config knobs (all defaults in `modal_app.py::train`): `bs=16 crop=512 lr=1e-4
lora_rank=16 fp16`. Only LoRA + AuxHead train (backbone frozen) — the cheapest real first
run; unfreeze the UNet (a code change in `backbone.py`, `freeze_backbone=False`) only if
the frozen-backbone run clears the §5 gate but underfits.

## 4. Monitor (from any later session, even one with no memory of launching)

```bash
modal app logs <app-id>            # streams the same step/loss lines train.py prints
# or the Modal dashboard URL (safe to hand the maintainer to watch passively)
```

## 5. Retrieve + evaluate against the FROZEN gate

```bash
# pull the adapter (either path works; HF is the durable one)
modal volume get vitraux-delight-ckpt run038/adapter.pt ./adapter.pt
#   or: huggingface_hub download vitraux/delight-foundation-038 adapter.pt

python foundation/eval_foundation.py --ckpt ./adapter.pt --backbone marigold-iid \
    --data <local holdout renders> --out results/038_run/eval
```

`eval_foundation.py` runs the checkpoint through the frozen instruments and prints the
EVAL_PROTOCOL baseline-ladder table + the **continuation gate**:

> GO iff the model beats BOTH classical (`invariance_T` 0.0932) AND quotient (0.0815) on
> the PRIMARY cross-capture-consistency criterion over held-out identities, WITHOUT firing
> the sub-floor flattening flag (fine retained-energy must stay well above the 0.03
> flatten-control floor). A model that flattens texture to win consistency is a FAIL, not
> a GO (EVAL_PROTOCOL §1a).

No GO → the fine-tune is not shippable for that class family regardless of GT-MAE; iterate
(more steps / unfreeze UNet / add the Bet-3 IC-Light consistency loss — the hook is noted
in train.py) before spending more GPU.

## 6. Multi-day / resume

The loop saves every `steps//10` to the checkpoint Volume; a 24h Modal timeout or a
preemption is handled by re-launching `::train` (it re-reads the latest `adapter.pt` if
present — wire `weights=` in a resume wrapper) and/or setting `modal.Retries(max_retries=N)`
on the function. Same checkpointing discipline COMPUTE_OPTIONS §5 step 6 describes.

## 7. Estimated cost (from COMPUTE_OPTIONS §5)

| item | GPU-hours | Modal A100-80GB @ $2.50/hr | notes |
|---|---:|---:|---|
| one 30k-step LoRA fine-tune (frozen backbone, bs16, 512²) | ~18–24 | **$45–60** | dominated by the 866M-UNet forward; frozen-backbone keeps activations/optimizer small |
| held-out eval sweep | ~1–2 | $3–5 | cheap; can also go to a RunPod/Vast 4090 |
| a full experimentation month (a few runs + sweeps) | ~100 blended | **$150–300** | the COMPUTE_OPTIONS §5 suggested workspace cap: **$300** |

Data egress is the sleeper cost (GT_SPEC §2): the 20k GT-v3 tree is ~1.2–1.8 TB. Upload
once to the Modal Volume and keep it there; do NOT re-transfer per run. Pull back only the
~0.4–2 MB adapter, never the dataset.

## 8. What is NOT wired yet (honest gaps, report 038 §risks)

- **`gt_B` / `gt_veil` supervision needs the GT-v3 data.** The loader reads them when
  present (verified against the format) and the B-loss activates per-sample on `has_B`;
  the render_022/023 data used for the local smoke test is v2 (no `gt_B`), so B/veil were
  exercised structurally, not learned. The 037 finding that `gt_veil` is non-zero on ALL
  existing data (front-surface reflection) means veil supervision is likely load-bearing,
  not optional.
- **B is currently decoded by the trained AuxHead, not the frozen VAE.** Promoting B to a
  second VAE-decoded latent (a second UNet output block) is the higher-fidelity real-run
  upgrade; it is a `backbone.py` change, localized.
- **The real empty-text conditioning** should be the Marigold cached empty embedding;
  `backbone.py` loads it from the model's text encoder when present and falls back to
  zeros otherwise (documented).
- **No cross-capture consistency loss in training yet** (only in eval). Report 027 Bet 3's
  IC-Light linearity / same-seed T-agreement loss is the highest-value training-signal add
  once the frozen-backbone baseline is measured — the hook is flagged in `train.py`.
