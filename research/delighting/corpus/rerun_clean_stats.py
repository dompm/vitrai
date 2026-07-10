#!/usr/bin/env python3
"""Task B (report 021): re-run 015's lighting triage + extractor breadth test
on the CLEAN corpus (results/corpus/clean_manifest.json, built by
clean_manifest.py) instead of the raw, contaminated/duplicated corpus 015
used. Same heuristics/extractor code as 015 (triage.py's `heuristics`/
`auto_verdict`, extract.py unmodified) -- only the sampling source changes:
stratified over manufacturer x extractor-class from the clean manifest
(4 manufacturers now, SGE is gone entirely, no need for its "no metadata"
special case).

Writes:
  results/corpus/triage_sample_clean.json / triage_contact_sheet_clean.jpg
  results/corpus/extractor_stats_clean.json / extractor_best_typical_worst_clean.jpg

Usage: python3 rerun_clean_stats.py [--n 100]
"""
import argparse
import collections
import json
import os
import random
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import triage  # noqa: E402  (reuse heuristics()/auto_verdict()/build_contact_sheet())
import extract  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CATALOG_DIR = os.path.join(REPO_ROOT, "frontend", "public", "assets", "catalog_images")
RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")
CLEAN_MANIFEST = os.path.join(RESULTS_DIR, "clean_manifest.json")
MANUFACTURERS = ("bullseye", "oceanside", "youghiogheny", "wissmach")


