#!/usr/bin/env python3
"""Runner for the Bet-1 probe (report 028): score DSRNet's log-space separation with the
report-014 drag test and emit qualitative panels. See bet1_probe.py for the method.

Synthetic (has gt_T -> drag test + grain floor):
  cathedral-green (the hard transmissive case; the bar to beat is classical 0.140 lum-CV)
  wispy-white     (control: already solved by classical, relit ~ grain floor)
Real (no correspondence -> qualitative panels only):
  the tutorial hammered-cathedral sheet + clean-corpus cathedral swatches.

Outputs results/bet1_probe/{drag_table.json, panel_*.jpg}. Env: XREFLECTION_DIR, DSRNET_CKPT.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assembled_bench as ab   # noqa: E402  (drag_test + io reused verbatim)
import bet1_probe as bp        # noqa: E402
import extract                 # noqa: E402

RUN_SIZE = int(os.environ.get("PROBE_RUN_SIZE", "512"))


def classical_T(A, gclass):
    m = extract.extract_maps(A, gclass, mark_region="none")
    return m["T"], m["L"].reshape(-1, 3).mean(0)


def degeneracy(layer_lin, A):
    """How copy-of-input / how empty is a candidate map? Correlation of luminance with the
    input photo, and the map's own dynamic range (empty => near-constant/near-zero)."""
    a = ab.lum(A).ravel()
    l = ab.lum(layer_lin).ravel()
    corr = float(np.corrcoef(a, l)[0, 1])
    return {"lum_corr_with_input": corr,
            "map_cv": float(l.std() / (l.mean() + 1e-9)),
            "map_median_lin": float(np.median(layer_lin)),
            "map_mean_lin": float(layer_lin.mean())}


def drag_for(A, Tmap, gtT, pj, meta):
    ev1 = meta["lighting"]["IBL_1"]["ev"]
    ev2 = meta["lighting"]["IBL_2_variants"][0]["ev"]
    gEV = 2.0 ** (ev2 - ev1)
    # lum-CV is gain-invariant; use a flat unit illuminant so Lab dE is reported at a
    # consistent level across candidates (documented in the report).
    I_hat = np.array([1.0, 1.0, 1.0])
    return ab.drag_test(A, Tmap, gtT, gEV, I_hat, pj, meta)


def run_synthetic(name, gclass, data_dir, out_dir):
    d = os.path.join(data_dir, name + "__seed42")
    meta = json.load(open(os.path.join(d, "meta.json")))
    pj = meta["projection"]
    A = ab.load_exr(os.path.join(d, "renderA_photo_linear.exr"))
    gtT = ab.load_exr(os.path.join(d, "gt_T.exr"))

    Tc, _ = classical_T(A, gclass)
    logsep = bp.separate_log(A, run_size=RUN_SIZE)
    srgbsep = bp.separate_srgb(A, run_size=RUN_SIZE)

    cands = {
        "raw_photo": A,                       # sanity: drag of the photo itself
        "classical_T": Tc,                    # the bar
        "log_trans": logsep["trans"],         # Bet-1: model transmission layer as de-lit glass
        "log_refl": logsep["refl"],           # Bet-1: model reflection layer as de-lit glass
        "srgb_trans": srgbsep["trans"],       # control (no log): transmission layer
        "srgb_refl": srgbsep["refl"],         # control (no log): reflection layer
    }
    table = {}
    for k, m in cands.items():
        dt = drag_for(A, m, gtT, pj, meta)
        deg = degeneracy(m, A)
        table[k] = {"drag": dt, "degeneracy": deg}
    # grain floor (independent of candidate: dispersion of authored gt_T directly)
    table["_grain_floor"] = drag_for(A, Tc, gtT, pj, meta)["grain_floor"]

    _panel_synth(out_dir, name, A, gtT, Tc, logsep, srgbsep)
    return table


def _srgb8(lin, sz=256):
    a = (np.clip(extract.lin_to_srgb(np.clip(lin, 0, 1)), 0, 1) * 255).astype(np.uint8)
    return cv2.resize(a, (sz, sz), interpolation=cv2.INTER_AREA)


def _norm8(x, sz=256):
    """Show a [0,1] normalized-log layer straight (already display-ready-ish)."""
    a = (np.clip(x, 0, 1) * 255).astype(np.uint8)
    return cv2.resize(a, (sz, sz), interpolation=cv2.INTER_AREA)


