"""Shared stratified-sampling helper for the corpus tasks (triage, extractor
breadth test). Reads results/corpus/per_image_class.json (written by
census.py) and picks a roughly-balanced sample across manufacturer x
extractor-class cells, plus a slice of the "no metadata" residual (SGE) so
the lighting triage isn't blind to the one manufacturer with zero registry
coverage.
"""
import collections
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CATALOG_DIR = os.path.join(REPO_ROOT, "frontend", "public", "assets", "catalog_images")
PER_IMAGE_CLASS = os.path.join(HERE, "..", "results", "corpus", "per_image_class.json")

MANUFACTURERS = ("bullseye", "oceanside", "youghiogheny", "sge", "wissmach")


def load_per_image_class():
    return json.load(open(PER_IMAGE_CLASS))


def stratified_sample(n_total=100, seed=7):
    """~n_total images stratified by manufacturer (5-way, roughly equal) then
    by extractor class within each manufacturer (roughly equal across the
    classes present for that manufacturer). SGE (no metadata) is sampled
    directly from the filesystem, uniformly, since it has no class label."""
    rng = random.Random(seed)
    per_image = load_per_image_class()
    by_mfr_class = collections.defaultdict(list)
    for fname, info in per_image.items():
        by_mfr_class[(info["manufacturer"].lower(), info["extractor_class"])].append(fname)

    per_mfr_quota = n_total // len(MANUFACTURERS)
    sample = []
    for mfr in MANUFACTURERS:
        if mfr == "sge":
            all_sge = sorted(f for f in os.listdir(CATALOG_DIR) if f.startswith("sge-"))
            rng.shuffle(all_sge)
            for f in all_sge[:per_mfr_quota]:
                sample.append({"file": f, "manufacturer": "sge", "extractor_class": None,
                               "category": None, "match_kind": "no-metadata"})
            continue
        classes = sorted({c for (m, c) in by_mfr_class if m == mfr and c is not None})
        if not classes:
            continue
        per_class_quota = max(1, per_mfr_quota // len(classes))
        for cls in classes:
            files = list(by_mfr_class[(mfr, cls)])
            rng.shuffle(files)
            for f in files[:per_class_quota]:
                info = per_image[f]
                sample.append({"file": f, "manufacturer": mfr, "extractor_class": cls,
                               "category": info["category"], "match_kind": info["match_kind"]})
    return sample


if __name__ == "__main__":
    s = stratified_sample()
    print(len(s), "sampled")
    ct = collections.Counter((x["manufacturer"], x["extractor_class"]) for x in s)
    for k, v in sorted(ct.items()):
        print(k, v)
