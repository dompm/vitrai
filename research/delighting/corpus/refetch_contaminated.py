#!/usr/bin/env python3
"""refetch_contaminated.py -- one-off recovery script (report 024).

Executes report 019's Patch #1 ("image-pick guard") as a targeted, offline
re-fetch instead of a scraper rewrite. Does NOT modify `build_swatch_library.py`
and does NOT touch `glass_swatch_registry.json` (owned by the scraper agent).

Scope (report 019 Sec 1/2, report 024 task): the 14 registered Bullseye
images where the scraper's `images[0]` rule picked a fired reaction-test-tile
photo instead of the product sheet -- the "Reactive" non-iridescent trio
(Cloud Opalescent / Ice Transparent / Red Reactive, x2 size variants each =
6) plus the entire "Alchemy" line (2 colorways x 2 sizes x iridescent-or-not
= 8).

Pipeline per target:
  1. Join `swatch_quarantine.json` (019) against the registry on this
     taxonomy to build the target list (no hand-picked id list in code).
  2. Fetch the product's live Shopify JSON from shop.bullseyeglass.com
     (same store the scraper hits), by SKU match against the paginated
     `products.json` listing (politely rate-limited, ~1 req/s, same
     User-Agent convention as build_swatch_library.py).
  3. Download every image on the product page (not just position 0).
  4. Run 019's `audit_flagger.analyze_image` + `flag_signals` on each
     candidate; reject any image flagged `test_fire_tiles` (the
     image-heuristic verdict -- name-based reasons like `reaction_demo_line`
     describe the *product line*, not the specific photo, and would reject
     every candidate identically, so those are not used as a per-image
     filter here).
  5. Winner = the LAST (highest-position) surviving candidate -- report
     019's finding is that the real sheet sits at position 2+ once the
     test-fire tile is skipped, so among clean-verdict images this prefers
     the merchandiser's photo furthest from the contaminated lead slot.
  6. If nothing survives, record the product as unrecoverable (no guess).

Write policy: recovered images are saved as NEW files with a `-v2` suffix
into the MAIN checkout's `catalog_images/` -- the existing contaminated
files are left in place (still referenced by the quarantine list and audit
history). `glass_swatch_registry.json` is not edited; `refetch_manifest.json`
is the hand-off artifact for the registry owner.

Usage:
    python3 refetch_contaminated.py [--dry-run] [--out ../results/corpus/refetch_manifest.json]

Requires: requests, PIL, numpy, scipy (the corpus/system python -- see repro
note in reports/024-refetch.md if the project .venv lacks these).
"""
import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")
QUARANTINE_PATH = os.path.join(RESULTS_DIR, "swatch_quarantine.json")
REGISTRY_PATH = os.path.join(REPO_ROOT, "frontend", "public", "assets", "glass_swatch_registry.json")

# The MAIN checkout -- where recovered -v2 images are actually written.
# (This worktree's frontend/public/assets/{catalog_images,glass_swatch_registry.json}
# are read-only symlinks into this same path, per the task's symlink convention.)
MAIN_CHECKOUT = "/Users/dominiquepiche-meunier/Documents/vitraux"
MAIN_CATALOG_DIR = os.path.join(MAIN_CHECKOUT, "frontend", "public", "assets", "catalog_images")

sys.path.insert(0, HERE)
import audit_flagger  # noqa: E402  (analyze_image, flag_signals)

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
STORE_PRODUCTS_URL = "https://shop.bullseyeglass.com/products.json"
REQUEST_DELAY_S = 1.0  # polite rate limit, per task (~1 req/s)


