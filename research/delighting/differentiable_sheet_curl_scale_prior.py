#!/usr/bin/env python3
"""Curl-regularized inverse rendering with weak material scale/color priors.

Reports 023-026 converged on two remaining ingredients:

  1. motion + curl-regularized displacement reduces background/geometric leakage;
  2. T is still globally ambiguous against B.

This script tests whether a weak prior on mean material transmittance is enough
to break that remaining scale/color ambiguity.
"""
import argparse
import json
import os
import time

import cv2
import numpy as np
import torch
from PIL import Image

import differentiable_sheet_curl_regularized as curl_exp
import differentiable_sheet_heightfield as hf
import differentiable_sheet_inverse as inv
import differentiable_sheet_motion as motion

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "results", "differentiable_sheet_curl_scale_prior_sweep")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def target_for_mode(T_gt, mode):
    rgb = T_gt.mean(axis=(0, 1)).astype(np.float32)
    if mode == "none":
        return None
    if mode == "luma-oracle":
        return np.array([(T_gt * inv.LUM).sum(-1).mean()], dtype=np.float32)
    if mode == "rgb-oracle":
        return rgb
    if mode == "rgb-bright-biased":
        return np.clip(rgb * np.array([1.20, 1.12, 1.16], np.float32), 0.002, 0.95)
    if mode == "rgb-chroma-biased":
        return np.clip(rgb * np.array([1.35, 0.92, 1.20], np.float32), 0.002, 0.95)
    raise ValueError(f"unknown prior mode {mode}")


def prior_loss_for(T, target, mode, device):
    if mode == "none":
        return T.new_tensor(0.0)
    if mode == "luma-oracle":
        lum = torch.tensor(inv.LUM, dtype=T.dtype, device=device).view(1, 3, 1, 1)
        mean_lum = (T * lum).sum(dim=1).mean()
        tgt = torch.tensor(float(target[0]), dtype=T.dtype, device=device)
        return torch.abs(mean_lum - tgt)
    tgt = torch.tensor(target, dtype=T.dtype, device=device).view(1, 3)
    mean_rgb = T.mean(dim=(2, 3))
    return torch.abs(mean_rgb - tgt).mean()


def optimize_curl_prior(obs_list, shifts, args, device, mode, target):
    n = obs_list[0].shape[0]
    obs_t = [inv.np_to_torch_img(obs, device) for obs in obs_list]
    shift_t = [
        torch.from_numpy(motion.shift_field(n, s)).permute(2, 0, 1)[None].float().to(device)
        for s in shifts
    ]

    mean_obs = np.mean(np.stack(obs_list, axis=0), axis=0)
    neutral_B = np.ones_like(mean_obs, dtype=np.float32) * 0.82
    t0 = inv.init_low_T(mean_obs, neutral_B, args.ambient, args.leak, args.t_low_res)
    b0 = inv.init_unknown_B(mean_obs, args.b_low_res)

    t_param = torch.nn.Parameter(torch.from_numpy(t0).permute(2, 0, 1)[None].to(device))
    b_param = torch.nn.Parameter(torch.from_numpy(b0).permute(2, 0, 1)[None].to(device))
    disp_param = torch.nn.Parameter(torch.zeros((1, 2, args.disp_low_res, args.disp_low_res), device=device))
    opt = torch.optim.AdamW([
        {"params": [t_param], "lr": args.lr_t},
        {"params": [b_param], "lr": args.lr_b},
        {"params": [disp_param], "lr": args.lr_d},
    ], weight_decay=0.0)

    log = []
    for step in range(args.steps_motion):
        T = torch.sigmoid(inv.upsample_param(t_param, n))
        B = torch.sigmoid(inv.upsample_param(b_param, n))
        disp = args.max_disp * torch.tanh(inv.upsample_param(disp_param, n, mode="bilinear"))
        recon_losses = [
            torch.abs(inv.render(T, B, disp + sh, args.ambient, args.leak) - obs).mean()
            for sh, obs in zip(shift_t, obs_t)
        ]
        loss_recon = sum(recon_losses) / len(recon_losses)
        curl_loss = curl_exp.curl_torch(disp / args.max_disp).abs().mean()
        prior_loss = prior_loss_for(T, target, mode, device)
        loss = (
            loss_recon
            + args.t_tv * inv.tv(T)
            + args.b_tv * inv.tv(B)
            + args.disp_tv * inv.tv(disp / args.max_disp)
            + args.disp_lap * inv.lap(disp / args.max_disp).abs().mean()
            + args.disp_mag * (disp / args.max_disp).pow(2).mean()
            + args.curl_weight * curl_loss
            + args.prior_weight * prior_loss
        )
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_([t_param, b_param, disp_param], 5.0)
        opt.step()
        if step % args.log_every == 0 or step == args.steps_motion - 1:
            log.append({
                "step": step,
                "loss": float(loss.item()),
                "recon": float(loss_recon.item()),
                "curl": float(curl_loss.item()),
                "prior": float(prior_loss.item()),
                "disp_abs": float(disp.abs().mean().item()),
            })

    T_np = inv.torch_to_np_img(torch.sigmoid(inv.upsample_param(t_param, n)))
    B_np = inv.torch_to_np_img(torch.sigmoid(inv.upsample_param(b_param, n)))
    disp_np = disp.detach().cpu().numpy()[0].transpose(1, 2, 0).astype(np.float32)
    return {"T": T_np, "B": B_np, "disp": disp_np, "prior_mode": mode, "target": None if target is None else target.tolist(), "log": log}


