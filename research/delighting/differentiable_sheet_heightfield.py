#!/usr/bin/env python3
"""Height-field displacement inverse-rendering experiment.

Report 023 showed that known sheet/background motion reduces high-frequency
background leakage in the recovered material, but still leaves T globally wrong.
That experiment used a free two-channel optical flow for refraction even though
the synthetic truth is generated from a scalar relief/height field.

This script asks whether the representation itself is part of the problem:

  free optical flow D(x)         vs.       D(x) = scale * grad(height(x))

Both methods see the same two shifted observations, share one unknown background,
and optimize T/B/D end-to-end. If the height-field version helps, the renderer
track should move toward relief-first material states rather than arbitrary flow.
"""
import argparse
import json
import os
import time

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw

import differentiable_sheet_inverse as inv
import differentiable_sheet_motion as motion

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "results", "differentiable_sheet_heightfield_sweep")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def height_to_disp(height, max_scale, scale_param=None):
    """Convert signed height to a normalized gradient displacement field.

    The synthetic truth scales the height gradient to a target displacement
    percentile. We cannot use a differentiable percentile cheaply here, so this
    optimizer learns a global gradient scale and RMS-normalizes the gradient.
    """
    gx = F.pad((height[..., 2:] - height[..., :-2]) * 0.5, (1, 1, 0, 0), mode="replicate")
    gy = F.pad((height[..., 2:, :] - height[..., :-2, :]) * 0.5, (0, 0, 1, 1), mode="replicate")
    grad = torch.cat([gx, gy], dim=1)
    rms = torch.sqrt(grad.pow(2).mean(dim=(1, 2, 3), keepdim=True) + 1e-5)
    unit = grad / rms
    if scale_param is None:
        scale = max_scale
    else:
        scale = max_scale * torch.sigmoid(scale_param).view(1, 1, 1, 1)
    return scale * unit


def height_to_disp_np(height, scale=1.0):
    gx = np.pad((height[:, 2:] - height[:, :-2]) * 0.5, ((0, 0), (1, 1)), mode="edge")
    gy = np.pad((height[2:, :] - height[:-2, :]) * 0.5, ((1, 1), (0, 0)), mode="edge")
    grad = np.stack([gx, gy], axis=-1).astype(np.float32)
    rms = np.sqrt(float(np.mean(grad * grad)) + 1e-5)
    return scale * grad / max(rms, 1e-6)


def scalar_logit(x):
    x = float(np.clip(x, 1e-4, 1.0 - 1e-4))
    return float(np.log(x / (1.0 - x)))


def best_height_scale(height, disp, max_scale):
    unit = height_to_disp_np(height, 1.0)
    denom = float(np.sum(unit * unit))
    if denom < 1e-8:
        return max_scale * 0.5
    scale = float(np.sum(unit * disp) / denom)
    return float(np.clip(scale, max_scale * 0.03, max_scale * 0.97))


