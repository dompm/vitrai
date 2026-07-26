#!/usr/bin/env python3
"""055 — ZERO-SHOT on the CTO's real Pixel photos: model vs the classical extractor.

The external 053 review's final gate: "evaluate zero-shot on untouched cropped phone
photos". These 15 handheld Pixel captures were never in any training set and were never
rendered — they are the sim-to-real test. For each photo we emit one panel row:

  photo crop | model T | model σ_s | model conf | checker relit by model σ_s | classical T | classical h

so the model's maps sit directly beside the frozen classical extractor's maps on the SAME
crop. Panels are meant to show warts: no cherry-picking, every photo in the set is emitted.

Crops: the sheet region only (hands, background, window frame excluded). Two photos use the
lead's measured corner rects; the rest use a per-photo centred fraction, verified by eye via
`--crops-only` before any model was run.

Usage:
  real_photo_panels.py --crops-only --out results/055/real       # verify the crop table
  real_photo_panels.py --ckpt <adapter.pt> --out results/055/real
"""
import argparse
import json
import os
import sys

import numpy as np

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, DELIGHT)
from extract import srgb_to_lin, lin_to_srgb, extract_maps  # noqa: E402

PHOTO_DIR = "/Users/dominiquepiche-meunier/Documents/vitrai-datasets/real-user-photos-2026-05"

# Per-photo config, assigned from a contact sheet of all 15 (results/055/real/contact.jpg).
#   cls          : --glass-class for the classical extractor (and documentation of the taxon)
#   mark         : mark_region passed to extract_maps
#   rect         : explicit (x0,y0,x1,y1) sheet crop -- the lead's measured corners
#   frac         : (w_frac, h_frac, cx, cy) centred crop as a fraction of the full frame,
#                  cx/cy in [0,1] = crop centre. Used when `rect` is None.
CONFIG = {
    "PXL_20260508_165038844": dict(cls="wispy",           mark="none", frac=(0.30, 0.72, 0.50, 0.50)),
    "PXL_20260508_165112222": dict(cls="opalescent",      mark="bottom-right", frac=(0.62, 0.55, 0.50, 0.48)),
    "PXL_20260509_231130531": dict(cls="opalescent",      mark="none", frac=(0.60, 0.50, 0.50, 0.45)),
    "PXL_20260509_231242267": dict(cls="wispy",           mark="none", rect=(380, 470, 2630, 3870)),
    "PXL_20260509_231306065": dict(cls="wispy",           mark="none", frac=(0.45, 0.55, 0.50, 0.48)),
    "PXL_20260509_231322397": dict(cls="wispy",           mark="none", frac=(0.30, 0.42, 0.52, 0.45)),
    "PXL_20260509_231524518": dict(cls="dark-opaque",     mark="none", frac=(0.45, 0.60, 0.50, 0.50)),
    "PXL_20260509_231602127": dict(cls="wispy",           mark="none", frac=(0.58, 0.58, 0.50, 0.50)),
    "PXL_20260509_231625820": dict(cls="dark-opaque",     mark="none", rect=(120, 10, 2960, 4070)),
    "PXL_20260509_231659060": dict(cls="opalescent",      mark="none", frac=(0.36, 0.48, 0.52, 0.48)),
    "PXL_20260509_231731810": dict(cls="opalescent",      mark="none", frac=(0.36, 0.50, 0.52, 0.48)),
    "PXL_20260509_231821794": dict(cls="cathedral-clear", mark="none", frac=(0.58, 0.52, 0.50, 0.50)),
    "PXL_20260509_231918269": dict(cls="wispy",           mark="none", frac=(0.30, 0.48, 0.50, 0.50)),
    "PXL_20260509_231939252": dict(cls="opalescent",      mark="none", frac=(0.60, 0.55, 0.50, 0.52)),
    "PXL_20260509_231948511": dict(cls="opalescent",      mark="none", frac=(0.42, 0.55, 0.52, 0.50)),
}


def crop_of(img, cfg):
    H, W = img.shape[:2]
    if cfg.get("rect"):
        x0, y0, x1, y1 = cfg["rect"]
    else:
        fw, fh, cx, cy = cfg["frac"]
        w, h = int(W * fw), int(H * fh)
        x0, y0 = int(W * cx - w / 2), int(H * cy - h / 2)
        x1, y1 = x0 + w, y0 + h
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    return img[y0:y1, x0:x1], (x0, y0, x1, y1)


def to_work(a, work):
    H, W = a.shape[:2]
    s = work / max(H, W)
    return cv2.resize(a, (max(8, int(round(W * s))), max(8, int(round(H * s)))),
                      interpolation=cv2.INTER_AREA)


