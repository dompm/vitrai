#!/usr/bin/env python3
"""Catalog-derived material mean priors for the curl renderer.

Report 027 showed that an oracle material mean prior collapses the remaining
T/B gauge. This script replaces the oracle with noisy priors computed from the
manufacturer catalog swatch corpus:

  - category/color median RGB
  - category/color median luma
  - "greenest" cathedral subsets by chroma

The goal is not to prove catalog images are calibrated truth. It is to measure
whether real catalog statistics land near the useful biased-prior regime.
"""
import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import differentiable_sheet_curl_scale_prior as scale_exp
import differentiable_sheet_heightfield as hf
import differentiable_sheet_inverse as inv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "results", "differentiable_sheet_catalog_prior_sweep")


def default_registry():
    candidates = [
        os.path.abspath(os.path.join(HERE, "..", "..", "frontend", "public", "assets", "glass_swatch_registry.json")),
        "/Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/glass_swatch_registry.json",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[-1]


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def public_root_for_registry(registry_path):
    return Path(registry_path).resolve().parents[1]


def image_mean_lin(path, max_dim=160):
    img = Image.open(path).convert("RGB")
    img.thumbnail((max_dim, max_dim), Image.Resampling.BOX)
    rgb = np.asarray(img).astype(np.float32) / 255.0
    h, w = rgb.shape[:2]
    rgb = rgb[int(0.05 * h):int(0.95 * h), int(0.05 * w):int(0.95 * w)]
    mx = rgb.max(axis=-1)
    mask = (mx < 0.985) & (mx > 0.015)
    if mask.mean() > 0.20:
        rgb = rgb[mask]
    return inv.srgb_to_lin(rgb.reshape(-1, 3)).mean(axis=0).astype(np.float32)


def load_catalog_means(registry_path, category, color_family, max_items=9999):
    registry = json.load(open(registry_path))
    root = public_root_for_registry(registry_path)
    rows = []
    for item in registry:
        if item.get("category") != category or item.get("color_family") != color_family:
            continue
        local = item.get("local_image", "").lstrip("/")
        path = root / local
        if not path.exists():
            continue
        try:
            mean = image_mean_lin(path)
            rows.append({
                "id": item.get("id"),
                "manufacturer": item.get("manufacturer"),
                "name": item.get("name"),
                "mean_rgb": mean,
                "luma": float(mean @ inv.LUM),
                "red_green_ratio": float(mean[0] / max(mean[1], 1e-6)),
                "green_chroma": float(mean[1] / max(mean.sum(), 1e-6)),
            })
        except Exception:
            continue
    rows.sort(key=lambda r: r["id"] or "")
    return rows[:max_items]


def rgb_prior_from_rows(rows, mode, top_n):
    if not rows:
        raise ValueError("no catalog rows for prior")
    selected = rows
    if mode == "cathedral-green-rgb":
        selected = rows
    elif mode == "cathedral-green-luma":
        selected = rows
    elif mode == "greenest-rgb":
        selected = sorted(rows, key=lambda r: -r["green_chroma"])[:top_n]
    elif mode == "greenest-luma":
        selected = sorted(rows, key=lambda r: -r["green_chroma"])[:top_n]
    elif mode == "low-redgreen-rgb":
        selected = sorted(rows, key=lambda r: r["red_green_ratio"])[:top_n]
    elif mode == "low-redgreen-luma":
        selected = sorted(rows, key=lambda r: r["red_green_ratio"])[:top_n]
    else:
        raise ValueError(f"unknown catalog mode {mode}")
    rgb = np.median(np.stack([r["mean_rgb"] for r in selected]), axis=0).astype(np.float32)
    luma = float(np.median([r["luma"] for r in selected]))
    return rgb, np.array([luma], dtype=np.float32), selected


def mode_target(mode, catalog_rows, top_n):
    if mode == "none":
        return "none", None, []
    if mode == "rgb-oracle":
        return "rgb-oracle", "oracle", []
    if mode == "luma-oracle":
        return "luma-oracle", "oracle", []
    rgb, luma, selected = rgb_prior_from_rows(catalog_rows, mode, top_n)
    if mode.endswith("-luma"):
        return "luma-oracle", luma, selected
    return "rgb-oracle", rgb, selected


def save_contact(out_dir, gt, methods):
    first = [
        hf.tile(gt["T"], "GT clean T"),
        hf.tile(gt["B"], "synthetic background B"),
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
    Image.fromarray(np.concatenate(rows, axis=0)).save(os.path.join(out_dir, "contact.jpg"), quality=92)


def run_case(args, out_dir, case_name, catalog_rows):
    ensure_dir(out_dir)
    rng = np.random.default_rng(args.seed)
    rng2 = np.random.default_rng(args.seed + 77)
    import torch
    import differentiable_sheet_motion as motion

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
    prior_info = {}
    for label in parse_modes(args.prior_modes):
        internal_mode, target, selected = mode_target(label, catalog_rows, args.top_n)
        if isinstance(target, str) and target == "oracle":
            target = scale_exp.target_for_mode(T, internal_mode)
        rec = scale_exp.optimize_curl_prior(obs, shifts, args, device, internal_mode, target)
        rec["prior_mode"] = label
        methods.append((label, rec))
        prior_info[label] = {
            "internal_mode": internal_mode,
            "target": None if target is None else np.asarray(target).tolist(),
            "selected_ids": [r["id"] for r in selected[:12]],
            "selected_n": len(selected),
        }

    gt = {
        "T": T,
        "D": D,
        "height": height_gt,
        "B": B,
        "obs": obs,
        "warped": warped,
        "shifts": shifts,
    }
    metrics = [scale_exp.method_metrics(label, rec, gt, args) for label, rec in methods]
    save_contact(out_dir, gt, methods)
    scale_exp.write_summary(out_dir, metrics)
    payload = {
        "case": case_name,
        "claim": "Noisy catalog mean priors may land close enough to break the T/B gauge.",
        "config": vars(args) | {"device": device, "shifts": shifts},
        "gt_mean_rgb": T.mean(axis=(0, 1)).tolist(),
        "gt_mean_luma": float((T * inv.LUM).sum(axis=-1).mean()),
        "prior_info": prior_info,
        "metrics": metrics,
    }
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(payload, f, indent=2)
    print(f"==== CATALOG PRIOR: {case_name} ====")
    for m in metrics:
        print(
            f"{m['name']:24s} T={m['T_mae']:.4f} B={m['B_mae']:.4f} "
            f"meanRGB={m['mean_rgb_mae']:.4f} corr={m['T_highfreq_corr_with_bg']:.3f}"
        )
    return payload


def summarize_sweep(out_dir, cases):
    by_method = {}
    for case in cases:
        for m in case["metrics"]:
            by_method.setdefault(m["name"], []).append(m)

    def mean_std(rows, key):
        vals = np.array([r[key] for r in rows], dtype=np.float64)
        return float(vals.mean()), float(vals.std())

    order = {m: i for i, m in enumerate(parse_modes("none,luma-oracle,rgb-oracle,cathedral-green-luma,cathedral-green-rgb,greenest-luma,greenest-rgb,low-redgreen-luma,low-redgreen-rgb"))}
    lines = [
        "# Catalog-derived material prior sweep",
        "",
        "| method | T MAE mean | T MAE std | B MAE mean | recon MAE mean | preview CV mean | T-bg corr mean | mean RGB MAE | mean luma abs | n |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    summary = {}
    for method, rows in sorted(by_method.items(), key=lambda kv: order.get(kv[0], 99)):
        t_mu, t_sd = mean_std(rows, "T_mae")
        b_mu, _ = mean_std(rows, "B_mae")
        recon_mu, _ = mean_std(rows, "renderer_recon_mae")
        cv_mu, _ = mean_std(rows, "preview_lum_cv")
        corr_mu, _ = mean_std(rows, "T_highfreq_corr_with_bg")
        rgb_mu, _ = mean_std(rows, "mean_rgb_mae")
        lum_mu, _ = mean_std(rows, "mean_luma_abs")
        summary[method] = {
            "T_mae_mean": t_mu,
            "T_mae_std": t_sd,
            "B_mae_mean": b_mu,
            "renderer_recon_mae_mean": recon_mu,
            "preview_lum_cv_mean": cv_mu,
            "T_highfreq_corr_with_bg_mean": corr_mu,
            "mean_rgb_mae_mean": rgb_mu,
            "mean_luma_abs_mean": lum_mu,
            "n": len(rows),
        }
        lines.append(
            f"| {method} | {t_mu:.4f} | {t_sd:.4f} | {b_mu:.4f} | {recon_mu:.4f} | "
            f"{cv_mu:.3f} | {corr_mu:.3f} | {rgb_mu:.4f} | {lum_mu:.4f} | {len(rows)} |"
        )
    with open(os.path.join(out_dir, "sweep_summary.md"), "w") as f:
        f.write("\n".join(lines))
    with open(os.path.join(out_dir, "sweep_metrics.json"), "w") as f:
        json.dump({"cases": cases, "summary": summary}, f, indent=2)
    return summary


def write_catalog_prior_summary(out_dir, catalog_rows, args):
    modes = [m for m in parse_modes(args.prior_modes) if m not in ("none", "rgb-oracle", "luma-oracle")]
    lines = [
        "# Catalog prior targets",
        "",
        f"Registry: `{args.registry}`",
        f"Catalog filter: category `{args.catalog_category}`, color `{args.catalog_color}`.",
        f"Rows: {len(catalog_rows)}.",
        "",
        "| mode | internal prior | selected n | target RGB/luma | first selected ids |",
        "|---|---|---:|---|---|",
    ]
    for mode in modes:
        internal, target, selected = mode_target(mode, catalog_rows, args.top_n)
        lines.append(
            f"| {mode} | {internal} | {len(selected)} | "
            f"`{np.round(target, 4).tolist() if target is not None else None}` | "
            f"{', '.join(r['id'] for r in selected[:5])} |"
        )
    with open(os.path.join(out_dir, "catalog_prior_targets.md"), "w") as f:
        f.write("\n".join(lines))


def parse_modes(text):
    return [x.strip() for x in text.split(",") if x.strip()]


def parse_seeds(text):
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--registry", default=default_registry())
    ap.add_argument("--catalog-category", default="Cathedral")
    ap.add_argument("--catalog-color", default="Green")
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--size", type=int, default=144)
    ap.add_argument("--seed", type=int, default=91)
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
    ap.add_argument("--prior-modes", default="none,luma-oracle,rgb-oracle,cathedral-green-luma,cathedral-green-rgb,greenest-luma,greenest-rgb,low-redgreen-luma,low-redgreen-rgb")
    ap.add_argument("--log-every", type=int, default=450)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--sweep-seeds", default="91,92,93,94")
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()

    ensure_dir(args.out)
    catalog_rows = load_catalog_means(args.registry, args.catalog_category, args.catalog_color)
    write_catalog_prior_summary(args.out, catalog_rows, args)
    if not args.sweep:
        run_case(args, args.out, "single", catalog_rows)
        return

    cases = []
    for seed in parse_seeds(args.sweep_seeds):
        case_args = argparse.Namespace(**(vars(args) | {"seed": seed}))
        case_name = f"seed{seed}"
        payload = run_case(case_args, os.path.join(args.out, case_name), case_name, catalog_rows)
        cases.append({"case": case_name, "seed": seed, "metrics": payload["metrics"], "config": payload["config"], "prior_info": payload["prior_info"]})
    summary = summarize_sweep(args.out, cases)
    print("==== CATALOG PRIOR SWEEP SUMMARY ====")
    for method, row in summary.items():
        print(f"{method}: T={row['T_mae_mean']:.4f} B={row['B_mae_mean']:.4f} meanRGB={row['mean_rgb_mae_mean']:.4f}")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