def optimize_motion_heightfield(obs_list, shifts, args, device, height_init=None, scale_init=None):
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

    torch.manual_seed(args.seed + 1009)
    t_param = torch.nn.Parameter(torch.from_numpy(t0).permute(2, 0, 1)[None].to(device))
    b_param = torch.nn.Parameter(torch.from_numpy(b0).permute(2, 0, 1)[None].to(device))
    if height_init is None:
        h0 = 0.02 * torch.randn((1, 1, args.height_low_res, args.height_low_res), device=device)
    else:
        h_low = cv2.resize(
            np.clip(height_init, -0.95, 0.95).astype(np.float32),
            (args.height_low_res, args.height_low_res),
            interpolation=cv2.INTER_AREA,
        )
        h0 = torch.from_numpy(np.arctanh(h_low).astype(np.float32))[None, None].to(device)
    h_param = torch.nn.Parameter(h0)
    scale_logit = args.height_scale_logit
    if scale_init is not None:
        scale_logit = scalar_logit(scale_init / max(args.height_scale_max, 1e-6))
    scale_param = torch.nn.Parameter(torch.tensor([scale_logit], device=device))
    opt = torch.optim.AdamW([
        {"params": [t_param], "lr": args.lr_t},
        {"params": [b_param], "lr": args.lr_b},
        {"params": [h_param], "lr": args.lr_h},
        {"params": [scale_param], "lr": args.lr_scale},
    ], weight_decay=0.0)

    log = []
    for step in range(args.steps_height):
        T = torch.sigmoid(inv.upsample_param(t_param, n))
        B = torch.sigmoid(inv.upsample_param(b_param, n))
        height = torch.tanh(inv.upsample_param(h_param, n))
        disp = height_to_disp(height, args.height_scale_max, scale_param)
        recon_losses = [
            torch.abs(inv.render(T, B, disp + sh, args.ambient, args.leak) - obs).mean()
            for sh, obs in zip(shift_t, obs_t)
        ]
        loss_recon = sum(recon_losses) / len(recon_losses)
        loss = (
            loss_recon
            + args.t_tv * inv.tv(T)
            + args.b_tv * inv.tv(B)
            + args.height_tv * inv.tv(height)
            + args.height_lap * inv.lap(height).abs().mean()
            + args.disp_tv * inv.tv(disp / args.max_disp)
            + args.disp_mag * (disp / args.max_disp).pow(2).mean()
        )
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_([t_param, b_param, h_param, scale_param], 5.0)
        opt.step()
        if step % args.log_every == 0 or step == args.steps_height - 1:
            log.append({
                "step": step,
                "loss": float(loss.item()),
                "recon": float(loss_recon.item()),
                "disp_abs": float(disp.abs().mean().item()),
                "height_scale": float((args.height_scale_max * torch.sigmoid(scale_param)).item()),
            })

    with torch.no_grad():
        T = torch.sigmoid(inv.upsample_param(t_param, n))
        B = torch.sigmoid(inv.upsample_param(b_param, n))
        height = torch.tanh(inv.upsample_param(h_param, n))
        disp = height_to_disp(height, args.height_scale_max, scale_param)
    return {
        "T": inv.torch_to_np_img(T),
        "B": inv.torch_to_np_img(B),
        "disp": disp.detach().cpu().numpy()[0].transpose(1, 2, 0).astype(np.float32),
        "height": height.detach().cpu().numpy()[0, 0].astype(np.float32),
        "height_scale": float((args.height_scale_max * torch.sigmoid(scale_param)).item()),
        "log": log,
    }


def add_height_metrics(metrics, rec, gt):
    row = dict(metrics)
    if "height" in rec:
        row["height_corr"] = inv.corr(rec["height"], gt["height"])
        row["height_abs_corr"] = abs(row["height_corr"])
        row["height_lap_std"] = float(np.std(cv2.Laplacian(rec["height"].astype(np.float32), cv2.CV_32F)))
        row["height_scale"] = float(rec.get("height_scale", 0.0))
    else:
        row["height_corr"] = 0.0
        row["height_abs_corr"] = 0.0
        row["height_lap_std"] = 0.0
        row["height_scale"] = 0.0
    return row


def tile(rgb, label, w=170):
    srgb = inv.lin_to_srgb(np.clip(rgb, 0, 1))
    img = (srgb * 255).astype(np.uint8)
    h0, w0 = img.shape[:2]
    img = cv2.resize(img, (w, max(1, int(round(h0 * w / max(w0, 1))))), interpolation=cv2.INTER_AREA)
    hdr = Image.new("RGB", (img.shape[1], 24), (0, 0, 0))
    d = ImageDraw.Draw(hdr)
    d.text((5, 6), label[:30], fill=(255, 230, 90))
    return np.concatenate([np.asarray(hdr), img], axis=0)


def heat_tile(a, label, w=170):
    a = np.asarray(a, np.float32)
    lo, hi = np.percentile(a, [2, 98])
    norm = np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)
    img = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h0, w0 = img.shape[:2]
    img = cv2.resize(img, (w, max(1, int(round(h0 * w / max(w0, 1))))), interpolation=cv2.INTER_AREA)
    hdr = Image.new("RGB", (img.shape[1], 24), (0, 0, 0))
    d = ImageDraw.Draw(hdr)
    d.text((5, 6), label[:30], fill=(255, 230, 90))
    return np.concatenate([np.asarray(hdr), img], axis=0)


