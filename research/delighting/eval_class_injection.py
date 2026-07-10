#!/usr/bin/env python3
"""Report 016: CLASS-ERROR INJECTION eval of the absolute-scale anchor.

The class prior is unreliable in the wild (report 015: VLM 30.6% vs catalog
metadata, and the metadata itself is noisy marketing taxonomy at class
boundaries), and the pipeline's absolute T scale hangs on that class via
T_ANCHOR. This harness measures how each anchor design degrades when the
class is WRONG: every synthetic-v2 sample is extracted under ALL FOUR class
priors, and T is scored against ground truth per (recipe x assumed-class x
anchor-design).

Anchor designs compared:
  class       T_ANCHOR[assumed_class] target (reports 003/009), i.e. current
  continuous  extract.estimate_anchor_scale image estimate blended with the
              class target via extract.blend_anchor_target (report 016)
Optionally (--sweep) a grid of blend variants, used to pick the shipped
blend constants; the headline table is class vs continuous.

The anchor target only affects the final scalar gain k, so the pipeline is
run ONCE per (sample, assumed class) with anchor='none' and every design is
applied on top (including the ANCHOR_K_MIN/MAX sanity gate, replicated
exactly), making the sweep cheap and the comparison exact.

Metrics per cell: T_mae vs gt (marked pixels excluded, as eval_synthetic),
and T_lum_ratio = mean extracted T luminance / mean gt T luminance (the
"came out N x too bright" number that makes the dark-opaque-as-cathedral
failure legible).

Usage:  eval_class_injection.py --data DIR [--out DIR] [--size 700] [--sweep]
"""
import argparse
import glob
import json
import os
import sys

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import cv2  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract  # noqa: E402
from eval_synthetic import CLASS_MAP, load_gt_T, load_gt_mask, clean_photo_path, resize_to  # noqa: E402


def apply_anchor(T_pre, R, target, pct=99):
    """Replicates extract_maps' anchor + sanity gate on an unanchored T."""
    T = T_pre
    k = target / max(np.percentile(T, pct), 1e-3)
    fallback = False
    if not (extract.ANCHOR_K_MIN < k < extract.ANCHOR_K_MAX):
        fallback = True
        T = np.clip(R, 0, 1)
        k = target / max(np.percentile(T, pct), 1e-3)
        k = float(np.clip(k, extract.ANCHOR_K_MIN, extract.ANCHOR_K_MAX))
    return np.clip(T * k, 0, 1), float(k), fallback


def blend_with(t_class, t_img, tau0, tau1, wmax):
    d = abs(np.log(t_img) - np.log(t_class))
    ramp = (d - np.log(tau0)) / (np.log(tau1) - np.log(tau0))
    w = wmax * float(np.clip(ramp, 0.0, 1.0))
    return float(np.exp((1.0 - w) * np.log(t_class) + w * np.log(t_img)))


