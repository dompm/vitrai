#!/usr/bin/env python3
"""Task C (report 021): SYNTHETIC-RECIPE GROUNDING -- quantify the real
corpus's appearance distribution (per metadata class: hue/chroma/lightness
in CIE LCh, plus a high-frequency texture-energy statistic) and compare
against the 8 authored synthetic recipes in generate_synthetic.py (5
original + 3 dark-family from report 017).

Two independent measurements, same color-space math, so they're comparable:

  (a) REAL: for each image in the clean, backlit-verified subset of
      clean_manifest.json (confidence != 'low' -- drops the Textured/Baroque
      grab-bag, whose Oceanside iridescent-finish subset report 015 flagged
      as front-lit-leaning -- AND Youghiogheny dark-opaque, 015's specific
      front-lit tell), load the photo, take a center crop (avoids
      light-table edge/background pixels), convert sRGB -> CIE Lab -> LCh,
      and compute a chroma-weighted circular-mean hue, median L, median C,
      and a radial-FFT high-frequency energy fraction on the luma channel.

  (b) SYNTHETIC: re-derive each recipe's authored `T` array with the exact
      same base_color/noise formulas as generate_synthetic.py's
      create_glass_textures() (duplicated here in pure numpy/scipy -- the
      original can't be imported directly, it starts with `import bpy`,
      which needs a Blender interpreter this environment doesn't have).
      T there is linear-light (saved as EXR, 'Linear Rec.709' colorspace);
      apply the standard sRGB OETF before the same Lab/LCh conversion so
      it's being compared in the same encoding a real photo lives in.

CAVEAT (stated plainly, not hidden): a real photo is L(illumination) * T *
(shading from h/normal), so its measured chroma/lightness spread is
inflated a bit by backlight falloff and surface-relief shading that a flat
authored T array doesn't have. This is a coverage-map / gap-finding tool,
not a pixel-exact radiometric match -- adequate for "which regions of
appearance space are under-represented," which is what this task needs.

Usage: python3 appearance_stats.py [--out results/corpus/appearance_stats.json]
"""
import argparse
import collections
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import zoom

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CATALOG_DIR = os.path.join(REPO_ROOT, "frontend", "public", "assets", "catalog_images")
RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")
CLEAN_MANIFEST = os.path.join(RESULTS_DIR, "clean_manifest.json")

# ---------------------------------------------------------------------------
# color math: sRGB [0,1] <-> linear <-> CIE XYZ (D65) <-> CIE Lab -> LCh
# ---------------------------------------------------------------------------
_SRGB2XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
])
_WHITE = np.array([0.9504559, 1.0000000, 1.0888328])  # D65


def srgb_to_linear(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def srgb_to_lab(rgb01):
    """rgb01: (...,3) sRGB in [0,1]. Returns (...,3) Lab."""
    lin = srgb_to_linear(rgb01)
    xyz = lin @ _SRGB2XYZ.T
    xyz = xyz / _WHITE
    delta = 6 / 29
    f = np.where(xyz > delta ** 3, np.cbrt(xyz), xyz / (3 * delta ** 2) + 4 / 29)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def lab_to_lch(lab):
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    C = np.sqrt(a ** 2 + b ** 2)
    h = np.degrees(np.arctan2(b, a)) % 360
    return L, C, h


def chroma_weighted_circular_mean_hue(h_deg, weights):
    rad = np.radians(h_deg)
    s = np.sum(weights * np.sin(rad))
    c = np.sum(weights * np.cos(rad))
    return float(np.degrees(np.arctan2(s, c)) % 360)


def high_freq_energy_fraction(luma01):
    """Radial-FFT high-frequency energy fraction on a square luma array.
    outer half of the radial spectrum (by Nyquist-normalized radius) over
    total spectral energy, DC excluded. Scale-invariant texture-coarseness
    proxy: near 0 for flat/smooth color, higher for fine mottling/streaking."""
    h, w = luma01.shape
    n = min(h, w)
    a = luma01[:n, :n]
    a = a - a.mean()
    F = np.fft.fftshift(np.fft.fft2(a))
    P = np.abs(F) ** 2
    cy, cx = n // 2, n // 2
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2) / (n / 2)  # normalized 0..~1.4
    total = P.sum() - P[cy, cx]  # exclude DC
    if total <= 0:
        return 0.0
    high = P[(r > 0.5) & (r <= 1.0)].sum()
    return float(high / total)


def load_center_crop_srgb01(path, out_size=200, crop_frac=0.6):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    cw, ch = int(w * crop_frac), int(h * crop_frac)
    left, top = (w - cw) // 2, (h - ch) // 2
    im = im.crop((left, top, left + cw, top + ch)).resize((out_size, out_size), Image.LANCZOS)
    return np.asarray(im).astype(np.float64) / 255.0


