#!/usr/bin/env python3
"""Report 048 -- validate the (T, h) -> (T, h, sigma_s) material-target extension.

Two validation levels:
  (A) AUTHORING (this script's default): call the trunk generator's author_glass_arrays
      headless (bpy stubbed -- authoring is pure numpy/scipy, generate_synthetic.py:1028
      "no bpy state touched") for the 12 oracle-045 families, and check the report-043
      decomposition contract EXACTLY:
        - decompose_haze(h, recipe) -> (sigma_s, a_glow)
        - project_h(sigma_s, a_glow) == the emitted h  (OUTPUT_CONTRACT sec 0:
          h = a_glow + (1-a_glow)*sigma_s)
        - a_glow == 0 for every non-opal recipe; nonzero only for the opal family
        - value ranges sane ([0,1], sigma_s clip 0.92, a_glow clip 0.35)
      Produces results/048/sigma_target_board.jpg (per-family T | sigma_s | a_glow | h |
      h_proj) and sigma_target_metrics.json.
  (B) ON-DISK round-trip (--ondisk <gen_data>): re-derive the same identity on the
      generator's rendered+encoded gt_sigma_s/gt_a_glow/gt_h PNGs, i.e. does the
      decomposition survive the Cycles emission-passthrough + sRGB-shaped 16-bit encode.

Usage:
  <venv>/python results/048/verify_sigma_target.py                 # authoring board+metrics
  <venv>/python results/048/verify_sigma_target.py --ondisk results/048/gen_data
"""
import argparse
import json
import os
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.dirname(os.path.dirname(HERE))  # research/delighting
sys.path.insert(0, DELIGHT)

# 12 oracle-045 families (report 045 sec 5 / report 048 brief)
FAMILIES = [
    ("cathedral-green", 6001), ("cathedral-amber", 6002),
    ("streaky-mix", 6001), ("streaky-fine-texture", 6002),
    ("wispy-white", 6001), ("saturated-opalescent", 6001),
    ("ring-mottle", 6001), ("dark-ruby", 6001),
    ("dark-textured", 6002), ("baroque-rolling-wave", 6001),
    ("confetti-shard", 6002), ("fracture-streamer", 6003),
]
OPAL = {"wispy-white", "saturated-opalescent"}
SIZE = 256
TILE = 150


def load_generator():
    """Import generate_synthetic with bpy stubbed so the pure-numpy authoring runs
    without Blender."""
    sys.modules.setdefault("bpy", types.ModuleType("bpy"))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gensyn048", os.path.join(DELIGHT, "generate_synthetic.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _jsonable(o):
    import numpy as _np
    if isinstance(o, (_np.bool_,)):
        return bool(o)
    if isinstance(o, (_np.integer,)):
        return int(o)
    if isinstance(o, (_np.floating,)):
        return float(o)
    raise TypeError(str(type(o)))


def stats(a):
    a = np.asarray(a, np.float64)
    return {"min": float(a.min()), "max": float(a.max()),
            "mean": float(a.mean()), "p99": float(np.percentile(a, 99))}


def to_gray_tile(a, label, val=None):
    import cv2
    a = np.clip(np.asarray(a, np.float32), 0, 1)
    if a.ndim == 3:
        a = a[..., 0]
    img = (a * 255).astype(np.uint8)
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    img = cv2.resize(img, (TILE, TILE), interpolation=cv2.INTER_AREA)
    cv2.putText(img, label, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (60, 220, 60), 1, cv2.LINE_AA)
    if val is not None:
        cv2.putText(img, val, (4, TILE - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (80, 200, 255), 1, cv2.LINE_AA)
    return img


def to_color_tile(rgb, label):
    import cv2
    rgb = np.clip(np.asarray(rgb, np.float32), 0, 1)
    # authored-linear T -> sRGB view for display
    srgb = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(np.clip(rgb, 1e-6, 1), 1 / 2.4) - 0.055)
    img = (np.clip(srgb, 0, 1) * 255).astype(np.uint8)[..., ::-1]  # RGB->BGR
    img = cv2.resize(np.ascontiguousarray(img), (TILE, TILE), interpolation=cv2.INTER_AREA)
    cv2.putText(img, label, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (60, 220, 60), 1, cv2.LINE_AA)
    return img


