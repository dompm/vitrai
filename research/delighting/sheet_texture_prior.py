#!/usr/bin/env python3
"""Texture-preserving sheet prior experiment.

Report 013 shows the fixed extractor removes smooth illumination from real
hammered cathedral sheets, but transmitted garden/window structure still leaks
into T. This experiment asks a deliberately bolder product question:

  If we assume a cathedral sheet has roughly one physical tint and the spatial
  variation we want to keep is mainly high-frequency hammered relief, can a
  sheet-level prior make pieces less position-sensitive?

This is not a ship path by itself. It is a "plausible material prior" probe:
stronger consistency, higher risk of inventing/over-flattening. The right product
would need provenance/confidence before using this visually.
"""
import json
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results", "sheet_texture_prior")

import extract as ex  # noqa: E402
import suncatcher_bench as sb  # noqa: E402


ASSIGN = {
    "GT_PIECE_1": "orange",
    "GT_PIECE_2": "green",
    "GT_PIECE_3": "green",
    "GT_PIECE_4": "green",
}

LABELS = {
    "GT_PIECE_1": "orange-slice",
    "GT_PIECE_2": "leaf-R",
    "GT_PIECE_3": "leaf-L",
    "GT_PIECE_4": "leaf-far-L",
}


def lum(a):
    return a[..., 0] * ex.LUM[0] + a[..., 1] * ex.LUM[1] + a[..., 2] * ex.LUM[2]


def robust_flatness(a, interior):
    x0, y0, x1, y1 = [int(v) for v in interior]
    y = lum(a[y0:y1, x0:x1]).astype(np.float32)
    low = cv2.GaussianBlur(y, (0, 0), 25)
    return {
        "cv": float(y.std() / max(y.mean(), 1e-9)),
        "lowfreq_cv": float(low.std() / max(low.mean(), 1e-9)),
    }


def sheet_texture_prior(relit, interior, sigma=34.0, detail_strength=1.10):
    """Force a sheet-level tint while preserving hammered luminance relief.

    The prior decomposes the current relit material into:
      - median sheet chroma: assumed physical tint
      - high-frequency luminance: assumed relief/hammer texture
      - low-frequency luminance/chroma: assumed capture/background leakage

    That assumption is too strong for streaky/wispy glass, but intentionally
    plausible for the tutorial hammered cathedral sheets.
    """
    out = relit.copy()
    x0, y0, x1, y1 = [int(v) for v in interior]
    roi = relit[y0:y1, x0:x1].astype(np.float64)

    Y = np.clip(lum(roi), 1e-5, 2.0)
    logY = np.log(Y)
    low = cv2.GaussianBlur(logY.astype(np.float32), (0, 0), sigma).astype(np.float64)
    high = np.clip(logY - low, -0.42, 0.42)

    valid = (Y > np.percentile(Y, 8)) & (Y < np.percentile(Y, 94))
    chroma = roi / np.maximum(Y[..., None], 1e-5)
    chroma_med = np.median(chroma[valid], axis=0)
    chroma_med = chroma_med / max(float(np.dot(chroma_med, ex.LUM)), 1e-5)

    target_y = float(np.percentile(Y[valid], 58))
    Y_clean = target_y * np.exp(high * detail_strength)
    clean = chroma_med[None, None, :] * Y_clean[..., None]
    out[y0:y1, x0:x1] = np.clip(clean, 0, 1)
    return out


def prep_sheets():
    sheets = {
        "green": sb.prep_sheet(sb.GREEN, "green"),
        "orange": sb.prep_sheet(sb.ORANGE, "orange"),
    }
    for name, sheet in sheets.items():
        sheet["prior"] = sheet_texture_prior(sheet["relit"], sheet["interior"])
        sheet["prior_flatness"] = robust_flatness(sheet["prior"], sheet["interior"])
    return sheets


