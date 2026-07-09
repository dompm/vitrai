#!/usr/bin/env python3
"""Task 1: REGISTRY CENSUS for the real-glass catalog corpus.

Corpus: frontend/public/assets/catalog_images/ (~3,200 manufacturer swatch
photos: Bullseye, Oceanside, Youghiogheny, SGE, Wissmach) + metadata in
frontend/public/assets/glass_swatch_registry.json (~1,381 rows: manufacturer,
name, category, SKU, real-world dims, local_image path). No material ground
truth exists anywhere in this corpus.

This script:
  1. Loads the registry and lists the actual files on disk.
  2. Reports manufacturer x catalog-category distribution.
  3. Builds an "extended" metadata index: files that don't have their own
     registry row but are same-SKU crop/size variants of a row that IS
     registered (e.g. `bullseye-0000090030ffull.jpg` is the 12"x12" crop of
     the same design as the registered `..f1010.jpg`) get that row's
     category/name by fuzzy suffix-stripped SKU match. This matters because
     the registry was deliberately DEDUPLICATED to one canonical size variant
     per SKU (report/commit "keep standard sheet sizes"), so raw exact-match
     coverage understates how much of the corpus has *recoverable* metadata.
  4. Maps catalog category + name keywords onto the extractor's 4 classes
     {cathedral-clear, wispy, opalescent, dark-opaque} and reports coverage
     + a confidence tier per rule.

Usage: python3 census.py [--out results/corpus/census.json]
"""
import argparse
import collections
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CATALOG_DIR = os.path.join(REPO_ROOT, "frontend", "public", "assets", "catalog_images")
REGISTRY_PATH = os.path.join(REPO_ROOT, "frontend", "public", "assets", "glass_swatch_registry.json")

# Manufacturers the task brief names, with the swatch counts it quotes -- used
# only as a sanity check against what's actually on disk.
EXPECTED_COUNTS = {
    "bullseye": 1650, "oceanside": 560, "youghiogheny": 532,
    "sge": 236, "wissmach": 222,
}

SIZE_VARIANT_SUFFIXES = [
    r"f1010$", r"fhalf$", r"ffull$",           # Bullseye
    r"6x12$", r"6x8$", r"grp$",                  # Youghiogheny / SGE size tags
    r"_8s$",                                      # Oceanside half-sheet tag
]


def base_key(stem):
    for pat in SIZE_VARIANT_SUFFIXES:
        stem2 = re.sub(pat, "", stem)
        if stem2 != stem:
            return stem2
    return stem


# ---------------------------------------------------------------------------
# Task 1c: category + name-keyword -> extractor class mapping.
#
# The manufacturer catalog taxonomy {Cathedral, Opalescent, Wispy/Streaky,
# Textured/Baroque, English Muffle, Ring Mottle} does not line up 1:1 with the
# extractor's optical classes {cathedral-clear, wispy, opalescent,
# dark-opaque} -- catalog categories describe glass ART TRADITION / product
# line, the extractor classes describe LIGHT TRANSPORT behaviour. Two
# corrections are needed:
#   - "Black Opalescent" (a whole Bullseye/Oceanside/Youghiogheny product
#     line) is catalogued under "Opalescent" but is optically closer to
#     dark-opaque: at typical viewing/backlighting it transmits very little
#     light and looks near-black, not milky-glowing. Same for the literal
#     word "opaque" in a name.
#   - "Textured/Baroque" is a grab-bag (rough-rolled/hammered/waterglass
#     texture on otherwise transparent OR opal glass) that must be split by
#     name keyword: "opal" -> opalescent, an explicit N-color "mix" -> wispy
#     (streaky), else default cathedral-clear (the majority are
#     rough-rolled/hammered *transparent* colored cathedral glass).
# Confidence tiers, reported alongside the mapping:
#   high   -- direct category match (Cathedral, Opalescent, Wispy/Streaky)
#             with no override keyword triggered
#   medium -- override keyword fired (Black Opalescent -> dark-opaque) or a
#             small/ambiguous bucket mapped by convention (English Muffle,
#             Ring Mottle)
#   low    -- Textured/Baroque name-keyword sub-split (grab-bag category)
#   none   -- no registry row at all (or row with unrecognized category)
# ---------------------------------------------------------------------------
DARK_OPAQUE_RE = re.compile(r"\bblack\s+opal(escent)?\b|\bopaque\b|\bblack\s+opal\b", re.I)


