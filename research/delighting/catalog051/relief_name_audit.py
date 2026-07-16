#!/usr/bin/env python3
"""Report 051, scope 6 — per-SKU relief-cache: how much is a METADATA LOOKUP?

The product idea caches a per-SKU relief preset. For many sheets the
manufacturer already NAMES the surface texture (granite / ripple / waterglass /
glue chip / hammered / muffle / baroque ...), so the preset is a pure
name->preset lookup with no vision needed. This script quantifies that fraction
over (a) the shipped registry, (b) the clean corpus, and (c) the realpairs
benchmark products, and reports the complement — smooth-named sheets that still
need per-photo relief estimation.

We separate SURFACE-RELIEF texture words (what the relief map is about) from
COLOR/OPACITY words (opalescent, wispy, iridescent, streaky) which describe the
bulk material, not the surface height field, and must NOT be counted as relief
metadata.
"""
import argparse
import json
import os
import re
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_REPO = "/Users/dominiquepiche-meunier/Documents/vitraux"
REGISTRY = os.path.join(MAIN_REPO, "frontend", "public", "assets", "glass_swatch_registry.json")
CLEAN_MANIFEST = os.path.join(HERE, "..", "results", "corpus", "clean_manifest.json")
REALPAIRS = os.path.join(HERE, "..", "realpairs", "results", "manifest_033.json")
OUT = os.path.join(HERE, "..", "results", "051", "relief_name_audit.json")

# keyword (regex, matched on lowered text) -> relief family (the cached preset key).
# Ordered; first match wins for the "primary family" tally.
RELIEF_KEYWORDS = [
    (r"glue[\s\-]?chip", "glue_chip"),
    (r"herringbone", "herringbone"),
    (r"waterglass|water[\s\-]glass", "waterglass"),
    (r"granite", "granite"),
    (r"ripple", "ripple"),
    (r"stipple", "stipple"),
    (r"hammer", "hammered"),
    (r"corduroy|cord(?![a-z])", "corduroy"),
    (r"reed(ed)?(?![a-z])", "reeded"),
    (r"flemish", "flemish"),
    (r"drape", "drapery"),
    (r"seed(y)?(?![a-z])", "seedy"),
    (r"pebble", "pebble"),
    (r"crackle|crackled", "crackle"),
    (r"muffle", "muffle"),
    (r"baroque", "baroque"),
    (r"moss", "moss"),
    (r"chord", "chord"),
    (r"wavolite", "wavolite"),
    (r"artique", "artique"),
    (r"vecchio", "vecchio"),
    (r"glacier|aqualite", "glacier"),
    (r"rough[\s\-]?roll|rough(?![a-z])", "rough_rolled"),
    (r"textured?(?![a-z])", "generic_textured"),
]

# category strings that are themselves a texture declaration
TEXTURE_CATEGORIES = {"Textured/Baroque", "English Muffle"}

# words that describe bulk material, NOT surface relief — must not be counted.
NON_RELIEF_CONTROL = [
    (r"opal", "opalescent"), (r"wispy", "wispy"), (r"iridescent", "iridescent"),
    (r"streaky", "streaky"), (r"mottle", "mottle"), (r"dichro", "dichroic"),
]


def relief_family(text):
    t = (text or "").lower()
    for pat, fam in RELIEF_KEYWORDS:
        if re.search(pat, t):
            return fam
    return None


def audit(records, name_key, cat_key=None, label=""):
    """records: list of dicts. Returns a summary."""
    n = len(records)
    fam_counts = collections.Counter()
    cat_texture = 0
    name_texture = 0
    either = 0
    per_brand = collections.defaultdict(lambda: [0, 0])  # brand -> [n, texture_named]
    control = collections.Counter()
    examples = collections.defaultdict(list)
    for r in records:
        nm = r.get(name_key) or ""
        fam = relief_family(nm)
        cat = (r.get(cat_key) if cat_key else None)
        is_cat_tex = cat in TEXTURE_CATEGORIES
        brand = r.get("brand") or r.get("manufacturer") or r.get("_brand") or "?"
        per_brand[brand][0] += 1
        has_tex = bool(fam) or is_cat_tex
        if fam:
            name_texture += 1
            fam_counts[fam] += 1
            if len(examples[fam]) < 3:
                examples[fam].append(nm[:70])
        if is_cat_tex:
            cat_texture += 1
        if has_tex:
            either += 1
            per_brand[brand][1] += 1
        for pat, c in NON_RELIEF_CONTROL:
            if re.search(pat, nm.lower()):
                control[c] += 1
    return {
        "label": label,
        "n": n,
        "name_texture_hits": name_texture,
        "category_texture_hits": cat_texture,
        "texture_named_either": either,
        "texture_named_frac": round(either / n, 4) if n else 0,
        "smooth_named_needs_vision": n - either,
        "smooth_named_frac": round((n - either) / n, 4) if n else 0,
        "relief_family_counts": dict(fam_counts.most_common()),
        "family_examples": {k: v for k, v in examples.items()},
        "non_relief_control_counts": dict(control.most_common()),
        "per_brand": {b: {"n": v[0], "texture_named": v[1],
                          "frac": round(v[1] / v[0], 3) if v[0] else 0}
                      for b, v in sorted(per_brand.items())},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()
    results = {}

    reg = json.load(open(REGISTRY))
    results["registry"] = audit(reg, "name", "category", "shipped registry (1,269 SKUs)")

    clean = json.load(open(CLEAN_MANIFEST))["images"]
    for c in clean:
        c["_brand"] = c.get("manufacturer")
    results["clean_corpus"] = audit(clean, "name", "category", "clean corpus (1,281 imgs)")

    if os.path.exists(REALPAIRS):
        rp = json.load(open(REALPAIRS))
        for p in rp:
            p["_brand"] = p.get("brand")
        results["realpairs_products"] = audit(rp, "title", None, "realpairs Delphi products (254)")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(results, open(args.out, "w"), indent=1)

    for key, s in results.items():
        print(f"\n=== {s['label']} ===")
        print(f"  texture-named (relief preset = metadata lookup): "
              f"{s['texture_named_either']}/{s['n']} = {s['texture_named_frac']*100:.1f}%")
        print(f"    via name={s['name_texture_hits']}  via category={s['category_texture_hits']}")
        print(f"  smooth-named (needs per-photo relief): {s['smooth_named_frac']*100:.1f}%")
        print(f"  top relief families: {list(s['relief_family_counts'].items())[:8]}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
