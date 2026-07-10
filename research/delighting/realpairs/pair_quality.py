#!/usr/bin/env python3
"""Iteration 030 task 2 -- pair-quality check on hand-picked multi-capture products.

For each hand-picked product (chosen from the census for having >=2 distinct
capture types and a decent image count), downloads the FULL-resolution image
set (1500x1500), classifies each image with classify.py's heuristic (rerun at
full res, which the calibration step showed is materially more reliable than
the 70x55 census thumb -- see report), picks the most informative pair
(prefer a clean `lightbox` reference against the most different other
capture), and checks registrability the same way `register_pair.py` does:
ORB + RANSAC homography, both directions, keep the better one.

Verdict per pair:
  registrable        -- >= ORB_INLIER_THRESH inliers: same visible region,
                         can be pixel-aligned (the strong case: true
                         cross-capture ground truth for that sub-region).
  same-sheet-diff-region -- ORB fails (too few / no inliers) but the two
                         images plainly show the same physical sheet pattern
                         (same streak/granite/hue layout) at a different
                         crop/zoom -- statistics-only pairing.
  uncertain / different -- eyeballed and flagged; documented, not silently
                         dropped.

Writes results/panels/<product_id>_pair.jpg (downscaled, committed) and
results/pair_quality.json (verdicts + ORB inlier counts).
"""
import argparse
import json
import os
import sys
import time
import urllib.request

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from classify import analyze_image, classify, UA  # noqa: E402
from register_pair import orb_register, load_u8, checker_blend  # noqa: E402

HERO_FULL_URL = "https://images.delphiglass.com/image_1500/{id}.jpg"
GALLERY_FULL_URL = "https://www.delphiglass.com/syscat/image_add/{id}_{n}0.jpg"

ORB_INLIER_THRESH = 20


def fetch(url, dest, retries=3):
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return True
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if len(data) < 1000:
                return False
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "wb").write(data)
            return True
        except Exception:
            time.sleep(1.2 * (attempt + 1))
    return False


def download_full_set(entry, img_root, sleep_s=1.0):
    pid = entry["product_id"]
    out = []
    hero_path = os.path.join(img_root, f"{pid}_hero_full.jpg")
    if fetch(HERO_FULL_URL.format(id=pid), hero_path):
        out.append(("hero", hero_path))
    time.sleep(sleep_s)
    for g in entry.get("gallery", []):
        n = g["index"]
        gpid = g["product_id"]
        p = os.path.join(img_root, f"{gpid}_{n}_full.jpg")
        if fetch(GALLERY_FULL_URL.format(id=gpid, n=n), p):
            out.append((f"gallery_{n}", p))
        time.sleep(sleep_s)
    return out


PRIORITY = ["lightbox", "window", "shop_held", "standing", "closeup", "other"]


def pick_pair(labeled):
    """labeled: list of (key, path, label). Prefer lightbox vs the most
    'different' other label; else any two distinct labels; else first two."""
    by_label = {}
    for k, p, l in labeled:
        by_label.setdefault(l, []).append((k, p))
    if "lightbox" in by_label:
        a = by_label["lightbox"][0]
        for pref in ["window", "shop_held", "standing", "closeup", "other"]:
            if pref in by_label:
                return ("lightbox", a[0], a[1]), (pref, by_label[pref][0][0], by_label[pref][0][1])
    labels_present = list(by_label.keys())
    if len(labels_present) >= 2:
        la, lb = labels_present[0], labels_present[1]
        a = by_label[la][0]
        b = by_label[lb][0]
        return (la, a[0], a[1]), (lb, b[0], b[1])
    if len(labeled) >= 2:
        k0, p0, l0 = labeled[0]
        k1, p1, l1 = labeled[1]
        return (l0, k0, p0), (l1, k1, p1)
    return None, None


