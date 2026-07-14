"""Report 043 review board: before | after | real-exemplar evidence for the
three landed items (results/043/board_043.jpg).

Row A (item 1, MMv3-G1 scatter PSF): the razor-edge test -- crops of the
  black_metal frame-occluder edge seen through milky wispy-white glass
  (before = origin code; after = item-1 shader, wall held at 5 m so the row
  isolates item 1), the hidden-glass gt_B crop (the physically sharp
  background truth), and the measured 10-90% edge profiles.
Row B (item 2, gt_veil scene fix): gt_veil heatmaps before/after (shader
  held constant -- item-1 state vs item-1+2 state) + the log-binned veil
  histogram. Palette: dataviz reference categorical slots 1-2.
Rows C-F (item 3, exemplar-grounded taxa colors): per taxon
  before-render | after-render | two real corpus exemplars.

Inputs are the /tmp/043_* render dirs produced by the report-043 runs (see
reports/043-mmv3-physics.md sec 7 for the exact invocations).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, DELIGHT)
from extract import load_aov_exr  # noqa: E402

_CANDS = [os.path.join(DELIGHT, "frontend", "public", "assets", "catalog_images"),
          "/Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/catalog_images"]
CATALOG = next(p for p in _CANDS if os.path.isdir(p) and os.listdir(p))

BEFORE = "/tmp/043_before/wispy-white__seed601__light9293"
ITEM1 = "/tmp/043_item1/wispy-white__seed601__light9293"
AFTER = "/tmp/043_after/wispy-white__seed601__light9293"
TAXA_BEFORE = "/tmp/043_taxa_before"
TAXA_AFTER = "/tmp/043_taxa_after"

# dataviz reference palette (used as published): series-1 blue, series-2 aqua
C_BEFORE = "#2a78d6"
C_AFTER = "#1baf7a"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"

TILE = 380
PAD = 14
LABEL_H = 26

EXEMPLARS = {
    "baroque-rolling-wave": ["wissmach-w343g.jpg", "oceanside-of4441w.jpg"],
    "fracture-streamer": ["bullseye-0043250000ffull.jpg", "bullseye-0041180000ffull.jpg"],
    "confetti-shard": ["bullseye-0041100000ffull.jpg", "bullseye-0041110000ffull.jpg"],
    "ring-mottle": ["youghiogheny-yu0074.jpg", "youghiogheny-yu0040.jpg"],
}


def font(sz=15):
    for cand in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.exists(cand):
            try:
                return ImageFont.truetype(cand, sz)
            except Exception:
                pass
    return ImageFont.load_default()


def load_gray(d, name):
    im = cv2.imread(os.path.join(d, name), cv2.IMREAD_UNCHANGED)
    if im is None:
        im = load_aov_exr(os.path.join(d, name))
    if im.ndim == 3:
        im = im[..., :3].mean(-1)
    return im.astype(np.float64)


def find_edge_col(gtB):
    """Median occluder right-edge column over the center rows (row-A crops)."""
    H, W = gtB.shape
    cols = []
    for r in range(int(H * 0.35), int(H * 0.65), 8):
        row = gtB[r]
        dark = row < 0.25 * np.median(row[int(W * 0.6):])
        cc = np.where(dark[:int(W * 0.5)])[0]
        if len(cc) and 10 < cc.max() < W * 0.45:
            cols.append(cc.max())
    return int(np.median(cols))


def edge_profiles(d):
    gtB = load_gray(d, "gt_B.exr")
    ph = load_gray(d, "without_shadow_photo_linear.exr")
    H, W = ph.shape
    profs = []
    for r in range(int(H * 0.35), int(H * 0.65), 8):
        row = gtB[r]
        dark = row < 0.25 * np.median(row[int(W * 0.6):])
        cc = np.where(dark[:int(W * 0.5)])[0]
        if len(cc) == 0:
            continue
        e = cc.max()
        if e < 120 or e > W * 0.45 or e + 120 >= W:
            continue
        profs.append(ph[r, e - 120:e + 120])
    m = np.array(profs).mean(0)
    return (m - m[:40].mean()) / (m[-40:].mean() - m[:40].mean() + 1e-9)


def crop_tile(png_path, cx_frac, cy_frac, half=260):
    im = Image.open(png_path).convert("RGB")
    W, H = im.size
    cx, cy = int(W * cx_frac), int(H * cy_frac)
    box = (max(0, cx - half), max(0, cy - half), min(W, cx + half), min(H, cy + half))
    return im.crop(box).resize((TILE, TILE), Image.LANCZOS)


def crop_tile_exr(exr_path, cx_frac, cy_frac, half=260, ev=0.0):
    im = cv2.imread(exr_path, cv2.IMREAD_UNCHANGED)
    if im is None:
        im = load_aov_exr(exr_path)
    im = im[..., :3][..., ::-1] if im.ndim == 3 else np.stack([im] * 3, -1)
    im = np.clip(im * (2.0 ** ev), 0, 1) ** (1 / 2.2)
    pil = Image.fromarray((im * 255).astype(np.uint8))
    W, H = pil.size
    cx, cy = int(W * cx_frac), int(H * cy_frac)
    box = (max(0, cx - half), max(0, cy - half), min(W, cx + half), min(H, cy + half))
    return pil.crop(box).resize((TILE, TILE), Image.LANCZOS)


def full_tile(path):
    return Image.open(path).convert("RGB").resize((TILE, TILE), Image.LANCZOS)


def fig_to_tile(fig):
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())[..., :3]
    plt.close(fig)
    return Image.fromarray(buf).resize((TILE, TILE), Image.LANCZOS)


def style_ax(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#d8d7d2")
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(True, color="#ecebe7", linewidth=0.8)
    ax.set_axisbelow(True)


def edge_profile_fig():
    fig, ax = plt.subplots(figsize=(4.2, 4.2), dpi=110, facecolor=SURFACE)
    style_ax(ax)
    px = np.arange(-120, 120)
    gb = edge_profiles(BEFORE)
    ga = edge_profiles(ITEM1)
    gt = load_gray(BEFORE, "gt_B.exr")
    e = find_edge_col(gt)
    r0 = gt.shape[0] // 2
    gtp = gt[r0, e - 120:e + 120]
    gtp = (gtp - gtp[:40].mean()) / (gtp[-40:].mean() - gtp[:40].mean() + 1e-9)
    ax.plot(px, gtp, color="#b3b2ac", lw=1.4, ls="--", label="gt_B (sharp truth)")
    ax.plot(px, gb, color=C_BEFORE, lw=2, label="photo before (29 px)")
    ax.plot(px, ga, color=C_AFTER, lw=2, label="photo after, item 1 (58 px)")
    ax.set_xlabel("px from occluder edge", color=INK2, fontsize=9)
    ax.set_ylabel("normalized luminance", color=INK2, fontsize=9)
    ax.set_title("occluder-edge profile through milky glass", color=INK, fontsize=10)
    ax.legend(fontsize=8, frameon=False, labelcolor=INK2, loc="upper left")
    fig.tight_layout()
    return fig_to_tile(fig)


def veil_hist_fig():
    vb = load_aov_exr(os.path.join(ITEM1, "gt_veil.exr")).mean(-1).ravel()
    va = load_aov_exr(os.path.join(AFTER, "gt_veil.exr")).mean(-1).ravel()
    edges = np.array([0, 1e-5, 1e-4, 1e-3, 1e-2, 0.05, 0.1, 0.5, 2.0])
    labels = ["0", "1e-5", "1e-4", "1e-3", "1e-2", ".05", ".1", ".5+"]
    hb = np.histogram(vb, bins=edges)[0] / vb.size * 100
    ha = np.histogram(va, bins=edges)[0] / va.size * 100
    x = np.arange(len(hb))
    fig, ax = plt.subplots(figsize=(4.2, 4.2), dpi=110, facecolor=SURFACE)
    style_ax(ax)
    w = 0.38
    ax.bar(x - w / 2 - 0.01, hb, width=w, color=C_BEFORE, label="before fix (wall 5 m)")
    ax.bar(x + w / 2 + 0.01, ha, width=w, color=C_AFTER, label="after fix (wall 60 m)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel("gt_veil luminance bin (render-linear)", color=INK2, fontsize=9)
    ax.set_ylabel("% of pixels", color=INK2, fontsize=9)
    ax.set_title("gt_veil histogram, --specular OFF", color=INK, fontsize=10)
    ax.legend(fontsize=8, frameon=False, labelcolor=INK2)
    # selective direct labels: the two bins that tell the story
    ax.annotate(f"{hb[-2]:.0f}%", (x[-2] - w / 2 - 0.01, hb[-2] + 1.5), color=INK2,
                fontsize=8, ha="center")
    ax.annotate(f"{ha[0]:.0f}%", (x[0] + w / 2 + 0.01, ha[0] + 1.5), color=INK2,
                fontsize=8, ha="center")
    fig.tight_layout()
    return fig_to_tile(fig)


def veil_heat_tile(d, vmax=0.5):
    v = load_aov_exr(os.path.join(d, "gt_veil.exr")).mean(-1)
    v = np.clip(v / vmax, 0, 1)
    # sequential single-hue ramp (blue, light->dark) per the color formula
    cmap = matplotlib.colormaps["Blues"]
    rgb = (cmap(v)[..., :3] * 255).astype(np.uint8)
    return Image.fromarray(rgb).resize((TILE, TILE), Image.LANCZOS)


def label(draw, x, y, text, f):
    draw.text((x, y), text, fill=INK, font=f)


def main():
    f = font(15)
    fs = font(13)
    rows = []

    # --- Row A: razor edge
    gtB = load_gray(BEFORE, "gt_B.exr")
    e = find_edge_col(gtB)
    cx = e / gtB.shape[1]
    rows.append(("ITEM 1 - scatter PSF razor-edge test (wispy-white seed 601; occluder edge through milky glass)", [
        (crop_tile(os.path.join(BEFORE, "without_shadow_photo.png"), cx, 0.5), "before (origin): edge dimmed, 29 px"),
        (crop_tile(os.path.join(ITEM1, "without_shadow_photo.png"), cx, 0.5), "after (item 1): edge BLURRED, 58 px"),
        (crop_tile_exr(os.path.join(BEFORE, "gt_B.exr"), cx, 0.5), "gt_B hidden-glass truth (1 px sharp)"),
        (edge_profile_fig(), "measured 10-90% edge profiles"),
    ]))

    # --- Row B: veil
    rows.append(("ITEM 2 - gt_veil isolation fix (shader constant; only the DarkWall size changes)", [
        (veil_heat_tile(ITEM1), "gt_veil before (wall 5 m): mean 0.253"),
        (veil_heat_tile(AFTER), "gt_veil after (wall 60 m): mean 0.0004"),
        (veil_hist_fig(), "distribution: 100% -> 24.6% pixels >1e-4"),
    ]))

    # --- Rows C-F: taxa
    for taxon, exes in EXEMPLARS.items():
        tiles = []
        for root, tag in ((TAXA_BEFORE, "before (037 authored guess)"), (TAXA_AFTER, "after (043 exemplar-grounded)")):
            hits = [os.path.join(root, d, "without_shadow_photo.png")
                    for d in sorted(os.listdir(root)) if d.startswith(taxon + "__")] if os.path.isdir(root) else []
            if hits and os.path.exists(hits[0]):
                tiles.append((full_tile(hits[0]), tag))
        for ex in exes:
            p = os.path.join(CATALOG, ex)
            if os.path.exists(p):
                tiles.append((full_tile(p), f"real: {ex[:34]}"))
        rows.append((f"ITEM 3 - {taxon}", tiles))

    ncols = max(len(t) for _, t in rows)
    W = PAD + ncols * (TILE + PAD)
    H = PAD
    for _, tiles in rows:
        H += LABEL_H + TILE + LABEL_H + PAD
    board = Image.new("RGB", (W, H + 40), SURFACE)
    dr = ImageDraw.Draw(board)
    dr.text((PAD, 8), "Report 043 review board -- MMv3 physics upgrade (items 1-3)", fill=INK, font=font(18))
    y = 40
    for title, tiles in rows:
        dr.text((PAD, y), title, fill=INK, font=f)
        y += LABEL_H
        x = PAD
        for tile, cap in tiles:
            board.paste(tile, (x, y))
            dr.text((x, y + TILE + 4), cap, fill=INK2, font=fs)
            x += TILE + PAD
        y += TILE + LABEL_H + PAD
    out = os.path.join(HERE, "board_043.jpg")
    board.save(out, quality=90)
    print("wrote", out, board.size)


if __name__ == "__main__":
    main()
