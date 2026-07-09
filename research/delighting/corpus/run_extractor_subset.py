#!/usr/bin/env python3
"""Task 3: EXTRACTOR BREADTH TEST.

Runs the FIXED classical extractor (extract.py, unchanged) over a stratified
~60-image subset that the lighting-geometry triage (triage.py, Task 2) flagged
as backlit -- SGE excluded entirely (unreliable/mixed content, see report),
Youghiogheny dark-opaque excluded (triage found surface texture visible on
near-black glass, which implies front/reflected light, not backlit
transmission). Glass class comes from the metadata mapping (census.py), NOT
the VLM (that's Task 4) -- --glass-class is passed explicitly per image.

There is NO ground truth for real photos, so this reports PLAUSIBILITY
diagnostics only:
  - T_raw_p99 outlier flag: extract.py's own pre-clip transmittance-spread
    signal (see extract.py comment near T_ANCHOR); an outlier here means the
    absolute-scale anchor is probably wrong for this image (residual hotspot,
    or the class prior doesn't match the photo).
  - self-recon MAE/p95 (extract.py's built-in metric: how well L*T*(h,B~)
    reproduces the input on non-mark/non-specular pixels)
  - summary stats of T (mean luminance, per-channel) and h per extractor class
  - a best/typical/worst contact sheet by recon MAE, downscaled

Usage: python3 run_extractor_subset.py
"""
import json
import os
import sys
import collections

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))  # extract.py lives in research/delighting/
sys.path.insert(0, HERE)
from sample_utils import CATALOG_DIR  # noqa: E402
import extract  # noqa: E402

RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")
OUT_DIR = os.path.join(RESULTS_DIR, "extractor_subset")
TRIAGE_JSON = os.path.join(RESULTS_DIR, "triage_sample.json")


