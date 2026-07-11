#!/usr/bin/env python3
"""Iteration 033 -- full-scale Delphi real-pairs harvest.

Scales report 030's validated pipeline (crawl.py discovery + classify.py
capture-type classifier + pairwise_matrix.py's same_photo/cross_capture ORB
registration) from the 15-product pair-quality probe / 157-product thumb-only
census to ALL parseable products, at FULL resolution (1500x1500), with the
pairwise registration run on every within-product image pair.

Per product:
  1. Download full-res hero + gallery images (1500x1500) to
     realpairs/data/images/<pid>/ -- gitignored, durable local dataset, same
     posture as synthetic renders. Idempotent (skips existing non-empty files).
  2. Classify every image with classify.py's calibrated heuristic (run at full
     res, which report 030 SS1.2 showed is materially more reliable than the
     70x55 census thumb: 87% vs 57% binary clean/wild accuracy).
  3. Exhaustive within-product pairwise ORB registration (same code path as
     pairwise_matrix.py): same_photo (crop/rescale derivation) vs
     cross_capture (registrable, substantial residual) vs none (not
     registrable -- becomes a statistics_only candidate if same-sheet is
     plausible).
  4. Two additional automated screens report 030 only did by eyeballing 15
     products (honesty note: these are heuristic PROXIES for what a human
     verified at small scale, not re-validated at n=350 -- flagged, not
     silently trusted):
       - finished_product_flag: gallery tail slots (index >= 6) are, per
         report 030 SS2.2, disproportionately "project made from this glass"
         photos rather than sheet photos. Pairs involving a tail-slot image
         are flagged, not dropped (a human can filter further).
       - opal_streaky_caution: product title matches an opal/streaky/wispy/
         mottled/granite keyword -- report 030 SS2.3's sheet-identity-
         unverified case (238607 mermaid dreams) was exactly an opal/streaky
         product. Flag only; does not change registrability.

Resumable: keyed by product_id (deduped -- Delphi reuses one photo-id across
thickness/size SKU variants, report 030 SS4). A product already present in
the output manifest with status "done" is skipped entirely on rerun; a
product that errored partway is retried.

Checkpointing: manifest written to --out every --checkpoint-every products
(default 5) so a long background run survives interruption.
"""
import argparse
import itertools
import json
import os
import sys
import time
import urllib.request

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from classify import analyze_image, classify, UA  # noqa: E402
from register_pair import orb_register, load_u8  # noqa: E402

HERO_FULL_URL = "https://images.delphiglass.com/image_1500/{id}.jpg"
GALLERY_FULL_URL = "https://www.delphiglass.com/syscat/image_add/{id}_{n}0.jpg"

ORB_INLIER_THRESH = 20
SAME_PHOTO_MAD = 10.0
REG_SIZE = 700  # working resolution for ORB registration, matches pairwise_matrix.py

OPAL_STREAKY_KEYWORDS = [
    "opal", "opaque", "streaky", "wispy", "mottle", "mottled", "granite",
    "ring mottle", "cathedral streaky", "art glass streaky",
]


def fetch(url, dest, retries=3, sleep_s=1.0):
    """Returns (ok, was_network_hit)."""
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return True, False
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            if len(data) < 1000:
                return False, True
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "wb").write(data)
            return True, True
        except Exception:
            time.sleep(sleep_s * (attempt + 1))
    return False, True


def dedup_by_product_id(manifest):
    """Delphi reuses one photo-id across thickness/size SKU variants (report
    030 SS4) -- keep the entry with the most gallery images per unique pid."""
    by_pid = {}
    for m in manifest:
        pid = m.get("product_id")
        if not pid or "error" in m:
            continue
        prev = by_pid.get(pid)
        if prev is None or len(m.get("gallery", [])) > len(prev.get("gallery", [])):
            by_pid[pid] = m
    return list(by_pid.values())


