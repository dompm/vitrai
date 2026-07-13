#!/usr/bin/env python3
"""Iteration 038 / deliverable 3 — TRAIN the Bet-2 FoundationDelighter.

LoRA/adapter fine-tune of a pretrained latent-diffusion dense predictor (backbone.py)
to emit the OUTPUT_CONTRACT tier-1 state: T, haze/scatter h, background layer B,
shadow+mark masks, and a calibrated confidence. Runs BOTH:

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

    batch = {k: stack(k) for k in ("photo", "T", "h", "B", "shadow", "mark", "valid")}
    batch["has_B"] = torch.tensor([1.0 if r["has_B"] else 0.0 for r in recs], device=device)
    return batch


def compute_losses(out, batch, w):
    """OUTPUT_CONTRACT-tier-1 supervised losses. `valid` = sheet minus marks; T is
    up-weighted inside cast shadow (the region reports 008/010 flag as the hard case).

    T is supervised in LATENT space (report 040): pixel-space L1 against decode(T)
    required backprop through the full frozen-VAE decoder activation graph -- a real
    memory cost (tripped the swap-growth guard at 256^2) for no accuracy benefit, and
    is not how latent-diffusion models are normally trained anyway. MSE against
    `out["z_T_hat"]` (the UNet's own output, before any VAE decode) is directly on the
    trainable path with none of that cost. `batch["z_T_gt"]` must be precomputed by the
    caller via `model.encode(batch["T"]) under torch.no_grad()` -- see train_loop /
    overfit_gate.py's run_gate for the call site. The old shadow-upweighting is kept by
    downsampling the pixel-space (valid, shadow) mask to z_T_hat's spatial resolution
    (adaptive so it's correct regardless of a backbone's VAE downsample factor)."""
    assert "z_T_hat" in out, "backbone.py forward() must expose z_T_hat (latent T)"
    assert "z_T_gt" in batch, ("caller must set batch['z_T_gt'] = model.encode(batch['T']) "
                              "under no_grad before calling compute_losses")
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
    # out["T"] is None on steps where the caller passed need_T=False (report 040: decode()
    # is now a metric/visualization convenience, not on the training path) -- conf just
    # gets no supervision that step rather than forcing an unwanted decode.
    if out["T"] is not None:
        with torch.no_grad():
            err = torch.abs(out["T"].detach() - batch["T"]).mean(1, keepdim=True)  # sRGB-ish
            conf_target = torch.exp(-err / 0.05)
        l_conf = (torch.abs(out["conf"] - conf_target) * valid).sum() / valid.sum().clamp_min(1)
    else:
        l_conf = torch.zeros((), device=out["z_T_hat"].device, dtype=out["z_T_hat"].dtype)

    total = (w["T"] * l_T + w["h"] * l_h + w["B"] * l_B +
             w["shadow"] * l_sh + w["mark"] * l_mk + w["conf"] * l_conf)
    return total, {"T": float(l_T), "h": float(l_h), "B": float(l_B),
                   "shadow": float(l_sh), "mark": float(l_mk), "conf": float(l_conf),
                   "total": float(total)}


def train_loop(data_roots, out_dir, backbone="tiny", steps=150, bs=2, crop=256,
               lr=1e-3, lora_rank=8, device=None, fp32=True, cache_only=False,
               log_every=10, save_every=None, weights=None, check_grads=True):
    os.makedirs(out_dir, exist_ok=True)
    device = device or ("mps" if torch.backends.mps.is_available()
                        else "cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float32 if fp32 else torch.float16
    weights = weights or {"T": 6.0, "h": 2.0, "B": 2.0, "shadow": 1.0, "mark": 1.0, "conf": 1.0}

    if check_grads:
        # report 040: a frozen submodule's forward pass can silently sever gradient to
        # an upstream TRAINABLE path (not just its own weights) without any error and
        # without a plain fwd/bwd smoke test noticing -- cheap enough (~seconds, tiny
        # backbone, backbone-agnostic since the bug lives in shared code) to run before
        # every real launch. Set check_grads=False only for a deliberate re-check of a
        # run already known-good.
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
        # decode() only when this step will actually log/use pixel-space T (report 040:
        # T's training signal is latent-only now; decode() is a metric/visualization
        # convenience that can OOM a larger batch on its own forward-pass memory).
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
                  f"T={parts['T']:.4f} h={parts['h']:.4f} B={parts['B']:.4f} "
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
    ap.add_argument("--no-check-grads", action="store_true",
                    help="skip the report-040 gradient-flow preflight (default: runs it)")
    args = ap.parse_args()
    if args.smoke:
        args.backbone, args.steps, args.crop, args.bs = "tiny", args.steps or 150, 256, 2
    train_loop(args.data, args.out, backbone=args.backbone, steps=args.steps, bs=args.bs,
               crop=args.crop, lr=args.lr, lora_rank=args.lora_rank, device=args.device,
               fp32=not args.fp16, cache_only=args.cache_only,
               check_grads=not args.no_check_grads)


if __name__ == "__main__":
    main()
