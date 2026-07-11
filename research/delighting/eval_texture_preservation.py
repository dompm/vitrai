#!/usr/bin/env python3
"""Texture-preservation metrics (report 034, EVAL_PROTOCOL.md metric family 2).

The consistency metrics reward a de-lighting method for producing the SAME
canonical material from different captures. Taken alone they can be gamed by a
method that FLATTENS the sheet -- a spatially-smooth map is trivially consistent
across captures but has thrown away the streaks, seed-bubbles, and hammered
relief that make the glass legible as glass (reports 013/014/029/031). This
module measures the opposite pressure: the high-frequency structure of the sheet
must SURVIVE de-lighting.

Two metrics, both defined in EVAL_PROTOCOL.md sec 3:

  1. MULTISCALE GRADIENT PRESERVATION (MGP). Band-pass the luminance of a
     reference and a test map at a set of scales; at each scale report the
     Pearson correlation of the gradient-magnitude fields and the retained
     gradient energy ratio. The FINE bands (small sigma) carry the texture we
     must keep; the COARSE bands carry the illumination envelope we are allowed
     (indeed want) to change, so a low coarse-band correlation is fine and only
     the fine-band score is a pass/fail signal.

  2. FEATURE-CORRESPONDENCE SURVIVAL (FCS). Detect salient texture features
     (ORB keypoints on the reference) and measure the fraction that still land on
     a feature in the test map within a small radius. This is the streak/bubble/
     relief-cue survival number an artist cares about (report 012's "is this
     derived from the real sheet or invented").

Reference signal (EVAL_PROTOCOL.md sec 1b):
  * SYNTHETIC: reference = authored gt_T; test = extracted T. Texture in the
    intrinsic map must match the authored intrinsic map. (`--mode gt`.)
  * REAL registered pair: reference = de-lit T from capture A; test = de-lit T
    from capture B at the SAME registered coordinates. Texture must both survive
    AND agree. (`--mode pair`, feed two aligned maps.)
  * REAL single capture (the runnable frozen-baseline subset here): reference =
    the input PHOTO's high-frequency structure; test = the de-lit T. The photo's
    texture must survive de-lighting. This cannot distinguish real relief from
    baked see-through background, so it is a NECESSARY-not-sufficient screen --
    a method that fails it has definitely over-flattened. (`--mode photo`, the
    default for the library/benchmark run.)

Run (frozen-baseline reference row, report 034):
  python3 eval_texture_preservation.py --library --illum classical
  python3 eval_texture_preservation.py --library --illum quotient
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract  # noqa: E402

# Fine bands (sigma 1,2) carry streak/bubble/relief texture; coarse bands (4,8)
# carry the illumination envelope de-lighting is allowed to change.
SCALES = [1.0, 2.0, 4.0, 8.0]
FINE_SCALES = {1.0, 2.0}


def _luma(lin):
    return extract.lum(np.clip(lin, 0, None)).astype(np.float64)


def bandpass(y, sigma):
    """Difference-of-Gaussian band centred near `sigma` (octave-wide)."""
    return extract.gauss(y, sigma) - extract.gauss(y, 2.0 * sigma)


def grad_mag(y):
    gx = cv2.Sobel(y, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(y, cv2.CV_64F, 0, 1, ksize=3)
    return np.sqrt(gx * gx + gy * gy)


def _pearson(a, b, mask):
    a, b = a[mask], b[mask]
    a = a - a.mean()
    b = b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 1e-12 else 0.0


def multiscale_gradient_preservation(ref_lin, test_lin, mask=None, scales=SCALES):
    """Per-scale gradient-magnitude correlation + retained energy of `test`
    relative to `ref` (both linear RGB). Returns per-scale dict and the
    fine-band summary (the pass/fail number)."""
    yr, yt = _luma(ref_lin), _luma(test_lin)
    if mask is None:
        mask = np.ones(yr.shape, bool)
    per_scale = {}
    fine_corrs, fine_retain = [], []
    for s in scales:
        gr = grad_mag(bandpass(yr, s))
        gt = grad_mag(bandpass(yt, s))
        corr = _pearson(gr, gt, mask)
        # retained energy: how much reference gradient magnitude the test keeps
        # (>1 = test is MORE textured than ref, e.g. it injected structure).
        er = float(np.sqrt((gr[mask] ** 2).mean()))
        et = float(np.sqrt((gt[mask] ** 2).mean()))
        retain = et / er if er > 1e-9 else 0.0
        per_scale[f"sigma{int(s)}"] = {"grad_corr": corr, "retained_energy": retain}
        if s in FINE_SCALES:
            fine_corrs.append(corr)
            fine_retain.append(retain)
    return {
        "per_scale": per_scale,
        "fine_grad_corr": float(np.mean(fine_corrs)),
        "fine_retained_energy": float(np.mean(fine_retain)),
    }


def feature_correspondence_survival(ref_lin, test_lin, mask=None, radius=6, n_features=500):
    """Fraction of ORB keypoints found on `ref` that survive (land within
    `radius` px of an ORB keypoint) on `test`. Texture-feature survival."""
    def u8(lin):
        return (np.clip(extract.lin_to_srgb(np.clip(lin, 0, 1)), 0, 1) * 255).astype(np.uint8)

    gref = cv2.cvtColor(u8(ref_lin), cv2.COLOR_RGB2GRAY)
    gtest = cv2.cvtColor(u8(test_lin), cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(n_features)
    kr = orb.detect(gref, None)
    kt = orb.detect(gtest, None)
    if mask is not None:
        kr = [k for k in kr if mask[int(round(k.pt[1])), int(round(k.pt[0]))]]
        kt = [k for k in kt if mask[int(round(k.pt[1])), int(round(k.pt[0]))]]
    if not kr:
        return {"n_ref_kp": 0, "survival": None}
    if not kt:
        return {"n_ref_kp": len(kr), "n_test_kp": 0, "survival": 0.0}
    pts_t = np.array([k.pt for k in kt])
    survived = 0
    for k in kr:
        d = np.hypot(pts_t[:, 0] - k.pt[0], pts_t[:, 1] - k.pt[1])
        if d.min() <= radius:
            survived += 1
    return {"n_ref_kp": len(kr), "n_test_kp": len(kt),
            "survival": float(survived / len(kr))}


def evaluate(ref_lin, test_lin, mask=None):
    """Both texture-preservation metrics for a (reference, test) map pair."""
    return {
        "mgp": multiscale_gradient_preservation(ref_lin, test_lin, mask),
        "fcs": feature_correspondence_survival(ref_lin, test_lin, mask),
    }


# ---------------------------------------------------------------- baseline run
def _library_items():
    lib = os.path.join(HERE, "benchmark", "library")
    man = json.load(open(os.path.join(lib, "manifest.json")))
    items = [(os.path.join(lib, n), e["class_override"], e.get("corners"),
              e.get("mark_region", "none")) for n, e in man.items()]
    bench = os.path.join(HERE, "benchmark")
    bman = json.load(open(os.path.join(bench, "manifest.json")))
    for n, e in bman.items():
        items.append((os.path.join(bench, n), e["class_override"], e.get("corners"),
                      e.get("mark_region", "none")))
    return items


def run_library(illum, size, out_dir):
    """Frozen-baseline row: texture preservation of the de-lit T vs the input
    PHOTO on the 9 real library sheets + 2 benchmark images (mode=photo). Also
    scores a FLATTEN control (Gaussian-blurred photo) to prove the metric
    catches over-flattening -- the failure mode the drag test can be gamed by."""
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for path, gclass, corners, mark in _library_items():
        lin = extract.load_linear(path, corners, size)
        maps = extract.extract_maps(lin, gclass, mark_region=mark, illum=illum)
        T = maps["T"]
        valid = ~(maps.get("mark_mask", np.zeros(T.shape[:2], bool)))
        row = {"image": os.path.basename(path), "class": gclass, "illum": illum}
        row["T_vs_photo"] = evaluate(lin, T, valid)
        # flatten control: an 8-sigma blur of the photo is a stand-in for an
        # over-flattening method; the metric MUST score it far worse than T.
        flat = extract.gauss(lin, 8.0)
        row["flatten_control_vs_photo"] = evaluate(lin, flat, valid)
        rows.append(row)
        print(f"{row['image']:20s} [{gclass:14s}] {illum:9s} "
              f"T fine_corr={row['T_vs_photo']['mgp']['fine_grad_corr']:.3f} "
              f"fcs={row['T_vs_photo']['fcs']['survival']:.3f}  | "
              f"flatten fine_corr={row['flatten_control_vs_photo']['mgp']['fine_grad_corr']:.3f} "
              f"fcs={row['flatten_control_vs_photo']['fcs']['survival']:.3f}")

    def agg(key):
        corr = np.mean([r[key]["mgp"]["fine_grad_corr"] for r in rows])
        ret = np.mean([r[key]["mgp"]["fine_retained_energy"] for r in rows])
        surv = np.mean([r[key]["fcs"]["survival"] for r in rows if r[key]["fcs"]["survival"] is not None])
        return {"fine_grad_corr": float(corr), "fine_retained_energy": float(ret),
                "fcs_survival": float(surv)}

    summary = {"illum": illum, "size": size, "n_images": len(rows),
               "mode": "photo (T vs input photo high-frequency)",
               "aggregate_T": agg("T_vs_photo"),
               "aggregate_flatten_control": agg("flatten_control_vs_photo"),
               "per_image": rows}
    out = os.path.join(out_dir, f"texture_preservation_{illum}.json")
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\naggregate T:      {json.dumps(summary['aggregate_T'])}")
    print(f"aggregate FLATTEN: {json.dumps(summary['aggregate_flatten_control'])}")
    print(f"wrote {out}")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", action="store_true",
                    help="run the frozen-baseline library+benchmark row")
    ap.add_argument("--illum", default="classical", choices=["classical", "quotient"])
    ap.add_argument("--size", type=int, default=700)
    ap.add_argument("--out", default=os.path.join(HERE, "results", "texture_preservation"))
    args = ap.parse_args()
    if args.library:
        run_library(args.illum, args.size, args.out)
    else:
        ap.error("nothing to do; pass --library (map-pair use is via evaluate() import)")


if __name__ == "__main__":
    main()
