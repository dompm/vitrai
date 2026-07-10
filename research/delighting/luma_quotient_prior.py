#!/usr/bin/env python3
"""Luma-only quotient prior for sheet cleanup.

Report 019 sanity-checks the luma neural result from report 018. If the product
needs a trustworthy "remove uneven backlight but preserve glass color" assist,
we should compare the learned luma field to the simplest physical quotient:

  output = input * exp(-alpha * smooth_log_luminance_residual)

This preserves chroma/hue and high-frequency relief from the uploaded sheet.
It is still a prior, not measured truth: true wisps/streaks can be low-frequency
material, so this should be class/confidence gated.
"""
import argparse
import json
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "results", "luma_quotient_prior")

import catalog_texture_audit as audit_lib  # noqa: E402
import extract as ex  # noqa: E402
import sheet_texture_prior as prior_exp  # noqa: E402
import suncatcher_bench as sb  # noqa: E402


def lum(a):
    return a[..., 0] * ex.LUM[0] + a[..., 1] * ex.LUM[1] + a[..., 2] * ex.LUM[2]


def luma_quotient(material, interior, sigma=34.0, alpha=1.0, scale_clip=(0.35, 2.8)):
    """Remove only smooth luminance variation, preserving measured chroma.

    In log-luminance:
      logY = low + high
      logY_out = logY - alpha * (low - median(low))

    alpha=0 keeps the input. alpha=1 flattens the smooth luma field while keeping
    high-frequency relief.
    """
    out = material.copy()
    x0, y0, x1, y1 = [int(v) for v in interior]
    roi = material[y0:y1, x0:x1].astype(np.float64)
    Y = np.clip(lum(roi), 1e-5, 2.0)
    logY = np.log(Y)
    low = cv2.GaussianBlur(logY.astype(np.float32), (0, 0), sigma).astype(np.float64)
    valid = (Y > np.percentile(Y, 4)) & (Y < np.percentile(Y, 97))
    target_low = float(np.median(low[valid]))
    log_scale = -alpha * (low - target_low)
    scale = np.exp(np.clip(log_scale, np.log(scale_clip[0]), np.log(scale_clip[1])))
    out[y0:y1, x0:x1] = np.clip(roi * scale[..., None], 0, 1)
    return out


def metric_position_ext(polys, cens, sheets, scales, conds):
    out = {}
    for n in polys:
        s = prior_exp.ASSIGN[n]
        centers = sb.grid_centers(sb.valid_center_range(polys[n], sheets[s]["interior"], scales[s]), 3, 3)
        entry = {"label": prior_exp.LABELS[n], "sheet": s, "n_positions": len(centers)}
        for cond in conds:
            means = [
                sb.piece_mean_lin(sheets[s][cond], polys[n], cens[n], center, scales[s])[0]
                for center in centers
            ]
            entry[cond] = sb.dispersion(means)
        out[n] = entry
    return out


def metric_consistency_ext(polys, cens, sheets, scales, place, by_sheet, conds):
    out = {}
    for s, names in by_sheet.items():
        if len(names) < 2:
            continue
        entry = {"n_pieces": len(names)}
        for cond in conds:
            means = [
                sb.piece_mean_lin(sheets[s][cond], polys[n], cens[n], place[n], scales[s])[0]
                for n in names
            ]
            entry[cond] = sb.dispersion(means)
        out[s] = entry
    return out


def summarize_position(position, conds):
    return {
        cond: {
            "mean_dE": float(np.mean([position[n][cond]["mean_dE_to_centroid"] for n in position])),
            "lum_cv": float(np.mean([position[n][cond]["lum_cv"] for n in position])),
            "hue_std_deg": float(np.mean([position[n][cond]["hue_std_deg"] for n in position])),
        }
        for cond in conds
    }


def sheet_texture_row(sheet, cond):
    x0, y0, x1, y1 = [int(v) for v in sheet["interior"]]
    rgb = np.clip(ex.lin_to_srgb(sheet[cond][y0:y1, x0:x1]), 0, 1)
    tex = audit_lib.texture_metrics_from_rgb01(rgb)
    flat = prior_exp.robust_flatness(sheet[cond], sheet["interior"])
    return {
        "cv": flat["cv"],
        "lowfreq_cv": flat["lowfreq_cv"],
        "highfreq_std": tex["highfreq_std"],
        "chroma_mad": tex["chroma_mad"],
    }


def labeled_tile(rgb, text, w=190):
    rgb8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    h0, w0 = rgb8.shape[:2]
    tile = cv2.resize(rgb8, (w, max(1, int(round(h0 * w / max(w0, 1))))), interpolation=cv2.INTER_AREA)
    hdr = Image.new("RGB", (tile.shape[1], 24), (0, 0, 0))
    draw = ImageDraw.Draw(hdr)
    draw.text((5, 6), text[:34], fill=(255, 230, 90))
    return np.concatenate([np.asarray(hdr), tile], axis=0)


