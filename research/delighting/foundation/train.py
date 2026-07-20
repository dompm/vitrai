#!/usr/bin/env python3
"""Iteration 038 / deliverable 3 — TRAIN the Bet-2 FoundationDelighter.

LoRA/adapter fine-tune of a pretrained latent-diffusion dense predictor (backbone.py)
to emit the OUTPUT_CONTRACT tier-1 state: T, haze/scatter h, haze-driven scatter radius
sigma_s (report 048 material-target extension), background layer B, shadow+mark masks,
and a calibrated confidence. Runs BOTH:

  * locally on MPS with a tiny config (`--smoke`) for the end-to-end loop test, and
  * as a Modal A100 app (modal_app.py imports `train_loop` from here).

Identity-holdout is enforced by dataset.py (a `seed%5==0` / 800-812 identity is NEVER
in the train split), so nothing here can leak a test identity — the split is upstream.

Smoke (M4, no cloud, no big download):
  train.py --smoke --data <render_022> --out results/038_smoke
Real first run (Modal, config change only):
  train.py --backbone marigold-iid --data /data/render_037 --steps 30000 --bs 16 \
           --crop 512 --out /ckpt
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dataset import GlassDelightDataset  # noqa: E402
from backbone import FoundationDelighter  # noqa: E402


def _gamma(x, g=2.4):
    return torch.clamp(x, 1e-4, 1.0) ** (1.0 / g)


def collate(dataset, bs, device):
    """Sample `bs` split-legal augmented crops -> batched tensors (B,C,H,W)."""
    recs = []
    while len(recs) < bs:
        c = dataset.sample_crop()
        if c is not None:
            recs.append(c)

    def stack(key):
        a = np.stack([r[key] for r in recs])          # (B,H,W,C)
        return torch.from_numpy(a).permute(0, 3, 1, 2).float().to(device)

    batch = {k: stack(k) for k in ("photo", "T", "h", "sigma_s", "B", "shadow", "mark", "valid")}
    batch["has_B"] = torch.tensor([1.0 if r["has_B"] else 0.0 for r in recs], device=device)
    batch["has_sigma_s"] = torch.tensor([1.0 if r["has_sigma_s"] else 0.0 for r in recs], device=device)
    return batch


def compute_losses(out, batch, w):
    """OUTPUT_CONTRACT-tier-1 supervised losses. `valid` = sheet minus marks; T is
    up-weighted inside cast shadow (the region reports 008/010 flag as the hard case).

    T is supervised in LATENT space (report 040, ported in 053b's pre-flight series): the
    old pixel-space L1 went through decode(), whose `torch.no_grad()` SEVERED T's gradient
    to the LoRA entirely (gate1b: T-only loss bit-for-bit frozen 100+ steps) — and removing
    the no_grad cost ~1GB+ of frozen-VAE decoder activations. MSE against `out["z_T_hat"]`
    (the UNet's own output) is directly on the trainable path with none of that cost — the
    standard latent-diffusion training target anyway. `batch["z_T_gt"]` must be precomputed
    by the caller via `model.encode(batch["T"])` under no_grad (see train_loop). The shadow
    up-weighting survives by adaptive-pooling the pixel (valid, shadow) map to z resolution."""
    assert "z_T_hat" in out, "backbone.forward() must expose z_T_hat (latent T)"
    assert "z_T_gt" in batch, ("caller must set batch['z_T_gt'] = model.encode(batch['T']) "
                               "under no_grad before compute_losses")
    valid = batch["valid"]                              # (B,1,H,W), pixel space
    shadow = batch["shadow"]
    wmap = valid * (1.0 + 8.0 * shadow)                 # emphasise shadow recovery
    with torch.no_grad():
        wmap_lat = F.adaptive_avg_pool2d(wmap, out["z_T_hat"].shape[-2:])
    wmap_lat = wmap_lat.expand_as(out["z_T_hat"])

    # T: MSE in latent space, shadow-weighted (see docstring)
    l_T = (((out["z_T_hat"] - batch["z_T_gt"]) ** 2) * wmap_lat).sum() / wmap_lat.sum().clamp_min(1)
    # h
    l_h = (torch.abs(out["h"] - batch["h"]) * valid).sum() / valid.sum().clamp_min(1)
    # sigma_s (report 048): L1 in authored-linear [0,1], valid-masked, ONLY on renders
    # that carry gt_sigma_s (has_sigma_s gate mirrors has_B) so pre-043 batches whose
    # sigma_s is zero-filled contribute no spurious gradient.
    hasS = batch["has_sigma_s"].view(-1, 1, 1, 1)
    smask = (valid * hasS)
    l_sigma_s = (torch.abs(out["sigma_s"] - batch["sigma_s"]) * smask).sum() / smask.sum().clamp_min(1)
    # B (only where GT-v3 gt_B exists), in log1p space
    hasB = batch["has_B"].view(-1, 1, 1, 1)
    bmask = (valid * hasB).expand_as(out["B"])
    denomB = bmask.sum().clamp_min(1)
    l_B = (torch.abs(torch.log1p(out["B"]) - torch.log1p(batch["B"].clamp_min(0))) * bmask).sum() / denomB
    # shadow / mark: BCE on the logits
    l_sh = (F.binary_cross_entropy_with_logits(out["shadow_logit"], shadow, reduction="none") * valid).sum() / valid.sum().clamp_min(1)
    l_mk = (F.binary_cross_entropy_with_logits(out["mark_logit"], batch["mark"], reduction="none") * valid).sum() / valid.sum().clamp_min(1)
    # confidence: predict its OWN T error (EVAL_PROTOCOL §1d). target = exp(-err/tau),
    # high where the model's T is accurate. err detached so conf can't cheat by hurting T.
    # out["T"] is None on need_T=False steps (report 040: decode() is a metric/visualization
    # convenience, off the training path) — conf simply gets no supervision that step.
    if out["T"] is not None:
        with torch.no_grad():
            err = torch.abs(out["T"].detach() - batch["T"]).mean(1, keepdim=True)  # sRGB-ish
            conf_target = torch.exp(-err / 0.05)
        l_conf = (torch.abs(out["conf"] - conf_target) * valid).sum() / valid.sum().clamp_min(1)
    else:
        l_conf = torch.zeros((), device=out["z_T_hat"].device, dtype=out["z_T_hat"].dtype)

    total = (w["T"] * l_T + w["h"] * l_h + w["sigma_s"] * l_sigma_s + w["B"] * l_B +
             w["shadow"] * l_sh + w["mark"] * l_mk + w["conf"] * l_conf)
    return total, {"T": float(l_T), "h": float(l_h), "sigma_s": float(l_sigma_s),
                   "B": float(l_B), "shadow": float(l_sh), "mark": float(l_mk),
                   "conf": float(l_conf), "total": float(total)}


def train_loop(data_roots, out_dir, backbone="tiny", steps=150, bs=2, crop=256,
               lr=1e-3, lora_rank=8, device=None, fp32=True, cache_only=False,
               log_every=10, save_every=None, weights=None):
    os.makedirs(out_dir, exist_ok=True)
    device = device or ("mps" if torch.backends.mps.is_available()
                        else "cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float32 if fp32 else torch.float16
    # sigma_s weighted like h (2.0): the oracle-045 gate makes it a first-order material
    # channel (report 048), co-equal with h in the material target (T, h, sigma_s).
    weights = weights or {"T": 6.0, "h": 2.0, "sigma_s": 2.0, "B": 2.0,
                          "shadow": 1.0, "mark": 1.0, "conf": 1.0}

    # Report 040 (ported, 053b pre-flight): the gradient-flow preflight runs UNCONDITIONALLY
    # before any training step, local or cloud — a severed head (the decode()-no_grad bug
    # class) fails LOUD in under a minute instead of silently wasting the whole run. Uses the
    # tiny backbone + a synthetic batch, so it costs seconds and needs no data/downloads.
    from test_grad_flow import preflight_or_raise
    preflight_or_raise(backbone="tiny", device=device)

    ds = GlassDelightDataset(data_roots, split="train", crop=crop, augment=True)
    print(f"[train] {len(ds)} TRAIN identities-crops source | backbone={backbone} device={device}")
    print(f"[train] recipes: {sorted({s['recipe'] for s in ds.samples})}")

    model = FoundationDelighter(backbone=backbone, dtype=dtype, freeze_backbone=True,
                                lora_rank=lora_rank, cache_only=cache_only).to(device)
    tp = model.trainable_parameters()
    n_tr = sum(p.numel() for p in tp)
    print(f"[train] trainable params: {n_tr/1e3:.1f}k (LoRA+AuxHead)  backbone frozen | meta={model.meta}")
    opt = torch.optim.AdamW(tp, lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)

    log, t0 = [], time.time()
    model.train()
    for step in range(steps):
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        batch = collate(ds, bs, device)
        with torch.no_grad():
            batch["z_T_gt"] = model.encode(batch["T"].clamp(0, 1))
        # decode() only on steps that log/use pixel-space T (report 040: T trains latent-only;
        # the decode's own forward memory can OOM a big batch by itself).
        need_T = (step % log_every == 0) or (step == steps - 1)
        out = model(batch["photo"].clamp(0, None), need_T=need_T)
        loss, parts = compute_losses(out, batch, weights)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(tp, 2.0)
        opt.step()
        sched.step()
        if step % log_every == 0 or step == steps - 1:
            parts["step"] = step
            parts["sec"] = round(time.time() - t0, 1)
            log.append(parts)
            print(f"  step {step:4d}  total={parts['total']:.4f}  "
                  f"T={parts['T']:.4f} h={parts['h']:.4f} ss={parts['sigma_s']:.4f} "
                  f"B={parts['B']:.4f} "
                  f"sh={parts['shadow']:.4f} mk={parts['mark']:.4f} cf={parts['conf']:.4f}  "
                  f"{parts['sec']:.0f}s")
        if save_every and step and step % save_every == 0:
            model.save_adapter(os.path.join(out_dir, "adapter.pt"))

    ckpt = os.path.join(out_dir, "adapter.pt")
    model.save_adapter(ckpt)
    json.dump(log, open(os.path.join(out_dir, "train_log.json"), "w"), indent=2)
    print(f"[train] saved {ckpt} ({os.path.getsize(ckpt)} bytes) + train_log.json")
    return model, log


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", nargs="+", required=True, help="render root(s)")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "results", "038_smoke"))
    ap.add_argument("--backbone", default="tiny",
                    choices=["tiny", "marigold-iid", "marigold-depth", "sd2"])
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--bs", type=int, default=2)
    ap.add_argument("--crop", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--lora-rank", type=int, default=8)
    ap.add_argument("--device", default=None)
    ap.add_argument("--fp16", action="store_true", help="half precision (cloud GPU)")
    ap.add_argument("--cache-only", action="store_true", help="HF local_files_only (no download)")
    ap.add_argument("--smoke", action="store_true",
                    help="preset: backbone=tiny, 150 steps, 256 crop, bs2 (M4 loop test)")
    args = ap.parse_args()
    if args.smoke:
        args.backbone, args.steps, args.crop, args.bs = "tiny", args.steps or 150, 256, 2
    train_loop(args.data, args.out, backbone=args.backbone, steps=args.steps, bs=args.bs,
               crop=args.crop, lr=args.lr, lora_rank=args.lora_rank, device=args.device,
               fp32=not args.fp16, cache_only=args.cache_only)


if __name__ == "__main__":
    main()
