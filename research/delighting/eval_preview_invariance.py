#!/usr/bin/env python3
"""Product-shaped preview benchmark: raw RGB copy vs de-lit material relight.

The previous synthetic eval scores extracted T/h against authored maps. This
script scores the thing a Vitrai user feels: if a photographed sheet is dragged
into a stained-glass preview, does the preview depend on the capture photo's
background, exposure, and shadows, or on the physical glass?

For each synthetic sample, render a controlled "studio preview" from the
ground-truth material maps:

    preview = illum * T * (h + (1-h) * controlled_background)

Then compare two product routes:

  raw-copy baseline: the captured photo, exposure-matched to the target preview.
    This is generous to the current app; it removes global exposure but keeps
    baked background, frame/hand shadows, and source lighting.

  material relight: extract T/h from the photo, then render the same controlled
    studio preview with those maps.

It also compares clean vs with-shadow photos of the same sample. A physically
stable material representation should have a small clean-shadow preview gap.
"""
import argparse
import glob
import json
import os
import sys

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract  # noqa: E402


CLASS_MAP = {
    "cathedral-green": "cathedral-clear",
    "cathedral-amber": "cathedral-clear",
    "dark-opaque": "dark-opaque",
    "wispy-white": "wispy",
    "streaky-mix": "wispy",
}

PREVIEW_ILLUM = np.array([1.0, 0.86, 0.68], dtype=np.float64)


def clean_photo_path(sample):
    for name in ("without_shadow_photo.png", "photo.png", "no_shadow_photo.png"):
        path = os.path.join(sample, name)
        if os.path.exists(path):
            return path
    return None


def shadow_photo_path(sample):
    path = os.path.join(sample, "with_shadow_photo.png")
    return path if os.path.exists(path) else None


def load_exr_rgb(path):
    arr = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if arr is None:
        return None
    if arr.ndim == 3:
        arr = arr[..., ::-1]  # BGR -> RGB
    return arr.astype(np.float64)


def load_gt_T(sample):
    path = os.path.join(sample, "gt_T.exr")
    if os.path.exists(path):
        return load_exr_rgb(path)
    path = os.path.join(sample, "gt_T.png")
    if os.path.exists(path):
        return np.asarray(Image.open(path).convert("RGB")).astype(np.float64) / 255.0
    return None


def load_gt_h(sample):
    path = os.path.join(sample, "gt_h.png")
    if os.path.exists(path):
        return np.asarray(Image.open(path)).astype(np.float64) / 65535.0
    return None


def load_gt_mark(sample):
    path = os.path.join(sample, "gt_mark_mask.png")
    if not os.path.exists(path):
        return None
    arr = np.asarray(Image.open(path)).astype(np.float64)
    if arr.ndim == 3:
        arr = arr.mean(-1)
    return arr / (65535.0 if arr.max() > 255 else 255.0)


def resize_to(arr, hw):
    H, W = hw
    return cv2.resize(arr.astype(np.float32), (W, H), interpolation=cv2.INTER_AREA).astype(np.float64)


def preview_background(H, W):
    """A neutral backlit workbench with gentle structure.

    Uniform white would make h invisible because T*(h+(1-h)*1) collapses to T.
    The soft bands and dark leads make clear glass reveal a new controlled
    environment, while hazy glass diffuses it away.
    """
    y, x = np.mgrid[0:H, 0:W].astype(np.float64)
    xx = x / max(W - 1, 1)
    yy = y / max(H - 1, 1)
    base = 0.78 + 0.16 * (1 - yy) + 0.04 * np.sin(2 * np.pi * xx)
    warm = np.stack([base, base * 0.96, base * 0.88], axis=-1)

    # lead-like lines behind the glass: enough to exercise haze, not so harsh
    # that small registration differences dominate the score.
    stripe_v = np.exp(-((np.mod(xx * 5.0 + 0.03 * np.sin(yy * 7), 1.0) - 0.5) / 0.035) ** 2)
    stripe_h = np.exp(-((np.mod(yy * 4.0 + 0.04 * np.sin(xx * 5), 1.0) - 0.5) / 0.04) ** 2)
    stripes = np.clip(stripe_v + 0.75 * stripe_h, 0, 1)
    bg = warm * (1 - 0.42 * stripes[..., None])
    return np.clip(bg, 0.05, 1.0)


def render_preview(T, h, bg):
    return extract.render(T, h, PREVIEW_ILLUM, bg=bg)


