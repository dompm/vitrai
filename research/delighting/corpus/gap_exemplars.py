#!/usr/bin/env python3
"""Task D support (report 021): for each of the coverage gaps identified by
appearance_stats.py (recipe hue/texture regions that are under-represented
vs the real backlit-verified corpus), find the nearest REAL swatches to a
proposed gap centroid (in L*, C*, hue-circular distance, optionally gated
by a minimum high-frequency-texture threshold), and render a labeled
contact sheet -- these are the "nearest real swatch to the gap" exemplars
a new synthetic recipe should be grounded against.

Usage: python3 gap_exemplars.py
"""
import json
import os
import collections

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CATALOG_DIR = os.path.join(REPO_ROOT, "frontend", "public", "assets", "catalog_images")
RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")

APPEARANCE = json.load(open(os.path.join(RESULTS_DIR, "appearance_stats.json")))
CLEAN = json.load(open(os.path.join(RESULTS_DIR, "clean_manifest.json")))["images"]
CLASS_BY_FILE = {im["file"]: im["extractor_class"] for im in CLEAN}
MFR_BY_FILE = {im["file"]: im["manufacturer"] for im in CLEAN}

# --- gap centroid definitions (report 021 Sec C) ---------------------------
GAPS = [
    {
        "name": "cathedral-blue",
        "why": "Cathedral-clear recipes cover only green (h~146deg) and amber (h~84deg); "
               "real cathedral-clear spans a chroma-weighted hue range of ~32-331deg (nearly "
               "the whole wheel) -- blue cathedral glass (a real, common Bullseye/Youghiogheny "
               "product line) has zero synthetic representation.",
        "cls": "cathedral-clear", "target_L": 45, "target_C": 45, "target_hue": 255,
        "min_C": 20,
    },
    {
        "name": "cathedral-red",
        "why": "Same recipe-hue gap as above, opposite side of the wheel: no red/ruby "
               "cathedral-clear recipe (existing dark-ruby is the dark-opaque family, "
               "h_haze~0.20, not a clear transmissive red).",
        "cls": "cathedral-clear", "target_L": 45, "target_C": 55, "target_hue": 10,
        "min_C": 20,
    },
    {
        "name": "saturated-opalescent",
        "why": "No recipe combines high haze (h>=0.5) with real chroma: wispy-white is the "
               "only high-haze recipe and it is near-neutral (C~2). Real opalescent glass "
               "(a whole extractor class, ~21% of the clean corpus) is milky AND colorful "
               "(median C~32, up to 83) -- entirely unrepresented as a haze x chroma combo.",
        "cls": "opalescent", "target_L": 60, "target_C": 45, "target_hue": 340,
        "min_C": 25,
    },
    {
        "name": "streaky-fine-texture",
        "why": "streaky-mix's hf_energy_frac (0.0016) is far below real wispy's median "
               "(0.0166) and its p95 (0.0734) -- real streaky/marbled glass has much finer, "
               "sharper-edged mixing than the cubic-interpolated blend mask the recipe uses "
               "(this is also 015 Sec3's #3 failure mode: the extractor loses structure on "
               "exactly this kind of real glass). Also only one hue pair (white/blue) exists; "
               "picking a high-hf, warm-hue exemplar covers both gaps at once.",
        "cls": "wispy", "target_L": 55, "target_C": 40, "target_hue": 30,
        "min_hf": 0.03,
    },
    {
        "name": "dark-textured",
        "why": "All 4 dark recipes use the same near-flat T-noise (hf_energy_frac~0.0016); "
               "real dark-opaque's hf median is 0.11, with several images (mostly Bullseye "
               "black-opalescent) above 0.3 -- clear surface structure visible through "
               "near-black glass that no dark recipe currently has any T-space texture for.",
        "cls": "dark-opaque", "target_L": 15, "target_C": 5, "target_hue": 200,
        "min_hf": 0.2,
    },
]


def hue_circular_dist(h1, h2):
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)


