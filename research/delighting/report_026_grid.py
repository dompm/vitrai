#!/usr/bin/env python3
"""Report 026: four-condition grid across the standing instruments.

Cross-track synthesis of the intern track's report 019 (`luma_quotient_prior.py`)
into the main pipeline's evaluation frame. Four conditions, scored identically
wherever an instrument permits:

  raw             the untouched linear photo (or synthetic ground-truth photo).
  quotient_alone  report 019's deterministic log-luminance quotient
                  (`out = in * exp(-alpha*(low - median(low)))`, alpha=1.0),
                  applied DIRECTLY to the raw photo. No material model: no
                  chroma separation beyond what falls out of dividing by a
                  luminance-only field, no absolute anchor, no haze estimate.
                  Reuses extract.py's own `luminance_envelope_quotient` (the
                  same function report 026's --illum quotient mode calls) so
                  quotient_alone and hybrid are provably the same removal,
                  integrated at two different depths.
  classical       extract.py's shipped extractor, --illum classical (DEFAULT,
                  post-023/025), T*(h+(1-h)*1) at a plain B=1 backdrop.
  hybrid          extract.py --illum quotient: the SAME classical pipeline
                  (chroma fit, marks, haze, absolute anchor) with ONLY the
                  smooth illumination envelope swapped for the quotient.

Four instruments (task brief 026):
  1. real-suncatcher position sensitivity (report 013's harness; dE + lum CV
     + hue std, report 019's own metric).
  2. synthetic per-pixel GT accuracy (T_mae / h_mae), render_022 (26 samples,
     13 recipes) + render_023_holdout (seeds 800-812, held out).
  3. preview-invariance uniform-target (relight fidelity) -- quotient_alone
     gets the SAME single-scalar exposure-match hack already given to the
     raw-copy baseline (it has no absolute anchor either); documented, not
     hidden.
  4. cross-lighting invariance per-sheet (same authored glass, N lightings).

Library default-path check: verified separately (extract.py benchmark/library
--no-vlm, byte-identical h_mean/T_mean_rgb to report 025's shipped values,
since --illum defaults to 'classical' everywhere and quotient_alone is not on
extract.py's default code path at all).

Usage:
  report_026_grid.py --render22 DIR --render23holdout DIR --out results/quotient_synthesis_026
"""
import argparse
import glob
import itertools
import json
import os
import sys

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract as ex  # noqa: E402
import suncatcher_bench as sb  # noqa: E402
import sheet_texture_prior as prior_exp  # noqa: E402
import eval_synthetic as esyn  # noqa: E402
import eval_preview_invariance as epi  # noqa: E402

CONDS = ["raw", "quotient_alone", "classical", "hybrid"]
COND_LABEL = {
    "raw": "raw",
    "quotient_alone": "quotient-alone (a=1.0)",
    "classical": "current T,h (classical)",
    "hybrid": "hybrid (quotient illum)",
}


def quotient_alone_lin(lin, alpha=1.0):
    """report 019's removal, applied directly to a raw linear photo -- no
    material model. Reuses extract.py's own quotient-envelope helper (the
    same one --illum quotient calls inside estimate_illumination), so this
    is provably the identical smooth-field removal as the hybrid's, just not
    wired through chroma/haze/marks/anchor."""
    Y = ex.lum(lin)
    env = ex.luminance_envelope_quotient(Y, alpha=alpha)
    return lin / env[..., None]


def material_maps(lin, glass_class, cond, mark_region="none"):
    """Return (material_at_B1, T_or_None, h_or_None) for one condition."""
    if cond == "raw":
        return lin, None, None
    if cond == "quotient_alone":
        return np.clip(quotient_alone_lin(lin), 0, None), None, None
    illum = "classical" if cond == "classical" else "quotient"
    m = ex.extract_maps(lin, glass_class, mark_region=mark_region, illum=illum)
    T, h = m["T"], m["h"]
    relit = T * (h[..., None] + (1 - h[..., None]) * 1.0)
    return relit, T, h


