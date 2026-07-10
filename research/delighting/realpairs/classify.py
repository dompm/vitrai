#!/usr/bin/env python3
"""Iteration 030 -- cheap heuristic capture-type classifier + census runner.

Classifies each product image into one of:
  lightbox   - clean, uniform-backlit swatch (product studio shot)
  window     - held up against a window / outdoors, backlit by sky/daylight
  shop_held  - held by a hand indoors, front-lit shop background
  standing   - sheet standing/leaning on a surface among other sheets, no hand
  closeup    - tight crop, no visible background at all (texture detail)
  other      - none of the above fit confidently

Runs on the SMALL images only (listing thumbnails: hero image_new 300x300,
gallery thumbs 70x55) to keep the census's load on delphiglass.com modest --
per the task brief, ~1 req/s, normal UA, image bytes only (page HTML never
touches the live site; see crawl.py's docstring).
"""
import argparse
import json
import os
import time
import urllib.request

import cv2
import numpy as np
from PIL import Image

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) research-delighting-030 (internal eval; contact via github)"

HERO_URL = "https://images.delphiglass.com/image_new/{id}.jpg"          # ~300x300
GALLERY_THUMB_URL = "https://www.delphiglass.com/syscat/image_add/{id}_{n}.jpg"  # ~70x55
GALLERY_FULL_URL = "https://www.delphiglass.com/syscat/image_add/{id}_{n}0.jpg"  # 1500x1500
HERO_FULL_URL = "https://images.delphiglass.com/image_1500/{id}.jpg"


def fetch(url, dest, retries=3):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read()
            if len(data) < 200:  # tiny error page, not a real image
                return False
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "wb").write(data)
            return True
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return False


# ---------------------------------------------------------------- features --

def _load_rgb(path):
    im = Image.open(path).convert("RGB")
    return np.asarray(im).astype(np.float32) / 255.0