def setup_geometry(polys, sheets):
    by_sheet = {
        "green": [n for n in polys if ASSIGN[n] == "green"],
        "orange": [n for n in polys if ASSIGN[n] == "orange"],
    }
    scales = {
        s: sb.sheet_scale([polys[n] for n in by_sheet[s]], sheets[s]["interior"])
        for s in sheets
    }
    place = {}
    for s, names in by_sheet.items():
        ranges = [sb.valid_center_range(polys[n], sheets[s]["interior"], scales[s]) for n in names]
        for i, n in enumerate(names):
            cxlo, cxhi, cylo, cyhi = ranges[i]
            fx = (i + 0.5) / len(names)
            place[n] = (float(cxlo + fx * (cxhi - cxlo)), float((cylo + cyhi) / 2))
    return by_sheet, scales, place


def metric_position(polys, cens, sheets, scales):
    out = {}
    for n in polys:
        s = ASSIGN[n]
        centers = sb.grid_centers(sb.valid_center_range(polys[n], sheets[s]["interior"], scales[s]), 3, 3)
        entry = {"label": LABELS[n], "sheet": s, "n_positions": len(centers)}
        for cond in ("raw", "relit", "prior"):
            means = [
                sb.piece_mean_lin(sheets[s][cond], polys[n], cens[n], center, scales[s])[0]
                for center in centers
            ]
            entry[cond] = sb.dispersion(means)
        out[n] = entry
    return out


def metric_consistency(polys, cens, sheets, scales, place, by_sheet):
    out = {}
    for s, names in by_sheet.items():
        if len(names) < 2:
            continue
        entry = {"n_pieces": len(names)}
        for cond in ("raw", "relit", "prior"):
            means = [
                sb.piece_mean_lin(sheets[s][cond], polys[n], cens[n], place[n], scales[s])[0]
                for n in names
            ]
            entry[cond] = sb.dispersion(means)
        out[s] = entry
    return out


def agg(metric, cond, key="mean_dE_to_centroid"):
    return float(np.mean([metric[n][cond][key] for n in metric]))


def summarize(position):
    return {
        cond: {
            "mean_dE": agg(position, cond),
            "lum_cv": agg(position, cond, "lum_cv"),
            "hue_std_deg": agg(position, cond, "hue_std_deg"),
        }
        for cond in ("raw", "relit", "prior")
    }


def srgb_tile(a, size=260):
    rgb = (np.clip(ex.lin_to_srgb(a), 0, 1) * 255).astype(np.uint8)
    h, w = rgb.shape[:2]
    scale = size / max(h, w)
    return cv2.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def labeled(img, text):
    hdr = Image.new("RGB", (img.shape[1], 24), (0, 0, 0))
    draw = ImageDraw.Draw(hdr)
    draw.text((6, 6), text, fill=(255, 230, 90))
    return np.concatenate([np.asarray(hdr), img], axis=0)