# ============================================================ instrument 1
def instrument1_suncatcher(out_dir):
    sheets = {}
    for name, path in (("green", sb.GREEN), ("orange", sb.ORANGE)):
        lin = ex.load_linear(path, None, sb.SHEET_SIZE)
        rgb01 = ex.lin_to_srgb(lin)
        interior = sb.detect_interior(rgb01, name)
        entry = {"interior": interior}
        for cond in CONDS:
            mat, _, _ = material_maps(lin, sb.GLASS_CLASS, cond)
            entry[cond] = mat
        sheets[name] = entry

    polys = sb.parse_gt_polygons(sb.TUT_TYPES)
    cens = {n: sb.centroid(p) for n, p in polys.items()}
    by_sheet, scales, place = prior_exp.setup_geometry(polys, sheets)

    position = {}
    for n in polys:
        s = prior_exp.ASSIGN[n]
        centers = sb.grid_centers(sb.valid_center_range(polys[n], sheets[s]["interior"], scales[s]), 3, 3)
        entry = {"label": prior_exp.LABELS[n], "sheet": s}
        for cond in CONDS:
            means = [sb.piece_mean_lin(sheets[s][cond], polys[n], cens[n], c, scales[s])[0] for c in centers]
            entry[cond] = sb.dispersion(means)
        position[n] = entry

    agg = {
        cond: {
            "mean_dE": float(np.mean([position[n][cond]["mean_dE_to_centroid"] for n in position])),
            "lum_cv": float(np.mean([position[n][cond]["lum_cv"] for n in position])),
            "hue_std_deg": float(np.mean([position[n][cond]["hue_std_deg"] for n in position])),
        }
        for cond in CONDS
    }

    print("==== INSTRUMENT 1: real suncatcher position sensitivity ====")
    for cond in CONDS:
        r = agg[cond]
        print(f"  {COND_LABEL[cond]:26s}: dE={r['mean_dE']:.2f} lumCV={r['lum_cv']:.3f} hue={r['hue_std_deg']:.1f}")

    with open(os.path.join(out_dir, "instrument1_suncatcher.json"), "w") as f:
        json.dump({"aggregate": agg, "per_piece": position}, f, indent=2)
    return agg


# ============================================================ instrument 2
def instrument2_synthetic(data_dirs, size, out_dir):
    samples = []
    for d in data_dirs:
        samples.extend(sorted(glob.glob(os.path.join(d, "*"))))
    rows = []
    for s in samples:
        if not os.path.isdir(s):
            continue
        meta_p = os.path.join(s, "meta.json")
        if not os.path.exists(meta_p):
            continue
        meta = json.load(open(meta_p))
        label = meta.get("class_label")
        gclass = esyn.CLASS_MAP.get(label)
        if gclass is None:
            continue
        photo = esyn.clean_photo_path(s)
        gtT = esyn.load_gt_T(s)
        gth = esyn.load_gt_h(s)
        if photo is None or gtT is None or gth is None:
            continue
        lin = ex.load_linear(photo, None, size)
        H, W = lin.shape[:2]
        gtT_r = esyn.resize_to(gtT, (H, W))
        gth_r = esyn.resize_to(gth[..., None] if gth.ndim == 2 else gth, (H, W))
        if gth_r.ndim == 3:
            gth_r = gth_r[..., 0]
        mark = esyn.load_gt_mask(s, "gt_mark_mask.png")
        valid = np.ones((H, W), bool)
        if mark is not None:
            valid &= ~(esyn.resize_to(mark, (H, W)) > 0.5)
        vt = valid[..., None] * np.ones((1, 1, 3), bool)

        row = {"sample": os.path.basename(s), "label": label, "glass_class": gclass}
        for cond in CONDS:
            if cond == "raw":
                T_est = lin
            elif cond == "quotient_alone":
                T_est = np.clip(quotient_alone_lin(lin), 0, None)
            else:
                illum = "classical" if cond == "classical" else "quotient"
                m = ex.extract_maps(lin, gclass, mark_region="none", illum=illum)
                T_est = m["T"]

            if cond in ("raw", "quotient_alone"):
                # No absolute anchor exists for these two conditions -- report
                # both the UNSCALED comparison (honest: this is what you get
                # with zero calibration) and a best-fit single global scalar
                # gain against THIS sample's own GT (an oracle-scale upper
                # bound -- discloses the ceiling a perfect calibration step
                # could buy quotient_alone, not something it can produce
                # itself without ground truth at inference time).
                k_oracle = float(np.median(gtT_r[vt]) / max(np.median(T_est[vt]), 1e-6))
                dT_unscaled = np.abs(T_est - gtT_r)
                dT_oracle = np.abs(T_est * k_oracle - gtT_r)
                row[f"{cond}_T_mae_unscaled"] = float(dT_unscaled[vt].mean())
                row[f"{cond}_T_mae_oraclescale"] = float(dT_oracle[vt].mean())
                row[f"{cond}_h_mae"] = None  # no haze channel exists
            else:
                dT = np.abs(T_est - gtT_r)
                row[f"{cond}_T_mae"] = float(dT[vt].mean())
                h_est = m["h"]
                dh = np.abs(h_est - gth_r)
                row[f"{cond}_h_mae"] = float(dh[valid].mean())
        rows.append(row)
        print(f"  {row['sample']:38s} [{label}] "
              f"raw_unscaled={row['raw_T_mae_unscaled']:.3f} "
              f"q_alone_oracle={row['quotient_alone_T_mae_oraclescale']:.3f} "
              f"classical={row['classical_T_mae']:.3f} h={row['classical_h_mae']:.3f} "
              f"hybrid={row['hybrid_T_mae']:.3f} h={row['hybrid_h_mae']:.3f}")

    with open(os.path.join(out_dir, "instrument2_rows.json"), "w") as f:
        json.dump(rows, f, indent=2)

    labels = sorted({r["label"] for r in rows})
    per_recipe = {}
    for label in labels:
        sel = [r for r in rows if r["label"] == label]
        per_recipe[label] = {
            "n": len(sel),
            "raw_T_mae_unscaled": float(np.mean([r["raw_T_mae_unscaled"] for r in sel])),
            "quotient_alone_T_mae_unscaled": float(np.mean([r["quotient_alone_T_mae_unscaled"] for r in sel])),
            "quotient_alone_T_mae_oraclescale": float(np.mean([r["quotient_alone_T_mae_oraclescale"] for r in sel])),
            "classical_T_mae": float(np.mean([r["classical_T_mae"] for r in sel])),
            "classical_h_mae": float(np.mean([r["classical_h_mae"] for r in sel])),
            "hybrid_T_mae": float(np.mean([r["hybrid_T_mae"] for r in sel])),
            "hybrid_h_mae": float(np.mean([r["hybrid_h_mae"] for r in sel])),
        }
    with open(os.path.join(out_dir, "instrument2_per_recipe.json"), "w") as f:
        json.dump(per_recipe, f, indent=2)
    print("\n==== INSTRUMENT 2: synthetic per-pixel GT accuracy (per recipe) ====")
    for label, r in sorted(per_recipe.items()):
        print(f"  {label:24s} n={r['n']:2d}  classical T={r['classical_T_mae']:.3f} h={r['classical_h_mae']:.3f}"
              f"  hybrid T={r['hybrid_T_mae']:.3f} h={r['hybrid_h_mae']:.3f}"
              f"  q_alone(oracle-scale) T={r['quotient_alone_T_mae_oraclescale']:.3f}")
    return per_recipe, rows


