"""046 side-view -- does the preview need a THICKNESS map? A physics demonstration
on the existing ground-truth maps (no new Cycles render -- see report 046 sec 6 for
why the current surface-BSDF generator can't render the volumetric case, and why the
answer is nonetheless decidable analytically).

The current material model bakes thickness INTO the head-on transmittance:
`couple_T_to_height` authors gt_T(x) = T_base(x)^thickness(x), thickness(x) =
1 - coupling*(2*height(x) - 1) (gen045_module.py:376-387). So at a tilted view the
absorption path length scales the WHOLE exponent by 1/cos(theta_r):

  correct grazing absorption = T_base^(thickness/cos) = (T_base^thickness)^(1/cos)
                             = gt_T ^ (1/cos(theta_r))          <-- a GLOBAL factor.

Hence the three variants the CTO asked to compare:
  (a) baked-T, view-independent      L = gt_T * B                 (current preview)
  (b) baked-T + global cos path-len  L = gt_T^(1/cos_r) * B       (flat-uniform sheet)
  (c) per-pixel thickness Beer-Lambert  == (b), EXACTLY, by the identity above.
A separate thickness MAP buys nothing over the global cos factor for absorption.

The one genuinely thickness-dependent VIEW effect is geometric, not absorptive:
  (d) slab refraction PARALLAX       B sampled at uv + thickness(x)*tan(theta_r)*dir
      -- thick regions shift the background more than thin ones. This exists only in
      a VOLUMETRIC slab; the current flat surface-BSDF truth has zero parallax, so it
      cannot be rendered here -- it is shown as the illustrative "what a thickness map
      would buy in a 3D/volumetric preview" (-> a future report 047).

Scatter is left OFF here to keep the checker + parallax legible (the thickness question
is about absorption + geometry; haze-scatter, report 046 sec 2, only washes both out
further -- decisive for hazy families, which is itself why parallax matters only for
LOW-haze high-relief glass like cathedral).

Run: .venv/bin/python sideview_046.py --data <oracle45_data> --out ../results/046
"""
import argparse
import json
import os

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np

from browser_render_046 import read_exr, lin_to_srgb, score

IOR = 1.5
# Illustrative volumetric slab for the DIFFERENTIAL parallax panel (d). Only the
# relief-driven VARIATION of thickness matters (a uniform slab just shifts the whole
# background -- a global registration a thickness map is not needed for); this gain
# turns the height relief (std ~0.1) into a several-px background-shift swing, the
# amplitude of a ~cm-relief art-glass slab. Illustrative magnitude, not calibrated --
# the POINT is the relief-following STRUCTURE, which only a height/thickness map can
# produce and which only exists in a volumetric model.
RELIEF_GAIN_PX = 80.0

# per-recipe thickness coupling (gen045_module: cathedral most, opal least). Used
# only to reconstruct thickness(x) for the parallax panel; absorption needs none.
COUPLING = {"cathedral-green": 0.30, "cathedral-amber": 0.30, "baroque-rolling-wave": 0.22,
            "streaky-mix": 0.18, "fracture-streamer": 0.20, "confetti-shard": 0.15,
            "dark-ruby": 0.05, "wispy-white": 0.02}

# rows: relief-textured families + a synthetic FLAT control (cathedral-green maps
# with the height field flattened to constant) -- the honest contrast, since ALL our
# synthetic families actually carry relief (height std ~0.08-0.15), so there is no
# naturally-flat family to use.
PANEL_ROWS = [("cathedral-green", False), ("baroque-rolling-wave", False),
              ("streaky-mix", False), ("cathedral-green", True)]


def load(d):
    T = np.clip(read_exr(os.path.join(d, "gt_T.exr")), 1e-4, 1.0)
    B = read_exr(os.path.join(d, "struct_B.exr"))
    h = read_exr(os.path.join(d, "gt_height.exr"))
    if h.ndim == 3:
        h = h[..., 0]
    return T, B, np.clip(h, 0, 1)