def make_panel(path_a, path_b, path_reg_b, out_path, labels, title):
    size = 420
    def load(p):
        return np.asarray(Image.open(p).convert("RGB").resize((size, size), Image.LANCZOS))
    imgs = [load(path_a), load(path_b)]
    caps = [f"A: {labels[0]}", f"B: {labels[1]}"]
    if path_reg_b is not None:
        imgs.append(load(path_reg_b))
        caps.append("B warped onto A (ORB)")
    pad = 4
    strip_h = 22
    cols = []
    for im, cap in zip(imgs, caps):
        canvas = Image.new("RGB", (size, size + strip_h), (25, 25, 25))
        canvas.paste(Image.fromarray(im), (0, strip_h))
        d = ImageDraw.Draw(canvas)
        d.text((4, 4), cap, fill=(255, 255, 255))
        cols.append(np.asarray(canvas))
    sheet = np.concatenate([np.pad(c, ((0, 0), (0, pad), (0, 0)), constant_values=10) for c in cols], axis=1)
    Image.fromarray(sheet).save(out_path, quality=85)


def run(manifest_path, census_path, img_root, out_dir, product_ids=None, n_pick=15):
    manifest = {m["product_id"]: m for m in json.load(open(manifest_path)) if m.get("product_id")}
    census = json.load(open(census_path))
    if product_ids is None:
        cands = [c for c in census if c["n_distinct"] >= 2 and c["n_images"] >= 5]
        cands.sort(key=lambda c: -c["n_images"])
        product_ids = [c["product_id"] for c in cands[:n_pick]]

    os.makedirs(out_dir, exist_ok=True)
    panels_dir = os.path.join(out_dir, "panels")
    os.makedirs(panels_dir, exist_ok=True)
    results = []
    for pid in product_ids:
        entry = manifest.get(pid)
        if entry is None:
            print(f"SKIP {pid}: not in manifest")
            continue
        print(f"=== {pid} ({entry['brand']}) {entry.get('title')}")
        images = download_full_set(entry, img_root)
        labeled = []
        for key, path in images:
            feat = analyze_image(path)
            label, conf, reason = classify(feat)
            labeled.append((key, path, label))
            print(f"   {key:14s} -> {label:10s} ({reason})")
        a, b = pick_pair(labeled)
        if a is None:
            results.append({"product_id": pid, "brand": entry["brand"], "verdict": "insufficient_images",
                             "n_images": len(images)})
            continue
        (la, ka, pa), (lb, kb, pb) = a, b
        size = 900
        a_u8 = load_u8(pa, size)
        b_u8 = load_u8(pb, size)
        warped_ab, inliers_ab = orb_register(b_u8, a_u8)
        warped_ba, inliers_ba = orb_register(a_u8, b_u8)
        best_inliers = max(inliers_ab, inliers_ba)
        registrable = best_inliers >= ORB_INLIER_THRESH
        reg_path = None
        if registrable:
            reg_path = os.path.join(img_root, f"{pid}_reg_preview.jpg")
            warped = warped_ab if inliers_ab >= inliers_ba else warped_ba
            ref = a_u8 if inliers_ab >= inliers_ba else b_u8
            Image.fromarray(checker_blend(ref, warped)).save(reg_path, quality=88)
        panel_path = os.path.join(panels_dir, f"{pid}.jpg")
        make_panel(pa, pb, reg_path, panel_path, (la, lb), entry.get("title", ""))
        rec = {
            "product_id": pid, "brand": entry["brand"], "title": entry.get("title"),
            "url": entry["url"], "n_images_downloaded": len(images),
            "pair_a": {"key": ka, "label": la}, "pair_b": {"key": kb, "label": lb},
            "orb_inliers_a_from_b": inliers_ab, "orb_inliers_b_from_a": inliers_ba,
            "best_inliers": best_inliers, "registrable": registrable,
            "panel": panel_path,
        }
        results.append(rec)
        print(f"   PAIR {la}<->{lb}: inliers a<-b={inliers_ab} b<-a={inliers_ba} "
              f"-> {'REGISTRABLE' if registrable else 'not registrable (diff region / eyeball needed)'}")
        json.dump(results, open(os.path.join(out_dir, "pair_quality.json"), "w"), indent=1)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="results/product_manifest.json")
    ap.add_argument("--census", default="results/census.json")
    ap.add_argument("--img-root", default="/tmp/delphi_pairs_images")
    ap.add_argument("--out", default="results")
    ap.add_argument("--ids", nargs="*", default=None)
    ap.add_argument("--n", type=int, default=15)
    args = ap.parse_args()
    run(args.manifest, args.census, args.img_root, args.out, product_ids=args.ids, n_pick=args.n)
