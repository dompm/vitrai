#!/usr/bin/env python3
"""Report 032 WP-D: per-recipe review contact sheet from a rendered batch.

Builds a labeled grid (rows = recipes, cols = [photo OFF, photo ON(specular),
gt_T, gt_height]) downscaled for committing to results/032/, so the lead can
rebuild the review page from it. Usage:

    python3 results/032/contact_sheet_032.py /tmp/b032_off /tmp/b032_on \
        results/032/contact_sheet_032.jpg
"""
import os, sys, glob, json
import numpy as np
import cv2

TILE = 340
LABEL_H = 26


def load_tile(path, tile=TILE):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        return np.full((tile, tile, 3), 30, np.uint8)
    h, w = img.shape[:2]
    s = tile / max(h, w)
    img = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))))
    out = np.full((tile, tile, 3), 30, np.uint8)
    out[:img.shape[0], :img.shape[1]] = img
    return out


def label_bar(text, width, height=LABEL_H):
    bar = np.full((height, width, 3), 18, np.uint8)
    cv2.putText(bar, text, (6, height - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (220, 220, 220), 1, cv2.LINE_AA)
    return bar


def main(off_dir, on_dir, out_path):
    offs = {os.path.basename(d).split("__")[0]: d
            for d in sorted(glob.glob(os.path.join(off_dir, "*"))) if os.path.isdir(d)}
    ons = {os.path.basename(d).split("__")[0]: d
           for d in sorted(glob.glob(os.path.join(on_dir, "*"))) if os.path.isdir(d)}
    recipes = sorted(offs)
    header = ["photo (specular OFF)", "photo (specular ON)", "gt_T", "gt_height"]
    rows = [np.concatenate([label_bar(h, TILE) for h in header], axis=1)]
    for r in recipes:
        do, dn = offs[r], ons.get(r)
        tiles = [
            load_tile(os.path.join(do, "without_shadow_photo.png")),
            load_tile(os.path.join(dn, "without_shadow_photo.png")) if dn else np.full((TILE, TILE, 3), 30, np.uint8),
            load_tile(os.path.join(do, "gt_T.png")),
            load_tile(os.path.join(do, "gt_height.png")),
        ]
        row = np.concatenate(tiles, axis=1)
        rows.append(label_bar(r, row.shape[1]))
        rows.append(row)
    sheet = np.concatenate(rows, axis=0)
    cv2.imwrite(out_path, sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])
    print(f"wrote {out_path}  ({sheet.shape[1]}x{sheet.shape[0]}, {len(recipes)} recipes)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
