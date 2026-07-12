#!/usr/bin/env python3
"""Iteration 005: quantitative evaluation of the classical extractor against
synthetic PER-PIXEL GROUND TRUTH.

All prior metrics (reports 001-004) were self-reconstruction proxies, structurally
blind to the L/T gauge (report 003). This harness uses an external synthetic
dataset with authored ground-truth transmittance (gt_T) and haze (gt_h) rendered
through the same camera, so extracted maps can be compared per-pixel on an
ABSOLUTE scale.

Ground-truth conventions (VERIFIED, see report 005 sec 1; UNITS CORRECTED report 025):
  * gt_T.exr  : float32 RGB. Report 017 measured (and report 025 re-confirms) that
                the renderer applies an sRGB-shaped encode between the AUTHORED
                linear texture and everything it writes to disk (gt_T.exr, gt_h.exr/
                png, and even the raw `tex_*.exr` texture dumps -- the encode happens
                at Blender's `Image.save()`, not in the camera/view-transform step;
                see report 025 sec 1). This is "LINEAR" only in the sense of being
                directly comparable to the extractor's own T, which has always been
                fit/anchored (T_ANCHOR, the continuous-anchor constants) against this
                same rendered/encoded gt_T statistic, never against authored arrays --
                so no change needed here, T's calibration was already self-consistent
                in "rendered units" end to end.
  * gt_h.png  : 16-bit uint /65535, but SRGB-ENCODED relative to the authored haze
                value (measured to the 3rd decimal, report 022 sec 6 + report 025 sec
                1: rendered = srgb_encode(authored), e.g. authored 0.09 -> stored
                0.332). Unlike T, the extractor's `estimate_haze` was never calibrated
                against this rendered statistic -- report 021 sec 5 picked AUTHORED
                flat-h targets to match the real corpus's own extractor-h_mean
                statistic (i.e. authored h is meant to equal what a correct extractor
                OUTPUTS, native units). So h's canonical convention is AUTHORED LINEAR,
                and this loader now applies `extract.srgb_to_lin` after the /65535
                normalization to recover it -- directly comparable to extractor h.
                Old reports (up to and including 023) compared extractor h against the
                UNDECODED (rendered/encoded) gt_h; report 025 sec "units" has the
                old->corrected number mapping.
  * gt_mark_mask.png : marking layer (grease pencil). Marked pixels optionally
                excluded from T/h error (extractor inpaints them; they are a
                separate concern).
  * camera-aligned: gt maps share the photo's pixel grid; cross-correlation peaks
                at zero offset, so no registration is needed.

Class-prior mapping (ORACLE: fed from meta.json class_label, isolating extractor
error from classifier error):
  cathedral-green / cathedral-amber -> cathedral-clear
  dark-opaque                       -> dark-opaque
  wispy-white                       -> wispy
  streaky-mix                       -> wispy   (documented judgment: authored h
     floor 0.05 sits below opalescent's 0.55 h-floor and its streaks reach
     near-clear, so wispy -- variable h with clear streaks -- fits the range;
     opalescent would force a high haze floor the data does not have. Report 025:
     restated in authored units -- this was "~0.24" pre-025, the RENDERED/encoded
     floor srgb_encode(0.05); the comparison and conclusion are unchanged, only the
     unit label was wrong.)

Usage
-----
  eval_synthetic.py --data DIR --out DIR [--size 700] [--recipes r1,r2]
                    [--vlm] [--shadow] [--max-rows N]
Re-runnable: pick up whatever samples exist now; a partial batch is fine.
"""
import argparse
import glob
import json
import os
import sys

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract  # noqa: E402

