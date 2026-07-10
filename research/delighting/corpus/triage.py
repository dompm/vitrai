#!/usr/bin/env python3
"""Task 2: LIGHTING-GEOMETRY TRIAGE (critical).

The extractor's T,h semantics (extract.py docstring: L(x) backlight
illumination field, B(x) background seen THROUGH the glass) only apply to
BACKLIT photos (glass held/mounted against a light source or light table).
Catalog swatch photos could instead be FRONT-LIT product shots (glass lying
on a table/background, lit by room/studio light from the camera side) -- in
that regime there is no "light passing through onto a background", transmit-
tance can't be read off the pixels the same way, and running the extractor
would silently produce numbers that don't mean what report 003/009 assume
they mean.

This script computes cheap per-image luminance/vignette/specular heuristics
for a stratified sample (see sample_utils.py) and renders a labeled contact
sheet for human (eyes-on) inspection. It does NOT itself decide backlit vs
front-lit with certainty -- ambiguous cases need the human verdict, which is
recorded by hand in reports/015-corpus.md after looking at the sheet this
script produces.

Heuristics (all on sRGB [0,1], no color management):
  mean_lum, std_lum        overall exposure + contrast
  p01, p99                 tail probes: p99 close to 1.0 with a heavy right
                           tail suggests a bright, glowing backlit look;
                           front-lit product shots on a shot table tend to
                           have a lower, more centered p99
  corner_center_ratio      mean luminance of the 4 image corners / mean
                           luminance of the center 40%. A light-TABLE backlit
                           shot cropped to the glass tends to be closer to 1
                           (uniform glow edge-to-edge, or falls off smoothly);
                           a front-lit swatch-on-background shot has a sharp
                           discontinuity at the glass edge which usually
                           reads as ratio far from 1 (background flat white/
                           grey vs a colored, non-flat glass center)
  specular_frac            fraction of pixels > 0.93 luminance forming small
                           high-local-contrast blobs (top-hat) -- a proxy for
                           front-surface sheen, which implies a reflected
                           (front) light source rather than pure transmission
  dark_edge_frac           fraction of the outer 10% border below 0.15
                           luminance -- a dark surround (light table framed
                           by its own housing / studio dark-field) is a
                           positive backlit signal specific to light-table
                           rigs
  sat_mean                 mean HSV saturation -- transmissive backlit glass
                           usually reads highly saturated/jewel-toned; flat
                           front lighting on opal/white-ish glass reads
                           desaturated

Usage: python3 triage.py [--n 100] [--out-json ...] [--out-sheet ...]
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sample_utils import CATALOG_DIR, stratified_sample  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LUM = np.array([0.2126, 0.7152, 0.0722])


def load_srgb01(path, max_dim=300):
    im = Image.open(path).convert("RGB")
    s = max_dim / max(im.size)
    if s < 1:
        im = im.resize((max(1, int(im.size[0] * s)), max(1, int(im.size[1] * s))), Image.LANCZOS)
    return np.asarray(im).astype(np.float64) / 255.0


def heuristics(rgb):
    h, w, _ = rgb.shape
    lum = rgb @ LUM
    mean_lum, std_lum = float(lum.mean()), float(lum.std())
    p01, p99 = float(np.percentile(lum, 1)), float(np.percentile(lum, 99))

    b = max(1, int(0.1 * min(h, w)))
    border_mask = np.zeros((h, w), bool)
    border_mask[:b, :] = border_mask[-b:, :] = True
    border_mask[:, :b] = border_mask[:, -b:] = True
    ch, cw = int(0.3 * h), int(0.3 * w)
    center = lum[ch:h - ch, cw:w - cw]
    corner_center_ratio = float(lum[border_mask].mean() / (center.mean() + 1e-6))
    dark_edge_frac = float((lum[border_mask] < 0.15).mean())

    gray8 = (lum * 255).astype(np.uint8)
    tophat = cv2.morphologyEx(gray8, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    specular_frac = float(((tophat > 40) & (gray8 > 235)).mean())

    hsv = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2HSV)
    sat_mean = float(hsv[..., 1].mean() / 255.0)

    return {
        "mean_lum": round(mean_lum, 4), "std_lum": round(std_lum, 4),
        "p01": round(p01, 4), "p99": round(p99, 4),
        "corner_center_ratio": round(corner_center_ratio, 4),
        "dark_edge_frac": round(dark_edge_frac, 4),
        "specular_frac": round(specular_frac, 5),
        "sat_mean": round(sat_mean, 4),
    }


def auto_verdict(m):
    """A best-effort automatic rule, reported alongside (not instead of) the
    human contact-sheet read. Backlit-leaning if bright with a glowing tail
    and low specular sheen; front-lit-leaning if higher sheen / harder edge
    discontinuity / lower p99."""
    score = 0
    score += 1 if m["p99"] > 0.92 else -1
    score += 1 if m["specular_frac"] < 0.004 else -1
    score += 1 if 0.85 < m["corner_center_ratio"] < 1.2 else -1
    score += 1 if m["sat_mean"] > 0.25 else 0
    return "backlit" if score >= 1 else "front-lit"


def build_contact_sheet(sample, metrics, out_path, tile=140, cols=10):
    tiles = []
    for item, m in zip(sample, metrics):
        path = os.path.join(CATALOG_DIR, item["file"])
        im = Image.open(path).convert("RGB")
        s = tile / max(im.size)
        im = im.resize((max(1, int(im.size[0] * s)), max(1, int(im.size[1] * s))), Image.LANCZOS)
        canvas = Image.new("RGB", (tile, tile + 34), (20, 20, 20))
        canvas.paste(im, ((tile - im.size[0]) // 2, (tile - im.size[1]) // 2))
        d = ImageDraw.Draw(canvas)
        label = f"{item['manufacturer'][:4]}/{str(item['extractor_class'])[:8]}"
        verdict = auto_verdict(m)
        d.text((2, tile + 1), label, fill=(255, 255, 120))
        d.text((2, tile + 12), f"p99{m['p99']:.2f} sp{m['specular_frac']:.3f}", fill=(160, 220, 255))
        color = (120, 255, 140) if verdict == "backlit" else (255, 140, 120)
        d.text((2, tile + 23), verdict, fill=color)
        tiles.append(np.asarray(canvas))

    rows = []
    for i in range(0, len(tiles), cols):
        row_tiles = tiles[i:i + cols]
        while len(row_tiles) < cols:
            row_tiles.append(np.full_like(row_tiles[0], 20))
        rows.append(np.concatenate(row_tiles, axis=1))
    sheet = np.concatenate(rows, axis=0)
    Image.fromarray(sheet).save(out_path, quality=88)
    print("wrote", out_path, sheet.shape)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out-json", default=os.path.join(HERE, "..", "results", "corpus", "triage_sample.json"))
    ap.add_argument("--out-sheet", default=os.path.join(HERE, "..", "results", "corpus", "triage_contact_sheet.jpg"))
    args = ap.parse_args()

    sample = stratified_sample(args.n)
    metrics = []
    for item in sample:
        rgb = load_srgb01(os.path.join(CATALOG_DIR, item["file"]))
        m = heuristics(rgb)
        m["auto_verdict"] = auto_verdict(m)
        metrics.append(m)

    records = [{**item, **m} for item, m in zip(sample, metrics)]
    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    with open(args.out_json, "w") as fh:
        json.dump(records, fh, indent=1)
    print("wrote", args.out_json)

    build_contact_sheet(sample, metrics, args.out_sheet)

    import collections
    print("\n=== per-manufacturer automatic verdict tally ===")
    tally = collections.Counter((r["manufacturer"], r["auto_verdict"]) for r in records)
    for k, v in sorted(tally.items()):
        print(k, v)
    print("\n=== per-manufacturer mean heuristics ===")
    by_mfr = collections.defaultdict(list)
    for r in records:
        by_mfr[r["manufacturer"]].append(r)
    for mfr, rs in sorted(by_mfr.items()):
        n = len(rs)
        print(f"{mfr:14s} n={n:3d} mean_lum={np.mean([r['mean_lum'] for r in rs]):.3f} "
              f"p99={np.mean([r['p99'] for r in rs]):.3f} "
              f"specular={np.mean([r['specular_frac'] for r in rs]):.4f} "
              f"corner/center={np.mean([r['corner_center_ratio'] for r in rs]):.3f} "
              f"sat={np.mean([r['sat_mean'] for r in rs]):.3f}")


if __name__ == "__main__":
    main()
