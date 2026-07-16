"""050 relief preset bank -- a small, procedural, TILEABLE surface-relief
normal-map generator for the glass preview.

Context (report 047): the relief normal is NOT a fidelity target -- even the
ground-truth normal worsens the match to Cycles truth, because three.js
screen-space refraction turns relief into high-frequency sparkle, not smooth
lensing. But the CTO eye-tested the sparkle and wants it kept AS A PRESENTATION
EFFECT, with the hard requirement that the category + settings be AUTO-DETECTED
from one user photo (report 050's job), never hand-tuned by the end user.

This module is the "bank" side: given a category + <=3 knobs, synthesise a
deterministic, cheap, tileable height field and its tangent-space normal map.
Detection (detect_relief.py) picks the category + knob bins from a photo.

TAXONOMY GROUNDING. The category list and their relief statistics are grounded
in (a) the real sheet-glass corpus classes and (b) our own generator's authored
relief families (generate_synthetic.generate_relief_height), which are the free
synthetic ground truth:

  preset          <- generator recipe family            (bump_distance range, m)
  ------------------------------------------------------------------------------
  smooth          <- (float/cast glass; ~flat)          ~0
  hammered        <- cathedral-green/amber/blue/red     0.0016 - 0.0045
  granite         <- dark-opaque/deep/ruby/slate/...    0.0010 - 0.0030
  seedy           <- wispy-white/opalescent/confetti    0.0008 - 0.0025  (+micro_events)
  ripple          <- streaky-mix/fine/fracture-streamer 0.00015 - 0.0007 (anisotropic)
  rolling_wave    <- baroque-rolling-wave               0.006  - 0.014   (coarsest)

Each preset = category + up to 3 knobs (amplitude, feature_scale, [angle]).
Knobs are exposed to detection as BINS (subtle/medium/strong x fine/medium/coarse).

Tileability: all noise is band-limited in the Fourier domain (periodic by
construction) and discrete stamps wrap around edges, so the resulting height /
normal tile seamlessly -- required for a cheap repeating preview material.
"""
from __future__ import annotations
import numpy as np

# ------------------------------------------------------------------ knob bins
# amplitude bin -> relief height scale (unitless height 0..1 std multiplier;
# maps to the material's normalScale / displacement amplitude).
AMP_BINS = {"subtle": 0.35, "medium": 0.65, "strong": 1.0}
# feature_scale bin -> characteristic feature size as a FRACTION of the tile.
# smaller fraction = finer/denser features.
SCALE_BINS = {"fine": 0.045, "medium": 0.11, "coarse": 0.26}

# Per-category defaults + which bins are meaningful. Values chosen so a
# category rendered at its default bins reproduces the look of its generator
# family (verified by eye against generate_relief_height octave mix).
PRESETS = {
    "smooth": {
        "desc": "float / cast sheet -- essentially flat, only faint sub-mm imperfection",
        "amp_default": "subtle", "scale_default": "fine",
        "amp_floor": 0.06,        # even 'strong' smooth is nearly flat
        "knobs": ["amplitude"],
    },
    "hammered": {
        "desc": "isotropic mm-scale pebbled cells (classic cathedral glass)",
        "amp_default": "medium", "scale_default": "medium",
        "knobs": ["amplitude", "feature_scale"],
    },
    "granite": {
        "desc": "dense fine stipple / granite tooth (rolled dark & textured sheet)",
        "amp_default": "medium", "scale_default": "fine",
        "knobs": ["amplitude", "feature_scale"],
    },
    "seedy": {
        "desc": "sparse discrete round bumps / seeds / small bubbles on a soft ground",
        "amp_default": "medium", "scale_default": "medium",
        "knobs": ["amplitude", "feature_scale"],
    },
    "ripple": {
        "desc": "directional pulled / reeded streaks (streaky & waterglass sheet)",
        "amp_default": "subtle", "scale_default": "medium",
        "knobs": ["amplitude", "feature_scale", "angle"],
    },
    "rolling_wave": {
        "desc": "coarse cm-scale rolling waves (baroque / hammered-coarse sheet)",
        "amp_default": "strong", "scale_default": "coarse",
        "knobs": ["amplitude", "feature_scale"],
    },
}
CATEGORIES = list(PRESETS.keys())


