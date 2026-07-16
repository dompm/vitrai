#!/usr/bin/env python3
"""Report 053 — COMPLETE, CORRELATED phone-camera ISP pipelines (loader-side nuisance).

The external dataset review the CTO commissioned (docs/external/053-dataset-capture-
review.md) found that the loader's `_augment_photo` applied four INDEPENDENTLY randomized
effects (exposure jitter + signal-dependent noise + gamma jitter + JPEG) and nothing else:
no AWB, no local HDR/tonemap, no sharpening halos, no denoising, no saturation shift, no
per-channel clipping, no lens shading, no chromatic aberration, no motion/defocus blur, no
rescale/HEIC, and — critically — no CORRELATED device presets. A model trained on that set
learns "Blender glass grammar" and a hand-tuned four-knob nuisance model, not the joint
distribution of artifacts a real phone ISP stamps onto a window capture.

This module replaces those four independent knobs with several NAMED, COMPLETE device-like
pipelines applied in the physically correct ISP ORDER:

    scene-linear
      -> exposure / auto-exposure error
      -> AWB (white-balance) error, per-channel gain
      -> lens shading (radial vignette + colour shading)
      -> chromatic aberration (per-channel radial magnification)
      -> sensor noise (signal-dependent, in the linear sensor domain)
      -> optical blur (defocus OR motion — handheld)
      -> local HDR / tone mapping (highlight compression + local-contrast HALOS)   [-> display]
      -> denoise (edge-preserving; smears fine texture, couples with gain/noise)
      -> sharpen (unsharp with OVERSHOOT halos; couples with denoise)
      -> saturation / per-channel clip
      -> rescale (resolution loss: down then up)
      -> JPEG / HEIC-grade block quantization
    -> decode back to scene-linear

CORRELATIONS ARE THE POINT (review §2): a "low-light" preset couples high gain + strong
signal-dependent noise + aggressive denoise + stronger local tonemap + compensating
sharpening; a "bright-window-HDR" preset couples highlight compression + local-contrast
halos + mild noise. Independent knobs cannot produce those joints.

Contract (report 025 srgb/linear conventions preserved):
  * INPUT  : scene-linear RGB float32, HxWx3 (the generator's photo_linear space).
  * OUTPUT : scene-linear RGB float32 — every op that must live in a display/quantized space
             round-trips through the sRGB view and is decoded back with `srgb_to_lin`, so the
             loader keeps handing scene-linear to the model. The TARGETS are never touched:
             this trains nuisance (N) invariance, the intrinsics stay fixed.
  * numpy / cv2 only, fast enough for on-the-fly per-crop augmentation.

The presets are a small named set (5) + per-parameter jitter within each. `apply_phone_pipeline`
draws a preset (optionally forced, for held-out-preset splits / boards) and a parameter sample,
runs the ordered pipeline, and returns the processed scene-linear photo. `PRESET_NAMES` is the
authoritative list the holdout split (dataset.py) and the contact-sheet boards key on.
"""
import os
import sys

import numpy as np

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from extract import srgb_to_lin, lin_to_srgb, lum  # noqa: E402  (frozen colour helpers, report 025)


