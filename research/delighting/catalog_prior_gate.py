#!/usr/bin/env python3
"""Prototype a catalog-statistics gate for sheet-prior assistance.

The sheet prior from report 014 is powerful but unsafe if applied globally. This
script turns catalog texture statistics into a small provenance-aware gate:

  Does this sheet look more contaminated by capture/background variation than
  real manufacturer sheets in the same material family?

It does not modify images. It scores conditions and writes tables that can guide
whether a future product should label a render as catalog-prior assisted.
"""
import argparse
import json
import math
import os
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_AUDIT = os.path.join(HERE, "results", "catalog_texture_audit", "metrics.json")
OUT = os.path.join(HERE, "results", "catalog_prior_gate")


def robust_z(value, stats, key):
    s = stats[key]
    scale = max(s["p75"] - s["p25"], 1e-6)
    return (value - s["median"]) / scale


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def score(row, category_stats):
    """Return a prior-assistance score in [0,1].

    High score means broad low-frequency variation is anomalously high for the
    presumed material family, while chroma variation is not strongly signaling a
    true multi-color/wispy sheet.
    """
    z_low = robust_z(row["lowfreq_cv"], category_stats, "lowfreq_cv")
    z_lum = robust_z(row["lum_cv"], category_stats, "lum_cv")
    z_chroma = robust_z(row["chroma_mad"], category_stats, "chroma_mad")
    z_detail = robust_z(row["highfreq_std"], category_stats, "highfreq_std")

    # Preserve true material variation: high chroma variation is often real in
    # wispy/streaky/opalescent sheets. High detail alone should not trigger the
    # prior; it may be the hammered texture we want to keep.
    logit = 1.35 * z_low + 0.35 * z_lum - 0.90 * max(z_chroma, 0) - 0.18 * max(z_detail, 0) - 0.45
    return {
        "score": float(sigmoid(logit)),
        "z_lowfreq": float(z_low),
        "z_lum": float(z_lum),
        "z_chroma": float(z_chroma),
        "z_detail": float(z_detail),
    }


def compact_row(row, category_stats, family):
    s = score(row, category_stats)
    return {
        "id": row["id"],
        "family": family,
        "score": s["score"],
        "z_lowfreq": s["z_lowfreq"],
        "z_chroma": s["z_chroma"],
        "z_detail": s["z_detail"],
        "lowfreq_cv": row["lowfreq_cv"],
        "highfreq_std": row["highfreq_std"],
        "chroma_mad": row["chroma_mad"],
    }


def summarize_catalog(rows, category_summary):
    by_cat = defaultdict(list)
    for row in rows:
        cat = row["category"]
        if cat not in category_summary:
            continue
        by_cat[cat].append(compact_row(row, category_summary[cat], cat))

    summary = {}
    for cat, scored in by_cat.items():
        scores = np.array([r["score"] for r in scored])
        summary[cat] = {
            "n": len(scored),
            "median_score": float(np.percentile(scores, 50)),
            "p75_score": float(np.percentile(scores, 75)),
            "flag_gt_050": float((scores > 0.50).mean()),
            "flag_gt_070": float((scores > 0.70).mean()),
        }
    return summary


def write_markdown(out_dir, suncatcher, catalog_summary):
    lines = [
        "# Catalog prior gate",
        "",
        "A score near 1 means broad low-frequency variation is anomalously high for the presumed material family and the sheet-prior should be considered. A score near 0 means leave the sheet alone or require manual/provenance labeling.",
        "",
        "## Suncatcher sheet conditions",
        "",
        "| sample | family | score | z_lowfreq | z_chroma | z_detail | lowfreq_cv | highfreq_std |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in suncatcher:
        lines.append(
            f"| {row['id']} | {row['family']} | {row['score']:.2f} | {row['z_lowfreq']:.1f} | "
            f"{row['z_chroma']:.1f} | {row['z_detail']:.1f} | {row['lowfreq_cv']:.3f} | {row['highfreq_std']:.3f} |"
        )

    lines.extend([
        "",
        "## Catalog self-check",
        "",
        "| category | n | median score | p75 score | flagged >0.50 | flagged >0.70 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for cat, row in sorted(catalog_summary.items(), key=lambda kv: (-kv[1]["n"], kv[0])):
        lines.append(
            f"| {cat} | {row['n']} | {row['median_score']:.2f} | {row['p75_score']:.2f} | "
            f"{row['flag_gt_050'] * 100:.0f}% | {row['flag_gt_070'] * 100:.0f}% |"
        )
    lines.extend([
        "",
        "## Read",
        "",
        "- The raw and fixed suncatcher sheets should score high if report 013's background-leak diagnosis is right.",
        "- The sheet-prior outputs should score low; otherwise the prior did not remove the suspicious broad variation.",
        "- High catalog false-positive rates mean this gate is not yet ship-safe. It is a research triage signal.",
        "",
    ])
    with open(os.path.join(out_dir, "gate_summary.md"), "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default=DEFAULT_AUDIT)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    audit = json.load(open(args.audit))
    category_summary = audit["category_summary"]
    catalog_rows = audit["catalog_rows"]

    # The tutorial sheets are hammered cathedral; Textured/Baroque is the closest
    # catalog family for their relief statistics even though the extractor class
    # remains cathedral-clear.
    family = "Textured/Baroque"
    fam_stats = category_summary[family]
    suncatcher = [
        compact_row(row, fam_stats, family)
        for row in audit["suncatcher_conditions"]
    ]
    catalog_self = summarize_catalog(catalog_rows, category_summary)

    payload = {
        "audit": args.audit,
        "suncatcher_family": family,
        "suncatcher_scores": suncatcher,
        "catalog_self_check": catalog_self,
    }
    with open(os.path.join(OUT, "gate_metrics.json"), "w") as f:
        json.dump(payload, f, indent=2)
    write_markdown(OUT, suncatcher, catalog_self)

    for row in suncatcher:
        print(f"{row['id']:14s} score={row['score']:.2f} low_z={row['z_lowfreq']:.1f} chroma_z={row['z_chroma']:.1f}")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
