#!/usr/bin/env python3
"""Iteration 044 -- full coglassworks.com sheet-glass census via the store's
documented JSON API.

Access posture (report 041 SS1/SS7, maintainer-approved 2026-07-12): the
store's robots.txt links to /agents.md, which documents read-only
GET /collections/{handle}/products.json access for agents. Discovery uses
ONLY that endpoint -- six-ish paginated requests at ~1 req/s with a
descriptive UA carrying a contact email. Zero HTML page loads.

Output: results/census_044.json -- every product record with body_html
stripped (bulky, low-value; the approx-size line is extracted first), plus
per-listing identity-grouper results (piece groups / unverified buckets) and
aggregate stats. This file is COMMITTED (metadata posture per
REAL_PAIRS_DATASET.md SS5 / SS9.5); raw images are handled by download_044.py
and never committed.
"""
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from identity_grouper import group_listing_images, classify_listing  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "research-delighting-044 (stained-glass material research, internal eval; "
      "contact: dompm@hotmail.com)")

COLLECTION_URL = "https://coglassworks.com/collections/sheet-glass/products.json?limit=250&page={page}"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results", "census_044.json")

APPROX_RE = re.compile(r"approx\.?\s*size:?\s*([^<\n]+)", re.IGNORECASE)


def fetch_json(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"  retry {attempt + 1} after error: {e}", flush=True)
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}")


def slim_product(p):
    body = p.get("body_html") or ""
    m = APPROX_RE.search(body)
    return {
        "id": p["id"],
        "handle": p["handle"],
        "title": p.get("title"),
        "vendor": p.get("vendor"),
        "product_type": p.get("product_type"),
        "tags": p.get("tags", []),
        "approx_size": m.group(1).strip() if m else None,
        "published_at": p.get("published_at"),
        "variants": [
            {"sku": v.get("sku"), "title": v.get("title"), "price": v.get("price"),
             "available": v.get("available")}
            for v in p.get("variants", [])
        ],
        "images": [
            {"position": im.get("position"), "src": im.get("src"),
             "width": im.get("width"), "height": im.get("height")}
            for im in p.get("images", [])
        ],
    }


def fetch_all_products():
    products = []
    seen_ids = set()
    page = 1
    while True:
        url = COLLECTION_URL.format(page=page)
        print(f"page {page} ...", flush=True)
        data = fetch_json(url)
        batch = data.get("products", [])
        if not batch:
            break
        for p in batch:
            if p["id"] in seen_ids:
                continue
            seen_ids.add(p["id"])
            products.append(slim_product(p))
        page += 1
        time.sleep(1.0)
        if page > 20:  # safety valve; catalog is ~6 pages
            break
    return products


def main():
    if "--regroup" in sys.argv:
        # Recompute grouper fields + aggregate from the already-fetched
        # census on disk -- zero network traffic (used after grouper fixes).
        with open(OUT) as f:
            products = json.load(f)["products"]
        print(f"regrouping {len(products)} products from disk", flush=True)
    else:
        products = fetch_all_products()
    print(f"{len(products)} unique products", flush=True)

    # Run the identity grouper over every listing.
    stats = {"multi_piece_sku_named": 0, "single_piece_sku_named": 0,
             "mixed_convention": 0, "unverified_camera_roll": 0,
             "unverified_other": 0}
    tier_tokens = {}
    tier_pairs = {}
    n_pieces = 0
    n_pieces_2plus = 0
    n_within_piece_pairs = 0
    n_images_total = 0
    for p in products:
        fnames = [im["src"] for im in p["images"]]
        n_images_total += len(fnames)
        skus = [v["sku"] for v in p["variants"] if v.get("sku")]
        res = group_listing_images(p["handle"], fnames, variant_skus=skus)
        bucket = classify_listing(res)
        stats[bucket] += 1
        n_pieces += res.piece_count
        for token, files in res.groups.items():
            tier = res.tiers[token]
            tier_tokens[tier] = tier_tokens.get(tier, 0) + 1
            if len(files) >= 2:
                n_pieces_2plus += 1
                n = len(files)
                npair = n * (n - 1) // 2
                n_within_piece_pairs += npair
                tier_pairs[tier] = tier_pairs.get(tier, 0) + npair
        p["grouper"] = {
            "bucket": bucket,
            "groups": {t: [os.path.basename(f).split("?")[0] for f in fs]
                        for t, fs in res.groups.items()},
            "tiers": res.tiers,
            "unverified": [os.path.basename(f).split("?")[0] for f in res.unverified],
        }

    aggregate = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_products": len(products),
        "n_images": n_images_total,
        "listing_buckets": stats,
        "n_distinct_piece_tokens": n_pieces,
        "n_pieces_with_2plus_images": n_pieces_2plus,
        "n_within_piece_pairs": n_within_piece_pairs,
        "piece_tokens_by_tier": tier_tokens,
        "pairs_by_tier": tier_pairs,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump({"aggregate": aggregate, "products": products}, f, indent=1)
    print(json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