CLASS_MAP = {
    "cathedral-green": "cathedral-clear",
    "cathedral-amber": "cathedral-clear",
    "dark-opaque": "dark-opaque",
    "wispy-white": "wispy",
    "streaky-mix": "wispy",
    # Report 017: dark-family calibration top-up (all oracle-class dark-opaque --
    # same family of dense rolled glass, different absolute darkness/tint).
    "dark-deep": "dark-opaque",
    "dark-ruby": "dark-opaque",
    "dark-slate": "dark-opaque",
    # Report 022: five gap recipes (021 §5), class mapping per that report's
    # brief -- cathedral-blue/red are the same hammered-cathedral family as
    # green/amber; saturated-opalescent is the FIRST opalescent-class
    # recipe; streaky-fine-texture/dark-textured are texture-detail variants
    # of the wispy/dark-opaque families.
    "cathedral-blue": "cathedral-clear",
    "cathedral-red": "cathedral-clear",
    "saturated-opalescent": "opalescent",
    "streaky-fine-texture": "wispy",
    "dark-textured": "dark-opaque",
    # Report 037 item C: four new taxa recipes (031 §2/4/5), class-mapped by
    # structural/relief family -- baroque-rolling-wave shares the cathedral-
    # clear family's transmissive base (its differentiator is relief scale,
    # not oracle class); fracture-streamer/confetti-shard are Voronoi-cell
    # body patterns over a near-clear/white base, closer to wispy's
    # patchy-color-variation family than a flat cathedral read; ring-mottle
    # follows dark-ruby's proven-convincing precedent for this taxon (031
    # §3) -- same oracle class, distinct authored hue.
    "baroque-rolling-wave": "cathedral-clear",
    "fracture-streamer": "wispy",
    "confetti-shard": "wispy",
    "ring-mottle": "dark-opaque",
}


# ------------------------------------------------------------------ io helpers
def load_exr_rgb(path):
    a = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if a is None:
        return None
    if a.ndim == 3:
        a = a[..., ::-1]  # BGR -> RGB
    return a.astype(np.float64)


def load_gt_T(sample):
    p = os.path.join(sample, "gt_T.exr")
    if os.path.exists(p):
        return load_exr_rgb(p)
    p = os.path.join(sample, "gt_T.png")  # fallback: raw-linear 8-bit
    if os.path.exists(p):
        return np.asarray(Image.open(p).convert("RGB")).astype(np.float64) / 255.0
    return None


def load_gt_h(sample):
    """Report 025: gt_h.png is sRGB-shaped-ENCODED relative to the authored haze
    value (see the module docstring's units note); decode it so the returned array
    is in the same authored-linear units as the extractor's own h."""
    p = os.path.join(sample, "gt_h.png")
    if os.path.exists(p):
        raw = np.asarray(Image.open(p)).astype(np.float64) / 65535.0
        return extract.srgb_to_lin(raw)
    return None


def load_gt_mask(sample, name):
    p = os.path.join(sample, name)
    if not os.path.exists(p):
        return None
    a = np.asarray(Image.open(p)).astype(np.float64)
    if a.ndim == 3:
        a = a.mean(-1)
    return a / (65535.0 if a.max() > 255 else 255.0)


def clean_photo_path(sample):
    for n in ("without_shadow_photo.png", "photo.png", "no_shadow_photo.png"):
        p = os.path.join(sample, n)
        if os.path.exists(p):
            return p
    return None


def shadow_photo_path(sample):
    p = os.path.join(sample, "with_shadow_photo.png")
    return p if os.path.exists(p) else None


def resize_to(a, hw):
    H, W = hw
    return cv2.resize(a.astype(np.float32), (W, H), interpolation=cv2.INTER_AREA).astype(np.float64)