def save_sheet_contact(sheets):
    rows = []
    for name in ("green", "orange"):
        sheet = sheets[name]
        x0, y0, x1, y1 = [int(v) for v in sheet["interior"]]
        tiles = []
        for cond, label in (("raw", "raw photo"), ("relit", "fixed T/h"), ("prior", "sheet prior")):
            tiles.append(labeled(srgb_tile(sheet[cond][y0:y1, x0:x1]), f"{name} {label}"))
        H = max(t.shape[0] for t in tiles)
        tiles = [np.pad(t, ((0, H - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in tiles]
        rows.append(np.concatenate(tiles, axis=1))
    W = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, W - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    Image.fromarray(np.concatenate(rows, axis=0)).save(os.path.join(OUT, "sheet_contact.jpg"), quality=92)


def save_position_contact(polys, cens, sheets, scales, position):
    worst = max(position, key=lambda n: position[n]["raw"]["max_pairwise_dE"])
    s = ASSIGN[worst]
    centers = sb.grid_centers(sb.valid_center_range(polys[worst], sheets[s]["interior"], scales[s]), 3, 3)
    rows = []
    for cond, label in (("raw", "RAW-COPY"), ("relit", "FIXED T/h"), ("prior", "SHEET PRIOR")):
        tiles = []
        for center in centers:
            sample, mask, _ = sb.sample_piece(sheets[s][cond], polys[worst], cens[worst], center, scales[s], rs=1.0)
            rgb = (np.clip(ex.lin_to_srgb(sample), 0, 1) * 255).astype(np.uint8)
            rgb[~mask] = 245
            tiles.append(cv2.resize(rgb, (180, int(180 * rgb.shape[0] / rgb.shape[1])), interpolation=cv2.INTER_AREA))
        H = max(t.shape[0] for t in tiles)
        row = np.concatenate([np.pad(t, ((0, H - t.shape[0]), (0, 6), (0, 0)), constant_values=245) for t in tiles], axis=1)
        rows.append(labeled(row, f"{label}: {LABELS[worst]} at 9 sheet positions"))
    W = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, W - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    Image.fromarray(np.concatenate(rows, axis=0)).save(os.path.join(OUT, f"position_contact_{worst}.jpg"), quality=92)
    return worst


def write_summary(metrics):
    a = metrics["metric2_aggregate"]
    lines = [
        "| condition | mean dE | luminance CV | hue std deg |",
        "|---|---:|---:|---:|",
    ]
    for cond in ("raw", "relit", "prior"):
        lines.append(
            f"| {cond} | {a[cond]['mean_dE']:.2f} | {a[cond]['lum_cv']:.3f} | {a[cond]['hue_std_deg']:.1f} |"
        )
    lines.append("")
    lines.append("Primary read: `prior` is a plausible sheet-level material prior, not a measured ground truth.")
    with open(os.path.join(OUT, "summary_table.md"), "w") as f:
        f.write("\n".join(lines))


def main():
    os.makedirs(OUT, exist_ok=True)
    polys = sb.parse_gt_polygons(sb.TUT_TYPES)
    cens = {n: sb.centroid(p) for n, p in polys.items()}
    sheets = prep_sheets()
    by_sheet, scales, place = setup_geometry(polys, sheets)

    consistency = metric_consistency(polys, cens, sheets, scales, place, by_sheet)
    position = metric_position(polys, cens, sheets, scales)
    worst = save_position_contact(polys, cens, sheets, scales, position)
    save_sheet_contact(sheets)

    metrics = {
        "claim": "High-risk plausible sheet prior: force sheet-level tint, preserve high-frequency hammered relief, suppress low/mid-frequency background leakage.",
        "honesty": "This improves consistency only if the cathedral sheet is physically near-uniform. It may invent/over-flatten and needs provenance/confidence.",
        "config": {
            "source": "frontend/public/assets/{green,orange}.png via suncatcher benchmark geometry",
            "conditions": ["raw", "relit", "prior"],
            "prior_sigma": 34.0,
            "prior_detail_strength": 1.10,
        },
        "sheet_flatness": {
            s: {
                "raw": {
                    "cv": sheets[s]["flatness"]["raw_cv"],
                    "lowfreq_cv": sheets[s]["flatness"]["raw_lowfreq_cv"],
                },
                "relit": {
                    "cv": sheets[s]["flatness"]["relit_cv"],
                    "lowfreq_cv": sheets[s]["flatness"]["relit_lowfreq_cv"],
                },
                "prior": sheets[s]["prior_flatness"],
            }
            for s in sheets
        },
        "metric1_cross_piece_consistency": consistency,
        "metric2_position_sensitivity": position,
        "metric2_aggregate": summarize(position),
        "worst_piece": worst,
    }
    with open(os.path.join(OUT, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    write_summary(metrics)

    print("==== POSITION-SENSITIVITY AGGREGATE ====")
    for cond, row in metrics["metric2_aggregate"].items():
        print(f"{cond:5s}: dE={row['mean_dE']:.2f} lumCV={row['lum_cv']:.3f} hue={row['hue_std_deg']:.1f}")
    print("worst piece:", worst, LABELS[worst])
    print("wrote", OUT)


if __name__ == "__main__":
    main()