def save_sheet_contact(sheets, cond_labels, out_path):
    rows = []
    for name in ("green", "orange"):
        sheet = sheets[name]
        x0, y0, x1, y1 = [int(v) for v in sheet["interior"]]
        tiles = []
        for cond, label in cond_labels:
            rgb = np.clip(ex.lin_to_srgb(sheet[cond][y0:y1, x0:x1]), 0, 1)
            tiles.append(labeled_tile(rgb, f"{name} {label}"))
        h = max(t.shape[0] for t in tiles)
        tiles = [np.pad(t, ((0, h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in tiles]
        rows.append(np.concatenate(tiles, axis=1))
    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    Image.fromarray(np.concatenate(rows, axis=0)).save(out_path, quality=92)


def maybe_load_neural_comparison():
    out = {}
    for key, folder in (
        ("rgb_smooth", "catalog_leak_cleaner_smooth"),
        ("luma_neural", "catalog_leak_cleaner_luma"),
    ):
        path = os.path.join(HERE, "results", folder, "metrics.json")
        if os.path.exists(path):
            m = json.load(open(path))
            out[key] = m["suncatcher"]["metric2_aggregate"]
    return out


def write_summary(out_dir, metrics, cond_labels):
    agg = metrics["metric2_aggregate"]
    lines = [
        "# Luma quotient prior summary",
        "",
        "Deterministic low-frequency luminance quotient. Preserves uploaded chroma and high-frequency relief.",
        "",
        "## Position sensitivity",
        "",
        "| condition | mean dE | luminance CV | hue std deg |",
        "|---|---:|---:|---:|",
    ]
    for cond, label in cond_labels:
        row = agg[cond]
        lines.append(f"| {label} | {row['mean_dE']:.2f} | {row['lum_cv']:.3f} | {row['hue_std_deg']:.1f} |")

    neural = metrics.get("neural_comparison", {})
    if neural:
        lines.extend([
            "",
            "## Neural comparison",
            "",
            "| model after fixed `T/h` | mean dE | luminance CV | hue std deg |",
            "|---|---:|---:|---:|",
        ])
        if "luma_neural" in neural:
            row = neural["luma_neural"]["relit_neural"]
            lines.append(f"| luma neural | {row['mean_dE']:.2f} | {row['lum_cv']:.3f} | {row['hue_std_deg']:.1f} |")
        if "rgb_smooth" in neural:
            row = neural["rgb_smooth"]["relit_neural"]
            lines.append(f"| RGB smooth neural | {row['mean_dE']:.2f} | {row['lum_cv']:.3f} | {row['hue_std_deg']:.1f} |")
    lines.extend([
        "",
        "## Read",
        "",
        "- This is a prior, not measured ground truth. It is plausible for hammered/cathedral sheets and dangerous for true wisps/streaks.",
        "- If it beats the luma neural cleaner, the learned model should spend capacity on confidence/chroma/geometry rather than exposure correction.",
        "",
    ])
    with open(os.path.join(out_dir, "summary_table.md"), "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--sigma", type=float, default=34.0)
    ap.add_argument("--alphas", default="0.25,0.50,0.75,1.00")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    alphas = [float(x) for x in args.alphas.split(",") if x.strip()]

    sheets = prior_exp.prep_sheets()
    cond_labels = [("raw", "raw"), ("relit", "fixed T/h")]
    for alpha in alphas:
        cond = f"luma_q_{int(round(alpha * 100)):03d}"
        cond_labels.append((cond, f"luma quotient a={alpha:.2f}"))
        for sheet in sheets.values():
            sheet[cond] = luma_quotient(sheet["relit"], sheet["interior"], sigma=args.sigma, alpha=alpha)
    cond_labels.append(("prior", "hand sheet prior"))

    polys = sb.parse_gt_polygons(sb.TUT_TYPES)
    cens = {n: sb.centroid(p) for n, p in polys.items()}
    by_sheet, scales, place = prior_exp.setup_geometry(polys, sheets)
    conds = [c for c, _ in cond_labels]

    position = metric_position_ext(polys, cens, sheets, scales, conds)
    consistency = metric_consistency_ext(polys, cens, sheets, scales, place, by_sheet, conds)
    aggregate = summarize_position(position, conds)
    sheet_metrics = {
        s: {cond: sheet_texture_row(sheet, cond) for cond in conds}
        for s, sheet in sheets.items()
    }

    save_sheet_contact(
        sheets,
        [("raw", "raw"), ("relit", "fixed T/h")]
        + [(f"luma_q_{int(round(a * 100)):03d}", f"q a={a:.2f}") for a in alphas]
        + [("prior", "hand prior")],
        os.path.join(args.out, "sheet_contact.jpg"),
    )

    metrics = {
        "claim": "A deterministic luma quotient can remove smooth brightness contamination while preserving measured chroma and relief.",
        "honesty": "This is a class/confidence-gated prior, not measured truth; low-frequency variation can be real glass.",
        "config": {"sigma": args.sigma, "alphas": alphas},
        "metric1_cross_piece_consistency": consistency,
        "metric2_position_sensitivity": position,
        "metric2_aggregate": aggregate,
        "sheet_metrics": sheet_metrics,
        "neural_comparison": maybe_load_neural_comparison(),
    }
    with open(os.path.join(args.out, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    write_summary(args.out, metrics, cond_labels)

    print("==== REAL SUNCATCHER POSITION SENSITIVITY ====")
    for cond, label in cond_labels:
        row = aggregate[cond]
        print(f"{label:22s}: dE={row['mean_dE']:.2f} lumCV={row['lum_cv']:.3f} hue={row['hue_std_deg']:.1f}")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
