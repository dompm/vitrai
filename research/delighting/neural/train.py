#!/usr/bin/env python3
"""Train the shadow-removal U-Net on cached synthetic pairs (MPS).

Target = the classical extractor's transmittance from the CLEAN photo (T_ns):
the network's only job is to make the with-shadow material match the shadow-free
material, i.e. become shadow-invariant. Shadow mask supervised by the pair diff.

Small data (12 sheets) so we train on shadow-weighted random crops with flips.
The held-out test (unseen lighting) is the honest number -- see eval_neural.py.
"""
import argparse
import json
import os
import time

import numpy as np
import torch
import torch.nn.functional as F

import common
from model import ShadowUNet, blend


def load_cache(names):
    data = []
    for n in names:
        z = np.load(os.path.join(common.CACHE_DIR, n + ".npz"))
        data.append({
            "name": n,
            "lin_ws": z["lin_ws"], "T_ws": z["T_ws"], "T_ns": z["T_ns"],
            "shadow": z["shadow"], "valid": z["valid"],
            "shadow_yx": np.argwhere(z["shadow"]),
        })
    return data


def make_input(lin_ws, T_ws):
    # 6ch: with-shadow linear RGB + classical T
    return np.concatenate([lin_ws, T_ws], axis=-1)


def sample_patch(s, ps, rng):
    H, W = s["shadow"].shape
    if len(s["shadow_yx"]) > 0 and rng.random() < 0.75:
        cy, cx = s["shadow_yx"][rng.integers(len(s["shadow_yx"]))]
        y0 = int(np.clip(cy - rng.integers(0, ps), 0, max(H - ps, 0)))
        x0 = int(np.clip(cx - rng.integers(0, ps), 0, max(W - ps, 0)))
    else:
        y0 = rng.integers(0, max(H - ps, 1))
        x0 = rng.integers(0, max(W - ps, 1))
    sl = (slice(y0, y0 + ps), slice(x0, x0 + ps))
    inp = make_input(s["lin_ws"][sl], s["T_ws"][sl])
    T_ns = s["T_ns"][sl]
    shadow = s["shadow"][sl].astype(np.float32)
    valid = s["valid"][sl].astype(np.float32)
    # random flips
    if rng.random() < 0.5:
        inp, T_ns, shadow, valid = inp[:, ::-1], T_ns[:, ::-1], shadow[:, ::-1], valid[:, ::-1]
    if rng.random() < 0.5:
        inp, T_ns, shadow, valid = inp[::-1], T_ns[::-1], shadow[::-1], valid[::-1]
    return (np.ascontiguousarray(inp), np.ascontiguousarray(T_ns),
            np.ascontiguousarray(shadow), np.ascontiguousarray(valid))


def batch(data, bs, ps, rng, device):
    xs, ts, ss, vs = [], [], [], []
    for _ in range(bs):
        s = data[rng.integers(len(data))]
        inp, T_ns, shadow, valid = sample_patch(s, ps, rng)
        xs.append(inp); ts.append(T_ns); ss.append(shadow); vs.append(valid)
    to = lambda a, c: torch.from_numpy(np.stack(a)).permute(0, 3, 1, 2).float().to(device) if c else \
        torch.from_numpy(np.stack(a))[:, None].float().to(device)
    return to(xs, True), to(ts, True), to(ss, False), to(vs, False)


def gamma(x):
    # epsilon floor: pow(0, 1/2.4) has infinite gradient -> NaN on dark pixels
    return torch.clamp(x, 1e-4, 1.0) ** (1 / 2.4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=2500)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--ps", type=int, default=192)
    ap.add_argument("--lr", type=float, default=1.2e-3)
    ap.add_argument("--lam-t", type=float, default=6.0)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    device = "mps" if torch.backends.mps.is_available() else "cpu"

    names = common.list_samples()
    train_names, test_names = common.split(names)
    print(f"train ({len(train_names)}): {train_names}")
    print(f"test  ({len(test_names)}): {test_names}")
    data = load_cache(train_names)

    net = ShadowUNet(in_ch=6, base=16).to(device)
    n_params = sum(p.numel() for p in net.parameters())
    print(f"model params: {n_params/1e3:.1f}k  device={device}")
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, args.steps)

    # class balance for the mask (shadow is rare)
    pos = np.mean([s["shadow"].sum() for s in data])
    tot = np.mean([s["valid"].sum() for s in data])
    pos_weight = torch.tensor([float(np.clip((tot - pos) / max(pos, 1), 1, 60))], device=device)
    print(f"mask pos_weight={pos_weight.item():.1f}")

    net.train()
    t0 = time.time()
    log = []
    for step in range(args.steps):
        x, T_ns, shadow, valid = batch(data, args.bs, args.ps, rng, device)
        mask_logit, T_pred = net(x)
        mprob = torch.sigmoid(mask_logit)
        T_final = blend(x[:, 3:6], mprob, T_pred)

        # 1) mask supervision (valid pixels only)
        bce = F.binary_cross_entropy_with_logits(mask_logit, shadow, pos_weight=pos_weight, reduction="none")
        l_mask = (bce * valid).sum() / valid.sum().clamp_min(1)

        # 2) blended output should reproduce the shadow-free classical T,
        #    weighted much higher inside the shadow (the region we must fix)
        w = valid * (1.0 + 12.0 * shadow)
        l_final = (torch.abs(gamma(T_final) - gamma(T_ns)) * w).sum() / (3 * w.sum()).clamp_min(1)

        # 3) direct target on the residual head inside shadow (gradient even when
        #    the mask is still uncertain early in training)
        ws = valid * shadow
        l_pred = (torch.abs(gamma(T_pred) - gamma(T_ns)) * ws).sum() / (3 * ws.sum()).clamp_min(1)

        loss = l_mask + args.lam_t * l_final + args.lam_t * 0.5 * l_pred
        opt.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 5.0)
        opt.step(); sched.step()

        if step % 200 == 0 or step == args.steps - 1:
            msg = (f"step {step:5d}  loss={loss.item():.4f}  mask={l_mask.item():.4f}  "
                   f"final={l_final.item():.4f}  pred={l_pred.item():.4f}  "
                   f"{(time.time()-t0):.0f}s")
            print(msg)
            log.append({"step": step, "loss": float(loss.item()),
                        "l_mask": float(l_mask.item()), "l_final": float(l_final.item()),
                        "l_pred": float(l_pred.item())})

    torch.save({"state_dict": net.state_dict(), "in_ch": 6, "base": 16,
                "args": vars(args)}, common.WEIGHTS)
    json.dump(log, open(os.path.join(common.HERE, "train_log.json"), "w"), indent=2)
    print(f"saved {common.WEIGHTS}")


if __name__ == "__main__":
    main()