LUM = np.array([0.2126, 0.7152, 0.0722])


def image_appearance_stats(path):
    rgb = load_center_crop_srgb01(path)
    lab = srgb_to_lab(rgb)
    L, C, h = lab_to_lch(lab)
    luma = rgb @ LUM
    return {
        "L_median": float(np.median(L)),
        "C_median": float(np.median(C)),
        "hue_deg": chroma_weighted_circular_mean_hue(h.ravel(), C.ravel()),
        "C_p90": float(np.percentile(C, 90)),
        "hf_energy_frac": high_freq_energy_fraction(luma),
    }


# ---------------------------------------------------------------------------
# Synthetic recipes -- re-derived by importing generate_synthetic.py's REAL
# author_glass_arrays (pure numpy/scipy; bpy stubbed) rather than duplicating
# its formulas here (report 032: the duplicate drifted every recipe change).
# seed=42 matches the script's own default.
# ---------------------------------------------------------------------------
def _load_generator():
    """Report 032: SINGLE SOURCE OF TRUTH. Earlier revisions duplicated
    generate_synthetic.py's generate_noise + every recipe's base_color/noise
    formulas here in pure numpy (the file's docstring notes the original
    "can't be imported directly, it starts with `import bpy`"). That copy drifted
    out of sync every time a recipe changed (the WP-A flow-advected streaks,
    micro-events, and Beer-Lambert coupling in report 032 would each need a
    manual re-copy). Instead we stub `bpy` (author_glass_arrays touches no
    Blender state -- it is pure numpy/scipy) and import the REAL authoring
    function, so this grounding harness re-derives byte-identical authored T to
    what the renderer bakes into gt_T. No duplication, no drift."""
    import sys, types
    if "bpy" not in sys.modules:
        sys.modules["bpy"] = types.ModuleType("bpy")
    _gs_dir = os.path.abspath(os.path.join(HERE, ".."))  # research/delighting
    if _gs_dir not in sys.path:
        sys.path.insert(0, _gs_dir)
    import generate_synthetic as _gs
    return _gs


_GS = _load_generator()


def recipe_T(recipe, size=512, seed=42):
    """Returns the recipe's authored linear-light T array, (size,size,3) --
    the exact array generate_synthetic.author_glass_arrays produces (includes
    the report-032 flow-advected streaks, micro-events, and T<->height
    coupling), so appearance grounding sees the SHIPPED recipe, not a copy."""
    T, _h, _mark, _mark_white, _mark_index, _height, _normal, _bd, _sigma_s, _a_glow = _GS.author_glass_arrays(recipe, size=size, seed=seed)
    return T.astype(np.float64)


RECIPES = ["cathedral-green", "cathedral-amber", "dark-opaque", "dark-deep",
           "dark-ruby", "dark-slate", "streaky-mix", "wispy-white",
           # Report 022: five gap recipes (021 §5)
           "cathedral-blue", "cathedral-red", "saturated-opalescent",
           "streaky-fine-texture", "dark-textured",
           # Report 037 item C: four new taxa (031 §2/4/5)
           "baroque-rolling-wave", "fracture-streamer", "confetti-shard", "ring-mottle"]
# rough family->extractor-class mapping, for placing recipes on the same
# coverage map as the real per-class distributions
RECIPE_CLASS = {
    "cathedral-green": "cathedral-clear", "cathedral-amber": "cathedral-clear",
    "dark-opaque": "dark-opaque", "dark-deep": "dark-opaque",
    "dark-ruby": "dark-opaque", "dark-slate": "dark-opaque",
    "streaky-mix": "wispy", "wispy-white": "wispy",
    # Report 022: five gap recipes, class mapping per the report brief.
    "cathedral-blue": "cathedral-clear", "cathedral-red": "cathedral-clear",
    "saturated-opalescent": "opalescent",
    "streaky-fine-texture": "wispy", "dark-textured": "dark-opaque",
    # Report 037 item C: four new taxa, same mapping rationale as
    # eval_synthetic.py's CLASS_MAP (kept in sync -- see that file's comment).
    "baroque-rolling-wave": "cathedral-clear", "fracture-streamer": "wispy",
    "confetti-shard": "wispy", "ring-mottle": "dark-opaque",
}


