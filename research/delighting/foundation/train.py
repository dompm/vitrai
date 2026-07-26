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


def _write_resume(out_dir, step, steps, argv, roots, backbone, crop, bs, lr):
    """Breadcrumb next to the adapter (lab rule): a session boundary must never cost more
    than the steps since the last checkpoint. Rewritten at every save."""
    txt = f"""# RESUME — 055 train-once pilot

Last checkpoint: **step {step} / {steps}** (written {time.strftime('%Y-%m-%d %H:%M:%S')}).

- adapter:     `{os.path.join(out_dir, 'adapter.pt')}`
- train state: `{os.path.join(out_dir, 'train_state.pt')}` (optimizer + scheduler + step)
- loss log:    `{os.path.join(out_dir, 'train_log.jsonl')}` (one JSON object per logged step)

Config: backbone={backbone} crop={crop} bs={bs} lr={lr}
Data roots:
{chr(10).join('  - ' + r for r in roots)}

## Resume the run

```
caffeinate -i {argv} --resume
```

`--resume` reloads adapter + optimizer + scheduler from `train_state.pt` and continues at
the saved step; the JSONL log is appended, not truncated.
"""
    with open(os.path.join(out_dir, "RESUME.md"), "w") as f:
        f.write(txt)


def train_loop(data_roots, out_dir, backbone="tiny", steps=150, bs=2, crop=256,
               lr=1e-3, lora_rank=8, device=None, fp32=True, cache_only=False,
               log_every=10, save_every=None, weights=None,
               crop_view=True, patch_prob=0.2, resume=False, argv="", snapshot_every=None,
               mirror_dir=None):
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

    # 055: the two-view deployment diet is now explicit. `crop_view=True` serves the
    # user-CROPPED sheet (lazy homography warp, 053b) — without it the "sheet" view is the
    # full uncropped render, i.e. NOT the deployment geometry the 053 pilot was built to
    # simulate; `patch_prob` mixes in native-res detail patches. Old-style roots carry no
    # crop_sim meta and load unwarped, so a mixed-domain root list is safe.
    ds = GlassDelightDataset(data_roots, split="train", crop=crop, augment=True,
                             crop_view=crop_view, patch_prob=patch_prob)
    print(f"[train] {len(ds)} TRAIN identities-crops source | backbone={backbone} device={device}")
    print(f"[train] crop_view={crop_view} patch_prob={patch_prob} crop={crop} bs={bs}")
    print(f"[train] recipes: {sorted({s['recipe'] for s in ds.samples})}")
    per_root = {}
    for s in ds.samples:
        per_root[os.path.dirname(s["dir"].rstrip("/"))] = per_root.get(
            os.path.dirname(s["dir"].rstrip("/")), 0) + 1
    for r, n in sorted(per_root.items()):
        print(f"[train]   domain mix: {n:4d} train samples from {r}")

    model = FoundationDelighter(backbone=backbone, dtype=dtype, freeze_backbone=True,
                                lora_rank=lora_rank, cache_only=cache_only).to(device)
    tp = model.trainable_parameters()
    n_tr = sum(p.numel() for p in tp)
    print(f"[train] trainable params: {n_tr/1e3:.1f}k (LoRA+AuxHead)  backbone frozen | meta={model.meta}")
    opt = torch.optim.AdamW(tp, lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)

    ckpt = os.path.join(out_dir, "adapter.pt")
    state_p = os.path.join(out_dir, "train_state.pt")
    jsonl_p = os.path.join(out_dir, "train_log.jsonl")
    start_step = 0
    if resume and os.path.exists(state_p):
        st = torch.load(state_p, map_location=device, weights_only=False)
        model.load_adapter(ckpt, map_location=device)
        opt.load_state_dict(st["opt"])
        sched.load_state_dict(st["sched"])
        start_step = int(st["step"]) + 1
        print(f"[train] RESUMED from {state_p} at step {start_step}")

    def _save(step):
        """Atomic-ish checkpoint: adapter + optimizer/scheduler state + breadcrumb.
        tmp+rename so a kill mid-write cannot leave a truncated adapter behind."""
        model.save_adapter(ckpt + ".tmp")
        os.replace(ckpt + ".tmp", ckpt)
        torch.save({"opt": opt.state_dict(), "sched": sched.state_dict(), "step": step},
                   state_p + ".tmp")
        os.replace(state_p + ".tmp", state_p)
        # Keep a COARSE ladder of immortal snapshots alongside the rolling adapter: with a
        # small identity pool a long run can overfit, and the rolling checkpoint alone leaves
        # no way to score an earlier point without retraining.
        if snapshot_every and step and step % snapshot_every == 0:
            model.save_adapter(os.path.join(out_dir, f"adapter_step{step:06d}.pt"))
        _write_resume(out_dir, step, steps, argv, list(data_roots), backbone, crop, bs, lr)
        # Durable mirror OUTSIDE the worktree. The 040 adapters were lost to a worktree
        # cleanup race, so the checkpoint is copied to a plain local directory at EVERY save
        # — this is the primary hedge and it survives Drive auth being down. Best-effort:
        # a failed mirror must never take down a 14-hour training run.
        if mirror_dir:
            try:
                os.makedirs(mirror_dir, exist_ok=True)
                import shutil
                for f in ("adapter.pt", "train_state.pt", "train_log.jsonl", "RESUME.md"):
                    src = os.path.join(out_dir, f)
                    if os.path.exists(src):
                        shutil.copyfile(src, os.path.join(mirror_dir, f + ".tmp"))
                        os.replace(os.path.join(mirror_dir, f + ".tmp"),
                                   os.path.join(mirror_dir, f))
            except Exception as e:
                print(f"  [mirror] WARNING copy to {mirror_dir} failed: {e}", flush=True)

    log, t0 = [], time.time()
    model.train()
    for step in range(start_step, steps):
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
            parts["lr"] = float(sched.get_last_lr()[0])
            log.append(parts)
            # append-as-you-go (055): a killed session must still leave the whole curve on
            # disk — the end-of-run train_log.json alone loses everything on an interrupt.
            with open(jsonl_p, "a") as f:
                f.write(json.dumps(parts) + "\n")
            print(f"  step {step:4d}  total={parts['total']:.4f}  "
                  f"T={parts['T']:.4f} h={parts['h']:.4f} ss={parts['sigma_s']:.4f} "
                  f"B={parts['B']:.4f} "
                  f"sh={parts['shadow']:.4f} mk={parts['mark']:.4f} cf={parts['conf']:.4f}  "
                  f"{parts['sec']:.0f}s", flush=True)
        if save_every and step and step % save_every == 0:
            _save(step)
            print(f"  [ckpt] step {step} -> {ckpt}", flush=True)

    _save(steps - 1)
    json.dump(log, open(os.path.join(out_dir, "train_log.json"), "w"), indent=2)
    print(f"[train] saved {ckpt} ({os.path.getsize(ckpt)} bytes) + train_log.json/.jsonl")
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
    ap.add_argument("--log-every", type=int, default=10)
    ap.add_argument("--save-every", type=int, default=None,
                    help="checkpoint (adapter+optimizer+RESUME.md) every N steps")
    ap.add_argument("--no-crop-view", action="store_true",
                    help="serve the FULL uncropped render as the sheet view (pre-053b behaviour)")
    ap.add_argument("--patch-prob", type=float, default=0.2,
                    help="probability a draw is a native-res detail patch (two-view diet)")
    ap.add_argument("--resume", action="store_true",
                    help="continue from <out>/train_state.pt (adapter + optimizer + step)")
    ap.add_argument("--snapshot-every", type=int, default=None,
                    help="also keep an immortal adapter_step<N>.pt at this coarser cadence")
    ap.add_argument("--mirror-dir", default=None,
                    help="mirror every checkpoint to this durable dir OUTSIDE the worktree")
    args = ap.parse_args()
    if args.smoke:
        args.backbone, args.steps, args.crop, args.bs = "tiny", args.steps or 150, 256, 2
    argv = " ".join([sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
    train_loop(args.data, args.out, backbone=args.backbone, steps=args.steps, bs=args.bs,
               crop=args.crop, lr=args.lr, lora_rank=args.lora_rank, device=args.device,
               fp32=not args.fp16, cache_only=args.cache_only,
               log_every=args.log_every, save_every=args.save_every,
               crop_view=not args.no_crop_view, patch_prob=args.patch_prob,
               resume=args.resume, argv=argv, snapshot_every=args.snapshot_every,
               mirror_dir=args.mirror_dir)


if __name__ == "__main__":
    main()