# ------------------------------------------------------------------ evaluation
def eval_sample(sample, size, exclude_marks=True):
    """Run the ORACLE-class extractor on the clean photo and compare to gt."""
    meta = json.load(open(os.path.join(sample, "meta.json")))
    label = meta.get("class_label", "?")
    gclass = CLASS_MAP.get(label)
    if gclass is None:
        return None
    photo = clean_photo_path(sample)
    gtT = load_gt_T(sample)
    gth = load_gt_h(sample)
    if photo is None or gtT is None or gth is None:
        return None

    lin = extract.load_linear(photo, None, size)
    m = extract.extract_maps(lin, gclass, mark_region="none")  # oracle class; no mark removal here
    T, h = m["T"], m["h"]
    H, W = h.shape

    gtT_r = resize_to(gtT, (H, W))
    gth_r = resize_to(gth[..., None] if gth.ndim == 2 else gth, (H, W))
    if gth_r.ndim == 3:
        gth_r = gth_r[..., 0]

    valid = np.ones((H, W), bool)
    mark = load_gt_mask(sample, "gt_mark_mask.png")
    mark_frac = 0.0
    if mark is not None:
        mark_r = resize_to(mark, (H, W)) > 0.5
        mark_frac = float(mark_r.mean())
        if exclude_marks:
            valid &= ~mark_r

    vt = valid[..., None] * np.ones((1, 1, 3), bool)
    dT = np.abs(T - gtT_r)
    dh = np.abs(h - gth_r)

    # Report 022 task D: self-reconstruction MAE alongside the GT-comparison
    # metrics above, so a single eval_synthetic.py run over new recipes
    # reports both numbers extract.py's own CLI would (process()'s
    # recon_mae_srgb255), without a second pass over the same samples.
    I_hat, _Bq = extract.reconstruct(m["L"], T, h, m["R"])
    recon_err = np.abs(extract.lin_to_srgb(np.clip(I_hat, 0, 1)) - extract.lin_to_srgb(np.clip(lin, 0, 1)))
    recon_clean = valid[..., None] * np.ones((1, 1, 3), bool)  # marks only; no specular mask here (mark_region="none")
    recon_mae_srgb255 = float(recon_err[recon_clean].mean() * 255)

    res = {
        "sample": os.path.basename(sample),
        "class_label": label,
        "glass_class": gclass,
        "size": [H, W],
        "mark_frac": mark_frac,
        "T_mae": float(dT[vt].mean()),
        "T_p95": float(np.percentile(dT[vt], 95)),
        "h_mae": float(dh[valid].mean()),
        "h_p95": float(np.percentile(dh[valid], 95)),
        "T_mean_ext": [float(v) for v in T[vt].reshape(-1, 3).mean(0)],
        "T_mean_gt": [float(v) for v in gtT_r[vt].reshape(-1, 3).mean(0)],
        "h_mean_ext": float(h[valid].mean()),
        "h_mean_gt": float(gth_r[valid].mean()),
        "T_anchor_k": m["k"],
        "T_raw_p99": m["raw_p99"],
        "recon_mae_srgb255": recon_mae_srgb255,
    }
    arrays = {"photo_lin": lin, "T": T, "gtT": gtT_r, "h": h, "gth": gth_r, "dT": dT}
    return res, arrays


def eval_shadow(sample, size):
    """Extract T from with_shadow vs without_shadow; quantify T corruption from the
    cast hand shadow (OP-1). Shadow region auto-detected as where the with-shadow
    photo is darker than the clean one (no gt_shadow_mask exists in the dataset)."""
    meta = json.load(open(os.path.join(sample, "meta.json")))
    gclass = CLASS_MAP.get(meta.get("class_label"))
    p_clean, p_sh = clean_photo_path(sample), shadow_photo_path(sample)
    if gclass is None or p_clean is None or p_sh is None:
        return None
    lin_c = extract.load_linear(p_clean, None, size)
    lin_s = extract.load_linear(p_sh, None, size)
    Tc = extract.extract_maps(lin_c, gclass, mark_region="none")["T"]
    Ts = extract.extract_maps(lin_s, gclass, mark_region="none")["T"]
    Yc, Ys = extract.lum(lin_c), extract.lum(lin_s)
    shadow = (Yc - Ys) > 0.02  # photo darkened by the cast shadow
    dT = np.abs(Ts - Tc).mean(-1)
    return {
        "sample": os.path.basename(sample),
        "class_label": meta.get("class_label"),
        "shadow_area_pct": float(shadow.mean() * 100),
        "dT_in_shadow": float(dT[shadow].mean()) if shadow.any() else None,
        "dT_outside": float(dT[~shadow].mean()) if (~shadow).any() else None,
        "dT_global": float(dT.mean()),
    }


