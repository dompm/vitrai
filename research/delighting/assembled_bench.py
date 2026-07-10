#!/usr/bin/env python3
"""Assembled-pair benchmark (report 014): the project's purest end-to-end metric.

Everything is simulated in Blender so the flat sheet CAPTURE and the ASSEMBLED
piece are the SAME authored glass by construction (see generate_assembled.py):
  RENDER A -- flat sheet under IBL_1 (the extractor's input photo)
  RENDER B -- 2x2 assembled leaded piece under IBL_2 (same HDRI rotated + EV) -- the RELIGHT TRUTH
  RENDER C -- the same assembled piece under IBL_1 (assembly-model control)

Pipeline under test:
 1. extract T,h from RENDER A with the fixed classical extractor (oracle class);
 2. composite the four pieces app-style by sampling the extracted maps at the
    KNOWN UV rects recorded in meta.json, laid in a 2x2 grid with flat dark strips;
 3. relight the composite with an illuminant estimated for IBL_2, derived HONESTLY:
       I2_hat = <L_A> * 2^(ev2 - ev1)
    where <L_A> is the mean of the extractor's own recovered illumination field
    L from RENDER A, and 2^(ev2-ev1) is the KNOWN EV delta from meta. This uses
    NO pixel of RENDER B. The HDRI rotation's effect on the backlight COLOUR is
    deliberately NOT modelled -- that is the documented honest limitation, and we
    quantify it with an ORACLE-global-gain ceiling (a per-channel least-squares
    gain fit to RENDER B; labelled cheating, reported only to attribute error).

Baseline: RAW-COPY -- sample RENDER A's photo pixels at the same UV rects, same
strips, and the same global EV exposure match (2^(ev2-ev1)). Grants raw the same
EV knowledge as relit, so the ONLY difference measured is whether the capture's
spatial lighting envelope is baked in (raw) or removed and re-lit flat (relit).

Metrics (inside piece masks, eroded a few px):
 1. RELIGHT FIDELITY -- composite-vs-RENDER-B MAE per condition; plus RENDER C vs
    composite-under-IBL_1 for the assembly-model split.
 2. DRAG TEST -- re-source each piece from N=9 UV positions; variance (luminance
    CV) of the assembled result across positions, raw vs relit, both vs the GRAIN
    FLOOR = the same-size-region variance of the AUTHORED gt_T directly.
 3. Visual panels: RENDER B | relit | raw, per material; + a drag-test strip.

Run: /usr/bin/python3 assembled_bench.py --data assembled_data --out results/assembled
"""
import argparse
import json
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw

import extract  # fixed classical extractor (report 009)

LUM = np.array([0.2126, 0.7152, 0.0722])
CLASS_MAP = {"cathedral-green": "cathedral-clear", "cathedral-amber": "cathedral-clear",
             "wispy-white": "wispy", "streaky-mix": "wispy", "dark-opaque": "dark-opaque"}
EROOD = 10  # piece-mask erosion (px)


# ----------------------------------------------------------------- io / space
def load_exr(p):
    a = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    if a is None:
        raise FileNotFoundError(p)
    return (a[..., ::-1] if a.ndim == 3 else np.stack([a] * 3, -1)).astype(np.float64)


def lum(a):
    return a[..., 0] * LUM[0] + a[..., 1] * LUM[1] + a[..., 2] * LUM[2]


def lin_to_srgb(a):
    return extract.lin_to_srgb(a)


def to_lab(rgb_lin):
    """rgb_lin: HxWx3 linear -> HxWx3 CIELAB."""
    srgb = np.clip(lin_to_srgb(np.clip(rgb_lin, 0, 1)), 0, 1).astype(np.float32)
    return cv2.cvtColor(srgb, cv2.COLOR_RGB2LAB).astype(np.float64)


# ----------------------------------------------------------------- projection
def uv_to_px(u, v, pj):
    col = (u - pj["u_lo"]) / (pj["u_hi"] - pj["u_lo"]) * pj["W"]
    row = (pj["v_hi"] - v) / (pj["v_hi"] - pj["v_lo"]) * pj["H"]
    return col, row