def nearest_exemplars(gap, k=3):
    rows = [v for v in APPEARANCE["real_per_image"].values()
            if CLASS_BY_FILE.get(v["file"]) == gap["cls"]]
    if gap.get("min_C"):
        rows = [r for r in rows if r["C_median"] >= gap["min_C"]]
    if gap.get("min_hf"):
        rows = [r for r in rows if r["hf_energy_frac"] >= gap["min_hf"]]
    if not rows:
        return []
    def dist(r):
        dL = (r["L_median"] - gap["target_L"]) / 40.0
        dC = (r["C_median"] - gap["target_C"]) / 40.0
        dh = hue_circular_dist(r["hue_deg"], gap["target_hue"]) / 90.0
        return dL ** 2 + dC ** 2 + dh ** 2
    rows.sort(key=dist)
    return rows[:k]


def build_contact_sheet(all_picks, out_path, tile=180):
    tiles = []
    for gap_name, picks in all_picks:
        for r in picks:
            f = r["file"]
            path = os.path.join(CATALOG_DIR, f)
            im = Image.open(path).convert("RGB")
            s = tile / max(im.size)
            im = im.resize((max(1, int(im.size[0] * s)), max(1, int(im.size[1] * s))), Image.LANCZOS)
            canvas = Image.new("RGB", (tile, tile + 46), (18, 18, 18))
            canvas.paste(im, ((tile - im.size[0]) // 2, (tile - im.size[1]) // 2))
            d = ImageDraw.Draw(canvas)
            d.text((2, tile + 1), gap_name, fill=(255, 220, 120))
            d.text((2, tile + 13), f"{MFR_BY_FILE.get(f,'?')[:10]}", fill=(180, 220, 255))
            d.text((2, tile + 25), f"L{r['L_median']:.0f} C{r['C_median']:.0f} h{r['hue_deg']:.0f}", fill=(200, 200, 200))
            d.text((2, tile + 35), f"hf{r['hf_energy_frac']:.3f}", fill=(200, 200, 200))
            tiles.append(np.asarray(canvas))
    cols = max(len(picks) for _, picks in all_picks)
    rows_imgs = []
    idx = 0
    for gap_name, picks in all_picks:
        row_tiles = tiles[idx: idx + len(picks)]
        idx += len(picks)
        while len(row_tiles) < cols:
            row_tiles.append(np.full_like(row_tiles[0], 18))
        rows_imgs.append(np.concatenate(row_tiles, axis=1))
    sheet = np.concatenate(rows_imgs, axis=0)
    Image.fromarray(sheet).save(out_path, quality=90)
    print("wrote", out_path, sheet.shape)


def main():
    all_picks = []
    out = {}
    for gap in GAPS:
        picks = nearest_exemplars(gap)
        all_picks.append((gap["name"], picks))
        out[gap["name"]] = {
            "why": gap["why"],
            "target": {"L": gap["target_L"], "C": gap["target_C"], "hue_deg": gap["target_hue"]},
            "cls": gap["cls"],
            "nearest_real_exemplars": [
                {"file": r["file"], "manufacturer": MFR_BY_FILE.get(r["file"]),
                 "L_median": r["L_median"], "C_median": r["C_median"],
                 "hue_deg": r["hue_deg"], "hf_energy_frac": r["hf_energy_frac"]}
                for r in picks
            ],
        }
        print(f"\n=== gap: {gap['name']} ===")
        for r in picks:
            print(f"  {r['file']:35s} {MFR_BY_FILE.get(r['file']):14s} "
                  f"L={r['L_median']:.1f} C={r['C_median']:.1f} hue={r['hue_deg']:.0f} hf={r['hf_energy_frac']:.4f}")

    with open(os.path.join(RESULTS_DIR, "gap_exemplars.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"\nwrote {os.path.join(RESULTS_DIR, 'gap_exemplars.json')}")

    build_contact_sheet(all_picks, os.path.join(RESULTS_DIR, "gap_exemplars_contact_sheet.jpg"))


if __name__ == "__main__":
    main()