# ------------------------------------------------------------ tileable noise
def _radial_freq(n):
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.fftfreq(n)[None, :]
    return fy, fx, np.sqrt(fy * fy + fx * fx)


def band_noise(n, seed, feat_frac, octaves=3, aniso=1.0, angle_deg=0.0,
               lacunarity=2.2, persistence=0.55):
    """Periodic (tileable) band-limited fractal noise in [0,1].

    feat_frac : dominant feature size as a fraction of the tile (0..0.5).
                center frequency f0 = 1/(feat_frac*n) cycles/pixel.
    aniso     : >1 stretches features ALONG `angle_deg` (produces streaks).
    """
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((n, n))
    F = np.fft.fft2(white)
    fy, fx, _ = _radial_freq(n)
    # rotate the frequency axes so anisotropy aligns with angle_deg
    a = np.radians(angle_deg)
    fu = fx * np.cos(a) + fy * np.sin(a)     # along streak
    fv = -fx * np.sin(a) + fy * np.cos(a)    # across streak
    # anisotropic radial metric: squeeze the along-streak axis so only
    # cross-streak frequencies survive -> long features along the streak.
    fr = np.sqrt((fu / aniso) ** 2 + (fv * aniso) ** 2)
    f0 = 1.0 / max(feat_frac * n, 1.0)       # cycles/pixel
    env = np.zeros((n, n))
    amp, fc = 1.0, f0
    for _ in range(octaves):
        # log-normal bandpass around fc
        with np.errstate(divide="ignore"):
            lr = np.log((fr + 1e-9) / fc)
        env += amp * np.exp(-(lr ** 2) / (2 * 0.5 ** 2))
        amp *= persistence
        fc *= lacunarity
    env[0, 0] = 0.0
    out = np.real(np.fft.ifft2(F * env))
    out -= out.min()
    mx = out.max()
    if mx > 1e-9:
        out /= mx
    return out


def _stamp_seeds(n, seed, feat_frac, density, amp):
    """Discrete round bump/seed events, wrapped for tileability."""
    rng = np.random.default_rng(seed + 991)
    h = np.zeros((n, n))
    r = max(2.0, feat_frac * n * 0.6)
    ncells = int(density * (n / (2 * r)) ** 2)
    yy, xx = np.mgrid[0:n, 0:n]
    for _ in range(max(1, ncells)):
        cy, cx = rng.uniform(0, n, size=2)
        rr = r * rng.uniform(0.6, 1.4)
        # nearest wrapped distance
        dy = np.minimum(np.abs(yy - cy), n - np.abs(yy - cy))
        dx = np.minimum(np.abs(xx - cx), n - np.abs(xx - cx))
        d2 = (dy * dy + dx * dx) / (rr * rr)
        # raised bump with a slightly sunken rim (seed refractive profile)
        prof = np.exp(-d2) - 0.35 * np.exp(-d2 / 3.0)
        h += prof * rng.uniform(0.7, 1.0)
    h -= h.min()
    mx = h.max()
    if mx > 1e-9:
        h /= mx
    return h * amp


