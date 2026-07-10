#!/usr/bin/env python3
"""SUNCATCHER BENCHMARK -- report 013.

The first end-to-end product test on REAL assets: the app's tutorial project is a
ground-truth-ish pair. `frontend/public/assets/orange-pattern.jpg` is a PHOTO of a
real physical stained-glass suncatcher (an orange with three green leaves) hanging
backlit in a window. `green.png` / `orange.png` are photos of the raw hammered
cathedral glass tiles it was (nominally) cut from. The tutorial's GT polygons
(`frontend/src/components/Tutorial/types.ts`) are drawn ON the pattern photo, so
they are pixel-aligned to the real object by construction.

We reimplement the app's per-piece compositing (ResultPanel.PieceOverlay) in two
conditions and ask whether de-light+relight makes the preview a more COHERENT
object than raw pixel-copy:

  a. RAW-COPY  (current app): copy sheet pixels straight into the piece polygon.
  b. RELIT     : run the FIXED classical extractor (extract.py, report 009) on
                 each sheet -> intrinsic transmittance T; render illum * T (haze
                 term h~0 for cathedral, plain bright backdrop B=1).

PROVENANCE / HONESTY (confirmed by the maintainer):
  * The pattern photo was NOT shot from the same physical glass as the sheet
    photos -- different glass, and the reference carries its OWN baked window
    light. So ABSOLUTE per-piece color vs the reference is NOT an accuracy claim;
    it is reported only as "style distance", or ignored.
  * PRIMARY metric is CROSS-PIECE CONSISTENCY + LIGHTING-POSITION SENSITIVITY,
    which need no true reference: pieces cut from ONE sheet should agree in color
    after de-lighting; raw-copy inherits each region's local backlight and should
    disagree. Same piece sampled from a bright vs dark sheet region: raw shifts,
    relit shouldn't.
  * The reference photo's role is a QUALITATIVE realism anchor for the side-by-side
    panel. The global illuminant fit below is PRESENTATION (make the panel
    comparable), not measurement -- and it uses the SAME model for both conditions.

Deviations from the literal app pipeline (documented, both conditions identical):
  * DEFAULT_PROJECT.pieces is empty -- the tutorial builds piece transforms
    interactively, so no transform is stored. We parse the GT polygons and
    SYNTHESIZE transforms: each piece samples a distinct region of its sheet's
    glass interior (auto-detected tile bbox, eroded off the wood frame / label /
    sill reflection). This mirrors an artist spreading pieces across a sheet.
  * We sample the glass INTERIOR only (the app's literal default transform centers
    the piece on the full sheet photo incl. frame+background; that is a strictly
    worse raw-copy and not the interesting comparison).
  * Scale is chosen so each piece occupies ~<half the interior, leaving room to
    translate it for the position-sensitivity test. rotation=0.
"""
import json
import os
import re
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import extract as ex  # noqa: E402  (uses srgb_to_lin, lin_to_srgb, load_linear, extract_maps)

PATTERN = os.path.join(ROOT, "frontend/public/assets/orange-pattern.jpg")
GREEN = os.path.join(ROOT, "frontend/public/assets/green.png")
ORANGE = os.path.join(ROOT, "frontend/public/assets/orange.png")
TUT_TYPES = os.path.join(ROOT, "frontend/src/components/Tutorial/types.ts")
OUT = os.path.join(HERE, "results/suncatcher")

SHEET_SIZE = 1400   # extractor working resolution (max dim) for the sheets
GLASS_CLASS = "cathedral-clear"  # both sheets are hammered cathedral (see report)
FIT_FRAC = 0.45     # a piece's sampled sheet extent <= FIT_FRAC * interior extent


