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
                                         # {"file.jpg": {"glass_class": "wispy", "corners": [..]}}
  add --vlm to ask the `claude` CLI for the class (multiple choice; see vlm_classify.py)
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
    normalized convolution)."""
    filled = img * conf[..., None]
    w = conf.copy()
    sigma = 2.0
    out = None
    for _ in range(iters):
        fw = gauss(filled, sigma)
        ww = gauss(w, sigma)
        cand = fw / np.maximum(ww[..., None], 1e-6)
        out = cand if out is None else np.where((w > 0.05)[..., None], out, cand)
        sigma *= 2.0
    return conf[..., None] * img + (1 - conf[..., None]) * out


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
    win = max(5, int(0.35 * max(small.shape)))
    env = percentile_filter(small, 88, size=win, mode='nearest')
    env = gauss(env, 0.15 * max(small.shape))
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


def detect_marks(R, W):
    """Grease-pencil markings: thin dark strokes whose COLOR is anomalous.

    Local stats (black-hat depth, sharpness) barely separate pencil from wispy
    glass veining, and shape filtering fails because strokes merge with veins
    into one connected component. What does separate them on the test photo:
    a marking is a foreign pigment, so its chroma deviates from the local glass
    chroma, while veins are the same material family (chroma anomaly ~0.12 for
    pencil vs ~0.03 for veins). Detector = stroke-scale darkness (black-hat)
    x chroma anomaly vs a large local window."""
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
    if mark_mask is not None and mark_mask.any():
        # belt & braces: inpainting may leave stroke fringes; fill them too
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


def process(path, glass_class, corners, out_dir, size, debug=False):
    name = os.path.splitext(os.path.basename(path))[0]
    img = Image.open(path).convert("RGB")
    if corners:
        img = img.crop(tuple(corners))
    w0, h0 = img.size
    scale = size / max(w0, h0)
    img = img.resize((int(w0 * scale), int(h0 * scale)), Image.LANCZOS)
    rgb = np.asarray(img).astype(np.float64) / 255.0
    lin = srgb_to_lin(rgb)
    W = lin.shape[1]

    # 1. speculars
    lin_ns, spec_mask = suppress_speculars(lin, glass_class, W)
    # 2. illumination + ratio
    L = estimate_illumination(lin_ns, glass_class, W)
    R = lin_ns / np.maximum(L, 1e-4)
    # 3. markings
    mark_mask = detect_marks(R, W)
    if mark_mask.any():
        R = inpaint_lin(np.clip(R, 0, 1), mark_mask, radius=max(4, int(0.01 * W)))
    # 4. haze + transmittance
    h = estimate_haze(R, glass_class, W)
    if mark_mask.any():  # stroke fringes also dent h; heal them
        h8 = (np.clip(h, 0, 1) * 255).astype(np.uint8)
        m8 = cv2.dilate(mark_mask.astype(np.uint8), ellipse(2)) * 255
        h = cv2.inpaint(h8, m8, 5, cv2.INPAINT_TELEA).astype(np.float64) / 255
    T, conf = assemble_T(R, h, glass_class, mark_mask)
    # normalize T: lightest real glass transmits ~97%
    T = np.clip(T * (0.97 / max(np.percentile(T, 99), 1e-3)), 0, 1)

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
    ap.add_argument("--vlm", action="store_true", help="classify glass via `claude` CLI (multiple choice)")
    ap.add_argument("--debug", action="store_true", help="save intermediate masks/fields")
    args = ap.parse_args()

    def classify(p):
        if args.glass_class:
            return args.glass_class
        if args.vlm:
            from vlm_classify import classify_glass
            c = classify_glass(p)
            print(f"  VLM class for {os.path.basename(p)}: {c}")
            return c
        return "wispy"

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
            process(p, entry.get("glass_class") or classify(p), entry.get("corners"),
                    args.out, args.size, args.debug)
    else:
        corners = [int(v) for v in args.corners.split(",")] if args.corners else None
        process(args.input, classify(args.input), corners, args.out, args.size, args.debug)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
