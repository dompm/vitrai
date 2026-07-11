#!/usr/bin/env python3
"""Iteration 033 -- maintainer-caught contamination screens, applied post-crawl.

The maintainer's review of the 030 preview surfaced four contamination modes
the harvest's manifest must account for. This script runs AFTER harvest_033.py
against the downloaded full-res images + results/manifest_033.json and writes
results/contamination_033.json with per-mode counts. Nothing is deleted; the
output is an advisory annotation layer keyed by product_id / image_key, same
posture as report 019's audit_flagger.

Modes:
  1. finished_product -- gallery images showing objects MADE from the glass
     (mosaic vases, suncatchers). The harvest's tail-slot flag (gallery index
     >= 6) is a weak positional proxy; the maintainer's example 186196
     "Van Gogh Silver" has mosaic-vase photos in EARLY slots. Validation here:
     every Van Gogh-line product's images get an eyeball panel
     (results/panels_033/vangogh_validation_*.jpg) and the tail-slot +
     lineup screens' hit rates against hand labels are recorded in
     results/vangogh_validation.json (labels filled in by reviewer).
  2. lineup_collage -- fanned multi-sheet marketing shot on white (maintainer
     example: 220063 MLW Vivid Amethyst Mirror). Reuses report 019's
     audit_flagger signals (near-white ground + blob structure): reason codes
     `test_fire_tiles` (multi compact blobs on white) and `product_on_white`
     (single dominant blob on mostly-white border) both mark an image as a
     studio-ground shot, not a full-bleed/wild sheet capture.
  3. non_transmissive exclusion -- mirror glass has no transmissive component;
     it should not be in a T-map pairs dataset at all. Title-keyword screen
     (mirror). Checked against the census: the only non-transmissive finishes
     in the 10 crawled sheet categories are the 3 MLW mirror products
     (specialty-finish-glass); Van Gogh's metallic-coated glass is kept but
     carries mode-1 screening since its galleries are mosaic-heavy.
     ALSO: multi-sheet LISTINGS (sampler packs, sample sets) -- "Glass Pack" /
     "Sampler" / "Sample Set" titles are assortments whose photos are
     lineups by construction; flagged as `multi_sheet_listing`.
  4. capture-label errors -- 186204's "window" image is a front-lit shop rack
     (real sheets, wrong label). Folded into report 033's classifier-accuracy
     accounting, not a new screen (the clean/wild binary is unaffected;
     window-vs-shop confusion was already quantified in report 030 SS1.2).
  5. suspect_same_photo (harvest-agent-caught, eyeball-confirmed on the top
     contact-sheet candidate 174075): pairwise_matrix.py's same-photo gate is
     (mad < 10 AND grad_corr > 0.35); on low-contrast CLEAR glass the
     gradient correlation of a genuine crop-derivation sits far below 0.35
     (median grad_corr across all cross_capture pairs is ~0.12), so
     hero-as-crop duplicates leak into cross_capture with tiny residuals and
     saturated inlier counts. Post-hoc flag: cross_capture pairs with
     residual_mad < 15 AND inliers >= 200 are marked suspect_same_photo.
     Advisory, like the rest.
  1b. line_stock_photo (found while validating mode 1 -- the decisive screen):
     the Van Gogh line's finished-product shots are the SAME photos reused
     across every product in the line (vase / vanity / rose table / chess
     table / comparison collage), and Wissmach/Uro reuse tail-slot stock
     photos the same way. Detection: perceptual dhash (8x8 gradient hash,
     exact match) grouped across products -- catches both byte-identical
     files AND the re-encoded copies a sha1 misses (12 of the Van Gogh
     line's 67 non-sheet images are re-encodes; sha1-only recall 69%,
     dhash recall on the same ground truth 87%).
  6. variant_duplicate_listing (found while validating 1b): pid pairs that
     share >=2 dhash groups including a hero are the SAME product listed
     twice (Delphi's Spectrum->Oceanside "96 COE" relistings: 174130/230307,
     174974/234255, 175010/234263). Their shared images are NOT stock photos
     -- they are the product's real photos under two listings -- so these
     pairs are recorded for product-level dedup instead of image flagging
     (keep one listing per pair when counting distinct physical sheets).
"""
import argparse
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "corpus"))
from audit_flagger import analyze_image as flag_analyze, flag_signals  # noqa: E402

MIRROR_KEYWORDS = ["mirror"]
MULTI_SHEET_KEYWORDS = ["glass pack", "sampler", "sample set", "variety pack", "crate"]