def select_backlit_verified():
    recs = json.load(open(TRIAGE_JSON))
    pool = [r for r in recs if r["auto_verdict"] == "backlit" and r["manufacturer"] != "sge"
            and not (r["manufacturer"] == "youghiogheny" and r["extractor_class"] == "dark-opaque")]
    return pool


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    pool = select_backlit_verified()
    print(f"backlit-verified subset: {len(pool)} images")

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
            clean = ~(mark_mask | spec_mask)[..., None] * np.ones_like(err, bool)
            metrics = {
                "file": item["file"], "manufacturer": item["manufacturer"],
                "extractor_class": item["extractor_class"],
                "recon_mae_srgb255": float(err[clean].mean() * 255),
                "recon_p95_srgb255": float(np.percentile(err[clean], 95) * 255),
                "h_mean": float(h.mean()),
                "T_mean_rgb": [float(v) for v in T.reshape(-1, 3).mean(0)],
                "T_mean_lum": float((T.reshape(-1, 3) @ extract.LUM).mean()),
                "T_anchor_k": m["k"], "T_raw_p99": m["raw_p99"],
            }
            Image.fromarray((extract.lin_to_srgb(T) * 255).astype(np.uint8)).save(f"{OUT_DIR}/{name}_T.png")
            Image.fromarray((h * 255).astype(np.uint8)).save(f"{OUT_DIR}/{name}_h.png")
            warm = np.array([1.0, 0.72, 0.42])
            panel_cols = [
                extract.tile(lin, "original"), extract.tile(T, "T"),
                extract.tile(h, "h"),
                extract.tile(np.clip(extract.render(T, h, warm), 0, 1), "relit"),
            ]
            panel = np.concatenate([np.pad(c, ((3, 3), (3, 3), (0, 0)), constant_values=25) for c in panel_cols], axis=1)
            Image.fromarray(panel).save(f"{OUT_DIR}/{name}_panel.jpg", quality=85)
            all_metrics.append(metrics)
            print(f"  {name}: class={item['extractor_class']} MAE={metrics['recon_mae_srgb255']:.2f} "
                  f"T_raw_p99={metrics['T_raw_p99']:.3f} h_mean={metrics['h_mean']:.3f}")
        except Exception as e:
            print(f"  FAILED {name}: {e}")
            all_metrics.append({"file": item["file"], "manufacturer": item["manufacturer"],
                                 "extractor_class": item["extractor_class"], "error": str(e)})

    ok = [m for m in all_metrics if "error" not in m]
    failed = [m for m in all_metrics if "error" in m]

    # class-conditioned T_raw_p99 outlier flag: > 2 sigma from the class mean
    # among this sample (no external ground truth to compare against -- this
    # is an internal-consistency flag, see extract.py's own comment on what
    # T_raw_p99 outliers usually mean: residual hotspot or misclass)
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

    summary = {"n_processed": len(ok), "n_failed": len(failed), "failed_files": [m["file"] for m in failed]}
    print("\n=== per-class summary (T,h) ===")
    per_class_summary = {}
    for cls in sorted(by_class):
        rows = [m for m in ok if m["extractor_class"] == cls]
        maes = [r["recon_mae_srgb255"] for r in rows]
        hs = [r["h_mean"] for r in rows]
        lums = [r["T_mean_lum"] for r in rows]
        outliers = sum(1 for r in rows if r["T_raw_p99_outlier"])
        s = {
            "n": len(rows), "recon_mae_mean": float(np.mean(maes)), "recon_mae_max": float(np.max(maes)),
            "h_mean_avg": float(np.mean(hs)), "h_mean_range": [float(np.min(hs)), float(np.max(hs))],
            "T_lum_mean_avg": float(np.mean(lums)), "T_lum_range": [float(np.min(lums)), float(np.max(lums))],
            "T_raw_p99_outliers": outliers,
        }
        per_class_summary[cls] = s
        print(f"  {cls:16s} n={s['n']:3d} MAE={s['recon_mae_mean']:.2f} (max {s['recon_mae_max']:.2f}) "
              f"h={s['h_mean_avg']:.2f} [{s['h_mean_range'][0]:.2f}-{s['h_mean_range'][1]:.2f}] "
              f"T_lum={s['T_lum_mean_avg']:.2f} [{s['T_lum_range'][0]:.2f}-{s['T_lum_range'][1]:.2f}] "
              f"p99_outliers={outliers}")
    summary["per_class"] = per_class_summary
    summary["all_metrics"] = ok
    summary["class_T_raw_p99_stats"] = class_stats

    with open(os.path.join(RESULTS_DIR, "extractor_stats.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"\nwrote {os.path.join(RESULTS_DIR, 'extractor_stats.json')}")

    # best/typical/worst contact sheet by recon MAE
    ok_sorted = sorted(ok, key=lambda m: m["recon_mae_srgb255"])
    picks = {
        "best": ok_sorted[:3],
        "typical": ok_sorted[len(ok_sorted) // 2 - 1: len(ok_sorted) // 2 + 2],
        "worst": ok_sorted[-3:],
    }
    build_btw_sheet(picks)


def build_btw_sheet(picks):
    from PIL import ImageDraw
    tiles = []
    for tier, rows in picks.items():
        for r in rows:
            name = os.path.splitext(r["file"])[0]
            panel_path = f"{OUT_DIR}/{name}_panel.jpg"
            if not os.path.exists(panel_path):
                continue
            im = Image.open(panel_path)
            s = 640 / im.size[0]
            im = im.resize((640, int(im.size[1] * s)), Image.LANCZOS)
            canvas = Image.new("RGB", (660, im.size[1] + 24), (15, 15, 15))
            canvas.paste(im, (10, 22))
            d = ImageDraw.Draw(canvas)
            label = f"{tier.upper()}: {r['manufacturer']}/{r['extractor_class']} MAE={r['recon_mae_srgb255']:.2f}"
            d.text((6, 3), label, fill=(255, 255, 120))
            tiles.append(np.asarray(canvas))
    if not tiles:
        return
    wmax = max(t.shape[1] for t in tiles)
    tiles = [np.pad(t, ((0, 4), (0, wmax - t.shape[1]), (0, 0)), constant_values=15) for t in tiles]
    sheet = np.concatenate(tiles, axis=0)
    out_path = os.path.join(RESULTS_DIR, "extractor_best_typical_worst.jpg")
    Image.fromarray(sheet).save(out_path, quality=85)
    print("wrote", out_path, sheet.shape)


if __name__ == "__main__":
    main()
