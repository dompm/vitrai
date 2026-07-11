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
            if len(data) < 200 or not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
                return False  # error page / non-image response
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "wb").write(data)
            return True
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return False


# ---------------------------------------------------------------- features --

def _load_rgb(path):
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im).astype(np.float32) / 255.0
    # Tiny census thumbs (70x55) carry heavy JPEG block noise that inflates
    # border_std / sky_top and drags predictions toward the 'wild' branches
    # (calibration: thumb-res accuracy 53% vs 77% full-res before this fix).
    # Upscale + denoise before feature extraction.
    if min(arr.shape[:2]) < 100:
        h, w = arr.shape[:2]
        arr = cv2.resize(arr, (w * 3, h * 3), interpolation=cv2.INTER_LANCZOS4)
        arr = np.clip(cv2.GaussianBlur(arr, (0, 0), sigmaX=1.2), 0.0, 1.0)
    return arr


def analyze_image(path):
    try:
        rgb = _load_rgb(path)
    except Exception:
        return None  # corrupt / non-image bytes on disk
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

    # TOP-BAND cues -- Delphi's window shots consistently show trees/sky above
    # the sheet's top edge (sheet propped on the storefront windowsill), and
    # through-glass window shots show foliage mid-frame.
    tb = max(1, int(round(0.16 * h)))
    hue_t, sat_t, val_t = hue[:tb, :], sat[:tb, :], val[:tb, :]
    sky_top = float((((val_t > 0.72) & (sat_t < 0.30)) |
                     ((hue_t > 95) & (hue_t < 135) & (sat_t > 0.15) & (val_t > 0.4))).mean())
    veg_mask = (hue > 30) & (hue < 90) & (sat > 0.15) & (val > 0.08) & (val < 0.85)
    veg_top = float(veg_mask[:tb, :].mean())
    veg_all = float(veg_mask.mean())

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
        sky_top=sky_top, veg_top=veg_top, veg_all=veg_all,
    )


def classify(feat):
    """Decision list calibrated on 30 hand-labeled full-res images (report 030
    SS1.2). Labels: lightbox / window / shop / closeup / other.

    Design notes from the calibration pass (kept honest, all in the report):
    - `shop` MERGES the brief's held-in-shop and standing-on-surface classes.
      Skin-tone hand detection is unusable on this corpus: pink/amber/beige art
      glass lands in every practical skin-color gate (a pink wispy sheet scored
      a 0.254 'skin' blob fraction), and hands in these photos are small and
      often gloved/cropped. Held-vs-propped does not change the capture
      physics (indoor front-lit, shop background), so the merge costs the
      research nothing.
    - The single most reliable split is border_std: 'wild' shots (visible
      background: window/shop/other) have border-ring luminance std > ~0.19,
      clean full-bleed/lightbox shots sit below it (30/30 separation on the
      window-vs-closeup calibration classes).
    - Within wild, Delphi's house style makes WINDOW detection easy: sheets
      propped on the storefront windowsill with trees/sky above, or an outdoor
      scene visible THROUGH transparent glass (sky_top / veg_top cues).
    - Known residual confusions (counted in the report's accuracy): finished
      panels/mosaics photographed in a window read as `window`; the
      flowers-behind-glass demo trope reads as `closeup`/`window`; pale
      near-white glass full-bleed reads as `lightbox`."""
    if feat is None:
        return "other", 0.0, "unreadable"

    veg_top, sky_top, veg_all = feat["veg_top"], feat["sky_top"], feat["veg_all"]
    wild = feat["border_std"] > 0.185

    if wild:
        if sky_top > 0.40 or veg_top > 0.25:
            return "window", min(1.0, max(sky_top, veg_top)), \
                "background visible; sky/foliage above or through the sheet"
        return "shop", 0.6, "background visible; indoor (no sky/foliage cue)"

    if feat["near_white"] > 0.35 and feat["edge_ratio"] > 1.5 and veg_all < 0.03:
        return "lightbox", min(1.0, feat["near_white"] + 0.3), \
            "uniform near-white border distinct from interior"
    return "closeup", min(1.0, 1.2 - feat["border_std"]), \
        "full-bleed texture, no distinct background band"


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
            cached = os.path.exists(path) and os.path.getsize(path) > 0
            ok = fetch(url, path)
            if not ok:
                continue
            feat = analyze_image(path)
            label, conf, reason = classify(feat)
            classifications.append({"key": key, "label": label, "confidence": round(conf, 3),
                                     "reason": reason})
            if not cached:  # throttle only actual network hits
                n_fetched += 1
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
