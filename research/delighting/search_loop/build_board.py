#!/usr/bin/env python3
"""
Step 4: assemble the review board -- one row per pilot product, reference
swatch first, then verified (match=true) candidates with a small context
label baked into the tile. Small JPEGs only.
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
RESULTS = HERE / "results"
OUT_DIR = HERE.parent / "results" / "042"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TILE = 160
PAD = 6
LABEL_H = 18
MAX_COLS = 9  # reference + up to 8 verified matches shown per row


def load_font(size=12):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except Exception:
        return ImageFont.load_default()


def make_tile(img_path, label, border_color):
    im = Image.open(img_path).convert("RGB")
    im.thumbnail((TILE, TILE - LABEL_H))
    canvas = Image.new("RGB", (TILE, TILE), (30, 30, 30))
    ox = (TILE - im.width) // 2
    oy = LABEL_H + (TILE - LABEL_H - im.height) // 2
    canvas.paste(im, (ox, oy))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, TILE - 1, LABEL_H - 1], fill=border_color)
    font = load_font(11)
    d.text((3, 3), label[:24], fill=(0, 0, 0), font=font)
    d.rectangle([0, 0, TILE - 1, TILE - 1], outline=border_color, width=3)
    return canvas


def main():
    manifest = json.loads((RESULTS / "downloaded_manifest.json").read_text())
    verifications = json.loads((RESULTS / "vlm_verifications.json").read_text())
    ref_dir = HERE / "reference_swatches"

    rows = []
    row_labels = []
    for pid, entry in manifest.items():
        product = entry["product"]
        images = entry["images"]
        ref_path = ref_dir / f"{pid}.jpg"
        tiles = []
        if ref_path.exists():
            tiles.append(make_tile(ref_path, "REFERENCE", (70, 130, 180)))

        v = verifications.get(pid, {})
        vmap = {item["index"]: item for item in v.get("verifications", [])}
        for i, im in enumerate(images, start=2):
            info = vmap.get(i)
            if not info or not info.get("match"):
                continue
            ctx = info.get("context") or "?"
            img_path = HERE / im["file"]
            if not img_path.exists():
                continue
            tiles.append(make_tile(img_path, ctx, (60, 160, 90)))
            if len(tiles) - 1 >= MAX_COLS - 1:
                break

        if len(tiles) <= 1:
            # no verified matches -- still show reference + a "no matches" marker
            pass

        rows.append(tiles)
        n_match = sum(1 for it in vmap.values() if it.get("match"))
        row_labels.append(f"{product['manufacturer']} — {product['name'][:40]} ({n_match} verified)")

    if not rows:
        print("No rows to render.")
        return

    n_cols = max(len(r) for r in rows)
    n_cols = max(n_cols, 1)
    row_label_h = 20
    board_w = n_cols * TILE + PAD * (n_cols + 1)
    board_h = sum(TILE + row_label_h + PAD for _ in rows) + PAD

    board = Image.new("RGB", (board_w, board_h), (245, 245, 245))
    d = ImageDraw.Draw(board)
    font = load_font(13)

    y = PAD
    for tiles, label in zip(rows, row_labels):
        d.text((PAD, y), label, fill=(20, 20, 20), font=font)
        y += row_label_h
        x = PAD
        for tile in tiles:
            board.paste(tile, (x, y))
            x += TILE + PAD
        y += TILE + PAD

    out_path = OUT_DIR / "search_loop_board.jpg"
    board.save(out_path, "JPEG", quality=88)
    print(f"Wrote {out_path} ({board.width}x{board.height})")


if __name__ == "__main__":
    main()
