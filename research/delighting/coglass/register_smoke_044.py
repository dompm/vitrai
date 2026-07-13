#!/usr/bin/env python3
"""Iteration 044 -- registration smoke test on sampled coglassworks pairs.

Question this answers (task step 4): same-piece coglassworks photos are
mostly held-sheet shots at DIFFERENT hand angles (report 041 SS2.4) -- do
such pairs ORB-register at all? The answer decides whether this dataset
plugs into the registered-consistency benchmark (like Delphi's 145
registrable pairs) or mostly into the weak/statistics-only pool.

Method: sample N pairs from results/pairs_044.json, stratified to
over-sample cross_condition pairs (the prize class), run the SAME code path
as the Delphi harvest (register_pair.orb_register at 700px working res,
inliers >= 20 -> registrable; central-region MAD < 10 with high gradient
correlation -> same_photo derivation, i.e. dedup metadata not a pair).
Writes results/register_smoke_044.json + per-pair checkerboard blends under
results/smoke_panels_044/ (small, committed) for eyeball verification.
"""
import argparse
import json
import os
import random
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from register_pair import orb_register, load_u8, checker_blend  # noqa: E402

PAIRS = os.path.join(HERE, "results", "pairs_044.json")
IMG_ROOT = os.path.join(HERE, "data", "images")
OUT = os.path.join(HERE, "results", "register_smoke_044.json")
PANELS = os.path.join(HERE, "results", "smoke_panels_044")

ORB_INLIER_THRESH = 20
SAME_PHOTO_MAD = 10.0
REG_SIZE = 700


def central_residual(ref, warped):
    H, W = ref.shape[:2]
    cy, cx = H // 2, W // 2
    ch, cw = H // 3, W // 3
    r = ref[cy - ch // 2:cy + ch // 2, cx - cw // 2:cx + cw // 2].astype(np.float32)
    w_ = warped[cy - ch // 2:cy + ch // 2, cx - cw // 2:cx + cw // 2].astype(np.float32)
    mad = float(np.median(np.abs(r - w_)))
    gr = cv2.Sobel(cv2.cvtColor(r.astype(np.uint8), cv2.COLOR_RGB2GRAY), cv2.CV_32F, 1, 1)
    gw = cv2.Sobel(cv2.cvtColor(w_.astype(np.uint8), cv2.COLOR_RGB2GRAY), cv2.CV_32F, 1, 1)
    denom = gr.std() * gw.std()
    cc = float((gr * gw).mean() / denom) if denom > 1e-6 else 0.0
    return mad, cc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--n-cross", type=int, default=10,
                    help="how many of --n to draw from cross_condition pairs")
    ap.add_argument("--seed", type=int, default=44)
    ap.add_argument("--tiers", default="variant,handle,handle_prefix,prefix_sibling",
                    help="verification tiers eligible for sampling")
    args = ap.parse_args()

    with open(PAIRS) as f:
        data = json.load(f)
    tiers = set(args.tiers.split(","))
    eligible = [p for p in data["pairs"] if p["tier"] in tiers]
    cross = [p for p in eligible if p["pair_class"] == "cross_condition"]
    same = [p for p in eligible if p["pair_class"] == "same_condition"]
    rng = random.Random(args.seed)
    sample = (rng.sample(cross, min(args.n_cross, len(cross)))
              + rng.sample(same, min(args.n - min(args.n_cross, len(cross)), len(same))))
    print(f"sampled {len(sample)} pairs "
          f"({sum(1 for p in sample if p['pair_class'] == 'cross_condition')} cross-condition)")

    os.makedirs(PANELS, exist_ok=True)
    results = []
    for p in sample:
        pa = os.path.join(IMG_ROOT, p["handle"], p["a"])
        pb = os.path.join(IMG_ROOT, p["handle"], p["b"])
        rec = dict(p)
        try:
            a = load_u8(pa, REG_SIZE)
            b = load_u8(pb, REG_SIZE)
            warped, inliers = orb_register(b, a)
            rec["inliers"] = inliers
            if warped is None or inliers < ORB_INLIER_THRESH:
                rec["verdict"] = "not_registrable"
            else:
                mad, cc = central_residual(a, warped)
                rec["residual_mad"] = round(mad, 2)
                rec["grad_corr"] = round(cc, 3)
                if mad < SAME_PHOTO_MAD and cc > 0.8:
                    rec["verdict"] = "same_photo_derivation"
                else:
                    rec["verdict"] = "cross_capture_registrable"
                blend = checker_blend(a, warped)
                name = f"{p['token']}_{os.path.splitext(p['a'])[0]}__{os.path.splitext(p['b'])[0]}.jpg"
                Image.fromarray(blend).resize(
                    (blend.shape[1] // 2, blend.shape[0] // 2)).save(
                    os.path.join(PANELS, name), quality=72)
                rec["panel"] = name
        except Exception as e:
            rec["verdict"] = f"error: {e}"
        results.append(rec)
        print(f"  {p['token']} {p['a']} x {p['b']} [{p['pair_class']}] "
              f"-> {rec['verdict']} (inliers={rec.get('inliers')})", flush=True)

    from collections import Counter
    agg = dict(Counter(r["verdict"] for r in results))
    agg_cross = dict(Counter(r["verdict"] for r in results
                             if r["pair_class"] == "cross_condition"))
    summary = {"n": len(results), "verdicts": agg,
               "verdicts_cross_condition_only": agg_cross}
    with open(OUT, "w") as f:
        json.dump({"summary": summary, "pairs": results}, f, indent=1)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
