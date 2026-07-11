#!/usr/bin/env python3
"""Report 031: independent prevalence estimate #2 -- name-keyword frequency
over the FULL clean manifest (n=1281), as a cross-check against the
stratified-sample-based estimate (which is deliberately breadth-biased, not
prevalence-representative). Keyword groups mirror sample_variety_031.py's
first-tag-match-wins scheme so the two estimates are comparable.
"""
import json
import os
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "..", "results", "corpus", "clean_manifest.json")

KEYWORDS = collections.OrderedDict([
    ("flemish", ["flemish"]),
    ("fracture_streamer", ["fracture", "fractures", "crackle"]),
    ("dew_rainwater", ["dew drop", "rainwater"]),
    ("seedy", ["seedy"]),
    ("ring_mottle", ["mottle", "mottled"]),
    ("streamer", ["streamer"]),
    ("baroque_hammered", ["baroque", "hammered", "artique"]),
    ("cloud_sunset", ["cloud", "sunset"]),
    ("muffle", ["muffle"]),
    ("marine_moss", ["marine", "moss"]),
    ("reactive_fusion", ["reactive", "fusion"]),
    ("granite_ripple", ["granite", "ripple", "waterglass", "rough rolled"]),
    ("iridescent_dichroic_lumin", ["iridescent", "dichroic", "luminescent"]),
    ("wispy_streaky", ["wispy", "streaky"]),
    ("opal", ["opal"]),
])


def first_tag(name_l):
    for tag, kws in KEYWORDS.items():
        if any(k in name_l for k in kws):
            return tag
    return None


def main():
    d = json.load(open(MANIFEST))
    imgs = d["images"]
    n = len(imgs)
    counts = collections.Counter()
    for im in imgs:
        t = first_tag(im["name"].lower())
        counts[t or "plain_no_keyword"] += 1
    print(f"n={n}")
    for tag, c in counts.most_common():
        print(f"{tag}: {c} ({100*c/n:.1f}%)")


if __name__ == "__main__":
    main()
