#!/usr/bin/env python3
"""Contact sheet over a batch: one row per sheet -- original | T | h | relit
warm | relit cool -- plus the per-sheet clean-pixel recon MAE in the label.

Usage: contact_sheet.py BENCH_DIR RESULTS_DIR OUT.jpg [tile_px]
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import srgb_to_lin, lin_to_srgb  # noqa: E402

WARM = np.array([1.0, 0.72, 0.42])
COOL = np.array([0.65, 0.82, 1.0])


def tile_img(arr, size):
    im = Image.fromarray(arr)
    s = size / max(im.size)
    return np.asarray(im.resize((max(1, int(im.size[0] * s)), max(1, int(im.size[1] * s))),
                                Image.LANCZOS))


def main(bench, results, out, size=190):
    manifest = {}
    mpath = os.path.join(bench, "manifest.json")
    if os.path.exists(mpath):
        manifest = json.load(open(mpath))
    rows = []
    header = None
    for f in sorted(os.listdir(bench)):
        if not f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        name = os.path.splitext(f)[0]
        tp, hp = os.path.join(results, f"{name}_T.png"), os.path.join(results, f"{name}_h.png")
        if not (os.path.exists(tp) and os.path.exists(hp)):
            continue
        src = Image.open(os.path.join(bench, f)).convert("RGB")
        corners = manifest.get(f, {}).get("corners")
        if corners:
            src = src.crop(tuple(corners))
        T_lin = srgb_to_lin(np.asarray(Image.open(tp)).astype(np.float64) / 255)
        h = np.asarray(Image.open(hp)).astype(np.float64) / 255
        enc = lambda a: (lin_to_srgb(np.clip(a, 0, 1)) * 255).astype(np.uint8)
        tiles = [
            tile_img(np.asarray(src), size),
            tile_img(enc(T_lin), size),
            tile_img(np.stack([(h * 255).astype(np.uint8)] * 3, -1), size),
            tile_img(enc(T_lin * WARM), size),
            tile_img(enc(T_lin * COOL), size),
        ]
        hh = max(t.shape[0] for t in tiles)
        tiles = [np.pad(t, ((0, hh - t.shape[0]), (2, 2), (0, 0)), constant_values=25) for t in tiles]
        row = np.concatenate(tiles, axis=1)
        mfile = os.path.join(results, f"{name}_metrics.json")
        label = name
        if os.path.exists(mfile):
            met = json.load(open(mfile))
            label = (f"{name}  [{met['glass_class']}]  MAE {met['recon_mae_srgb255']:.2f}/255  "
                     f"p95 {met['recon_p95_srgb255']:.1f}  h_mean {met['h_mean']:.2f}")
        bar = np.full((18, row.shape[1], 3), 15, np.uint8)
        im = Image.fromarray(np.concatenate([bar, row], axis=0))
        d = ImageDraw.Draw(im)
        d.text((6, 3), label, fill=(255, 255, 120))
        rows.append(np.asarray(im))
        if header is None:
            cw = row.shape[1] // 5
            hb = Image.fromarray(np.full((20, row.shape[1], 3), 40, np.uint8))
            dh = ImageDraw.Draw(hb)
            for i, t in enumerate(["original", "T", "h", "relit warm", "relit cool"]):
                dh.text((i * cw + 8, 4), t, fill=(255, 255, 120))
            header = np.asarray(hb)
    wmax = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 4), (0, wmax - r.shape[1]), (0, 0)), constant_values=15) for r in rows]
    sheet = np.concatenate([header] + rows, axis=0)
    Image.fromarray(sheet).save(out, quality=90)
    print("saved", out, sheet.shape)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], int(a[3]) if len(a) > 3 else 190)