# ------------------------------------------------------------ height per preset
def make_height(category, size=512, seed=0, amplitude=None, feature_scale=None,
                angle_deg=None):
    """Return (height[0..1] float32, amp01 float) for a preset + knob bins.

    amplitude/feature_scale accept a bin name (str) or None -> preset default.
    amp01 is the resolved height amplitude (for normalScale / displacement).
    """
    if category not in PRESETS:
        raise ValueError(f"unknown category {category!r}; choices {CATEGORIES}")
    p = PRESETS[category]
    amp_bin = amplitude or p["amp_default"]
    scale_bin = feature_scale or p["scale_default"]
    amp01 = AMP_BINS[amp_bin]
    feat = SCALE_BINS[scale_bin]

    if category == "smooth":
        # faint fine imperfection only; amplitude floored very low
        h = band_noise(size, seed, feat_frac=0.03, octaves=2)
        amp01 = max(p["amp_floor"], amp01 * 0.12)

    elif category == "hammered":
        # isotropic multi-octave pebble; mirrors 0.52 fine + 0.34 mid + 0.14 broad
        h = band_noise(size, seed, feat_frac=feat, octaves=4,
                       persistence=0.55, lacunarity=2.4)

    elif category == "granite":
        # denser + finer than hammered: more octaves, slower falloff
        h = 0.65 * band_noise(size, seed, feat_frac=feat, octaves=4,
                              persistence=0.62, lacunarity=2.6)
        h += 0.35 * band_noise(size, seed + 3, feat_frac=feat * 0.6, octaves=2)

    elif category == "seedy":
        ground = 0.5 * band_noise(size, seed, feat_frac=max(feat, 0.14), octaves=3)
        seeds = _stamp_seeds(size, seed, feat_frac=feat, density=1.0, amp=1.0)
        h = 0.45 * ground + 0.55 * seeds

    elif category == "ripple":
        ang = 90.0 if angle_deg is None else float(angle_deg)
        h = band_noise(size, seed, feat_frac=feat, octaves=3, aniso=4.5,
                       angle_deg=ang, persistence=0.6, lacunarity=2.2)

    elif category == "rolling_wave":
        # coarse, smooth, low octave count (like baroque-rolling-wave)
        h = 0.75 * band_noise(size, seed, feat_frac=max(feat, 0.22), octaves=2,
                              persistence=0.65, lacunarity=2.0)
        h += 0.25 * band_noise(size, seed + 5, feat_frac=max(feat, 0.16), octaves=1)

    h = h - h.min()
    mx = h.max()
    if mx > 1e-9:
        h = h / mx
    return h.astype(np.float32), float(amp01)


def height_to_normal(height, strength=1.0):
    """Tangent-space RGB normal from a scalar height field.
    BYTE-COMPATIBLE with generate_synthetic.height_to_normal so procedural and
    GT normals feed the material identically."""
    gy, gx = np.gradient(height.astype(np.float64))
    nx = -gx * strength
    ny = -gy * strength
    nz = np.ones_like(height, dtype=np.float64)
    n = np.stack([nx, ny, nz], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8
    return (n * 0.5 + 0.5).astype(np.float32)


def make_normal(category, size=512, seed=0, amplitude=None, feature_scale=None,
                angle_deg=None, normal_strength=None):
    """Convenience: height -> normal map (HxWx3 [0,1] float32) for a preset.
    normal_strength scales the gradient; if None, derived from amplitude bin so
    'strong' presets bump harder. Returns (normal, meta)."""
    h, amp01 = make_height(category, size, seed, amplitude, feature_scale, angle_deg)
    strength = (normal_strength if normal_strength is not None
                else 4.0 * amp01 * size / 512.0)
    nrm = height_to_normal(h, strength=strength)
    meta = {"category": category, "size": size, "seed": seed,
            "amplitude": amplitude or PRESETS[category]["amp_default"],
            "feature_scale": feature_scale or PRESETS[category]["scale_default"],
            "angle_deg": angle_deg, "amp01": amp01, "normal_strength": strength}
    return nrm, meta


if __name__ == "__main__":
    import json, sys, os
    # smoke test / preview grid
    out = sys.argv[1] if len(sys.argv) > 1 else None
    for c in CATEGORIES:
        h, amp = make_height(c, size=256, seed=7)
        n, meta = make_normal(c, size=256, seed=7)
        print(f"{c:14s} amp01={amp:.2f} h[{h.min():.2f},{h.max():.2f}] "
              f"grad_rms={np.sqrt(np.mean(np.gradient(h)[0]**2)):.4f}")
    print(json.dumps({"categories": CATEGORIES,
                      "amp_bins": AMP_BINS, "scale_bins": SCALE_BINS}, indent=2))
