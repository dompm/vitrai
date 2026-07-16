#!/usr/bin/env python3
"""Report 051 — orchestrate the full benchmark suite in one pass.

Runs, over the restored realpairs:
  1. raw + distractors, scope=all           (PRIMARY wild->clean number + gate)
  2. raw, NO distractors                     (distractor-pool ablation)
  3. delighted-T + distractors               (scope 3: does delighting help?)
  4. luma-quotient + distractors             (scope 3: cheap normalization)
  5. raw + distractors, scope=holdout        (034 holdout comparability)
  6. any-capture leave-one-out diagnostic    (isolates the clean-reference gap)

Writes each run's json under results/051/ and a combined summary_all.json.
"""
import json
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import realpairs_bench as B
from transforms import DelightCache, luma_quotient
from rp_data import build_image_table, RP

OUT_DIR = B.OUT_DIR
IMG_ROOT = os.path.join(RP, "data", "images")


def all_paths():
    _, images = build_image_table(IMG_ROOT)
    return sorted({i["path"] for i in images if i["role"] in ("reference", "wild")})


def save(result, name):
    json.dump(result[0], open(os.path.join(OUT_DIR, f"{name}.json"), "w"), indent=1)
    json.dump({"gate_curve": result[2]["curve"]},
              open(os.path.join(OUT_DIR, f"{name}_gatecurve.json"), "w"))
    json.dump(result[1], open(os.path.join(OUT_DIR, f"{name}_perquery.json"), "w"),
              indent=1, default=str)
    json.dump(result[3], open(os.path.join(OUT_DIR, f"{name}_board.json"), "w"),
              indent=1, default=str)


def headline(r):
    m = r["retrieval"]; g = r["gate"]; gs = r["gate_score_summary"]
    at = g.get("at_p90_threshold", {})
    return {"repr": r["repr"], "distractors": r["use_distractors"], "scope": r["eval_scope"],
            "n_queries": r["n_wild_queries"], "index": r["index_size"],
            "top1": m["top1"], "top5": m["top5"], "gate_auc": round(g["auc"], 4),
            "in_cat_correct_med": gs["in_catalog_correct_median"],
            "in_cat_wrong_med": gs["in_catalog_wrong_median"],
            "ooc_med": gs["ooc_median"],
            "p90_recall": (g.get("pick_precision90") or {}).get("recall"),
            "p90_thresh": (g.get("pick_precision90") or {}).get("t"),
            "confident_frac": at.get("frac_confident"),
            "top1_among_confident": at.get("top1_acc_among_confident")}


def main():
    summary = {"runs": {}}

    print("== 1. raw + distractors (PRIMARY) ==")
    r1 = B.run(IMG_ROOT, use_distractors=True, repr_name="raw", tag="raw_distractors")
    save(r1, "bench_raw_distractors"); summary["runs"]["raw_distractors"] = headline(r1[0])

    print("== 2. raw, no distractors ==")
    r2 = B.run(IMG_ROOT, use_distractors=False, repr_name="raw", tag="raw_nodistract")
    save(r2, "bench_raw_nodistract"); summary["runs"]["raw_nodistract"] = headline(r2[0])

    print("== 3. delighted-T + distractors ==")
    dc = DelightCache(os.path.join(OUT_DIR, "delight_cache"))
    paths = all_paths()
    print(f"   delighting {len(paths)} images (cached)...")
    dc.ensure(paths)
    r3 = B.run(IMG_ROOT, use_distractors=True, repr_name="delight_T",
               transform=dc.transform, tag="delight_distractors")
    save(r3, "bench_delight_distractors"); summary["runs"]["delight_distractors"] = headline(r3[0])

    print("== 4. luma-quotient + distractors ==")
    r4 = B.run(IMG_ROOT, use_distractors=True, repr_name="luma_quotient",
               transform=luma_quotient, tag="quotient_distractors")
    save(r4, "bench_quotient_distractors"); summary["runs"]["quotient_distractors"] = headline(r4[0])

    print("== 5. raw + distractors, holdout ==")
    r5 = B.run(IMG_ROOT, use_distractors=True, repr_name="raw",
               eval_scope="holdout", tag="raw_holdout")
    save(r5, "bench_raw_holdout"); summary["runs"]["raw_holdout"] = headline(r5[0])

    print("== 6. any-capture leave-1-out diagnostic ==")
    diag = B.diagnostic_any_capture(IMG_ROOT, use_distractors=True)
    summary["runs"]["any_capture_diag"] = diag

    # per-brand / per-capture / per-class breakdowns from the primary run
    summary["primary_breakdowns"] = r1[0]["retrieval"]["breakdowns"]
    json.dump(summary, open(os.path.join(OUT_DIR, "summary_all.json"), "w"), indent=1)

    print("\n===== SUMMARY =====")
    for k, v in summary["runs"].items():
        if k == "any_capture_diag":
            print(f"  {k:22s} top1={v['top1']:.3f} top5={v['top5']:.3f} (n={v['n_queries']})")
        else:
            print(f"  {k:22s} top1={v['top1']:.3f} top5={v['top5']:.3f} "
                  f"auc={v['gate_auc']:.3f} p90rec={v['p90_recall']} "
                  f"conf_frac={v['confident_frac']} conf_acc={v['top1_among_confident']}")
    print(f"\nwrote {os.path.join(OUT_DIR, 'summary_all.json')}")


if __name__ == "__main__":
    main()
