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

# Absolute-transmittance anchor (report 003, revised report 009). Per-image
# exposure is unknown, so the split between the illumination scale L and the
# transmittance scale T is a gauge the photo does not fix -- and the self-recon
# metric is blind to it (L absorbs whatever T gives up). We pin the gauge with a
# class prior: (percentile, target) = "the brightest 1% of this class transmits
# about `target`". Chosen so dark-opaque comes out near-black (its p99->0.97
# stretch was the original report-003 bug) while the near-clear classes are
# essentially unchanged (target ~= old 0.97).
#
# Report 009 revision: synthetic per-pixel ground truth (report 007/008) showed
# dark-opaque and opalescent running SYSTEMATICALLY TOO DARK against authored T,
# to the point that dark-opaque's material-relight LOST to a raw pixel copy on
# the product preview-invariance benchmark (report 008: raw MAE 18.9 vs material
# 42.9) -- an over-dark anchor is a real regression, not just a numeric miss.
# cathedral-clear / wispy were checked the same way and left UNCHANGED: their
# extracted mean luminance already matches the measured GT within ~1-4%
# (cathedral-amber ext/gt luminance 0.697/0.706; wispy-white's own GT p99 sits at
# ~0.949, matching the 0.95 target almost exactly) -- their residual per-pixel
# errors are relief/color-constancy issues (see fix 2, and report 007 item 4),
# not an anchor-scale problem, and pushing the anchor further would overfit one
# recipe (e.g. cathedral-amber) at the expense of another (cathedral-green is
# already slightly OVER, not under) -- rejected per the overfitting guard.
#   dark-opaque: measured GT p99 (same percentile the anchor targets) is ~0.216
#   across both rendered samples, more than double the old 0.10. We do NOT fit
#   that number directly -- the task brief itself flags gt~=0.19 as one
#   synthetic recipe's authoring choice ("dim tinted, not near-black"), and nothing
#   guarantees real "dark-opaque" sheets share that peak. Picked target = 0.20,
#   deliberately just under the measured GT peak: a physically-legible "these
#   sheets are deeply tinted, not literally opaque" reading that still leaves
#   headroom below authored GT so we are not curve-fitting one sample. Checked
#   against the real 9-sheet library (report 003's black.jpg, genuinely near-
#   opaque): this only lifts its extracted mean from ~2% to ~4% (its own
#   internal contrast -- median/peak ratio ~0.2 -- keeps it dark regardless of
#   the class ceiling), so black glass still reads black.
#   opalescent: no synthetic recipe exercises this CLASS directly (wispy-white/
#   streaky-mix are both scored under the "wispy" oracle class per
#   eval_synthetic.py). But wispy-white's measured GT p99 (~0.949, milky-white
#   opal glass) refutes the old target's premise ("brightest is translucent, not
#   clear" -> 0.80): strongly backlit milky glass CAN reach near-full
#   transmittance at its brightest fleck (haze scatters the light, it does not
#   have to absorb it). Raised to 0.88 -- still below wispy's 0.95 (milky
#   diffusers are conservatively kept a notch below streaky/clear-patch glass,
#   which really can show a clear near-white streak), but well above the old
#   0.80. Validated only qualitatively (real library white.jpg, gauge (c)) since
#   there is no ground truth for this class; a smaller, more conservative bump
#   than dark-opaque's for that reason.
T_ANCHOR = {
    "cathedral-clear": (99, 0.95),
    "wispy": (99, 0.95),
    "opalescent": (99, 0.88),   # milky: brightest is translucent, not clear
    "dark-opaque": (99, 0.20),  # brightest fleck transmits ~20%; median ends dark, not black
}