def uv_window_bbox(uc, vc, half_uv, pj):
    """Pixel bbox (x0,y0,x1,y1) in RENDER-A space for a UV window centred (uc,vc)."""
    c0, r1 = uv_to_px(uc - half_uv, vc - half_uv, pj)  # (u_lo -> col0), (v_lo -> row1/bottom)
    c1, r0 = uv_to_px(uc + half_uv, vc + half_uv, pj)
    return [int(round(c0)), int(round(r0)), int(round(c1)), int(round(r1))]


def crop(img, bbox, shrink=0):
    x0, y0, x1, y1 = [int(round(v)) for v in bbox]
    x0, y0 = max(0, x0 + shrink), max(0, y0 + shrink)
    x1, y1 = min(img.shape[1], x1 - shrink), min(img.shape[0], y1 - shrink)
    return img[y0:y1, x0:x1]


# ----------------------------------------------------------------- compositing
def build_composite(piece_imgs, pieces, shape, lead=0.006):
    """Place each piece image into its dest bbox; fill the rest with flat dark lead."""
    out = np.full((shape[0], shape[1], 3), lead, np.float64)
    for pimg, p in zip(piece_imgs, pieces):
        x0, y0, x1, y1 = [int(round(v)) for v in p["dest_bbox_px"]]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(shape[1], x1), min(shape[0], y1)
        h, w = y1 - y0, x1 - x0
        out[y0:y1, x0:x1] = cv2.resize(pimg.astype(np.float32), (w, h),
                                       interpolation=cv2.INTER_AREA).astype(np.float64)
    return out


def piece_masks(pieces, shape, erode=EROOD):
    masks = []
    for p in pieces:
        x0, y0, x1, y1 = [int(round(v)) for v in p["dest_bbox_px"]]
        m = np.zeros(shape[:2], bool)
        m[max(0, y0 + erode):min(shape[0], y1 - erode),
          max(0, x0 + erode):min(shape[1], x1 - erode)] = True
        masks.append(m)
    return masks


def union(masks):
    u = np.zeros_like(masks[0])
    for m in masks:
        u |= m
    return u


# ----------------------------------------------------------------- gains
def oracle_gain(pred, truth, mask):
    """Per-channel least-squares gain g minimising ||g*pred - truth|| on mask.
    CHEATING (uses RENDER B) -- reported only as an attribution ceiling."""
    g = np.ones(3)
    for c in range(3):
        p, t = pred[mask][:, c], truth[mask][:, c]
        d = float((p * p).sum())
        g[c] = float((p * t).sum() / d) if d > 1e-9 else 1.0
    return g


def mae255(a, b, mask):
    da = np.abs(lin_to_srgb(np.clip(a, 0, 1)) - lin_to_srgb(np.clip(b, 0, 1)))
    return float(da[mask].mean() * 255)


