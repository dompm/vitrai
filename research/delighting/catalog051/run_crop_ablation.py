#!/usr/bin/env python3
"""Report 051 — center-crop query ablation (scene-domination hypothesis).

The primary raw numbers came in low (top-1 ~0.13) with distractors nearly
irrelevant — consistent with the wild photos' global embedding being dominated
by the SCENE (windowsill/trees/racks) rather than the sheet. References are
full-frame sheet texture. If a dumb central crop recovers a large chunk of
accuracy, the product lesson is a sheet-detection/crop stage (or asking the
user to fill the frame), not a better backbone.

Runs: crop50 / crop50+quotient / crop30, all + distractors, and writes
results/051/summary_crop.json.
"""
import functools
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import realpairs_bench as B
from transforms import center_crop, crop_then_quotient
from run_all import save, headline, IMG_ROOT, OUT_DIR


def main():
    summary = {}
    runs = [
        ("crop50_distractors", "crop50", functools.partial(center_crop, frac=0.5)),
        ("crop50q_distractors", "crop50_quotient", functools.partial(crop_then_quotient, frac=0.5)),
        ("crop30_distractors", "crop30", functools.partial(center_crop, frac=0.3)),
    ]
    for name, repr_name, tf in runs:
        print(f"== {name} ==", flush=True)
        r = B.run(IMG_ROOT, use_distractors=True, repr_name=repr_name,
                  transform=tf, tag=name)
        save(r, f"bench_{name}")
        summary[name] = headline(r[0])
        print(f"   top1={summary[name]['top1']:.3f} top5={summary[name]['top5']:.3f} "
              f"auc={summary[name]['gate_auc']:.3f}", flush=True)
    json.dump(summary, open(os.path.join(OUT_DIR, "summary_crop.json"), "w"), indent=1)
    print("wrote summary_crop.json")


if __name__ == "__main__":
    main()