# --------------------------------------------------------------------------
# 1. Parse the GT polygons out of the TS file (hand-rolled regex, documented).
#    We extract each `export const GT_PIECE_N: ... = [ [x,y], ... ];` block and
#    read the numeric pairs. No JS engine needed -- the literals are plain arrays.
# --------------------------------------------------------------------------
def parse_gt_polygons(path):
    src = open(path).read()
    polys = {}
    for m in re.finditer(r"export const (GT_PIECE_\d+)\s*:\s*\[number, number\]\[\]\s*=\s*\[(.*?)\];", src, re.S):
        name, body = m.group(1), m.group(2)
        pairs = re.findall(r"\[\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\]", body)
        poly = [(float(a), float(b)) for a, b in pairs]
        # first == last in these arrays; drop the closing duplicate if present
        if len(poly) > 1 and poly[0] == poly[-1]:
            poly = poly[:-1]
        polys[name] = np.array(poly, float)
    return polys


def centroid(poly):
    return poly.mean(axis=0)


def bbox(poly):
    return poly[:, 0].min(), poly[:, 1].min(), poly[:, 0].max(), poly[:, 1].max()


# --------------------------------------------------------------------------
# 2. Detect the glass-tile interior of a sheet photo (exclude wood frame,
#    label sticker, sill reflection, and out-of-focus garden background).
#    Largest saturated-colored connected component, then erode inward.
# --------------------------------------------------------------------------
def detect_interior(rgb01, kind):
    r, g, b = rgb01[..., 0], rgb01[..., 1], rgb01[..., 2]
    mx, mn = rgb01.max(-1), rgb01.min(-1)
    sat = (mx - mn) / (mx + 1e-6)
    if kind == "green":
        mask = (g > r + 0.10) & (g > b + 0.10) & (sat > 0.45) & (g > 0.25)
    else:  # orange
        mask = (r > g + 0.18) & (g > b + 0.05) & (sat > 0.55) & (r > 0.5)
    mask = mask.astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, _ = stats[i]
    # erode inward: 8% each side, extra on bottom (sill reflection) + right (label)
    ex_, ey_ = int(0.08 * w), int(0.08 * h)
    x0, y0 = x + ex_, y + ey_
    x1, y1 = x + w - int(0.15 * w), y + h - int(0.17 * h)  # extra R/bottom: label + sill
    return np.array([x0, y0, x1, y1], float)


# --------------------------------------------------------------------------
# 3. Per-sheet material prep: raw linear sheet + extracted intrinsic T (relit
#    material at B=1, h~0). Both live in the same "sheet-work" pixel space
#    (max dim SHEET_SIZE), and share the detected interior bbox.
# --------------------------------------------------------------------------
def prep_sheet(path, kind):
    lin = ex.load_linear(path, None, SHEET_SIZE)          # raw linear RGB, HxWx3
    rgb01 = ex.lin_to_srgb(lin)
    interior = detect_interior(rgb01, kind)
    maps = ex.extract_maps(lin, GLASS_CLASS)
    T, h = maps["T"], maps["h"]
    # relit material at a plain bright backdrop B=1 (cathedral: h~0 -> ~= T)
    relit = T * (h[..., None] + (1 - h[..., None]) * 1.0)
    # pixel-level spatial-flatness diagnostic on the interior: coefficient of
    # variation of luminance (all frequencies) and of a heavily-blurred copy
    # (low-freq = "lighting-scale" only). Shows how much variation de-lighting
    # actually removes, independent of the piece-mean product metric.
    x0, y0, x1, y1 = [int(v) for v in interior]
    def cv(a, lowfreq=False):
        l = (a[y0:y1, x0:x1] * ex.LUM).sum(-1).astype(np.float32)
        if lowfreq:
            l = cv2.GaussianBlur(l, (0, 0), 25)
        return float(l.std() / max(l.mean(), 1e-9))
    flat = {"raw_cv": cv(lin), "relit_cv": cv(relit),
            "raw_lowfreq_cv": cv(lin, True), "relit_lowfreq_cv": cv(relit, True)}
    return {
        "raw": lin, "relit": relit, "interior": interior,
        "h_mean": float(h.mean()), "T_mean": T.reshape(-1, 3).mean(0).tolist(),
        "flatness": flat, "shape": lin.shape[:2],
    }


