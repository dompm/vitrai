#!/usr/bin/env python3
"""Report 031: materialize downscaled, committable exemplar images for cited
tile indices (the images/ dir holds symlinks to an external, gitignored
catalog checkout -- we need real bytes in the repo for the report to be
reproducible/viewable without that checkout).

Usage: extract_exemplars_031.py OUT_SUBDIR IDX [IDX ...]
Writes results/variety_031/exemplars/OUT_SUBDIR/<idx>_<manufacturer>_<tag>.jpg
at max dimension 480px, quality 85 (small, but committable).
"""
import json
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "results", "variety_031")
IMG_DIR = os.path.join(OUT_DIR, "images")
EXEMPLAR_DIR = os.path.join(OUT_DIR, "exemplars")
MAXDIM = 480


def main():
    subdir = sys.argv[1]
    idxs = [int(x) for x in sys.argv[2:]]
    manifest = {m["idx"]: m for m in json.load(open(os.path.join(OUT_DIR, "sample_manifest.json")))}
    out_dir = os.path.join(EXEMPLAR_DIR, subdir)
    os.makedirs(out_dir, exist_ok=True)
    for idx in idxs:
        m = manifest[idx]
        src = os.path.join(IMG_DIR, m["sample_file"])
        im = Image.open(src).convert("RGB")
        s = MAXDIM / max(im.size)
        if s < 1:
            im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
        safe_name = f"{idx:03d}_{m['manufacturer']}_{m['tag']}.jpg"
        out_path = os.path.join(out_dir, safe_name)
        im.save(out_path, quality=85)
        print("wrote", out_path, "  name:", m["name"])


if __name__ == "__main__":
    main()