def _get_json(url, retries=3):
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.load(r)
            time.sleep(REQUEST_DELAY_S)
            return data
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(REQUEST_DELAY_S * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def _get_bytes(url, retries=3):
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            time.sleep(REQUEST_DELAY_S)
            return data
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(REQUEST_DELAY_S * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def cache_bullseye_products(cache_path=None):
    """Page through the live Bullseye Shopify products.json (same source the
    scraper uses), politely rate-limited. Cached to disk so re-runs of this
    script don't re-hit the store."""
    if cache_path and os.path.exists(cache_path):
        print(f"using cached product listing: {cache_path}")
        return json.load(open(cache_path))
    products = []
    page = 1
    while page <= 14:
        url = f"{STORE_PRODUCTS_URL}?page={page}&limit=250"
        try:
            data = _get_json(url)
        except RuntimeError as e:
            print(f"  stopping pagination at page {page}: {e}")
            break
        batch = data.get("products", [])
        if not batch:
            break
        products.extend(batch)
        print(f"  cached page {page}: {len(batch)} products (running total {len(products)})")
        page += 1
    if cache_path:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(products, open(cache_path, "w"))
    return products


def build_target_list():
    """Task 1: quarantine entries with test-fire reason codes JOINED to
    registry rows, restricted to report 019's Bullseye reactive
    (non-iridescent) + Alchemy taxonomy -- i.e. the specific smoking-gun
    class report 019 hand-verified as contaminated, not every
    test_fire_tiles hit corpus-wide (that set also includes unrelated
    products like Opaline Opalescent -- out of scope for this recovery)."""
    quarantine = json.load(open(QUARANTINE_PATH))
    registry = json.load(open(REGISTRY_PATH))
    reg_by_id = {r["id"]: r for r in registry}

    targets = []
    for item in quarantine["items"]:
        rid = item.get("id")
        if not rid or item.get("manufacturer") != "Bullseye":
            continue
        if not ({"test_fire_tiles", "reaction_demo_line"} & set(item["reason"])):
            continue
        row = reg_by_id.get(rid)
        if not row:
            continue
        name = (row.get("name") or "").lower()
        is_reactive_non_irid = "reactive" in name and "iridescent" not in name
        is_alchemy = "alchemy" in name
        if not (is_reactive_non_irid or is_alchemy):
            continue
        targets.append({
            "id": rid,
            "base_sku": row["base_sku"],
            "name": row["name"],
            "old_local_image": row["local_image"],
            "old_file": os.path.basename(row["local_image"]),
            "quarantine_reason": item["reason"],
        })
    targets.sort(key=lambda t: t["id"])
    return targets


def pick_best_image(candidates_analyzed):
    """candidates_analyzed: list of dicts with position, url, path, signals,
    reasons (in ascending position order). Winner = last surviving
    (non-test_fire_tiles) candidate."""
    survivors = [c for c in candidates_analyzed if "test_fire_tiles" not in c["reasons"]]
    if not survivors:
        return None
    return survivors[-1]


# --- Human-verification overrides (task step 5: "VERIFY with your own eyes"). ---
# The cheap image heuristic (white-ground + compact-blob signature, report 019) has two
# known false negatives on THIS target set, found by eyeballing every automated pick's
# actual pixels before writing anything: both "Alchemy Clear Silver to Bronze,
# non-iridescent" products (0010160030, 0010160050) only have 2 live product images, and
# BOTH are the same before/after fired-tile demo (one zoomed crop, one zoomed-out crop).
# The zoomed-in crop's two adjoining rectangles merge into a single non-frame-filling
# blob that trips the weaker `product_on_white` bucket instead of `test_fire_tiles` --
# so the automated picker took it as a "winner" even though it is not a sheet at all.
# Overridden to reject (moved to unrecoverable) here, not silently accepted.
#
# Two more picks (0000090030, 0000090050, "Reactive Cloud Opalescent") are genuine
# photos of the actual product sheet (edge-to-edge glass, consistent rounded corners,
# ~85% of the frame) but include a small reaction-demo insert (4 small tiles) in the
# upper-left corner -- a hybrid "sheet + corner call-out" style, not a pure test-fire
# photo and not a pure clean sheet either. Accepted (materially correct vs. the
# pure-demo position-1 they replace) but flagged with an explicit caveat, following
# report 021 Sec 5's precedent of accept-with-caveat over silent accept or blanket
# exclude for borderline real-corpus photography.
MANUAL_REVIEW = {
    "bullseye-0010160030f1010": {
        "verdict": "reject",
        "note": "both live product images are the same before/after fired-tile demo "
                "(different crop/zoom); the 'winner' picked by the automated flagger "
                "(position 1) is NOT a sheet -- flagger false negative, confirmed by eye.",
    },
    "bullseye-0010160050f1010": {
        "verdict": "reject",
        "note": "same before/after demo pair as 0010160030 (same colorway, other size "
                "variant); flagger false negative, confirmed by eye.",
    },
    "bullseye-0000090030f1010": {
        "verdict": "accept_with_caveat",
        "note": "the picked image (position 2) is a genuine photo of the product sheet "
                "(~85% of frame, edge-to-edge, consistent corners) but includes a small "
                "4-tile reaction-demo insert in the upper-left corner -- not a pure "
                "clean sheet, but materially correct vs. the pure test-fire lead photo "
                "it replaces. A center-crop color/texture extractor would not touch the "
                "corner insert.",
    },
    "bullseye-0000090050f1010": {
        "verdict": "accept_with_caveat",
        "note": "same hybrid sheet+corner-demo composite style as 0000090030 (same "
                "product line, other size variant).",
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(RESULTS_DIR, "refetch_manifest.json"))
    ap.add_argument("--cache", default=os.path.join(HERE, "_refetch_cache"),
                     help="scratch dir for cached product listing + downloaded candidates")
    ap.add_argument("--dry-run", action="store_true",
                     help="do everything except write -v2 files into the main checkout")
    args = ap.parse_args()

    os.makedirs(args.cache, exist_ok=True)
    os.makedirs(MAIN_CATALOG_DIR, exist_ok=True)

    targets = build_target_list()
    print(f"target list: {len(targets)} registered contaminated images "
          f"(Bullseye reactive-non-iridescent + Alchemy, report 019 taxonomy)")
    for t in targets:
        print(f"  {t['id']:35s} {t['name']}")

    print("\nfetching live Bullseye product catalog (paginated, rate-limited)...")
    products = cache_bullseye_products(os.path.join(args.cache, "bullseye_products.json"))
    print(f"cached {len(products)} live products")

    sku_index = {}
    for p in products:
        for v in p.get("variants", []):
            sku = (v.get("sku") or "").upper()
            if sku:
                sku_index[sku] = p

    manifest_entries = []
    unrecoverable = []

    for t in targets:
        sku = t["base_sku"].upper()
        product = sku_index.get(sku)
        if not product:
            print(f"\n[{t['id']}] SKU {sku} not found in live catalog -- unrecoverable")
            unrecoverable.append({**t, "reason": "sku_not_found_in_live_catalog"})
            continue

        handle = product["handle"]
        product_url = f"https://shop.bullseyeglass.com/products/{handle}"
        images = product.get("images", [])
        print(f"\n[{t['id']}] SKU {sku} -> {handle} ({len(images)} images)")

        analyzed = []
        for pos, im in enumerate(images, start=1):
            src = im.get("src", "")
            if src.startswith("//"):
                src = "https:" + src
            cand_path = os.path.join(args.cache, f"{t['id']}_p{pos}.jpg")
            if not os.path.exists(cand_path):
                try:
                    data = _get_bytes(src)
                except RuntimeError as e:
                    print(f"    pos {pos}: download failed ({e})")
                    continue
                with open(cand_path, "wb") as f:
                    f.write(data)
            try:
                sig = audit_flagger.analyze_image(cand_path)
                reasons = audit_flagger.flag_signals(sig)
            except Exception as e:  # noqa: BLE001
                print(f"    pos {pos}: flagger error ({e})")
                continue
            print(f"    pos {pos}: {src.split('/')[-1]:40s} reasons={reasons or ['clean']}")
            analyzed.append({
                "position": pos, "url": src, "path": cand_path,
                "signals": sig, "reasons": reasons,
            })

        winner = pick_best_image(analyzed)
        override = MANUAL_REVIEW.get(t["id"])

        if winner is None:
            print(f"  -> UNRECOVERABLE: no candidate image passed the flagger (reject test_fire_tiles)")
            unrecoverable.append({
                **t, "reason": "no_candidate_passed_flagger",
                "product_url": product_url,
                "candidates": [{"position": c["position"], "url": c["url"],
                                 "reasons": c["reasons"]} for c in analyzed],
            })
            continue

        if override and override["verdict"] == "reject":
            print(f"  -> UNRECOVERABLE (human-verification override): {override['note']}")
            unrecoverable.append({
                **t, "reason": "human_verification_rejected_automated_pick",
                "product_url": product_url,
                "automated_pick_position": winner["position"],
                "override_note": override["note"],
                "candidates": [{"position": c["position"], "url": c["url"],
                                 "reasons": c["reasons"]} for c in analyzed],
            })
            continue

        new_file = f"{t['old_file'].rsplit('.', 1)[0]}-v2.jpg"
        dest_path = os.path.join(MAIN_CATALOG_DIR, new_file)
        print(f"  -> WINNER: position {winner['position']} "
              f"({'no flags' if not winner['reasons'] else winner['reasons']}) -> {new_file}"
              + (f"  [CAVEAT: {override['note']}]" if override else ""))

        if not args.dry_run:
            from PIL import Image
            img = Image.open(winner["path"])
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(dest_path, "JPEG", quality=85)  # match existing corpus's typical encoding

        manifest_entries.append({
            "old_id": t["id"],
            "old_file": t["old_file"],
            "new_file": new_file,
            "manufacturer": "Bullseye",
            "name": t["name"],
            "base_sku": t["base_sku"],
            "product_url": product_url,
            "image_position_picked": winner["position"],
            "n_candidate_images": len(images),
            "flagger_verdict": winner["reasons"] or ["clean"],
            "flagger_signals": winner["signals"],
            "quarantine_reason_original": t["quarantine_reason"],
            "human_verification_caveat": override["note"] if override else None,
        })

    out = {
        "definition": "Report 024 -- targeted re-fetch of the 14 registered Bullseye "
                       "reactive(non-iridescent)/Alchemy images report 019 identified as "
                       "test-fire-tile contamination (019's smoking gun). Executes 019 "
                       "Patch #1 as a one-off recovery, not a scraper rewrite. Does NOT "
                       "edit glass_swatch_registry.json -- registry integration is the "
                       "scraper owner's, this manifest is the bridge.",
        "n_targets": len(targets),
        "n_recovered": len(manifest_entries),
        "n_unrecoverable": len(unrecoverable),
        "recovered": manifest_entries,
        "unrecoverable": unrecoverable,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nrecovered {len(manifest_entries)}/{len(targets)}, "
          f"{len(unrecoverable)} unrecoverable -> {args.out}")


if __name__ == "__main__":
    main()