# ------------------------------------------------------------------ VLM
def run_vlm(photo):
    from vlm_classify import classify_glass
    return classify_glass(photo)


# ------------------------------------------------------------------ rendering
def tile(img_lin_or_gray, label, linear=True, gain=1.0):
    a = img_lin_or_gray * gain
    if linear:
        a = extract.lin_to_srgb(np.clip(a, 0, 1))
    else:
        a = np.clip(a, 0, 1)
    a = (a * 255).astype(np.uint8)
    if a.ndim == 2:
        a = np.stack([a] * 3, -1)
    im = Image.fromarray(a)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(label), 15], fill=(0, 0, 0))
    d.text((3, 2), label, fill=(255, 255, 90))
    return np.asarray(im)


def contact_row(arrays, res, row_px=190):
    """original | extracted T | gt_T | T-error x5 | extracted h | gt_h."""
    cols = [
        tile(arrays["photo_lin"], "photo"),
        tile(arrays["T"], "ext T"),
        tile(arrays["gtT"], "gt T"),
        tile(arrays["dT"], "|T err| x5", linear=False, gain=5.0),
        tile(arrays["h"], "ext h", linear=False),
        tile(arrays["gth"], "gt h", linear=False),
    ]
    cols = [cv2.resize(c, (row_px, row_px), interpolation=cv2.INTER_AREA) for c in cols]
    row = np.concatenate([np.pad(c, ((2, 14), (2, 2), (0, 0)), constant_values=20) for c in cols], axis=1)
    im = Image.fromarray(row)
    ImageDraw.Draw(im).text(
        (4, row_px + 1),
        f"{res['sample']}  Tmae={res['T_mae']:.3f} hmae={res['h_mae']:.3f}",
        fill=(220, 220, 220))
    return np.asarray(im)


