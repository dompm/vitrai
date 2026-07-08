#!/usr/bin/env python3
"""Single-photo glass material extraction (research prototype, Track A: classical).

From ONE casual photo of a glass sheet held against a light source, estimate:
  T(x)  per-pixel RGB transmittance (glass color, illumination removed)
  h(x)  haze / diffusion fraction (1 = milky opal, 0 = clear glass showing background)

Model
-----
Linearized photo:  I(x) = L(x) * [ h(x)*T(x) + (1-h(x))*T(x)*B(x) ] + S(x)
  L(x)  backlight illumination field (smooth luminance envelope x low-order chroma field)
  B(x)  background radiance relative to L (lawn/sky seen through clear regions)
  S(x)  additive front-surface specular sheen
The class prior (--glass-class) resolves the dark-pixel ambiguity:
  wispy / cathedral-clear : dark low-texture pixels = background through clear glass -> high T, low h
  dark-opaque             : dark pixels = the glass itself -> low T, high h
  opalescent              : everything diffuses; h has a high floor

Pipeline
--------
 1. crop -> downscale -> sRGB-linearize
 2. specular suppression: morphological top-hat highlights, inpaint (Telea)
 3. illumination L: smooth percentile-envelope of luminance x weighted-quadratic chroma
    field fitted to milky pixels only (so backlight color gradients are removed but
    glass tint, which follows glass structure, is not)
 4. R = I / L
 5. grease-pencil / marking removal: black-hat strokes on R, inpaint
 6. h from local statistics of R (brightness, local relative texture, saturation),
    class-modulated, edge-aware smoothed (guided filter)
 7. T assembly: T = R where the glass color is directly observed (milky or bright
    background), diffusion-filled elsewhere (background content must not enter T)
 8. metrics: self-reconstruction I_hat = L*T*(h + (1-h)*B~), where B~ is the residual
    background restricted to QUARTER resolution -- glass detail misassigned to the
    background layer is lost by the downsampling and shows up as error.

Usage
-----
  extract.py PHOTO [--glass-class C] [--corners x0,y0,x1,y1] [--out DIR] [--size N]
  extract.py FOLDER --out DIR            # batch mode; per-file options may come from
                                         # a manifest.json in the folder:
                                         # {"file.jpg": {"class_override": "wispy", "corners": [..]}}
  Class defaults to the `claude` CLI classifier (multiple choice; see vlm_classify.py);
  a manifest `class_override` or --class beats it, --no-vlm disables it.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

CLASSES = ("opalescent", "wispy", "cathedral-clear", "dark-opaque")
LUM = np.array([0.2126, 0.7152, 0.0722])

# Absolute-transmittance anchor (report 003). Per-image exposure is unknown, so
# the split between the illumination scale L and the transmittance scale T is a
# gauge the photo does not fix -- and the self-recon metric is blind to it (L
# absorbs whatever T gives up). We pin the gauge with a class prior: (percentile,
# target) = "the clearest glass of this class transmits about `target`". Chosen
# so dark-opaque comes out near-black (its p99->0.97 stretch was the visible bug)
# while the near-clear classes are essentially unchanged (target ~= old 0.97).
T_ANCHOR = {
    "cathedral-clear": (99, 0.95),
    "wispy": (99, 0.95),
    "opalescent": (99, 0.80),   # milky: brightest is translucent, not clear
    "dark-opaque": (99, 0.10),  # brightest fleck transmits ~10%; median ends near-black
}


# ---------------------------------------------------------------- basic ops
def srgb_to_lin(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055)


def lum(a):
    # explicit sum (not `@`): Accelerate-BLAS matmul emits spurious FP warnings on macOS
    return a[..., 0] * LUM[0] + a[..., 1] * LUM[1] + a[..., 2] * LUM[2]


def gauss(a, sigma):
    return cv2.GaussianBlur(a, (0, 0), sigmaX=float(sigma), borderType=cv2.BORDER_REPLICATE)


def box(a, r):
    return cv2.boxFilter(a, -1, (2 * r + 1, 2 * r + 1), borderType=cv2.BORDER_REPLICATE)


def smoothstep(x, lo, hi):
    t = np.clip((x - lo) / max(hi - lo, 1e-9), 0, 1)
    return t * t * (3 - 2 * t)


def guided_filter(guide, p, r, eps):
    """Edge-aware smoothing of p guided by (grayscale) guide."""
    m_g, m_p = box(guide, r), box(p, r)
    var_g = box(guide * guide, r) - m_g * m_g
    cov = box(guide * p, r) - m_g * m_p
    a = cov / (var_g + eps)
    b = m_p - a * m_g
    return box(a, r) * guide + box(b, r)


def local_std(a, r):
    m = box(a, r)
    return np.sqrt(np.maximum(box(a * a, r) - m * m, 0))


def ellipse(r):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def inpaint_lin(lin, mask, radius=5):
    """cv2.inpaint works on 8-bit; round-trip through sRGB encoding."""
    enc = (lin_to_srgb(np.clip(lin, 0, 1)) * 255).astype(np.uint8)
    out = cv2.inpaint(enc, mask.astype(np.uint8) * 255, radius, cv2.INPAINT_TELEA)
    return srgb_to_lin(out.astype(np.float64) / 255)


def diffusion_fill(img, conf, iters=6):
    """Fill low-confidence pixels from high-confidence neighbours (multi-scale
    normalized convolution). Accepts HxW or HxWx3."""
    squeeze = img.ndim == 2
    if squeeze:
        img = img[..., None]
    filled = img * conf[..., None]
    w = conf.copy()
    sigma = 2.0
    out = None
    for _ in range(iters):
        fw = gauss(filled, sigma)
        if fw.ndim == 2:  # cv2 squeezes HxWx1
            fw = fw[..., None]
        ww = gauss(w, sigma)
        cand = fw / np.maximum(ww[..., None], 1e-6)
        out = cand if out is None else np.where((w > 0.05)[..., None], out, cand)
        sigma *= 2.0
    res = conf[..., None] * img + (1 - conf[..., None]) * out
    return res[..., 0] if squeeze else res


# ------------------------------------------------------------ pipeline steps
def suppress_speculars(lin, glass_class, W):
    """Front-surface sheen. Deliberately conservative: on textured glass most
    'glints' are transmitted lensing that belongs in T, so only near-clipped
    pixels and extreme small-scale outliers are treated as speculars."""
    Y = lum(lin)
    mask = lin.max(axis=-1) > srgb_to_lin(np.array(0.985))  # near-clipped
    if glass_class in ("opalescent", "wispy", "dark-opaque"):
        r = max(2, int(0.012 * W))
        tophat = cv2.morphologyEx(Y.astype(np.float32), cv2.MORPH_TOPHAT, ellipse(r)).astype(np.float64)
        mask |= (tophat > 0.22) & (Y > np.percentile(Y, 85))
    mask = cv2.dilate(mask.astype(np.uint8), ellipse(2)).astype(bool)
    if mask.mean() > 0.15:  # sanity valve: never inpaint a large image fraction
        return lin, np.zeros_like(mask)
    return inpaint_lin(lin, mask, radius=4), mask


def milkiness(rgb_like, r_tex):
    """Score in [0,1]: bright, locally smooth, desaturated -> milky diffuse glass.
    Texture is measured on a median-filtered luminance so that impulse-like
    sparkle (1-3 px glints) does not read as background texture."""
    Y = lum(rgb_like)
    Ym = cv2.medianBlur(np.clip(Y, 0, 4).astype(np.float32), 5).astype(np.float64)
    rel_tex = local_std(Ym, r_tex) / (box(Ym, r_tex) + 0.05)
    smooth = np.exp(-((rel_tex / 0.07) ** 2))
    mx, mn = rgb_like.max(axis=-1), rgb_like.min(axis=-1)
    sat = (mx - mn) / (mx + 1e-6)
    desat = np.exp(-((sat / 0.35) ** 2))
    bright = smoothstep(Y, 0.30, 0.65)
    return bright * smooth * desat


def estimate_illumination(lin, glass_class, W):
    """L = smooth luminance envelope x low-order chroma field.

    The luminance envelope is a large-window high-percentile filter: since T<=1
    and I = L*T, the illumination rides on top of the observed luminance.
    The chroma field is a weighted quadratic polynomial fitted to MILKY pixels
    (they show the illuminant color through a near-neutral diffuser). A quadratic
    cannot follow glass structure, so wispy tint survives in T while sky/sunset
    color gradients are removed. For cathedral-clear / dark-opaque the sheet is
    assumed uniformly tinted, the illuminant is taken as neutral and all color
    stays in T (single-photo tint/illuminant ambiguity, resolved by class prior).
    """
    Y = lum(lin)
    H_, W_ = Y.shape

    # --- luminance envelope (percentile filter on a downsampled grid)
    from scipy.ndimage import percentile_filter
    s = 8
    small = cv2.resize(Y.astype(np.float32), (max(W_ // s, 8), max(H_ // s, 8)),
                       interpolation=cv2.INTER_AREA).astype(np.float64)
    # p95/0.35 chosen by sweep (report 002): higher percentile pushes glass
    # structure out of the envelope into T (+21% T contrast on the wispy case)
    # at negligible cost in residual illumination on the easy case
    d = max(small.shape)
    win = max(5, int(0.35 * d))
    base = gauss(percentile_filter(small, 95, size=win, mode='nearest'), 0.15 * d)
    # hotspot recovery (report 004): the broad envelope smooths a compact backlight
    # hotspot down, so R = I/L runs hot there and the hotspot leaks into T (blue's
    # cyan patch, red's milder one). A tighter-window, higher-percentile envelope
    # tracks the compact peak; taking the max lifts L only where the tight peak
    # exceeds the broad one -- i.e. on a compact bright blob. Over broad uniform
    # glass the two agree, so glass color is untouched (median L unchanged).
    pw = max(3, int(0.15 * d))
    peak = gauss(percentile_filter(small, 98, size=pw, mode='nearest'), 0.05 * d)
    env = np.maximum(base, peak)
    env = cv2.resize(env.astype(np.float32), (W_, H_), interpolation=cv2.INTER_CUBIC).astype(np.float64)
    env = np.maximum(env, 1e-3)

    # --- chroma field
    chroma = np.ones_like(lin)
    if glass_class in ("opalescent", "wispy"):
        w0 = milkiness(lin / np.maximum(env, 1e-3)[..., None], r_tex=max(2, int(0.006 * W)))
        c = lin / (Y[..., None] + 1e-6)
        s2 = 6
        cs = cv2.resize(c.astype(np.float32), (W_ // s2, H_ // s2), interpolation=cv2.INTER_AREA)
        ws = cv2.resize(w0.astype(np.float32), (W_ // s2, H_ // s2), interpolation=cv2.INTER_AREA)
        ys, xs = np.mgrid[0:cs.shape[0], 0:cs.shape[1]]
        xs = xs / cs.shape[1] - 0.5
        ys = ys / cs.shape[0] - 0.5
        A = np.stack([np.ones_like(xs), xs, ys, xs * xs, ys * ys, xs * ys], -1).reshape(-1, 6)
        wv = np.sqrt(np.maximum(ws.reshape(-1), 1e-4))
        fit = np.zeros((H_ // s2 if False else cs.shape[0], cs.shape[1], 3))
        yf, xf = np.mgrid[0:cs.shape[0], 0:cs.shape[1]]
        for ch in range(3):
            coef, *_ = np.linalg.lstsq(A * wv[:, None], cs[..., ch].reshape(-1) * wv, rcond=None)
            fit[..., ch] = (A * coef).sum(-1).reshape(cs.shape[:2])
        fit = np.clip(fit, 0.4, 2.5)
        chroma = cv2.resize(fit.astype(np.float32), (W_, H_), interpolation=cv2.INTER_CUBIC).astype(np.float64)
        chroma /= lum(chroma)[..., None] + 1e-9  # renormalize: luminance lives in env

    return env[..., None] * chroma


REGION_GRID = {
    "top-left": (0, 0), "top-center": (1, 0), "top-right": (2, 0),
    "middle-left": (0, 1), "center": (1, 1), "middle-right": (2, 1),
    "bottom-left": (0, 2), "bottom-center": (1, 2), "bottom-right": (2, 2),
}


def region_box_mask(region, shape, margin=0.10):
    """3x3 grid cell (+margin) as a boolean mask."""
    H_, W_ = shape
    cx, cy = REGION_GRID[region]
    m = np.zeros(shape, bool)
    x0, x1 = max(0.0, cx / 3 - margin), min(1.0, (cx + 1) / 3 + margin)
    y0, y1 = max(0.0, cy / 3 - margin), min(1.0, (cy + 1) / 3 + margin)
    m[int(y0 * H_):int(y1 * H_), int(x0 * W_):int(x1 * W_)] = True
    return m


def detect_marks(R, W):
    """Global (region-unknown) mark detector: thin dark strokes whose COLOR is
    anomalous. Marking = foreign pigment: chroma deviates from the local glass
    chroma (~0.12 L2 for pencil vs ~0.03 for veins) x stroke-scale black-hat
    darkness. Conservative thresholds: partial stroke coverage and some vein
    false positives (report 002 quantifies); when the mark REGION is known
    (VLM localization / manifest), remove_marks_in_region() is used instead.
    """
    Y = np.clip(lum(R), 0.05, 1.5)
    r = max(3, int(0.014 * W))
    blackhat = cv2.morphologyEx(Y.astype(np.float32), cv2.MORPH_BLACKHAT, ellipse(r)).astype(np.float64)
    chroma = R / (Y[..., None] + 1e-6)
    local_c = box(chroma, max(8, int(0.06 * W)))
    anom = np.sqrt(((chroma - local_c) ** 2).sum(axis=-1))
    mx, mn = R.max(axis=-1), R.min(axis=-1)
    sat = (mx - mn) / (mx + 1e-6)
    score = smoothstep(blackhat, 0.08, 0.16) * smoothstep(anom, 0.075, 0.13)
    mask = (score > 0.4) & (sat < 0.5)
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, ellipse(3)).astype(bool)
    mask = cv2.dilate(mask.astype(np.uint8), ellipse(max(3, int(0.009 * W)))).astype(bool)
    if mask.mean() > 0.10:  # sanity valve
        mask &= score > np.percentile(score[mask], 60)
    return mask


def remove_marks_in_region(R, region, W):
    """Region-targeted mark removal (region from VLM localization / manifest).

    Detect-then-fill proved fragile: score thresholds always leave stroke
    fringes and the fill reconstructs a legible ghost from them. Instead, lift
    EVERY small-scale dark feature inside the region to its morphological
    closing (disk ~2.2% of width): strokes, including their wide faint smudge,
    are removed wholesale; structures larger than the disk (streaks, veins)
    are untouched. Cost: small dark glass flecks inside that one grid cell are
    also lifted -- confined, and preferable to a readable SKU.
    Returns (R_fixed, soft_alpha)."""
    reg = region_box_mask(region, R.shape[:2])
    k = ellipse(max(6, int(0.022 * W)))
    closed = np.stack([cv2.morphologyEx(R[..., c].astype(np.float32), cv2.MORPH_CLOSE, k)
                       for c in range(3)], -1).astype(np.float64)
    Yc, Yr = lum(closed), lum(R)
    gain = np.clip((Yc - Yr) / np.maximum(Yc, 0.05), 0, 1)
    alpha = gauss(smoothstep(gain, 0.05, 0.15) * reg, 2)
    return R + alpha[..., None] * (closed - R), alpha


def estimate_haze(R, glass_class, W):
    """h(x) from local statistics of the illumination-normalized image R."""
    Y = np.clip(lum(R), 0, 2)
    r_tex = max(2, int(0.006 * W))
    m = milkiness(R, r_tex)

    mx, mn = R.max(axis=-1), R.min(axis=-1)
    sat = (mx - mn) / (mx + 1e-6)
    bg_color = 1 - np.exp(-((sat / 0.25) ** 2))  # saturated => background content
    if glass_class == "opalescent":
        h = (0.55 + 0.45 * m) * (1 - 0.9 * bg_color)
    elif glass_class == "wispy":
        h = np.clip(0.05 + 1.1 * m, 0, 1) * (1 - 0.9 * bg_color)
    elif glass_class == "cathedral-clear":
        h = 0.06 + 0.20 * m  # texture is glass relief, not diffusion
    else:  # dark-opaque: dark smooth pixels ARE the glass
        rel_tex = local_std(Y, r_tex) / (box(Y, r_tex) + 0.05)
        smooth = np.exp(-((rel_tex / 0.07) ** 2))
        dark = smoothstep(1 - Y, 0.4, 0.8)
        h = np.clip(0.25 + 0.75 * np.maximum(dark * smooth, 0.4 * m), 0, 1)

    h = guided_filter(Y, h, r=max(4, int(0.02 * W)), eps=3e-3)
    return np.clip(h, 0, 1)


def assemble_T(R, h, glass_class, mark_mask=None):
    """Glass color where directly observed; diffusion-fill where the photo shows
    background instead of glass."""
    Rc = np.clip(R, 0, 1)
    Y = lum(Rc)
    if glass_class == "dark-opaque":
        return Rc, np.ones_like(Y)
    if glass_class == "cathedral-clear":
        # background assumed featureless backlight; relief/lensing stays in T
        return Rc, np.ones_like(Y)
    # wispy / opalescent: trust pixels that are milky OR show a bright, near-
    # neutral background (saturated bright pixels are background content, e.g.
    # lawn -- these classes are near-white glass, so color there is not glass)
    mx, mn = Rc.max(axis=-1), Rc.min(axis=-1)
    sat = (mx - mn) / (mx + 1e-6)
    desat = np.exp(-((sat / 0.35) ** 2))
    conf = np.clip(np.maximum(h, smoothstep(Y, 0.70, 0.92) * desat), 0, 1)
    # sharpen: mid-confidence pixels (wispy structure, h~0.5) used to be
    # blended 50/50 with the smooth fill, washing out contrast (report 001
    # failure 4); trust them fully and only fill real background
    conf = smoothstep(conf, 0.08, 0.50)
    if mark_mask is not None and mark_mask.any():
        conf = np.where(mark_mask, 0.0, conf)
    T = diffusion_fill(Rc, conf)
    return np.clip(T, 0, 1), conf


# ------------------------------------------------------------------ rendering
def render(T, h, illum_rgb, bg=None):
    """out = L_new * T * (h + (1-h)*B); B defaults to 1 (uniform light table)."""
    B = np.ones_like(T) if bg is None else bg
    return illum_rgb * T * (h[..., None] + (1 - h[..., None]) * B)


def reconstruct(L, T, h, R):
    """Self-reconstruction with the residual background restricted to 1/4 res."""
    denom = np.maximum(T * (h[..., None] + (1 - h[..., None])), 1e-3)  # = T
    B = np.clip(R / np.maximum(T, 1e-3), 0, 3)
    B = np.where(h[..., None] > 0.95, 1.0, B)
    H_, W_ = h.shape
    Bq = cv2.resize(B.astype(np.float32), (W_ // 4, H_ // 4), interpolation=cv2.INTER_AREA)
    Bq = cv2.resize(Bq, (W_, H_), interpolation=cv2.INTER_CUBIC).astype(np.float64)
    I_hat = L * T * (h[..., None] + (1 - h[..., None]) * np.clip(Bq, 0, 3))
    return I_hat, Bq


# ------------------------------------------------------------------ plumbing
def tile(img_lin_or_srgb, label, is_linear=True, height=None):
    a = lin_to_srgb(img_lin_or_srgb) if is_linear else np.clip(img_lin_or_srgb, 0, 1)
    a = (a * 255).astype(np.uint8)
    if a.ndim == 2:
        a = np.stack([a] * 3, -1)
    im = Image.fromarray(a)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(label), 16], fill=(0, 0, 0))
    d.text((4, 2), label, fill=(255, 255, 90))
    return np.asarray(im)


def load_linear(path, corners, size):
    """Load a photo, optionally crop to the glass region, downscale to `size`
    (max dim), and return its linear-RGB array. Shared by process() and the
    pair-registration harness so both see identical pixels."""
    img = Image.open(path).convert("RGB")
    if corners:
        img = img.crop(tuple(corners))
    w0, h0 = img.size
    scale = size / max(w0, h0)
    img = img.resize((int(w0 * scale), int(h0 * scale)), Image.LANCZOS)
    return srgb_to_lin(np.asarray(img).astype(np.float64) / 255.0)


def extract_maps(lin, glass_class, mark_region="unknown"):
    """Core map computation (pipeline steps 1-4) on a linear-RGB image.
    Returns a dict of the intermediate/output arrays. process() adds metrics
    and file output on top; the harness reuses the maps directly."""
    W = lin.shape[1]
    # 1. speculars
    lin_ns, spec_mask = suppress_speculars(lin, glass_class, W)
    # 2. illumination + ratio
    L = estimate_illumination(lin_ns, glass_class, W)
    R = lin_ns / np.maximum(L, 1e-4)
    # 3. markings. Repair by diffusion fill, NOT Telea: Telea leaves a tinted
    # smudge that the saturation/chroma cues downstream re-detect as content
    # (report 001 shipped an h map with legible SKU strokes because h was
    # computed from Telea residue and then healed with too small a halo)
    if mark_region == "none":
        mark_mask = np.zeros(R.shape[:2], bool)
    elif mark_region == "unknown":
        mark_mask = detect_marks(R, W)
        if mark_mask.any():
            R = diffusion_fill(np.clip(R, 0, 1.5), 1.0 - mark_mask.astype(np.float64))
    else:
        R, alpha = remove_marks_in_region(R, mark_region, W)
        mark_mask = alpha > 0.25
    # 4. haze + transmittance (R is mark-free here; no post-hoc healing)
    h = estimate_haze(R, glass_class, W)
    T, conf = assemble_T(R, h, glass_class, mark_mask)
    # anchor T to absolute transmittance via the class prior, then move L and R
    # by the inverse so L*T (and thus the self-recon) is exactly invariant -- the
    # scale is a gauge, only T's numeric level changes. See T_ANCHOR.
    pct, target = T_ANCHOR[glass_class]
    # raw_p99: p99 of the un-clipped transmittance before assemble_T's [0,1] clip
    # saturates it. This is the per-sheet scale diagnostic -- how far the brightest
    # transmitting pixels sit above the envelope's clear level (residual
    # hotspot / specular). k itself is ~class-constant because the envelope already
    # normalizes each sheet's clear level to ~1, so raw_p99 is what actually varies.
    raw_p99 = float(np.percentile(np.clip(R, 0, None), 99))
    k = target / max(np.percentile(T, pct), 1e-3)
    T = np.clip(T * k, 0, 1)
    L, R = L / k, R * k
    return {"lin_ns": lin_ns, "spec_mask": spec_mask, "L": L, "R": R, "mark_mask": mark_mask,
            "h": h, "T": T, "conf": conf, "k": float(k), "raw_p99": raw_p99}


def process(path, glass_class, corners, out_dir, size, debug=False, mark_region="unknown"):
    """mark_region: 'unknown' (global conservative detector), 'none' (skip
    mark handling), or a 3x3 grid cell name (targeted aggressive detector)."""
    name = os.path.splitext(os.path.basename(path))[0]
    lin = load_linear(path, corners, size)
    m = extract_maps(lin, glass_class, mark_region)
    lin_ns, spec_mask, L, R = m["lin_ns"], m["spec_mask"], m["L"], m["R"]
    mark_mask, h, T, conf = m["mark_mask"], m["h"], m["T"], m["conf"]

    # 5. metrics
    I_hat, Bq = reconstruct(L, T, h, R)
    err = np.abs(lin_to_srgb(np.clip(I_hat, 0, 1)) - lin_to_srgb(np.clip(lin_ns, 0, 1)))
    # contaminant pixels (marks, speculars) are removed on purpose: the maps
    # SHOULD disagree with the photo there, so score only the clean pixels
    clean = ~(mark_mask | spec_mask)[..., None] * np.ones_like(err, bool)
    metrics = {
        "glass_class": glass_class,
        "recon_mae_srgb255": float(err[clean].mean() * 255),
        "recon_p95_srgb255": float(np.percentile(err[clean], 95) * 255),
        "recon_mae_all_srgb255": float(err.mean() * 255),
        "spec_pixels_pct": float(spec_mask.mean() * 100),
        "mark_pixels_pct": float(mark_mask.mean() * 100),
        "h_mean": float(h.mean()),
        "T_mean_rgb": [float(v) for v in T.reshape(-1, 3).mean(0)],
        # absolute-scale anchor (report 004 DECISION 2): k = the gain applied to
        # hit the class target (class-constant while >=1% of T clips to the
        # ceiling); T_raw_p99 = pre-clip transmittance spread, the per-sheet signal
        # -- an outlier there flags a residual hotspot or a possible misclass.
        "T_anchor_k": m["k"],
        "T_raw_p99": m["raw_p99"],
    }

    # 6. outputs
    os.makedirs(out_dir, exist_ok=True)
    Image.fromarray((lin_to_srgb(T) * 255).astype(np.uint8)).save(f"{out_dir}/{name}_T.png")
    Image.fromarray((h * 255).astype(np.uint8)).save(f"{out_dir}/{name}_h.png")
    warm = np.array([1.0, 0.72, 0.42])
    cool = np.array([0.65, 0.82, 1.0])
    cols = [
        tile(lin, "original"),
        tile(T, "T (transmittance)"),
        tile(h, "h (haze 0..1)"),
        tile(np.clip(I_hat, 0, 1), "self-recon"),
        tile(np.clip(err * 5, 0, 1), "|err| x5", is_linear=False),
        tile(np.clip(render(T, h, warm), 0, 1), "relit warm"),
        tile(np.clip(render(T, h, cool), 0, 1), "relit cool"),
    ]
    panel = np.concatenate([np.pad(c, ((3, 3), (3, 3), (0, 0)), constant_values=25) for c in cols], axis=1)
    Image.fromarray(panel).save(f"{out_dir}/{name}_panel.jpg", quality=88)  # jpg: panels are big
    if debug:
        dbg = np.concatenate([
            tile(spec_mask.astype(float), "specular mask", is_linear=False),
            tile(mark_mask.astype(float), "mark mask", is_linear=False),
            tile(np.clip(L, 0, 1), "illumination L"),
            tile(np.clip(R, 0, 1), "ratio R=I/L"),
            tile(conf, "T confidence", is_linear=False),
            tile(np.clip(Bq / 2, 0, 1), "background B/2", is_linear=False),
        ], axis=1)
        Image.fromarray(dbg).save(f"{out_dir}/{name}_debug.jpg", quality=88)
    with open(f"{out_dir}/{name}_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"{name}: class={glass_class} recon MAE={metrics['recon_mae_srgb255']:.2f}/255 "
          f"p95={metrics['recon_p95_srgb255']:.2f} marks={metrics['mark_pixels_pct']:.2f}% "
          f"spec={metrics['spec_pixels_pct']:.2f}%")
    return metrics


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="photo file or folder (batch mode)")
    ap.add_argument("--glass-class", "--class", dest="glass_class", choices=CLASSES, default=None)
    ap.add_argument("--corners", help="x0,y0,x1,y1 crop of the glass region (original pixels)")
    ap.add_argument("--out", default="results")
    ap.add_argument("--size", type=int, default=700, help="working resolution (max dim)")
    ap.add_argument("--no-vlm", action="store_true",
                    help="skip the default VLM class call (use --class / manifest override, else 'wispy')")
    ap.add_argument("--mark-region", default=None,
                    help="'none', 'unknown', or a 3x3 cell (e.g. bottom-right)")
    ap.add_argument("--debug", action="store_true", help="save intermediate masks/fields")
    args = ap.parse_args()

    def classify(p, entry=None):
        # Precedence (report 004 DECISION 1): --class (whole run) > manifest
        # `class_override` (per-file, explicit human choice) > VLM (the DEFAULT) >
        # 'wispy' fallback. The class is never a silent hard-coded default: a
        # value in the manifest is an explicit override, and everything else is
        # asked of the VLM -- a stale default can no longer beat the classifier
        # (that is what misclassified white.jpg in 002).
        if args.glass_class:
            return args.glass_class
        override = (entry or {}).get("class_override")
        if override:
            return override
        if not args.no_vlm:
            try:
                from vlm_classify import classify_glass
                c = classify_glass(p)
                print(f"  VLM class for {os.path.basename(p)}: {c}")
                return c
            except Exception as e:
                print(f"  VLM class failed ({e}); falling back to 'wispy'")
        return "wispy"

    def marks(p, entry=None):
        # Mark region is human-only (report 003/004): the VLM hallucinates marks
        # on clean sheets, so it does NOT drive removal. Manifest / CLI, else the
        # conservative global detector ('unknown').
        return (entry or {}).get("mark_region") or args.mark_region or "unknown"

    if os.path.isdir(args.input):
        manifest = {}
        mpath = os.path.join(args.input, "manifest.json")
        if os.path.exists(mpath):
            manifest = json.load(open(mpath))
        for f in sorted(os.listdir(args.input)):
            if not f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                continue
            entry = manifest.get(f, {})
            p = os.path.join(args.input, f)
            process(p, classify(p, entry), entry.get("corners"),
                    args.out, args.size, args.debug, mark_region=marks(p, entry))
    else:
        corners = [int(v) for v in args.corners.split(",")] if args.corners else None
        process(args.input, classify(args.input), corners, args.out, args.size, args.debug,
                mark_region=marks(args.input))


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