# --------------------------------------------------------------------------- presets
# Each preset is a dict of parameter RANGES (lo, hi) sampled per call. The names are stable
# — the holdout split and the boards reference them. A preset is a COMPLETE ISP config, so
# its parameters co-vary as a real device tuning would (see module docstring).
#
# Parameter glossary (all ranges are [lo, hi], sampled uniformly unless noted):
#   ev             : auto-exposure error in stops (log2 gain applied in linear).
#   awb            : per-channel WB error; r_gain/b_gain multiplicative around 1 (green fixed).
#   vignette       : peak radial darkening at the corner (fraction, 0=no vignette).
#   color_shading  : extra per-channel corner tint spread (lens IR/CRA colour shading).
#   ca_px          : chromatic aberration — R/B radial magnification, in px at the corner.
#   read_noise     : gaussian read noise sigma (linear, signal-independent floor).
#   shot_noise     : signal-dependent (shot) noise scale: sigma = shot*sqrt(max(p,0)).
#   blur_sigma     : optical blur sigma (px). motion_prob picks directional vs isotropic.
#   motion_prob    : P(blur is directional motion blur) vs isotropic defocus.
#   hl_compress    : highlight-compression strength (Reinhard-ish shoulder in linear).
#   local_contrast : local-contrast (unsharp-on-tone) gain — the HDR "clarity"/HALO term.
#   local_radius   : radius (px) of the local-contrast kernel — large radius => visible halos.
#   denoise        : edge-preserving denoise strength (bilateral sigma_color, display units).
#   sharpen        : unsharp-mask amount; overshoot>0 makes edge HALOS.
#   sharpen_radius : unsharp radius (px).
#   saturation     : saturation multiply around luma (1=unchanged).
#   rescale        : downscale factor before upscale-back (1=no resolution loss).
#   jpeg_q         : (lo, hi) JPEG quality. codec 'heic' adds chroma smear (see _quantize).
#   codec          : 'jpeg' or 'heic' (HEIC approximated — see _quantize docstring).

PRESETS = {
    # A clean, well-exposed mid-range capture. The "easy" end of the distribution — light
    # processing, so the model still sees near-pristine inputs some of the time.
    "neutral_mid": dict(
        ev=(-0.35, 0.35), awb_r=(0.94, 1.06), awb_b=(0.94, 1.06),
        vignette=(0.02, 0.12), color_shading=(0.0, 0.02), ca_px=(0.0, 0.6),
        read_noise=(0.0015, 0.006), shot_noise=(0.004, 0.012),
        blur_sigma=(0.0, 0.7), motion_prob=0.15,
        hl_compress=(0.1, 0.5), local_contrast=(0.05, 0.25), local_radius=(6, 18),
        denoise=(0.01, 0.04), sharpen=(0.2, 0.6), sharpen_radius=(1.0, 2.0),
        saturation=(0.98, 1.12), rescale=(1.0, 1.25),
        jpeg_q=(70, 95), codec="jpeg",
    ),
    # Apple-style computational HDR of a BRIGHT WINDOW: aggressive highlight compression, strong
    # local contrast (the tell-tale HDR halo ring around a mullion / bright pane), punchy but
    # controlled sat, HEIC output. Low gain (bright scene) => little noise, little denoise.
    "bright_window_hdr": dict(
        ev=(-0.8, 0.1), awb_r=(0.90, 1.08), awb_b=(0.92, 1.10),
        vignette=(0.04, 0.16), color_shading=(0.0, 0.03), ca_px=(0.3, 1.4),
        read_noise=(0.001, 0.004), shot_noise=(0.003, 0.010),
        blur_sigma=(0.0, 0.6), motion_prob=0.1,
        hl_compress=(0.9, 2.2), local_contrast=(0.45, 1.0), local_radius=(14, 44),
        denoise=(0.01, 0.05), sharpen=(0.6, 1.4), sharpen_radius=(1.2, 2.6),
        saturation=(1.05, 1.30), rescale=(1.0, 1.3),
        jpeg_q=(75, 96), codec="heic",
    ),
    # Hand-held LOW LIGHT / dim interior lifted by AE: high gain, heavy signal-dependent noise,
    # AGGRESSIVE denoise that smears fine glass texture, over-sharpening to claw detail back,
    # warm AWB drift, motion blur likely, HEIC. The hardest joint for a de-lighter.
    "low_light_handheld": dict(
        ev=(0.2, 1.1), awb_r=(0.98, 1.18), awb_b=(0.82, 1.02),
        vignette=(0.06, 0.20), color_shading=(0.01, 0.05), ca_px=(0.4, 1.8),
        read_noise=(0.006, 0.020), shot_noise=(0.015, 0.045),
        blur_sigma=(0.4, 1.8), motion_prob=0.55,
        hl_compress=(0.5, 1.6), local_contrast=(0.25, 0.7), local_radius=(10, 34),
        denoise=(0.06, 0.16), sharpen=(0.8, 1.8), sharpen_radius=(1.0, 2.4),
        saturation=(0.90, 1.15), rescale=(1.1, 1.6),
        jpeg_q=(45, 82), codec="heic",
    ),
    # Android "punchy" tuning: saturation-forward, strong edge sharpening HALOS, moderate
    # tonemap, more CA, JPEG output at variable quality (chat/upload recompression).
    "android_punchy": dict(
        ev=(-0.5, 0.5), awb_r=(0.90, 1.12), awb_b=(0.90, 1.12),
        vignette=(0.03, 0.15), color_shading=(0.0, 0.03), ca_px=(0.5, 2.2),
        read_noise=(0.002, 0.010), shot_noise=(0.006, 0.022),
        blur_sigma=(0.0, 1.0), motion_prob=0.3,
        hl_compress=(0.4, 1.3), local_contrast=(0.3, 0.8), local_radius=(8, 26),
        denoise=(0.02, 0.09), sharpen=(1.0, 2.4), sharpen_radius=(0.9, 2.0),
        saturation=(1.10, 1.45), rescale=(1.0, 1.4),
        jpeg_q=(40, 88), codec="jpeg",
    ),
    # Ultra-wide / cheap-lens capture: dominant lens shading (vignette + colour shading) and
    # strong CA at the edges, softish optics, otherwise moderate. Stresses the spatial (non-
    # uniform-over-the-frame) nuisance axis the old independent knobs entirely lacked.
    "wide_edge": dict(
        ev=(-0.5, 0.4), awb_r=(0.92, 1.10), awb_b=(0.92, 1.10),
        vignette=(0.14, 0.34), color_shading=(0.03, 0.09), ca_px=(1.2, 3.5),
        read_noise=(0.002, 0.010), shot_noise=(0.006, 0.020),
        blur_sigma=(0.2, 1.2), motion_prob=0.25,
        hl_compress=(0.3, 1.1), local_contrast=(0.2, 0.6), local_radius=(10, 30),
        denoise=(0.02, 0.08), sharpen=(0.5, 1.4), sharpen_radius=(1.0, 2.2),
        saturation=(0.95, 1.20), rescale=(1.1, 1.5),
        jpeg_q=(55, 90), codec="jpeg",
    ),
}
PRESET_NAMES = tuple(PRESETS.keys())