# --------------------------------------------------------------------------
# 4. Sampling: for a piece polygon + a transform t (sheet-work coord that the
#    polygon centroid maps to) + scale, sample a material image inside the
#    polygon. Returns (rendered_linear canvas region, polygon mask) in a render
#    space scaled from pattern coords by `rs`.
#    Mapping (mirrors ResultPanel.PieceOverlay, rotation=0):
#       glass = t + scale * (P_pattern - centroid)
# --------------------------------------------------------------------------
def sample_piece(material_lin, poly, cen, t, scale, rs):
    """Render one piece into its own bbox canvas at render-scale rs.
    Returns (canvas HxWx3 linear, mask HxW bool, (ox,oy) canvas origin in render px)."""
    x0, y0, x1, y1 = bbox(poly)
    ox, oy = int(np.floor(x0 * rs)), int(np.floor(y0 * rs))
    W = int(np.ceil(x1 * rs)) - ox + 1
    H = int(np.ceil(y1 * rs)) - oy + 1
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    Px = (uu + ox) / rs
    Py = (vv + oy) / rs
    gx = (t[0] + scale * (Px - cen[0])).astype(np.float32)
    gy = (t[1] + scale * (Py - cen[1])).astype(np.float32)
    samp = cv2.remap(material_lin.astype(np.float32), gx, gy,
                     interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    # polygon mask in render space
    mask = np.zeros((H, W), np.uint8)
    pts = np.round((poly * rs - [ox, oy])).astype(np.int32)
    cv2.fillPoly(mask, [pts], 1)
    return samp.astype(np.float64), mask.astype(bool), (ox, oy)


def piece_mean_lin(material_lin, poly, cen, t, scale, erode_px=6):
    """Mean linear RGB inside the (eroded) polygon, sampling at native sheet res
    (rs=1 in pattern px). Erosion drops solder-edge / background-bleed pixels."""
    samp, mask, _ = sample_piece(material_lin, poly, cen, t, scale, rs=1.0)
    if erode_px > 0:
        mask = cv2.erode(mask.astype(np.uint8),
                         np.ones((erode_px, erode_px), np.uint8)).astype(bool)
    px = samp[mask]
    return px.mean(0), px


# --------------------------------------------------------------------------
# 5. Colour helpers (Lab via sRGB uint8; CIE76 dE for dispersion).
# --------------------------------------------------------------------------
def lin_to_lab(lin_rgb):
    srgb = np.clip(ex.lin_to_srgb(np.asarray(lin_rgb, float).reshape(1, 1, 3)), 0, 1)
    u8 = (srgb * 255).astype(np.uint8)
    lab = cv2.cvtColor(u8, cv2.COLOR_RGB2LAB).astype(np.float64).reshape(3)
    lab[0] *= 100.0 / 255.0  # cv2 packs L in 0..255
    lab[1] -= 128.0
    lab[2] -= 128.0
    return lab


def de76(a, b):
    return float(np.linalg.norm(np.asarray(a) - np.asarray(b)))


def dispersion(means_lin):
    """Given a list of piece-mean linear RGBs, return spread of their means, three
    complementary ways so the report is not misled by any single lens:
      * perceptual  : Lab dE76 (mean-to-centroid, max pairwise). Note: dE grows with
        saturation, so a de-lit map that is MORE saturated can score a wider dE for
        the same *relative* variation -- read alongside lum_cv.
      * brightness  : coefficient of variation (std/mean) of linear luminance. This
        is scale/saturation-free -- the cleanest "do regions agree in brightness".
      * hue         : circular std of the Lab hue angle (degrees)."""
    labs = [lin_to_lab(m) for m in means_lin]
    c = np.mean(labs, 0)
    to_c = [de76(l, c) for l in labs]
    pair = [de76(labs[i], labs[j]) for i in range(len(labs)) for j in range(i + 1, len(labs))]
    lums = np.array([float(np.dot(m, ex.LUM)) for m in means_lin])
    lum_cv = float(lums.std() / max(lums.mean(), 1e-9))
    hues = np.array([np.arctan2(l[2], l[1]) for l in labs])
    hue_std_deg = float(np.degrees(np.sqrt(-2 * np.log(max(np.abs(np.mean(np.exp(1j * hues))), 1e-9)))))
    return {"mean_dE_to_centroid": float(np.mean(to_c)),
            "max_pairwise_dE": float(max(pair)) if pair else 0.0,
            "lum_cv": lum_cv, "hue_std_deg": hue_std_deg,
            "labs": [l.tolist() for l in labs]}


# --------------------------------------------------------------------------
# 6. Global illuminant fit (PRESENTATION). Per-channel: material_c*(a_c+b_c*yn)
#    ~= ref_c, least-squares over all piece pixels. Same model both conditions.
#    yn = pattern-y normalised to [0,1] (low-order vertical gradient for the real
#    window's top-to-bottom light falloff).
# --------------------------------------------------------------------------
def fit_illuminant(samples):
    """samples: list of (material_px Nx3, ref_px Nx3, yn Nx1). Returns (a[3],b[3])."""
    mats = np.concatenate([s[0] for s in samples], 0)
    refs = np.concatenate([s[1] for s in samples], 0)
    yns = np.concatenate([s[2] for s in samples], 0).reshape(-1)
    a = np.zeros(3); b = np.zeros(3)
    for c in range(3):
        A = np.stack([mats[:, c], mats[:, c] * yns], 1)
        sol, *_ = np.linalg.lstsq(A, refs[:, c], rcond=None)
        a[c], b[c] = sol
    return a, b


def apply_illuminant(mat_lin, yn, a, b):
    g = a + b * yn[..., None]
    return mat_lin * g


# --------------------------------------------------------------------------
# 7. Transform synthesis + valid-center range for a piece on a sheet.
# --------------------------------------------------------------------------
def sheet_scale(pieces, interior):
    x0, y0, x1, y1 = interior
    regW, regH = x1 - x0, y1 - y0
    s = min(min(FIT_FRAC * regW / (bbox(p)[2] - bbox(p)[0]),
                FIT_FRAC * regH / (bbox(p)[3] - bbox(p)[1])) for p in pieces)
    return float(s)


def valid_center_range(poly, interior, scale):
    x0, y0, x1, y1 = interior
    bx0, by0, bx1, by1 = bbox(poly)
    sx = scale * (bx1 - bx0) / 2.0
    sy = scale * (by1 - by0) / 2.0
    cxlo, cxhi = x0 + sx, x1 - sx
    cylo, cyhi = y0 + sy, y1 - sy
    if cxlo > cxhi:
        cxlo = cxhi = (x0 + x1) / 2
    if cylo > cyhi:
        cylo = cyhi = (y0 + y1) / 2
    return cxlo, cxhi, cylo, cyhi


def grid_centers(rng, nx, ny):
    cxlo, cxhi, cylo, cyhi = rng
    xs = np.linspace(cxlo, cxhi, nx) if nx > 1 else [(cxlo + cxhi) / 2]
    ys = np.linspace(cylo, cyhi, ny) if ny > 1 else [(cylo + cyhi) / 2]
    return [(float(x), float(y)) for y in ys for x in xs]


# --------------------------------------------------------------------------
# 8. Rendering the full-assembly panel in pattern space.
# --------------------------------------------------------------------------
def render_assembly(material_by_piece, order, polys, cens, rs, canvas_wh,
                    yn_full, illum, backdrop_lin):
    a, b = illum
    W, H = canvas_wh
    canvas = backdrop_lin.copy()
    for name in order:
        mat = material_by_piece[name]["mat"]
        t = material_by_piece[name]["t"]
        scale = material_by_piece[name]["scale"]
        samp, mask, (ox, oy) = sample_piece(mat, polys[name], cens[name], t, scale, rs)
        # per-pixel vertical gradient illuminant
        vv = (np.arange(samp.shape[0]) + oy)[:, None] / (H)
        yn = np.clip(vv, 0, 1) * np.ones((1, samp.shape[1]))
        lit = samp * (a + b * yn[..., None])
        # composite
        h, w = mask.shape
        cy0, cx0 = max(0, oy), max(0, ox)
        cy1, cx1 = min(H, oy + h), min(W, ox + w)
        my0, mx0 = cy0 - oy, cx0 - ox
        sub_m = mask[my0:my0 + (cy1 - cy0), mx0:mx0 + (cx1 - cx0)]
        sub_l = lit[my0:my0 + (cy1 - cy0), mx0:mx0 + (cx1 - cx0)]
        region = canvas[cy0:cy1, cx0:cx1]
        region[sub_m] = sub_l[sub_m]
        canvas[cy0:cy1, cx0:cx1] = region
    # draw solder (dark lead lines) on polygon edges
    srgb = (np.clip(ex.lin_to_srgb(canvas), 0, 1) * 255).astype(np.uint8)
    for name in order:
        pts = np.round(polys[name] * rs).astype(np.int32)
        cv2.polylines(srgb, [pts], True, (28, 26, 24), max(2, int(3 * rs / 0.3)), cv2.LINE_AA)
    return srgb


def main():
    os.makedirs(OUT, exist_ok=True)
    polys = parse_gt_polygons(TUT_TYPES)
    assign = {"GT_PIECE_1": "orange", "GT_PIECE_2": "green",
              "GT_PIECE_3": "green", "GT_PIECE_4": "green"}
    labels = {"GT_PIECE_1": "orange-slice", "GT_PIECE_2": "leaf-R",
              "GT_PIECE_3": "leaf-L", "GT_PIECE_4": "leaf-far-L"}
    cens = {n: centroid(p) for n, p in polys.items()}

    sheets = {"green": prep_sheet(GREEN, "green"), "orange": prep_sheet(ORANGE, "orange")}
    print("sheet prep:", {k: {"h_mean": round(v["h_mean"], 3),
                              "T_mean": [round(x, 2) for x in v["T_mean"]],
                              "interior": [int(z) for z in v["interior"]]}
                          for k, v in sheets.items()})

    # ---- scales + placements per sheet ----
    by_sheet = {"green": [n for n in polys if assign[n] == "green"],
                "orange": [n for n in polys if assign[n] == "orange"]}
    scales = {s: sheet_scale([polys[n] for n in by_sheet[s]], sheets[s]["interior"])
              for s in sheets}
    # assembly placement: spread same-sheet pieces across distinct interior columns
    place = {}
    for s, names in by_sheet.items():
        rng_all = [valid_center_range(polys[n], sheets[s]["interior"], scales[s]) for n in names]
        nx = len(names)
        for i, n in enumerate(names):
            cxlo, cxhi, cylo, cyhi = rng_all[i]
            fx = (i + 0.5) / nx
            cx = cxlo + fx * (cxhi - cxlo)
            cy = (cylo + cyhi) / 2
            place[n] = (float(cx), float(cy))

    # ================= METRIC 1: cross-piece consistency (green, 3 leaves) ======
    consistency = {}
    for s, names in by_sheet.items():
        if len(names) < 2:
            continue
        raw_means, relit_means = [], []
        for n in names:
            rm, _ = piece_mean_lin(sheets[s]["raw"], polys[n], cens[n], place[n], scales[s])
            lm, _ = piece_mean_lin(sheets[s]["relit"], polys[n], cens[n], place[n], scales[s])
            raw_means.append(rm); relit_means.append(lm)
        consistency[s] = {"n_pieces": len(names),
                          "raw": dispersion(raw_means),
                          "relit": dispersion(relit_means)}

    # ============ METRIC 2: lighting-position sensitivity (per piece) ===========
    position = {}
    for n in polys:
        s = assign[n]
        rng = valid_center_range(polys[n], sheets[s]["interior"], scales[s])
        centers = grid_centers(rng, 3, 3)
        raw_means = [piece_mean_lin(sheets[s]["raw"], polys[n], cens[n], c, scales[s])[0] for c in centers]
        relit_means = [piece_mean_lin(sheets[s]["relit"], polys[n], cens[n], c, scales[s])[0] for c in centers]
        position[n] = {"label": labels[n], "sheet": s, "n_positions": len(centers),
                       "raw": dispersion(raw_means), "relit": dispersion(relit_means)}

    # ============ METRIC 3: style-distance vs reference (NOT accuracy) ==========
    # reference piece means from the pattern photo; also collect pixels for the
    # illuminant fit (both conditions) and yn.
    pat_lin = ex.load_linear(PATTERN, None, max(Image.open(PATTERN).size))  # full-res linear
    PH, PW = pat_lin.shape[:2]
    fit_raw, fit_relit = [], []
    style = {}
    ref_means = {}
    for n in polys:
        s = assign[n]
        # reference pixels inside eroded polygon (pattern space, rs=1 in pattern px)
        mask = np.zeros((PH, PW), np.uint8)
        cv2.fillPoly(mask, [np.round(polys[n]).astype(np.int32)], 1)
        mask = cv2.erode(mask, np.ones((9, 9), np.uint8)).astype(bool)
        ref_px = pat_lin[mask]
        ys = np.where(mask)[0].astype(np.float64) / PH
        ref_means[n] = ref_px.mean(0)
        raw_m, raw_px = piece_mean_lin(sheets[s]["raw"], polys[n], cens[n], place[n], scales[s])
        relit_m, relit_px = piece_mean_lin(sheets[s]["relit"], polys[n], cens[n], place[n], scales[s])
        # subsample piece pixels to match ref count for a balanced fit
        k = min(len(raw_px), len(relit_px), len(ref_px))
        ridx = np.random.RandomState(0).choice(len(ref_px), k, replace=False)
        rawidx = np.random.RandomState(1).choice(len(raw_px), k, replace=False)
        relidx = np.random.RandomState(2).choice(len(relit_px), k, replace=False)
        ynk = ys[ridx].reshape(-1, 1)
        fit_raw.append((raw_px[rawidx], ref_px[ridx], ynk))
        fit_relit.append((relit_px[relidx], ref_px[ridx], ynk))
        style[n] = {"label": labels[n], "sheet": s,
                    "ref_mean_lab": lin_to_lab(ref_means[n]).tolist(),
                    "raw_mean_lab": lin_to_lab(raw_m).tolist(),
                    "relit_mean_lab": lin_to_lab(relit_m).tolist()}

    illum_raw = fit_illuminant(fit_raw)
    illum_relit = fit_illuminant(fit_relit)

    # style dE after applying the fitted illuminant to the piece MEAN (yn=centroid y)
    for n in polys:
        s = assign[n]
        cyn = cens[n][1] / PH
        raw_m, _ = piece_mean_lin(sheets[s]["raw"], polys[n], cens[n], place[n], scales[s])
        relit_m, _ = piece_mean_lin(sheets[s]["relit"], polys[n], cens[n], place[n], scales[s])
        raw_lit = raw_m * (illum_raw[0] + illum_raw[1] * cyn)
        relit_lit = relit_m * (illum_relit[0] + illum_relit[1] * cyn)
        style[n]["raw_dE_to_ref"] = de76(lin_to_lab(raw_lit), lin_to_lab(ref_means[n]))
        style[n]["relit_dE_to_ref"] = de76(lin_to_lab(relit_lit), lin_to_lab(ref_means[n]))

    # ================= VISUAL PANEL =================
    rs = 1000.0 / PH
    CW, CH = int(round(PW * rs)), int(round(PH * rs))
    yn_full = (np.arange(CH)[:, None] / CH) * np.ones((1, CW))
    warm_bg = np.array(ex.srgb_to_lin(np.array([0.90, 0.89, 0.86]))).reshape(1, 1, 3) * np.ones((CH, CW, 3))
    matp = {}
    for n in polys:
        s = assign[n]
        matp[n] = {"mat": None, "t": place[n], "scale": scales[s]}
    order = list(polys.keys())
    matp_raw = {n: {**matp[n], "mat": sheets[assign[n]]["raw"]} for n in polys}
    matp_relit = {n: {**matp[n], "mat": sheets[assign[n]]["relit"]} for n in polys}
    raw_panel = render_assembly(matp_raw, order, polys, cens, rs, (CW, CH), yn_full, illum_raw, warm_bg)
    relit_panel = render_assembly(matp_relit, order, polys, cens, rs, (CW, CH), yn_full, illum_relit, warm_bg)
    ref_panel = np.asarray(Image.open(PATTERN).convert("RGB").resize((CW, CH), Image.LANCZOS))

    def labeled(img, txt):
        im = Image.fromarray(img).copy()
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 12 + 9 * len(txt), 26], fill=(0, 0, 0))
        d.text((6, 6), txt, fill=(255, 230, 90))
        return np.asarray(im)

    gap = np.full((CH, 12, 3), 255, np.uint8)
    panel = np.concatenate([labeled(ref_panel, "REFERENCE (real photo)"), gap,
                            labeled(raw_panel, "RAW-COPY"), gap,
                            labeled(relit_panel, "RELIT (de-light+relight)")], 1)
    Image.fromarray(panel).save(os.path.join(OUT, "panel_assembly.jpg"), quality=90)

    # worst-piece closeup: piece with largest raw position-sensitivity
    worst = max(position, key=lambda n: position[n]["raw"]["max_pairwise_dE"])
    save_worst_closeup(worst, labels[worst], polys, cens, place, scales, sheets,
                       assign, illum_raw, illum_relit, ref_panel, rs, PH)

    # ================= metrics.json + verdict =================
    def agg(metric, cond, key="mean_dE_to_centroid"):
        vals = [metric[n][cond][key] for n in metric]
        return float(np.mean(vals))
    metrics = {
        "provenance": "Pattern photo is DIFFERENT physical glass than the sheet photos, "
                      "with its own baked window light. Absolute color vs reference is "
                      "style-distance, not accuracy. Primary = consistency + position-sensitivity.",
        "config": {"sheet_size": SHEET_SIZE, "glass_class": GLASS_CLASS,
                   "fit_frac": FIT_FRAC, "scales": scales,
                   "illum_raw": {"gain": illum_raw[0].tolist(), "vgrad": illum_raw[1].tolist()},
                   "illum_relit": {"gain": illum_relit[0].tolist(), "vgrad": illum_relit[1].tolist()},
                   "h_mean": {s: sheets[s]["h_mean"] for s in sheets}},
        "sheet_interior_flatness": {s: sheets[s]["flatness"] for s in sheets},
        "metric1_cross_piece_consistency": consistency,
        "metric2_position_sensitivity": position,
        "metric2_aggregate": {
            "raw_mean_dE": agg(position, "raw"), "relit_mean_dE": agg(position, "relit"),
            "raw_lum_cv": agg(position, "raw", "lum_cv"), "relit_lum_cv": agg(position, "relit", "lum_cv"),
            "raw_hue_std_deg": agg(position, "raw", "hue_std_deg"), "relit_hue_std_deg": agg(position, "relit", "hue_std_deg")},
        "metric3_style_distance": style,
        "worst_piece": worst,
    }
    with open(os.path.join(OUT, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    print("\n==== SHEET INTERIOR FLATNESS (pixel-level; lower=flatter) ====")
    for s in sheets:
        f = sheets[s]["flatness"]
        print(f"  {s}: CV raw {f['raw_cv']:.3f} -> relit {f['relit_cv']:.3f} | "
              f"lowfreq-CV raw {f['raw_lowfreq_cv']:.3f} -> relit {f['relit_lowfreq_cv']:.3f}")
    print("\n==== CONSISTENCY (green sheet, 3 leaves) ====")
    for s, d in consistency.items():
        print(f"  {s}: dE raw {d['raw']['mean_dE_to_centroid']:.2f} -> relit {d['relit']['mean_dE_to_centroid']:.2f} | "
              f"lumCV raw {d['raw']['lum_cv']:.3f} -> relit {d['relit']['lum_cv']:.3f} | "
              f"hue raw {d['raw']['hue_std_deg']:.1f} -> relit {d['relit']['hue_std_deg']:.1f}")
    print("\n==== POSITION-SENSITIVITY (per piece, 9 sheet positions) ====")
    for n, d in position.items():
        print(f"  {d['label']:12s}[{d['sheet']}]: dE raw {d['raw']['mean_dE_to_centroid']:.2f} -> relit {d['relit']['mean_dE_to_centroid']:.2f} | "
              f"lumCV raw {d['raw']['lum_cv']:.3f} -> relit {d['relit']['lum_cv']:.3f} | "
              f"hue raw {d['raw']['hue_std_deg']:.1f} -> relit {d['relit']['hue_std_deg']:.1f}")
    a = metrics["metric2_aggregate"]
    print(f"  AGG: dE {a['raw_mean_dE']:.2f}->{a['relit_mean_dE']:.2f} | "
          f"lumCV {a['raw_lum_cv']:.3f}->{a['relit_lum_cv']:.3f} | "
          f"hue {a['raw_hue_std_deg']:.1f}->{a['relit_hue_std_deg']:.1f}")
    print("\n==== STYLE-DISTANCE vs reference (NOT accuracy) ====")
    for n, d in style.items():
        print(f"  {d['label']:12s}: raw dE {d['raw_dE_to_ref']:.1f} | relit dE {d['relit_dE_to_ref']:.1f}")
    print("\nworst piece (raw position-sensitivity):", worst, labels[worst])
    print("wrote", os.path.join(OUT, "metrics.json"))


def save_worst_closeup(worst, label, polys, cens, place, scales, sheets,
                       assign, illum_raw, illum_relit, ref_panel, rs, PH):
    s = assign[worst]
    rng = valid_center_range(polys[worst], sheets[s]["interior"], scales[s])
    centers = grid_centers(rng, 3, 3)
    tiles_raw, tiles_relit = [], []
    for c in centers:
        for mat, illum, bucket in [(sheets[s]["raw"], illum_raw, tiles_raw),
                                   (sheets[s]["relit"], illum_relit, tiles_relit)]:
            samp, mask, (ox, oy) = sample_piece(mat, polys[worst], cens[worst], c, scales[s], rs=1.0)
            cyn = cens[worst][1] / PH
            lit = samp * (illum[0] + illum[1] * cyn)
            srgb = (np.clip(ex.lin_to_srgb(lit), 0, 1) * 255).astype(np.uint8)
            srgb[~mask] = 245
            bucket.append(cv2.resize(srgb, (180, int(180 * srgb.shape[0] / srgb.shape[1]))))
    Hs = max(t.shape[0] for t in tiles_raw + tiles_relit)

    def row(tiles):
        return np.concatenate([np.pad(t, ((0, Hs - t.shape[0]), (0, 6), (0, 0)),
                                      constant_values=245) for t in tiles], 1)
    rr = labeled_row(row(tiles_raw), "RAW-COPY, same piece @ 9 sheet positions")
    lr = labeled_row(row(tiles_relit), "RELIT, same piece @ 9 sheet positions")
    W = max(rr.shape[1], lr.shape[1])
    rr = np.pad(rr, ((0, 0), (0, W - rr.shape[1]), (0, 0)), constant_values=255)
    lr = np.pad(lr, ((0, 0), (0, W - lr.shape[1]), (0, 0)), constant_values=255)
    out = np.concatenate([rr, np.full((8, W, 3), 255, np.uint8), lr], 0)
    Image.fromarray(out).save(os.path.join(OUT, f"closeup_worst_{worst}.jpg"), quality=92)


def labeled_row(img, txt):
    im = Image.fromarray(img)
    hdr = Image.new("RGB", (img.shape[1], 22), (0, 0, 0))
    d = ImageDraw.Draw(hdr); d.text((5, 5), txt, fill=(255, 230, 90))
    return np.concatenate([np.asarray(hdr), np.asarray(im)], 0)


if __name__ == "__main__":
    main()
