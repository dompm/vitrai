#!/usr/bin/env python3
"""Step 5: aggregate yield stats and emit the final verified per-product
image sets (verified_sets.json) with context labels + source URLs."""
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
RESULTS = HERE / "results"


def main():
    manifest = json.loads((RESULTS / "downloaded_manifest.json").read_text())
    verif = json.loads((RESULTS / "vlm_verifications.json").read_text())

    verified_sets = {}
    ctx_counter = Counter()
    per_product = []

    for pid, entry in manifest.items():
        v = verif.get(pid, {})
        vmap = {item["index"]: item for item in v.get("verifications", [])}
        images = entry["images"]
        matches = []
        for i, im in enumerate(images, start=2):
            info = vmap.get(i)
            if info and info.get("match"):
                matches.append(
                    {
                        "file": im["file"],
                        "url": im["url"],
                        "source_page": im["source_page"],
                        "title": im["title"],
                        "context": info.get("context"),
                        "confidence": info.get("confidence"),
                        "reason": info.get("reason"),
                    }
                )
                ctx_counter[info.get("context") or "?"] += 1
        verified_sets[pid] = {"product": entry["product"], "verified_images": matches}
        ctxs = Counter(m["context"] for m in matches)
        n_ctx_classes = len(ctxs)
        per_product.append(
            {
                "pid": pid,
                "n_candidates": len(images),
                "n_verified": len(matches),
                "contexts": dict(ctxs),
                "n_context_classes": n_ctx_classes,
                "multi_context": n_ctx_classes >= 2,
                "elapsed_s": v.get("elapsed_s"),
            }
        )

    (RESULTS / "verified_sets.json").write_text(json.dumps(verified_sets, indent=2))

    print(f"{'pid':<28} {'cand':>4} {'verif':>5} {'multi':>5}  contexts")
    for p in per_product:
        print(
            f"{p['pid']:<28} {p['n_candidates']:>4} {p['n_verified']:>5} "
            f"{'YES' if p['multi_context'] else 'no':>5}  {p['contexts']}"
        )
    total_v = sum(p["n_verified"] for p in per_product)
    total_c = sum(p["n_candidates"] for p in per_product)
    multi = sum(1 for p in per_product if p["multi_context"])
    print(f"\nTOTAL verified {total_v}/{total_c} candidates "
          f"({total_v/len(per_product):.1f}/product); "
          f"{multi}/{len(per_product)} products multi-context")
    print("Context mix:", dict(ctx_counter))
    times = [p["elapsed_s"] for p in per_product if p["elapsed_s"]]
    if times:
        print(f"VLM time/product: mean {sum(times)/len(times):.0f}s, "
              f"min {min(times):.0f}s, max {max(times):.0f}s")

    (RESULTS / "aggregate_042.json").write_text(
        json.dumps(
            {
                "per_product": per_product,
                "context_mix": dict(ctx_counter),
                "total_verified": total_v,
                "total_candidates": total_c,
                "products_multi_context": multi,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
