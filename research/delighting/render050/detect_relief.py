"""050 auto-detection of relief category + knob settings from ONE user photo.

The CTO requirement (verbatim): the category + settings (hammered, small bumps,
...) must be AUTO-DETECTED from the user photo, not something the user tunes by
trying 8 presets. This module maps: raw photo -> (category, amplitude_bin,
feature_scale_bin, [angle]) -> a procedural preset from relief_presets.

Two detection channels, per the validated lab pattern (VLMs classify glass well,
regress badly -- reports 019-024, vlm_classify.py):
  * CATEGORY: VLM multiple-choice (claude CLI subprocess), 6 explicit options.
  * KNOBS   : (a) classical image statistics on the photo, and (b) VLM
              multiple-choice bins -- both computed so validation can ship the
              more reliable one.

Signals used (mission: for clear glass relief is visible only as glints/shading
in the photo; for streaky/wispy the structure lives in the tint T -> use both):
  * luminance high-frequency energy + dominant bandpass scale + specular glint
    density/contrast  (the relief-glint signal, dominant for clear glass)
  * chroma high-frequency energy + gradient-orientation anisotropy  (the T-borne
    structure, dominant for streaky/wispy)
A derived-from-T pseudo-height normal is also produced as a blend component
where texture is visible in T.
"""
from __future__ import annotations
import json, os, subprocess, hashlib
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".relief_vlm_cache.json")
import relief_presets as RP

# ----------------------------------------------------------------- VLM channel
CAT_LETTERS = {"A": "smooth", "B": "hammered", "C": "granite",
               "D": "seedy", "E": "ripple", "F": "rolling_wave"}
# direction-first prompt: on the synthetic holdout this beat the flat 6-option
# prompt on haiku (fine 0.50->0.58, coarse ->0.67) and, notably, beat SONNET with
# the same prompt (0.33/0.42) -- category detection here is NOT model-capability
# limited, it is genuine single-photo relief ambiguity, so we keep the cheap model.
CAT_PROMPT = """Read the image file at {path} and look at it closely. It is a \
photo of one sheet of art glass. Judge ONLY the SURFACE TEXTURE relief, not the \
colour. Decide FIRST whether the texture is DIRECTIONAL (features clearly line up \
and run one way -- parallel streaks/reeds/pulls) or ISOTROPIC (features look the \
same in all directions -- an all-over field of bumps/cells/seeds with no single \
direction). Only choose ripple if the direction is unmistakable. Then pick \
exactly one:
A) smooth - flat/float/cast, clean surface, essentially no relief
B) hammered - ISOTROPIC all-over field of small rounded dimples/cells (classic cathedral)
C) granite - ISOTROPIC dense fine sandy/stippled tooth, busier and finer than hammered
D) seedy - ISOTROPIC scattered discrete round bumps/seeds/bubbles on a soft surface
E) ripple - DIRECTIONAL parallel streaks/reeds/pulled lines running one way
F) rolling_wave - large coarse smooth waves/folds, centimetre-scale undulation
Reply with ONLY the single letter (A-F)."""

AMP_LETTERS = {"A": "subtle", "B": "medium", "C": "strong"}
AMP_PROMPT = """Read the image file at {path} and look at it. It is a photo of a \
sheet of art glass. How PRONOUNCED / DEEP is its surface texture relief -- how \
strongly do the bumps/waves/streaks catch the light and distort what is seen \
through the glass? Answer with ONLY one letter:
A) subtle - very shallow, the surface is nearly flat, only faint texture
B) medium - a clearly visible but moderate texture
C) strong - deep, bold texture with strong glints and heavy distortion"""

SCALE_LETTERS = {"A": "fine", "B": "medium", "C": "coarse"}
SCALE_PROMPT = """Read the image file at {path} and look at it. It is a photo of \
a sheet of art glass. How LARGE are the individual surface-texture features (the \
bumps, cells, streak spacing or waves)? Answer with ONLY one letter:
A) fine - tiny, dense features (many per hand-width)
B) medium - moderate features
C) coarse - large features, only a few span the sheet"""


def _cache():
    if os.path.exists(CACHE):
        try:
            return json.load(open(CACHE))
        except Exception:
            return {}
    return {}


def _save_cache(c):
    json.dump(c, open(CACHE, "w"), indent=1)


def _vlm(image_path, prompt, mapping, kind, model="haiku", timeout=120):
    image_path = os.path.abspath(image_path)
    c = _cache()
    key = f"{kind}:{image_path}:{os.path.getmtime(image_path):.0f}"
    if key in c:
        return c[key]
    out = subprocess.run(
        ["claude", "-p", prompt.format(path=image_path),
         "--allowedTools", "Read", "--model", model],
        capture_output=True, text=True, timeout=timeout)
    ans = out.stdout.strip().rstrip(".").upper()[-1:]
    val = mapping.get(ans)
    if val is None:
        raise RuntimeError(f"VLM unparseable {out.stdout!r} for {image_path}")
    c[key] = val
    _save_cache(c)
    return val


def vlm_category(path, model="haiku"):
    return _vlm(path, CAT_PROMPT, CAT_LETTERS, "cat2", model)


def vlm_amplitude(path, model="haiku"):
    return _vlm(path, AMP_PROMPT, AMP_LETTERS, "amp", model)


def vlm_scale(path, model="haiku"):
    return _vlm(path, SCALE_PROMPT, SCALE_LETTERS, "scale", model)


