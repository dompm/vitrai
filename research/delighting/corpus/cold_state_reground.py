#!/usr/bin/env python3
"""Re-run report-021 appearance grounding with official cold-sheet anchors.

The sampling, class exclusions, center crop, Lab conversion, and high-frequency
metric are imported from ``appearance_stats.py``. Only the image source changes:
for selected Bullseye striker rows, the current catalog image is replaced with
the manufacturer-labeled cold sheet from ``cold_state_audit.py``'s manifest.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

import appearance_stats as appearance
import cold_state_audit as audit


HERE = Path(__file__).resolve().parent
DELIGHTING = HERE.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clean-manifest",
        type=Path,
        default=DELIGHTING / "results/corpus/clean_manifest.json",
    )
    parser.add_argument(
        "--state-manifest",
        type=Path,
        default=DELIGHTING / "results/cold_state_audit_032/material_state_manifest.json",
    )
    parser.add_argument(
        "--catalog-dir",
        type=Path,
        required=True,
        help="Existing catalog_images directory",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DELIGHTING / "results/cold_state_audit_032/regrounding.json",
    )
    parser.add_argument("--max-per-class", type=int, default=250)
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def stats_from_image(image: Image.Image) -> dict[str, float]:
    image = image.convert("RGB")
    width, height = image.size
    crop_width, crop_height = int(width * 0.6), int(height * 0.6)
    left, top = (width - crop_width) // 2, (height - crop_height) // 2
    image = image.crop(
        (left, top, left + crop_width, top + crop_height)
    ).resize((200, 200), Image.Resampling.LANCZOS)
    rgb = np.asarray(image, dtype=np.float64) / 255.0
    lab = appearance.srgb_to_lab(rgb)
    lightness, chroma, hue = appearance.lab_to_lch(lab)
    luma = rgb @ appearance.LUM
    return {
        "L_median": float(np.median(lightness)),
        "C_median": float(np.median(chroma)),
        "hue_deg": appearance.chroma_weighted_circular_mean_hue(
            hue.ravel(), chroma.ravel()
        ),
        "C_p90": float(np.percentile(chroma, 90)),
        "hf_energy_frac": appearance.high_freq_energy_fraction(luma),
    }


def summarize_values(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = np.asarray([row[key] for row in rows], dtype=np.float64)
    return {
        "mean": float(values.mean()),
        "std": float(values.std()),
        "p5": float(np.percentile(values, 5)),
        "p50": float(np.percentile(values, 50)),
        "p95": float(np.percentile(values, 95)),
    }


def summarize_classes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_class: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        by_class[row["extractor_class"]].append(row)
    result: dict[str, Any] = {}
    for extractor_class, class_rows in sorted(by_class.items()):
        hues = np.asarray([row["hue_deg"] for row in class_rows])
        chromas = np.asarray([row["C_median"] for row in class_rows])
        result[extractor_class] = {
            "n": len(class_rows),
            "L_median": summarize_values(class_rows, "L_median"),
            "C_median": summarize_values(class_rows, "C_median"),
            "hue_circular_mean_deg": appearance.chroma_weighted_circular_mean_hue(
                hues, chromas
            ),
            "hf_energy_frac": summarize_values(class_rows, "hf_energy_frac"),
        }
    return result


def metric_delta(
    baseline: dict[str, Any], corrected: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for extractor_class in sorted(baseline):
        before = baseline[extractor_class]
        after = corrected[extractor_class]
        result[extractor_class] = {
            "n": before["n"],
            "L_p50_delta": after["L_median"]["p50"] - before["L_median"]["p50"],
            "C_p50_delta": after["C_median"]["p50"] - before["C_median"]["p50"],
            "hf_p50_delta": after["hf_energy_frac"]["p50"]
            - before["hf_energy_frac"]["p50"],
            "hue_circular_mean_delta": (
                (after["hue_circular_mean_deg"] - before["hue_circular_mean_deg"] + 180)
                % 360
                - 180
            ),
        }
    return result


def gauge_from_registry_id(registry_id: str) -> str | None:
    match = re.match(r"bullseye-\d{6}(0030|0050)", registry_id or "")
    return match.group(1) if match else None


def anchor_url(anchor: dict[str, Any], registry_id: str) -> str | None:
    gauge = gauge_from_registry_id(registry_id)
    candidate = None
    if gauge == "0030":
        candidate = anchor.get("cold_3mm")
    elif gauge == "0050":
        candidate = anchor.get("cold_2mm")
    candidate = candidate or anchor.get("cold_fallback")
    if not candidate:
        return None
    return candidate.get("thumbnail_url") or candidate.get("url")


def main() -> None:
    args = parse_args()
    clean = json.loads(args.clean_manifest.read_text())["images"]
    state_manifest = json.loads(args.state_manifest.read_text())
    anchors = {row["formula"]: row for row in state_manifest["cold_anchor_rows"]}
    proven_fired = {
        row["formula"]
        for row in state_manifest["rows"]
        if row["store_first_classification"] == "fired_closer"
    }
    all_labeled_strikers = {
        formula for formula, anchor in anchors.items() if anchor["striker"]
    }

    eligible = [
        item
        for item in clean
        if item["confidence"] != "low"
        and not (
            item["manufacturer"].lower() == "youghiogheny"
            and item["extractor_class"] == "dark-opaque"
        )
    ]
    by_class: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for item in eligible:
        by_class[item["extractor_class"]].append(item)
    rng = random.Random(11)
    selected: list[dict[str, Any]] = []
    for extractor_class in by_class:
        rng.shuffle(by_class[extractor_class])
        selected.extend(by_class[extractor_class][: args.max_per_class])

    baseline_rows: list[dict[str, Any]] = []
    baseline_images: dict[str, Image.Image] = {}
    for index, item in enumerate(selected, start=1):
        image = Image.open(args.catalog_dir / item["file"]).convert("RGB")
        baseline_images[item["file"]] = image.copy()
        row = dict(item)
        row.update(stats_from_image(image))
        formula = audit.formula_from_registry_id(item.get("registry_id", ""))
        row["formula"] = formula
        baseline_rows.append(row)
        if index % 200 == 0:
            print(f"read {index}/{len(selected)} baseline images", flush=True)

    fetcher = audit.ImageFetcher(audit.make_session(), args.timeout)
    anchor_stats: dict[tuple[str, str], tuple[dict[str, float], Image.Image, str]] = {}
    replacement_failures: list[dict[str, str]] = []

    def build_scope(name: str, formulas: set[str]) -> dict[str, Any]:
        corrected_rows: list[dict[str, Any]] = []
        paired_rows: list[dict[str, Any]] = []
        for baseline in baseline_rows:
            corrected = dict(baseline)
            formula = baseline.get("formula")
            if formula not in formulas or formula not in anchors:
                corrected_rows.append(corrected)
                continue
            url = anchor_url(anchors[formula], baseline["registry_id"])
            if not url:
                corrected_rows.append(corrected)
                continue
            key = (formula, url)
            try:
                if key not in anchor_stats:
                    image = fetcher.get(url)
                    anchor_stats[key] = (stats_from_image(image), image.copy(), url)
                stats, cold_image, used_url = anchor_stats[key]
                for field, value in stats.items():
                    corrected[field] = value
                corrected["replacement_url"] = used_url
                corrected["replaced_with_official_cold"] = True
                baseline_lab = audit.robust_lab(baseline_images[baseline["file"]])
                cold_lab = audit.robust_lab(cold_image)
                paired_rows.append(
                    {
                        "file": baseline["file"],
                        "registry_id": baseline["registry_id"],
                        "formula": formula,
                        "extractor_class": baseline["extractor_class"],
                        "baseline_L": baseline["L_median"],
                        "cold_L": corrected["L_median"],
                        "baseline_C": baseline["C_median"],
                        "cold_C": corrected["C_median"],
                        "paired_center_delta_e": audit.delta_e(baseline_lab, cold_lab),
                        "cold_url": used_url,
                    }
                )
            except Exception as error:
                replacement_failures.append(
                    {"scope": name, "formula": formula, "error": str(error)}
                )
            corrected_rows.append(corrected)

        baseline_summary = summarize_classes(baseline_rows)
        corrected_summary = summarize_classes(corrected_rows)
        delta_e_values = [row["paired_center_delta_e"] for row in paired_rows]
        return {
            "scope": name,
            "requested_formulas": len(formulas),
            "sampled_rows_replaced": len(paired_rows),
            "sampled_formulas_replaced": len({row["formula"] for row in paired_rows}),
            "paired_center_delta_e": {
                "median": audit.round_or_none(audit.percentile(delta_e_values, 0.5)),
                "p75": audit.round_or_none(audit.percentile(delta_e_values, 0.75)),
                "p90": audit.round_or_none(audit.percentile(delta_e_values, 0.9)),
                "max": audit.round_or_none(max(delta_e_values) if delta_e_values else None),
            },
            "corrected_per_class": corrected_summary,
            "delta_from_baseline": metric_delta(baseline_summary, corrected_summary),
            "paired_rows": sorted(
                paired_rows, key=lambda row: row["paired_center_delta_e"], reverse=True
            ),
        }

    baseline_summary = summarize_classes(baseline_rows)
    scopes = {
        "proven_fired_choices": build_scope("proven_fired_choices", proven_fired),
        "all_labeled_strikers": build_scope(
            "all_labeled_strikers", all_labeled_strikers
        ),
    }
    output = {
        "method": {
            "eligible_clean_rows": len(eligible),
            "selected_rows": len(selected),
            "max_per_class": args.max_per_class,
            "sample_seed": 11,
            "note": (
                "Exact report-021 sample/exclusion/statistic protocol. The two scopes replace "
                "only the image source for selected Bullseye rows with an official cold sheet."
            ),
        },
        "baseline_per_class": baseline_summary,
        "scopes": scopes,
        "replacement_failures": replacement_failures,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2))
    print(json.dumps({"method": output["method"], "scopes": {
        key: {field: value for field, value in scope.items() if field != "paired_rows"}
        for key, scope in scopes.items()
    }, "replacement_failures": replacement_failures}, indent=2))


if __name__ == "__main__":
    main()