# ------------------------------------------------------------------ aggregation
def aggregate(rows):
    """Per-recipe (class_label) summary."""
    out = {}
    by = {}
    for r in rows:
        by.setdefault(r["class_label"], []).append(r)
    for label, rs in sorted(by.items()):
        T_mae = np.mean([r["T_mae"] for r in rs])
        T_p95 = np.mean([r["T_p95"] for r in rs])
        h_mae = np.mean([r["h_mae"] for r in rs])
        h_p95 = np.mean([r["h_p95"] for r in rs])
        ext = np.mean([r["T_mean_ext"] for r in rs], axis=0)
        gt = np.mean([r["T_mean_gt"] for r in rs], axis=0)
        out[label] = {
            "n": len(rs),
            "T_mae": float(T_mae), "T_p95": float(T_p95),
            "h_mae": float(h_mae), "h_p95": float(h_p95),
            "T_mean_ext": [float(v) for v in ext],
            "T_mean_gt": [float(v) for v in gt],
            "h_mean_ext": float(np.mean([r["h_mean_ext"] for r in rs])),
            "h_mean_gt": float(np.mean([r["h_mean_gt"] for r in rs])),
            "recon_mae_srgb255": float(np.mean([r["recon_mae_srgb255"] for r in rs])),
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="synthetic_data folder (read-only)")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "synthetic_eval"))
    ap.add_argument("--size", type=int, default=700)
    ap.add_argument("--recipes", default=None, help="comma list of class_label filters")
    ap.add_argument("--vlm", action="store_true", help="run VLM classifier once per recipe")
    ap.add_argument("--shadow", action="store_true", help="measure with/without-shadow T gap")
    ap.add_argument("--max-rows", type=int, default=4, help="max contact-sheet rows per recipe")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    recipe_filter = set(args.recipes.split(",")) if args.recipes else None

    samples = sorted(d for d in glob.glob(os.path.join(args.data, "*")) if os.path.isdir(d))
    rows, sheets, shadow_rows = [], {}, []
    skipped = []
    for s in samples:
        mp = os.path.join(s, "meta.json")
        if not os.path.exists(mp):
            skipped.append((os.path.basename(s), "no meta"))
            continue
        label = json.load(open(mp)).get("class_label", "?")
        if recipe_filter and label not in recipe_filter:
            continue
        r = eval_sample(s, args.size)
        if r is None:
            skipped.append((os.path.basename(s), "incomplete"))
            continue
        res, arrays = r
        rows.append(res)
        print(f"  {res['sample']:42s} class={res['glass_class']:15s} "
              f"T_mae={res['T_mae']:.3f} T_p95={res['T_p95']:.3f} "
              f"h_mae={res['h_mae']:.3f}  Text={np.round(res['T_mean_ext'],3)} "
              f"Tgt={np.round(res['T_mean_gt'],3)}")
        sheets.setdefault(label, [])
        if len(sheets[label]) < args.max_rows:
            sheets[label].append(contact_row(arrays, res))
        if args.shadow:
            sh = eval_shadow(s, args.size)
            if sh:
                shadow_rows.append(sh)
                print(f"    shadow: area={sh['shadow_area_pct']:.1f}% "
                      f"dT_in={sh['dT_in_shadow']} dT_out={sh['dT_outside']}")

    # contact sheets per recipe
    for label, rws in sheets.items():
        w = max(r.shape[1] for r in rws)
        rws = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=20) for r in rws]
        sheet = np.concatenate(rws, axis=0)
        Image.fromarray(sheet).save(os.path.join(args.out, f"contact_{label}.jpg"), quality=80)

    summary = aggregate(rows)

    # VLM confusion (one call per recipe)
    vlm = {}
    if args.vlm:
        for label in sorted({r["class_label"] for r in rows}):
            s = next(x for x in samples if os.path.basename(x).startswith(label))
            p = clean_photo_path(s)
            try:
                vlm[label] = {"sample": os.path.basename(s), "vlm_class": run_vlm(p),
                              "oracle_class": CLASS_MAP[label]}
            except Exception as e:
                vlm[label] = {"sample": os.path.basename(s), "error": str(e)}
            print(f"  VLM[{label}] -> {vlm[label]}")

    report = {
        "size": args.size, "n_samples": len(rows),
        "counts": {k: v["n"] for k, v in summary.items()},
        "skipped": skipped, "per_recipe": summary,
        "per_sample": rows, "shadow": shadow_rows, "vlm": vlm,
    }
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(report, f, indent=2)

    # markdown summary table
    lines = ["| recipe | n | T_mae | T_p95 | h_mae | h_p95 | T_mean_ext | T_mean_gt | h_ext | h_gt | recon_mae_srgb255 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for label, v in summary.items():
        te = ",".join(f"{x:.2f}" for x in v["T_mean_ext"])
        tg = ",".join(f"{x:.2f}" for x in v["T_mean_gt"])
        lines.append(f"| {label} | {v['n']} | {v['T_mae']:.3f} | {v['T_p95']:.3f} | "
                     f"{v['h_mae']:.3f} | {v['h_p95']:.3f} | {te} | {tg} | "
                     f"{v['h_mean_ext']:.2f} | {v['h_mean_gt']:.2f} | {v['recon_mae_srgb255']:.2f} |")
    md = "\n".join(lines)
    with open(os.path.join(args.out, "summary_table.md"), "w") as f:
        f.write(md + "\n")
    print("\n" + md)
    print(f"\nskipped: {skipped}")
    print(f"outputs in {args.out}")


if __name__ == "__main__":
    main()