def save_contact(out_dir, gt, methods):
    rows = []
    first = [
        tile(gt["T"], "GT clean T"),
        tile(gt["B"], "GT shared B"),
        tile(gt["obs"][0], "obs shift 0"),
        tile(gt["obs"][1], "obs shifted"),
        heat_tile(gt["height"], "GT height"),
        heat_tile(np.linalg.norm(gt["D"], axis=-1), "GT disp"),
    ]
    h = max(t.shape[0] for t in first)
    rows.append(np.concatenate([np.pad(t, ((0, h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in first], 1))

    for label, rec in methods:
        err = np.clip(6.0 * np.abs(rec["T"] - gt["T"]), 0, 1)
        row = [
            tile(rec["T"], f"{label} T"),
            tile(rec["B"], f"{label} B"),
            tile(err, f"{label} |Terr|x6"),
            heat_tile(np.linalg.norm(rec["disp"], axis=-1), f"{label} disp"),
        ]
        if "height" in rec:
            row.append(heat_tile(rec["height"], f"{label} height"))
        h = max(t.shape[0] for t in row)
        rows.append(np.concatenate([np.pad(t, ((0, h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in row], 1))

    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    Image.fromarray(np.concatenate(rows, 0)).save(os.path.join(out_dir, "contact.jpg"), quality=92)


def write_summary(out_dir, metrics):
    lines = [
        "# Height-field displacement inverse summary",
        "",
        "| method | recon MAE | T MAE | B MAE | preview lum CV | T-bg corr | disp EPE | height corr | height scale |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in metrics:
        lines.append(
            f"| {m['name']} | {m['renderer_recon_mae']:.4f} | {m['T_mae']:.4f} | "
            f"{m['B_mae']:.4f} | {m['preview_lum_cv']:.3f} | "
            f"{m['T_highfreq_corr_with_bg']:.3f} | {m['disp_epe_px']:.2f} | "
            f"{m['height_corr']:.3f} | {m['height_scale']:.2f} |"
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

    t0 = time.time()
    free = motion.optimize_motion(obs, shifts, args, device)
    height = optimize_motion_heightfield(obs, shifts, args, device)
    oracle_scale = best_height_scale(height_gt, D, args.height_scale_max)
    height_oracle = optimize_motion_heightfield(obs, shifts, args, device, height_init=height_gt, scale_init=oracle_scale)
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
    metrics = [
        add_height_metrics(motion.motion_metrics("two-frame free-flow D", free, gt, args), free, gt),
        add_height_metrics(motion.motion_metrics("two-frame height-field D", height, gt, args), height, gt),
        add_height_metrics(motion.motion_metrics("two-frame height-field D oracle init", height_oracle, gt, args), height_oracle, gt),
    ]
    save_contact(out_dir, gt, [
        ("free-flow D", free),
        ("height-field D", height),
        ("height oracle-init D", height_oracle),
    ])
    payload = {
        "case": case_name,
        "claim": "Constrain refraction displacement to a scalar height-field gradient.",
        "config": vars(args) | {"device": device, "elapsed_s": elapsed, "shifts": shifts},
        "metrics": metrics,
        "logs": {"free": free["log"], "height": height["log"], "height_oracle": height_oracle["log"]},
    }
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(payload, f, indent=2)
    write_summary(out_dir, metrics)
    print(f"==== HEIGHT-FIELD INVERSE: {case_name} ====")
    for m in metrics:
        print(
            f"{m['name']:28s} recon={m['renderer_recon_mae']:.4f} T={m['T_mae']:.4f} "
            f"B={m['B_mae']:.4f} corr={m['T_highfreq_corr_with_bg']:.3f} "
            f"dispEPE={m['disp_epe_px']:.2f} hCorr={m['height_corr']:.3f}"
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
        "# Height-field displacement inverse sweep",
        "",
        "| method | T MAE mean | T MAE std | B MAE mean | preview CV mean | T-bg corr mean | disp EPE mean | height corr mean | scale mean | n |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, rows in sorted(by_method.items()):
        t_mu, t_sd = mean_std(rows, "T_mae")
        b_mu, _ = mean_std(rows, "B_mae")
        cv_mu, _ = mean_std(rows, "preview_lum_cv")
        corr_mu, _ = mean_std(rows, "T_highfreq_corr_with_bg")
        epe_mu, _ = mean_std(rows, "disp_epe_px")
        hc_mu, _ = mean_std(rows, "height_corr")
        sc_mu, _ = mean_std(rows, "height_scale")
        summary[method] = {
            "T_mae_mean": t_mu,
            "T_mae_std": t_sd,
            "B_mae_mean": b_mu,
            "preview_lum_cv_mean": cv_mu,
            "T_highfreq_corr_with_bg_mean": corr_mu,
            "disp_epe_px_mean": epe_mu,
            "height_corr_mean": hc_mu,
            "height_scale_mean": sc_mu,
            "n": len(rows),
        }
        lines.append(
            f"| {method} | {t_mu:.4f} | {t_sd:.4f} | {b_mu:.4f} | {cv_mu:.3f} | "
            f"{corr_mu:.3f} | {epe_mu:.2f} | {hc_mu:.3f} | {sc_mu:.2f} | {len(rows)} |"
        )
    with open(os.path.join(out_dir, "sweep_summary.md"), "w") as f:
        f.write("\n".join(lines))
    with open(os.path.join(out_dir, "sweep_metrics.json"), "w") as f:
        json.dump({"cases": cases, "summary": summary}, f, indent=2)
    return summary


def parse_seeds(text):
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--size", type=int, default=144)
    ap.add_argument("--seed", type=int, default=51)
    ap.add_argument("--ambient", type=float, default=0.12)
    ap.add_argument("--leak", type=float, default=0.88)
    ap.add_argument("--max-disp", type=float, default=10.0)
    ap.add_argument("--shift-x", type=float, default=19.0)
    ap.add_argument("--shift-y", type=float, default=-11.0)
    ap.add_argument("--t-low-res", type=int, default=26)
    ap.add_argument("--disp-low-res", type=int, default=54)
    ap.add_argument("--b-low-res", type=int, default=72)
    ap.add_argument("--height-low-res", type=int, default=54)
    ap.add_argument("--steps-motion", type=int, default=1200)
    ap.add_argument("--steps-height", type=int, default=1400)
    ap.add_argument("--lr-t", type=float, default=0.08)
    ap.add_argument("--lr-d", type=float, default=0.05)
    ap.add_argument("--lr-b", type=float, default=0.035)
    ap.add_argument("--lr-h", type=float, default=0.055)
    ap.add_argument("--lr-scale", type=float, default=0.020)
    ap.add_argument("--t-tv", type=float, default=0.010)
    ap.add_argument("--b-tv", type=float, default=0.0015)
    ap.add_argument("--disp-tv", type=float, default=0.004)
    ap.add_argument("--disp-lap", type=float, default=0.004)
    ap.add_argument("--disp-mag", type=float, default=0.001)
    ap.add_argument("--height-tv", type=float, default=0.010)
    ap.add_argument("--height-lap", type=float, default=0.018)
    ap.add_argument("--height-scale-max", type=float, default=18.0)
    ap.add_argument("--height-scale-logit", type=float, default=0.0)
    ap.add_argument("--log-every", type=int, default=450)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--sweep-seeds", default="51,52,53,54")
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
    print("==== HEIGHT-FIELD SWEEP SUMMARY ====")
    for method, row in summary.items():
        print(
            f"{method}: T={row['T_mae_mean']:.4f} B={row['B_mae_mean']:.4f} "
            f"corr={row['T_highfreq_corr_with_bg_mean']:.3f} hCorr={row['height_corr_mean']:.3f}"
        )
    print("wrote", args.out)


if __name__ == "__main__":
    main()