def img_path(img_root, pid, key):
    if key == "hero":
        return os.path.join(img_root, pid, "hero_full.jpg")
    n = key.split("_")[1]
    return os.path.join(img_root, pid, f"g{n}_full.jpg")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="results/manifest_033.json")
    ap.add_argument("--img-root", default="data/images")
    ap.add_argument("--out", default="results/contamination_033.json")
    args = ap.parse_args()

    products = json.load(open(args.manifest))
    done = [p for p in products if p.get("status") == "done"]

    out = {"modes": {}, "products": {}}

    # --- mode 3: title-keyword exclusions -------------------------------
    mirror_products, multisheet_products = [], []
    for p in done:
        t = (p.get("title") or "").lower()
        rec = out["products"].setdefault(p["product_id"], {"flags": [], "images": {}})
        if any(k in t for k in MIRROR_KEYWORDS):
            rec["flags"].append("non_transmissive_mirror")
            mirror_products.append(p["product_id"])
        if any(k in t for k in MULTI_SHEET_KEYWORDS):
            rec["flags"].append("multi_sheet_listing")
            multisheet_products.append(p["product_id"])

    # --- mode 1b + 6: cross-product duplicate photos (dhash) ------------
    def dhash(path, size=8):
        im = Image.open(path).convert("L").resize((size + 1, size), Image.LANCZOS)
        px = list(im.getdata())
        bits = 0
        for r in range(size):
            for c in range(size):
                bits = (bits << 1) | (1 if px[r * (size + 1) + c] > px[r * (size + 1) + c + 1] else 0)
        return f"{bits:016x}"

    hash_to_imgs = {}
    for p in done:
        pid = p["product_id"]
        for im in p["images"]:
            path = img_path(args.img_root, pid, im["image_key"])
            if not os.path.exists(path):
                continue
            try:
                hh = dhash(path)
            except Exception:
                continue
            hash_to_imgs.setdefault(hh, []).append((pid, im["image_key"]))

    cross_groups = {hh: m for hh, m in hash_to_imgs.items()
                    if len(set(pid for pid, _ in m)) >= 2}
    # mode 6: pid pairs sharing >=2 groups, at least one containing a hero,
    # are the same product listed twice (variant relisting) -- record the
    # pair, exempt their shared images from the stock flag.
    from collections import Counter
    pairs_count = Counter()
    pair_has_hero = set()
    for hh, m in cross_groups.items():
        pids = sorted(set(pid for pid, _ in m))
        if len(pids) == 2:
            pairs_count[tuple(pids)] += 1
            if any(key == "hero" for _, key in m):
                pair_has_hero.add(tuple(pids))
    variant_pairs = [pp for pp, n in pairs_count.items() if n >= 2 and pp in pair_has_hero]
    variant_set = set(variant_pairs)

    stock_groups = []
    n_stock_imgs = 0
    for hh, m in sorted(cross_groups.items()):
        pids = sorted(set(pid for pid, _ in m))
        if len(pids) == 2 and tuple(pids) in variant_set:
            continue  # same product relisted, not a stock photo
        stock_groups.append({"dhash": hh, "members": [list(x) for x in m]})
        for pid, key in m:
            n_stock_imgs += 1
            out["products"].setdefault(pid, {"flags": [], "images": {}})
            out["products"][pid]["images"].setdefault(key, []).append("line_stock_photo")
    for a, b in variant_pairs:
        for pid in (a, b):
            out["products"].setdefault(pid, {"flags": [], "images": {}})
            if "variant_duplicate_listing" not in out["products"][pid]["flags"]:
                out["products"][pid]["flags"].append("variant_duplicate_listing")

    # --- mode 2: lineup/on-white screen (audit_flagger reuse) -----------
    lineup_flagged = []  # (pid, key, reasons)
    n_scanned = 0
    for p in done:
        pid = p["product_id"]
        for im in p["images"]:
            path = img_path(args.img_root, pid, im["image_key"])
            if not os.path.exists(path):
                continue
            try:
                sig = flag_analyze(path)
            except Exception:
                continue
            n_scanned += 1
            reasons = flag_signals(sig)
            if reasons:
                lineup_flagged.append({"product_id": pid, "image_key": im["image_key"],
                                        "capture_type": im["capture_type"],
                                        "reasons": reasons, "signals": sig})
                out["products"].setdefault(pid, {"flags": [], "images": {}})
                out["products"][pid]["images"].setdefault(im["image_key"], []).extend(reasons)

    # --- mode 1 bookkeeping: pairs invalidated by each screen -----------
    def pair_flagged(p, pr, pid_flags, img_flags):
        a_flag = pr["a"] in img_flags
        b_flag = pr["b"] in img_flags
        return a_flag or b_flag

    n_cross_total = 0
    n_cross_killed_mirror = 0
    n_cross_killed_multisheet = 0
    n_cross_killed_lineup = 0
    n_cross_killed_stock = 0
    n_cross_killed_tail = 0
    n_cross_killed_suspect = 0
    n_cross_surviving = 0
    suspect_pairs = []
    for p in done:
        pid = p["product_id"]
        rec = out["products"].get(pid, {"flags": [], "images": {}})
        for pr in p.get("pairs", []):
            if pr["kind"] != "cross_capture":
                continue
            n_cross_total += 1
            killed = False
            reasons_a = rec["images"].get(pr["a"], [])
            reasons_b = rec["images"].get(pr["b"], [])
            if "non_transmissive_mirror" in rec["flags"]:
                n_cross_killed_mirror += 1
                killed = True
            if "multi_sheet_listing" in rec["flags"]:
                n_cross_killed_multisheet += 1
                killed = True
            if "line_stock_photo" in reasons_a or "line_stock_photo" in reasons_b:
                n_cross_killed_stock += 1
                killed = True
            if any(r in ("test_fire_tiles", "product_on_white") for r in reasons_a + reasons_b):
                n_cross_killed_lineup += 1
                killed = True
            if pr["finished_product_flag"]:
                n_cross_killed_tail += 1
                killed = True
            if (pr["residual_mad"] is not None and pr["residual_mad"] < 15
                    and pr["inliers"] >= 200):
                n_cross_killed_suspect += 1
                suspect_pairs.append({"product_id": pid, "a": pr["a"], "b": pr["b"],
                                       "inliers": pr["inliers"], "residual_mad": pr["residual_mad"],
                                       "grad_corr": pr["grad_corr"]})
                killed = True
            if not killed:
                n_cross_surviving += 1

    out["modes"] = {
        "non_transmissive_mirror": {
            "n_products": len(mirror_products), "product_ids": mirror_products,
            "n_cross_capture_pairs_removed": n_cross_killed_mirror,
        },
        "multi_sheet_listing": {
            "n_products": len(multisheet_products), "product_ids": multisheet_products,
            "n_cross_capture_pairs_removed": n_cross_killed_multisheet,
        },
        "line_stock_photo": {
            "n_duplicate_groups": len(stock_groups),
            "n_images_flagged": n_stock_imgs,
            "n_cross_capture_pairs_removed": n_cross_killed_stock,
            "groups": stock_groups,
        },
        "lineup_or_on_white": {
            "n_images_scanned": n_scanned,
            "n_images_flagged": len(lineup_flagged),
            "n_cross_capture_pairs_removed": n_cross_killed_lineup,
            "flagged": lineup_flagged,
        },
        "finished_product_tail_slot": {
            "n_cross_capture_pairs_removed": n_cross_killed_tail,
        },
        "suspect_same_photo": {
            "rule": "cross_capture AND residual_mad < 15 AND inliers >= 200",
            "n_cross_capture_pairs_removed": n_cross_killed_suspect,
            "pairs": suspect_pairs,
        },
        "variant_duplicate_listing": {
            "n_pairs": len(variant_pairs),
            "pid_pairs": [list(pp) for pp in variant_pairs],
        },
        "summary": {
            "n_cross_capture_total": n_cross_total,
            "n_cross_capture_surviving_all_screens": n_cross_surviving,
        },
    }

    json.dump(out, open(args.out, "w"), indent=1)
    print(f"scanned {n_scanned} images across {len(done)} products")
    print(f"mirror products excluded: {len(mirror_products)} {mirror_products}")
    print(f"multi-sheet listings flagged: {len(multisheet_products)} {multisheet_products}")
    print(f"lineup/on-white images flagged: {len(lineup_flagged)}")
    print(f"line stock photos (cross-product dhash duplicates): {n_stock_imgs} images in {len(stock_groups)} groups")
    print(f"variant duplicate listings (same product, two pids): {len(variant_pairs)} {variant_pairs}")
    print(f"cross_capture pairs: {n_cross_total} total -> {n_cross_surviving} surviving all screens "
          f"(removed: mirror {n_cross_killed_mirror}, multi-sheet {n_cross_killed_multisheet}, "
          f"stock {n_cross_killed_stock}, lineup {n_cross_killed_lineup}, "
          f"tail-slot {n_cross_killed_tail}, suspect-same-photo {n_cross_killed_suspect}; "
          f"overlaps possible)")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