def method_metrics(name, rec, gt, args):
    row = motion.motion_metrics(name, rec, gt, args)
    row["curl_abs"] = curl_exp.curl_abs_np(rec["disp"] / args.max_disp)
    mean_rgb = rec["T"].mean(axis=(0, 1))
    gt_rgb = gt["T"].mean(axis=(0, 1))
    row["mean_rgb_mae"] = float(np.mean(np.abs(mean_rgb - gt_rgb)))
    row["mean_luma_abs"] = float(abs((rec["T"] * inv.LUM).sum(-1).mean() - (gt["T"] * inv.LUM).sum(-1).mean()))
    row["prior_mode"] = rec["prior_mode"]
    return row


def save_contact(out_dir, gt, methods):
    first = [
        hf.tile(gt["T"], "GT clean T"),
        hf.tile(gt["B"], "GT shared B"),
        hf.tile(gt["obs"][0], "obs shift 0"),
        hf.tile(gt["obs"][1], "obs shifted"),
        hf.heat_tile(np.linalg.norm(gt["D"], axis=-1), "GT disp"),
    ]
    rows = []
    row_h = max(t.shape[0] for t in first)
    rows.append(np.concatenate([np.pad(t, ((0, row_h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in first], 1))

    for label, rec in methods:
        err = np.clip(6.0 * np.abs(rec["T"] - gt["T"]), 0, 1)
        row = [
            hf.tile(rec["T"], f"{label} T"),
            hf.tile(rec["B"], f"{label} B"),
            hf.tile(err, f"{label} |Terr|x6"),
            hf.heat_tile(np.linalg.norm(rec["disp"], axis=-1), f"{label} disp"),
        ]
        row_h = max(t.shape[0] for t in row)
        rows.append(np.concatenate([np.pad(t, ((0, row_h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in row], 1))

    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    Image.fromarray(np.concatenate(rows, 0)).save(os.path.join(out_dir, "contact.jpg"), quality=92)


def write_summary(out_dir, metrics):
    lines = [
        "# Curl + material prior inverse summary",
        "",
        "| method | recon MAE | T MAE | B MAE | preview CV | T-bg corr | disp EPE | curl abs | mean RGB MAE | mean luma abs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in metrics:
        lines.append(
            f"| {m['name']} | {m['renderer_recon_mae']:.4f} | {m['T_mae']:.4f} | "
            f"{m['B_mae']:.4f} | {m['preview_lum_cv']:.3f} | {m['T_highfreq_corr_with_bg']:.3f} | "
            f"{m['disp_epe_px']:.2f} | {m['curl_abs']:.5f} | {m['mean_rgb_mae']:.4f} | "
            f"{m['mean_luma_abs']:.4f} |"
        )
    with open(os.path.join(out_dir, "summary_table.md"), "w") as f:
        f.write("\n".join(lines))


def run_case(args, out_dir, case_name="single"):
    ensure_dir(out_dir)
    rng = np.random.default_rng(args.seed)
    rng2 = np.random.default_rng(args.seed + 77)
    device = "mps" if torch.backends.mps.is_available() and not args.cpu else "cpu"

    T = inv.make_material_T(args.size, rng)
    D, height_gt = inv.make_displacement(args.size, rng, amp_px=args.max_disp * 0.92)
    B = inv.make_background(args.size, rng)
    shifts = [(0.0, 0.0), (args.shift_x, args.shift_y)]
    obs, warped = [], []
    for shift, rr in zip(shifts, (rng, rng2)):
        o, w = motion.render_np(T, B, D + motion.shift_field(args.size, shift), args.ambient, args.leak, rr)
        obs.append(o)
        warped.append(w)

    methods = []
    t0 = time.time()
    for mode in parse_modes(args.prior_modes):
        target = target_for_mode(T, mode)
        rec = optimize_curl_prior(obs, shifts, args, device, mode, target)
        methods.append((mode, rec))
    elapsed = time.time() - t0

    gt = {
        "T": T,
        "D": D,
        "height": height_gt,
        "B": B,
        "obs": obs,
        "warped": warped,
        "shifts": shifts,
    }
    metrics = [method_metrics(label, rec, gt, args) for label, rec in methods]
    save_contact(out_dir, gt, methods)
    payload = {
        "case": case_name,
        "claim": "A weak mean material prior may resolve the remaining T/B scale-color ambiguity after curl regularization.",
        "config": vars(args) | {"device": device, "elapsed_s": elapsed, "shifts": shifts},
        "gt_mean_rgb": T.mean(axis=(0, 1)).tolist(),
        "gt_mean_luma": float((T * inv.LUM).sum(-1).mean()),
        "metrics": metrics,
        "logs": {label: rec["log"] for label, rec in methods},
    }
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(payload, f, indent=2)
    write_summary(out_dir, metrics)
    print(f"==== CURL + SCALE PRIOR: {case_name} ====")
    for m in metrics:
        print(
            f"{m['name']:18s} recon={m['renderer_recon_mae']:.4f} T={m['T_mae']:.4f} "
            f"B={m['B_mae']:.4f} meanRGB={m['mean_rgb_mae']:.4f} corr={m['T_highfreq_corr_with_bg']:.3f}"
        )
    print(f"device={device} elapsed={elapsed:.1f}s")
    return payload


def summarize_sweep(out_dir, cases):
    by_method = {}
    for case in cases:
        for m in case["metrics"]:
            by_method.setdefault(m["name"], []).append(m)

    def mean_std(rows, key):
        vals = np.array([r[key] for r in rows], dtype=np.float64)
        return float(vals.mean()), float(vals.std())

    summary = {}
    lines = [
        "# Curl + material prior inverse sweep",
        "",
        "| method | T MAE mean | T MAE std | B MAE mean | recon MAE mean | preview CV mean | T-bg corr mean | disp EPE mean | mean RGB MAE | mean luma abs | n |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    order = {m: i for i, m in enumerate(parse_modes("none,luma-oracle,rgb-oracle,rgb-bright-biased,rgb-chroma-biased"))}
    for method, rows in sorted(by_method.items(), key=lambda kv: order.get(kv[0], 99)):
        t_mu, t_sd = mean_std(rows, "T_mae")
        b_mu, _ = mean_std(rows, "B_mae")
        recon_mu, _ = mean_std(rows, "renderer_recon_mae")
        cv_mu, _ = mean_std(rows, "preview_lum_cv")
        corr_mu, _ = mean_std(rows, "T_highfreq_corr_with_bg")
        epe_mu, _ = mean_std(rows, "disp_epe_px")
        rgb_mu, _ = mean_std(rows, "mean_rgb_mae")
        lum_mu, _ = mean_std(rows, "mean_luma_abs")
        summary[method] = {
            "T_mae_mean": t_mu,
            "T_mae_std": t_sd,
            "B_mae_mean": b_mu,
            "renderer_recon_mae_mean": recon_mu,
            "preview_lum_cv_mean": cv_mu,
            "T_highfreq_corr_with_bg_mean": corr_mu,
            "disp_epe_px_mean": epe_mu,
            "mean_rgb_mae_mean": rgb_mu,
            "mean_luma_abs_mean": lum_mu,
            "n": len(rows),
        }
        lines.append(
            f"| {method} | {t_mu:.4f} | {t_sd:.4f} | {b_mu:.4f} | {recon_mu:.4f} | "
            f"{cv_mu:.3f} | {corr_mu:.3f} | {epe_mu:.2f} | {rgb_mu:.4f} | {lum_mu:.4f} | {len(rows)} |"
        )
    with open(os.path.join(out_dir, "sweep_summary.md"), "w") as f:
        f.write("\n".join(lines))
    with open(os.path.join(out_dir, "sweep_metrics.json"), "w") as f:
        json.dump({"cases": cases, "summary": summary}, f, indent=2)
    return summary


def parse_modes(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def parse_seeds(text):
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--size", type=int, default=144)
    ap.add_argument("--seed", type=int, default=81)
    ap.add_argument("--ambient", type=float, default=0.12)
    ap.add_argument("--leak", type=float, default=0.88)
    ap.add_argument("--max-disp", type=float, default=10.0)
    ap.add_argument("--shift-x", type=float, default=19.0)
    ap.add_argument("--shift-y", type=float, default=-11.0)
    ap.add_argument("--t-low-res", type=int, default=26)
    ap.add_argument("--disp-low-res", type=int, default=54)
    ap.add_argument("--b-low-res", type=int, default=72)
    ap.add_argument("--steps-motion", type=int, default=1200)
    ap.add_argument("--lr-t", type=float, default=0.08)
    ap.add_argument("--lr-d", type=float, default=0.05)
    ap.add_argument("--lr-b", type=float, default=0.035)
    ap.add_argument("--t-tv", type=float, default=0.010)
    ap.add_argument("--b-tv", type=float, default=0.0015)
    ap.add_argument("--disp-tv", type=float, default=0.004)
    ap.add_argument("--disp-lap", type=float, default=0.004)
    ap.add_argument("--disp-mag", type=float, default=0.001)
    ap.add_argument("--curl-weight", type=float, default=0.30)
    ap.add_argument("--prior-weight", type=float, default=0.25)
    ap.add_argument("--prior-modes", default="none,luma-oracle,rgb-oracle,rgb-bright-biased,rgb-chroma-biased")
    ap.add_argument("--log-every", type=int, default=450)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--sweep-seeds", default="81,82,83,84")
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()

    if not args.sweep:
        run_case(args, args.out)
        return

    ensure_dir(args.out)
    cases = []
    for seed in parse_seeds(args.sweep_seeds):
        case_args = argparse.Namespace(**(vars(args) | {"seed": seed}))
        case_name = f"seed{seed}"
        payload = run_case(case_args, os.path.join(args.out, case_name), case_name)
        cases.append({"case": case_name, "seed": seed, "metrics": payload["metrics"], "config": payload["config"]})
    summary = summarize_sweep(args.out, cases)
    print("==== CURL + SCALE PRIOR SWEEP SUMMARY ====")
    for method, row in summary.items():
        print(
            f"{method}: T={row['T_mae_mean']:.4f} B={row['B_mae_mean']:.4f} "
            f"meanRGB={row['mean_rgb_mae_mean']:.4f} corr={row['T_highfreq_corr_with_bg_mean']:.3f}"
        )
    print("wrote", args.out)


if __name__ == "__main__":
    main()
