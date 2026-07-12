"""Cheap authored-T preview (no Blender): render each rebuilt streak recipe's
authored T array as sRGB for several seeds, plus its gt_h (sRGB-encoded, the
on-disk GT) as a grayscale strip, so we can eyeball liquidity + h-structure
before committing to a Blender board."""
import sys, types, os
sys.modules["bpy"] = types.ModuleType("bpy")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import numpy as np
from PIL import Image, ImageDraw
import generate_synthetic as gs

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results", "039")


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def main():
    recipes = ["streaky-mix", "streaky-fine-texture", "wispy-white"]
    seeds = [42, 101, 202, 303, 404]
    sz = 220
    pad = 16
    rows = len(recipes) * 2  # T row + h row per recipe
    sheet = Image.new("RGB", (len(seeds) * sz, rows * (sz + pad) + 10), (250, 250, 250))
    d = ImageDraw.Draw(sheet)
    for ri, recipe in enumerate(recipes):
        for si, seed in enumerate(seeds):
            T, h, *_ = gs.author_glass_arrays(recipe, size=sz, seed=seed)
            timg = Image.fromarray((lin_to_srgb(T) * 255).astype(np.uint8))
            himg = Image.fromarray((lin_to_srgb(h) * 255).astype(np.uint8)).convert("RGB")
            yT = (2 * ri) * (sz + pad)
            yH = (2 * ri + 1) * (sz + pad)
            sheet.paste(timg, (si * sz, yT))
            sheet.paste(himg, (si * sz, yH))
            if si == 0:
                d.text((2, yT + 2), f"{recipe} T", fill=(255, 255, 0))
                d.text((2, yH + 2), f"{recipe} gt_h", fill=(255, 0, 0))
    out = os.path.join(RESULTS, "authored_T_preview.jpg")
    sheet.save(out, quality=90)
    print("wrote", out)


if __name__ == "__main__":
    main()