# Anchor sanity gate (report 016). The anchor gain k = target / p99(T_pre) is
# ~class-constant in healthy extractions because the illumination envelope
# already normalizes the sheet's clear level to ~1, so p99(T_pre) clips at ~1
# and k ~= the class target. Measured over every in-sample extraction we have
# (26 synthetic v2 samples under oracle class, the 9-sheet real library, the 2
# benchmark singles, and the 57-image backlit-verified corpus subset of report
# 015), k spans [0.20, 0.9614] -- EXCEPT one catastrophic corpus case
# (wissmach-wf40105.jpg, a texture-free saturated solid red under the
# `opalescent` prior) where assemble_T's saturation cue read the ENTIRE sheet
# as background bleed-through, conf collapsed to 0 everywhere, diffusion_fill
# had no trusted source pixel, T came out identically zero, and k hit the
# percentile floor at target/1e-3 = 880, leaving T black (recon MAE 83/255,
# report 015 section 3 item 2). k outside a sane band is therefore a SYMPTOM
# of a degenerate T assembly (or a badly wrong class prior), not a fixable
# gain -- clamping k alone would keep the black T. The gate: if k leaves
# (0.05, 5.0) -- >= 4x margin on both sides of every in-sample value -- rebuild
# T by trusting R directly (the same assembly cathedral-clear/dark-opaque use;
# R is the directly-observed illumination-normalized image, so it is always
# non-degenerate), recompute k, clamp it into the band as a last resort, and
# flag `anchor_fallback` in the metrics so batch runs can QA-filter.
ANCHOR_K_MIN, ANCHOR_K_MAX = 0.05, 5.0

# ---- Continuous (image-statistics) absolute-scale anchor (report 016) ------
# Motivation: the class-anchored gauge above hangs ENTIRELY on the class label,
# and report 015 measured the VLM class prior at 30.6% accuracy on the real
# catalog corpus (barely above chance), with the catalog metadata itself being
# noisy marketing taxonomy at class boundaries. A dark sheet misread as
# cathedral-clear comes out ~4.75x too bright (0.95/0.20) under the class
# anchor -- a catastrophic, invisible failure. The continuous anchor estimates
# the absolute scale from CLASS-FREE image statistics and uses the class prior
# only as a regularizer, so a wrong class degrades the scale gracefully
# instead of failing hard.
#
# Model:  t_img = T_LO + (T_HI - T_LO) * sigmoid(c0 + c . (x - mu) / sd)
# with 3 class-free features of the raw linear photo:
#   log(p95(Y))    absolute brightness of the brightest transmitting regions
#                  (~ backlight x brightest transmittance; the main scale cue)
#   sat_lit        luminance-GATED mean saturation (only pixels bright enough,
#                  smoothstep(Y, 0.10, 0.30), for saturation to be signal) --
#                  deep tinted cathedral glass stays saturated even when dim,
#                  while dense dark-opaque glass reads dim AND (in its lit
#                  pixels, if any) desaturated
#   lit_frac       mean of that luminance gate: how much of the sheet
#                  transmits at all
# Feature-hardening note (measured, not hypothetical): a tighter synthetic
# fit exists using raw p90(saturation) and mean milkiness (LOO mean 1.27x vs
# this set's 1.45x), but both features are Cycles artifacts in disguise --
# on real photos, sensor noise at near-black gives a black sheet
# sat_p90 = 0.90 (read as "vividly tinted" -> t_img 0.39 for library
# black.jpg), and real hammered-opal relief kills milkiness' smoothness term
# (library white.jpg milk 0.12 vs synthetic wispy 0.5 -> t_img 0.36 for a
# bright milky sheet). The gated features fix both real-photo cases
# (white 0.93, black 0.28) at a measured cost in synthetic LOO accuracy;
# robustness in the wild is the goal, so the gated set ships.
# Fit: ridge (lam=2.0) least squares in logit space, target = p99 of gt_T
# (the exact statistic T_ANCHOR pins). Report 016 fit on the 26 synthetic-v2
# samples (5 recipes); report 017 refit on the widened 35-sample / 8-recipe
# set after adding three dark-family recipes (dark-deep ~0.055, dark-ruby
# ~0.13, dark-slate ~0.31) -- the dark end had been calibrated by ONE recipe
# (leave-dark-opaque-out could not predict dark at all, LORO worst 4.29x;
# now 3.37x with held-out dark predictions actually landing dark, and every
# dark-family LORO cell <= 2.5x; see fit_anchor.py + report 017). T_LO
# lowered 0.10 -> 0.04 with the refit: dark-deep's authored GT (0.055) sits
# below the old floor, i.e. the old model could not represent it; the refit
# at 0.04 is also better in-sample (mean 1.44x vs 1.51x) and on the real
# library (black.jpg t_img 0.236 vs target 0.20; blue.jpg -- report 016's
# only mover -- stays at the old disagreement, 0.611 vs old 0.620, where a
# T_LO=0.10 refit pushed it to 0.497 = 1.9x disagreement).
# Residual failure mode (honest): "dark glass under bright backlight" vs
# "bright glass under dim backlight" genuinely overlap in single-photo
# statistics -- the same L*T gauge ambiguity as ever; the estimator
# compresses that ambiguity to ~2-3x, it cannot remove it. Note the
# sat_lit feature reads 0 on ALL dim captures (the luminance gate excludes
# every pixel), so tinted-vs-neutral darkness is invisible to the estimator
# exactly where it would help most (report 017 dark-ruby measurement).
#
# The class prior remains as a REGULARIZER via an adaptive log-space blend
# (`blend_anchor_target`): when image estimate and class target agree within
# ANCHOR_BLEND_TAU0 (ratio), trust the class target fully (zero drift on
# healthy extractions); as disagreement grows toward TAU1, shift up to
# ANCHOR_BLEND_WMAX of the way (in log space) to the image estimate. Constants
# tuned on the synthetic class-error-injection eval (eval_class_injection.py).
# Report 020 refit: MU/SD/COEF refit on the SAME 35-sample/8-recipe set as
# report 017 (T_LO/T_HI unchanged) after the sat_lit ADAPTIVE-GATE fix above
# -- fit_anchor.py, same ridge-in-logit-space method, extended to reuse
# extract.anchor_features so fit and inference are identical by
# construction. Only sat_lit's mu/sd/coefficient move (0.238821->0.339133,
# 0.221127->0.197783, 1.28039->1.55464): the other two features and their
# coefficients are within noise of report 017's values, as expected since
# the fix only changes sat_lit's value on 12 of the 35 fit samples (all in
# the dark family) where the old absolute gate was degenerate.
ANCHOR_T_LO, ANCHOR_T_HI = 0.04, 0.98
ANCHOR_FEAT_MU = np.array([-1.98505, 0.339133, 0.241629])
ANCHOR_FEAT_SD = np.array([1.16796, 0.197783, 0.327259])
ANCHOR_COEF = np.array([0.0933926, 1.55464, 0.260738, 0.476681])
ANCHOR_BLEND_TAU0, ANCHOR_BLEND_TAU1, ANCHOR_BLEND_WMAX = 1.5, 3.0, 0.85


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