# ============================================================ instrument 3
def instrument3_preview_invariance(data_dirs, size, out_dir):
    samples = []
    for d in data_dirs:
        samples.extend(sorted(glob.glob(os.path.join(d, "*"))))
    rows = []
    for s in samples:
        if not os.path.isdir(s):
            continue
        # eval_preview_invariance.py has no multi-condition hook; built here,
        # reusing its loaders/renderer/exposure-match helpers directly.
        meta_p = os.path.join(s, "meta.json")
        if not os.path.exists(meta_p):
            continue
        meta = json.load(open(meta_p))
        label = meta.get("class_label")
        gclass = esyn.CLASS_MAP.get(label)
        if gclass is None:
            continue
        clean_path = epi.clean_photo_path(s)
        gtT = epi.load_gt_T(s)
        gth = epi.load_gt_h(s)
        if clean_path is None or gtT is None or gth is None:
            continue
        lin = ex.load_linear(clean_path, None, size)
        H, W = lin.shape[:2]
        gtT_r = epi.resize_to(gtT, (H, W))
        gth_r = epi.resize_to(gth[..., None] if gth.ndim == 2 else gth, (H, W))
        if gth_r.ndim == 3:
            gth_r = gth_r[..., 0]
        bg = epi.preview_background(H, W)
        target = epi.render_preview(gtT_r, gth_r, bg)
        valid = epi.valid_mask(s, lin, gtT_r, target)

        row = {"sample": os.path.basename(s), "label": label}
        for cond in CONDS:
            if cond == "raw":
                out = epi.exposure_match(lin, target, valid)
            elif cond == "quotient_alone":
                q = np.clip(quotient_alone_lin(lin), 0, None)
                # SAME single-scalar exposure hack raw-copy already gets, per
                # the brief: quotient_alone has no absolute anchor, so without
                # this it would be scored against an arbitrary luminance
                # level. Documented, not hidden -- see report 026 sec 3.
                out = epi.exposure_match(q, target, valid)
            else:
                illum = "classical" if cond == "classical" else "quotient"
                m = ex.extract_maps(lin, gclass, mark_region="none", illum=illum)
                out = epi.render_preview(m["T"], m["h"], bg)
            row[f"{cond}_mae"] = epi.srgb_mae255(out, target, valid)
        rows.append(row)
        print(f"  {row['sample']:38s} [{label}] " + " ".join(f"{c}={row[c+'_mae']:.1f}" for c in CONDS))

    with open(os.path.join(out_dir, "instrument3_rows.json"), "w") as f:
        json.dump(rows, f, indent=2)
    labels = sorted({r["label"] for r in rows})
    per_recipe = {
        label: {c: float(np.mean([r[f"{c}_mae"] for r in rows if r["label"] == label])) for c in CONDS}
        for label in labels
    }
    with open(os.path.join(out_dir, "instrument3_per_recipe.json"), "w") as f:
        json.dump(per_recipe, f, indent=2)
    print("\n==== INSTRUMENT 3: preview-invariance uniform-target (sRGB/255 MAE, lower=better) ====")
    for label, r in sorted(per_recipe.items()):
        print(f"  {label:24s} " + " ".join(f"{c}={r[c]:.1f}" for c in CONDS))
    return per_recipe, rows