# ----------------------------------------------------------------- per material
def run_material(sample_dir, out_dir):
    meta = json.load(open(os.path.join(sample_dir, "meta.json")))
    recipe = meta["recipe"]
    gclass = CLASS_MAP[recipe]
    pj = meta["projection"]
    pieces = meta["pieces"]
    ev1 = meta["lighting"]["IBL_1"]["ev"]
    variants = meta["lighting"]["IBL_2_variants"]

    A = load_exr(os.path.join(sample_dir, "renderA_photo_linear.exr"))
    C = load_exr(os.path.join(sample_dir, "renderC_photo_linear.exr"))
    gtT = load_exr(os.path.join(sample_dir, "gt_T.exr"))
    shape = A.shape

    # 1. extract T,h,L from RENDER A (oracle class), native RENDER-A pixel space
    m = extract.extract_maps(A, gclass, mark_region="none")
    T, h, L = m["T"], m["h"], m["L"]
    L_mean = L.reshape(-1, 3).mean(0)  # <L_A>: RENDER A's recovered backlight (RGB)

    # relit material appearance under illuminant I: render(T,h,I) = I*T*(h+(1-h)*1) = I*T
    # (flat backlight B=1, so haze folds out). We keep h for provenance only.
    masks = piece_masks(pieces, shape)
    umask = union(masks)

    # extractor T-accuracy vs authored gt_T over the sampled piece source regions
    # (context for the fidelity result: raw copies TRUE pixels, relit relies on T).
    src_masks = [np.zeros(shape[:2], bool) for _ in pieces]
    for sm, p in zip(src_masks, pieces):
        x0, y0, x1, y1 = [int(round(v)) for v in p["src_bbox_px"]]
        sm[max(0, y0 + EROOD):max(0, y1 - EROOD), max(0, x0 + EROOD):max(0, x1 - EROOD)] = True
    smask = union(src_masks)
    T_mae = float(np.abs(T - gtT)[smask].mean())

    results = {"recipe": recipe, "glass_class": gclass, "L_mean": L_mean.tolist(),
               "T_mae_vs_authored": T_mae, "variants": {}}

    # --- assembly-model control (under IBL_1): raw-copy composite vs RENDER C.
    raw_pieces_C = [crop(A, p["src_bbox_px"]) for p in pieces]
    comp_raw_C = build_composite(raw_pieces_C, pieces, shape)
    relit_pieces_C = [L_mean * crop(T, p["src_bbox_px"]) for p in pieces]  # I1_hat = <L_A>
    comp_relit_C = build_composite(relit_pieces_C, pieces, shape)
    results["assembly_control_IBL1"] = {
        "raw_copy_vs_C_mae255": mae255(comp_raw_C, C, umask),
        "relit_vs_C_mae255": mae255(comp_relit_C, C, umask),
        "note": ("raw-copy vs C ~ pure compositing-geometry error (should be tiny); "
                 "relit vs C adds extractor error + the intentional envelope flattening "
                 "under matched lighting"),
    }

    # --- relight fidelity: composite vs RENDER B, per IBL_2 variant
    panels = {}
    for var in variants:
        ev2 = var["ev"]
        gEV = 2.0 ** (ev2 - ev1)
        B = load_exr(os.path.join(sample_dir, f"renderB_{var['name']}_photo_linear.exr"))

        # honest illuminant for IBL_2 and raw EV match
        I2_hat = L_mean * gEV
        raw_unit = [crop(A, p["src_bbox_px"]) for p in pieces]        # appearance under IBL_1
        T_unit = [crop(T, p["src_bbox_px"]) for p in pieces]          # intrinsic

        comp_raw = build_composite([r * gEV for r in raw_unit], pieces, shape)
        comp_relit = build_composite([I2_hat * t for t in T_unit], pieces, shape)

        # oracle-global-gain ceiling (attribution; uses B -> cheating, labelled)
        g_raw = oracle_gain(build_composite(raw_unit, pieces, shape), B, umask)
        g_relit = oracle_gain(build_composite(T_unit, pieces, shape), B, umask)
        comp_raw_orc = build_composite([r * g_raw for r in raw_unit], pieces, shape)
        comp_relit_orc = build_composite([t * g_relit for t in T_unit], pieces, shape)

        results["variants"][var["name"]] = {
            "ev2": ev2, "gEV": gEV, "I2_hat": I2_hat.tolist(),
            "raw_honest_mae255": mae255(comp_raw, B, umask),
            "relit_honest_mae255": mae255(comp_relit, B, umask),
            "raw_oracle_gain_mae255": mae255(comp_raw_orc, B, umask),
            "relit_oracle_gain_mae255": mae255(comp_relit_orc, B, umask),
            "oracle_g_relit": g_relit.tolist(),
        }
        panels[var["name"]] = (B, comp_relit, comp_raw)

    # 2. DRAG TEST -- 9 UV source positions, luminance CV vs grain floor
    results["drag"] = drag_test(A, T, gtT, L_mean, pj, meta, variants[0], ev1)

    # 3. panels
    make_panels(out_dir, recipe, panels, A, T, gtT, L_mean, pj, meta, variants[0], ev1)
    return results


