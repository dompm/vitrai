"""Render a contact sheet of the relief preset bank: for each category, show
the height field, the tangent normal map, and a raking-light shaded preview
(what the relief's glint/shading structure looks like in a photo). Also draws
a 2x2 tile of each height to confirm seamless tiling."""
import os, numpy as np
from PIL import Image, ImageDraw, ImageFont
import relief_presets as RP

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "results", "050"))
os.makedirs(OUT, exist_ok=True)
N = 256


def shade(height, normal, light=(-0.5, -0.6, 0.62)):
    """Simple raking-light + specular preview of the relief surface."""
    L = np.array(light); L = L / np.linalg.norm(L)
    nvec = normal.astype(np.float64) * 2 - 1
    nvec /= np.linalg.norm(nvec, axis=-1, keepdims=True) + 1e-8
    diff = np.clip((nvec * L).sum(-1), 0, 1)
    V = np.array([0, 0, 1.0])
    H = (L + V); H /= np.linalg.norm(H)
    spec = np.clip((nvec * H).sum(-1), 0, 1) ** 40
    img = 0.30 + 0.55 * diff + 0.9 * spec
    return np.clip(img, 0, 1)


def to_img(arr):
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, 2)
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))


def tile2x2(arr):
    return np.block([[arr, arr], [arr, arr]])


def main():
    cats = RP.CATEGORIES
    cell = N
    cols = 4  # height | normal | shaded | 2x2 tiled height
    labels = ["height", "normal", "raking-light shade", "2x2 tile (seamless)"]
    pad, top, left = 8, 26, 130
    W = left + cols * (cell + pad) + pad
    Hh = top + len(cats) * (cell + pad) + pad
    sheet = Image.new("RGB", (W, Hh), (18, 20, 24))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
        fsm = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 11)
    except Exception:
        font = fsm = ImageFont.load_default()
    for j, lab in enumerate(labels):
        d.text((left + j * (cell + pad) + 4, 6), lab, fill=(180, 188, 200), font=fsm)
    for i, c in enumerate(cats):
        y = top + i * (cell + pad) + pad
        p = RP.PRESETS[c]
        d.text((6, y + 4), c, fill=(230, 235, 240), font=font)
        d.text((6, y + 24), p["amp_default"] + "/" + p["scale_default"],
               fill=(150, 160, 172), font=fsm)
        h, amp = RP.make_height(c, size=N, seed=11)
        n, meta = RP.make_normal(c, size=N, seed=11)
        sh = shade(h, n)
        htile = tile2x2(h)[:N, :N]  # crop back to cell but show the seam region
        # show the tiled version downsized to reveal the seam continuity
        htile_full = Image.fromarray((tile2x2(h) * 255).astype(np.uint8)).resize((N, N))
        panels = [to_img(h), to_img(n), to_img(sh), htile_full.convert("RGB")]
        for j, pn in enumerate(panels):
            sheet.paste(pn.resize((cell, cell)), (left + j * (cell + pad) + pad, y))
    path = os.path.join(OUT, "board_preset_bank.jpg")
    sheet.save(path, quality=90)
    print("wrote", path, sheet.size)


if __name__ == "__main__":
    main()
