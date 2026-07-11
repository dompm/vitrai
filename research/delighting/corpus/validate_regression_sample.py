#!/usr/bin/env python3
"""validate_regression_sample.py -- swatch_picker acceptance test #3 (report 035).

"The picker must not break the easy majority": sample 20 random products from the
existing (non-quarantined) catalog registry, fetch each product's LIVE full gallery
(politely, ~1 req/s, cached -- both shop.bullseyeglass.com and
stainedglassexpress.com, per Finding 4 of glass-library-integration-review.md, front
every manufacturer in this registry as Shopify stores), run swatch_picker.pick(), and
report the agreement rate against `images[0]` (position 1) -- the position our
existing registry actually shipped, and which is correct for the overwhelming
majority of non-quarantined products (report 019: pooled contamination 4.4%).

Writes ../results/corpus/swatch_picker_regression_sample.json.
"""
import json
import os
import random

import fetch_gallery
from swatch_picker import pick

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")
CACHE_DIR = os.path.join(RESULTS_DIR, "swatch_picker_cache")
REGISTRY_PATH = "/Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/glass_swatch_registry.json"
QUARANTINE_PATH = os.path.join(RESULTS_DIR, "swatch_quarantine.json")

N_SAMPLE = 20
SEED = 42


def main():
    registry = json.load(open(REGISTRY_PATH))
    quarantine = json.load(open(QUARANTINE_PATH))
    quarantined_ids = {x["id"] for x in quarantine["items"] if x.get("id")}
    pool = [x for x in registry if x["id"] not in quarantined_ids]
    random.seed(SEED)
    sample = random.sample(pool, N_SAMPLE)

    os.makedirs(CACHE_DIR, exist_ok=True)
    results = []
    n_agree = 0
    n_ok = 0
    for row in sample:
        try:
            g = fetch_gallery.fetch_gallery(row["product_url"], CACHE_DIR)
        except Exception as e:
            print(f"FETCH FAIL {row['id']}: {e}")
            results.append({"id": row["id"], "error": str(e)})
            continue
        if not g["images"]:
            print(f"NO IMAGES {row['id']}")
            continue
        text = g["title"] + ". " + g["body_html"]
        result = pick(g["images"], text=text, name=row.get("name"), manufacturer=row.get("manufacturer"))
        picked = result["pick"]
        agree = picked == 0
        n_agree += int(agree)
        n_ok += 1
        print(f"{row['id']:35s} {row['manufacturer']:12s} n_img={len(g['images'])}  "
              f"pick={picked}  agree_with_pos1={agree}")
        results.append({
            "id": row["id"], "manufacturer": row["manufacturer"], "name": row.get("name"),
            "product_url": row["product_url"], "n_images": len(g["images"]),
            "picked_position": (picked + 1) if picked is not None else None,
            "agree_with_position1": agree,
            "scores": [{"position": s["position"], "final_score": s["final_score"]}
                       for s in result["scores"]],
        })

    agreement_rate = n_agree / n_ok if n_ok else 0.0
    print(f"\nn={n_ok}  agree_with_position1={n_agree}  rate={agreement_rate:.2%}")
    out = {"n_sample": N_SAMPLE, "seed": SEED, "n_fetched_ok": n_ok,
           "n_agree_with_position1": n_agree, "agreement_rate": round(agreement_rate, 4),
           "results": results}
    out_path = os.path.join(RESULTS_DIR, "swatch_picker_regression_sample.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
