#!/usr/bin/env python3
"""Report 053b — EQUIVALENCE TEST: lazy crop warp == the old materialized crop/ files.

The 053 crop pass materialized a cropped duplicate of every GT channel into <sample>/crop/
(~150MB/sample). 053b makes GT crops LAZY (crop_sim.warp_channel applied at load time from the
homography stored in meta.json). Before deleting the materialized duplicates, this test asserts
on data that carries BOTH representations (the 68-sample deployment pilot) that

    warp_channel(read(original_file), meta.crop_sim.homography)  ==  read(crop/<file>)

channel by channel, sample by sample:
  * label channels (gt_mark_*): NEAREST warp of integer arrays -> EXACT equality required.
  * continuous integer PNGs (gt_T/gt_h/...): LINEAR warp of uint arrays, PNG lossless -> EXACT.
  * float EXRs: LINEAR warp of float arrays; the materialized file went through cv2's EXR
    encoder (half-float on write is possible) -> tolerance --float-tol (default 2e-3, half-
    precision grade). The observed max diff is printed so the real fidelity is on record.

Also runs a LOADER wiring check on one sample: GlassDelightDataset(crop_view=True) must produce
the same T/photo as manually warping the originals through the loader's own decode chain.

Usage: verify_lazy_crop_053b.py --root pilot_053_out [--float-tol 2e-3] [--max-samples N]
Exit 0 = all pass (safe to slim crop/ dirs); exit 1 = any mismatch (DO NOT delete).
"""
import argparse
import glob
import json
import os
import sys

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from crop_sim import warp_channel  # noqa: E402  (the single warp convention)


def _read(p):
    return cv2.imread(p, cv2.IMREAD_UNCHANGED)


def check_sample(d, float_tol):
    meta = json.load(open(os.path.join(d, "meta.json")))
    cs = meta.get("crop_sim")
    if not cs or not cs.get("homography_src_to_crop"):
        return None, []
    M = np.asarray(cs["homography_src_to_crop"], dtype=np.float64)
    crop_dir = os.path.join(d, "crop")
    rows = []
    ok = True
    for cp in sorted(glob.glob(os.path.join(crop_dir, "*.png")) +
                     glob.glob(os.path.join(crop_dir, "*.exr"))):
        name = os.path.basename(cp)
        # hand_mask is the shadow-caster's 512x512 TEXTURE, not a render-grid channel — the 053
        # pass warped it spuriously with the 1536-grid homography (meaningless output; never a
        # training channel). Excluded from equivalence; slimming deletes it with the rest.
        if name.startswith("hand_mask"):
            continue
        op = os.path.join(d, name)
        if not os.path.exists(op):
            continue
        orig = _read(op)
        mat = _read(cp)
        if orig is None or mat is None:
            continue
        lazy = warp_channel(orig, M, name)
        if lazy.shape != mat.shape:
            rows.append((name, "SHAPE MISMATCH", False))
            ok = False
            continue
        is_float = np.issubdtype(mat.dtype, np.floating)
        diff = np.abs(lazy.astype(np.float64) - mat.astype(np.float64))
        mx = float(diff.max())
        if is_float:
            passed = mx <= float_tol
        else:
            passed = mx == 0.0
        rows.append((name, mx, passed))
        ok = ok and passed
    return ok, rows


def loader_check(root):
    """Wire check: dataset(crop_view=True) equals manual warp through the same decode chain."""
    sys.path.insert(0, os.path.join(HERE, "foundation"))
    import dataset as D
    ds = D.GlassDelightDataset([root], split="all", augment=False, crop_view=True,
                               work_size=100000)  # no downsample: full-res compare
    for i in range(len(ds)):
        d = ds.samples[i]["dir"]
        meta = json.load(open(os.path.join(d, "meta.json")))
        cs = meta.get("crop_sim")
        if not cs:
            continue
        M = np.asarray(cs["homography_src_to_crop"], dtype=np.float64)
        comp = ds._components(i)
        if comp is None:
            continue
        # manual: loader decode chain with the warp injected exactly as _components does
        T_manual = D._load_gt_T(d, M)
        ph_manual = D._photo_linear(d, "without", M)
        dT = float(np.abs(comp["T"] - T_manual.astype(np.float32)).max())
        dP = float(np.abs(comp["photo_wo"] - ph_manual.astype(np.float32)).max())
        print(f"[loader] {os.path.basename(d)[:44]} maxdiff T={dT:.2e} photo={dP:.2e}")
        return dT == 0.0 and dP == 0.0
    print("[loader] no crop_sim sample found for the wiring check")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--float-tol", type=float, default=2e-3)
    ap.add_argument("--max-samples", type=int, default=None)
    args = ap.parse_args()

    dirs = [d for d in sorted(glob.glob(os.path.join(args.root, "*")))
            if os.path.isdir(os.path.join(d, "crop"))]
    if args.max_samples:
        dirs = dirs[:args.max_samples]
    n_ok = n_fail = n_ch = 0
    worst_float = 0.0
    for d in dirs:
        ok, rows = check_sample(d, args.float_tol)
        if ok is None:
            continue
        n_ch += len(rows)
        for name, mx, passed in rows:
            if isinstance(mx, float) and name.endswith(".exr"):
                worst_float = max(worst_float, mx)
            if not passed:
                print(f"FAIL {os.path.basename(d)}/{name}: maxdiff={mx}")
        if ok:
            n_ok += 1
        else:
            n_fail += 1
    print(f"[verify] {n_ok} samples OK, {n_fail} FAILED, {n_ch} channel files compared; "
          f"worst float-EXR maxdiff={worst_float:.3e} (tol {args.float_tol})")
    wiring_ok = loader_check(args.root)
    print(f"[verify] loader crop_view wiring: {'OK' if wiring_ok else 'FAIL'}")
    sys.exit(0 if (n_fail == 0 and wiring_ok) else 1)


if __name__ == "__main__":
    main()
