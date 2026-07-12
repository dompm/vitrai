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


def _autoexpose_photo(sample_dir):
    """Camera-style auto-exposure from the LINEAR render: scale so the median
    luminance lands at 0.18 (photographic mid-gray), then sRGB-encode. The
    generator's fixed EV meets HDRIs of wildly different brightness, so raw
    photo.png exposure is a lottery (the maintainer's dim rejected samples,
    and blown-out bright ones alike); a real product photographer's camera
    auto-exposes. Falls back to photo.png if the EXR is unreadable."""
    exr = os.path.join(sample_dir, "without_shadow_photo_linear.exr")
    png = os.path.join(sample_dir, "without_shadow_photo.png")
    try:
        os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
        import cv2
        a = cv2.imread(exr, cv2.IMREAD_UNCHANGED)
        a = cv2.cvtColor(a[..., :3].astype(np.float32), cv2.COLOR_BGR2RGB)
        lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        med = float(np.median(lum))
        a = a * (0.18 / max(med, 1e-6))
        a = np.clip(a, 0, 1)
        srgb = np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)
        return Image.fromarray((srgb * 255).astype(np.uint8))
    except Exception:
        return Image.open(png).convert("RGB")


def ours_crops(recipe):
    """[(photo_crop, gt_h_thumb_or_None), ...] per rendered sample."""
    out = []
    for d in sorted(glob.glob(os.path.join(RENDERS, f"{recipe}__*"))):
        p = os.path.join(d, "without_shadow_photo.png")
        hp = os.path.join(d, "gt_h.png")
        if os.path.exists(p):
            hthumb = None
            if os.path.exists(hp):
                ha = np.asarray(Image.open(hp))
                if ha.dtype == np.uint16:  # Blender writes 16-bit grayscale PNGs
                    ha = (ha / 257.0).astype(np.uint8)
                hthumb = center_crop(Image.fromarray(ha).convert("RGB")).resize(
                    (TILE, TILE // 3), Image.LANCZOS)
            out.append((center_crop(_autoexpose_photo(d)), hthumb))
    return out[:3]


def main():
    lab = 22
    div = 16
    hstrip = TILE // 3 + 4  # rendered-gt_h thumb strip under each of our tiles
    rows = len(FAMILIES)
    W = 3 * TILE + div + 3 * TILE
    H = rows * (TILE + hstrip + lab) + 30
    board = Image.new("RGB", (W, H), (250, 250, 250))
    d = ImageDraw.Draw(board)
    d.text((6, 6), "REAL corpus exemplars", fill=(0, 0, 0))
    d.text((3 * TILE + div + 6, 6),
           "OUR rebuilt render (auto-exposed, mark-free); strip below = rendered gt_h", fill=(0, 0, 0))
    for ri, (recipe, desc, reals) in enumerate(FAMILIES):
        y = 24 + ri * (TILE + hstrip + lab)
        for ci, fn in enumerate(reals):
            p = os.path.join(CATALOG, fn)
            if os.path.exists(p):
                board.paste(center_crop(Image.open(p).convert("RGB")), (ci * TILE, y))
        for ci, (crop, hthumb) in enumerate(ours_crops(recipe)):
            x = 3 * TILE + div + ci * TILE
            board.paste(crop, (x, y))
            if hthumb is not None:
                board.paste(hthumb, (x, y + TILE + 2))
        d.text((6, y + TILE + hstrip + 3), f"{recipe}  ({desc})", fill=(20, 20, 20))
    out = os.path.join(HERE, "review_board_039.jpg")
    board.save(out, quality=90)
    print("wrote", out)


if __name__ == "__main__":
    main()