def recipe_appearance_stats(recipe, size=512, seed=42):
    T_lin = recipe_T(recipe, size, seed)
    rgb = linear_to_srgb(T_lin)
    lab = srgb_to_lab(rgb)
    L, C, h = lab_to_lch(lab)
    luma = rgb @ LUM
    return {
        "L_median": float(np.median(L)), "C_median": float(np.median(C)),
        "hue_deg": chroma_weighted_circular_mean_hue(h.ravel(), C.ravel()),
        "C_p90": float(np.percentile(C, 90)),
        "hf_energy_frac": high_freq_energy_fraction(luma),
        "extractor_class_family": RECIPE_CLASS[recipe],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(RESULTS_DIR, "appearance_stats.json"))
    ap.add_argument("--max-per-class", type=int, default=250,
                     help="cap images per extractor class for runtime (random subsample)")
    args = ap.parse_args()

    clean = json.load(open(CLEAN_MANIFEST))["images"]
    backlit_verified = [im for im in clean if im["confidence"] != "low"
                        and not (im["manufacturer"].lower() == "youghiogheny"
                                 and im["extractor_class"] == "dark-opaque")]
    print(f"backlit-verified subset for appearance stats: {len(backlit_verified)} / {len(clean)} clean images "
          f"(excludes low-confidence Textured/Baroque tier + Youghiogheny dark-opaque)")

    import random
    rng = random.Random(11)
    by_class = collections.defaultdict(list)
    for im in backlit_verified:
        by_class[im["extractor_class"]].append(im)
    for cls in by_class:
        rng.shuffle(by_class[cls])
        by_class[cls] = by_class[cls][:args.max_per_class]

    real_per_image = {}
    real_by_class = collections.defaultdict(list)
    for cls, ims in by_class.items():
        for im in ims:
            path = os.path.join(CATALOG_DIR, im["file"])
            try:
                s = image_appearance_stats(path)
            except Exception as e:
                print(f"  FAILED {im['file']}: {e}")
                continue
            s["file"] = im["file"]
            s["manufacturer"] = im["manufacturer"]
            real_per_image[im["file"]] = s
            real_by_class[cls].append(s)
        print(f"  class={cls:16s} n={len(real_by_class[cls]):4d}")

    def summarize(rows, key):
        vals = np.array([r[key] for r in rows])
        return {"mean": float(vals.mean()), "std": float(vals.std()),
                "p5": float(np.percentile(vals, 5)), "p50": float(np.percentile(vals, 50)),
                "p95": float(np.percentile(vals, 95))}

    real_class_summary = {}
    for cls, rows in real_by_class.items():
        hues = np.array([r["hue_deg"] for r in rows])
        chromas = np.array([r["C_median"] for r in rows])
        real_class_summary[cls] = {
            "n": len(rows),
            "L_median": summarize(rows, "L_median"),
            "C_median": summarize(rows, "C_median"),
            "hue_circular_mean_deg": chroma_weighted_circular_mean_hue(hues, chromas),
            "hue_deg_p5_p95": [float(np.percentile(hues, 5)), float(np.percentile(hues, 95))],
            "hf_energy_frac": summarize(rows, "hf_energy_frac"),
        }

    print("\n=== REAL per-class appearance summary ===")
    for cls, s in real_class_summary.items():
        print(f"  {cls:16s} n={s['n']:4d} L={s['L_median']['p50']:.1f} [{s['L_median']['p5']:.1f}-{s['L_median']['p95']:.1f}] "
              f"C={s['C_median']['p50']:.1f} [{s['C_median']['p5']:.1f}-{s['C_median']['p95']:.1f}] "
              f"hue~{s['hue_circular_mean_deg']:.0f}deg [{s['hue_deg_p5_p95'][0]:.0f}-{s['hue_deg_p5_p95'][1]:.0f}] "
              f"hf={s['hf_energy_frac']['p50']:.4f} [{s['hf_energy_frac']['p5']:.4f}-{s['hf_energy_frac']['p95']:.4f}]")

    print("\n=== SYNTHETIC recipe appearance ===")
    recipe_summary = {}
    for r in RECIPES:
        s = recipe_appearance_stats(r)
        recipe_summary[r] = s
        print(f"  {r:16s} class~{s['extractor_class_family']:16s} L={s['L_median']:.1f} C={s['C_median']:.1f} "
              f"hue={s['hue_deg']:.0f}deg hf={s['hf_energy_frac']:.4f}")

    out = {
        "note": "L*a*b* (D65) computed from sRGB pixels; hue is a chroma-weighted circular "
                "mean in degrees; hf_energy_frac is the outer-half-radius fraction of a "
                "radial FFT power spectrum on luma (DC excluded). Real stats: center-crop "
                "of backlit-verified clean-manifest images (confidence != low, Youghiogheny "
                "dark-opaque excluded). Synthetic stats: authored linear T arrays from "
                "generate_synthetic.py's create_glass_textures(), sRGB-encoded, same math.",
        "n_backlit_verified": len(backlit_verified),
        "real_per_class": real_class_summary,
        "real_per_image": real_per_image,
        "synthetic_recipes": recipe_summary,
    }
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
