"""Report 039 review board: real exemplar crops | our rendered crops, per streak
sub-family. THE maintainer gate. Reads board_renders/*/without_shadow_photo.png
(mid-EV, mark-free) and matched real corpus sheets."""
import os
import glob
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.abspath(os.path.join(HERE, "..", ".."))
_CANDS = [os.path.join(DELIGHT, "frontend", "public", "assets", "catalog_images"),
          "/Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/catalog_images"]
CATALOG = next(p for p in _CANDS if os.path.isdir(p) and os.listdir(p))
RENDERS = os.path.join(HERE, "board_renders")

# (recipe, [real exemplar files representing the same sub-family])
FAMILIES = [
    ("streaky-mix", "saturated white-on-color", [
        "oceanside-of83896s.jpg", "oceanside-of3591s.jpg", "oceanside-ofr72.jpg"]),
    ("streaky-fine-texture", "marbled single-hue", [
        "wissmach-w145sp.jpg", "oceanside-of31902s.jpg", "wissmach-w701ll.jpg"]),
    ("wispy-white", "subtle milky", [
        "bullseye-0004200030f1010.jpg", "oceanside-of309s.jpg", "oceanside-of3291s.jpg"]),
]
TILE = 240


def center_crop(im, frac=0.62):
    w, h = im.size
    s = int(min(w, h) * frac)
    return im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((TILE, TILE), Image.LANCZOS)


def ours_crops(recipe):
    out = []
    for d in sorted(glob.glob(os.path.join(RENDERS, f"{recipe}__*"))):
        p = os.path.join(d, "without_shadow_photo.png")
        if os.path.exists(p):
            out.append(center_crop(Image.open(p).convert("RGB")))
    return out[:3]


def main():
    lab = 22
    div = 16
    rows = len(FAMILIES)
    W = 3 * TILE + div + 3 * TILE
    H = rows * (TILE + lab) + 30
    board = Image.new("RGB", (W, H), (250, 250, 250))
    d = ImageDraw.Draw(board)
    d.text((6, 6), "REAL corpus exemplars", fill=(0, 0, 0))
    d.text((3 * TILE + div + 6, 6), "OUR rebuilt render (mid-EV, mark-free)", fill=(0, 0, 0))
    for ri, (recipe, desc, reals) in enumerate(FAMILIES):
        y = 24 + ri * (TILE + lab)
        for ci, fn in enumerate(reals):
            p = os.path.join(CATALOG, fn)
            if os.path.exists(p):
                board.paste(center_crop(Image.open(p).convert("RGB")), (ci * TILE, y))
        for ci, crop in enumerate(ours_crops(recipe)):
            board.paste(crop, (3 * TILE + div + ci * TILE, y))
        d.text((6, y + TILE + 3), f"{recipe}  ({desc})", fill=(20, 20, 20))
    out = os.path.join(HERE, "review_board_039.jpg")
    board.save(out, quality=90)
    print("wrote", out)


if __name__ == "__main__":
    main()