def designs(sweep=False):
    """name -> fn(t_class, t_img) -> anchor target."""
    d = {
        "class": lambda tc, ti: tc,
        "continuous": extract.blend_anchor_target,
    }
    if sweep:
        d["img-only"] = lambda tc, ti: ti
        for w in (0.3, 0.5, 0.7):
            d[f"fixed-w{w}"] = lambda tc, ti, w=w: float(np.exp((1 - w) * np.log(tc) + w * np.log(ti)))
        for tau0, tau1, wmax in ((1.3, 2.5, 0.85), (1.5, 3.0, 0.7), (1.5, 3.0, 1.0),
                                 (2.0, 4.0, 0.85), (1.2, 2.0, 0.85)):
            d[f"adap-{tau0}-{tau1}-{wmax}"] = lambda tc, ti, a=tau0, b=tau1, c=wmax: blend_with(tc, ti, a, b, c)
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "results", "class_injection"))
    ap.add_argument("--size", type=int, default=700)
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    D = designs(args.sweep)

    rows = []
    samples = sorted(d for d in glob.glob(os.path.join(args.data, "*")) if os.path.isdir(d))
    for s in samples:
        mp = os.path.join(s, "meta.json")
        if not os.path.exists(mp):
            continue
        label = json.load(open(mp)).get("class_label")
        oracle = CLASS_MAP.get(label)
        photo = clean_photo_path(s)
        gtT = load_gt_T(s)
        if oracle is None or photo is None or gtT is None:
            continue
        lin = extract.load_linear(photo, None, args.size)
        t_img = float(extract.estimate_anchor_scale(lin))
        gt_scale = float(np.percentile(gtT, 99))

        for cls in extract.CLASSES:
            m = extract.extract_maps(lin, cls, mark_region="none", anchor="none")
            T_pre, R = m["T"], m["R"]
            H, W = m["h"].shape
            gtT_r = resize_to(gtT, (H, W))
            valid = np.ones((H, W), bool)
            mark = load_gt_mask(s, "gt_mark_mask.png")
            if mark is not None:
                valid &= ~(resize_to(mark, (H, W)) > 0.5)
            vt = valid[..., None] * np.ones((1, 1, 3), bool)
            gt_lum = float(extract.lum(gtT_r)[valid].mean())

            for name, fn in D.items():
                target = fn(extract.T_ANCHOR[cls][1], t_img)
                T, k, fb = apply_anchor(T_pre, R, target)
                mae = float(np.abs(T - gtT_r)[vt].mean())
                lum_ratio = float(extract.lum(T)[valid].mean() / max(gt_lum, 1e-6))
                rows.append(dict(sample=os.path.basename(s), label=label,
                                 oracle_class=oracle, assumed_class=cls,
                                 correct=cls == oracle, design=name,
                                 t_img=t_img, gt_scale=gt_scale,
                                 anchor_target=target, k=k, gate_fired=fb,
                                 T_mae=mae, T_lum_ratio=lum_ratio))
            done = [r for r in rows if r["sample"] == os.path.basename(s) and r["assumed_class"] == cls]
            msg = " ".join(f"{r['design']}={r['T_mae']:.3f}" for r in done)
            print(f"{os.path.basename(s):40s} as {cls:16s} t_img={t_img:.3f} {msg}", flush=True)

    json.dump(rows, open(os.path.join(args.out, "injection_rows.json"), "w"), indent=2)

    # ---------------- aggregation ----------------
    def agg(sel):
        return (float(np.mean([r["T_mae"] for r in sel])),
                float(np.mean([r["T_lum_ratio"] for r in sel])),
                float(max((max(r["T_lum_ratio"], 1 / max(r["T_lum_ratio"], 1e-6)))
                          for r in sel)))

    labels = sorted({r["label"] for r in rows})
    lines = []
    for name in D:
        lines.append(f"\n### design = {name}\n")
        lines.append("| recipe (oracle) | " + " | ".join(
            f"as {c}" for c in extract.CLASSES) + " |")
        lines.append("|---|" + "---|" * len(extract.CLASSES))
        for label in labels:
            oracle = CLASS_MAP[label]
            cells = []
            for cls in extract.CLASSES:
                sel = [r for r in rows if r["label"] == label and
                       r["assumed_class"] == cls and r["design"] == name]
                mae, lr, _ = agg(sel)
                mark = " *" if cls == oracle else ""
                cells.append(f"{mae:.3f} ({lr:.2f}x){mark}")
            lines.append(f"| {label} ({oracle}) | " + " | ".join(cells) + " |")

    lines.append("\n### summary: mean T_mae (mean lum-ratio error)\n")
    lines.append("| design | correct class | wrong class | worst wrong-class lum-ratio |")
    lines.append("|---|---|---|---|")
    for name in D:
        cor = [r for r in rows if r["design"] == name and r["correct"]]
        wrn = [r for r in rows if r["design"] == name and not r["correct"]]
        cm, _, _ = agg(cor)
        wm, _, wworst = agg(wrn)
        lines.append(f"| {name} | {cm:.3f} | {wm:.3f} | {wworst:.2f}x |")

    md = "\n".join(lines)
    with open(os.path.join(args.out, "injection_tables.md"), "w") as f:
        f.write(md + "\n")
    print(md)
    print(f"\noutputs in {args.out}")


if __name__ == "__main__":
    main()
