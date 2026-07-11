#!/usr/bin/env python3
"""Iteration 030 -- build a calibration contact sheet: N random census images
with their heuristic labels, for a human eyeball pass. The human verdicts get
recorded in results/calibration_labels.json and scored by this same script
(--score mode)."""
import argparse
import json
import os
import random

import numpy as np
from PIL import Image, ImageDraw


def build(census_path, img_root, out_img, out_index, n=30, seed=7, cell=180):
    census = json.load(open(census_path))
    pool = []
    for c in census:
        for cl in c["classifications"]:
            key = cl["key"]
            pid = c["product_id"]
            if key == "hero":
                fname = f"{pid}_hero.jpg"
            else:
                idx = key.split("_")[1]
                fname = f"{pid}_{idx}.jpg"
            path = os.path.join(img_root, fname)
            if os.path.exists(path):
                pool.append({"product_id": pid, "key": key, "path": path,
                             "label": cl["label"], "brand": c["brand"]})
    rng = random.Random(seed)
    sample = rng.sample(pool, min(n, len(pool)))
    cols = 6
    rows = (len(sample) + cols - 1) // cols
    strip = 26
    sheet = Image.new("RGB", (cols * cell, rows * (cell + strip)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, s in enumerate(sample):
        x = (i % cols) * cell
        y = (i // cols) * (cell + strip)
        im = Image.open(s["path"]).convert("RGB").resize((cell, cell), Image.LANCZOS)
        sheet.paste(im, (x, y + strip))
        d.text((x + 3, y + 3), f"#{i} {s['label']}", fill=(255, 255, 100))
        d.text((x + 3, y + 14), f"{s['product_id']}/{s['key']}", fill=(180, 180, 180))
    sheet.save(out_img, quality=88)
    json.dump(sample, open(out_index, "w"), indent=1)
    print(f"wrote {out_img} and {out_index} ({len(sample)} tiles)")


def score(index_path, human_path):
    sample = json.load(open(index_path))
    human = json.load(open(human_path))  # {"0": "lightbox", ...}
    n_ok = 0
    confusion = {}
    for i, s in enumerate(sample):
        truth = human.get(str(i))
        if truth is None:
            continue
        pred = s["label"]
        ok = (truth == pred)
        n_ok += ok
        confusion.setdefault((truth, pred), 0)
        confusion[(truth, pred)] += 1
    n = len([i for i in range(len(sample)) if str(i) in human])
    print(f"accuracy: {n_ok}/{n} = {100*n_ok/max(1,n):.1f}%")
    print("confusion (truth -> predicted):")
    for (t, p), c in sorted(confusion.items(), key=lambda kv: -kv[1]):
        mark = "" if t == p else "  <-- miss"
        print(f"  {t:10s} -> {p:10s} {c}{mark}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default="results/census.json")
    ap.add_argument("--img-root", default="/tmp/delphi_census_images")
    ap.add_argument("--out-img", default="/tmp/delphi_cache/calibration_sheet.jpg")
    ap.add_argument("--out-index", default="results/calibration_index.json")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--human", default="results/calibration_labels.json")
    args = ap.parse_args()
    if args.score:
        score(args.out_index, args.human)
    else:
        build(args.census, args.img_root, args.out_img, args.out_index, n=args.n)
