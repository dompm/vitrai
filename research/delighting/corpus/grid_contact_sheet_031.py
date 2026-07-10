#!/usr/bin/env python3
"""Report 031: build labeled NxM contact-sheet grids (9-12 tiles each) from
the sample_manifest.json picks, for VLM taxonomy-pass batches. Each tile is
labeled with a bold tile number (matching the manifest 'idx') so the VLM can
refer to "tile 3" etc. Also writes a per-batch text sidecar listing
idx/manufacturer/category/name as hints.
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "results", "variety_031")
IMG_DIR = os.path.join(OUT_DIR, "images")
GRID_DIR = os.path.join(OUT_DIR, "grids")

TILE = 260


def load_font(size):
    for path in ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "/System/Library/Fonts/Helvetica.ttc"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def make_grid(items, out_path, cols=3):
    n = len(items)
    rows = math.ceil(n / cols)
    font = load_font(28)
    sheet = Image.new("RGB", (cols * TILE, rows * (TILE + 34)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(items):
        r, c = divmod(i, cols)
        x0, y0 = c * TILE, r * (TILE + 34)
        path = os.path.join(IMG_DIR, im["sample_file"])
        try:
            tile = Image.open(path).convert("RGB")
        except Exception as e:
            tile = Image.new("RGB", (TILE, TILE - 4), (60, 0, 0))
        s = min((TILE - 8) / tile.width, (TILE - 40) / tile.height)
        tile = tile.resize((max(1, int(tile.width * s)), max(1, int(tile.height * s))))
        sheet.paste(tile, (x0 + 4, y0 + 34 + (TILE - 40 - tile.height) // 2))
        d.rectangle([x0, y0, x0 + TILE, y0 + 30], fill=(35, 35, 35))
        d.text((x0 + 6, y0 + 2), f"#{im['idx']:03d}", fill=(255, 230, 80), font=font)
    sheet.save(out_path, quality=88)
    print("saved", out_path, sheet.size)


def main():
    manifest = json.load(open(os.path.join(OUT_DIR, "sample_manifest.json")))
    batch_size = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    os.makedirs(GRID_DIR, exist_ok=True)
    for b in range(0, len(manifest), batch_size):
        batch = manifest[b:b + batch_size]
        bnum = b // batch_size
        out_img = os.path.join(GRID_DIR, f"batch{bnum:02d}.jpg")
        make_grid(batch, out_img, cols=cols)
        hints = os.path.join(GRID_DIR, f"batch{bnum:02d}_hints.txt")
        with open(hints, "w") as f:
            for im in batch:
                f.write(f"#{im['idx']:03d}  [{im['manufacturer']} / {im['category']} / tag={im['tag']}]  \"{im['name']}\"\n")
        print("hints ->", hints)


if __name__ == "__main__":
    main()