def label(img_u8, text, h=26):
    bar = np.zeros((h, img_u8.shape[1], 3), np.uint8)
    cv2.putText(bar, text, (6, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return np.concatenate([bar, img_u8], 0)


def gray3(a):
    """single-channel [0,1] -> 3-channel uint8"""
    a = np.clip(a[..., 0] if a.ndim == 3 else a, 0, 1)
    return (np.repeat(a[..., None], 3, -1) * 255).astype(np.uint8)


def srgb_u8(lin):
    return (np.clip(lin_to_srgb(np.clip(lin, 0, 1)), 0, 1) * 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--backbone", default="marigold-iid")
    ap.add_argument("--out", required=True)
    ap.add_argument("--work", type=int, default=512)
    ap.add_argument("--crops-only", action="store_true",
                    help="dump only the crop contact sheet (no model, no extractor)")
    ap.add_argument("--no-classical", action="store_true")
    ap.add_argument("--device", default=None)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    names = sorted(CONFIG)
    # ---------------------------------------------------------------- crop check
    if args.crops_only:
        cells = []
        for n in names:
            full = cv2.imread(os.path.join(PHOTO_DIR, n + ".jpg"))
            c, rect = crop_of(full, CONFIG[n])
            th = to_work(c, 300)
            cell = np.zeros((330, 300, 3), np.uint8)
            cell[30:30 + th.shape[0], :th.shape[1]] = th[:300, :300]
            cv2.putText(cell, f"{n[4:]} {CONFIG[n]['cls'][:11]}", (4, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
            cells.append(cell)
            print(f"{n}  crop={rect}  {c.shape[1]}x{c.shape[0]}")
        while len(cells) % 5:
            cells.append(np.zeros((330, 300, 3), np.uint8))
        rows = [np.concatenate(cells[i:i + 5], 1) for i in range(0, len(cells), 5)]
        p = os.path.join(args.out, "crop_check.jpg")
        cv2.imwrite(p, np.concatenate(rows, 0), [cv2.IMWRITE_JPEG_QUALITY, 90])
        print("wrote", p)
        return

    # ---------------------------------------------------------------- model
    import torch
    from backbone import FoundationDelighter
    import eval_foundation as ef
    dev = args.device or ("mps" if torch.backends.mps.is_available() else "cpu")
    model = FoundationDelighter(backbone=args.backbone, freeze_backbone=True,
                                cache_only=True).to(dev)
    model.load_adapter(args.ckpt, map_location=dev)
    model.eval()
    print(f"[real] loaded {args.ckpt} on {dev}")

    stats = {}
    rows = []
    for n in names:
        cfg = CONFIG[n]
        full = cv2.imread(os.path.join(PHOTO_DIR, n + ".jpg"))[..., ::-1]
        c, rect = crop_of(full, cfg)
        rgb = to_work(c.astype(np.float32) / 255.0, args.work)
        lin = srgb_to_lin(rgb)

        # ---- model ----
        ph = ef._pad8(np.ascontiguousarray(lin))
        with torch.no_grad():
            out = model(torch.from_numpy(ph).permute(2, 0, 1)[None].float().to(dev).clamp(0, None))

        def npx(k, ch):
            a = out[k][0].permute(1, 2, 0).float().cpu().numpy()
            return a[:lin.shape[0], :lin.shape[1], :ch]
        mT = npx("T", 3)
        mh = npx("h", 1)
        msig = npx("sigma_s", 1)
        mconf = npx("conf", 1)

        # ---- σ_s effect on a structured backdrop (same instrument as the synthetic eval) ----
        H, W = msig.shape[:2]
        checker = ef._checker(H, W)
        stack = ef._blur_stack(checker, ef._SIGMA_LEVELS)
        relit = ef._relight_checker(msig[..., 0], checker, stack)

        # ---- classical ----
        cT = ch_ = None
        if not args.no_classical:
            try:
                m = extract_maps(lin, cfg["cls"], mark_region=cfg["mark"])
                cT, ch_ = m["T"], m["h"]
            except Exception as e:
                print(f"  [classical FAILED {n}] {str(e)[:90]}")

        tiles = [label(srgb_u8(lin), f"{n[4:]} photo ({cfg['cls']})"),
                 label(srgb_u8(mT), "model T"),
                 label(gray3(msig), "model sigma_s"),
                 label(gray3(mconf), "model conf"),
                 label(srgb_u8(relit), "checker relit by model sigma_s")]
        if cT is not None:
            tiles += [label(srgb_u8(cT), "classical T"), label(gray3(ch_), "classical h")]
        hgt = min(t.shape[0] for t in tiles)
        row = np.concatenate([t[:hgt] for t in tiles], 1)
        cv2.imwrite(os.path.join(args.out, f"{n}_panel.jpg"), row[..., ::-1],
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        rows.append(row)

        stats[n] = {
            "glass_class": cfg["cls"], "crop_rect": list(rect),
            "model_T_mean": [float(x) for x in mT.reshape(-1, 3).mean(0)],
            "model_h_mean": float(mh.mean()), "model_sigma_s_mean": float(msig.mean()),
            "model_conf_mean": float(mconf.mean()), "model_conf_p10": float(np.percentile(mconf, 10)),
            "model_T_std": float(mT.std()),
            "photo_lin_p99": float(np.percentile(lin, 99)),
        }
        if cT is not None:
            stats[n].update({
                "classical_T_mean": [float(x) for x in cT.reshape(-1, 3).mean(0)],
                "classical_h_mean": float(ch_.mean()),
                "classical_T_std": float(cT.std()),
                "model_vs_classical_T_mae": float(np.abs(mT - cT).mean()),
            })
        print(f"  {n} done | T={stats[n]['model_T_mean']} conf={stats[n]['model_conf_mean']:.3f}",
              flush=True)

    wmax = max(r.shape[1] for r in rows)
    board = np.concatenate([np.pad(r, ((0, 6), (0, wmax - r.shape[1]), (0, 0))) for r in rows], 0)
    cv2.imwrite(os.path.join(args.out, "board_real_zeroshot.jpg"), board[..., ::-1],
                [cv2.IMWRITE_JPEG_QUALITY, 86])
    json.dump(stats, open(os.path.join(args.out, "real_stats.json"), "w"), indent=2)
    print(f"[real] wrote {len(rows)} panels + board_real_zeroshot.jpg + real_stats.json")


if __name__ == "__main__":
    main()
