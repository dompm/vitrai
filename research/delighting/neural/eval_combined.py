#!/usr/bin/env python3
"""Combined end-to-end eval: ORIGINAL vs FIXED classical vs FIXED+neural shadow.

Three preview-invariance conditions, all scored against the same GT-rendered
controlled preview (target), on the HELD-OUT split (unseen lighting):

  (1) original  : classical maps from the ORIGINAL extract.py (report 010 baseline)
  (2) fixed     : classical maps from the FIXED extract.py (report 009: absolute-
                  scale anchor + color-constancy fixes)
  (3) fixed+neural : the shadow-removal U-Net applied on top of the FIXED maps

Requires two caches: cache/ (original extractor) and cache_fixed/ (fixed
extractor, built via `NEURAL_CACHE=cache_fixed prepare_data.py`).

DISTRIBUTION-SHIFT NOTE: the U-Net was trained with the ORIGINAL extractor's T as
input. Cathedral/wispy T are (near) unchanged by the fix, so (3) is in-distribution
there. dark-opaque T changed materially -> (3) feeds the model out-of-distribution
input; we report it and flag it honestly rather than retrain.

v2 NOTE (report 012): on `research/delighting-datav2` there is only ONE classical
extractor (the fixed one merged in from report 009/011 -- there is no separate
buggy "original" left to diff against). NEURAL_CACHE_ORIG / NEURAL_CACHE_FIX let
the caller point both at the same v2 cache, so `orig == fixed` trivially
(T-shift 0) and the three meaningful conditions become raw / fixed-classical /
fixed-classical+retrained-neural, which is what report 012 actually compares.
"""
import argparse
import json
import os

import numpy as np
import torch

import common
import eval_preview_invariance as epi
from model import ShadowUNet, blend

CACHE_ORIG = os.environ.get("NEURAL_CACHE_ORIG", os.path.join(common.HERE, "cache"))
CACHE_FIX = os.environ.get("NEURAL_CACHE_FIX", os.path.join(common.HERE, "cache_fixed"))


def preview(T, h, bg):
    return epi.render_preview(T, h, bg)


def region_mae(a, b, region):
    return None if region.sum() == 0 else epi.srgb_mae255(a, b, region)


