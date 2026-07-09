#!/usr/bin/env python3
"""Task 4: VLM CLASSIFIER ACCURACY AT SCALE.

First real-scale test of vlm_classify.py's `claude` CLI multiple-choice
classifier (the Track-C class prior) against the corpus's own metadata labels
(census.py's category+keyword mapping, HIGH-confidence tier only -- i.e. a
direct, unambiguous catalog-category match, not our own Textured/Baroque
guess -- so this measures the VLM against a label we trust, not against
another guess).

~40 images, stratified across manufacturer x class among the high-confidence
subset. Uses the real `claude` CLI subprocess (~15s/call) via
vlm_classify.classify_glass; cached in research/delighting/.vlm_cache.json so
reruns are free.

Usage: python3 run_vlm_subset.py [--n 40]
"""
import argparse
import collections
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from sample_utils import CATALOG_DIR, load_per_image_class  # noqa: E402
from vlm_classify import classify_glass  # noqa: E402

RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")
CLASSES = ("opalescent", "wispy", "cathedral-clear", "dark-opaque")


def pick_high_confidence_sample(n, seed=11):
    per_image = load_per_image_class()
    high = [(f, info) for f, info in per_image.items() if info["confidence"] == "high"]
    by_cell = collections.defaultdict(list)
    for f, info in high:
        by_cell[(info["manufacturer"].lower(), info["extractor_class"])].append((f, info))
    rng = random.Random(seed)
    cells = sorted(by_cell)
    per_cell_quota = max(1, n // len(cells))
    sample = []
    for cell in cells:
        items = list(by_cell[cell])
        rng.shuffle(items)
        sample.extend(items[:per_cell_quota])
    rng.shuffle(sample)
    return sample[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args()

    sample = pick_high_confidence_sample(args.n)
    print(f"running VLM classifier on {len(sample)} high-confidence-metadata images")

    rows = []
    t0 = time.time()
    for i, (f, info) in enumerate(sample):
        path = os.path.join(CATALOG_DIR, f)
        try:
            pred = classify_glass(path)
        except Exception as e:
            pred = f"ERROR:{e}"
        gt = info["extractor_class"]
        match = pred == gt
        rows.append({"file": f, "manufacturer": info["manufacturer"], "category": info["category"],
                     "name": info["name"], "gt_class": gt, "vlm_class": pred, "match": match})
        print(f"  [{i+1}/{len(sample)}] {f}: gt={gt} vlm={pred} {'OK' if match else 'MISS'} "
              f"({time.time()-t0:.0f}s elapsed)")

    ok_rows = [r for r in rows if not str(r["vlm_class"]).startswith("ERROR")]
    n_ok = len(ok_rows)
    n_correct = sum(1 for r in ok_rows if r["match"])
    print(f"\naccuracy: {n_correct}/{n_ok} = {100*n_correct/max(1,n_ok):.1f}%")

    confusion = collections.Counter((r["gt_class"], r["vlm_class"]) for r in ok_rows)
    print("\n=== confusion matrix (rows=metadata GT, cols=VLM pred) ===")
    header = "gt\\pred".ljust(16) + "".join(c[:10].ljust(11) for c in CLASSES)
    print(header)
    matrix = {}
    for gt in CLASSES:
        line = gt.ljust(16)
        matrix[gt] = {}
        for pred in CLASSES:
            v = confusion.get((gt, pred), 0)
            matrix[gt][pred] = v
            line += str(v).ljust(11)
        print(line)

    per_class_acc = {}
    for cls in CLASSES:
        rows_cls = [r for r in ok_rows if r["gt_class"] == cls]
        if rows_cls:
            acc = sum(1 for r in rows_cls if r["match"]) / len(rows_cls)
            per_class_acc[cls] = {"n": len(rows_cls), "accuracy": acc}
    print("\nper-class accuracy:", json.dumps(per_class_acc, indent=1))

    out = {
        "n_sample": len(sample), "n_ok": n_ok, "n_correct": n_correct,
        "overall_accuracy": n_correct / max(1, n_ok),
        "confusion_matrix": matrix, "per_class_accuracy": per_class_acc,
        "rows": rows,
    }
    out_path = os.path.join(RESULTS_DIR, "vlm_confusion.json")
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
