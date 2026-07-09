#!/usr/bin/env python3
"""Held-out preview-invariance eval: classical vs classical+neural shadow removal.

Reuses eval_preview_invariance's methodology. For each sample we render the
controlled studio preview from GT maps (target), then compare three routes to
the preview a user would see FROM THE WITH-SHADOW PHOTO:

  (i)   raw-copy      : the with-shadow photo, exposure-matched to target
  (ii)  classical     : render(T_ws, h_ws)             -- no shadow handling
  (iii) neural        : render(blend(T_ws, m, T_pred), h_ws)  -- our correction

The headline metric is inside-shadow preview MAE (sRGB/255). Win = (iii) < (ii)
on held-out lighting, especially cathedral, without degrading non-shadow pixels.
"""
import argparse
import json
import os

import numpy as np
import torch
from PIL import Image, ImageDraw

import common
import extract
import eval_preview_invariance as epi
from model import ShadowUNet, blend


def preview(T, h, bg):
    return epi.render_preview(T, h, bg)


def mae_region(a, b, region):
    if region.sum() == 0:
        return None
    return epi.srgb_mae255(a, b, region)


def run_net(net, device, lin_ws, T_ws):
    x = np.concatenate([lin_ws, T_ws], axis=-1)
    xt = torch.from_numpy(x).permute(2, 0, 1)[None].float().to(device)
    with torch.no_grad():
        mask_logit, T_pred = net(xt)
        mprob = torch.sigmoid(mask_logit)
        T_final = blend(xt[:, 3:6], mprob, T_pred)
    T_final = T_final[0].permute(1, 2, 0).cpu().numpy().astype(np.float64)
    mprob = mprob[0, 0].cpu().numpy().astype(np.float64)
    return T_final, mprob