def map_class(category, name):
    """Return (extractor_class, confidence, rule)."""
    if DARK_OPAQUE_RE.search(name):
        return "dark-opaque", "medium", "name:black-opal/opaque-override"
    if category == "Cathedral":
        return "cathedral-clear", "high", "category:Cathedral"
    if category == "Opalescent":
        return "opalescent", "high", "category:Opalescent"
    if category == "Wispy/Streaky":
        return "wispy", "high", "category:Wispy/Streaky"
    if category == "English Muffle":
        return "cathedral-clear", "medium", "category:English-Muffle->cathedral"
    if category == "Ring Mottle":
        return "opalescent", "medium", "category:Ring-Mottle->opalescent"
    if category == "Textured/Baroque":
        if re.search(r"opal", name, re.I):
            return "opalescent", "low", "textured:opal-keyword"
        if re.search(r"\d\+?\s*-?\s*color\s+mix", name, re.I):
            return "wispy", "low", "textured:color-mix-keyword"
        return "cathedral-clear", "low", "textured:default"
    return None, "none", "no-category"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "..", "results", "corpus", "census.json"))
    args = ap.parse_args()

    registry = json.load(open(REGISTRY_PATH))
    files_on_disk = sorted(f for f in os.listdir(CATALOG_DIR)
                           if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
    print(f"catalog_images/: {len(files_on_disk)} files on disk")
    print(f"registry: {len(registry)} rows")

    by_mfr_disk = collections.Counter(f.split("-")[0] for f in files_on_disk)
    print("\n=== files on disk by manufacturer-prefix ===")
    for m, n in by_mfr_disk.most_common():
        exp = EXPECTED_COUNTS.get(m, "?")
        print(f"  {m:15s} {n:5d}  (brief said {exp})")

    # exact filename match
    exact_index = {e["local_image"].split("/")[-1]: e for e in registry}
    # fuzzy base-key index (may collide; keep list, flag if categories disagree)
    fuzzy_index = collections.defaultdict(list)
    for e in registry:
        fn = e["local_image"].split("/")[-1]
        stem = os.path.splitext(fn)[0]
        fuzzy_index[base_key(stem)].append(e)

    resolved = {}   # filename -> (entry, match_kind)
    for f in files_on_disk:
        if f in exact_index:
            resolved[f] = (exact_index[f], "exact")
            continue
        stem = os.path.splitext(f)[0]
        cands = fuzzy_index.get(base_key(stem))
        if cands:
            resolved[f] = (cands[0], "fuzzy-size-variant")

    n_exact = sum(1 for _, k in resolved.values() if k == "exact")
    n_fuzzy = sum(1 for _, k in resolved.values() if k == "fuzzy-size-variant")
    n_none = len(files_on_disk) - len(resolved)
    print(f"\n=== metadata resolution ===")
    print(f"  exact registry match:        {n_exact:5d} ({100*n_exact/len(files_on_disk):.1f}%)")
    print(f"  fuzzy size-variant recovery: {n_fuzzy:5d} ({100*n_fuzzy/len(files_on_disk):.1f}%)")
    print(f"  no metadata recoverable:     {n_none:5d} ({100*n_none/len(files_on_disk):.1f}%)")

    print("\n=== no-metadata files by manufacturer ===")
    no_meta_by_mfr = collections.Counter(f.split("-")[0] for f in files_on_disk if f not in resolved)
    for m, n in no_meta_by_mfr.most_common():
        print(f"  {m:15s} {n:5d} / {by_mfr_disk[m]:5d}  ({100*n/by_mfr_disk[m]:.0f}% of that mfr unregistered)")

    print("\n=== manufacturer x catalog-category (exact registry rows only) ===")
    ct = collections.Counter((e["manufacturer"], e.get("category")) for e in registry)
    for (mfr, cat), n in sorted(ct.items()):
        print(f"  {mfr:14s} {cat or '(none)':20s} {n:4d}")

    # class mapping over ALL resolved files (exact + fuzzy), so the coverage
    # number reflects the corpus, not just the registry
    class_counts = collections.Counter()
    conf_counts = collections.Counter()
    rule_counts = collections.Counter()
    per_image_class = {}
    for f, (entry, kind) in resolved.items():
        cls, conf, rule = map_class(entry.get("category"), entry.get("name", ""))
        class_counts[cls] += 1
        conf_counts[conf] += 1
        rule_counts[rule] += 1
        per_image_class[f] = {
            "manufacturer": entry["manufacturer"], "category": entry.get("category"),
            "name": entry.get("name"), "extractor_class": cls, "confidence": conf,
            "rule": rule, "match_kind": kind,
        }

    print("\n=== extractor-class mapping (over all metadata-resolved files) ===")
    for c, n in class_counts.most_common():
        print(f"  {str(c):18s} {n:5d}")
    print("\n  confidence tiers:")
    for c, n in conf_counts.most_common():
        print(f"    {c:8s} {n:5d}")
    print("\n  rule breakdown:")
    for r, n in rule_counts.most_common():
        print(f"    {r:40s} {n:5d}")

    n_confident = sum(n for c, n in class_counts.items() if c is not None) - conf_counts.get("low", 0)
    print(f"\n  'confident from metadata alone' (high+medium tiers, i.e. excluding the\n"
          f"   Textured/Baroque name-keyword guess and the unregistered residual):\n"
          f"   {conf_counts.get('high',0)+conf_counts.get('medium',0)} / {len(files_on_disk)} "
          f"({100*(conf_counts.get('high',0)+conf_counts.get('medium',0))/len(files_on_disk):.1f}% of corpus)")

    out = {
        "n_files_on_disk": len(files_on_disk),
        "n_registry_rows": len(registry),
        "by_manufacturer_disk": dict(by_mfr_disk),
        "metadata_resolution": {"exact": n_exact, "fuzzy_size_variant": n_fuzzy, "none": n_none},
        "no_metadata_by_manufacturer": dict(no_meta_by_mfr),
        "manufacturer_x_category_exact_rows": {f"{m}|{c}": n for (m, c), n in ct.items()},
        "class_mapping_counts": {str(k): v for k, v in class_counts.items()},
        "class_mapping_confidence": dict(conf_counts),
        "class_mapping_rules": dict(rule_counts),
        "confident_from_metadata_pct": 100 * (conf_counts.get("high", 0) + conf_counts.get("medium", 0)) / len(files_on_disk),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2)
    # also stash the per-image mapping (large-ish but useful for downstream sampling)
    per_image_path = os.path.join(os.path.dirname(args.out), "per_image_class.json")
    with open(per_image_path, "w") as fh:
        json.dump(per_image_class, fh, indent=1)
    print(f"\nwrote {args.out}")
    print(f"wrote {per_image_path}")


if __name__ == "__main__":
    main()
