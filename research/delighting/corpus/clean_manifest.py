#!/usr/bin/env python3
"""Task A (report 021): CANONICAL CLEAN CORPUS DEFINITION.

Builds `results/corpus/clean_manifest.json`, the single authoritative
definition of "the clean real-glass corpus" that every future delighting
experiment against the catalog corpus should load, instead of re-deriving
its own ad hoc filter. Composed from three prior reports' findings, applied
in this order:

  1. START: registry-recoverable images (015 census.py's `per_image_class.json`
     -- exact registry match OR fuzzy same-SKU size-variant recovery). This
     already excludes the 236 sge-* files and the 111 other no-metadata
     files, since sge/no-metadata images never get a `per_image_class` entry
     in the first place (015 Sec 1: SGE has 0% registry coverage).
  2. MINUS sge-* (belt-and-suspenders re-check by filename prefix -- 019's
     verdict that all sge-* are orphaned/unreliable junk not worth carrying
     even if some future census change ever gave them a fuzzy match).
  3. MINUS quarantine (019's swatch_quarantine.json, all 168 advisory-flagged
     files, all reason codes -- test_fire_tiles, reaction_demo_line,
     composite_streamer_line, AND product_on_white). The last of these is
     "weak/advisory" per 019 (some are legitimate pale front-lit sheets, not
     junk), but this manifest is meant to be a conservative, safe-by-default
     corpus: anything the flagger raised a hand about is out. The script
     also reports the size of the manifest if product_on_white were NOT
     excluded, so downstream users can see the sensitivity of this choice.
  4. MINUS hash-duplicates: byte-identical files, deduplicated by SHA-256
     content hash (NOT by SKU/filename). This is the general form of 019's
     "72 duplicate-image groups / 145 registry rows" finding (Bullseye
     reuses one photograph across a color's thickness variants, which are
     DIFFERENT registry rows/SKUs) -- but hashing over the whole
     registry-recoverable set also naturally absorbs the expected, much
     larger volume of same-SKU size-variant duplication (f1010/ffull/fhalf
     are verified byte-identical copies of the same photo, not actual
     distinct crops -- see report). One canonical file is kept per hash
     group; canonical choice prefers an `exact` registry match over a
     `fuzzy-size-variant` one, tie-broken by shortest-then-lexicographic
     filename for determinism. All group members (and every registry id
     that maps to the group) are recorded for traceability.

Output: results/corpus/clean_manifest.json --
  {
    "n_clean": ...,
    "counts_by_manufacturer": {...},
    "counts_by_class": {...},
    "counts_by_manufacturer_class": {...},
    "counts_by_confidence": {...},
    "exclusions": {"sge": n, "quarantine": n, "hash_duplicate": n},
    "sensitivity_without_product_on_white_exclusion": n,
    "images": [ {file, manufacturer, category, name, extractor_class,
                 confidence, rule, match_kind, registry_id, group_size,
                 group_members: [...], group_registry_ids: [...]} , ... ]
  }

Usage: python3 clean_manifest.py [--out results/corpus/clean_manifest.json]
"""
import argparse
import collections
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CATALOG_DIR = os.path.join(REPO_ROOT, "frontend", "public", "assets", "catalog_images")
REGISTRY_PATH = os.path.join(REPO_ROOT, "frontend", "public", "assets", "glass_swatch_registry.json")
RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")
PER_IMAGE_CLASS = os.path.join(RESULTS_DIR, "per_image_class.json")
QUARANTINE = os.path.join(RESULTS_DIR, "swatch_quarantine.json")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(RESULTS_DIR, "clean_manifest.json"))
    args = ap.parse_args()

    per_image = json.load(open(PER_IMAGE_CLASS))
    print(f"registry-recoverable (015 census): {len(per_image)} files")

    # filename -> registry id, for group traceability (best-effort: the exact
    # match's own id if the census kept it; fuzzy-matched files borrow their
    # matched row's fields but census.py doesn't store the row's `id` --
    # rebuild a filename -> id index straight from the registry + fuzzy logic
    # equivalent used in census.py so every file gets an id.)
    registry = json.load(open(REGISTRY_PATH))
    exact_id_by_file = {e["local_image"].split("/")[-1]: e["id"] for e in registry}

    import re
    SIZE_VARIANT_SUFFIXES = [r"f1010$", r"fhalf$", r"ffull$", r"6x12$", r"6x8$", r"grp$", r"_8s$"]

    def base_key(stem):
        for pat in SIZE_VARIANT_SUFFIXES:
            s2 = re.sub(pat, "", stem)
            if s2 != stem:
                return s2
        return stem

    fuzzy_index = collections.defaultdict(list)
    for e in registry:
        fn = e["local_image"].split("/")[-1]
        stem = os.path.splitext(fn)[0]
        fuzzy_index[base_key(stem)].append(e["id"])

    def registry_id_for(fname):
        if fname in exact_id_by_file:
            return exact_id_by_file[fname]
        stem = os.path.splitext(fname)[0]
        cands = fuzzy_index.get(base_key(stem))
        return cands[0] if cands else None

    # --- Step 2: sge-* re-check (should be a no-op given census's own coverage) ---
    n_sge = sum(1 for f in per_image if f.startswith("sge-"))
    pool = {f: v for f, v in per_image.items() if not f.startswith("sge-")}
    print(f"after sge- re-check exclusion: -{n_sge} -> {len(pool)}")

    # --- Step 3: quarantine exclusion ---
    quarantine = json.load(open(QUARANTINE))
    quarantine_files = {item["file"] for item in quarantine["items"]}
    quarantine_files_pow_only = {
        item["file"] for item in quarantine["items"]
        if item["reason"] == ["product_on_white"]
    }
    n_quarantine_hit = sum(1 for f in pool if f in quarantine_files)
    pool2 = {f: v for f, v in pool.items() if f not in quarantine_files}
    print(f"after quarantine exclusion (all 168 reason codes): -{n_quarantine_hit} -> {len(pool2)}")

    # sensitivity: how big would the manifest be if we only excluded the
    # high-confidence reason codes and let `product_on_white`-only flags
    # (weak/advisory per 019) back in?
    pool2_sens = {f: v for f, v in pool.items() if f not in (quarantine_files - quarantine_files_pow_only)}
    n_sensitivity = len(pool2_sens)

    # --- Step 4: hash-duplicate collapse ---
    by_hash = collections.defaultdict(list)
    missing = []
    for f in pool2:
        p = os.path.join(CATALOG_DIR, f)
        if not os.path.exists(p):
            missing.append(f)
            continue
        by_hash[sha256_of(p)].append(f)
    if missing:
        print(f"WARNING: {len(missing)} files in per_image_class.json missing on disk: {missing[:5]}...")

    clean_images = []
    n_duplicate_dropped = 0
    for h, files in by_hash.items():
        files_sorted_for_canonical = sorted(
            files, key=lambda f: (0 if pool2[f]["match_kind"] == "exact" else 1, len(f), f)
        )
        canonical = files_sorted_for_canonical[0]
        info = pool2[canonical]
        group_registry_ids = sorted({rid for rid in (registry_id_for(f) for f in files) if rid})
        clean_images.append({
            "file": canonical,
            "manufacturer": info["manufacturer"],
            "category": info["category"],
            "name": info["name"],
            "extractor_class": info["extractor_class"],
            "confidence": info["confidence"],
            "rule": info["rule"],
            "match_kind": info["match_kind"],
            "registry_id": registry_id_for(canonical),
            "group_size": len(files),
            "group_members": sorted(files),
            "group_registry_ids": group_registry_ids,
        })
        n_duplicate_dropped += len(files) - 1

    print(f"after hash-duplicate collapse: -{n_duplicate_dropped} duplicate files "
          f"({len(by_hash)} unique-image groups) -> {len(clean_images)}")

    # cross-SKU duplicate groups specifically (019's "72 groups" finding, generalized)
    cross_sku_groups = [c for c in clean_images if len(c["group_registry_ids"]) > 1]
    print(f"  of which {len(cross_sku_groups)} groups span >1 registry id "
          f"(cross-SKU photo reuse, 019 Sec 5 generalized)")

    # --- summary counts ---
    counts_by_mfr = collections.Counter(c["manufacturer"] for c in clean_images)
    counts_by_class = collections.Counter(c["extractor_class"] for c in clean_images)
    counts_by_mfr_class = collections.Counter((c["manufacturer"], c["extractor_class"]) for c in clean_images)
    counts_by_conf = collections.Counter(c["confidence"] for c in clean_images)

    print("\n=== clean manifest: per manufacturer ===")
    for m, n in counts_by_mfr.most_common():
        print(f"  {m:15s} {n:5d}")
    print("\n=== clean manifest: per extractor class ===")
    for c, n in counts_by_class.most_common():
        print(f"  {str(c):18s} {n:5d}")
    print("\n=== clean manifest: per confidence tier ===")
    for c, n in counts_by_conf.most_common():
        print(f"  {c:8s} {n:5d}")

    out = {
        "definition": "THE canonical clean corpus for delighting research (report 021). "
                       "= 015 registry-recoverable images MINUS sge-* MINUS 019 quarantine "
                       "(all reason codes) MINUS hash-duplicates (one canonical file per "
                       "SHA-256 content hash). Every future experiment against the catalog "
                       "corpus should load this file, not re-derive its own filter.",
        "n_registry_recoverable_start": len(per_image),
        "n_clean": len(clean_images),
        "exclusions": {
            "sge_prefix": n_sge,
            "quarantine_all_reason_codes": n_quarantine_hit,
            "hash_duplicate_files_dropped": n_duplicate_dropped,
        },
        "cross_sku_duplicate_groups": len(cross_sku_groups),
        "sensitivity_if_product_on_white_kept": n_sensitivity,
        "counts_by_manufacturer": dict(counts_by_mfr),
        "counts_by_class": {str(k): v for k, v in counts_by_class.items()},
        "counts_by_manufacturer_class": {f"{m}|{c}": n for (m, c), n in counts_by_mfr_class.items()},
        "counts_by_confidence": dict(counts_by_conf),
        "images": sorted(clean_images, key=lambda c: (c["manufacturer"], c["file"])),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
