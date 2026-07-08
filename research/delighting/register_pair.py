#!/usr/bin/env python3
"""Cross-lighting validation harness (metric M3 from report 001).

Two handheld photos of the SAME sheet under DIFFERENT lighting (a cross-lighting
pair, or a shadow / no-shadow pair). If the extracted material maps T,h are
real physical properties they must be invariant to the lighting, so:

  1. register B onto A (homography from the four sheet corners; auto-detect via
     ORB if corners are omitted and the framing is close),
  2. extract T,h independently from A and from B,
  3. forward-render A's material under B's illumination estimate and compare to
     the registered photo B.

Two numbers come out, and they probe different things:

  * T-agreement MAE  -- |sRGB(T_A) - sRGB(T_B)| over the sheet. The strong test:
    material maps from two lightings must match. Needs no background model, so
    this is the number to trust.
  * cross-recon MAE  -- render A's (T,h) under B's illumination field L_B and
    B's through-glass background, compare to photo B. Reuses extract.reconstruct
    unchanged (same quarter-res background surrogate as the self-recon metric),
    so it is directly comparable to the per-photo self-recon MAE in results/.
    Its background term is an estimate, so read it as corroboration, not proof.

Usage
-----
  register_pair.py A.jpg B.jpg --class wispy [options]

  --corners-a x0,y0,...,x3,y3   four sheet corners in A, order TL,TR,BR,BL
  --corners-b x0,y0,...,x3,y3   same four corners in B
        Both given -> each photo is rectified to a canonical rectangle, so they
        are pixel-aligned by construction (the robust path; recommended).
        Neither given -> ORB feature homography B->A (needs similar framing;
        errors out if too few inliers -- pass corners in that case).
  --mark-region R   passed through to extraction (e.g. bottom-right / none)
  --out DIR         default results/pairs
  --size N          working resolution, max dim (default 700)

Writes  <A>__<B>_pair.jpg  (original A | registered B | T_A | T_B | pred B | err x5),
        <A>__<B>_reg.jpg    (checkerboard blend of A and registered B),
        <A>__<B>_metrics.json.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import (extract_maps, lin_to_srgb, reconstruct, srgb_to_lin, tile)  # noqa: E402


def _corners(s):
    v = [float(x) for x in s.split(",")]
    if len(v) != 8:
        raise argparse.ArgumentTypeError("need 8 numbers: x0,y0,x1,y1,x2,y2,x3,y3 (TL,TR,BR,BL)")
    return np.array(v, np.float32).reshape(4, 2)


def canonical_size(quad, size):
    """Pixel dims of the rectified rectangle from a corner quad (TL,TR,BR,BL)."""
    tl, tr, br, bl = quad
    w = 0.5 * (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl))
    h = 0.5 * (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr))
    s = size / max(w, h)
    return max(8, int(round(w * s))), max(8, int(round(h * s)))


def rectify(srgb_u8, quad, out_w, out_h):
    """Warp the sheet quad (TL,TR,BR,BL, in original pixels) to a canonical rect."""
    dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], np.float32)
    H = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    return cv2.warpPerspective(srgb_u8, H, (out_w, out_h), flags=cv2.INTER_LANCZOS4,
                               borderMode=cv2.BORDER_REPLICATE)


def orb_register(src_u8, ref_u8):
    """Homography warping src onto ref via ORB + RANSAC. Returns (warped, n_inliers)."""
    g_s = cv2.cvtColor(src_u8, cv2.COLOR_RGB2GRAY)
    g_r = cv2.cvtColor(ref_u8, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(4000)
    k_s, d_s = orb.detectAndCompute(g_s, None)
    k_r, d_r = orb.detectAndCompute(g_r, None)
    if d_s is None or d_r is None:
        return None, 0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(bf.match(d_s, d_r), key=lambda m: m.distance)[:400]
    if len(matches) < 12:
        return None, len(matches)
    p_s = np.float32([k_s[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    p_r = np.float32([k_r[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(p_s, p_r, cv2.RANSAC, 4.0)
    if H is None:
        return None, 0
    warped = cv2.warpPerspective(src_u8, H, (ref_u8.shape[1], ref_u8.shape[0]),
                                 flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    return warped, int(mask.sum())


def load_u8(path, size):
    im = Image.open(path).convert("RGB")
    w0, h0 = im.size
    s = size / max(w0, h0)
    return np.asarray(im.resize((int(w0 * s), int(h0 * s)), Image.LANCZOS))


def checker_blend(a, b, cells=12):
    """Checkerboard of a and b to eyeball registration alignment."""
    H, W = a.shape[:2]
    step = max(1, W // cells)
    yy, xx = np.mgrid[0:H, 0:W]
    m = (((xx // step) + (yy // step)) % 2 == 0)[..., None]
    return np.where(m, a, b)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo_a")
    ap.add_argument("photo_b")
    ap.add_argument("--class", dest="glass_class", required=True)
    ap.add_argument("--corners-a", type=_corners)
    ap.add_argument("--corners-b", type=_corners)
    ap.add_argument("--mark-region", default="unknown")
    ap.add_argument("--out", default="results/pairs")
    ap.add_argument("--size", type=int, default=700)
    args = ap.parse_args()

    na = os.path.splitext(os.path.basename(args.photo_a))[0]
    nb = os.path.splitext(os.path.basename(args.photo_b))[0]
    n_inliers = None

    # --- register B onto A ---
    if args.corners_a is not None and args.corners_b is not None:
        # rectify at native resolution (corners are in original pixels), then
        # scale the canonical rect to the working size
        ow, oh = canonical_size(args.corners_a, args.size)
        a_u8 = rectify(np.asarray(Image.open(args.photo_a).convert("RGB")), args.corners_a, ow, oh)
        b_u8 = rectify(np.asarray(Image.open(args.photo_b).convert("RGB")), args.corners_b, ow, oh)
    else:
        a_u8 = load_u8(args.photo_a, args.size)
        b_u8, n_inliers = orb_register(load_u8(args.photo_b, args.size), a_u8)
        if b_u8 is None:
            sys.exit(f"ORB registration failed (inliers={n_inliers}); pass --corners-a / --corners-b")
        print(f"  ORB registration: {n_inliers} inliers")

    a_lin = srgb_to_lin(a_u8.astype(np.float64) / 255)
    b_lin = srgb_to_lin(b_u8.astype(np.float64) / 255)

    # --- extract material from each photo independently ---
    ma = extract_maps(a_lin, args.glass_class, args.mark_region)
    mb = extract_maps(b_lin, args.glass_class, args.mark_region)
    T_a, h_a = ma["T"], ma["h"]
    T_b = mb["T"]

    # --- forward-render A's material under B's illumination, compare to photo B ---
    # mb["L"], mb["R"] are already anchored on the same absolute scale as T_a
    # (both use the class T_ANCHOR), so crossing A's T,h with B's light+background
    # is scale-consistent.
    pred_b, _ = reconstruct(mb["L"], T_a, h_a, mb["R"])
    err = np.abs(lin_to_srgb(np.clip(pred_b, 0, 1)) - lin_to_srgb(np.clip(mb["lin_ns"], 0, 1)))
    valid = ~(mb["mark_mask"] | mb["spec_mask"])

    t_err = np.abs(lin_to_srgb(T_a) - lin_to_srgb(T_b))
    tv = ~(ma["mark_mask"] | ma["spec_mask"] | mb["mark_mask"] | mb["spec_mask"])

    metrics = {
        "pair": f"{na}__{nb}", "glass_class": args.glass_class,
        "registration": "corners" if n_inliers is None else f"orb:{n_inliers}",
        "T_agreement_mae_srgb255": float(t_err[tv].mean() * 255),
        "T_agreement_p95_srgb255": float(np.percentile(t_err[tv], 95) * 255),
        "cross_recon_mae_srgb255": float(err[valid].mean() * 255),
        "cross_recon_p95_srgb255": float(np.percentile(err[valid], 95) * 255),
    }

    os.makedirs(args.out, exist_ok=True)
    stem = f"{args.out}/{na}__{nb}"
    cols = [
        tile(a_lin, "A original"),
        tile(b_lin, "B registered"),
        tile(T_a, "T from A"),
        tile(T_b, "T from B"),
        tile(np.clip(pred_b, 0, 1), "B predicted from A"),
        tile(np.clip(err * 5, 0, 1), "|err| x5", is_linear=False),
    ]
    hh = max(c.shape[0] for c in cols)
    cols = [np.pad(c, ((0, hh - c.shape[0]), (3, 3), (0, 0)), constant_values=25) for c in cols]
    Image.fromarray(np.concatenate(cols, axis=1)).save(f"{stem}_pair.jpg", quality=88)
    Image.fromarray(checker_blend(a_u8, b_u8)).save(f"{stem}_reg.jpg", quality=90)
    with open(f"{stem}_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"{na} vs {nb}: T-agreement MAE={metrics['T_agreement_mae_srgb255']:.2f}/255 "
          f"(p95 {metrics['T_agreement_p95_srgb255']:.1f}), "
          f"cross-recon MAE={metrics['cross_recon_mae_srgb255']:.2f}/255")


if __name__ == "__main__":
    main()
