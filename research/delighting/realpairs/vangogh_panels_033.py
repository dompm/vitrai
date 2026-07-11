#!/usr/bin/env python3
"""Iteration 033 -- Van Gogh-line validation panels for the finished-product
screen (maintainer contamination mode 1, example 186196).

Renders every van-gogh-glass product's downloaded images as one captioned
grid row per product (image_key + gallery index + capture label + screen
flags), a few products per JPEG, downscaled. A human (or the harvesting
agent, multimodally) then labels which cells are finished-product/mosaic
shots; hit rates of the tail-slot and lineup screens against those labels go
into results/vangogh_validation.json and report 033.
"""
import argparse
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw


def img_path(img_root, pid, key):
    if key == "hero":
        return os.path.join(img_root, pid, "hero_full.jpg")
    n = key.split("_")[1]
    return os.path.join(img_root, pid, f"g{n}_full.jpg")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="results/manifest_033.json")
    ap.add_argument("--contamination", default="results/contamination_033.json")
    ap.add_argument("--img-root", default="data/images")
    ap.add_argument("--out-dir", default="results/panels_033")
    ap.add_argument("--brand", default="van-gogh-glass")
    ap.add_argument("--per-sheet", type=int, default=5)
    ap.add_argument("--cell", type=int, default=170)
    args = ap.parse_args()

    products = [p for p in json.load(open(args.manifest))
                if p.get("status") == "done" and p["brand"] == args.brand]
    products.sort(key=lambda p: p["product_id"])
    contam = {}
    if os.path.exists(args.contamination):
        contam = json.load(open(args.contamination)).get("products", {})

    os.makedirs(args.out_dir, exist_ok=True)
    cell, strip = args.cell, 30
    max_cols = max((len(p["images"]) for p in products), default=1)
    sheets = [products[i:i + args.per_sheet] for i in range(0, len(products), args.per_sheet)]
    index = []
    for si, group in enumerate(sheets):
        H = len(group) * (cell + strip + 24)
        W = max_cols * (cell + 4)
        canvas = Image.new("RGB", (W, H), (15, 15, 15))
        d = ImageDraw.Draw(canvas)
        for ri, p in enumerate(group):
            pid = p["product_id"]
            y0 = ri * (cell + strip + 24)
            d.text((4, y0 + 2), f"{pid} {p.get('title','')[:80]}", fill=(255, 230, 120))
            row_index = {"product_id": pid, "title": p.get("title"), "cells": []}
            for ci, im in enumerate(sorted(p["images"], key=lambda r: (r["image_key"] != "hero", r.get("gallery_index") or 0))):
                key = im["image_key"]
                path = img_path(args.img_root, pid, key)
                x0 = ci * (cell + 4)
                flags = []
                if im.get("gallery_index") is not None and im["gallery_index"] >= 6:
                    flags.append("TAIL")
                if key in contam.get(pid, {}).get("images", {}):
                    flags.append("LINEUP")
                cap = f"{key} {im['capture_type']}" + (f" [{','.join(flags)}]" if flags else "")
                d.text((x0 + 2, y0 + 16), cap[:34], fill=(180, 255, 180) if not flags else (255, 140, 140))
                if os.path.exists(path):
                    tile = Image.open(path).convert("RGB").resize((cell, cell), Image.LANCZOS)
                    canvas.paste(tile, (x0, y0 + strip))
                row_index["cells"].append({"image_key": key, "capture_type": im["capture_type"],
                                            "gallery_index": im.get("gallery_index"),
                                            "screen_flags": flags})
            index.append(row_index)
        out_path = os.path.join(args.out_dir, f"vangogh_validation_{si}.jpg")
        canvas.save(out_path, quality=82)
        print(f"wrote {out_path} ({len(group)} products)")
    json.dump(index, open(os.path.join(args.out_dir, "vangogh_validation_index.json"), "w"), indent=1)
    print(f"{len(products)} {args.brand} products -> {len(sheets)} panels")


if __name__ == "__main__":
    main()
