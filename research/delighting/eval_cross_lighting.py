#!/usr/bin/env python3
"""Report 017: CROSS-LIGHTING (capture) INVARIANCE metric.

The assembled-pair drag test (report 014) covers POSITION invariance (same
sheet, different piece placement). This harness covers CAPTURE-LIGHTING
invariance: for every (recipe, seed) group in a synthetic dataset -- i.e. the
SAME authored glass, rendered under N different lightings (different HDRI
rotation/EV draws) -- extract T,h from each lighting INDEPENDENTLY and measure
how much the extracted maps disagree with each other. A capture-invariant
extractor should de-light every lighting of the same sheet to (nearly) the
same map; the residual pairwise disagreement is exactly the pain the product
is trying to remove (report RESEARCH_STATE's "Success metric").

Three columns, all reachable through extract.py's real `--anchor auto`
default (commit 896c2d7):
  oracle               glass_class = the correct (GT) class, anchor='class'
                       -- what a human-verified manifest / --class override
                       gets.
  continuous           glass_class = 'wispy' (extract.py's own documented
                       fallback when --no-vlm and no override), anchor=
                       'continuous' -- what a real batch/corpus run gets
                       when the class source is unreliable (report 015: VLM
                       30.6%). This is the "vlm-free continuous path", and
                       it estimates t_img PER PHOTO.
  continuous_persheet  identical to `continuous` except the anchor's t_img
                       is pooled ACROSS the group (extract.estimate_anchor_
                       scale_sheet, report 020) before extracting any of
                       them -- the per-sheet scale mode, evaluated on
                       exactly the multi-lighting groups this harness
                       already builds (same authored glass, several
                       photos == this report's product scenario).

Per (recipe, seed) group: every unordered pair of lightings' extracted T (and
h) are compared, mean-abs-difference over all pixels (marks excluded via the
seed's own gt_mark_mask, identical across lightings of the same seed since the
texture is regenerated deterministically from the same seed). Reported per
recipe (averaged over that recipe's seed-groups), alongside each design's
mean per-sample GT-error (T_mae / h_mae vs authored ground truth) for
context -- invariance should be <= accuracy error; if it's bigger, the
extractor is capture-*dependent* even where it happens to be accurate on
average.

Usage:  eval_cross_lighting.py --data DIR [--data DIR2 ...] [--out DIR] [--size 700]
"""
import argparse
import glob
import itertools
import json
import os
import sys

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract  # noqa: E402
from eval_synthetic import CLASS_MAP, load_gt_T, load_gt_h, load_gt_mask, clean_photo_path, resize_to  # noqa: E402

DESIGNS = {
    # name -> (glass_class fed to extract_maps, anchor mode)
    "oracle": None,          # resolved per-sample to the GT class, anchor='class'
    "continuous": ("wispy", "continuous"),
    # Report 020: identical to "continuous" (same fallback class, same
    # anchor mode) EXCEPT the continuous anchor's t_img is pooled across
    # every lighting in the (recipe,seed) group -- estimate_anchor_scale_
    # sheet -- instead of estimated independently per photo. This is the
    # per-sheet scale mode's own invariance metric: a real multi-lighting
    # group IS several photos of the same sheet.
    "continuous_persheet": ("wispy", "continuous"),
}


def group_samples(data_dirs):
    groups = {}
    for data_dir in data_dirs:
        for s in sorted(glob.glob(os.path.join(data_dir, "*"))):
            if not os.path.isdir(s):
                continue
            mp = os.path.join(s, "meta.json")
            if not os.path.exists(mp):
                continue
            meta = json.load(open(mp))
            label = meta.get("class_label")
            seed = meta.get("seed")
            if label is None or seed is None or CLASS_MAP.get(label) is None:
                continue
            if clean_photo_path(s) is None or load_gt_T(s) is None:
                continue
            groups.setdefault((label, seed), []).append(s)
    return groups


def extract_one(sample, size, design, sheet_t_img=None):
    oracle = CLASS_MAP[json.load(open(os.path.join(sample, "meta.json"))).get("class_label")]
    photo = clean_photo_path(sample)
    lin = extract.load_linear(photo, None, size)
    if design == "oracle":
        m = extract.extract_maps(lin, oracle, mark_region="none", anchor="class")
    else:
        cls, anchor = DESIGNS[design]
        m = extract.extract_maps(lin, cls, mark_region="none", anchor=anchor, sheet_t_img=sheet_t_img)
    return m["T"], m["h"]