def run_net(net, device, lin_ws, T_ws):
    x = np.concatenate([lin_ws, T_ws], axis=-1)
    xt = torch.from_numpy(x).permute(2, 0, 1)[None].float().to(device)
    with torch.no_grad():
        mask_logit, T_pred = net(xt)
        mprob = torch.sigmoid(mask_logit)
        T_final = blend(xt[:, 3:6], mprob, T_pred)
    return T_final[0].permute(1, 2, 0).cpu().numpy().astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(common.HERE, "results"))
    ap.add_argument("--split", choices=["test", "train", "all"], default="test")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    ckpt = torch.load(common.WEIGHTS, map_location=device, weights_only=False)
    net = ShadowUNet(in_ch=ckpt["in_ch"], base=ckpt["base"]).to(device).eval()
    net.load_state_dict(ckpt["state_dict"])

    names = common.list_samples()
    train_names, test_names = common.split(names)
    pick = {"test": test_names, "train": train_names, "all": names}[args.split]

    rows = []
    for name in pick:
        o = np.load(os.path.join(CACHE_ORIG, name + ".npz"))
        f = np.load(os.path.join(CACHE_FIX, name + ".npz"))
        gt_T, gt_h = f["gt_T"].astype(np.float64), f["gt_h"].astype(np.float64)
        shadow, valid = f["shadow"], f["valid"]
        label = str(f["class_label"])
        H, W = gt_h.shape
        bg = epi.preview_background(H, W)

        target = preview(gt_T, gt_h, bg)
        lin_ws = f["lin_ws"].astype(np.float64)
        raw = epi.exposure_match(lin_ws, target, valid)

        p_orig = preview(o["T_ws"].astype(np.float64), o["h_ws"].astype(np.float64), bg)
        p_fix = preview(f["T_ws"].astype(np.float64), f["h_ws"].astype(np.float64), bg)
        T_neu = run_net(net, device, f["lin_ws"], f["T_ws"])
        p_neu = preview(T_neu, f["h_ws"].astype(np.float64), bg)

        nonshadow = valid & ~shadow
        Tshift = float(np.abs(o["T_ws"].astype(np.float64) - f["T_ws"].astype(np.float64))[valid].mean())
        rows.append({
            "sample": name, "class_label": label,
            "glass_class": common.CLASS_MAP[label],
            "shadow_pct": float(shadow.mean() * 100),
            "T_shift_orig_to_fixed": Tshift,
            "in_raw": region_mae(raw, target, shadow),
            "in_orig": region_mae(p_orig, target, shadow),
            "in_fixed": region_mae(p_fix, target, shadow),
            "in_neural": region_mae(p_neu, target, shadow),
            "out_raw": region_mae(raw, target, nonshadow),
            "out_orig": region_mae(p_orig, target, nonshadow),
            "out_fixed": region_mae(p_fix, target, nonshadow),
            "out_neural": region_mae(p_neu, target, nonshadow),
            "all_raw": epi.srgb_mae255(raw, target, valid),
            "all_orig": epi.srgb_mae255(p_orig, target, valid),
            "all_fixed": epi.srgb_mae255(p_fix, target, valid),
            "all_neural": epi.srgb_mae255(p_neu, target, valid),
        })
        r = rows[-1]
        g = lambda k: "n/a" if r[k] is None else f"{r[k]:5.1f}"
        print(f"{name:42s} sh={r['shadow_pct']:4.1f}%  IN orig={g('in_orig')} fixed={g('in_fixed')} "
              f"neu={g('in_neural')} | OUT orig={g('out_orig')} fixed={g('out_fixed')} neu={g('out_neural')}")

    def agg(rs, keys):
        out = {"n": len(rs)}
        for k in keys:
            vals = [r[k] for r in rs if r.get(k) is not None]
            out[k] = float(np.mean(vals)) if vals else None
        return out

    keys = ["in_raw", "in_orig", "in_fixed", "in_neural",
            "out_raw", "out_orig", "out_fixed", "out_neural",
            "all_raw", "all_orig", "all_fixed", "all_neural", "T_shift_orig_to_fixed"]
    per_recipe = {lab: agg([r for r in rows if r["class_label"] == lab], keys)
                  for lab in sorted({r["class_label"] for r in rows})}
    shadowed = [r for r in rows if r["shadow_pct"] > 0.5]
    summary = {"split": args.split, "per_sample": rows, "per_recipe": per_recipe,
               "cathedral": agg([r for r in rows if r["glass_class"] == "cathedral-clear"], keys),
               "shadowed_overall": agg(shadowed, keys),
               "overall": agg(rows, keys)}
    json.dump(summary, open(os.path.join(args.out, f"combined_eval_{args.split}.json"), "w"), indent=2)

    # markdown table (per recipe, inside/outside shadow)
    def cell(v):
        return "n/a" if v is None else f"{v:.1f}"
    lines = ["| recipe | n | IN raw | IN orig | IN fixed | IN fixed+neural | OUT raw | OUT orig | OUT fixed | OUT fixed+neural | T-shift |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for lab, v in per_recipe.items():
        lines.append(f"| {lab} | {v['n']} | {cell(v['in_raw'])} | {cell(v['in_orig'])} | {cell(v['in_fixed'])} | "
                     f"{cell(v['in_neural'])} | {cell(v['out_raw'])} | {cell(v['out_orig'])} | {cell(v['out_fixed'])} | "
                     f"{cell(v['out_neural'])} | {cell(v['T_shift_orig_to_fixed'])} |")
    so = summary["shadowed_overall"]
    lines.append(f"| **shadowed (all)** | {so['n']} | {cell(so['in_raw'])} | {cell(so['in_orig'])} | {cell(so['in_fixed'])} | "
                 f"{cell(so['in_neural'])} | {cell(so['out_raw'])} | {cell(so['out_orig'])} | {cell(so['out_fixed'])} | "
                 f"{cell(so['out_neural'])} | - |")
    table = "\n".join(lines)
    open(os.path.join(args.out, f"combined_table_{args.split}.md"), "w").write(table + "\n")
    print("\n" + table)
    print(f"\noutputs -> {args.out}")


if __name__ == "__main__":
    main()
