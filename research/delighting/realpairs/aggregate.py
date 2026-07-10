#!/usr/bin/env python3
"""Iteration 030 -- aggregate census.json into the headline numbers for report 030."""
import argparse
import json
from collections import Counter, defaultdict


def main(census_path, manifest_path):
    census = json.load(open(census_path))
    manifest = json.load(open(manifest_path))

    # Coverage caveat: how many manifest entries got n_images==0 because the only
    # available Wayback snapshot predates this parser's (2019+) template.
    stale = [m for m in manifest if m.get("n_images") == 0 and m.get("snapshot_ts", "9") < "2015"]
    zero_recent = [m for m in manifest if m.get("n_images") == 0 and m.get("snapshot_ts", "9") >= "2015"]
    errored = [m for m in manifest if "error" in m]

    n = len(census)
    with_images = [c for c in census if c["n_images"] > 0]
    n_imgs = [c["n_images"] for c in with_images]
    n_distinct = [c["n_distinct"] for c in with_images]
    multi = [c for c in with_images if c["n_distinct"] >= 2]

    print(f"census products (parsed, n_images>0): {len(with_images)} / {n} manifest rows")
    print(f"  (excluded: {len(stale)} stale pre-2015-template snapshots, "
          f"{len(zero_recent)} recent-snapshot-but-0-images [likely genuinely single-image "
          f"or a parse gap], {len(errored)} fetch errors)")
    print(f"images/product: mean={sum(n_imgs)/len(n_imgs):.2f} median={sorted(n_imgs)[len(n_imgs)//2]} "
          f"min={min(n_imgs)} max={max(n_imgs)}")
    print(f"products with >=2 DISTINCT capture types (heuristic labels): "
          f"{len(multi)}/{len(with_images)} = {100*len(multi)/len(with_images):.1f}%")

    label_counts = Counter()
    for c in with_images:
        for cl in c["classifications"]:
            label_counts[cl["label"]] += 1
    print("\nper-image label distribution (heuristic, all images):")
    total_imgs = sum(label_counts.values())
    for lab, cnt in label_counts.most_common():
        print(f"  {lab:10s} {cnt:5d}  {100*cnt/total_imgs:.1f}%")

    pair_type_counts = Counter()
    for c in with_images:
        labs = c["distinct_capture_types"]
        if len(labs) < 2:
            continue
        for i in range(len(labs)):
            for j in range(i + 1, len(labs)):
                pair_type_counts[tuple(sorted((labs[i], labs[j])))] += 1
    print("\ndistinct-capture-type-pair co-occurrence (per product, unordered):")
    for pair, cnt in pair_type_counts.most_common():
        print(f"  {pair[0]:10s} x {pair[1]:10s}  {cnt}")

    by_brand = defaultdict(list)
    for c in with_images:
        by_brand[c["brand"]].append(c)
    print("\nper-brand: n products, mean images/product, % with >=2 capture types")
    for brand, items in sorted(by_brand.items(), key=lambda kv: -len(kv[1])):
        m = sum(1 for c in items if c["n_distinct"] >= 2)
        mean_imgs = sum(c["n_images"] for c in items) / len(items)
        print(f"  {brand:24s} n={len(items):4d} mean_imgs={mean_imgs:.1f} "
              f"multi={m}/{len(items)}={100*m/len(items):.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default="results/census.json")
    ap.add_argument("--manifest", default="results/product_manifest.json")
    args = ap.parse_args()
    main(args.census, args.manifest)