def exposure_match(src, target, valid=None):
    """Match source to target with one scalar luminance gain.

    This is intentionally generous to raw-copy: the app does not currently get
    this for free, but it prevents the benchmark from being a trivial exposure
    contest.
    """
    src_y = extract.lum(np.clip(src, 0, None))
    target_y = extract.lum(np.clip(target, 0, None))
    if valid is None:
        valid = np.ones(src_y.shape, dtype=bool)
    if not np.any(valid):
        return src
    s = np.percentile(src_y[valid], 95)
    t = np.percentile(target_y[valid], 95)
    gain = float(np.clip(t / max(s, 1e-4), 0.05, 20.0))
    return np.clip(src * gain, 0, 1.5)


def srgb_mae255(a, b, valid=None):
    err = np.abs(extract.lin_to_srgb(np.clip(a, 0, 1)) - extract.lin_to_srgb(np.clip(b, 0, 1)))
    if valid is not None:
        err = err[valid[..., None] * np.ones_like(err, dtype=bool)]
    return float(err.mean() * 255.0)


def srgb_p95255(a, b, valid=None):
    err = np.abs(extract.lin_to_srgb(np.clip(a, 0, 1)) - extract.lin_to_srgb(np.clip(b, 0, 1)))
    if valid is not None:
        err = err[valid[..., None] * np.ones_like(err, dtype=bool)]
    return float(np.percentile(err, 95) * 255.0)


def mean_srgb(img, valid):
    srgb = extract.lin_to_srgb(np.clip(img, 0, 1))
    return [float(v) for v in srgb[valid].reshape(-1, 3).mean(0)]


