#!/usr/bin/env python3
"""Report 037 item E: per-recipe review contact sheet from the production-GT
integration-test batch (all 17 recipes -- 13 pre-037 + 4 new taxa -- one
lighting, --no-tex-dump --exr-codec DWAA --gt-b --gt-aov). Same pattern as
report 032's contact_sheet_032.py. Usage:

    python3 results/037/contact_sheet_037.py /tmp/037_review_batch \
        results/037/contact_sheet_037.jpg
"""
import os, sys, glob
import numpy as np
import cv2

TILE = 300
LABEL_H = 24

NEW_TAXA = {"baroque-rolling-wave", "fracture-streamer", "confetti-shard", "ring-mottle"}


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


def label_bar(text, width, height=LABEL_H, new_taxon=False):
    bar = np.full((height, width, 3), (40, 18, 18) if new_taxon else (18, 18, 18), np.uint8)
    cv2.putText(bar, text, (6, height - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                (230, 230, 230), 1, cv2.LINE_AA)
    return bar


def main(batch_dir, out_path):
    dirs = {os.path.basename(d).split("__")[0]: d
            for d in sorted(glob.glob(os.path.join(batch_dir, "*"))) if os.path.isdir(d)}
    recipes = sorted(dirs)
    header = ["photo", "gt_T", "gt_height", "gt_normal"]
    rows = [np.concatenate([label_bar(h, TILE) for h in header], axis=1)]
    for r in recipes:
        d = dirs[r]
        tiles = [
            load_tile(os.path.join(d, "without_shadow_photo.png")),
            load_tile(os.path.join(d, "gt_T.png")),
            load_tile(os.path.join(d, "gt_height.png")),
            load_tile(os.path.join(d, "gt_normal.png")),
        ]
        row = np.concatenate(tiles, axis=1)
        rows.append(label_bar(r, row.shape[1], new_taxon=r in NEW_TAXA))
        rows.append(row)
    sheet = np.concatenate(rows, axis=0)
    cv2.imwrite(out_path, sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])
    print(f"wrote {out_path}  ({sheet.shape[1]}x{sheet.shape[0]}, {len(recipes)} recipes)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
