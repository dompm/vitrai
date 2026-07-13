#!/usr/bin/env python3
"""Iteration 044 -- physical-piece-verified pair assembly for the coglassworks
harvest.

Inputs: results/census_044.json (grouper fields included) + downloaded images
under data/images/<handle>/. Outputs results/pairs_044.json:

  pieces:  every piece token with >=2 downloaded images, its verification
           tier (identity_grouper.py), and a per-image capture-condition
           label from realpairs/classify.py's calibrated heuristic (run at
           full res; taxonomy transfer caveat: that classifier was calibrated
           on Delphi's house style -- report 041 SS6.1 expects it to transfer
           with 'window'/'shop'/'closeup' doing the work and 'lightbox'
           essentially absent here; precision on THIS store is measured by
           the 044 hand-check, not assumed).
  pairs:   all within-piece image pairs, each labeled
           cross_condition (different capture labels) or same_condition.
  registry_candidates: coglassworks listings that PLAUSIBLY map to
           frontend's glass_swatch_registry.json entries -- brand+style-code
           or brand+name candidates, FLAGGED NOT ASSERTED (the name-collision
           rule from report 041 SS3 stands: never treat a name match as
           identity).

Camera-roll ("unverified") images never enter `pairs`.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "realpairs"))

from identity_grouper import group_listing_images  # noqa: E402
from classify import analyze_image, classify  # noqa: E402

CENSUS = os.path.join(HERE, "results", "census_044.json")
REGISTRY = os.path.join(HERE, "data_registry_snapshot.json")
IMG_ROOT = os.path.join(HERE, "data", "images")
OUT = os.path.join(HERE, "results", "pairs_044.json")

BRANDS = {
    "bullseye": "Bullseye", "wissmach": "Wissmach", "youghiogheny": "Youghiogheny",
    "oceanside": "Oceanside", "spectrum": "Oceanside",  # Spectrum became Oceanside
}
STOPWORDS = {"glass", "stained", "sheet", "fusible", "coe", "90", "96", "the",
             "and", "on", "of", "vintage", "iridescent", "irid"}


def brand_of(product):
    v = (product.get("vendor") or "").lower()
    for k, b in BRANDS.items():
        if k in v:
            return b, "vendor"
    t = (product.get("title") or "").lower() + " " + product["handle"].lower()
    for k, b in BRANDS.items():
        if k in t:
            return b, "title"
    return None, None


STYLE_CODE_RE = re.compile(r"\(([A-Za-z0-9 .\-/]{3,20})\)")


def norm_tokens(s):
    return {w for w in re.findall(r"[a-z]+", (s or "").lower())
            if len(w) > 2 and w not in STOPWORDS}


def build_registry_index():
    with open(REGISTRY) as f:
        reg = json.load(f)
    by_brand = {}
    for e in reg:
        by_brand.setdefault(e["manufacturer"], []).append({
            "id": e["id"], "sku": e.get("resolved_sku") or e.get("base_sku"),
            "name": e.get("resolved_name") or e.get("name"),
            "tokens": norm_tokens(e.get("resolved_name") or e.get("name")),
        })
    return by_brand


def registry_candidates(product, by_brand):
    brand, basis = brand_of(product)
    if not brand or brand not in by_brand:
        return []
    title = product.get("title") or ""
    out = []
    # (a) embedded style code in the title, normalized alnum-only compare
    for code in STYLE_CODE_RE.findall(title):
        code_n = re.sub(r"[^A-Z0-9]", "", code.upper())
        if len(code_n) < 3:
            continue
        for e in by_brand[brand]:
            sku_n = re.sub(r"[^A-Z0-9]", "", (e["sku"] or "").upper())
            if sku_n and (code_n in sku_n or sku_n in code_n):
                out.append({"registry_id": e["id"], "basis": "brand+style_code",
                            "style_code": code, "registry_sku": e["sku"],
                            "brand": brand, "brand_basis": basis})
    # (b) brand + name-token overlap (candidate ONLY -- report 041 SS3)
    ttoks = norm_tokens(title)
    if len(ttoks) >= 2:
        for e in by_brand[brand]:
            inter = ttoks & e["tokens"]
            if len(inter) >= max(2, min(len(ttoks), len(e["tokens"])) - 1) \
                    and len(inter) >= 2:
                out.append({"registry_id": e["id"], "basis": "brand+name_candidate",
                            "shared_tokens": sorted(inter),
                            "registry_name": e["name"],
                            "brand": brand, "brand_basis": basis})
    return out


def main():
    with open(CENSUS) as f:
        census = json.load(f)
    products = census["products"]
    by_brand = build_registry_index()

    feat_cache_path = os.path.join(HERE, "results", "capture_labels_044.json")
    labels = {}
    if os.path.exists(feat_cache_path):
        with open(feat_cache_path) as f:
            labels = json.load(f)

    pieces = []
    pairs = []
    crossref = []
    n_missing = 0
    t0 = time.time()

    for idx, p in enumerate(products):
        handle = p["handle"]
        fnames = [im["src"] for im in p["images"]]
        skus = [v["sku"] for v in p["variants"] if v.get("sku")]
        res = group_listing_images(handle, fnames, variant_skus=skus)

        cands = registry_candidates(p, by_brand)
        if cands:
            crossref.append({"handle": handle, "title": p.get("title"),
                             "vendor": p.get("vendor"), "candidates": cands})

        for token, files in res.groups.items():
            local = []
            for f in files:
                base = os.path.basename(f.split("?")[0])
                path = os.path.join(IMG_ROOT, handle, base)
                if os.path.exists(path) and os.path.getsize(path) > 1000:
                    local.append((base, path))
                else:
                    n_missing += 1
            if len(local) < 2:
                continue
            img_labels = {}
            for base, path in sorted(local):
                key = f"{handle}/{base}"
                if key not in labels:
                    lab, conf, why = classify(analyze_image(path))
                    labels[key] = {"label": lab, "conf": round(float(conf), 3)}
                img_labels[base] = labels[key]
            piece = {"handle": handle, "token": token, "tier": res.tiers[token],
                     "images": {b: img_labels[b] for b, _ in sorted(local)}}
            pieces.append(piece)
            bases = sorted(b for b, _ in local)
            for i in range(len(bases)):
                for j in range(i + 1, len(bases)):
                    la, lb = img_labels[bases[i]]["label"], img_labels[bases[j]]["label"]
                    pairs.append({
                        "handle": handle, "token": token, "tier": res.tiers[token],
                        "a": bases[i], "b": bases[j],
                        "capture_a": la, "capture_b": lb,
                        "pair_class": "cross_condition" if la != lb else "same_condition",
                    })
        if (idx + 1) % 100 == 0:
            print(f"[{idx + 1}/{len(products)}] pieces={len(pieces)} "
                  f"pairs={len(pairs)} ({time.time() - t0:.0f}s)", flush=True)
            with open(feat_cache_path, "w") as f:
                json.dump(labels, f)

    with open(feat_cache_path, "w") as f:
        json.dump(labels, f)

    from collections import Counter
    agg = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_pieces_with_2plus_local_images": len(pieces),
        "n_pairs": len(pairs),
        "n_images_missing_on_disk": n_missing,
        "pairs_by_class": dict(Counter(pr["pair_class"] for pr in pairs)),
        "pairs_by_tier": dict(Counter(pr["tier"] for pr in pairs)),
        "cross_condition_by_tier": dict(Counter(
            pr["tier"] for pr in pairs if pr["pair_class"] == "cross_condition")),
        "capture_label_mix": dict(Counter(
            v["label"] for v in labels.values())),
        "n_registry_candidate_listings": len(crossref),
        "n_registry_style_code_listings": sum(
            1 for c in crossref
            if any(x["basis"] == "brand+style_code" for x in c["candidates"])),
    }
    with open(OUT, "w") as f:
        json.dump({"aggregate": agg, "pieces": pieces, "pairs": pairs,
                   "registry_candidates": crossref}, f, indent=1)
    print(json.dumps(agg, indent=2))


if __name__ == "__main__":
    main()