def group_pooled_t_img(samples, size):
    """Report 020: pool the continuous anchor's per-photo t_img across every
    lighting of one (recipe,seed) group -- the synthetic stand-in for
    'several photos of the same sheet' -- into one scale (estimate_anchor_
    scale_sheet, median across photos)."""
    lins = [extract.load_linear(clean_photo_path(s), None, size) for s in samples]
    return extract.estimate_anchor_scale_sheet(lins)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", action="append", required=True, help="synthetic_data folder (read-only); repeatable")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "cross_lighting"))
    ap.add_argument("--size", type=int, default=700)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    groups = group_samples(args.data)
    print(f"{len(groups)} (recipe,seed) groups: " +
          ", ".join(f"{k[0]}/seed{k[1]}(n={len(v)})" for k, v in sorted(groups.items())))

    rows = []  # per (label, seed, design): invariance + gt-error
    for (label, seed), samples in sorted(groups.items()):
        if len(samples) < 2:
            print(f"  skip {label}/seed{seed}: only {len(samples)} lighting(s), need >=2 for a pair")
            continue
        mark = load_gt_mask(samples[0], "gt_mark_mask.png")

        for design in DESIGNS:
            sheet_t_img = group_pooled_t_img(samples, args.size) if design == "continuous_persheet" else None
            maps = []  # (T, h, gtT_r, gth_r, valid)
            for s in samples:
                T, h = extract_one(s, args.size, design, sheet_t_img=sheet_t_img)
                H, W = h.shape
                gtT = load_gt_T(s)
                gth = load_gt_h(s)
                gtT_r = resize_to(gtT, (H, W)) if gtT is not None else None
                gth_r = resize_to(gth[..., None] if gth.ndim == 2 else gth, (H, W)) if gth is not None else None
                if gth_r is not None and gth_r.ndim == 3:
                    gth_r = gth_r[..., 0]
                valid = np.ones((H, W), bool)
                if mark is not None:
                    valid &= ~(resize_to(mark, (H, W)) > 0.5)
                maps.append((os.path.basename(s), T, h, gtT_r, gth_r, valid))

            # pairwise cross-lighting disagreement (the invariance metric)
            pair_dT, pair_dh = [], []
            for (na, Ta, ha, _, _, va), (nb, Tb, hb, _, _, vb) in itertools.combinations(maps, 2):
                v = va & vb
                vt = v[..., None] * np.ones((1, 1, 3), bool)
                pair_dT.append(float(np.abs(Ta - Tb)[vt].mean()))
                pair_dh.append(float(np.abs(ha - hb)[v].mean()))

            # per-sample GT-error, for context (accuracy floor the invariance
            # number should sit under)
            gt_dT, gt_dh = [], []
            for name, T, h, gtT_r, gth_r, valid in maps:
                if gtT_r is None or gth_r is None:
                    continue
                vt = valid[..., None] * np.ones((1, 1, 3), bool)
                gt_dT.append(float(np.abs(T - gtT_r)[vt].mean()))
                gt_dh.append(float(np.abs(h - gth_r)[valid].mean()))

            rows.append(dict(label=label, oracle_class=CLASS_MAP[label], seed=seed, design=design,
                              n_lightings=len(samples), n_pairs=len(pair_dT),
                              invariance_T=float(np.mean(pair_dT)), invariance_h=float(np.mean(pair_dh)),
                              gt_T_mae=float(np.mean(gt_dT)) if gt_dT else None,
                              gt_h_mae=float(np.mean(gt_dh)) if gt_dh else None))
            print(f"  {label:12s} seed{seed} design={design:11s} n={len(samples)} pairs={len(pair_dT):2d} "
                  f"invariance_T={rows[-1]['invariance_T']:.4f} invariance_h={rows[-1]['invariance_h']:.4f} "
                  f"gt_T_mae={rows[-1]['gt_T_mae']:.4f} gt_h_mae={rows[-1]['gt_h_mae']:.4f}")

    with open(os.path.join(args.out, "cross_lighting_rows.json"), "w") as f:
        json.dump(rows, f, indent=2)

    # ---------------- aggregation: per recipe (label), weighted by pair count ----------------
    labels = sorted({r["label"] for r in rows})
    lines = ["| recipe | design | n groups | n pairs | invariance T_mae | invariance h_mae | "
             "GT T_mae (context) | GT h_mae (context) |",
             "|---|---|---|---|---|---|---|---|"]
    for label in labels:
        for design in DESIGNS:
            sel = [r for r in rows if r["label"] == label and r["design"] == design]
            if not sel:
                continue
            npairs = sum(r["n_pairs"] for r in sel)
            if npairs == 0:
                continue
            invT = sum(r["invariance_T"] * r["n_pairs"] for r in sel) / npairs
            invh = sum(r["invariance_h"] * r["n_pairs"] for r in sel) / npairs
            gtT = float(np.mean([r["gt_T_mae"] for r in sel if r["gt_T_mae"] is not None]))
            gth = float(np.mean([r["gt_h_mae"] for r in sel if r["gt_h_mae"] is not None]))
            lines.append(f"| {label} | {design} | {len(sel)} | {npairs} | {invT:.4f} | {invh:.4f} | "
                         f"{gtT:.4f} | {gth:.4f} |")

    md = "\n".join(lines)
    with open(os.path.join(args.out, "cross_lighting_table.md"), "w") as f:
        f.write(md + "\n")
    print("\n" + md)
    print(f"\noutputs in {args.out}")


if __name__ == "__main__":
    main()