def authoring_validation(out_dir):
    import cv2
    gen = load_generator()
    rows, metrics, all_ok = [], [], True
    for recipe, seed in FAMILIES:
        T, h, md, mw, mi, ht, nm, bd, sigma_s, a_glow = gen.author_glass_arrays(recipe, size=SIZE, seed=seed)
        h_proj = gen.project_h(sigma_s, a_glow)
        res = np.abs(h_proj - h)
        is_opal = recipe in OPAL
        aglow_max = float(a_glow.max())
        rec = {
            "recipe": recipe, "seed": seed, "is_opal": is_opal,
            "identity_residual_max": float(res.max()),
            "identity_residual_mean": float(res.mean()),
            "sigma_s": stats(sigma_s), "a_glow": stats(a_glow),
            "h": stats(h), "T": stats(T),
        }
        # contract checks
        checks = {
            "identity_ok": float(res.max()) < 1e-5,
            "aglow_zero_iff_nonopal": (aglow_max == 0.0) != is_opal or (is_opal and aglow_max > 0),
            "ranges_ok": (0 <= sigma_s.min() and sigma_s.max() <= 1.0
                          and 0 <= a_glow.min() and a_glow.max() <= 0.3501
                          and 0 <= h.min() and h.max() <= 1.0),
        }
        # aglow rule: exactly zero for non-opal, >0 for opal
        checks["aglow_rule"] = (aglow_max == 0.0) if not is_opal else (aglow_max > 0.0)
        rec["checks"] = checks
        ok = checks["identity_ok"] and checks["ranges_ok"] and checks["aglow_rule"]
        rec["all_ok"] = ok
        all_ok = all_ok and ok
        metrics.append(rec)

        # board row
        lab = f"{recipe}:{seed}"
        left = np.full((TILE, 168, 3), 24, np.uint8)
        cv2.putText(left, recipe[:20], (6, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (230, 230, 230), 1, cv2.LINE_AA)
        cv2.putText(left, f"seed {seed}", (6, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (150, 150, 150), 1, cv2.LINE_AA)
        cv2.putText(left, ("OPAL" if is_opal else "non-opal"), (6, 118),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, ((90, 180, 255) if is_opal else (120, 120, 120)), 1, cv2.LINE_AA)
        tiles = [
            left,
            to_color_tile(T, "T"),
            to_gray_tile(sigma_s, "sigma_s", f"max {sigma_s.max():.2f}"),
            to_gray_tile(a_glow, "a_glow", f"max {aglow_max:.3f}"),
            to_gray_tile(h, "h", f"max {h.max():.2f}"),
            to_gray_tile(h_proj, "h_proj", f"|res|<{res.max():.0e}"),
        ]
        rows.append(np.concatenate(tiles, axis=1))

    # header
    import cv2
    header = np.full((30, rows[0].shape[1], 3), 12, np.uint8)
    cv2.putText(header, "Report 048  material target (T, h, sigma_s)   columns: family | T | sigma_s | a_glow | h | h_proj=a_glow+(1-a_glow)*sigma_s",
                (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1, cv2.LINE_AA)
    board = np.concatenate([header] + rows, axis=0)
    os.makedirs(out_dir, exist_ok=True)
    board_path = os.path.join(out_dir, "sigma_target_board.jpg")
    cv2.imwrite(board_path, board, [cv2.IMWRITE_JPEG_QUALITY, 90])

    summary = {
        "level": "authoring",
        "n_families": len(FAMILIES),
        "all_ok": all_ok,
        "max_identity_residual_over_families": max(m["identity_residual_max"] for m in metrics),
        "opal_families_with_nonzero_aglow": [m["recipe"] for m in metrics if m["is_opal"] and m["a_glow"]["max"] > 0],
        "nonopal_families_with_zero_aglow": sum(1 for m in metrics if not m["is_opal"] and m["a_glow"]["max"] == 0),
        "per_family": metrics,
    }
    json.dump(summary, open(os.path.join(out_dir, "sigma_target_metrics.json"), "w"), indent=2, default=_jsonable)
    print(f"[authoring] families={len(FAMILIES)} all_ok={all_ok} "
          f"max_identity_residual={summary['max_identity_residual_over_families']:.2e}")
    print(f"[authoring] opal w/ nonzero a_glow: {summary['opal_families_with_nonzero_aglow']}")
    print(f"[authoring] non-opal w/ zero a_glow: {summary['nonopal_families_with_zero_aglow']}/10")
    print(f"[authoring] wrote {board_path}")
    for m in metrics:
        print(f"   {m['recipe']:24s} seed{m['seed']}  sigma_s[{m['sigma_s']['min']:.2f},{m['sigma_s']['max']:.2f}] "
              f"a_glow_max={m['a_glow']['max']:.3f}  h[{m['h']['min']:.2f},{m['h']['max']:.2f}]  "
              f"res={m['identity_residual_max']:.1e}  {'OK' if m['all_ok'] else 'FAIL'}")
    return all_ok


def _load_gt_png(path):
    """16-bit gt_*.png -> authored-linear, matching foundation/dataset._load_gt_h
    (srgb_to_lin decode)."""
    import cv2
    from extract import srgb_to_lin
    raw = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if raw is None:
        return None
    raw = raw.astype(np.float32) / 65535.0
    if raw.ndim == 3:
        raw = raw[..., 0]
    return srgb_to_lin(raw)


def ondisk_validation(gen_data, out_dir):
    """Level B: verify h == a_glow + (1-a_glow)*sigma_s on the RENDERED+ENCODED gt maps."""
    import glob
    res = []
    for d in sorted(glob.glob(os.path.join(gen_data, "*"))):
        if not os.path.isdir(d):
            continue
        pj = os.path.join(d, "meta.json")
        meta = json.load(open(pj)) if os.path.exists(pj) else {}
        ss = _load_gt_png(os.path.join(d, "gt_sigma_s.png"))
        ag = _load_gt_png(os.path.join(d, "gt_a_glow.png"))
        hh = _load_gt_png(os.path.join(d, "gt_h.png"))
        if ss is None or ag is None or hh is None:
            print(f"[ondisk] {os.path.basename(d)}: MISSING gt maps "
                  f"(sigma_s={ss is not None} a_glow={ag is not None} h={hh is not None})")
            continue
        proj = np.clip(ag + (1 - ag) * ss, 0, 1)
        r = np.abs(proj - hh)
        rec = {"dir": os.path.basename(d), "recipe": meta.get("class_label", "?"),
               "residual_max": float(r.max()), "residual_mean": float(r.mean()),
               "sigma_s_max": float(ss.max()), "a_glow_max": float(ag.max()), "h_max": float(hh.max())}
        res.append(rec)
        print(f"[ondisk] {rec['recipe']:22s} residual mean={rec['residual_mean']:.2e} "
              f"max={rec['residual_max']:.2e}  sigma_s_max={rec['sigma_s_max']:.2f} a_glow_max={rec['a_glow_max']:.3f}")
    if res:
        summary = {"level": "ondisk", "n": len(res),
                   "residual_mean_over_samples": float(np.mean([x["residual_mean"] for x in res])),
                   "residual_max_over_samples": float(np.max([x["residual_max"] for x in res])),
                   "per_sample": res}
        json.dump(summary, open(os.path.join(out_dir, "sigma_target_ondisk_metrics.json"), "w"), indent=2, default=_jsonable)
        print(f"[ondisk] n={len(res)} mean_residual={summary['residual_mean_over_samples']:.2e} "
              f"max_residual={summary['residual_max_over_samples']:.2e}")
    else:
        print("[ondisk] no samples found")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ondisk", default=None, help="path to gen_data with rendered gt_*.png")
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    if args.ondisk:
        ondisk_validation(args.ondisk, args.out)
    else:
        ok = authoring_validation(args.out)
        sys.exit(0 if ok else 1)