def variants(T, B, height, recipe, theta_deg, flat=False):
    theta = np.radians(theta_deg)
    theta_r = np.arcsin(np.sin(theta) / IOR)
    cos_r = np.cos(theta_r)
    coup = COUPLING.get(recipe, 0.15)
    if flat:
        height = np.full_like(height, float(height.mean()))  # constant-thickness control
    thickness = 1.0 - coup * (2.0 * height - 1.0)     # same convention as authoring

    a = T * B                                         # view-independent baked-T
    b = (T ** (1.0 / cos_r)) * B                      # global cos path-length

    # (c) per-pixel thickness Beer-Lambert via an INDEPENDENT code path: factor the
    # head-on gt_T into (T_base, thickness) using the authoring coupling, then apply
    # Beer-Lambert with the per-pixel path length thickness/cos_r. Algebraically this
    # is (T_base^thickness)^(1/cos) = gt_T^(1/cos) == b; computing it the long way and
    # differencing against b is the numerical proof that a thickness MAP is redundant
    # with T for absorption (the diff comes out at float epsilon, ~5e-8).
    T_base = T ** (1.0 / thickness[..., None])        # recovered intrinsic per-unit tint
    c = (T_base ** (thickness[..., None] / cos_r)) * B

    # (d) volumetric slab DIFFERENTIAL refraction parallax: the relief-driven (mean-
    # subtracted) background shift. The uniform part is a global registration -- what
    # a thickness MAP uniquely buys is this per-pixel VARIATION, which follows the
    # height relief and vanishes for a flat sheet.
    relief = height - float(height.mean())
    off = RELIEF_GAIN_PX * relief * np.tan(theta_r)   # px, mean ~0, follows relief
    H, W = height.shape
    cols, rows = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    Bp = cv2.remap(B, cols.astype(np.float32), (rows + off).astype(np.float32),
                   cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    d = (T ** (1.0 / cos_r)) * Bp
    return {"a": a, "b": b, "c": c, "d": d,
            "theta_r_deg": float(np.degrees(theta_r)), "inv_cos": float(1.0 / cos_r),
            "off_px_std": float(off.std()), "off_px_range": [float(off.min()), float(off.max())]}


def to_u8(lin, size):
    img = (lin_to_srgb(np.clip(lin, 0, 1)) * 255).astype(np.uint8)
    return cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)[..., ::-1].copy()


def diffmap(x, y, size, gain=6.0):
    dd = np.abs(lin_to_srgb(np.clip(x, 0, 1)) - lin_to_srgb(np.clip(y, 0, 1))).mean(-1)
    dm = cv2.applyColorMap((np.clip(dd * gain, 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    return cv2.resize(dm, (size, size), interpolation=cv2.INTER_AREA)


def label(img, text):
    cv2.rectangle(img, (0, 0), (img.shape[1], 18), (0, 0, 0), -1)
    cv2.putText(img, text, (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (255, 255, 255), 1, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--theta", type=float, default=55.0)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    cell = 240
    rows_img, results = [], []
    for recipe, flat in PANEL_ROWS:
        d = os.path.join(args.data, [x for x in os.listdir(args.data)
                                     if x.startswith(recipe + "__")][0])
        T, B, height = load(d)
        v = variants(T, B, height, recipe, args.theta, flat=flat)
        tag = f"{recipe[:16]} FLAT" if flat else recipe[:20]
        headon = T * B
        bc_max = float(np.abs(v["b"] - v["c"]).max())
        ab_mae = score(v["a"], v["b"])[0]      # angle-darkening magnitude (sRGB MAE)
        db_mae = score(v["d"], v["b"])[0]      # differential-parallax (thickness) magnitude
        results.append({"recipe": recipe, "flat_control": flat, "coupling": COUPLING.get(recipe, 0.15),
                        "theta_incidence_deg": args.theta, "theta_refracted_deg": v["theta_r_deg"],
                        "inv_cos_r": v["inv_cos"], "parallax_px_std": v["off_px_std"],
                        "parallax_px_range": v["off_px_range"],
                        "b_vs_c_max_abs": bc_max, "a_vs_b_mae": ab_mae, "d_vs_b_mae": db_mae})
        cells = [
            label(to_u8(headon, cell), f"{tag} head-on T*B"),
            label(to_u8(v["a"], cell), f"grazing {args.theta:.0f}d (a) baked-T"),
            label(to_u8(v["b"], cell), f"(b) T^(1/cos)  x{v['inv_cos']:.2f}"),
            label(to_u8(v["d"], cell), "(d) +diff. slab parallax"),
            label(diffmap(v["b"], v["c"], cell), f"|b-c| x6  max {bc_max:.1e}"),
            label(diffmap(v["d"], v["b"], cell), f"|d-b| x6  MAE {db_mae:.1f}"),
        ]
        rows_img.append(np.concatenate(cells, axis=1))
        print(f"{tag:22s} theta_r={v['theta_r_deg']:.1f} 1/cos={v['inv_cos']:.3f} "
              f"| b==c max {bc_max:.1e} | a-vs-b MAE {ab_mae:.1f} | parallax std {v['off_px_std']:.1f}px d-vs-b MAE {db_mae:.1f}")
    board = np.concatenate(rows_img, axis=0)
    bp = os.path.join(args.out, "sideview_thickness_board.jpg")
    cv2.imwrite(bp, board, [cv2.IMWRITE_JPEG_QUALITY, 88])
    with open(os.path.join(args.out, "sideview_metrics.json"), "w") as fp:
        json.dump({"theta_incidence_deg": args.theta, "relief_gain_px": RELIEF_GAIN_PX,
                   "samples": results}, fp, indent=2)
    print(f"board -> {bp}  {board.shape}")


if __name__ == "__main__":
    main()
