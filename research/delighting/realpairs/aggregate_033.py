#!/usr/bin/env python3
"""Iteration 033 -- aggregate results/manifest_033.json into the headline
numbers for report 033: products harvested, images, pairs by type, per-brand
distribution, filter hit-rates. Companion to 030's aggregate.py (which
worked off the 157-product thumb-only census; this works off the full-res
harvest of every parseable product with exhaustive pairwise registration)."""
import argparse
import json
from collections import Counter, defaultdict


def main(manifest_path):
    products = json.load(open(manifest_path))
    done = [p for p in products if p.get("status") == "done"]
    print(f"products in manifest: {len(products)} ({len(done)} status=done)")

    n_imgs = [p["n_images"] for p in done]
    print(f"images/product: mean={sum(n_imgs)/len(n_imgs):.2f} "
          f"median={sorted(n_imgs)[len(n_imgs)//2]} min={min(n_imgs)} max={max(n_imgs)} "
          f"total={sum(n_imgs)}")

    by_brand = Counter(p["brand"] for p in done)
    print("\nproducts per brand:")
    for b, c in by_brand.most_common():
        print(f"  {b:24s} {c}")

    label_counts = Counter()
    for p in done:
        for im in p["images"]:
            label_counts[im["capture_type"]] += 1
    total_imgs = sum(label_counts.values())
    print("\nper-image capture-type distribution (full-res classifier):")
    for lab, cnt in label_counts.most_common():
        print(f"  {lab:10s} {cnt:5d}  {100*cnt/total_imgs:.1f}%")

    CLEAN = {"lightbox", "closeup"}
    WILD = {"window", "shop"}
    n_distinct = []
    paired = 0
    for p in done:
        labs = set(im["capture_type"] for im in p["images"])
        n_distinct.append(len(labs))
        if any(l in CLEAN for l in labs) and any(l in WILD for l in labs):
            paired += 1
    multi = sum(1 for n in n_distinct if n >= 2)
    print(f"\nproducts with >=2 distinct capture types: {multi}/{len(done)} = {100*multi/len(done):.1f}%")
    print(f"products with >=1 CLEAN AND >=1 WILD image: {paired}/{len(done)} = {100*paired/len(done):.1f}%")

    all_pairs = [pr for p in done for pr in p.get("pairs", [])]
    kind_counts = Counter(pr["kind"] for pr in all_pairs)
    print(f"\ntotal within-product pairs examined: {len(all_pairs)}")
    for k, c in kind_counts.most_common():
        print(f"  {k:16s} {c:6d}  {100*c/len(all_pairs):.1f}%")

    cross = [pr for pr in all_pairs if pr["kind"] == "cross_capture"]
    cross_clean = [pr for pr in cross if not pr["finished_product_flag"]]
    n_opal_products = sum(1 for p in done if p.get("opal_streaky_caution"))
    n_finished_flagged_pairs = sum(1 for pr in cross if pr["finished_product_flag"])

    products_with_cross = set()
    products_with_cross_clean = set()
    products_with_statonly = set()
    for p in done:
        pairs = p.get("pairs", [])
        if any(pr["kind"] == "cross_capture" for pr in pairs):
            products_with_cross.add(p["product_id"])
        if any(pr["kind"] == "cross_capture" and not pr["finished_product_flag"] for pr in pairs):
            products_with_cross_clean.add(p["product_id"])
        if any(pr["kind"] == "none" for pr in pairs):
            products_with_statonly.add(p["product_id"])

    print(f"\nregistrable cross_capture pairs: {len(cross)} "
          f"({len(cross_clean)} not finished-product-flagged, "
          f"{n_finished_flagged_pairs} flagged as possible finished-product tail slot)")
    print(f"products with >=1 registrable cross_capture pair: "
          f"{len(products_with_cross)}/{len(done)} = {100*len(products_with_cross)/len(done):.1f}%")
    print(f"products with >=1 registrable pair excluding finished-product-flagged: "
          f"{len(products_with_cross_clean)}/{len(done)} = {100*len(products_with_cross_clean)/len(done):.1f}%")
    print(f"products with >=1 statistics-only (non-registrable) pair candidate: "
          f"{len(products_with_statonly)}/{len(done)} = {100*len(products_with_statonly)/len(done):.1f}%")
    print(f"products flagged opal/streaky caution (title keyword): "
          f"{n_opal_products}/{len(done)} = {100*n_opal_products/len(done):.1f}%")

    same_photo = [pr for pr in all_pairs if pr["kind"] == "same_photo"]
    print(f"\nsame_photo derivation pairs (dedup metadata, not sheet pairs): {len(same_photo)}")

    inl = sorted(pr["inliers"] for pr in cross)
    if inl:
        print(f"\ncross_capture inlier distribution: min={inl[0]} median={inl[len(inl)//2]} "
              f"mean={sum(inl)/len(inl):.1f} max={inl[-1]}")

    stats = {
        "n_products_done": len(done),
        "n_images": sum(n_imgs),
        "images_per_product_mean": sum(n_imgs)/len(n_imgs),
        "products_per_brand": dict(by_brand),
        "capture_type_dist": dict(label_counts),
        "products_multi_capture": multi,
        "products_clean_and_wild": paired,
        "n_pairs_total": len(all_pairs),
        "pair_kind_counts": dict(kind_counts),
        "n_cross_capture": len(cross),
        "n_cross_capture_clean": len(cross_clean),
        "products_with_cross_capture": len(products_with_cross),
        "products_with_cross_capture_clean": len(products_with_cross_clean),
        "products_with_statistics_only": len(products_with_statonly),
        "products_opal_streaky_caution": n_opal_products,
        "n_same_photo": len(same_photo),
    }
    json.dump(stats, open("results/aggregate_033.json", "w"), indent=1)
    print("\nwrote results/aggregate_033.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="results/manifest_033.json")
    args = ap.parse_args()
    main(args.manifest)