def analyze_image(path):
    rgb = _load_rgb(path)
    h, w = rgb.shape[:2]
    if h < 8 or w < 8:
        return None
    ring = max(2, int(round(0.14 * min(h, w))))
    mask_border = np.zeros((h, w), bool)
    mask_border[:ring, :] = True
    mask_border[-ring:, :] = True
    mask_border[:, :ring] = True
    mask_border[:, -ring:] = True
    mask_interior = ~mask_border

    lum = rgb.mean(axis=2)
    border_lum = lum[mask_border]
    interior_lum = lum[mask_interior]

    border_std = float(border_lum.std())
    interior_std = float(interior_lum.std())
    border_mean = float(border_lum.mean())

    hsv = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2HSV)
    hue = hsv[..., 0].astype(np.float32)
    sat = hsv[..., 1].astype(np.float32) / 255.0
    val = hsv[..., 2].astype(np.float32) / 255.0

    border_hue = hue[mask_border]
    border_sat = sat[mask_border]
    border_val = val[mask_border]
    # hue histogram entropy over saturated-enough border pixels (unsaturated
    # near-white/black pixels don't carry meaningful hue)
    sig = border_sat > 0.12
    if sig.sum() > 20:
        hist, _ = np.histogram(border_hue[sig], bins=12, range=(0, 180))
        p = hist / max(1, hist.sum())
        hue_entropy = float(-(p[p > 0] * np.log2(p[p > 0])).sum())
    else:
        hue_entropy = 0.0

    near_white = float(((border_val > 0.82) & (border_sat < 0.18)).mean())
    near_black = float((border_val < 0.16).mean())
    # sky/foliage hue fraction (outdoor-window cue) vs wood/shelf hue fraction
    # (indoor-shop cue); OpenCV hue range 0-180
    sky_like = ((border_hue > 85) & (border_hue < 140) & (border_sat > 0.15)) | \
               ((border_val > 0.75) & (border_sat < 0.25))  # overcast/blown sky
    wood_like = (border_hue > 5) & (border_hue < 30) & (border_sat > 0.25) & (border_val < 0.75)
    border_sky_frac = float(sky_like.mean())
    border_wood_frac = float(wood_like.mean())

    # top vs bottom brightness gradient (sky-backlit window cue)
    top = lum[: max(1, h // 5), :].mean()
    bot = lum[-max(1, h // 5):, :].mean()
    top_bottom_grad = float(top - bot)

    # Skin-tone blob. Colour alone is a weak cue here: amber/gold/brown art glass
    # (very common) sits in the SAME YCrCb/RGB range as real skin. The
    # discriminator that actually works is TEXTURE: a hand is smooth (low local
    # Laplacian variance) and a compact, roughly-round blob touching the frame
    # edge (fingers gripping a sheet); textured amber/streaky glass triggers the
    # same colour rule but is high local-variance and/or spans a much larger,
    # non-compact area. Restricted to the outer ~40% of the frame (hands grip
    # sheets at the edge in these shots; glass fills the centre either way).
    rgbu8 = (rgb * 255).astype(np.uint8)
    r, g, b = rgbu8[..., 0].astype(np.int16), rgbu8[..., 1].astype(np.int16), rgbu8[..., 2].astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    skin_color = ((r > 95) & (g > 40) & (b > 20) & ((mx - mn) > 15) &
                  (np.abs(r - g) > 12) & (r > g) & (r > b))
    search_ring = max(2, int(round(0.40 * min(h, w))))
    mask_search = np.zeros((h, w), bool)
    mask_search[:search_ring, :] = True
    mask_search[-search_ring:, :] = True
    mask_search[:, :search_ring] = True
    mask_search[:, -search_ring:] = True
    skin_color = skin_color & mask_search

    gray_u8 = cv2.cvtColor(rgbu8, cv2.COLOR_RGB2GRAY)
    lap = cv2.Laplacian(gray_u8, cv2.CV_32F, ksize=3)
    lap_local = cv2.GaussianBlur(np.abs(lap), (0, 0), sigmaX=3)

    skin_frac_total = float(skin_color.mean())
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        skin_color.astype(np.uint8), connectivity=8)
    skin_blob_frac = 0.0
    min_area = 0.0015 * h * w
    max_area = 0.35 * h * w
    for i in range(1, n_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < min_area or area > max_area:
            continue
        comp_mask = labels == i
        bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        fill = area / float(max(1, bw * bh))
        if fill < 0.25:  # not compact (a diffuse gradient, not a hand blob)
            continue
        texture = float(lap_local[comp_mask].mean())
        if texture > 9.0:  # smooth-skin threshold, calibrated against ex1 (see report)
            continue
        skin_blob_frac = max(skin_blob_frac, area / float(h * w))

    # straight-line cue (shelf/table/window-frame edges) via Canny+Hough
    gray = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 60, 150)
    min_len = max(6, int(0.35 * min(h, w)))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=max(8, min_len // 2),
                             minLineLength=min_len, maxLineGap=3)
    n_long_lines = 0 if lines is None else len(lines)

    edge_ratio = border_std / (interior_std + 1e-6)

    return dict(
        w=w, h=h,
        border_std=border_std, interior_std=interior_std, border_mean=border_mean,
        hue_entropy=hue_entropy, near_white=near_white, near_black=near_black,
        top_bottom_grad=top_bottom_grad, skin_blob_frac=skin_blob_frac,
        skin_frac_total=skin_frac_total, n_long_lines=n_long_lines,
        edge_ratio=edge_ratio, border_sky_frac=border_sky_frac, border_wood_frac=border_wood_frac,
    )


def classify(feat):
    if feat is None:
        return "other", 0.0, "unreadable"

    # 1. hand present -> a held shot; disambiguate window vs shop by sky/foliage
    #    vs wood/shelf hue fraction in the border (NOT brightness gradient alone
    #    -- indoor overhead lighting also produces a bright-top gradient, so
    #    that cue alone is unreliable; calibration finding, see report).
    if feat["skin_blob_frac"] > 0.010:
        conf = min(1.0, feat["skin_blob_frac"] * 20)
        if feat["border_sky_frac"] > feat["border_wood_frac"] + 0.08:
            return "window", conf, "hand + sky/foliage border hue"
        return "shop_held", conf, "hand + wood/shelf border hue (or ambiguous)"

    # 2. near-uniform bright or dark border relative to the interior (a real
    #    lightbox backdrop, distinguishable from the sheet), low hue diversity
    #    -> clean studio swatch
    if (feat["near_white"] > 0.5 or feat["near_black"] > 0.5) and feat["edge_ratio"] > 1.3:
        return "lightbox", min(1.0, feat["near_white"] + feat["near_black"]), "uniform bright/dark border, distinct from interior"

    # 3. border statistically indistinguishable from interior (no separate
    #    background band at all) -> full-bleed shot. Two readings share this
    #    signature and are NOT reliably separable at low resolution: a lightbox
    #    swatch shot tight enough to fill the frame edge-to-edge, and a tight
    #    detail crop. Default to closeup (the more common gallery-tail use of
    #    this signature); flagged as the classifier's known confusion pair.
    if feat["edge_ratio"] < 1.35:
        return "closeup", min(1.0, 1.5 - feat["edge_ratio"]), "border ~= interior texture, no bg edge (lightbox/closeup confusable)"

    # 4. clear background with structure (lines/hue diversity) but no hand
    #    -> standing on a surface / propped among other sheets
    if feat["hue_entropy"] > 1.4 or feat["n_long_lines"] >= 2:
        return "standing", 0.5, "structured background, no hand"

    # 5. fallback: mildly non-uniform border, weak signal either way
    if feat["border_std"] < 0.08:
        return "lightbox", 0.3, "weak uniform-border fallback"
    return "other", 0.3, "no confident rule fired"


# -------------------------------------------------------------- census run --

def gather_product_images(entry, img_root):
    """Returns list of (label_key, local_path, url) for hero + gallery thumbs."""
    pid = entry.get("product_id")
    if not pid:
        return []
    out = []
    hero_path = os.path.join(img_root, f"{pid}_hero.jpg")
    out.append(("hero", hero_path, HERO_URL.format(id=pid)))
    for g in entry.get("gallery", []):
        n = g["index"]
        gpid = g["product_id"]
        p = os.path.join(img_root, f"{gpid}_{n}.jpg")
        out.append((f"gallery_{n}", p, GALLERY_THUMB_URL.format(id=gpid, n=n)))
    return out


def run_census(manifest_path, img_root, out_path, sleep_s=0.9, limit=None):
    manifest = json.load(open(manifest_path))
    products = [m for m in manifest if m.get("product_id") and "error" not in m]
    if limit:
        products = products[:limit]
    results = []
    if os.path.exists(out_path):
        results = json.load(open(out_path))
        done_pids = {r["product_id"] for r in results}
        products = [p for p in products if p["product_id"] not in done_pids]
    n_fetched = 0
    for i, entry in enumerate(products):
        imgs = gather_product_images(entry, img_root)
        classifications = []
        for key, path, url in imgs:
            ok = fetch(url, path)
            if not ok:
                continue
            n_fetched += 1
            feat = analyze_image(path)
            label, conf, reason = classify(feat)
            classifications.append({"key": key, "label": label, "confidence": round(conf, 3),
                                     "reason": reason})
            time.sleep(sleep_s)
        labels = set(c["label"] for c in classifications)
        results.append({
            "product_id": entry["product_id"], "brand": entry["brand"], "url": entry["url"],
            "title": entry.get("title"), "n_images": len(classifications),
            "distinct_capture_types": sorted(labels),
            "n_distinct": len(labels),
            "classifications": classifications,
        })
        print(f"[{i+1}/{len(products)}] {entry['brand']:22s} {entry['product_id']} "
              f"n={len(classifications)} types={sorted(labels)}")
        if (i + 1) % 10 == 0:
            json.dump(results, open(out_path, "w"), indent=1)
    json.dump(results, open(out_path, "w"), indent=1)
    print(f"done. {len(results)} products, {n_fetched} images fetched this run.")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="results/product_manifest.json")
    ap.add_argument("--img-root", default="/tmp/delphi_census_images")
    ap.add_argument("--out", default="results/census.json")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    run_census(args.manifest, args.img_root, args.out, limit=args.limit)
