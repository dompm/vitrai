#!/usr/bin/env python3
"""Report 031: stratified sample from the clean corpus for VLM glass-VARIETY
coverage scanning. Prioritizes STRUCTURAL/categorical breadth (mottle,
granite, baroque, ripple, seedy, ring, drapery, flemish, hammered, muffle,
iridescent, streamer, fracture...) over color breadth, per the task brief.

Two-tier sampling:
  1. Name-keyword tag groups (rare/distinctive tags get near-full coverage;
     common tags -- opal/iridescent/wispy/granite -- get a small handful,
     since their corpus-wide prevalence is separately estimated by exact
     keyword frequency over the FULL clean manifest, not by this sample).
  2. "Plain" (no structural keyword) baseline fill, stratified across
     manufacturer x category, to catch varieties with no naming convention
     (e.g. visible seeds/bubbles in a plainly-named sheet).

Writes results/variety_031/sample_manifest.json (72 picks with tags) and
symlinks the actual files into results/variety_031/images/ for contact-sheet
building.
"""
import json
import os
import random
import collections

random.seed(42)
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CATALOG_DIR = os.path.join(REPO_ROOT, "frontend", "public", "assets", "catalog_images")
MANIFEST = os.path.join(HERE, "..", "results", "corpus", "clean_manifest.json")
OUT_DIR = os.path.join(HERE, "..", "results", "variety_031")
IMG_DIR = os.path.join(OUT_DIR, "images")

KEYWORDS = collections.OrderedDict([
    # rare/distinctive first (priority order = first-tag-match-wins)
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

QUOTAS = {
    "flemish": 5, "fracture_streamer": 4, "dew_rainwater": 2, "seedy": 2,
    "ring_mottle": 6, "streamer": 5, "baroque_hammered": 8, "cloud_sunset": 6,
    "muffle": 6, "marine_moss": 6, "reactive_fusion": 6, "granite_ripple": 6,
    "iridescent_dichroic_lumin": 3, "wispy_streaky": 2, "opal": 2,
}
PLAIN_TARGET_TOTAL = 72


def first_tag(name_l):
    for tag, kws in KEYWORDS.items():
        if any(k in name_l for k in kws):
            return tag
    return None


def main():
    d = json.load(open(MANIFEST))
    imgs = d["images"]
    for im in imgs:
        im["_tag"] = first_tag(im["name"].lower())

    by_tag = collections.defaultdict(list)
    for im in imgs:
        if im["_tag"]:
            by_tag[im["_tag"]].append(im)

    picked = []
    picked_files = set()
    for tag, quota in QUOTAS.items():
        pool = by_tag.get(tag, [])
        random.shuffle(pool)
        # spread across manufacturers where possible
        pool.sort(key=lambda im: im["manufacturer"])
        take = pool[:quota]
        for im in take:
            picked.append(im)
            picked_files.add(im["file"])

    # plain baseline fill: untagged images, stratified by manufacturer x category
    remaining = PLAIN_TARGET_TOTAL - len(picked)
    plain_pool = [im for im in imgs if im["_tag"] is None and im["file"] not in picked_files]
    by_mc = collections.defaultdict(list)
    for im in plain_pool:
        by_mc[(im["manufacturer"], im["category"])].append(im)
    for lst in by_mc.values():
        random.shuffle(lst)
    keys = sorted(by_mc.keys())
    i = 0
    plain_picked = []
    while len(plain_picked) < remaining and keys:
        k = keys[i % len(keys)]
        if by_mc[k]:
            plain_picked.append(by_mc[k].pop())
        i += 1
        if all(not v for v in by_mc.values()):
            break
    for im in plain_picked:
        im["_tag"] = "plain"
        picked.append(im)
        picked_files.add(im["file"])

    print(f"Total picked: {len(picked)}")
    tagc = collections.Counter(im["_tag"] for im in picked)
    for t, c in tagc.most_common():
        print(f"  {t}: {c}")

    os.makedirs(IMG_DIR, exist_ok=True)
    out_manifest = []
    for idx, im in enumerate(picked):
        src = os.path.join(CATALOG_DIR, im["file"])
        if not os.path.exists(src):
            print("MISSING FILE:", src)
            continue
        safe_name = f"{idx:03d}_{im['manufacturer']}_{im['_tag']}_{os.path.basename(im['file'])}"
        dst = os.path.join(IMG_DIR, safe_name)
        if os.path.lexists(dst):
            os.remove(dst)
        os.symlink(src, dst)
        out_manifest.append({
            "idx": idx, "sample_file": safe_name, "orig_file": im["file"],
            "manufacturer": im["manufacturer"], "category": im["category"],
            "name": im["name"], "tag": im["_tag"], "registry_id": im.get("registry_id"),
        })
    with open(os.path.join(OUT_DIR, "sample_manifest.json"), "w") as f:
        json.dump(out_manifest, f, indent=1)
    print("wrote", os.path.join(OUT_DIR, "sample_manifest.json"), "n=", len(out_manifest))


if __name__ == "__main__":
    main()