def _u(rng, rng_pair):
    return float(rng.uniform(rng_pair[0], rng_pair[1]))


def _radius_map(H, W):
    """Normalized radius in [0, ~1] at the frame corners, plus the (cx, cy) center."""
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    norm = np.hypot(cx, cy) + 1e-6
    r = np.hypot(xs - cx, ys - cy) / norm
    return r, cx, cy


# --------------------------------------------------------------------------- ISP stages
def _lens_shading(p, rng, vignette, color_shading, rmap):
    """Radial vignette (all channels) + a per-channel colour-shading term (corner tint)."""
    r2 = rmap * rmap
    base = 1.0 - vignette * r2
    out = p * base[..., None]
    if color_shading > 0:
        # corners drift warm/cool: R gains, B loses (or a random sign) toward the edge
        sign = 1.0 if rng.random() < 0.5 else -1.0
        rgain = 1.0 + sign * color_shading * r2
        bgain = 1.0 - sign * color_shading * r2
        out[..., 0] *= rgain
        out[..., 2] *= bgain
    return out


def _chromatic_aberration(p, ca_px, rmap, cx, cy):
    """Lateral CA: magnify R outward and B inward by ca_px at the corner (radial remap)."""
    if ca_px < 0.5:
        return p
    H, W = p.shape[:2]
    xs, ys = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    dx, dy = xs - cx, ys - cy
    # displacement grows with radius; +ca on R (outward), -ca on B (inward)
    scale = rmap  # 0 at center -> 1 at corner
    out = p.copy()
    rad = np.hypot(dx, dy) + 1e-6
    for ch, s in ((0, +ca_px), (2, -ca_px)):
        mx = np.ascontiguousarray(xs + (dx / rad) * scale * s, dtype=np.float32)
        my = np.ascontiguousarray(ys + (dy / rad) * scale * s, dtype=np.float32)
        src = np.ascontiguousarray(p[..., ch], dtype=np.float32)
        out[..., ch] = cv2.remap(src, mx, my, cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
    return out


def _sensor_noise(p, rng, read_noise, shot_noise):
    """Signal-dependent sensor noise in the linear domain: read floor + shot (∝ sqrt(signal))."""
    n = rng.standard_normal(p.shape).astype(np.float32)
    sigma = read_noise + shot_noise * np.sqrt(np.clip(p, 0, None))
    return p + n * sigma


def _optical_blur(p, rng, blur_sigma, motion_prob):
    """Isotropic defocus OR a directional motion blur (handheld)."""
    if blur_sigma < 0.15:
        return p
    if rng.random() < motion_prob:
        # directional motion blur: a line kernel at a random angle
        L = max(3, int(round(blur_sigma * 4)) | 1)
        k = np.zeros((L, L), np.float32)
        k[L // 2, :] = 1.0
        ang = float(rng.uniform(0, 180))
        M = cv2.getRotationMatrix2D((L / 2 - 0.5, L / 2 - 0.5), ang, 1.0)
        k = cv2.warpAffine(k, M, (L, L))
        s = k.sum()
        if s > 0:
            k /= s
        return cv2.filter2D(p, -1, k, borderType=cv2.BORDER_REPLICATE)
    return cv2.GaussianBlur(p, (0, 0), sigmaX=float(blur_sigma), borderType=cv2.BORDER_REPLICATE)


def _tonemap_to_display(p, hl_compress, local_contrast, local_radius):
    """Local HDR / tone mapping. Returns a display-referred [0,1] image.

    Two coupled effects a phone HDR pipeline applies:
      1. HIGHLIGHT COMPRESSION — a Reinhard-ish shoulder in linear pulls blown window
         highlights back under 1.0 instead of hard-clipping them.
      2. LOCAL CONTRAST ("clarity") — unsharp on the TONE image with a LARGE radius. This is
         what creates the signature HDR HALO: a bright/dark ring hugging a high-contrast edge
         (a mullion against a bright pane). Large `local_radius` => wide, visible halos.
    """
    # 1) highlight compression in linear (per-luminance shoulder, preserves hue)
    if hl_compress > 0:
        Y = lum(p)[..., None]
        # Reinhard extended: maps large Y toward 1 with a knee set by hl_compress
        wp = 1.0 + 3.0 / (hl_compress + 1e-3)          # white point: stronger compress => lower wp
        scale = (1.0 + Y / (wp * wp)) / (1.0 + Y)
        p = p * scale
    disp = lin_to_srgb(np.clip(p, 0, 1))               # linear -> display sRGB view
    # 2) local contrast / halos on the display tone image
    if local_contrast > 0:
        rad = float(max(2.0, local_radius))
        base = cv2.GaussianBlur(disp, (0, 0), sigmaX=rad, borderType=cv2.BORDER_REPLICATE)
        disp = disp + local_contrast * (disp - base)
    return np.clip(disp, 0, 1).astype(np.float32)


def _denoise(disp, denoise):
    """Edge-preserving denoise on the display image (bilateral). Smears fine texture — the
    real cost of a strong denoiser, and the reason low-light captures lose glass grain."""
    if denoise < 0.01:
        return disp
    d = cv2.bilateralFilter(disp, d=5, sigmaColor=float(denoise), sigmaSpace=6.0)
    return d


def _sharpen(disp, sharpen, sharpen_radius):
    """Unsharp mask WITH overshoot: disp + amount*(disp - blur). amount>1 => bright/dark HALOS
    at edges (the oversharpened look phones stamp to fight their own denoiser)."""
    if sharpen < 0.05:
        return disp
    base = cv2.GaussianBlur(disp, (0, 0), sigmaX=float(sharpen_radius),
                            borderType=cv2.BORDER_REPLICATE)
    out = disp + sharpen * (disp - base)
    return np.clip(out, 0, 1)


def _saturate(disp, saturation):
    """Saturation multiply around luma (display domain), then per-channel clip to [0,1]."""
    if abs(saturation - 1.0) > 1e-3:
        Y = lum(disp)[..., None]
        disp = Y + saturation * (disp - Y)
    return np.clip(disp, 0, 1)   # per-channel clip (independent channel gamut clipping)


def _rescale(disp, rng, rescale):
    """Resolution loss: downscale by `rescale` then upscale back (simulates a lower-res sensor
    read / an upload resize / digital zoom). No-op when rescale ~ 1."""
    if rescale <= 1.02:
        return disp
    H, W = disp.shape[:2]
    dw, dh = max(8, int(round(W / rescale))), max(8, int(round(H / rescale)))
    small = cv2.resize(disp, (dw, dh), interpolation=cv2.INTER_AREA)
    up_interp = cv2.INTER_CUBIC if rng.random() < 0.5 else cv2.INTER_LINEAR
    return cv2.resize(small, (W, H), interpolation=up_interp)


def _quantize(disp, rng, jpeg_q, codec):
    """Block/transform quantization. 'jpeg' is a real cv2 JPEG round-trip. 'heic' is
    APPROXIMATED (cv2 has no HEVC-image encoder): HEIC's stronger chroma subsampling +
    smaller blocks are modeled as a chroma-plane smear followed by a high-quality JPEG, which
    reproduces HEIC's characteristic low chroma-noise / soft-chroma-edge signature without the
    blocky luma of a low-quality JPEG. Documented approximation (report 053)."""
    u8 = (np.clip(disp, 0, 1) * 255.0 + 0.5).astype(np.uint8)
    q = int(rng.integers(int(jpeg_q[0]), int(jpeg_q[1]) + 1))
    if codec == "heic":
        # chroma smear in YCrCb, then a high-Q JPEG for the DCT quantization texture
        ycc = cv2.cvtColor(u8, cv2.COLOR_RGB2YCrCb).astype(np.float32)
        ycc[..., 1] = cv2.GaussianBlur(ycc[..., 1], (0, 0), 1.1)
        ycc[..., 2] = cv2.GaussianBlur(ycc[..., 2], (0, 0), 1.1)
        u8 = cv2.cvtColor(np.clip(ycc, 0, 255).astype(np.uint8), cv2.COLOR_YCrCb2RGB)
        q = max(q, 82)
    ok, enc = cv2.imencode(".jpg", u8[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, q])
    if ok:
        u8 = cv2.imdecode(enc, cv2.IMREAD_COLOR)[..., ::-1]
    return u8.astype(np.float32) / 255.0


# --------------------------------------------------------------------------- entry point
def apply_phone_pipeline(photo_lin, rng, preset_name=None, allowed_presets=None):
    """Run one complete device ISP over a scene-linear photo; return scene-linear.

    photo_lin       : HxWx3 float32, scene-linear (generator photo_linear space).
    rng             : np.random.Generator (the loader's stream).
    preset_name     : force a specific preset (for boards / held-out-preset test); else sampled.
    allowed_presets : restrict the random draw to this subset of PRESET_NAMES (the holdout
                      split hands the TRAIN presets here so a test-only device never trains).
    Returns (photo_lin_out, preset_name).
    """
    p = np.ascontiguousarray(photo_lin.astype(np.float32))
    if p.ndim == 2:
        p = np.repeat(p[..., None], 3, -1)
    H, W = p.shape[:2]

    if preset_name is None:
        pool = list(allowed_presets) if allowed_presets else list(PRESET_NAMES)
        preset_name = pool[int(rng.integers(len(pool)))]
    cfg = PRESETS[preset_name]

    rmap, cx, cy = _radius_map(H, W)

    # ---- sensor / linear domain ----
    p = p * float(2.0 ** _u(rng, cfg["ev"]))                              # auto-exposure error
    p[..., 0] *= _u(rng, cfg["awb_r"]); p[..., 2] *= _u(rng, cfg["awb_b"])  # AWB error
    p = _lens_shading(p, rng, _u(rng, cfg["vignette"]),
                      _u(rng, cfg["color_shading"]), rmap)                 # lens shading
    p = _chromatic_aberration(p, _u(rng, cfg["ca_px"]), rmap, cx, cy)      # CA
    p = _sensor_noise(p, rng, _u(rng, cfg["read_noise"]),
                      _u(rng, cfg["shot_noise"]))                          # sensor noise
    p = _optical_blur(p, rng, _u(rng, cfg["blur_sigma"]), cfg["motion_prob"])  # optical blur

    # ---- tone / display domain ----
    disp = _tonemap_to_display(p, _u(rng, cfg["hl_compress"]),
                               _u(rng, cfg["local_contrast"]),
                               _u(rng, cfg["local_radius"]))               # local HDR / tonemap
    disp = _denoise(disp, _u(rng, cfg["denoise"]))                        # denoise
    disp = _sharpen(disp, _u(rng, cfg["sharpen"]), _u(rng, cfg["sharpen_radius"]))  # sharpen+halos
    disp = _saturate(disp, _u(rng, cfg["saturation"]))                    # saturation + clip
    disp = _rescale(disp, rng, _u(rng, cfg["rescale"]))                   # rescale
    disp = _quantize(disp, rng, cfg["jpeg_q"], cfg["codec"])              # JPEG / HEIC

    # ---- decode back to scene-linear (report 025) ----
    return srgb_to_lin(disp).astype(np.float32), preset_name


# --------------------------------------------------------------------------- self test / board
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="phone-pipeline self-test + preset contact strip")
    ap.add_argument("--photo", type=str, default=None, help="a scene-linear .exr photo to run")
    ap.add_argument("--out", type=str, default=os.path.join(HERE, "..", "results", "053",
                                                             "phone_pipeline_strip.jpg"))
    ap.add_argument("--reps", type=int, default=2, help="samples per preset")
    args = ap.parse_args()

    rng = np.random.default_rng(0)
    if args.photo and os.path.exists(args.photo):
        img = cv2.imread(args.photo, cv2.IMREAD_UNCHANGED)
        photo = img[..., ::-1].astype(np.float32) if img.ndim == 3 else img.astype(np.float32)
        if photo.max() > 4.0:
            photo = srgb_to_lin(photo / 255.0)
    else:
        # synthetic test scene: a bright "window" gradient + a dark "mullion" bar + colour patches
        H = W = 384
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        photo = np.zeros((H, W, 3), np.float32)
        photo[...] = (0.15 + 1.6 * (xx / W))[..., None]      # bright window gradient (HDR>1)
        photo[:, W // 2 - 6:W // 2 + 6, :] = 0.02            # dark mullion (high-contrast edge)
        photo[40:120, 40:120] = np.array([0.6, 0.15, 0.12])  # red patch
        photo[40:120, 260:340] = np.array([0.12, 0.35, 0.6])  # blue patch
        photo[260:340, 40:120] = np.array([0.5, 0.5, 0.5])    # gray patch

    def tile(a):
        return (lin_to_srgb(np.clip(a, 0, 1)) * 255).astype(np.uint8)

    rows = []
    orig = tile(photo)
    cv2.putText(orig, "scene-linear IN", (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    for name in PRESET_NAMES:
        cells = [orig]
        for r in range(args.reps):
            out, _ = apply_phone_pipeline(photo, rng, preset_name=name)
            t = tile(out)
            cv2.putText(t, name, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
            cells.append(t)
        rows.append(np.concatenate(cells, 1))
    board = np.concatenate(rows, 0)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    cv2.imwrite(args.out, board[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("wrote", os.path.abspath(args.out), board.shape, "| presets:", PRESET_NAMES)
