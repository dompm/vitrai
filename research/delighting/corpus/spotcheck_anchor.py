#!/usr/bin/env python3
"""Report 016: corpus spot-check of the anchor sanity gate + continuous anchor.

10 real catalog swatches from report 015's backlit-verified subset (incl. the
T_anchor_k=880 blowup and the best/typical/worst of each class). Each image is
extracted under (a) its metadata class and (b) a deliberately FLIPPED class
(the most damaging confusion for that class), with both anchor designs.
No ground truth exists for these photos -- the deliverable is a before/after
contact sheet for eyeballing + the per-image k / t_img / target numbers.

Usage: python3 spotcheck_anchor.py   (writes ../results/class_injection/corpus_spotcheck*)
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from sample_utils import CATALOG_DIR  # noqa: E402
import extract  # noqa: E402

OUT_DIR = os.path.join(HERE, "..", "results", "class_injection")

# file -> metadata class (from report 015's stratified subset)
PICKS = [
    ("wissmach-wf40105.jpg", "opalescent"),        # the k=880 blowup (solid saturated red)
    ("wissmach-wf10lum105.jpg", "opalescent"),     # worst non-blowup opalescent
    ("oceanside-of22872s.jpg", "opalescent"),      # best-case milky
    ("wissmach-wblacki.jpg", "dark-opaque"),       # worst dark-opaque
    ("bullseye-0000130030ffull.jpg", "dark-opaque"),
    ("oceanside-of1009w6x12.jpg", "dark-opaque"),
    ("oceanside-of3172s.jpg", "cathedral-clear"),  # best cathedral
    ("wissmach-w18h.jpg", "cathedral-clear"),      # worst cathedral (dark textured)
    ("wissmach-wiwo702.jpg", "wispy"),             # worst wispy (marbled)
    ("bullseye-60105b0030fhalf.jpg", "wispy"),
]

# most damaging confusion per class (scale-wise): dark<->bright flips
FLIP = {
    "dark-opaque": "cathedral-clear",   # the report-003 "black glass glows" bug
    "cathedral-clear": "dark-opaque",   # crushes a clear sheet to near-black
    "opalescent": "dark-opaque",
    "wispy": "dark-opaque",
}

WARM = np.array([1.0, 0.72, 0.42])


def run(lin, cls, anchor):
    m = extract.extract_maps(lin, cls, mark_region="unknown", anchor=anchor)
    return m


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rows_img, meta = [], []
    for fname, cls in PICKS:
        path = os.path.join(CATALOG_DIR, fname)
        lin = extract.load_linear(path, None, 700)
        t_img = float(extract.estimate_anchor_scale(lin))
        tiles_all = [extract.tile(lin, os.path.splitext(fname)[0][:24])]
        rec = {"file": fname, "meta_class": cls, "t_img": t_img}
        for tag, use_cls in (("meta", cls), ("flip", FLIP[cls])):
            for anchor in ("class", "continuous"):
                m = run(lin, use_cls, anchor)
                T, h = m["T"], m["h"]
                lab = f"{tag}:{use_cls[:9]} {anchor[:4]} k={m['k']:.2f}" + (" GATE" if m["anchor_fallback"] else "")
                tiles_all.append(extract.tile(np.clip(extract.render(T, h, WARM), 0, 1), lab))
                rec[f"{tag}_{anchor}"] = {
                    "class_used": use_cls, "k": m["k"], "target": m["anchor_target"],
                    "gate_fired": m["anchor_fallback"],
                    "T_mean_lum": float(extract.lum(T).mean()),
                }
        meta.append(rec)
        row = np.concatenate([np.pad(t, ((2, 2), (2, 2), (0, 0)), constant_values=25)
                              for t in tiles_all], axis=1)
        s = 1600 / row.shape[1]
        row = np.asarray(Image.fromarray(row).resize(
            (1600, int(row.shape[0] * s)), Image.LANCZOS))
        rows_img.append(row)
        print(f"{fname:36s} t_img={t_img:.3f} "
              + " ".join(f"{k}={v['T_mean_lum']:.2f}{'G' if v['gate_fired'] else ''}"
                         for k, v in rec.items() if isinstance(v, dict)))

    # header strip
    hdr = Image.new("RGB", (1600, 22), (10, 10, 10))
    d = ImageDraw.Draw(hdr)
    d.text((4, 4), "original | relit-warm: meta-class/class-anchor, meta/continuous, "
                   "flipped-class/class-anchor, flipped/continuous", fill=(255, 255, 120))
    sheet = np.concatenate([np.asarray(hdr)] + rows_img, axis=0)
    out = os.path.join(OUT_DIR, "corpus_spotcheck.jpg")
    Image.fromarray(sheet).save(out, quality=87)
    json.dump(meta, open(os.path.join(OUT_DIR, "corpus_spotcheck.json"), "w"), indent=2)
    print("wrote", out)


if __name__ == "__main__":
    main()
