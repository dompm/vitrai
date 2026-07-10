#!/usr/bin/env python3
"""Free-flow warm start projected into an integrable height field.

Report 024 found that height-field displacement is a good latent state when the
height basin is known, but a bad cold start. This experiment tests the obvious
non-oracle bridge:

  1. fit the two-frame shared-background model with free optical flow D_free;
  2. project D_free onto the closest curl-free / integrable scalar height field;
  3. initialize the height-field optimizer from that projected relief.

If this gets close to the oracle-height control, we have a practical path from
easy optimization to a physical relief representation.
"""
import argparse
import json
import os
import time

import cv2
import numpy as np

import differentiable_sheet_heightfield as hf
import differentiable_sheet_inverse as inv
import differentiable_sheet_motion as motion

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "results", "differentiable_sheet_integrable_projection_sweep")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def project_flow_to_height(disp):
    """Least-squares periodic projection from vector flow to scalar height.

    Solves min_H ||grad(H) - D||^2 in the Fourier domain. The result keeps the
    curl-free part of the free-flow displacement and discards non-integrable
    components. Absolute height scale is normalized away; refraction scale is
    recovered separately by `best_height_scale`.
    """
    p = disp[..., 0].astype(np.float32)
    q = disp[..., 1].astype(np.float32)
    p = p - float(p.mean())
    q = q - float(q.mean())
    h, w = p.shape
    ky = 2.0 * np.pi * np.fft.fftfreq(h).astype(np.float32)
    kx = 2.0 * np.pi * np.fft.fftfreq(w).astype(np.float32)
    kyy, kxx = np.meshgrid(ky, kx, indexing="ij")
    denom = kxx * kxx + kyy * kyy
    P = np.fft.fft2(p)
    Q = np.fft.fft2(q)
    H = np.zeros_like(P)
    mask = denom > 1e-8
    H[mask] = -1j * (kxx[mask] * P[mask] + kyy[mask] * Q[mask]) / denom[mask]
    height = np.fft.ifft2(H).real.astype(np.float32)
    height = cv2.GaussianBlur(height, (0, 0), 1.2)
    height = height - float(height.mean())
    scale = float(np.percentile(np.abs(height), 99))
    if scale > 1e-6:
        height = np.clip(height / scale, -1.0, 1.0)
    return height.astype(np.float32)


def method_metrics(name, rec, gt, args):
    return hf.add_height_metrics(motion.motion_metrics(name, rec, gt, args), rec, gt)


def save_contact(out_dir, gt, methods):
    first = [
        hf.tile(gt["T"], "GT clean T"),
        hf.tile(gt["B"], "GT shared B"),
        hf.tile(gt["obs"][0], "obs shift 0"),
        hf.tile(gt["obs"][1], "obs shifted"),
        hf.heat_tile(gt["height"], "GT height"),
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
        if "height" in rec:
            row.append(hf.heat_tile(rec["height"], f"{label} height"))
        row_h = max(t.shape[0] for t in row)
        rows.append(np.concatenate([np.pad(t, ((0, row_h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in row], 1))

    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    from PIL import Image

    Image.fromarray(np.concatenate(rows, 0)).save(os.path.join(out_dir, "contact.jpg"), quality=92)


def write_summary(out_dir, metrics):
    lines = [
        "# Integrable projection inverse summary",
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
    import torch

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
    projected_height = project_flow_to_height(free["disp"])
    projected_scale = hf.best_height_scale(projected_height, free["disp"], args.height_scale_max)
    projected = hf.optimize_motion_heightfield(
        obs,
        shifts,
        args,
        device,
        height_init=projected_height,
        scale_init=projected_scale,
    )
    oracle_scale = hf.best_height_scale(height_gt, D, args.height_scale_max)
    oracle = hf.optimize_motion_heightfield(obs, shifts, args, device, height_init=height_gt, scale_init=oracle_scale)
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
        method_metrics("two-frame free-flow D", free, gt, args),
        method_metrics("height-field from projected free-flow", projected, gt, args),
        method_metrics("height-field oracle init", oracle, gt, args),
    ]
    save_contact(out_dir, gt, [
        ("free-flow D", free),
        ("projected-height D", projected),
        ("oracle-height D", oracle),
    ])
    payload = {
        "case": case_name,
        "claim": "Project free-flow displacement into an integrable height-field warm start.",
        "config": vars(args) | {
            "device": device,
            "elapsed_s": elapsed,
            "shifts": shifts,
            "projected_scale_init": projected_scale,
            "oracle_scale_init": oracle_scale,
        },
        "metrics": metrics,
        "logs": {"free": free["log"], "projected": projected["log"], "oracle": oracle["log"]},
    }
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(payload, f, indent=2)
    write_summary(out_dir, metrics)
    print(f"==== INTEGRABLE PROJECTION: {case_name} ====")
    for m in metrics:
        print(
            f"{m['name']:38s} recon={m['renderer_recon_mae']:.4f} T={m['T_mae']:.4f} "
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
        "# Integrable projection inverse sweep",
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
    ap.add_argument("--seed", type=int, default=61)
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
    ap.add_argument("--sweep-seeds", default="61,62,63,64")
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
    print("==== INTEGRABLE PROJECTION SWEEP SUMMARY ====")
    for method, row in summary.items():
        print(
            f"{method}: T={row['T_mae_mean']:.4f} B={row['B_mae_mean']:.4f} "
            f"corr={row['T_highfreq_corr_with_bg_mean']:.3f} hCorr={row['height_corr_mean']:.3f}"
        )
    print("wrote", args.out)


if __name__ == "__main__":
    main()
