#!/usr/bin/env python3
"""Iteration 044 -- visual boards for the coglassworks pair harvest.

Two modes:
  --mode pairs      the deliverable sample board (~10 verified pairs, one row
                    per pair: photo A | photo B, captioned with token, tier,
                    capture labels). Written to
                    ../results/044/coglass_pairs_board.jpg (downscaled,
                    committed; captioned as Colorado Glass Works' photography
                    -- report 041 SS7 posture).
  --mode handcheck  grouper-precision hand-check sheets: N sampled listings,
                    one row per listing, images ordered by grouper assignment
                    with the token printed above each thumb and a color bar
                    per token group. A human (or VLM) then checks each row:
                    do all images under one token show the same physical
                    piece (sticker text, shard shape, size)?
"""
import argparse
import json
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_ROOT = os.path.join(HERE, "data", "images")
PAIRS = os.path.join(HERE, "results", "pairs_044.json")
CENSUS = os.path.join(HERE, "results", "census_044.json")

THUMB = 300
GROUP_COLORS = [(214, 69, 65), (65, 131, 215), (38, 166, 91), (244, 179, 80),
                (155, 89, 182), (52, 73, 94)]


def font(size=16):
    for cand in ("/System/Library/Fonts/Helvetica.ttc",
                 "/System/Library/Fonts/Supplemental/Arial.ttf"):
        if os.path.exists(cand):
            return ImageFont.truetype(cand, size)
    return ImageFont.load_default()


def thumb(path, size=THUMB):
    im = Image.open(path).convert("RGB")
    im.thumbnail((size, size))
    canvas = Image.new("RGB", (size, size), (24, 24, 24))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return canvas


def mode_pairs(args):
    with open(PAIRS) as f:
        data = json.load(f)
    rng = random.Random(args.seed)
    cross = [p for p in data["pairs"]
             if p["pair_class"] == "cross_condition"
             and p["tier"] in ("variant", "handle")]
    same = [p for p in data["pairs"]
            if p["pair_class"] == "same_condition"
            and p["tier"] in ("variant", "handle")]
    # one pair per piece token for variety
    chosen, seen = [], set()
    for pool, want in ((cross, args.n // 2), (same, args.n)):
        rng.shuffle(pool)
        for p in pool:
            if len(chosen) >= min(args.n, want + len(chosen)) and pool is cross:
                break
            if len(chosen) >= args.n:
                break
            if p["token"] in seen:
                continue
            pa = os.path.join(IMG_ROOT, p["handle"], p["a"])
            pb = os.path.join(IMG_ROOT, p["handle"], p["b"])
            if os.path.exists(pa) and os.path.exists(pb):
                seen.add(p["token"])
                chosen.append(p)
    chosen = chosen[:args.n]

    f_cap = font(15)
    f_head = font(20)
    pad, caph = 8, 44
    W = 2 * (THUMB + pad) + pad
    H = 70 + len(chosen) * (THUMB + caph + pad)
    board = Image.new("RGB", (W, H), (16, 16, 16))
    d = ImageDraw.Draw(board)
    d.text((pad, 8), "coglassworks.com same-piece pairs (iteration 044)", font=f_head,
           fill=(235, 235, 235))
    d.text((pad, 36), "photography (c) Colorado Glass Works -- research eval only, "
           "downscaled", font=f_cap, fill=(160, 160, 160))
    y = 70
    for p in chosen:
        for k, key in enumerate(("a", "b")):
            t = thumb(os.path.join(IMG_ROOT, p["handle"], p[key]))
            board.paste(t, (pad + k * (THUMB + pad), y))
        cap1 = f"{p['token']}  [{p['tier']}]  {p['pair_class']}"
        cap2 = f"{p['a']} ({p['capture_a']})  x  {p['b']} ({p['capture_b']})"
        d.text((pad, y + THUMB + 4), cap1, font=f_cap, fill=(235, 220, 160))
        d.text((pad, y + THUMB + 23), cap2, font=f_cap, fill=(170, 170, 170))
        y += THUMB + caph + pad
    out = os.path.abspath(os.path.join(HERE, "..", "results", "044",
                                       "coglass_pairs_board.jpg"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    board.save(out, quality=78)
    print(f"wrote {out} ({len(chosen)} pairs)")


def mode_handcheck(args):
    with open(CENSUS) as f:
        census = json.load(f)
    rng = random.Random(args.seed)
    listings = [p for p in census["products"]
                if p["grouper"]["bucket"] in
                ("multi_piece_sku_named", "single_piece_sku_named", "mixed_convention")]
    sample = rng.sample(listings, min(args.n, len(listings)))
    f_cap = font(14)
    f_tok = font(18)
    per_sheet = args.per_sheet
    sheets = [sample[i:i + per_sheet] for i in range(0, len(sample), per_sheet)]
    outdir = os.path.join(HERE, "results", "handcheck_044")
    os.makedirs(outdir, exist_ok=True)
    index = []
    for si, sheet in enumerate(sheets):
        maxcols = max(sum(len(v) for v in p["grouper"]["groups"].values())
                      for p in sheet)
        W = 30 + maxcols * (THUMB + 8)
        H = len(sheet) * (THUMB + 66)
        img = Image.new("RGB", (W, H), (16, 16, 16))
        d = ImageDraw.Draw(img)
        for ri, p in enumerate(sheet):
            y = ri * (THUMB + 66)
            d.text((8, y + 4), p["handle"], font=f_cap, fill=(160, 160, 160))
            x = 8
            row = {"handle": p["handle"], "groups": {}}
            for gi, (token, files) in enumerate(sorted(p["grouper"]["groups"].items())):
                color = GROUP_COLORS[gi % len(GROUP_COLORS)]
                row["groups"][token] = files
                for base in files:
                    path = os.path.join(IMG_ROOT, p["handle"], base)
                    if not os.path.exists(path):
                        continue
                    t = thumb(path)
                    img.paste(t, (x, y + 44))
                    d.rectangle([x, y + 36, x + THUMB, y + 43], fill=color)
                    d.text((x, y + 18), f"{token} [{p['grouper']['tiers'][token]}]",
                           font=f_tok, fill=color)
                    x += THUMB + 8
            index.append(row)
        out = os.path.join(outdir, f"handcheck_sheet_{si}.jpg")
        img.save(out, quality=70)
        print(f"wrote {out} ({len(sheet)} listings)")
    with open(os.path.join(outdir, "handcheck_index.json"), "w") as f:
        json.dump(index, f, indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["pairs", "handcheck"], required=True)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--per-sheet", type=int, default=5)
    ap.add_argument("--seed", type=int, default=44)
    args = ap.parse_args()
    if args.mode == "pairs":
        mode_pairs(args)
    else:
        mode_handcheck(args)
