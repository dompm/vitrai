#!/usr/bin/env python3
"""Report 053 — CROP-WORKFLOW SIMULATION (post-render pass, run in the venv, NOT Blender).

The external review noted the synthetic sheet is always rendered dead-centre, edge-to-edge,
perfectly fronto-parallel — but a real deployment capture is a phone photo the USER framed and
cropped: a few percent of padding/trim error, a small handheld tilt, a scale/zoom difference,
and (when the app or the user rectifies it) a four-corner perspective correction. A model trained
only on the perfect framing learns to rely on it.

This pass takes a finished sample dir and applies ONE synthetic user-crop homography. Report
053b STORAGE FIX: the original 053 pass materialized a cropped duplicate of EVERY GT channel
into crop/ (~150 MB/sample — tripling the honest ~80 MB/sample render cost and blowing the
disk budget at scale). GT crops are now LAZY: this pass writes ONLY
  (1) the cropped PHOTO sheet(s) (crop/*_shadow_photo.png — small, human-viewable, board fuel),
  (2) the local DETAIL PATCHES (photo + a few GT channels at patch size — small), and
  (3) the exact 3x3 transform + capture_geometry + patch boxes into meta.json.
Any consumer that needs a cropped GT channel warps it on the fly from the ORIGINAL file with the
stored homography (`warp_channel` below; `foundation/dataset.py` does this at load time via
`crop_view=True`). Equivalence of the lazy warp vs the old materialized crops is asserted by
`verify_lazy_crop_053b.py` on data that carries both representations.

Determinism: the transform RNG is keyed on the sample's seed (parsed from meta.json), so the crop
is reproducible and a re-run is idempotent. The `capture_geometry` it stamps into meta.json feeds
the EVAL_PROTOCOL §3b-ext holdout (dataset.HOLDOUT_GEOMETRIES reserves 'perspective_rectified' to
TEST-only), so the crop family is itself a held-out axis.

Interpolation discipline: continuous channels (photo, gt_T, gt_h, gt_sigma_s, gt_height, gt_normal,
gt_B) use INTER_LINEAR; label channels (masks / mark index) use INTER_NEAREST so class ids are not
blended. Multilayer AOVs (gt_veil/gt_index) are single-part-EXR-unreadable by cv2 and are SKIPPED
(documented) — the stored homography lets them be warped later with the OpenEXR reader if needed.

Usage:
  crop_sim.py --root <render_dir>            # crop every sample dir in place (adds crop/ + patches)
  crop_sim.py --sample <one_sample_dir>
Options: --n-patches 3 --patch 320 --perspective-prob 0.35
"""
import argparse
import glob
import json
import os

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np

# channel filename -> interpolation. Continuous = LINEAR; label/index = NEAREST.
NEAREST_KEYS = ("gt_mark_mask", "gt_mark_white", "gt_mark_index")
# multilayer / cv2-unreadable AOVs to skip (documented in the module docstring)
SKIP_KEYS = ("gt_veil", "gt_index", "gt_uv", "gt_depth", "gt_index_B")


def _seed_of(sample_dir):
    mp = os.path.join(sample_dir, "meta.json")
    if os.path.exists(mp):
        try:
            m = json.load(open(mp))
            if "seed" in m:
                return int(m["seed"]), m
        except Exception:
            pass
    base = os.path.basename(sample_dir.rstrip("/"))
    for tok in base.split("__"):
        if tok.startswith("seed"):
            try:
                return int(tok[4:]), None
            except ValueError:
                pass
    return abs(hash(base)) % (2 ** 31), None


def _read(path):
    a = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    return a


def _interp_for(name):
    return cv2.INTER_NEAREST if any(k in name for k in NEAREST_KEYS) else cv2.INTER_LINEAR


def warp_channel(img, M, name="", out_wh=None):
    """THE single source of truth for the crop warp (report 053b): identical conventions for
    the materialized photo crop, the patch GT, the lazy loader (dataset.py crop_view), and the
    equivalence test. LINEAR for continuous channels, NEAREST for label channels (by `name`),
    BORDER_REPLICATE. `M` is meta['crop_sim']['homography_src_to_crop'] (list or ndarray)."""
    M = np.asarray(M, dtype=np.float64)
    H, W = img.shape[:2]
    out_wh = out_wh or (W, H)
    return cv2.warpPerspective(img, M, out_wh, flags=_interp_for(name),
                               borderMode=cv2.BORDER_REPLICATE)


def build_crop_homography(H, W, rng, perspective_prob=0.35):
    """Return (M 3x3, geometry_label, params). M maps SOURCE pixel coords -> CROPPED output
    coords (same HxW canvas). Composes a small scale, tilt, and pad/trim translation, plus an
    optional four-corner perspective rectification."""
    scale = float(rng.uniform(0.92, 1.10))          # <1 pad (border), >1 trim (lose edges)
    tilt = float(rng.uniform(-4.0, 4.0)) * np.pi / 180.0
    tx = float(rng.uniform(-0.05, 0.05)) * W        # framing/pad-trim error (<=5%)
    ty = float(rng.uniform(-0.05, 0.05)) * H
    cx, cy = W / 2.0, H / 2.0
    ca, sa = np.cos(tilt), np.sin(tilt)
    # affine part (about the image centre) then translate
    def xf(x, y):
        xr = ca * (x - cx) - sa * (y - cy)
        yr = sa * (x - cx) + ca * (y - cy)
        return scale * xr + cx + tx, scale * yr + cy + ty
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    dst = np.float32([xf(x, y) for x, y in src])
    geometry = "tilt_scale_crop"
    persp = 0.0
    if rng.random() < perspective_prob:
        # four-corner perspective jitter: an app/user rectification of an off-axis capture
        persp = float(rng.uniform(0.02, 0.06))
        dst = dst + np.float32([[rng.uniform(-persp, persp) * W, rng.uniform(-persp, persp) * H]
                                for _ in range(4)])
        geometry = "perspective_rectified"
    if (abs(scale - 1) < 0.015 and abs(tilt) < 0.5 * np.pi / 180 and
            abs(tx) < 0.01 * W and abs(ty) < 0.01 * H and persp == 0.0):
        geometry = "axis_crop"
    M = cv2.getPerspectiveTransform(src, dst)
    params = {"scale": round(scale, 4), "tilt_deg": round(float(tilt * 180 / np.pi), 3),
              "tx_px": round(tx, 2), "ty_px": round(ty, 2), "perspective": round(persp, 4)}
    return M, geometry, params