def tile(img, label, linear=True, gain=1.0):
    arr = np.clip(np.asarray(img) * gain, 0, 1)
    if linear:
        arr = extract.lin_to_srgb(arr)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, -1)
    im = Image.fromarray((arr * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(label), 16], fill=(0, 0, 0))
    d.text((4, 2), label, fill=(255, 255, 90))
    return np.asarray(im)


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

    rows, contact = [], []
    for name in pick:
        z = np.load(os.path.join(common.CACHE_DIR, name + ".npz"))
        lin_ws = z["lin_ws"].astype(np.float64)
        T_ws, h_ws = z["T_ws"].astype(np.float64), z["h_ws"].astype(np.float64)
        gt_T, gt_h = z["gt_T"].astype(np.float64), z["gt_h"].astype(np.float64)
        shadow, valid = z["shadow"], z["valid"]
        label = str(z["class_label"])
        H, W = h_ws.shape
        bg = epi.preview_background(H, W)

        T_neural, mprob = run_net(net, device, z["lin_ws"], z["T_ws"])

        target = preview(gt_T, gt_h, bg)
        mat_cls = preview(T_ws, h_ws, bg)
        mat_neu = preview(T_neural, h_ws, bg)
        raw = epi.exposure_match(lin_ws, target, valid)

        nonshadow = valid & ~shadow
        row = {
            "sample": name, "class_label": label,
            "glass_class": common.CLASS_MAP[label],
            "shadow_pct": float(shadow.mean() * 100),
            "pred_shadow_pct": float((mprob > 0.5)[valid].mean() * 100),
            # inside-shadow preview MAE (the headline)
            "in_raw": mae_region(raw, target, shadow),
            "in_classical": mae_region(mat_cls, target, shadow),
            "in_neural": mae_region(mat_neu, target, shadow),
            # non-shadow: must not degrade
            "out_classical": mae_region(mat_cls, target, nonshadow),
            "out_neural": mae_region(mat_neu, target, nonshadow),
            # whole valid
            "all_classical": epi.srgb_mae255(mat_cls, target, valid),
            "all_neural": epi.srgb_mae255(mat_neu, target, valid),
        }
        rows.append(row)
        ins = lambda k: "n/a" if row[k] is None else f"{row[k]:.1f}"
        print(f"{name:42s} sh={row['shadow_pct']:4.1f}%  IN raw={ins('in_raw')} "
              f"cls={ins('in_classical')} neu={ins('in_neural')}   "
              f"OUT cls={row['out_classical']:.1f} neu={row['out_neural']:.1f}")

        # contact row (downscaled)
        cols = [
            tile(raw, "raw(shadow)"), tile(target, "target"),
            tile(mat_cls, "classical"), tile(mat_neu, "neural"),
            tile(shadow.astype(float), "gt shadow", linear=False),
            tile(mprob, "pred mask", linear=False),
            tile(np.abs(extract.lin_to_srgb(np.clip(mat_cls, 0, 1)) -
                        extract.lin_to_srgb(np.clip(target, 0, 1))), "cls err x4", linear=False, gain=4.0),
            tile(np.abs(extract.lin_to_srgb(np.clip(mat_neu, 0, 1)) -
                        extract.lin_to_srgb(np.clip(target, 0, 1))), "neu err x4", linear=False, gain=4.0),
        ]
        import cv2
        cols = [cv2.resize(c, (150, 150), interpolation=cv2.INTER_AREA) for c in cols]
        rowimg = np.concatenate([np.pad(c, ((2, 16), (2, 2), (0, 0)), constant_values=20) for c in cols], 1)
        im = Image.fromarray(rowimg)
        ImageDraw.Draw(im).text((4, 152), f"{name}  in cls={ins('in_classical')} neu={ins('in_neural')}",
                                fill=(230, 230, 230))
        contact.append(np.asarray(im))

    # aggregates (per class and overall), inside-shadow only where a shadow exists
    def agg(rs):
        def m(key):
            vals = [r[key] for r in rs if r[key] is not None]
            return float(np.mean(vals)) if vals else None
        return {"n": len(rs), "in_raw": m("in_raw"), "in_classical": m("in_classical"),
                "in_neural": m("in_neural"), "out_classical": m("out_classical"),
                "out_neural": m("out_neural"), "all_classical": m("all_classical"),
                "all_neural": m("all_neural")}

    per_class = {lab: agg([r for r in rows if r["class_label"] == lab])
                 for lab in sorted({r["class_label"] for r in rows})}
    cath = agg([r for r in rows if r["glass_class"] == "cathedral-clear"])
    overall = agg(rows)
    # inside-shadow aggregate over samples with a real shadow (>0.5%)
    with_shadow = agg([r for r in rows if r["shadow_pct"] > 0.5])

    summary = {"split": args.split, "per_sample": rows, "per_class": per_class,
               "cathedral": cath, "overall": overall,
               "with_shadow_samples": with_shadow}
    json.dump(summary, open(os.path.join(args.out, f"neural_eval_{args.split}.json"), "w"), indent=2)

    if contact:
        width = max(r.shape[1] for r in contact)
        padded = [np.pad(r, ((0, 0), (0, width - r.shape[1]), (0, 0)), constant_values=20) for r in contact]
        Image.fromarray(np.concatenate(padded, 0)).save(
            os.path.join(args.out, f"neural_contact_{args.split}.jpg"), quality=82)

    print("\n=== inside-shadow preview MAE (sRGB/255), samples with shadow>0.5% ===")
    print(f"  raw-copy   : {with_shadow['in_raw']:.1f}")
    print(f"  classical  : {with_shadow['in_classical']:.1f}")
    print(f"  neural     : {with_shadow['in_neural']:.1f}")
    print(f"=== cathedral inside-shadow: cls={cath['in_classical']:.1f} -> neu={cath['in_neural']:.1f} ===")
    print(f"=== non-shadow MAE (all): cls={overall['out_classical']:.1f} -> neu={overall['out_neural']:.1f} ===")
    print(f"outputs -> {args.out}")


if __name__ == "__main__":
    main()