# Report 020: sat_lit's ADAPTIVE fallback gate, used only when the absolute
# gate below is degenerate (see anchor_features). Percentile band, not a
# fixed choice: measured to be insensitive to the exact numbers (dark-opaque
# sat_lit_adapt 0.182/0.199/0.175/0.195 for (80,97)/(90,99)/(70,95)/(85,99.5)
# respectively) -- the point is "the brightest fraction of THIS photo",
# whatever absolute luminance that happens to be, not the exact fraction.
SAT_LIT_FALLBACK_PLO, SAT_LIT_FALLBACK_PHI = 80, 97


def anchor_features(lin):
    """Raw, class-free feature triplet for the continuous anchor (report 016):
    [log p95(luminance), luminance-gated mean saturation, lit-pixel fraction].
    Split out from estimate_anchor_scale so report 017's refit script
    (fit_anchor.py) computes features identically to the shipped estimator
    instead of duplicating the math.

    Report 020 fix (dim-capture blindness): the absolute luminance gate
    below (smoothstep(Y, 0.10, 0.30)) is what report 017 measured as
    completely blind on dim captures -- ALL 9 dark-family renders in that
    report had sat_lit==0, because no pixel in a dim photo ever crosses
    0.10 luminance, so a strongly-tinted dark sheet (dark-ruby) and a
    neutral one (dark-deep) were statistically indistinguishable on this
    feature, exactly where tint would help separate them. Fix: when the
    absolute gate excludes (nearly) everything -- the SAME condition that
    used to just return 0.0 -- fall back to a gate relative to THIS
    photo's OWN brightest pixels (percentile-based, not a fixed luminance)
    so saturation is measured on the brightest available pixels of a dim
    capture instead of on nothing. `lit_frac` (the third feature, "how much
    of the sheet transmits at all") deliberately keeps the absolute gate
    unchanged -- reading near-zero there on a dim capture is itself real,
    useful signal (report 016's original "lit-pixel fraction" cue), so
    making it adaptive would destroy the exact information this fix is
    trying to recover for sat_lit. On any capture where the absolute gate
    was already non-degenerate (every one of the original 5 recipes, and
    most dark-opaque lightings too) this is a no-op: same code path,
    same numbers, as report 016/017."""
    Y = lum(lin)
    mx, mn = lin.max(axis=-1), lin.min(axis=-1)
    sat = (mx - mn) / (mx + 1e-6)
    wlit = smoothstep(Y, 0.10, 0.30)
    if wlit.sum() > 1:
        sat_lit = float((sat * wlit).sum() / (wlit.sum() + 1e-6))
    else:
        p_lo = np.percentile(Y, SAT_LIT_FALLBACK_PLO)
        p_hi = np.percentile(Y, SAT_LIT_FALLBACK_PHI)
        lo2, hi2 = min(p_lo, p_hi), max(p_lo, p_hi)
        if hi2 - lo2 < 1e-6:
            hi2 = lo2 + 1e-6
        wlit2 = smoothstep(Y, lo2, hi2)
        sat_lit = float((sat * wlit2).sum() / (wlit2.sum() + 1e-9))
    return np.array([
        float(np.log(max(np.percentile(Y, 95), 1e-3))),
        sat_lit,
        float(wlit.mean()),
    ])