# ------------------------------------------------------------- classical stats
def _load_gray_lab(path, n=384):
    im = Image.open(path).convert("RGB").resize((n, n), Image.LANCZOS)
    rgb = np.asarray(im, np.float32) / 255.0
    # luminance
    lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    # simple opponent chroma (a,b-ish) without full Lab dependency
    ca = rgb[..., 0] - rgb[..., 1]
    cb = 0.5 * (rgb[..., 0] + rgb[..., 1]) - rgb[..., 2]
    return lum, ca, cb


def _radial_psd(img):
    f = np.fft.fftshift(np.fft.fft2(img - img.mean()))
    p = np.abs(f) ** 2
    n = img.shape[0]
    cy = cx = n // 2
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2).astype(int)
    tbin = np.bincount(r.ravel(), p.ravel())
    nbin = np.bincount(r.ravel())
    prof = tbin / np.maximum(nbin, 1)
    return prof  # index = radial freq in cycles/image


def _structure_tensor_aniso(lum):
    gy, gx = np.gradient(lum)
    Jxx = (gx * gx).mean(); Jyy = (gy * gy).mean(); Jxy = (gx * gy).mean()
    tr = Jxx + Jyy
    det = Jxx * Jyy - Jxy * Jxy
    l1 = tr / 2 + np.sqrt(max(tr * tr / 4 - det, 0))
    l2 = tr / 2 - np.sqrt(max(tr * tr / 4 - det, 0))
    aniso = (l1 - l2) / (l1 + l2 + 1e-9)
    angle = 0.5 * np.degrees(np.arctan2(2 * Jxy, Jxx - Jyy))
    return float(aniso), float(angle)


def classical_features(path, n=384):
    lum, ca, cb = _load_gray_lab(path, n)
    # high-frequency luminance energy fraction (glints)
    prof = _radial_psd(lum)
    freqs = np.arange(len(prof))
    lowcut = int(0.03 * n); midcut = int(0.10 * n)
    total = prof[1:].sum() + 1e-9
    hf_lum = prof[midcut:].sum() / total
    # dominant bandpass scale: peak of freq-weighted psd above the DC/low blob
    band = prof.copy(); band[:max(2, lowcut // 3)] = 0
    peak_freq = int(np.argmax(band[: n // 2]))
    peak_scale_frac = (1.0 / peak_freq) if peak_freq > 0 else 0.5  # fraction of image
    # specular glint density + contrast
    thr = np.percentile(lum, 99)
    glints = lum > thr
    spec_contrast = float(np.percentile(lum, 99) - np.percentile(lum, 50))
    # chroma HF (T-borne structure) + anisotropy
    chf = _radial_psd(ca) + _radial_psd(cb)
    chroma_hf = chf[midcut:].sum() / (chf[1:].sum() + 1e-9)
    aniso, angle = _structure_tensor_aniso(lum)
    return {
        "hf_lum": float(hf_lum), "peak_scale_frac": float(peak_scale_frac),
        "spec_contrast": spec_contrast, "chroma_hf": float(chroma_hf),
        "aniso": aniso, "angle_deg": angle,
        "lum_rms": float(lum.std()),
    }


# thresholds (set on the tuning split; see score050.py). Feature-scale bins
# align with relief_presets.SCALE_BINS fractions.
def bin_amplitude(feat):
    # combine glint contrast + hf luminance energy into a relief-strength score
    s = feat["spec_contrast"] * 2.2 + feat["hf_lum"] * 3.0
    if s < 0.26:
        return "subtle"
    if s < 0.55:
        return "medium"
    return "strong"


def bin_scale(feat):
    f = feat["peak_scale_frac"]
    if f < 0.05:
        return "fine"
    if f < 0.14:
        return "medium"
    return "coarse"


def classical_knobs(path):
    feat = classical_features(path)
    return {"amplitude": bin_amplitude(feat), "feature_scale": bin_scale(feat),
            "angle_deg": feat["angle_deg"], "features": feat}


# --------------------------------------------------- T-derived pseudo normal
def t_pseudo_normal(T, strength=6.0):
    """Pseudo-height from the tint map's luminance structure (high-pass), turned
    into a normal. For streaky/wispy the relief-relevant structure lives in T;
    this is a blend component where texture is visible in T. Returns (normal,
    t_structure_score in [0,1])."""
    from scipy.ndimage import gaussian_filter
    if T.ndim == 3:
        L = 0.299 * T[..., 0] + 0.587 * T[..., 1] + 0.114 * T[..., 2]
    else:
        L = T
    hp = L - gaussian_filter(L, sigma=max(2, L.shape[0] // 64))
    score = float(np.clip(hp.std() * 6.0, 0, 1))
    hp = (hp - hp.min()) / (hp.max() - hp.min() + 1e-8)
    nrm = RP.height_to_normal(hp, strength=strength)
    return nrm, score


# ------------------------------------------------------------------ full detect
def detect(path, use_vlm_knobs=False, model="haiku"):
    cat = vlm_category(path, model)
    ck = classical_knobs(path)
    res = {"category": cat,
           "amplitude": ck["amplitude"], "feature_scale": ck["feature_scale"],
           "angle_deg": round(ck["angle_deg"], 1) if cat == "ripple" else None,
           "features": ck["features"], "source": "vlm-cat+classical-knobs"}
    if use_vlm_knobs:
        res["vlm_amplitude"] = vlm_amplitude(path, model)
        res["vlm_scale"] = vlm_scale(path, model)
    return res


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        r = detect(p, use_vlm_knobs=True)
        print(os.path.basename(p), "->", r["category"], r["amplitude"],
              r["feature_scale"], "| vlm:", r.get("vlm_amplitude"), r.get("vlm_scale"))