def apply_crop_to_sample(sample_dir, n_patches=3, patch=320, perspective_prob=0.35):
    seed, meta = _seed_of(sample_dir)
    rng = np.random.default_rng(seed * 131 + 7)     # deterministic per sample; idempotent

    # reference grid from gt_T (the canonical grid the loader keys on)
    ref = None
    for cand in ("gt_T.png", "without_shadow_photo.png", "with_shadow_photo.png"):
        p = os.path.join(sample_dir, cand)
        if os.path.exists(p):
            ref = _read(p)
            break
    if ref is None:
        return None
    H, W = ref.shape[:2]
    M, geometry, params = build_crop_homography(H, W, rng, perspective_prob)

    out_dir = os.path.join(sample_dir, "crop")
    os.makedirs(out_dir, exist_ok=True)

    # --- 053b: materialize ONLY the cropped photo sheet(s); GT channels stay lazy ---
    photo_names = [c for c in ("without_shadow_photo.png", "with_shadow_photo.png")
                   if os.path.exists(os.path.join(sample_dir, c))]
    warped_paths = []
    photo_crops = {}
    for c in photo_names:
        img = _read(os.path.join(sample_dir, c))
        if img is None:
            continue
        w = warp_channel(img, M, c)
        cv2.imwrite(os.path.join(out_dir, c), w)
        photo_crops[c] = w
        warped_paths.append(c)

    # --- local detail patches (photo + a few small GT crops, warped IN MEMORY only) ---
    patches = []
    if photo_crops:
        ph = min(patch, H, W)
        margin = int(0.06 * min(H, W))               # avoid the crop's replicate-border ring
        gt_patch_names = [c for c in ("gt_T.png", "gt_h.png", "gt_sigma_s.png", "gt_mark_mask.png")
                          if os.path.exists(os.path.join(sample_dir, c))]
        gt_warped = {}
        for c in gt_patch_names:                     # warp once per channel, slice per patch
            img = _read(os.path.join(sample_dir, c))
            if img is not None:
                gt_warped[c] = warp_channel(img, M, c)
        pdir = os.path.join(sample_dir, "patches")
        os.makedirs(pdir, exist_ok=True)
        for i in range(n_patches):
            y0 = int(rng.integers(margin, max(margin + 1, H - ph - margin)))
            x0 = int(rng.integers(margin, max(margin + 1, W - ph - margin)))
            for c, arr in list(photo_crops.items()) + list(gt_warped.items()):
                cv2.imwrite(os.path.join(pdir, f"patch{i:02d}_{c}"), arr[y0:y0 + ph, x0:x0 + ph])
            patches.append({"idx": i, "x0": x0, "y0": y0, "size": ph})

    # --- record transform + geometry into meta.json (registration is now documented) ---
    if meta is None:
        mp = os.path.join(sample_dir, "meta.json")
        meta = json.load(open(mp)) if os.path.exists(mp) else {}
    meta["capture_geometry"] = geometry
    meta["crop_sim"] = {"homography_src_to_crop": M.tolist(), "params": params,
                        "cropped_channels": warped_paths, "patches": patches,
                        "gt_crops": "lazy",
                        "note": "053b: M maps source-render pixel coords -> cropped-sheet "
                                "coords. Only the photo sheet(s) + patches are materialized; "
                                "warp any GT channel on demand with crop_sim.warp_channel "
                                "(LINEAR continuous / NEAREST labels, BORDER_REPLICATE) — "
                                "foundation/dataset.py crop_view=True does this at load time."}
    with open(os.path.join(sample_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    return {"dir": sample_dir, "geometry": geometry, "n_patches": len(patches),
            "n_channels": len(warped_paths)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--root", help="render dir of many sample subdirs")
    g.add_argument("--sample", help="one sample dir")
    ap.add_argument("--n-patches", type=int, default=3)
    ap.add_argument("--patch", type=int, default=320)
    ap.add_argument("--perspective-prob", type=float, default=0.35)
    args = ap.parse_args()

    if args.sample:
        dirs = [args.sample]
    else:
        dirs = [d for d in sorted(glob.glob(os.path.join(args.root, "*")))
                if os.path.isdir(d) and os.path.exists(os.path.join(d, "meta.json"))]
    geoms = {}
    for d in dirs:
        r = apply_crop_to_sample(d, args.n_patches, args.patch, args.perspective_prob)
        if r:
            geoms[r["geometry"]] = geoms.get(r["geometry"], 0) + 1
            print(f"  {os.path.basename(d):46s} {r['geometry']:22s} "
                  f"{r['n_channels']} ch, {r['n_patches']} patches")
    print(f"[crop_sim] {sum(geoms.values())} samples | geometry mix: {geoms}")


if __name__ == "__main__":
    main()
