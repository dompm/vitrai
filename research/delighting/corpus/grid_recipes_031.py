#!/usr/bin/env python3
"""Report 031: build a labeled contact-sheet grid of our 13 synthetic recipe
renders (one clean 'without_shadow_photo' each) for the VLM taxonomy-mapping
call."""
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "results", "variety_031", "recipes")
TILE = 300


def load_font(size):
    for path in ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "/System/Library/Fonts/Helvetica.ttc"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def main():
    manifest = json.load(open(os.path.join(OUT_DIR, "recipe_manifest.json")))
    cols = 4
    rows = math.ceil(len(manifest) / cols)
    font = load_font(22)
    sheet = Image.new("RGB", (cols * TILE, rows * (TILE + 30)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, m in enumerate(manifest):
        r, c = divmod(i, cols)
        x0, y0 = c * TILE, r * (TILE + 30)
        path = os.path.join(OUT_DIR, m["sample_file"])
        tile = Image.open(path).convert("RGB")
        s = min((TILE - 8) / tile.width, (TILE - 36) / tile.height)
        tile = tile.resize((max(1, int(tile.width * s)), max(1, int(tile.height * s))))
        sheet.paste(tile, (x0 + 4, y0 + 30 + (TILE - 36 - tile.height) // 2))
        d.rectangle([x0, y0, x0 + TILE, y0 + 28], fill=(35, 35, 35))
        d.text((x0 + 6, y0 + 2), f"R{m['idx']:02d} {m['recipe']}", fill=(255, 230, 80), font=font)
    out_path = os.path.join(OUT_DIR, "recipe_grid.jpg")
    sheet.save(out_path, quality=92)
    print("saved", out_path, sheet.size)


if __name__ == "__main__":
    main()
