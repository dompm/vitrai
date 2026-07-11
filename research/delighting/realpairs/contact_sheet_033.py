#!/usr/bin/env python3
"""Iteration 033 -- contact sheet of best/worst registrable cross-capture pairs
from the full-scale harvest manifest (results/manifest_033.json).

"Best": highest-inlier registrable cross_capture pairs, not finished-product
tail-slot flagged, not opal/streaky caution -- the cleanest same-region
different-illumination sheet pairs the crawl found.

"Worst/borderline": registrable pairs that are borderline for one of the
three reasons a human reviewer should look at directly -- low inlier count
near the ORB threshold, finished_product_flag (gallery tail slot, may be a
project photo not a sheet), or opal_streaky_caution (sheet identity between
captures is unverified for opal/streaky glass per report 030 SS2.3).

Panels are checkerboard blends (registered B over A) at a small committed
size -- same convention as 030's results/panels/.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from register_pair import orb_register, load_u8, checker_blend  # noqa: E402


def img_path(img_root, pid, key):
    if key == "hero":
        return os.path.join(img_root, pid, "hero_full.jpg")
    n = key.split("_")[1]
    return os.path.join(img_root, pid, f"g{n}_full.jpg")


def make_panel(pa, pb, out_path, label_a, label_b, caption, size=380):
    a = np.asarray(Image.open(pa).convert("RGB").resize((size, size), Image.LANCZOS))
    b = np.asarray(Image.open(pb).convert("RGB").resize((size, size), Image.LANCZOS))
    a_u8 = load_u8(pa, 700)
    b_u8 = load_u8(pb, 700)
    w_ab, i_ab = orb_register(b_u8, a_u8)
    w_ba, i_ba = orb_register(a_u8, b_u8)
    if i_ab >= i_ba and w_ab is not None:
        ref, warped, inl = a_u8, w_ab, i_ab
    elif w_ba is not None:
        ref, warped, inl = b_u8, w_ba, i_ba
    else:
        ref, warped, inl = None, None, max(i_ab, i_ba)
    imgs = [a, b]
    caps = [f"A: {label_a}", f"B: {label_b}"]
    if ref is not None:
        blend = checker_blend(ref, warped)
        blend = np.asarray(Image.fromarray(blend).resize((size, size), Image.LANCZOS))
        imgs.append(blend)
        caps.append(f"checker blend ({inl} inliers)")
    strip_h = 24
    cols = []
    for im, cap in zip(imgs, caps):
        canvas = Image.new("RGB", (size, size + strip_h), (20, 20, 20))
        canvas.paste(Image.fromarray(im), (0, strip_h))
        d = ImageDraw.Draw(canvas)
        d.text((4, 4), cap, fill=(255, 255, 255))
        cols.append(np.asarray(canvas))
    pad = 3
    sheet = np.concatenate([np.pad(c, ((0, 0), (0, pad), (0, 0)), constant_values=8) for c in cols], axis=1)
    top = Image.new("RGB", (sheet.shape[1], 20), (10, 10, 10))
    ImageDraw.Draw(top).text((4, 3), caption[:110], fill=(230, 230, 230))
    out = Image.new("RGB", (sheet.shape[1], sheet.shape[0] + 20))
    out.paste(top, (0, 0))
    out.paste(Image.fromarray(sheet), (0, 20))
    out.save(out_path, quality=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="results/manifest_033.json")
    ap.add_argument("--img-root", default="data/images")
    ap.add_argument("--out-dir", default="results/panels_033")
    ap.add_argument("--n-best", type=int, default=10)
    ap.add_argument("--n-worst", type=int, default=4)
    args = ap.parse_args()

    products = {p["product_id"]: p for p in json.load(open(args.manifest))}
    contam_path = os.path.join(os.path.dirname(args.manifest), "contamination_033.json")
    contam = {}
    if os.path.exists(contam_path):
        contam = json.load(open(contam_path)).get("products", {})
    candidates = []
    for pid, p in products.items():
        for pr in p.get("pairs", []):
            if pr["kind"] != "cross_capture":
                continue
            candidates.append({**pr, "product_id": pid, "brand": p["brand"], "title": p.get("title"),
                                "opal_streaky_caution": p.get("opal_streaky_caution", False)})

    print(f"{len(candidates)} registrable cross_capture pairs across {len(products)} products")

    def suspect_same_photo(c):
        # crop-derivation leak on low-gradient glass (contamination_033 mode 5)
        return c["residual_mad"] is not None and c["residual_mad"] < 15 and c["inliers"] >= 200

    def image_flagged(c):
        rec = contam.get(c["product_id"], {})
        imgs = rec.get("images", {})
        return (c["a"] in imgs or c["b"] in imgs
                or "non_transmissive_mirror" in rec.get("flags", [])
                or "multi_sheet_listing" in rec.get("flags", []))

    clean = [c for c in candidates if not c["finished_product_flag"]
             and not c["opal_streaky_caution"] and not suspect_same_photo(c)
             and not image_flagged(c)]
    clean.sort(key=lambda c: -c["inliers"])
    # at most 2 best-pairs per product, for product variety on the sheet
    best, per_pid = [], {}
    for c in clean:
        if per_pid.get(c["product_id"], 0) >= 2:
            continue
        best.append(c)
        per_pid[c["product_id"]] = per_pid.get(c["product_id"], 0) + 1
        if len(best) >= args.n_best:
            break

    borderline = [c for c in candidates
                  if (c["finished_product_flag"] or c["opal_streaky_caution"] or c["inliers"] < 40)]
    borderline.sort(key=lambda c: c["inliers"])  # lowest-confidence first
    # prefer variety: one from each reason if possible
    worst = []
    seen_reason = set()
    for c in borderline:
        reason = ("finished_product" if c["finished_product_flag"] else
                   "opal_streaky" if c["opal_streaky_caution"] else "low_inliers")
        if reason in seen_reason and len(worst) < args.n_worst:
            continue
        worst.append(c)
        seen_reason.add(reason)
        if len(worst) >= args.n_worst:
            break
    if len(worst) < args.n_worst:
        for c in borderline:
            if c not in worst:
                worst.append(c)
            if len(worst) >= args.n_worst:
                break

    os.makedirs(args.out_dir, exist_ok=True)
    manifest_out = {"best": [], "worst": []}
    for tag, group in [("best", best), ("worst", worst)]:
        for i, c in enumerate(group):
            pid = c["product_id"]
            pa = img_path(args.img_root, pid, c["a"])
            pb = img_path(args.img_root, pid, c["b"])
            if not (os.path.exists(pa) and os.path.exists(pb)):
                continue
            out_path = os.path.join(args.out_dir, f"{tag}_{i+1:02d}_{pid}.jpg")
            reason = []
            if c["finished_product_flag"]:
                reason.append("finished_product_flag")
            if c["opal_streaky_caution"]:
                reason.append("opal_streaky_caution")
            if c["inliers"] < 40:
                reason.append(f"low_inliers={c['inliers']}")
            caption = (f"{pid} {c['brand']} \"{c['title']}\" -- {c['a']}({c['capture_type_a']}) x "
                       f"{c['b']}({c['capture_type_b']}) inliers={c['inliers']} mad={c['residual_mad']:.1f} "
                       + (f"[{', '.join(reason)}]" if reason else ""))
            print(f"{tag} #{i+1}: {caption}")
            make_panel(pa, pb, out_path, c["capture_type_a"], c["capture_type_b"], caption)
            manifest_out[tag].append({"panel": out_path, "product_id": pid, "brand": c["brand"],
                                       "title": c["title"], "pair": [c["a"], c["b"]],
                                       "capture_types": [c["capture_type_a"], c["capture_type_b"]],
                                       "inliers": c["inliers"], "residual_mad": c["residual_mad"],
                                       "flags": reason})
    json.dump(manifest_out, open(os.path.join(args.out_dir, "index.json"), "w"), indent=1)
    print(f"wrote {len(manifest_out['best'])} best + {len(manifest_out['worst'])} worst panels to {args.out_dir}")


if __name__ == "__main__":
    main()