def estimate_anchor_scale(lin):
    """Continuous, class-free absolute-scale estimate t_img (report 016): the
    predicted p99 transmittance of the sheet, from raw-photo statistics only.
    See the ANCHOR_* constants comment for model, features, fit and limits."""
    x = anchor_features(lin)
    s = ANCHOR_COEF[0] + float(np.dot(ANCHOR_COEF[1:], (x - ANCHOR_FEAT_MU) / ANCHOR_FEAT_SD))
    return ANCHOR_T_LO + (ANCHOR_T_HI - ANCHOR_T_LO) / (1.0 + np.exp(-s))


# ---- Per-SHEET scale pooling (report 020) -----------------------------
# Report 017 measured an honest cost of the continuous anchor: t_img is
# estimated per PHOTO, so the SAME physical sheet gets a different absolute
# scale under every capture, and the continuous path's cross-lighting
# invariance breaks on mid/dark glass (dark-opaque invariance T 0.036
# class-anchored -> 0.280 continuous) even though it is on average more
# accurate than the class anchor. "Class anchor is consistently wrong,
# continuous is averagely right" -- but in the PRODUCT a sheet is one
# physical entity, so when several photos of the SAME sheet are available
# (the synthetic multi-lighting groups are exactly this; a real user who
# shoots one sheet under 2-3 lightings/angles is the product case) there is
# no reason to let each photo re-derive its own scale independently.
def estimate_anchor_scale_sheet(lins):
    """Pool several photos of the SAME sheet into ONE continuous-anchor
    scale estimate, used for all of them.

    Aggregate = MEDIAN of the per-photo t_img estimates (`estimate_anchor_
    scale` applied independently to each photo), not a mean -- even a
    geometric/log-space one. Justification: the estimator's own documented
    failure mode is that a SINGLE unlucky photo (a specular hotspot
    inflating p95(luminance), an underexposed capture, a crop that catches
    mostly shadowed glass) can push one photo's raw-statistics reading far
    from the sheet's true scale while its siblings agree; the median
    tolerates up to floor((N-1)/2) such outlier photos without being
    dragged toward them, at zero extra machinery. A precision-weighted mean
    would need a per-photo uncertainty/confidence model to weight by, and
    none exists (there is no ground truth to calibrate one against, and
    report 016/017's whole ethos is not to invent an unmeasured knob) --
    the median is the assumption-free robust statistic available today.
    Because the feature->t_img map is a monotonic sigmoid, taking the
    median of the final t_img values is exactly equal to taking it in
    feature- or log-space -- median commutes with any monotonic transform
    -- so no separate log-space bookkeeping is needed.

    N=1 is the identity (median of one element is that element), so a
    single-photo call is byte-identical to calling `estimate_anchor_scale`
    directly -- pooling is strictly additive, never a behaviour change
    when only one photo is given."""
    ts = np.array([estimate_anchor_scale(lin) for lin in lins], dtype=np.float64)
    return float(np.median(ts))


