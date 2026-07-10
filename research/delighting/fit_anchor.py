#!/usr/bin/env python3
"""Report 017: refit + leave-one-RECIPE-out (LORO) evaluate the continuous
anchor's regression (extract.anchor_features -> t_img).

Report 016 shipped `ANCHOR_COEF`/`ANCHOR_FEAT_MU`/`ANCHOR_FEAT_SD` from a ridge
fit (lam=2.0) in logit space on the 26 synthetic-v2 samples across 5 recipes,
and flagged the honest limit: the dark end of that fit is calibrated by ONE
dark recipe family, so leave-that-recipe-out cannot predict dark at all (LORO
worst ~4.2x). This script reproduces that baseline and refits on a widened set
that adds three new dark-family recipes (report 017: dark-deep, dark-ruby,
dark-slate), then re-measures LORO worst-case before/after.

Model (unchanged from report 016): t_img = T_LO + (T_HI-T_LO) *
sigmoid(c0 + c.(x-mu)/sd), x = extract.anchor_features(lin) = [log p95(Y),
luminance-gated mean saturation, lit-pixel fraction]. mu/sd are the TRAINING
SET's own feature mean/std (recomputed per fit, not hardcoded), matching how
report 016 was produced.

Usage:
  fit_anchor.py --data DIR [--data DIR2 ...] --recipes-before r1,r2,...
                [--t-lo 0.10] [--t-hi 0.98] [--lam 2.0] [--size 700]
                [--out DIR] [--ship]

--recipes-before restricts the "before" LORO run to the listed class_labels
(the original 5-recipe set) even when --data points at a directory that also
contains the new dark recipes; the "after" run always uses every recipe found.
--ship prints the ANCHOR_* constants (fit on ALL provided data) ready to paste
into extract.py.
"""
import argparse
import glob
import json
import os
import sys

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract  # noqa: E402
from eval_synthetic import load_gt_T, clean_photo_path  # noqa: E402


def load_samples(data_dirs):
    rows = []
    for d in data_dirs:
        for s in sorted(glob.glob(os.path.join(d, "*"))):
            if not os.path.isdir(s):
                continue
            mp = os.path.join(s, "meta.json")
            if not os.path.exists(mp):
                continue
            meta = json.load(open(mp))
            label = meta.get("class_label")
            photo = clean_photo_path(s)
            gtT = load_gt_T(s)
            if label is None or photo is None or gtT is None:
                continue
            rows.append(dict(sample=os.path.basename(s), label=label, photo=photo,
                              gt_scale=float(np.percentile(gtT, 99))))
    return rows


def features_targets(rows, size):
    X, y, labels = [], [], []
    for r in rows:
        lin = extract.load_linear(r["photo"], None, size)
        X.append(extract.anchor_features(lin))
        y.append(r["gt_scale"])
        labels.append(r["label"])
        print(f"  {r['label']:12s} {r['sample']:40s} x={np.round(X[-1],3)} gt_p99={y[-1]:.4f}", flush=True)
    return np.array(X), np.array(y), np.array(labels)


def fit_ridge_logit(X, y, t_lo, t_hi, lam):
    mu = X.mean(0)
    sd = X.std(0)
    sd = np.where(sd < 1e-6, 1e-6, sd)
    Xn = (X - mu) / sd
    z = np.clip((y - t_lo) / (t_hi - t_lo), 1e-4, 1 - 1e-4)
    target = np.log(z / (1 - z))
    A = np.hstack([np.ones((Xn.shape[0], 1)), Xn])
    lam_mat = lam * np.eye(A.shape[1])
    lam_mat[0, 0] = 0.0  # do not regularize the intercept
    coef = np.linalg.solve(A.T @ A + lam_mat, A.T @ target)
    return coef, mu, sd


def predict(X, coef, mu, sd, t_lo, t_hi):
    Xn = (X - mu) / sd
    s = coef[0] + Xn @ coef[1:]
    return t_lo + (t_hi - t_lo) / (1.0 + np.exp(-s))