# ============================================================ instrument 4
def instrument4_cross_lighting(data_dirs, size, out_dir):
    groups = {}
    for d in data_dirs:
        for s in sorted(glob.glob(os.path.join(d, "*"))):
            if not os.path.isdir(s):
                continue
            mp = os.path.join(s, "meta.json")
            if not os.path.exists(mp):
                continue
            meta = json.load(open(mp))
            label = meta.get("class_label")
            seed = meta.get("seed")
            gclass = esyn.CLASS_MAP.get(label)
            if label is None or seed is None or gclass is None:
                continue
            if esyn.clean_photo_path(s) is None or esyn.load_gt_T(s) is None:
                continue
            groups.setdefault((label, seed), []).append(s)

    rows = []
    for (label, seed), samples in sorted(groups.items()):
        if len(samples) < 2:
            continue
        gclass = esyn.CLASS_MAP[label]
        mark = esyn.load_gt_mask(samples[0], "gt_mark_mask.png")
        fields = {cond: [] for cond in CONDS}  # per sample: (field, valid)
        for s in samples:
            lin = ex.load_linear(esyn.clean_photo_path(s), None, size)
            H, W = lin.shape[:2]
            valid = np.ones((H, W), bool)
            if mark is not None:
                valid &= ~(esyn.resize_to(mark, (H, W)) > 0.5)
            for cond in CONDS:
                if cond == "raw":
                    field = lin
                elif cond == "quotient_alone":
                    field = np.clip(quotient_alone_lin(lin), 0, None)
                else:
                    illum = "classical" if cond == "classical" else "quotient"
                    m = ex.extract_maps(lin, gclass, mark_region="none", illum=illum)
                    field = m["T"]
                fields[cond].append((field, valid))

        entry = {"label": label, "seed": seed, "n_lightings": len(samples)}
        for cond in CONDS:
            pair_d = []
            for (Ta, va), (Tb, vb) in itertools.combinations(fields[cond], 2):
                v = va & vb
                vt = v[..., None] * np.ones((1, 1, 3), bool)
                pair_d.append(float(np.abs(Ta - Tb)[vt].mean()))
            entry[f"{cond}_invariance"] = float(np.mean(pair_d)) if pair_d else None
        rows.append(entry)
        print(f"  {label:24s} seed{seed} " + " ".join(f"{c}={entry[c+'_invariance']:.4f}" for c in CONDS))

    with open(os.path.join(out_dir, "instrument4_rows.json"), "w") as f:
        json.dump(rows, f, indent=2)
    labels = sorted({r["label"] for r in rows})
    per_recipe = {
        label: {c: float(np.mean([r[f"{c}_invariance"] for r in rows if r["label"] == label])) for c in CONDS}
        for label in labels
    }
    with open(os.path.join(out_dir, "instrument4_per_recipe.json"), "w") as f:
        json.dump(per_recipe, f, indent=2)
    print("\n==== INSTRUMENT 4: cross-lighting invariance per recipe (pairwise field MAE, lower=better) ====")
    for label, r in sorted(per_recipe.items()):
        print(f"  {label:24s} " + " ".join(f"{c}={r[c]:.4f}" for c in CONDS))
    return per_recipe, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render22", required=True)
    ap.add_argument("--render23holdout", required=True)
    ap.add_argument("--size", type=int, default=700)
    ap.add_argument("--out", default=os.path.join(HERE, "results", "quotient_synthesis_026"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    i1 = instrument1_suncatcher(args.out)
    i2, _ = instrument2_synthetic([args.render22, args.render23holdout], args.size, args.out)
    i3, _ = instrument3_preview_invariance([args.render22, args.render23holdout], args.size, args.out)
    i4, _ = instrument4_cross_lighting([args.render22, args.render23holdout], args.size, args.out)

    with open(os.path.join(args.out, "grid_summary.json"), "w") as f:
        json.dump({
            "instrument1_suncatcher_position_sensitivity": i1,
            "instrument2_synthetic_per_recipe": i2,
            "instrument3_preview_invariance_per_recipe": i3,
            "instrument4_cross_lighting_per_recipe": i4,
        }, f, indent=2)
    print("\nwrote", args.out)


if __name__ == "__main__":
    main()