def drag_test(A, T, gtT, L_mean, pj, meta, var, ev1):
    """Re-source a single piece window from a 3x3 grid of UV positions; report the
    dispersion (luminance CV; Lab dE to centroid) of the piece-mean across the 9,
    for RAW (photo under IBL_1, EV-matched), RELIT (I2_hat*T), and the GRAIN FLOOR
    (authored gt_T -- the irreducible texture variation). Win: relit ~ grain, raw high."""
    gEV = 2.0 ** (var["ev"] - ev1)
    I2_hat = L_mean * gEV
    s = meta["layout"]["piece_half"]
    half_uv = 2 * s  # UV half-width of a piece window
    centers = np.linspace(pj["u_lo"] + half_uv + 0.01, pj["u_hi"] - half_uv - 0.01, 3)
    raw_means, relit_means, grain_means = [], [], []
    for vc in centers:
        for uc in centers:
            bb = uv_window_bbox(uc, vc, half_uv, pj)
            a = crop(A, bb, shrink=EROOD)
            t = crop(T, bb, shrink=EROOD)
            g = crop(gtT, bb, shrink=EROOD)
            raw_means.append((a * gEV).reshape(-1, 3).mean(0))
            relit_means.append((I2_hat * t).reshape(-1, 3).mean(0))
            grain_means.append(g.reshape(-1, 3).mean(0))

    def disp(means):
        means = np.array(means)
        Y = lum(means)
        cv = float(Y.std() / (Y.mean() + 1e-9))
        lab = to_lab(means[None])[0]  # Nx3 via 1-row image
        de = float(np.sqrt(((lab - lab.mean(0)) ** 2).sum(-1)).mean())
        return {"lum_cv": cv, "lab_dE": de}

    return {"n_positions": len(raw_means),
            "raw": disp(raw_means), "relit": disp(relit_means), "grain_floor": disp(grain_means)}


def label(img_srgb_u8, text):
    im = Image.fromarray(img_srgb_u8)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(text), 16], fill=(0, 0, 0))
    d.text((4, 2), text, fill=(255, 255, 90))
    return np.asarray(im)


def show(lin, sz=300):
    a = (np.clip(lin_to_srgb(np.clip(lin, 0, 1)), 0, 1) * 255).astype(np.uint8)
    return cv2.resize(a, (sz, sz), interpolation=cv2.INTER_AREA)


def make_panels(out_dir, recipe, panels, A, T, gtT, L_mean, pj, meta, var, ev1):
    os.makedirs(out_dir, exist_ok=True)
    # assembly panel: truth | relit | raw for the headline IBL_2 variant
    vname = list(panels.keys())[0]
    B, relit, raw = panels[vname]
    row = np.concatenate([
        label(show(B), f"RENDER B truth ({vname})"),
        label(show(relit), "relit composite"),
        label(show(raw), "raw-copy composite"),
    ], axis=1)
    Image.fromarray(row).save(os.path.join(out_dir, f"panel_{recipe}.jpg"), quality=90)

    # drag strip: one piece at 9 positions, raw row vs relit row vs grain row
    gEV = 2.0 ** (var["ev"] - ev1)
    I2_hat = L_mean * gEV
    s = meta["layout"]["piece_half"]
    half_uv = 2 * s
    centers = np.linspace(pj["u_lo"] + half_uv + 0.01, pj["u_hi"] - half_uv - 0.01, 3)
    raw_row, relit_row, grain_row = [], [], []
    for vc in centers:
        for uc in centers:
            bb = uv_window_bbox(uc, vc, half_uv, pj)
            raw_row.append(show(crop(A, bb) * gEV, 90))
            relit_row.append(show(I2_hat * crop(T, bb), 90))
            grain_row.append(show(crop(gtT, bb), 90))
    strip = np.concatenate([
        label(np.concatenate(raw_row, 1), "raw @9 positions"),
        label(np.concatenate(relit_row, 1), "relit @9 positions"),
        label(np.concatenate(grain_row, 1), "grain floor (authored T) @9"),
    ], axis=0)
    Image.fromarray(strip).save(os.path.join(out_dir, f"drag_{recipe}.jpg"), quality=90)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="assembled_data")
    ap.add_argument("--out", default="results/assembled")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    all_results = {}
    for name in sorted(os.listdir(args.data)):
        d = os.path.join(args.data, name)
        if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "meta.json")):
            continue
        print(f"== {name} ==")
        r = run_material(d, args.out)
        all_results[r["recipe"]] = r
        print(json.dumps({k: v for k, v in r.items() if k != "L_mean"}, indent=1)[:1200])
    with open(os.path.join(args.out, "metrics.json"), "w") as f:
        json.dump(all_results, f, indent=2)
    print("wrote", os.path.join(args.out, "metrics.json"))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