def loro(X, y, labels, t_lo, t_hi, lam):
    per_recipe = {}
    worst = 0.0
    for held in sorted(set(labels)):
        train, test = labels != held, labels == held
        if train.sum() == 0 or test.sum() == 0:
            continue
        coef, mu, sd = fit_ridge_logit(X[train], y[train], t_lo, t_hi, lam)
        pred = predict(X[test], coef, mu, sd, t_lo, t_hi)
        ratios = np.maximum(pred / y[test], y[test] / pred)
        per_recipe[held] = dict(mean=float(ratios.mean()), worst=float(ratios.max()),
                                 n=int(test.sum()), gt_range=[float(y[test].min()), float(y[test].max())],
                                 pred_range=[float(pred.min()), float(pred.max())])
        worst = max(worst, float(ratios.max()))
    return worst, per_recipe


def report(name, X, y, labels, t_lo, t_hi, lam):
    worst, per_recipe = loro(X, y, labels, t_lo, t_hi, lam)
    print(f"\n### LORO -- {name} (T_LO={t_lo}, T_HI={t_hi}, lam={lam}, "
          f"{len(set(labels))} recipes, {len(y)} samples)")
    print("| held-out recipe | n | gt range | pred range | mean ratio | worst ratio |")
    print("|---|---|---|---|---|---|")
    for r, v in per_recipe.items():
        print(f"| {r} | {v['n']} | {v['gt_range'][0]:.3f}-{v['gt_range'][1]:.3f} | "
              f"{v['pred_range'][0]:.3f}-{v['pred_range'][1]:.3f} | {v['mean']:.2f}x | {v['worst']:.2f}x |")
    print(f"**LORO worst-case: {worst:.2f}x**")
    return worst, per_recipe


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", action="append", required=True)
    ap.add_argument("--recipes-before", default=None,
                    help="comma list of class_labels for the BEFORE (original set) LORO run")
    ap.add_argument("--t-lo", type=float, default=0.10)
    ap.add_argument("--t-hi", type=float, default=0.98)
    ap.add_argument("--lam", type=float, default=2.0)
    ap.add_argument("--size", type=int, default=700)
    ap.add_argument("--out", default=os.path.join(HERE, "results", "anchor_refit"))
    ap.add_argument("--ship", action="store_true", help="print constants fit on ALL data")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    rows = load_samples(args.data)
    print(f"loaded {len(rows)} samples, recipes: {sorted(set(r['label'] for r in rows))}")
    X, y, labels = features_targets(rows, args.size)
    np.save(os.path.join(args.out, "X.npy"), X)
    np.save(os.path.join(args.out, "y.npy"), y)
    json.dump(labels.tolist(), open(os.path.join(args.out, "labels.json"), "w"))

    results = {}
    if args.recipes_before:
        before_set = set(args.recipes_before.split(","))
        sel = np.array([l in before_set for l in labels])
        worst_before, pr_before = report("BEFORE (original recipe set)", X[sel], y[sel], labels[sel],
                                          args.t_lo, args.t_hi, args.lam)
        results["before"] = dict(worst=worst_before, per_recipe=pr_before, t_lo=args.t_lo)

    worst_after, pr_after = report("AFTER (widened recipe set)", X, y, labels, args.t_lo, args.t_hi, args.lam)
    results["after"] = dict(worst=worst_after, per_recipe=pr_after, t_lo=args.t_lo)

    if args.ship:
        coef, mu, sd = fit_ridge_logit(X, y, args.t_lo, args.t_hi, args.lam)
        print("\n### Ship (fit on ALL provided data)")
        print(f"ANCHOR_T_LO, ANCHOR_T_HI = {args.t_lo}, {args.t_hi}")
        print(f"ANCHOR_FEAT_MU = np.array([{', '.join(f'{v:.6g}' for v in mu)}])")
        print(f"ANCHOR_FEAT_SD = np.array([{', '.join(f'{v:.6g}' for v in sd)}])")
        print(f"ANCHOR_COEF = np.array([{', '.join(f'{v:.6g}' for v in coef)}])")
        results["ship"] = dict(mu=mu.tolist(), sd=sd.tolist(), coef=coef.tolist())

    with open(os.path.join(args.out, "fit_results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(f"\noutputs in {args.out}")


if __name__ == "__main__":
    main()