def stratified_sample_clean(n_total=100, seed=7):
    rng = random.Random(seed)
    clean = json.load(open(CLEAN_MANIFEST))["images"]
    by_mfr_class = collections.defaultdict(list)
    for im in clean:
        by_mfr_class[(im["manufacturer"].lower(), im["extractor_class"])].append(im["file"])

    per_mfr_quota = n_total // len(MANUFACTURERS)
    sample = []
    for mfr in MANUFACTURERS:
        classes = sorted({c for (m, c) in by_mfr_class if m == mfr and c is not None})
        if not classes:
            continue
        per_class_quota = max(1, per_mfr_quota // len(classes))
        for cls in classes:
            files = list(by_mfr_class[(mfr, cls)])
            rng.shuffle(files)
            for f in files[:per_class_quota]:
                sample.append({"file": f, "manufacturer": mfr, "extractor_class": cls})
    return sample


def run_triage(sample, out_json, out_sheet):
    metrics = []
    for item in sample:
        rgb = triage.load_srgb01(os.path.join(CATALOG_DIR, item["file"]))
        m = triage.heuristics(rgb)
        m["auto_verdict"] = triage.auto_verdict(m)
        metrics.append(m)
    records = [{**item, **m} for item, m in zip(sample, metrics)]
    with open(out_json, "w") as fh:
        json.dump(records, fh, indent=1)
    print("wrote", out_json)
    triage.build_contact_sheet(sample, metrics, out_sheet)

    print("\n=== CLEAN CORPUS: per-manufacturer automatic verdict tally ===")
    tally = collections.Counter((r["manufacturer"], r["auto_verdict"]) for r in records)
    for k, v in sorted(tally.items()):
        print(k, v)
    print("\n=== CLEAN CORPUS: per-manufacturer mean heuristics ===")
    by_mfr = collections.defaultdict(list)
    for r in records:
        by_mfr[r["manufacturer"]].append(r)
    summary = {}
    for mfr, rs in sorted(by_mfr.items()):
        n = len(rs)
        n_backlit = sum(1 for r in rs if r["auto_verdict"] == "backlit")
        s = {
            "n": n, "mean_lum": float(np.mean([r["mean_lum"] for r in rs])),
            "p99": float(np.mean([r["p99"] for r in rs])),
            "specular_frac": float(np.mean([r["specular_frac"] for r in rs])),
            "corner_center_ratio": float(np.mean([r["corner_center_ratio"] for r in rs])),
            "sat_mean": float(np.mean([r["sat_mean"] for r in rs])),
            "auto_backlit_tally": f"{n_backlit}/{n}",
        }
        summary[mfr] = s
        print(f"{mfr:14s} n={n:3d} mean_lum={s['mean_lum']:.3f} p99={s['p99']:.3f} "
              f"specular={s['specular_frac']:.4f} corner/center={s['corner_center_ratio']:.3f} "
              f"sat={s['sat_mean']:.3f} auto_backlit={s['auto_backlit_tally']}")
    return records, summary


def run_extractor(records, out_stats, out_sheet):
    # Same exclusion rule as 015/run_extractor_subset.py: SGE excluded (moot,
    # already gone from the clean corpus), Youghiogheny dark-opaque excluded
    # (015 Sec 2: surface texture visible through near-black glass implies
    # front/reflected lighting for this specific manufacturer x class cell,
    # a lighting-geometry finding independent of corpus contamination/dedup).
    pool = [r for r in records if r["auto_verdict"] == "backlit"
            and not (r["manufacturer"] == "youghiogheny" and r["extractor_class"] == "dark-opaque")]
    print(f"\nbacklit-verified CLEAN subset: {len(pool)} images")

    out_dir = os.path.join(RESULTS_DIR, "extractor_subset_clean")
    os.makedirs(out_dir, exist_ok=True)
    all_metrics = []
    for item in pool:
        path = os.path.join(CATALOG_DIR, item["file"])
        name = os.path.splitext(item["file"])[0]
        try:
            lin = extract.load_linear(path, None, 700)
            m = extract.extract_maps(lin, item["extractor_class"], "unknown")
            lin_ns, spec_mask, L, R = m["lin_ns"], m["spec_mask"], m["L"], m["R"]
            mark_mask, h, T, conf = m["mark_mask"], m["h"], m["T"], m["conf"]
            I_hat, Bq = extract.reconstruct(L, T, h, R)
            err = np.abs(extract.lin_to_srgb(np.clip(I_hat, 0, 1)) - extract.lin_to_srgb(np.clip(lin_ns, 0, 1)))
            clean_px = ~(mark_mask | spec_mask)[..., None] * np.ones_like(err, bool)
            metrics = {
                "file": item["file"], "manufacturer": item["manufacturer"],
                "extractor_class": item["extractor_class"],
                "recon_mae_srgb255": float(err[clean_px].mean() * 255),
                "recon_p95_srgb255": float(np.percentile(err[clean_px], 95) * 255),
                "h_mean": float(h.mean()),
                "T_mean_rgb": [float(v) for v in T.reshape(-1, 3).mean(0)],
                "T_mean_lum": float((T.reshape(-1, 3) @ extract.LUM).mean()),
                "T_anchor_k": m["k"], "T_raw_p99": m["raw_p99"],
            }
            all_metrics.append(metrics)
            print(f"  {name}: class={item['extractor_class']} MAE={metrics['recon_mae_srgb255']:.2f} "
                  f"T_anchor_k={metrics['T_anchor_k']:.3f}")
        except Exception as e:
            print(f"  FAILED {name}: {e}")
            all_metrics.append({"file": item["file"], "manufacturer": item["manufacturer"],
                                 "extractor_class": item["extractor_class"], "error": str(e)})

    ok = [m for m in all_metrics if "error" not in m]
    failed = [m for m in all_metrics if "error" in m]

    by_class = collections.defaultdict(list)
    for m in ok:
        by_class[m["extractor_class"]].append(m["T_raw_p99"])
    class_stats = {}
    for cls, vals in by_class.items():
        arr = np.array(vals)
        class_stats[cls] = {"n": len(arr), "T_raw_p99_mean": float(arr.mean()), "T_raw_p99_std": float(arr.std())}
    for m in ok:
        mu, sd = class_stats[m["extractor_class"]]["T_raw_p99_mean"], class_stats[m["extractor_class"]]["T_raw_p99_std"]
        m["T_raw_p99_outlier"] = bool(sd > 1e-6 and abs(m["T_raw_p99"] - mu) > 2 * sd)
        m["T_anchor_qa_flag"] = bool(m["T_anchor_k"] > 5)  # 015 Sec 3's proposed QA gate

    print("\n=== CLEAN CORPUS per-class summary (T,h) ===")
    per_class_summary = {}
    for cls in sorted(by_class):
        rows = [m for m in ok if m["extractor_class"] == cls]
        maes = [r["recon_mae_srgb255"] for r in rows]
        hs = [r["h_mean"] for r in rows]
        lums = [r["T_mean_lum"] for r in rows]
        outliers = sum(1 for r in rows if r["T_raw_p99_outlier"])
        qa_flags = sum(1 for r in rows if r["T_anchor_qa_flag"])
        s = {
            "n": len(rows), "recon_mae_mean": float(np.mean(maes)), "recon_mae_max": float(np.max(maes)),
            "h_mean_avg": float(np.mean(hs)), "h_mean_range": [float(np.min(hs)), float(np.max(hs))],
            "T_lum_mean_avg": float(np.mean(lums)), "T_lum_range": [float(np.min(lums)), float(np.max(lums))],
            "T_raw_p99_outliers": outliers, "T_anchor_qa_flags": qa_flags,
        }
        per_class_summary[cls] = s
        print(f"  {cls:16s} n={s['n']:3d} MAE={s['recon_mae_mean']:.2f} (max {s['recon_mae_max']:.2f}) "
              f"h={s['h_mean_avg']:.2f} [{s['h_mean_range'][0]:.2f}-{s['h_mean_range'][1]:.2f}] "
              f"T_lum={s['T_lum_mean_avg']:.2f} [{s['T_lum_range'][0]:.2f}-{s['T_lum_range'][1]:.2f}] "
              f"p99_outliers={outliers} anchor_qa_flags={qa_flags}")

    summary = {"n_processed": len(ok), "n_failed": len(failed), "failed_files": [m["file"] for m in failed],
               "per_class": per_class_summary, "all_metrics": ok, "class_T_raw_p99_stats": class_stats}
    with open(out_stats, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"\nwrote {out_stats}")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()

    sample = stratified_sample_clean(args.n)
    print(f"clean stratified sample: {len(sample)}")
    records, triage_summary = run_triage(
        sample,
        os.path.join(RESULTS_DIR, "triage_sample_clean.json"),
        os.path.join(RESULTS_DIR, "triage_contact_sheet_clean.jpg"),
    )
    extractor_summary = run_extractor(
        records,
        os.path.join(RESULTS_DIR, "extractor_stats_clean.json"),
        os.path.join(RESULTS_DIR, "extractor_best_typical_worst_clean.jpg"),
    )


if __name__ == "__main__":
    main()