def _label(img, text):
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 6 * len(text), 15], fill=(0, 0, 0))
    d.text((3, 2), text, fill=(255, 255, 90))
    return np.asarray(im)


def _panel_synth(out_dir, name, A, gtT, Tc, logsep, srgbsep):
    os.makedirs(out_dir, exist_ok=True)
    row1 = np.concatenate([
        _label(_srgb8(A), "input photo (RENDER A)"),
        _label(_srgb8(logsep["trans"]), "log: transmission layer"),
        _label(_srgb8(logsep["refl"]), "log: reflection layer"),
        _label(_srgb8(gtT), "authored GT (de-lit)"),
        _label(_srgb8(Tc), "classical de-lit T"),
    ], axis=1)
    Image.fromarray(row1).save(os.path.join(out_dir, f"panel_{name}.jpg"), quality=90)


def run_real(path, gclass, tag, out_dir, crop_sq=True):
    """Real image: no ground truth -> qualitative panel only (input | trans | refl)."""
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        print("  MISSING", path)
        return None
    img = img[..., ::-1].astype(np.float64) / 255.0  # BGR8 -> RGB [0,1] sRGB
    if crop_sq:
        h, w = img.shape[:2]
        s = min(h, w)
        img = img[(h - s) // 2:(h - s) // 2 + s, (w - s) // 2:(w - s) // 2 + s]
    img = cv2.resize(img.astype(np.float32), (512, 512), interpolation=cv2.INTER_AREA).astype(np.float64)
    A = extract.srgb_to_lin(img)  # treat the display image as sRGB -> linear photo
    logsep = bp.separate_log(A, run_size=512)
    srgbsep = bp.separate_srgb(A, run_size=512)
    Tc, _ = classical_T(A, gclass)
    row = np.concatenate([
        _label(_srgb8(A), "input (real)"),
        _label(_srgb8(logsep["trans"]), "log: trans layer"),
        _label(_srgb8(logsep["refl"]), "log: refl layer"),
        _label(_srgb8(srgbsep["trans"]), "srgb-ctrl: trans"),
        _label(_srgb8(Tc), "classical de-lit T"),
    ], axis=1)
    os.makedirs(out_dir, exist_ok=True)
    Image.fromarray(row).save(os.path.join(out_dir, f"panel_real_{tag}.jpg"), quality=90)
    return {"trans_deg": degeneracy(logsep["trans"], A),
            "refl_deg": degeneracy(logsep["refl"], A)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="assembled_data")
    ap.add_argument("--out", default="results/bet1_probe")
    ap.add_argument("--reals", nargs="*", default=[])
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    results = {"run_size": RUN_SIZE, "synthetic": {}, "real": {}}
    for name, gclass in [("cathedral-green", "cathedral-clear"), ("wispy-white", "wispy")]:
        if os.path.isdir(os.path.join(args.data, name + "__seed42")):
            print("== synthetic", name, "==")
            results["synthetic"][name] = run_synthetic(name, gclass, args.data, args.out)
    for spec in args.reals:
        path, gclass, tag = spec.split("::")
        print("== real", tag, "==")
        results["real"][tag] = run_real(path, gclass, tag, args.out)
    with open(os.path.join(args.out, "drag_table.json"), "w") as f:
        json.dump(results, f, indent=2)
    print("wrote", os.path.join(args.out, "drag_table.json"))
    # concise console table
    for name, tab in results["synthetic"].items():
        print(f"\n-- {name} (grain floor lum-CV {tab['_grain_floor']['lum_cv']:.4f}) --")
        for k in ["raw_photo", "classical_T", "log_trans", "log_refl", "srgb_trans", "srgb_refl"]:
            dr, dg = tab[k]["drag"], tab[k]["degeneracy"]
            print(f"  {k:14s} lumCV {dr['relit']['lum_cv']:.4f}  dE {dr['relit']['lab_dE']:6.2f}"
                  f"  | corr {dg['lum_corr_with_input']:+.3f}  mapCV {dg['map_cv']:.3f}"
                  f"  med {dg['map_median_lin']:.4f}")


if __name__ == "__main__":
    main()
