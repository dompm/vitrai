#!/usr/bin/env python3
"""Audit manufacturer catalog sheets as a reality check for Material-v2 priors.

The scraped catalog lives outside this research worktree today. This script reads
`glass_swatch_registry.json` plus local catalog images and computes simple,
class-aware texture statistics. It then compares the suncatcher raw/relit/sheet
prior outputs against real purchasable sheets.

Why: `sheet_texture_prior.py` can make the suncatcher pieces dramatically more
consistent, but may over-flatten the sheet. The catalog gives us a style prior
from real manufacturers rather than our own procedural taste.
"""
import argparse
import json
import os
from collections import defaultdict

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "results", "catalog_texture_audit")

import extract as ex  # noqa: E402
import sheet_texture_prior as prior_exp  # noqa: E402


METRIC_KEYS = ("lum_cv", "lowfreq_cv", "highfreq_std", "chroma_mad", "sat_mean")


def resolve_default_registry():
    candidates = [
        os.path.abspath(os.path.join(HERE, "..", "..", "frontend", "public", "assets", "glass_swatch_registry.json")),
        "/Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/glass_swatch_registry.json",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


def public_root_for_registry(registry_path):
    # registry: frontend/public/assets/glass_swatch_registry.json
    return os.path.abspath(os.path.join(os.path.dirname(registry_path), ".."))


def robust_crop(rgb):
    h, w = rgb.shape[:2]
    mx = int(w * 0.04)
    my = int(h * 0.04)
    if w - 2 * mx > 64 and h - 2 * my > 64:
        return rgb[my:h - my, mx:w - mx]
    return rgb


def resize_max(rgb, max_dim):
    h, w = rgb.shape[:2]
    s = max_dim / max(h, w)
    if s >= 1:
        return rgb
    return cv2.resize(rgb, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)


def lin_lum(a):
    return a[..., 0] * ex.LUM[0] + a[..., 1] * ex.LUM[1] + a[..., 2] * ex.LUM[2]


def texture_metrics_from_rgb01(rgb01):
    lin = ex.srgb_to_lin(np.clip(rgb01, 0, 1)).astype(np.float64)
    y = np.clip(lin_lum(lin), 1e-5, 2.0)
    log_y = np.log(y)
    sigma = max(5.0, min(y.shape) / 18.0)
    low = cv2.GaussianBlur(log_y.astype(np.float32), (0, 0), sigma).astype(np.float64)
    high = log_y - low

    low_y = np.exp(low)
    chroma = lin / np.maximum(y[..., None], 1e-5)
    chroma_med = np.median(chroma.reshape(-1, 3), axis=0)
    chroma_dev = np.median(np.abs(chroma - chroma_med[None, None, :]))

    mx = rgb01.max(axis=-1)
    mn = rgb01.min(axis=-1)
    sat = (mx - mn) / np.maximum(mx, 1e-6)

    return {
        "mean_lum": float(y.mean()),
        "lum_cv": float(y.std() / max(y.mean(), 1e-9)),
        "lowfreq_cv": float(low_y.std() / max(low_y.mean(), 1e-9)),
        "highfreq_std": float(high.std()),
        "highfreq_p95": float(np.percentile(np.abs(high), 95)),
        "chroma_mad": float(chroma_dev),
        "sat_mean": float(sat.mean()),
    }


def load_catalog_image(public_root, item, max_dim):
    local = item.get("local_image", "")
    rel = local[1:] if local.startswith("/") else local
    path = os.path.join(public_root, rel)
    img = Image.open(path).convert("RGB")
    rgb = np.asarray(img).astype(np.float64) / 255.0
    return resize_max(robust_crop(rgb), max_dim), path


def summarize_rows(rows):
    summary = {}
    for key in METRIC_KEYS:
        vals = np.array([r[key] for r in rows], dtype=np.float64)
        summary[key] = {
            "p25": float(np.percentile(vals, 25)),
            "median": float(np.percentile(vals, 50)),
            "p75": float(np.percentile(vals, 75)),
        }
    return summary


def percentile(value, rows, key):
    vals = np.array([r[key] for r in rows], dtype=np.float64)
    return float((vals <= value).mean() * 100.0)


def metric_vector(row):
    return np.array([
        row["lum_cv"],
        row["lowfreq_cv"],
        row["highfreq_std"],
        row["chroma_mad"],
    ], dtype=np.float64)


def nearest_examples(target, rows, n=8):
    if not rows:
        return []
    X = np.stack([metric_vector(r) for r in rows])
    med = np.median(X, axis=0)
    scale = np.percentile(np.abs(X - med), 75, axis=0) + 1e-6
    tv = (metric_vector(target) - med) / scale
    d = np.linalg.norm((X - med) / scale - tv[None, :], axis=1)
    idx = np.argsort(d)[:n]
    return [rows[int(i)] | {"distance": float(d[int(i)])} for i in idx]


def make_thumb(path, label, w=170, h=140):
    img = Image.open(path).convert("RGB")
    img.thumbnail((w, h), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h + 34), (248, 248, 246))
    canvas.paste(img, ((w - img.width) // 2, 24 + (h - img.height) // 2))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, w, 22], fill=(0, 0, 0))
    draw.text((4, 5), label[:26], fill=(255, 230, 90))
    return np.asarray(canvas)


def save_catalog_contact(rows_by_category, suncatcher_rows, out_dir):
    selected = []
    for target_name in ("green_prior", "orange_prior"):
        target = next(r for r in suncatcher_rows if r["id"] == target_name)
        for cat in ("Cathedral", "Textured/Baroque", "Wispy/Streaky"):
            selected.extend(nearest_examples(target, rows_by_category.get(cat, []), n=3))

    # Deduplicate while preserving order.
    seen = set()
    deduped = []
    for row in selected:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        deduped.append(row)

    thumbs = [make_thumb(r["path"], f"{r['category']} {r['id']}") for r in deduped[:18]]
    if not thumbs:
        return
    cols = 3
    rows = []
    for i in range(0, len(thumbs), cols):
        chunk = thumbs[i:i + cols]
        H = max(t.shape[0] for t in chunk)
        chunk = [np.pad(t, ((0, H - t.shape[0]), (0, 8), (0, 0)), constant_values=255) for t in chunk]
        rows.append(np.concatenate(chunk, axis=1))
    W = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, W - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    Image.fromarray(np.concatenate(rows, axis=0)).save(os.path.join(out_dir, "nearest_catalog_examples.jpg"), quality=92)


def suncatcher_condition_rows():
    sheets = prior_exp.prep_sheets()
    rows = []
    for sheet_name, sheet in sheets.items():
        x0, y0, x1, y1 = [int(v) for v in sheet["interior"]]
        for cond in ("raw", "relit", "prior"):
            rgb = ex.lin_to_srgb(sheet[cond][y0:y1, x0:x1])
            row = texture_metrics_from_rgb01(np.clip(rgb, 0, 1))
            row.update({
                "id": f"{sheet_name}_{cond}",
                "sheet": sheet_name,
                "condition": cond,
            })
            rows.append(row)
    return rows


def write_markdown(out_dir, category_summary, category_counts, suncatcher_rows, rows_by_category):
    lines = [
        "# Catalog texture audit",
        "",
        "Manufacturer catalog images are used here as a reality check for the sheet-level prior.",
        "Lower `lowfreq_cv` means less broad lighting/background variation; `highfreq_std` is the retained local texture/relief signal.",
        "",
        "## Catalog distribution",
        "",
        "| category | n | lum_cv med | lowfreq_cv med | highfreq_std med | chroma_mad med | sat_mean med |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for cat, n in sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        s = category_summary[cat]
        lines.append(
            f"| {cat} | {n} | {s['lum_cv']['median']:.3f} | {s['lowfreq_cv']['median']:.3f} | "
            f"{s['highfreq_std']['median']:.3f} | {s['chroma_mad']['median']:.3f} | {s['sat_mean']['median']:.3f} |"
        )

    lines.extend([
        "",
        "## Suncatcher sheet conditions",
        "",
        "| sample | lum_cv | lowfreq_cv | highfreq_std | chroma_mad | textured highfreq percentile | cathedral lowfreq percentile |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    textured = rows_by_category.get("Textured/Baroque", [])
    cathedral = rows_by_category.get("Cathedral", [])
    for r in suncatcher_rows:
        hp = percentile(r["highfreq_std"], textured, "highfreq_std") if textured else 0
        lp = percentile(r["lowfreq_cv"], cathedral, "lowfreq_cv") if cathedral else 0
        lines.append(
            f"| {r['id']} | {r['lum_cv']:.3f} | {r['lowfreq_cv']:.3f} | {r['highfreq_std']:.3f} | "
            f"{r['chroma_mad']:.3f} | {hp:.0f}% | {lp:.0f}% |"
        )

    lines.extend([
        "",
        "## Read",
        "",
        "- The sheet prior is valuable if it lowers low-frequency contamination while keeping high-frequency texture inside the real catalog range.",
        "- If its high-frequency percentile collapses, it is too airbrushed; if its low-frequency percentile stays high, it did not solve the right problem.",
        "- This audit is a style/provenance check, not proof that the exact physical sheet was recovered.",
        "",
    ])
    with open(os.path.join(out_dir, "catalog_summary.md"), "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=resolve_default_registry())
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--max-dim", type=int, default=384)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    registry = json.load(open(args.registry))
    public_root = public_root_for_registry(args.registry)

    rows = []
    skipped = []
    for item in registry:
        try:
            rgb, path = load_catalog_image(public_root, item, args.max_dim)
            row = texture_metrics_from_rgb01(rgb)
            row.update({
                "id": item["id"],
                "manufacturer": item["manufacturer"],
                "category": item["category"],
                "name": item["name"],
                "path": path,
            })
            rows.append(row)
        except Exception as exc:
            skipped.append({"id": item.get("id"), "error": str(exc)})

    rows_by_category = defaultdict(list)
    for row in rows:
        rows_by_category[row["category"]].append(row)

    category_summary = {cat: summarize_rows(rs) for cat, rs in rows_by_category.items()}
    category_counts = {cat: len(rs) for cat, rs in rows_by_category.items()}
    suncatcher_rows = suncatcher_condition_rows()

    save_catalog_contact(rows_by_category, suncatcher_rows, args.out)
    write_markdown(args.out, category_summary, category_counts, suncatcher_rows, rows_by_category)

    payload = {
        "registry": args.registry,
        "n_catalog": len(rows),
        "n_skipped": len(skipped),
        "skipped": skipped[:50],
        "category_summary": category_summary,
        "suncatcher_conditions": suncatcher_rows,
    }
    with open(os.path.join(args.out, "metrics.json"), "w") as f:
        json.dump(payload, f, indent=2)

    print(f"catalog rows: {len(rows)} skipped: {len(skipped)}")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
