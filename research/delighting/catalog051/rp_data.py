#!/usr/bin/env python3
"""Report 051 — realpairs benchmark data assembly.

Reads the restored 033 harvest (per-product images with capture_type), applies
the report-033 contamination screens (dataset card §9.3), reconstructs local
image paths, and splits each product's surviving images into REFERENCE (clean:
closeup/lightbox — the catalog target) and WILD (window/shop — the user's photo).

wild -> clean is the product-identification direction: query = wild capture,
target = the product's clean capture(s). The frozen 034 holdout tag is attached
per product for comparability (retrieval here is zero-shot / training-free, so
there is no train->test leak — the tag is reported, not used to hide data).
"""
import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RP = os.path.join(HERE, "..", "realpairs")
FROZEN_MANIFEST = os.path.join(RP, "results", "manifest_033.json")
CONTAM = os.path.join(RP, "results", "contamination_033.json")

CLEAN_CAPTURES = {"closeup", "lightbox"}
WILD_CAPTURES = {"window", "shop", "shop_held", "standing"}
PRODUCT_KILL_FLAGS = {"non_transmissive_mirror", "multi_sheet_listing"}


def image_local_path(img_root, product_id, image_key):
    if image_key == "hero":
        return os.path.join(img_root, str(product_id), "hero_full.jpg")
    if image_key.startswith("gallery_"):
        n = image_key.split("_", 1)[1]
        return os.path.join(img_root, str(product_id), f"g{n}_full.jpg")
    return None


def holdout_reserved(product_id):
    """Frozen 034 base rule (EVAL_PROTOCOL §3c): sha1(pid)%5==0. (The v1.1
    per-brand top-ups add 3 specific pids; included explicitly.)"""
    h = int(hashlib.sha1(str(product_id).encode()).hexdigest(), 16)
    topups = {"239270", "203533", "220043"}
    return (h % 5 == 0) or (str(product_id) in topups)


def load_manifest(manifest_path=None):
    return json.load(open(manifest_path or FROZEN_MANIFEST))


def load_contam(contam_path=None):
    return json.load(open(contam_path or CONTAM))


def build_image_table(img_root, manifest_path=None, contam_path=None,
                      require_on_disk=True):
    """Returns (products, images) where products is a dict pid->meta and images
    is a list of per-image dicts with role in {reference, wild, excluded}."""
    manifest = load_manifest(manifest_path)
    contam = load_contam(contam_path)
    cprods = contam.get("products", {})

    products = {}
    images = []
    for p in manifest:
        pid = str(p["product_id"])
        if p.get("status") != "done":
            continue
        pflags = set(cprods.get(pid, {}).get("flags", []))
        killed_product = bool(pflags & PRODUCT_KILL_FLAGS)
        img_flags = cprods.get(pid, {}).get("images", {})
        pmeta = {
            "product_id": pid, "brand": p.get("brand"), "title": p.get("title"),
            "opal_streaky_caution": bool(p.get("opal_streaky_caution")),
            "holdout": holdout_reserved(pid),
            "product_killed": killed_product,
            "product_flags": sorted(pflags),
            "n_reference": 0, "n_wild": 0,
        }
        for im in p.get("images", []):
            key = im["image_key"]
            cap = im.get("capture_type")
            path = image_local_path(img_root, pid, key)
            on_disk = bool(path) and os.path.exists(path)
            im_contam = list(img_flags.get(key, []))
            role = "excluded"
            reason = None
            if killed_product:
                reason = "product_" + ("+".join(sorted(pflags)))
            elif im_contam:
                reason = "img_" + "+".join(im_contam)
            elif cap in CLEAN_CAPTURES:
                role = "reference"
            elif cap in WILD_CAPTURES:
                role = "wild"
            else:
                reason = f"capture_{cap}"
            if require_on_disk and not on_disk:
                # cannot embed what is not restored; mark separately
                role = "excluded"
                reason = (reason + ";" if reason else "") + "not_on_disk"
            rec = {
                "product_id": pid, "image_key": key, "capture_type": cap,
                "capture_conf": im.get("capture_conf"), "path": path,
                "on_disk": on_disk, "role": role, "exclude_reason": reason,
                "brand": p.get("brand"),
                "opal_streaky_caution": pmeta["opal_streaky_caution"],
                "holdout": pmeta["holdout"],
            }
            if role == "reference":
                pmeta["n_reference"] += 1
            elif role == "wild":
                pmeta["n_wild"] += 1
            images.append(rec)
        products[pid] = pmeta

    for pid, pm in products.items():
        pm["scorable"] = pm["n_reference"] >= 1 and pm["n_wild"] >= 1
    return products, images


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--img-root", default=os.path.join(RP, "data", "images"))
    ap.add_argument("--manifest", default=None)
    args = ap.parse_args()
    prods, imgs = build_image_table(args.img_root, manifest_path=args.manifest)
    on_disk = [i for i in imgs if i["on_disk"]]
    ref = [i for i in imgs if i["role"] == "reference"]
    wild = [i for i in imgs if i["role"] == "wild"]
    scorable = [p for p in prods.values() if p["scorable"]]
    print(f"products: {len(prods)} | scorable (>=1 ref & >=1 wild on disk): {len(scorable)}")
    print(f"images: {len(imgs)} total, {len(on_disk)} on disk | "
          f"reference={len(ref)} wild={len(wild)}")
    print(f"scorable in holdout: {sum(1 for p in scorable if p['holdout'])}")
    print(f"scorable opal-caution: {sum(1 for p in scorable if p['opal_streaky_caution'])}")
    import collections
    print("scorable per brand:", dict(collections.Counter(p['brand'] for p in scorable)))