def blend_anchor_target(t_class, t_img):
    """Class prior as regularizer (report 016): adaptive log-space blend.
    Agreement within TAU0 -> class target untouched; disagreement ramping to
    TAU1 -> up to WMAX of the (log) distance moved toward the image estimate."""
    d = abs(np.log(t_img) - np.log(t_class))
    ramp = (d - np.log(ANCHOR_BLEND_TAU0)) / (np.log(ANCHOR_BLEND_TAU1) - np.log(ANCHOR_BLEND_TAU0))
    w = ANCHOR_BLEND_WMAX * float(np.clip(ramp, 0.0, 1.0))
    return float(np.exp((1.0 - w) * np.log(t_class) + w * np.log(t_img)))


def luminance_envelope(Y):
    """Smooth luminance envelope (class-free). Since T<=1 and I = L*T, the
    illumination rides on top of the observed luminance, so a large-window
    high-percentile filter tracks L*T_bright.

    p95/0.35 chosen by sweep (report 002): higher percentile pushes glass
    structure out of the envelope into T (+21% T contrast on the wispy case)
    at negligible cost in residual illumination on the easy case.

    Hotspot recovery (report 004): the broad envelope smooths a compact
    backlight hotspot down, so R = I/L runs hot there and the hotspot leaks
    into T (blue's cyan patch, red's milder one). A tighter-window,
    higher-percentile envelope tracks the compact peak; taking the max lifts
    the envelope only where the tight peak exceeds the broad one -- i.e. on a
    compact bright blob. Over broad uniform glass the two agree, so glass
    color is untouched (median unchanged)."""
    from scipy.ndimage import percentile_filter
    H_, W_ = Y.shape
    s = 8
    small = cv2.resize(Y.astype(np.float32), (max(W_ // s, 8), max(H_ // s, 8)),
                       interpolation=cv2.INTER_AREA).astype(np.float64)
    d = max(small.shape)
    win = max(5, int(0.35 * d))
    base = gauss(percentile_filter(small, 95, size=win, mode='nearest'), 0.15 * d)
    pw = max(3, int(0.15 * d))
    peak = gauss(percentile_filter(small, 98, size=pw, mode='nearest'), 0.05 * d)
    env = np.maximum(base, peak)
    env = cv2.resize(env.astype(np.float32), (W_, H_), interpolation=cv2.INTER_CUBIC).astype(np.float64)
    return np.maximum(env, 1e-3)


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
    env = luminance_envelope(Y)

    # --- chroma field
    chroma = np.ones_like(lin)
    if glass_class in ("opalescent", "wispy"):
        w0 = milkiness(lin / np.maximum(env, 1e-3)[..., None], r_tex=max(2, int(0.006 * W)))
        c = lin / (Y[..., None] + 1e-6)
        s2 = 6
        cs = cv2.resize(c.astype(np.float32), (W_ // s2, H_ // s2), interpolation=cv2.INTER_AREA)
        ws = cv2.resize(w0.astype(np.float32), (W_ // s2, H_ // s2), interpolation=cv2.INTER_AREA)
        # report 009 fix 2: a nonzero weight FLOOR (as opposed to a hard cutoff)
        # let the large mass of only-partially-milky pixels vote in the fit.
        # For a material that is genuinely tinted in its clearer/less-milky
        # areas (streaky-mix: real blue tint anti-correlates with haze, see
        # report 009 for the measurement), that partial-milkiness mass is
        # partially colored, not neutral -- it dragged the fit into
        # mis-estimating a spatially-varying "illuminant" that actually
        # inverted the true blueness/haze relationship (measured: raw photo
        # corr(blueness, haze) = -0.16 (right sign), after the old fit = +0.18
        # (flipped) ). Zeroing weight below 0.3 keeps only pixels confidently
        # milky enough to be trusted as revealing illuminant, not glass color;
        # verified this is a small, same-direction win on both recipes that
        # exercise this code path (streaky-mix hue error 0.127 -> 0.123;
        # wispy-white unaffected, 0.0142 -> 0.0153 chroma error, noise-level).
        ws = np.where(ws < 0.3, 0.0, ws)
        ys, xs = np.mgrid[0:cs.shape[0], 0:cs.shape[1]]
        xs = xs / cs.shape[1] - 0.5
        ys = ys / cs.shape[0] - 0.5
        A = np.stack([np.ones_like(xs), xs, ys, xs * xs, ys * ys, xs * ys], -1).reshape(-1, 6)
        wv = np.sqrt(np.maximum(ws.reshape(-1), 1e-5))
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
    # wispy / opalescent: trust pixels that are milky OR show a bright,
    # near-the-SHEET'S-OWN-TINT background (saturated bright pixels that don't
    # match the glass's own color are background content, e.g. lawn).
    #
    # Report 009 fix 2: the old version measured saturation against absolute
    # neutral grey, i.e. it assumed this class is always near-white, so ANY
    # real color was read as background bleed-through and diffusion-filled
    # away -- one contributor to neutralizing streaky-mix's genuine blue tint
    # to grey (report 007/008: gt [0.64,0.77,0.92] extracted as
    # [0.77,0.78,0.78]). Investigation (report 009) found the dominant
    # contributor was actually upstream in `estimate_illumination`'s chroma
    # fit (fixed there separately); this confidence gate is a second, smaller,
    # independently-correct issue with the same wrong premise, kept as a
    # no-regression fix even though its effect was negligible on the specific
    # samples measured here (confidence was already high almost everywhere on
    # those samples -- see report 009 for the honest accounting). Fix: measure
    # saturation relative to the sheet's OWN robust median hue (a
    # wispy-white/opalescent sheet's median hue is near-neutral anyway, so
    # this is a no-op there; a uniformly-tinted sheet's dominant color now
    # reads as "not saturated", i.e. trusted as glass, while a patch that
    # genuinely differs from the sheet's own tint -- true background
    # bleed-through -- still stands out).
    chroma = Rc / (Y[..., None] + 1e-6)
    tint = np.median(chroma.reshape(-1, 3), axis=0)
    tint = tint / (tint.mean() + 1e-9)
    Rc_detinted = Rc / (tint[None, None, :] + 1e-6)
    mx, mn = Rc_detinted.max(axis=-1), Rc_detinted.min(axis=-1)
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


def extract_maps(lin, glass_class, mark_region="unknown", anchor="class", sheet_t_img=None):
    """Core map computation (pipeline steps 1-4) on a linear-RGB image.
    Returns a dict of the intermediate/output arrays. process() adds metrics
    and file output on top; the harness reuses the maps directly.

    anchor: 'class' (report 003/009 class-prior target), 'continuous'
    (report 016: class-free image-statistics estimate, class prior as
    regularizer via blend_anchor_target), or 'none' (research/eval only:
    return the UNANCHORED maps, k=1, so an eval harness can apply and
    compare anchor designs itself).

    sheet_t_img: optional pre-computed PER-SHEET continuous-anchor scale
    (report 020, `estimate_anchor_scale_sheet`) -- when given, used in
    place of this photo's own `estimate_anchor_scale(lin)` so several
    photos of the same physical sheet share one scale instead of each
    deriving its own. None (default) reproduces the exact single-photo
    report 016/017 behaviour byte-for-byte."""
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
    # t_img is computed in EVERY mode: even when it does not drive the anchor,
    # |log(t_img / class target)| is a free class/photo-mismatch QA signal
    # (report 016 flags the corpus images whose metadata class contradicts the
    # photo -- e.g. a "dark-opaque" registry row whose photo is a front-lit
    # iridescent coating -- at ratio > 2 with no false hits on the library).
    t_img = float(estimate_anchor_scale(lin)) if sheet_t_img is None else float(sheet_t_img)
    if anchor == "continuous":
        target = blend_anchor_target(target, t_img)
    # raw_p99: p99 of the un-clipped transmittance before assemble_T's [0,1] clip
    # saturates it. This is the per-sheet scale diagnostic -- how far the brightest
    # transmitting pixels sit above the envelope's clear level (residual
    # hotspot / specular). k itself is ~class-constant because the envelope already
    # normalizes each sheet's clear level to ~1, so raw_p99 is what actually varies.
    raw_p99 = float(np.percentile(np.clip(R, 0, None), 99))
    anchor_fallback = False
    if anchor == "none":
        k = 1.0
        target = None
    else:
        k = target / max(np.percentile(T, pct), 1e-3)
        # sanity gate (see ANCHOR_K_MIN/MAX comment): out-of-band k means the T
        # assembly degenerated (e.g. conf collapsed to 0 and diffusion_fill had
        # no source -> T identically 0 -> k explodes to target/1e-3). Rebuild T
        # from the directly-observed R, re-anchor, clamp as a last resort, flag.
        if not (ANCHOR_K_MIN < k < ANCHOR_K_MAX):
            anchor_fallback = True
            T = np.clip(R, 0, 1)
            conf = np.ones_like(conf)
            k = target / max(np.percentile(T, pct), 1e-3)
            k = float(np.clip(k, ANCHOR_K_MIN, ANCHOR_K_MAX))
        T = np.clip(T * k, 0, 1)
        L, R = L / k, R * k
    return {"lin_ns": lin_ns, "spec_mask": spec_mask, "L": L, "R": R, "mark_mask": mark_mask,
            "h": h, "T": T, "conf": conf, "k": float(k), "raw_p99": raw_p99,
            "anchor_fallback": anchor_fallback, "anchor_mode": anchor,
            "anchor_target": (None if target is None else float(target)),
            "anchor_t_img": t_img}


def process(path, glass_class, corners, out_dir, size, debug=False, mark_region="unknown",
            anchor="class", sheet_t_img=None):
    """mark_region: 'unknown' (global conservative detector), 'none' (skip
    mark handling), or a 3x3 grid cell name (targeted aggressive detector).
    sheet_t_img: see extract_maps -- pooled per-sheet continuous-anchor scale
    (report 020), None by default (single-photo behaviour, unchanged)."""
    name = os.path.splitext(os.path.basename(path))[0]
    lin = load_linear(path, corners, size)
    m = extract_maps(lin, glass_class, mark_region, anchor=anchor, sheet_t_img=sheet_t_img)
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
        # True when the sanity gate fired: k left (ANCHOR_K_MIN, ANCHOR_K_MAX)
        # and T was rebuilt from R. Batch runs should QA-flag these outputs.
        "anchor_fallback": m["anchor_fallback"],
        # 'class' or 'continuous' (report 016). anchor_t_img is the class-free
        # image-statistics scale estimate (computed in every mode);
        # anchor_target the target actually anchored to. anchor_scale_disagree
        # = max ratio between t_img and the CLASS target -- > ~2 flags a
        # class/photo mismatch worth reviewing, whichever mode anchored T.
        "anchor_mode": m["anchor_mode"],
        "anchor_target": m["anchor_target"],
        "anchor_t_img": m["anchor_t_img"],
        "anchor_scale_disagree": float(max(m["anchor_t_img"] / T_ANCHOR[glass_class][1],
                                           T_ANCHOR[glass_class][1] / m["anchor_t_img"])),
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
    ap.add_argument("input", nargs="+",
                     help="photo file, folder (batch mode), or SEVERAL photo files of the SAME "
                          "sheet (report 020 per-sheet scale pooling: see estimate_anchor_scale_sheet "
                          "-- the continuous anchor's scale is estimated once for the whole group "
                          "instead of once per photo). A single path (file or folder) is the "
                          "original single-photo/batch behaviour, byte-identical.")
    ap.add_argument("--glass-class", "--class", dest="glass_class", choices=CLASSES, default=None)
    ap.add_argument("--corners", help="x0,y0,x1,y1 crop of the glass region (original pixels)")
    ap.add_argument("--out", default="results")
    ap.add_argument("--size", type=int, default=700, help="working resolution (max dim)")
    ap.add_argument("--no-vlm", action="store_true",
                    help="skip the default VLM class call (use --class / manifest override, else 'wispy')")
    ap.add_argument("--mark-region", default=None,
                    help="'none', 'unknown', or a 3x3 cell (e.g. bottom-right)")
    ap.add_argument("--anchor", choices=("auto", "class", "continuous"), default="auto",
                    help="absolute-scale anchor: 'class' (class-prior target, report 003/009), "
                         "'continuous' (image-statistics estimate with the class prior as "
                         "regularizer, report 016), or 'auto' (DEFAULT, report 016 sign-off: "
                         "'continuous' when the class came from the VLM/fallback -- that path "
                         "is ~30%-reliable in the wild, report 015 -- and 'class' when a human "
                         "set it via --class or manifest class_override)")
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
            return args.glass_class, True
        override = (entry or {}).get("class_override")
        if override:
            return override, True
        if not args.no_vlm:
            try:
                from vlm_classify import classify_glass
                c = classify_glass(p)
                print(f"  VLM class for {os.path.basename(p)}: {c}")
                return c, False
            except Exception as e:
                print(f"  VLM class failed ({e}); falling back to 'wispy'")
        return "wispy", False

    def resolve_anchor(human_class):
        if args.anchor != "auto":
            return args.anchor
        return "class" if human_class else "continuous"

    def marks(p, entry=None):
        # Mark region is human-only (report 003/004): the VLM hallucinates marks
        # on clean sheets, so it does NOT drive removal. Manifest / CLI, else the
        # conservative global detector ('unknown').
        return (entry or {}).get("mark_region") or args.mark_region or "unknown"

    if len(args.input) == 1 and os.path.isdir(args.input[0]):
        in_dir = args.input[0]
        manifest = {}
        mpath = os.path.join(in_dir, "manifest.json")
        if os.path.exists(mpath):
            manifest = json.load(open(mpath))
        files = [f for f in sorted(os.listdir(in_dir)) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]

        # Report 020: per-sheet scale pooling. An optional manifest
        # `sheet_id` groups several files as photos of the SAME physical
        # sheet; the continuous anchor pools their scale estimates into
        # ONE number (estimate_anchor_scale_sheet) instead of each file
        # deriving its own. Files with no sheet_id (the default -- every
        # existing manifest) are solo groups of size 1, for which pooling
        # is the identity: sheet_t_img stays None and the code path below
        # is EXACTLY the pre-020 per-file behaviour, byte-identical.
        groups = {}
        for f in files:
            sid = manifest.get(f, {}).get("sheet_id")
            groups.setdefault(sid if sid is not None else f"\0solo\0{f}", []).append(f)
        sheet_t_img_by_file = {}
        for sid, fs in groups.items():
            if len(fs) < 2:
                continue
            lins = [load_linear(os.path.join(in_dir, f), manifest.get(f, {}).get("corners"), args.size)
                    for f in fs]
            pooled = estimate_anchor_scale_sheet(lins)
            print(f"  sheet '{sid}': pooled t_img={pooled:.4f} from {len(fs)} photos {fs}")
            for f in fs:
                sheet_t_img_by_file[f] = pooled

        for f in files:
            entry = manifest.get(f, {})
            p = os.path.join(in_dir, f)
            cls, human_cls = classify(p, entry)
            process(p, cls, entry.get("corners"),
                    args.out, args.size, args.debug, mark_region=marks(p, entry),
                    anchor=resolve_anchor(human_cls), sheet_t_img=sheet_t_img_by_file.get(f))
    elif len(args.input) == 1:
        corners = [int(v) for v in args.corners.split(",")] if args.corners else None
        cls, human_cls = classify(args.input[0])
        process(args.input[0], cls, corners, args.out, args.size, args.debug,
                mark_region=marks(args.input[0]), anchor=resolve_anchor(human_cls))
    else:
        # Report 020: several explicit photo paths on the command line = one
        # sheet-group (multi-photo entry point). All photos share ONE class
        # (a physical sheet has one class) and ONE pooled continuous-anchor
        # scale; each still gets its own output maps.
        for p in args.input:
            if os.path.isdir(p):
                ap.error(f"{p} is a directory; mixing folders with multiple file "
                          f"arguments is not supported")
        corners = [int(v) for v in args.corners.split(",")] if args.corners else None
        cls, human_cls = classify(args.input[0])
        anchor = resolve_anchor(human_cls)
        lins = [load_linear(p, corners, args.size) for p in args.input]
        sheet_t_img = estimate_anchor_scale_sheet(lins)
        print(f"  sheet group ({len(args.input)} photos): class={cls} anchor={anchor} "
              f"pooled t_img={sheet_t_img:.4f}")
        for p in args.input:
            process(p, cls, corners, args.out, args.size, args.debug,
                    mark_region=marks(p), anchor=anchor, sheet_t_img=sheet_t_img)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