def image_paths(entry, img_root):
    """Returns list of (key, gallery_index_or_None, local_path, url)."""
    pid = entry["product_id"]
    prod_dir = os.path.join(img_root, pid)
    out = [("hero", None, os.path.join(prod_dir, "hero_full.jpg"),
            HERO_FULL_URL.format(id=pid))]
    for g in entry.get("gallery", []):
        n = g["index"]
        gpid = g["product_id"]
        out.append((f"gallery_{n}", n, os.path.join(prod_dir, f"g{n}_full.jpg"),
                     GALLERY_FULL_URL.format(id=gpid, n=n)))
    return out


def central_residual(ref, warped):
    H, W = ref.shape[:2]
    cy, cx = H // 2, W // 2
    ch, cw = H // 3, W // 3
    r = ref[cy - ch // 2:cy + ch // 2, cx - cw // 2:cx + cw // 2].astype(np.float32)
    w_ = warped[cy - ch // 2:cy + ch // 2, cx - cw // 2:cx + cw // 2].astype(np.float32)
    mad = float(np.median(np.abs(r - w_)))
    gr = cv2.Sobel(cv2.cvtColor(r.astype(np.uint8), cv2.COLOR_RGB2GRAY), cv2.CV_32F, 1, 1)
    gw = cv2.Sobel(cv2.cvtColor(w_.astype(np.uint8), cv2.COLOR_RGB2GRAY), cv2.CV_32F, 1, 1)
    denom = gr.std() * gw.std()
    cc = float((gr * gw).mean() / denom) if denom > 1e-6 else 0.0
    return mad, cc


def process_product(entry, img_root, sleep_s):
    pid = entry["product_id"]
    title = entry.get("title")
    opal_flag = bool(title) and any(kw in title.lower() for kw in OPAL_STREAKY_KEYWORDS)

    paths = image_paths(entry, img_root)
    images = {}  # key -> {"path", "index", "url"}
    n_network_hits = 0
    for key, idx, path, url in paths:
        ok, hit = fetch(url, path, sleep_s=sleep_s)
        if hit:
            n_network_hits += 1
            time.sleep(sleep_s)
        if ok:
            images[key] = {"path": path, "index": idx, "url": url}

    if not images:
        return {"product_id": pid, "brand": entry["brand"], "title": title, "url": entry["url"],
                "status": "no_images", "images": [], "pairs": []}, n_network_hits

    # classify each image at full res
    img_records = []
    loaded = {}
    for key, info in images.items():
        feat = analyze_image(info["path"])
        label, conf, reason = classify(feat)
        w = feat["w"] if feat else None
        h = feat["h"] if feat else None
        img_records.append({
            "image_key": key, "gallery_index": info["index"], "url_full": info["url"],
            "capture_type": label, "capture_conf": round(conf, 3), "w": w, "h": h,
        })
        try:
            loaded[key] = load_u8(info["path"], REG_SIZE)
        except Exception:
            pass

    # exhaustive pairwise ORB registration
    pair_records = []
    keys_sorted = sorted(loaded.keys())
    for ka, kb in itertools.combinations(keys_sorted, 2):
        a, b = loaded[ka], loaded[kb]
        w_ab, i_ab = orb_register(b, a)
        w_ba, i_ba = orb_register(a, b)
        if i_ab >= i_ba and w_ab is not None:
            inl, ref, warped = i_ab, a, w_ab
        elif w_ba is not None:
            inl, ref, warped = i_ba, b, w_ba
        else:
            inl, ref, warped = max(i_ab, i_ba), None, None
        registrable = inl >= ORB_INLIER_THRESH and warped is not None
        if registrable:
            mad, cc = central_residual(ref, warped)
            kind = "same_photo" if (mad < SAME_PHOTO_MAD and cc > 0.35) else "cross_capture"
        else:
            mad, cc, kind = None, None, "none"
        idx_a = images[ka]["index"]
        idx_b = images[kb]["index"]
        tail_flag = (idx_a is not None and idx_a >= 6) or (idx_b is not None and idx_b >= 6)
        label_a = next(r["capture_type"] for r in img_records if r["image_key"] == ka)
        label_b = next(r["capture_type"] for r in img_records if r["image_key"] == kb)
        pair_type = "registrable_same_region" if kind == "cross_capture" else (
            "statistics_only" if kind == "none" else "same_photo_derivation")
        pair_records.append({
            "a": ka, "b": kb, "capture_type_a": label_a, "capture_type_b": label_b,
            "inliers": int(inl), "registrable": bool(registrable),
            "residual_mad": mad, "grad_corr": cc, "kind": kind,
            "pair_type": pair_type,
            "finished_product_flag": tail_flag,
        })

    return {
        "product_id": pid, "brand": entry["brand"], "title": title, "url": entry["url"],
        "status": "done", "opal_streaky_caution": opal_flag,
        "n_images": len(img_records), "images": img_records,
        "n_pairs": len(pair_records), "pairs": pair_records,
    }, n_network_hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="results/product_manifest.json")
    ap.add_argument("--img-root", default="data/images")
    ap.add_argument("--out", default="data/manifest_033_full.json")
    ap.add_argument("--committed-out", default="results/manifest_033.json")
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--checkpoint-every", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    manifest = json.load(open(args.manifest))
    products = dedup_by_product_id(manifest)
    products.sort(key=lambda p: p["product_id"])
    print(f"{len(products)} unique parseable products (deduped by product_id)")

    results = []
    done_pids = set()
    if os.path.exists(args.out):
        results = json.load(open(args.out))
        done_pids = {r["product_id"] for r in results if r.get("status") == "done"}
        # drop any non-done stubs so they get retried
        results = [r for r in results if r.get("status") == "done"]
    todo = [p for p in products if p["product_id"] not in done_pids]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(done_pids)} already done, {len(todo)} to process this run")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    t0 = time.time()
    total_hits = 0
    for i, entry in enumerate(todo):
        try:
            rec, hits = process_product(entry, args.img_root, args.sleep)
            total_hits += hits
            results.append(rec)
            n_cross = sum(1 for p in rec.get("pairs", []) if p["kind"] == "cross_capture")
            n_same = sum(1 for p in rec.get("pairs", []) if p["kind"] == "same_photo")
            elapsed = time.time() - t0
            rate = total_hits / max(1e-6, elapsed)
            print(f"[{i+1}/{len(todo)}] {entry['brand']:22s} {entry['product_id']} "
                  f"n_img={rec.get('n_images', 0)} cross={n_cross} same_photo={n_same} "
                  f"| {total_hits} net hits, {elapsed/60:.1f}m elapsed, {rate:.2f} req/s")
        except Exception as e:
            print(f"[{i+1}/{len(todo)}] ERROR {entry.get('product_id')}: {e}")
            results.append({"product_id": entry["product_id"], "brand": entry["brand"],
                             "title": entry.get("title"), "url": entry["url"],
                             "status": "error", "error": str(e), "images": [], "pairs": []})
        if (i + 1) % args.checkpoint_every == 0:
            json.dump(results, open(args.out, "w"), indent=1)
            write_committed(results, args.committed_out)
    json.dump(results, open(args.out, "w"), indent=1)
    write_committed(results, args.committed_out)
    print(f"DONE. {len(results)} products in manifest, {total_hits} network hits this run, "
          f"{(time.time()-t0)/60:.1f} min.")


def write_committed(results, path):
    """Slim committed rollup: drop nothing structurally (schema matches the
    brief) but this IS the full per-product record minus the loaded pixel
    arrays (never serialized anyway) -- homographies are also never stored,
    only inlier counts + residual stats, to keep file size sane at n~350."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    done = [r for r in results if r.get("status") == "done"]
    json.dump(done, open(path, "w"), indent=1)


if __name__ == "__main__":
    main()
