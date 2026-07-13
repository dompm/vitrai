#!/usr/bin/env python3
"""Make a numbered contact sheet (reference + all candidates) for one product,
for the human/agent precision spot-check of VLM verdicts."""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
TILE = 240
LABEL_H = 22


def font(size=16):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except Exception:
        return ImageFont.load_default()


def tile(img_path, label):
    im = Image.open(img_path).convert("RGB")
    im.thumbnail((TILE, TILE - LABEL_H))
    c = Image.new("RGB", (TILE, TILE), (25, 25, 25))
    c.paste(im, ((TILE - im.width) // 2, LABEL_H + (TILE - LABEL_H - im.height) // 2))
    d = ImageDraw.Draw(c)
    d.rectangle([0, 0, TILE - 1, LABEL_H - 1], fill=(255, 210, 60))
    d.text((5, 2), label, fill=(0, 0, 0), font=font(15))
    return c


def main(pid):
    manifest = json.loads((HERE / "results" / "downloaded_manifest.json").read_text())
    entry = manifest[pid]
    paths = [(HERE / "reference_swatches" / f"{pid}.jpg", "1 REF")]
    for i, im in enumerate(entry["images"], start=2):
        paths.append((HERE / im["file"], str(i)))

    cols = 4
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * TILE, rows * TILE), (245, 245, 245))
    for k, (p, lbl) in enumerate(paths):
        sheet.paste(tile(p, lbl), ((k % cols) * TILE, (k // cols) * TILE))
    out = HERE / "results" / f"contact_{pid}.jpg"
    sheet.save(out, "JPEG", quality=85)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
