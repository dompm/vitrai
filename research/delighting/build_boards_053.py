#!/usr/bin/env python3
"""Report 053 — contact-sheet BOARDS for the deployment-capture pilot (run in the venv).

Assembles downscaled JPEG contact sheets so the lead + CTO can EYEBALL realism without opening
EXRs: full-sheet views, the crop workflow (full render -> cropped sheet -> detail patches), the
new varied shadows, front-lit reflections, and finite-depth backgrounds. Renders are gitignored;
only these JPEG boards are committed.

Usage: build_boards_053.py --root <pilot_render_dir> --out results/053/boards
"""
import argparse
import glob
import json
import os

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np


def load_srgb(path, size=256):
    a = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if a is None:
        return None
    if a.dtype != np.uint8:
        a = np.clip(a, 0, 1) if a.max() <= 1.5 else a / max(a.max(), 1e-6)
        a = (np.clip(a, 0, 1) * 255).astype(np.uint8)
    if a.ndim == 2:
        a = cv2.cvtColor(a, cv2.COLOR_GRAY2BGR)
    if a.shape[2] == 4:
        a = a[..., :3]
    return cv2.resize(a, (size, size), interpolation=cv2.INTER_AREA)


def label(img, text, color=(255, 255, 255)):
    img = img.copy()
    cv2.rectangle(img, (0, 0), (img.shape[1], 16), (0, 0, 0), -1)
    cv2.putText(img, text[:44], (3, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.34, color, 1, cv2.LINE_AA)
    return img


def _meta(d):
    try:
        return json.load(open(os.path.join(d, "meta.json")))
    except Exception:
        return {}


def _photo(d):
    for c in ("without_shadow_photo.png", "with_shadow_photo.png", "photo.png"):
        p = os.path.join(d, c)
        if os.path.exists(p):
            return p
    return None


def _tag(m):
    bg = m.get("background") or {}
    depth = bg.get("depth_m")
    dtag = "bg∞" if (bg == {} or depth is None) else f"bg{depth}m"
    return (f"{m.get('class_label','?')[:14]} {dtag} "
            f"{'SH' if m.get('has_shadow') else ''}{'FL' if m.get('front_light') else ''}")


def _grid(cells, ncol):
    if not cells:
        return None
    while len(cells) % ncol:
        cells.append(np.zeros_like(cells[0]))
    rows = [np.concatenate(cells[i:i + ncol], 1) for i in range(0, len(cells), ncol)]
    return np.concatenate(rows, 0)


def board_overview(dirs, out, cell=256, ncol=5):
    cells = []
    for d in dirs:
        p = _photo(d)
        if not p:
            continue
        img = load_srgb(p, cell)
        if img is None:
            continue
        cells.append(label(img, _tag(_meta(d)), (120, 255, 120)))
    g = _grid(cells, ncol)
    if g is not None:
        cv2.imwrite(out, g, [cv2.IMWRITE_JPEG_QUALITY, 86])
        print("wrote", out, g.shape)


def board_crop_workflow(dirs, out, cell=256):
    rows = []
    for d in dirs:
        crop_dir = os.path.join(d, "crop")
        pdir = os.path.join(d, "patches")
        full = _photo(d)
        if not full or not os.path.isdir(crop_dir):
            continue
        m = _meta(d)
        cropped = None
        for c in ("without_shadow_photo.png", "with_shadow_photo.png"):
            if os.path.exists(os.path.join(crop_dir, c)):
                cropped = os.path.join(crop_dir, c)
                break
        row = [label(load_srgb(full, cell), "full render"),
               label(load_srgb(cropped, cell) if cropped else np.zeros((cell, cell, 3), np.uint8),
                     m.get("capture_geometry", "?"), (120, 200, 255))]
        pats = sorted(glob.glob(os.path.join(pdir, "patch*_without_shadow_photo.png")) +
                      glob.glob(os.path.join(pdir, "patch*_with_shadow_photo.png")))[:2]
        for pp in pats:
            row.append(label(load_srgb(pp, cell), "detail patch"))
        while len(row) < 4:
            row.append(np.zeros((cell, cell, 3), np.uint8))
        rows.append(np.concatenate(row[:4], 1))
    if rows:
        g = np.concatenate(rows, 0)
        cv2.imwrite(out, g, [cv2.IMWRITE_JPEG_QUALITY, 86])
        print("wrote", out, g.shape)


def board_shadows(dirs, out, cell=256):
    rows = []
    for d in dirs:
        m = _meta(d)
        if not m.get("has_shadow"):
            continue
        wo = os.path.join(d, "without_shadow_photo.png")
        wi = os.path.join(d, "with_shadow_photo.png")
        if not os.path.exists(wi):
            continue
        row = [label(load_srgb(wo, cell) if os.path.exists(wo) else np.zeros((cell, cell, 3), np.uint8),
                     "clean"),
               label(load_srgb(wi, cell), f"shadow: {m.get('class_label','?')[:16]}", (120, 200, 255))]
        rows.append(np.concatenate(row, 1))
    if rows:
        g = np.concatenate(rows, 0)
        cv2.imwrite(out, g, [cv2.IMWRITE_JPEG_QUALITY, 86])
        print("wrote", out, g.shape)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", default="results/053/boards")
    ap.add_argument("--cell", type=int, default=256)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    dirs = [d for d in sorted(glob.glob(os.path.join(args.root, "*")))
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "meta.json"))]
    print(f"[boards] {len(dirs)} samples under {args.root}")
    board_overview(dirs, os.path.join(args.out, "board_overview.jpg"), args.cell)
    board_crop_workflow(dirs, os.path.join(args.out, "board_crop_workflow.jpg"), args.cell)
    board_shadows(dirs, os.path.join(args.out, "board_shadows.jpg"), args.cell)


if __name__ == "__main__":
    main()