def valid_mask(sample, photo_lin, gtT, target):
    H, W = target.shape[:2]
    valid = np.ones((H, W), dtype=bool)
    mark = load_gt_mark(sample)
    if mark is not None:
        valid &= resize_to(mark, (H, W)) <= 0.5

    # Synthetic frame/mullion pixels are capture occluders, not glass. Exclude
    # only the obvious case: photo nearly black while authored glass is not.
    photo_y = extract.lum(photo_lin)
    gt_y = extract.lum(gtT)
    frame = (photo_y < 0.018) & (gt_y > 0.07)
    valid &= ~cv2.dilate(frame.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    return valid


def detect_shadow(clean_lin, shadow_lin):
    yc = extract.lum(clean_lin)
    ys = extract.lum(shadow_lin)
    shadow = (yc - ys) > 0.025
    shadow = cv2.morphologyEx(shadow.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return shadow.astype(bool)


def tile(img, label, linear=True, gain=1.0):
    arr = np.clip(img * gain, 0, 1)
    if linear:
        arr = extract.lin_to_srgb(arr)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    out = (arr * 255).astype(np.uint8)
    im = Image.fromarray(out)
    draw = ImageDraw.Draw(im)
    draw.rectangle([0, 0, 8 + 7 * len(label), 16], fill=(0, 0, 0))
    draw.text((4, 2), label, fill=(255, 255, 90))
    return np.asarray(im)


def contact_row(arrays, metrics, row_px):
    cols = [
        tile(arrays["raw_clean"], "raw clean"),
        tile(arrays["raw_shadow"], "raw shadow"),
        tile(arrays["target"], "target"),
        tile(arrays["mat_clean"], "mat clean"),
        tile(arrays["mat_shadow"], "mat shadow"),
        tile(np.abs(extract.lin_to_srgb(np.clip(arrays["raw_clean"], 0, 1)) -
                    extract.lin_to_srgb(np.clip(arrays["target"], 0, 1))), "raw err x4", linear=False, gain=4.0),
        tile(np.abs(extract.lin_to_srgb(np.clip(arrays["mat_clean"], 0, 1)) -
                    extract.lin_to_srgb(np.clip(arrays["target"], 0, 1))), "mat err x4", linear=False, gain=4.0),
        tile(arrays["shadow_mask"].astype(float), "shadow", linear=False),
    ]
    cols = [cv2.resize(c, (row_px, row_px), interpolation=cv2.INTER_AREA) for c in cols]
    row = np.concatenate([np.pad(c, ((2, 18), (2, 2), (0, 0)), constant_values=20) for c in cols], axis=1)
    im = Image.fromarray(row)
    draw = ImageDraw.Draw(im)
    draw.text(
        (4, row_px + 2),
        f"{metrics['sample']} raw={metrics['raw_mae']:.1f} mat={metrics['material_mae']:.1f} "
        f"gap raw={metrics['raw_shadow_gap']:.1f} mat={metrics['material_shadow_gap']:.1f}",
        fill=(225, 225, 225),
    )
    return np.asarray(im)


def eval_sample(sample, size):
    meta_path = os.path.join(sample, "meta.json")
    if not os.path.exists(meta_path):
        return None, "no meta"
    meta = json.load(open(meta_path))
    label = meta.get("class_label")
    glass_class = CLASS_MAP.get(label)
    if glass_class is None:
        return None, "unknown class"

    clean_path = clean_photo_path(sample)
    shadow_path = shadow_photo_path(sample)
    gtT = load_gt_T(sample)
    gth = load_gt_h(sample)
    if clean_path is None or shadow_path is None or gtT is None or gth is None:
        return None, "incomplete"

    clean_lin = extract.load_linear(clean_path, None, size)
    shadow_lin = extract.load_linear(shadow_path, None, size)
    maps_clean = extract.extract_maps(clean_lin, glass_class, mark_region="none")
    maps_shadow = extract.extract_maps(shadow_lin, glass_class, mark_region="none")

    H, W = maps_clean["h"].shape
    gtT = resize_to(gtT, (H, W))
    gth = resize_to(gth[..., None] if gth.ndim == 2 else gth, (H, W))
    if gth.ndim == 3:
        gth = gth[..., 0]

    bg = preview_background(H, W)
    target = render_preview(gtT, gth, bg)
    mat_clean = render_preview(maps_clean["T"], maps_clean["h"], bg)
    mat_shadow = render_preview(maps_shadow["T"], maps_shadow["h"], bg)

    valid = valid_mask(sample, clean_lin, gtT, target)
    raw_clean = exposure_match(clean_lin, target, valid)
    raw_shadow = exposure_match(shadow_lin, target, valid)
    shadow = detect_shadow(clean_lin, shadow_lin) & valid

    metrics = {
        "sample": os.path.basename(sample),
        "class_label": label,
        "glass_name": meta.get("glass_name", ""),
        "glass_class": glass_class,
        "has_frame": bool(meta.get("has_frame", False)),
        "valid_pct": float(valid.mean() * 100),
        "shadow_pct": float(shadow.mean() * 100),
        "raw_mae": srgb_mae255(raw_clean, target, valid),
        "raw_p95": srgb_p95255(raw_clean, target, valid),
        "material_mae": srgb_mae255(mat_clean, target, valid),
        "material_p95": srgb_p95255(mat_clean, target, valid),
        "raw_shadow_gap": srgb_mae255(raw_clean, raw_shadow, valid),
        "material_shadow_gap": srgb_mae255(mat_clean, mat_shadow, valid),
        "raw_shadow_gap_inside": srgb_mae255(raw_clean, raw_shadow, shadow) if shadow.any() else None,
        "material_shadow_gap_inside": srgb_mae255(mat_clean, mat_shadow, shadow) if shadow.any() else None,
        "target_mean_srgb": mean_srgb(target, valid),
        "raw_mean_srgb": mean_srgb(raw_clean, valid),
        "material_mean_srgb": mean_srgb(mat_clean, valid),
    }

    arrays = {
        "target": target,
        "mat_clean": mat_clean,
        "mat_shadow": mat_shadow,
        "raw_clean": raw_clean,
        "raw_shadow": raw_shadow,
        "shadow_mask": shadow,
    }
    return (metrics, arrays), None


def aggregate(rows):
    out = {}
    for label in sorted({r["class_label"] for r in rows}):
        rs = [r for r in rows if r["class_label"] == label]
        raw_inside = [r["raw_shadow_gap_inside"] for r in rs if r["raw_shadow_gap_inside"] is not None]
        mat_inside = [r["material_shadow_gap_inside"] for r in rs if r["material_shadow_gap_inside"] is not None]
        out[label] = {
            "n": len(rs),
            "raw_mae": float(np.mean([r["raw_mae"] for r in rs])),
            "material_mae": float(np.mean([r["material_mae"] for r in rs])),
            "raw_p95": float(np.mean([r["raw_p95"] for r in rs])),
            "material_p95": float(np.mean([r["material_p95"] for r in rs])),
            "raw_shadow_gap": float(np.mean([r["raw_shadow_gap"] for r in rs])),
            "material_shadow_gap": float(np.mean([r["material_shadow_gap"] for r in rs])),
            "raw_shadow_gap_inside": float(np.mean(raw_inside)) if raw_inside else None,
            "material_shadow_gap_inside": float(np.mean(mat_inside)) if mat_inside else None,
            "mean_raw_srgb": [float(v) for v in np.mean([r["raw_mean_srgb"] for r in rs], axis=0)],
            "mean_material_srgb": [float(v) for v in np.mean([r["material_mean_srgb"] for r in rs], axis=0)],
            "mean_target_srgb": [float(v) for v in np.mean([r["target_mean_srgb"] for r in rs], axis=0)],
        }
    return out


def group_light_variance(rows):
    """Mean-color variance across multiple captures of the same physical sheet."""
    by = {}
    for r in rows:
        by.setdefault(r["glass_name"], []).append(r)
    out = {}
    for name, rs in sorted(by.items()):
        if len(rs) < 2:
            continue
        raw = np.array([r["raw_mean_srgb"] for r in rs])
        mat = np.array([r["material_mean_srgb"] for r in rs])
        tgt = np.array([r["target_mean_srgb"] for r in rs])
        out[name] = {
            "n": len(rs),
            "raw_mean_std_srgb255": float(raw.std(axis=0).mean() * 255),
            "material_mean_std_srgb255": float(mat.std(axis=0).mean() * 255),
            "target_mean_std_srgb255": float(tgt.std(axis=0).mean() * 255),
        }
    return out


def write_summary_table(per_recipe, path):
    lines = [
        "| recipe | n | raw MAE | material MAE | raw shadow gap | material shadow gap | raw shadow inside | material shadow inside | raw p95 | material p95 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for label, v in per_recipe.items():
        raw_inside = "n/a" if v["raw_shadow_gap_inside"] is None else f"{v['raw_shadow_gap_inside']:.1f}"
        mat_inside = "n/a" if v["material_shadow_gap_inside"] is None else f"{v['material_shadow_gap_inside']:.1f}"
        lines.append(
            f"| {label} | {v['n']} | {v['raw_mae']:.1f} | {v['material_mae']:.1f} | "
            f"{v['raw_shadow_gap']:.1f} | {v['material_shadow_gap']:.1f} | "
            f"{raw_inside} | {mat_inside} | "
            f"{v['raw_p95']:.1f} | {v['material_p95']:.1f} |"
        )
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="synthetic_data folder")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "preview_invariance"))
    ap.add_argument("--size", type=int, default=700)
    ap.add_argument("--recipes", default=None, help="comma-separated class_label filter")
    ap.add_argument("--max-rows", type=int, default=4)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    recipe_filter = set(args.recipes.split(",")) if args.recipes else None
    samples = sorted(d for d in glob.glob(os.path.join(args.data, "*")) if os.path.isdir(d))

    rows = []
    skipped = []
    contacts = {}
    for sample in samples:
        meta_path = os.path.join(sample, "meta.json")
        if not os.path.exists(meta_path):
            skipped.append([os.path.basename(sample), "no meta"])
            continue
        label = json.load(open(meta_path)).get("class_label")
        if recipe_filter and label not in recipe_filter:
            continue
        result, reason = eval_sample(sample, args.size)
        if result is None:
            skipped.append([os.path.basename(sample), reason])
            continue
        metrics, arrays = result
        rows.append(metrics)
        contacts.setdefault(metrics["class_label"], [])
        if len(contacts[metrics["class_label"]]) < args.max_rows:
            contacts[metrics["class_label"]].append(contact_row(arrays, metrics, row_px=170))
        print(
            f"{metrics['sample']:42s} raw={metrics['raw_mae']:.1f} "
            f"mat={metrics['material_mae']:.1f} shadow raw={metrics['raw_shadow_gap']:.1f} "
            f"mat={metrics['material_shadow_gap']:.1f}"
        )

    for label, contact_rows in contacts.items():
        width = max(r.shape[1] for r in contact_rows)
        padded = [np.pad(r, ((0, 0), (0, width - r.shape[1]), (0, 0)), constant_values=20)
                  for r in contact_rows]
        Image.fromarray(np.concatenate(padded, axis=0)).save(
            os.path.join(args.out, f"contact_{label}.jpg"), quality=82
        )

    per_recipe = aggregate(rows)
    light_variance = group_light_variance(rows)
    report = {
        "size": args.size,
        "n_samples": len(rows),
        "preview_illum_rgb_linear": [float(v) for v in PREVIEW_ILLUM],
        "metric_units": "sRGB MAE on 0-255 scale after exposure-matching raw baseline to target preview",
        "skipped": skipped,
        "per_recipe": per_recipe,
        "per_sample": rows,
        "light_variance": light_variance,
    }
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(report, f, indent=2)
    table = write_summary_table(per_recipe, os.path.join(args.out, "summary_table.md"))
    print("\n" + table)
    print(f"\nskipped: {skipped}")
    print(f"outputs in {args.out}")


if __name__ == "__main__":
    main()
