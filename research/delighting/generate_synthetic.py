import bpy
import numpy as np
import argparse
import os
import json
import math
import random
import sys
import time
from contextlib import contextmanager

# Ensure we're running in background mode if we want, though this script works either way.
# Usage: python generate_synthetic.py --out DIR --seed N --count M

# ---------------------------------------------------------------------------
# Report: render-at-scale efficiency instrumentation.
#
# Lightweight, non-nested wall-time stage tracking. `stage(name)` blocks are
# scattered inline (never wrapped one inside another) so STAGE_TOTALS sums to
# the in-script wall time exactly -- no double counting from nested regions.
# Buckets, chosen to match the six things that dominate a synthetic-render
# process: hdri_download/hdri_load (network + Blender image decode),
# texture_authoring (numpy/scipy CPU work), scene_build (bpy.ops scene
# construction), main_render (the actual path-traced Cycles render --
# the GPU-bound stage), gt_render (fast samples=1 emission-passthrough GT
# passes -- also GPU, but ~free), image_encode_io (numpy->bpy.data.images
# encode + PNG/EXR writes + meta.json). `_T_SCRIPT_BEGIN` marks the first
# line this script's own Python code runs; the gap between that and the
# process's true wall-clock start (Blender binary init, addon/device
# enumeration, Python/bpy already initialized before -P scripts run) is NOT
# visible from inside the script -- report it externally as
# shell_wall_time - printed TOTAL, the "process startup" bucket.
# ---------------------------------------------------------------------------
_T_SCRIPT_BEGIN = time.perf_counter()
STAGE_TOTALS = {}
STAGE_COUNTS = {}


def _record(name, elapsed):
    STAGE_TOTALS[name] = STAGE_TOTALS.get(name, 0.0) + elapsed
    STAGE_COUNTS[name] = STAGE_COUNTS.get(name, 0) + 1
    print(f"[TIMING] {name}: {elapsed:.4f}s", flush=True)


@contextmanager
def stage(name):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _record(name, time.perf_counter() - t0)


def dump_timings(out_dir):
    """Write the cumulative per-process stage breakdown as JSON so a farm
    supervisor (render_farm.py) can aggregate across shards without scraping
    stdout."""
    script_total = time.perf_counter() - _T_SCRIPT_BEGIN
    payload = {
        "stage_totals_s": {k: round(v, 4) for k, v in STAGE_TOTALS.items()},
        "stage_counts": STAGE_COUNTS,
        "script_total_s": round(script_total, 4),
        "pid": os.getpid(),
    }
    path = os.path.join(out_dir, f"timings_pid{os.getpid()}.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[TIMING] script_total: {script_total:.4f}s", flush=True)
    return payload

def generate_noise(size, scale, seed, octaves=1, persistence=0.55, lacunarity=6.0):
    """Generate 2D value noise, optionally blended across multiple frequency
    octaves.

    Report 021/022: this function has declared an `octaves` parameter since
    the generator's first version, but the body never read it -- every T/h
    noise call was single-frequency, making every recipe's authored texture
    10-300x too spatially smooth vs the real catalog corpus
    (`corpus/appearance_stats.py`'s `hf_energy_frac`). `octaves=1` (the
    default) is BYTE-IDENTICAL to the old single-frequency behavior -- same
    seed, same single `np.random.rand(base_res, base_res)` call, same zoom,
    same normalize -- so every existing caller that doesn't ask for detail
    (e.g. `generate_relief_height`'s own fine/mid/broad calls, which already
    hand-blend three scales the way this function now does generically) is
    unaffected. `octaves>1` blends `octaves` independently-seeded noise
    fields, each `lacunarity`x finer in scale and `persistence`x lower
    amplitude than the last (standard fractal/fBm noise convention), then
    renormalizes the sum to [0,1] once at the end.
    """
    from scipy.ndimage import zoom

    def _band(band_scale, band_seed):
        np.random.seed(band_seed)
        # Report 032 (mirror-symmetry fix): the coarsest octave of large-scale
        # recipes lands at a tiny base_res (cathedral scale=200 @1536 -> 7; at
        # smaller working sizes as low as 2), and a cubic zoom of a 2-7 cell
        # grid produces low-frequency structure that is near mirror-symmetric
        # about the image CENTER for some seeds -- the gallery-flagged
        # cathedral-green artifact (seed700 measured mirror corr ~0.24, seed1234
        # LR ~0.30). Two statistics-preserving guards: (a) a base_res floor of 4
        # (no 2x2 degenerate symmetric cell), and (b) generate a slightly larger
        # grid and crop a per-band random-offset window so the image center is
        # NOT a reflection axis. Neither changes the noise's spatial frequency
        # or amplitude distribution (verified: hf_energy_frac unchanged within
        # noise, report 032 sec WP-A), so the 021/022 hf-energy grounding still
        # holds; it only decorrelates the spurious centered mirror (worst-case
        # corr 0.30 -> 0.13). The offset draw uses the SAME per-band seeded RNG
        # stream, so determinism (same seed -> same texture) is preserved.
        base_res = max(4, int(round(size / band_scale)))
        pad = 2
        low_freq = np.random.rand(base_res + pad, base_res + pad)
        zoom_factor = size / base_res
        img = zoom(low_freq, zoom_factor, order=3)
        H, W = img.shape
        off_y = int(np.random.randint(0, max(1, H - size + 1)))
        off_x = int(np.random.randint(0, max(1, W - size + 1)))
        return img[off_y:off_y + size, off_x:off_x + size]

    octaves = max(1, int(octaves))
    total = np.zeros((size, size), dtype=np.float64)
    amp_sum = 0.0
    amp = 1.0
    band_scale = float(scale)
    for i in range(octaves):
        # offset seed per-band so octaves aren't correlated copies of each
        # other at different zoom factors
        total += amp * _band(max(1.0, band_scale), seed + i * 7919)
        amp_sum += amp
        amp *= persistence
        band_scale /= lacunarity

    noise_img = total / amp_sum
    # Normalize to 0-1
    noise_img = (noise_img - noise_img.min()) / (noise_img.max() - noise_img.min() + 1e-8)
    return noise_img

# ===========================================================================
# Report 032 WP-A texture-authoring overhaul: flow-advected streaks, discrete
# micro-events (seeds/bubbles), and Beer-Lambert T<->height coupling. These are
# pure-numpy primitives (no bpy) mirrored verbatim in corpus/appearance_stats.py
# so the appearance-grounding harness re-derives the exact same recipe fields.
# ===========================================================================

def flow_field(size, seed, base_angle_deg, curl=0.16, curl_scale=5.0):
    """Smooth per-pixel unit flow field: a dominant roll/pull direction plus a
    low-frequency curl perturbation (local eddies). Drives streak advection so
    rolled-glass streaks run along a coherent direction with gentle meander
    instead of the old isotropic-threshold noise (report 029 gap G-1: our
    streaks had no roll-direction anisotropy; report 031: streaky-fine-texture
    and wispy-white misclassified because their streaks didn't read as streaks).
    """
    pert = generate_noise(size, size / curl_scale, seed + 313,
                          octaves=2, persistence=0.6, lacunarity=4.0)
    ang = math.radians(base_angle_deg) + (pert - 0.5) * 2.0 * curl * math.pi
    return np.cos(ang), np.sin(ang)


def advect_streaks(scalar, fx, fy, length=36, step=1.4):
    """Line-integral-convolution smear of `scalar` along flow (fx, fy): walks
    each pixel forward and backward along its local flow direction, averaging
    with a triangular taper (feathered ends). Produces anisotropic streaks
    aligned to the flow -- the core of the flow-advected authoring. Fixed
    per-pixel reference flow (1 resample/step) keeps it ~0.6s at 1536."""
    from scipy.ndimage import map_coordinates
    n = scalar.shape[0]
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    acc = scalar.astype(np.float64).copy()
    wsum = np.ones_like(acc)
    for d in (1.0, -1.0):
        px, py = xx.copy(), yy.copy()
        for k in range(1, length + 1):
            px = px + d * step * fx
            py = py + d * step * fy
            w = 1.0 - (k / (length + 1.0))
            acc += w * map_coordinates(scalar, [py, px], order=1, mode='reflect')
            wsum += w
    return acc / wsum


def streak_selector(size, seed, angle, ws=320, curl=0.14, contrast=1.7, lam=0.18):
    """A [0,1] streak-blend selector authored at working resolution `ws`
    (streaks are large-scale, so LIC at 320 then upscale is exact-enough and
    ~5x cheaper) then bilinear-zoomed to `size`. `contrast` crisps the streak
    edges; `lam` blends in occasional SHARP lamination lines (thresholded then
    advected) -- the sharp laminations real rolled sheets show between color
    pulls."""
    from scipy.ndimage import zoom
    fx, fy = flow_field(ws, seed, angle, curl=curl)
    sel = advect_streaks(
        generate_noise(ws, ws / 6.0, seed + 11, octaves=2, persistence=0.55, lacunarity=4.0),
        fx, fy, length=36)
    sel = (sel - sel.min()) / (sel.max() - sel.min() + 1e-8)
    sel = np.clip((sel - 0.5) * contrast + 0.5, 0, 1)
    if lam > 0:
        lam0 = (generate_noise(ws, ws / 9.0, seed + 29, octaves=1) > 0.82).astype(np.float64)
        sel = np.clip(sel + lam * np.clip(advect_streaks(lam0, fx, fy, length=44) * 3.0, 0, 1), 0, 1)
    return zoom(sel, size / ws, order=1)[:size, :size]


def micro_events(size, seed, density, r_range=(3.0, 8.0)):
    """Discrete refractive seed/bubble events (report 029 gap G-1: bubble/seed
    optics -- bright-core/dark-rim donuts -- were the VLM's single favorite
    authenticity cue for real sheets and we had NONE; report 031 taxon T11).
    Stamps small donut profiles (raised rim + sunken core) into a height delta
    and a small local transmission gain, and returns a footprint mask (exported
    as GT). `density` = expected events per 512x512 tile.
    Returns (height_delta, T_gain, event_mask), all float64 (size,size)."""
    rng = np.random.RandomState(seed + 77)
    n = max(0, int(density * (size / 512.0) ** 2))
    hd = np.zeros((size, size))
    tg = np.zeros((size, size))
    mask = np.zeros((size, size))
    if n == 0:
        return hd, tg, mask
    ys = rng.randint(0, size, n)
    xs = rng.randint(0, size, n)
    rs = rng.uniform(r_range[0], r_range[1], n)
    for x, y, r in zip(xs, ys, rs):
        R = int(math.ceil(r * 2.2))
        y0, y1 = max(0, y - R), min(size, y + R)
        x0, x1 = max(0, x - R), min(size, x + R)
        if y1 <= y0 or x1 <= x0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        dd = np.sqrt((xx - x) ** 2 + (yy - y) ** 2)
        ring = np.exp(-((dd - r * 0.6) / (0.28 * r)) ** 2)
        core = np.exp(-(dd / (0.32 * r)) ** 2)
        hd[y0:y1, x0:x1] += (ring - 0.6 * core)
        tg[y0:y1, x0:x1] += 0.12 * core - 0.05 * ring
        m = (dd < r * 1.1).astype(np.float64)
        mask[y0:y1, x0:x1] = np.maximum(mask[y0:y1, x0:x1], m)
    return hd, tg, mask


def couple_T_to_height(T, height, coupling):
    """Beer-Lambert T<->height coupling (report 029 gap G-3, the most-actionable
    NEW finding: color/lighting rode ON TOP of relief as independent fields).
    Local thickness co-varies with the SAME authored height field: crests
    (high height => thinner glass) transmit lighter AND less saturated; troughs
    (thicker) darker AND more saturated -- because (T_r/T_g)^p moves toward 1
    for p<1. `height` in [0,1]; `coupling` is the fractional thickness swing.
    Mean transmission is ~preserved (symmetric about height=0.5). Applied to the
    authored T that becomes BOTH gt_T (emission GT) and the transmitted photo,
    so the uniform-backlight validate agreement is unaffected."""
    thickness = 1.0 - coupling * (2.0 * height.astype(np.float64) - 1.0)
    return np.clip(T ** thickness[..., None], 0.0, 1.0)

def generate_scribble_mask(size, seed):
    np.random.seed(seed)
    mask = np.zeros((size, size), dtype=np.float32)
    num_lines = np.random.randint(1, 4)
    
    for _ in range(num_lines):
        # Random walk for scribble
        x, y = np.random.randint(0, size, 2)
        steps = np.random.randint(50, 200)
        
        # Smooth random walk using low frequency noise to drive direction
        angle = np.random.uniform(0, 2 * np.pi)
        for s in range(steps):
            if 0 <= x < size and 0 <= y < size:
                # Draw a thick dot
                r = np.random.randint(2, 6)
                ymin = max(0, int(y-r))
                ymax = min(size, int(y+r))
                xmin = max(0, int(x-r))
                xmax = min(size, int(x+r))
                mask[ymin:ymax, xmin:xmax] = 1.0
            
            # Change angle slightly
            angle += np.random.normal(0, 0.3)
            x += np.cos(angle) * np.random.uniform(2, 8)
            y += np.sin(angle) * np.random.uniform(2, 8)
            
    # Soften edges slightly
    from scipy.ndimage import gaussian_filter
    mask = gaussian_filter(mask, sigma=1.0)
    return np.clip(mask, 0, 1)

def generate_relief_height(recipe, size, seed):
    """Ground-truth surface relief for Glass Material v2.

    Earlier synthetic data used an untracked Blender Noise Texture for bump.
    That made rendered photos look more glass-like, but the relief disappeared
    from ground truth, so downstream models were trained to erase the very
    "hammered/lensing" signal that makes glass feel real. This function makes
    relief an explicit material channel.

    Returns:
      height in [0,1] (unitless texture)
      bump_distance in meters for Blender's Bump node
    """
    from scipy.ndimage import gaussian_filter, zoom

    fine = generate_noise(size, scale=18, seed=seed + 101)
    mid = generate_noise(size, scale=55, seed=seed + 102)
    broad = generate_noise(size, scale=180, seed=seed + 103)
    hammered = 0.52 * fine + 0.34 * mid + 0.14 * broad

    rng = random.Random(seed + 107)

    if recipe in ("cathedral-green", "cathedral-amber", "cathedral-blue", "cathedral-red"):
        # Report 022: cathedral-blue/red are the same family of hammered
        # cathedral glass as green/amber (021 gap recipes), just different
        # authored color -- share the relief statistics, not a new surface.
        height = hammered
        bump_distance = rng.uniform(0.0016, 0.0045)
    elif recipe in ("dark-opaque", "dark-deep", "dark-ruby", "dark-slate", "dark-textured"):
        # Report 017: the three new dark-family recipes (very-dark neutral,
        # dark-tinted, medium-dark) share dark-opaque's hammered-relief
        # statistics -- same family of dense rolled glass at different
        # absolute darkness/tint, not a different surface finish. Report 022
        # adds dark-textured (021 gap recipe) to the same family -- it is
        # purely a T/h texture-detail fix, not a new relief profile.
        height = 0.65 * hammered + 0.35 * generate_noise(size, scale=28, seed=seed + 104)
        bump_distance = rng.uniform(0.0010, 0.0030)
    elif recipe in ("streaky-mix", "streaky-fine-texture"):
        # Streaky sheets are smoother, with relief that follows the pull
        # direction instead of isotropic hammered cells. Report 022:
        # streaky-fine-texture (021 gap recipe) is the same pulled-glass
        # relief family as streaky-mix, its gap is in T/h texture detail.
        low = generate_noise(size, scale=220, seed=seed + 105)
        source_rows = max(1, size // 12)
        stretched = zoom(low[:source_rows, :], (size / source_rows, 1), order=3)[:size, :size]
        height = 0.70 * stretched + 0.30 * gaussian_filter(fine, sigma=5.0)
        bump_distance = rng.uniform(0.00015, 0.0007)
    elif recipe in ("wispy-white", "saturated-opalescent"):
        # Report 022: saturated-opalescent (021 gap recipe, the first
        # opalescent-class recipe) shares wispy-white's soft, cellular
        # diffuser relief -- both are milky/diffusing glass families: same
        # relief mechanism, different authored color/haze.
        height = 0.50 * hammered + 0.50 * generate_noise(size, scale=90, seed=seed + 106)
        bump_distance = rng.uniform(0.0008, 0.0025)
    else:
        raise ValueError(f"Unknown recipe: {recipe}")

    height = gaussian_filter(height, sigma=0.7)
    height = (height - height.min()) / (height.max() - height.min() + 1e-8)
    return height.astype(np.float32), float(bump_distance)

def height_to_normal(height, strength=1.0):
    """Convert a scalar height field to tangent-space-ish RGB normal.

    This is not a Blender-rendered normal pass; it is a portable app-facing
    normal map derived from the same relief texture. The renderer can recompute
    normals from height, but saving this gives training/eval a stable target.
    """
    gy, gx = np.gradient(height.astype(np.float64))
    nx = -gx * strength
    ny = -gy * strength
    nz = np.ones_like(height, dtype=np.float64)
    n = np.stack([nx, ny, nz], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8
    return (n * 0.5 + 0.5).astype(np.float32)

def save_numpy_to_image(array, filepath, is_color=True):
    H, W = array.shape[:2]
    
    if not is_color:
        rgba = np.ones((H, W, 4), dtype=np.float32)
        rgba[..., 0] = array
        rgba[..., 1] = array
        rgba[..., 2] = array
    else:
        rgba = np.ones((H, W, 4), dtype=np.float32)
        rgba[..., :3] = array
        
    pixels = rgba.flatten()
    
    name = f"{os.path.basename(filepath)}_{random.randint(0, 99999999)}"
    
    # Always create a new image to prevent Blender caching across variations
    img = bpy.data.images.new(name, width=W, height=H, alpha=False, float_buffer=True)
        
    img.pixels.foreach_set(pixels)
    
    # To avoid Blender's sRGB view transform on PNGs, ALWAYS save as EXR
    if filepath.endswith('.png'):
        filepath = filepath[:-4] + '.exr'
    img.filepath_raw = filepath
    img.file_format = 'OPEN_EXR'

    img.save()

    # We must set colorspace AFTER saving, otherwise Blender zeroes out the pixels!
    img.colorspace_settings.name = 'Linear Rec.709' if is_color else 'Non-Color'

    # Report 025 (units investigation): the EXR guard above does NOT fully avoid
    # the encode it names. Measured directly (a standalone Image.new/foreach_set/
    # save() with no scene/render involved at all): `img.save()` bakes an
    # sRGB-shaped encode into the FILE on disk regardless of format (EXR included)
    # -- e.g. an authored flat 0.09 array lands at ~0.332 in the saved bytes, to
    # the 3rd decimal exactly `srgb_encode(0.09)`. This affects every file this
    # function writes (tex_T/tex_h/tex_mark_mask/tex_height/tex_normal .exr) and,
    # via the identical code path inside render_ground_truths' emission-passthrough
    # GT render below, gt_T/gt_h/gt_mark_mask/gt_height too (017/022 already
    # documented this for gt_T/gt_h specifically; 025 traces the mechanism to this
    # function, not the render/view-transform step, and confirms it is a FILE-WRITE
    # phenomenon: reading `img.pixels` back in-memory right after save(), before
    # `colorspace_settings.name` is reassigned below, still gives the correct
    # authored value -- so the in-memory Image datablock (what the actual glass
    # material's shader nodes consume when this same `img` object is wired into
    # the Roughness/Emission node graph) is NOT affected, only what lands on disk
    # for any external (non-Blender) reader. Net effect: every *.exr/*.png ground-
    # truth file this generator writes is sRGB-shaped-encoded relative to the
    # authored array when read by extract.py/eval_*.py/cv2/PIL/numpy; report 025
    # fixes this on the READ side (`extract.srgb_to_lin` decode in eval_synthetic.
    # py / eval_preview_invariance.py's `load_gt_h`) rather than here, so existing
    # renders (v1/v2/dark-family/render_022/render_023_holdout) stay valid without
    # a re-render -- see report 025 sec "units" for the full writeup. T's own
    # calibration (T_ANCHOR, the continuous anchor) was already fit against this
    # same rendered/encoded gt_T statistic throughout 003-023, so it needed no
    # change; h's authoring (report 021 sec 5) targeted the real corpus's
    # extractor-h_mean statistic (authored-linear units), which is why only h's
    # readers needed a decode.
    return img

def author_glass_arrays(recipe, size=1536, seed=42):
    """The numpy/scipy CPU-only half of texture generation (recipe T/h color
    fields, mark scribble, relief height + derived normal). Pure function of
    (recipe, seed, size) -- no bpy/Blender state touched, nothing here is
    invalidated by bpy.ops.wm.read_factory_settings.

    Report render-at-scale: split out of the old create_glass_textures so it
    can be CACHED across light variations of the same glass piece (same
    recipe+seed) -- see main()'s `_texture_cache`. Before this split, every
    light variation re-ran this entire block from scratch even though its
    output only depends on (recipe, seed), never on the lighting variation.
    """
    np.random.seed(seed)
    _t0_tex = time.perf_counter()

    # ---- Report 022: per-family octave/roughness parameters -------------
    # generate_noise's octaves parameter was declared but unused (021 §3);
    # wiring it up made every recipe's texture detail tunable, so each
    # family gets its own (octaves, persistence, lacunarity) tuned against
    # `corpus/appearance_stats.py`'s hf_energy_frac real per-class medians
    # (cathedral-clear 0.046, opalescent 0.020, wispy 0.017, dark-opaque
    # 0.110). Tuned offline against the pure-numpy recipe re-derivation
    # (appearance_stats.py mirrors these exact constants -- keep both files
    # in sync when touching these). Dark-family's real 0.110 is
    # texture-relief-driven (021 §3), not purely a flat-color-noise
    # property -- (4, 0.6, 6.0) lands the flat-authored-T statistic at
    # ~0.068, a large, deliberate step up from the old ~0.0016 without
    # pretending a flat color noise field alone explains real dark glass's
    # relief-and-lighting-driven texture energy (see report 022 §2 for the
    # honest gap).
    CATHEDRAL_OCT = dict(octaves=4, persistence=0.6, lacunarity=6.0)
    OPALESCENT_OCT = dict(octaves=4, persistence=0.5, lacunarity=5.6)
    WISPY_OCT = dict(octaves=3, persistence=0.5, lacunarity=6.0)
    DARK_OCT = dict(octaves=4, persistence=0.6, lacunarity=6.0)

    if recipe == 'cathedral-green':
        # Report 022 §B: was [0.15,0.55,0.20] (authored Lab C=50.5, ~1.8x
        # real cathedral-clear's median C=28.7 -- 021 §3/§4). Re-picked at
        # the same L/hue, chroma pulled to the real median (Lab 72.2,28.7,
        # 146deg -> this linear value, computed by inverting srgb_to_lab).
        base_color = np.array([0.269, 0.5054, 0.2916])
        noise = generate_noise(size, scale=200, seed=seed, **CATHEDRAL_OCT)
        noise_scaled = (noise * 0.2) - 0.1
        T = np.clip(base_color * (1.0 + noise_scaled[..., None]), 0, 1)
        # Report 022 §B: 0.02 -> 0.09 (real cathedral-clear avg haze,
        # 021 §4 item 1 -- both cathedral recipes were under-hazed too).
        h = np.full((size, size), 0.09, dtype=np.float32)

    elif recipe == 'cathedral-amber':
        # Report 022 §B: was [0.75,0.45,0.08] (authored Lab C=55.8). Same
        # re-pick as cathedral-green: same L/hue (75.3, 84deg), chroma to
        # the real median (28.7).
        base_color = np.array([0.6424, 0.4664, 0.2347])
        noise = generate_noise(size, scale=200, seed=seed, **CATHEDRAL_OCT)
        noise_scaled = (noise * 0.2) - 0.1
        T = np.clip(base_color * (1.0 + noise_scaled[..., None]), 0, 1)
        h = np.full((size, size), 0.09, dtype=np.float32)

    elif recipe == 'dark-opaque':
        base_color = np.array([0.03, 0.035, 0.03])
        noise = generate_noise(size, scale=50, seed=seed, **DARK_OCT)
        noise_scaled = (noise * 0.01) - 0.005
        T = np.clip(base_color + noise_scaled[..., None], 0, 1)
        h = np.full((size, size), 0.3, dtype=np.float32)

    # ---- Report 017: dark-family top-up (anchor's dark end was calibrated
    # by dark-opaque alone). Base colors below are LINEAR authored values
    # chosen from the measured (not assumed) authored->rendered transform:
    # the renderer's gt_T/photo pipeline applies an sRGB-shaped encode
    # between the authored linear texture and what lands in gt_T.exr /
    # the photo (measured directly against synthetic_data_v2's dark-opaque:
    # authored [0.03,0.035,0.03] -> rendered gt_T p99 0.216, matching
    # srgb_encode(0.04) almost exactly -- see report 017 for the check
    # against a second recipe). Base colors here are chosen by INVERTING
    # that measured encode so the three new recipes land at the intended
    # RENDERED p99 targets (flattened-array percentile, T_ANCHOR's own
    # convention -- for a tinted recipe this is the dominant channel's
    # percentile, not the perceptual luminance).
    elif recipe == 'dark-deep':
        # very-dark neutral, target rendered p99 (all channels) ~= 0.05
        base_color = np.array([0.0039, 0.0039, 0.0041])
        noise = generate_noise(size, scale=50, seed=seed, **DARK_OCT)
        noise_scaled = (noise * 0.0012) - 0.0006
        T = np.clip(base_color + noise_scaled[..., None], 0, 1)
        h = np.full((size, size), 0.30, dtype=np.float32)

    elif recipe == 'dark-ruby':
        # dark-tinted, strong color: target rendered p99 (dominant/R
        # channel) ~= 0.12, with G/B held well below for real chroma
        # (not a near-neutral dark like dark-opaque).
        base_color = np.array([0.0143, 0.0023, 0.0027])
        noise = generate_noise(size, scale=50, seed=seed, **DARK_OCT)
        noise_scaled = (noise * 0.0043) - 0.0021
        T = np.clip(base_color + noise_scaled[..., None], 0, 1)
        h = np.full((size, size), 0.20, dtype=np.float32)

    elif recipe == 'dark-slate':
        # medium-dark, blue-grey: target rendered p99 (dominant/B channel)
        # ~= 0.30, bracketing dark-opaque's 0.216 from above.
        base_color = np.array([0.0593, 0.0660, 0.0732])
        noise = generate_noise(size, scale=50, seed=seed, **DARK_OCT)
        noise_scaled = (noise * 0.020) - 0.010
        T = np.clip(base_color + noise_scaled[..., None], 0, 1)
        h = np.full((size, size), 0.15, dtype=np.float32)

    elif recipe == 'streaky-mix':
        # Report 032 WP-A: flow-advected streaks replace the old vertical
        # zoom-stretch. A coherent pull direction (+/-18 deg) with mild curl
        # produces elongated, feathered two-color streaks WITH occasional sharp
        # lamination lines -- reads as rolled streaky glass (029 gap G-1). The
        # fine-detail layer is now at a genuinely fine scale (22, oct 2) so it
        # feeds hf_energy without swamping the macro streak reading that the old
        # isotropic scale-60 amp-0.8 overlay washed out (031: this was why the
        # streaky family lost directionality).
        angle = np.random.uniform(-18, 18)
        sel = streak_selector(size, seed, angle, curl=0.08, contrast=1.9, lam=0.22)
        color1 = np.array([0.9, 0.9, 0.95])
        color2 = np.array([0.3, 0.5, 0.8])
        T = np.clip(color1 * sel[..., None] + color2 * (1 - sel[..., None]), 0, 1)
        h = (0.9 * sel + 0.05 * (1 - sel)).astype(np.float32)
        detail = generate_noise(size, scale=22, seed=seed + 901,
                                octaves=2, persistence=0.55, lacunarity=6.0)
        T = np.clip(T + ((detail * 0.5) - 0.25)[..., None], 0, 1)

    elif recipe == 'wispy-white':
        # Report 032 WP-A: wispy-white was VLM-misclassified as smooth-opal
        # (031 taxon T14) because its wisps read as isotropic milkiness, not
        # streaks. Advect the wisp density field along a pull direction so the
        # milky veils elongate into legible wisps (macro-anisotropy 1.20 ->
        # 2.29 offline). Milky base/haze unchanged.
        from scipy.ndimage import zoom as _zoom
        ws = 320
        angle = np.random.uniform(-25, 25)
        fx, fy = flow_field(ws, seed, angle, curl=0.22)
        wisp0 = generate_noise(ws, ws / 5.5, seed + 1, octaves=3, persistence=0.5, lacunarity=5.0)
        wisp = advect_streaks(wisp0, fx, fy, length=44)
        wisp = (wisp - wisp.min()) / (wisp.max() - wisp.min() + 1e-8)
        wisp = np.clip((wisp - 0.45) * 2.0, 0, 1)
        wisp = _zoom(wisp, size / ws, order=1)[:size, :size]

        base_color = np.array([0.85, 0.87, 0.92])
        wisp_color = np.array([0.55, 0.55, 0.55])

        T = base_color * (1 - wisp[..., None]) + wisp_color * wisp[..., None]
        h = (0.5 + 0.45 * wisp).astype(np.float32)

    # ---- Report 022: five gap recipes from 021 §5 (Lab->linear base_color
    # and haze targets taken verbatim from that report's exemplar-grounded
    # table; class mapping for the extractor/appearance-grounding harnesses:
    # cathedral-blue/red -> cathedral-clear, saturated-opalescent ->
    # opalescent (the FIRST opalescent-class recipe), streaky-fine-texture/
    # dark-textured -> wispy/dark-opaque respectively.)
    elif recipe == 'cathedral-blue':
        # 021 §5 target Lab (45, 45, 255deg); grounded on wissmach-wi341dr.jpg
        # ("Medium Blue Double Rolled", no finish keyword) -- the two nearer
        # neighbors are "Luminescent" (surface-interference) lines, excluded
        # per 021's caveat.
        base_color = np.array([0.0, 0.174, 0.450])
        noise = generate_noise(size, scale=200, seed=seed, **CATHEDRAL_OCT)
        noise_scaled = (noise * 0.2) - 0.1
        T = np.clip(base_color * (1.0 + noise_scaled[..., None]), 0, 1)
        h = np.full((size, size), 0.09, dtype=np.float32)

    elif recipe == 'cathedral-red':
        # 021 §5 target Lab (45, 55, 10deg); grounded on oceanside-of152s.jpg
        # (clean solid red, no caveats).
        base_color = np.array([0.503, 0.043, 0.110])
        noise = generate_noise(size, scale=200, seed=seed, **CATHEDRAL_OCT)
        noise_scaled = (noise * 0.2) - 0.1
        T = np.clip(base_color * (1.0 + noise_scaled[..., None]), 0, 1)
        h = np.full((size, size), 0.09, dtype=np.float32)

    elif recipe == 'saturated-opalescent':
        # 021 §5 target Lab (60, 45, 340deg); grounded on
        # bullseye-0003010030f1010.jpg (clean rose); the other two nearest
        # neighbors are dichroic/Luminescent lines, excluded per 021's
        # caveat. FIRST opalescent-class recipe (021 §3: 21% of the clean
        # corpus, zero prior synthetic coverage).
        base_color = np.array([0.602, 0.172, 0.416])
        noise = generate_noise(size, scale=200, seed=seed, **OPALESCENT_OCT)
        noise_scaled = (noise * 0.2) - 0.1
        T = np.clip(base_color * (1.0 + noise_scaled[..., None]), 0, 1)
        # 021 §5: flat haze 0.55-0.65 (real range up to 0.98); mid of range.
        h = np.full((size, size), 0.60, dtype=np.float32)

    elif recipe == 'streaky-fine-texture':
        # 021 §5 target Lab (55, 40, 30deg); grounded on 3 clean, no-caveat
        # exemplars (bullseye-0023110030f1010.jpg hf0.046,
        # oceanside-of31902s.jpg hf0.064, oceanside-ofr9512x12.jpg hf0.039,
        # mean ~0.05) -- notably FINER than the wispy class median (0.017),
        # which is the entire point of the recipe (021 explicitly separated
        # this gap from ordinary wispy/streaky texture flatness). Unlike
        # streaky-mix's hard two-tone streak mask (which saturates and
        # swamps any added fine detail, see that recipe's comment), this is
        # a SOFT streak-direction brightness modulation on one base color
        # (matching the exemplars' "marbled" look, not a two-color mix)
        # plus a fine-detail layer for the recipe's namesake texture.
        # Report 032 WP-A: this recipe was the WORST legibility failure (031
        # classified it as ring/oval mottle T7, not streaky T12). The old
        # vertical zoom-stretch gave near-zero macro-anisotropy (1.12); a
        # flow-advected soft brightness modulation restores a coherent marbled
        # streak (1.59 offline) while keeping the single-base "marbled" look.
        base_color = np.array([0.549, 0.145, 0.125])
        angle = np.random.uniform(-18, 18)
        sel = streak_selector(size, seed, angle, curl=0.14, contrast=1.5, lam=0.12)
        streak_mod = (sel - 0.5) * 0.55
        T = np.clip(base_color * (1 + streak_mod[..., None]), 0, 1)
        detail = generate_noise(size, scale=20, seed=seed + 902,
                                octaves=3, persistence=0.55, lacunarity=6.0)
        detail_scaled = (detail * 0.18) - 0.09
        T = np.clip(T + detail_scaled[..., None], 0, 1)
        # 021 §5: flat haze 0.25-0.35 (real wispy avg 0.215); mid of range.
        h = np.full((size, size), 0.30, dtype=np.float32)

    elif recipe == 'dark-textured':
        # 021 §5 target Lab (15, 5, 200deg); grounded on 3 clean, no-caveat
        # exemplars (oceanside-of1009s.jpg hf0.369,
        # bullseye-0001000043f1010.jpg hf0.502 -- "clearly ribbed/reeded",
        # wissmach-wblack.jpg hf0.250). 021 §5: this recipe is purely a
        # texture-detail fix (haze already matches the dark family, no gap).
        base_color = np.array([0.012, 0.021, 0.021])
        noise = generate_noise(size, scale=50, seed=seed, **DARK_OCT)
        noise_scaled = (noise * 0.020) - 0.010
        T = np.clip(base_color + noise_scaled[..., None], 0, 1)
        h = np.full((size, size), 0.29, dtype=np.float32)

    else:
        raise ValueError(f"Unknown recipe: {recipe}")

    # ---- texture_authoring stage: the numpy/scipy CPU work above (recipe
    # color/haze fields) plus the mark scribble + relief height + normal
    # derivation below, EXCLUDING the bpy image encode/save calls (those are
    # image_encode_io -- a separate cost with a different hardware profile:
    # this bucket is single-threaded numpy/scipy on CPU, encode is Blender's
    # C++ image write path).
    # ---- Report 032 WP-A: relief FIRST (micro-events + Beer-Lambert coupling
    # both consume the height field), then couple T to it, then derive normal.
    height, bump_distance = generate_relief_height(recipe, size, seed)

    # Discrete micro-events (seeds/bubbles): per-recipe density (events / 512
    # tile). Baked into height (so they lens/refract through the existing bump
    # shader -- report 031's cost note for T11) and into T (a small local
    # transmission perturbation). density 0 disables. A dedicated gt_events GT
    # mask export is deferred to WP-C; the events already show up in gt_height.
    MICRO_EVENT_DENSITY = {
        'cathedral-green': 28, 'cathedral-amber': 28, 'cathedral-blue': 28, 'cathedral-red': 28,
        'streaky-mix': 22, 'streaky-fine-texture': 20,
        'wispy-white': 10, 'saturated-opalescent': 10,
        'dark-opaque': 16, 'dark-deep': 14, 'dark-ruby': 16, 'dark-slate': 18, 'dark-textured': 40,
    }
    density = MICRO_EVENT_DENSITY.get(recipe, 0)
    if density > 0:
        ev_h, ev_t, _ev_mask = micro_events(size, seed + 55, density)
        height = height + 0.08 * ev_h.astype(np.float32)
        height = (height - height.min()) / (height.max() - height.min() + 1e-8)
        T = np.clip(T + ev_t[..., None].astype(np.float32), 0, 1)

    # Beer-Lambert T<->height coupling (029 G-3). Per-recipe swing: clear
    # cathedral shows the most thickness-driven color variation; milky opal the
    # least (light scatters before it traverses a thickness gradient). 0 = off.
    COUPLING = {
        'cathedral-green': 0.22, 'cathedral-amber': 0.22, 'cathedral-blue': 0.22, 'cathedral-red': 0.22,
        'streaky-mix': 0.25, 'streaky-fine-texture': 0.22,
        'wispy-white': 0.14, 'saturated-opalescent': 0.14,
        'dark-opaque': 0.12, 'dark-deep': 0.12, 'dark-ruby': 0.14, 'dark-slate': 0.14, 'dark-textured': 0.18,
    }
    coupling = COUPLING.get(recipe, 0.0)
    if coupling > 0:
        T = couple_T_to_height(T, height, coupling).astype(np.float32)

    # ---- texture_authoring stage also covers the mark scribble + normal
    # derivation below (EXCLUDING the bpy image encode/save -- image_encode_io).
    mark = generate_scribble_mask(size, seed + 5)
    normal = height_to_normal(height, strength=18.0)
    _record('texture_authoring', time.perf_counter() - _t0_tex)

    return T, h, mark, height, normal, bump_distance


def encode_glass_textures(out_dir, T, h, mark, height, normal, bump_distance):
    """The bpy half: upload each numpy array into a fresh bpy.data.images
    datablock and write it to disk. MUST run every light variation --
    bpy.ops.wm.read_factory_settings(use_empty=True) in setup_scene() wipes
    ALL datablocks (including any images from a prior variation), so the
    encode step cannot be cached the way author_glass_arrays() can. This is
    also why save_numpy_to_image() always creates a brand-new image
    datablock (its own docstring/comment: "prevent Blender caching across
    variations") -- that constraint is unchanged here, just factored apart
    from the (cacheable) numpy compute.
    """
    T_path = os.path.join(out_dir, "tex_T.png")
    h_path = os.path.join(out_dir, "tex_h.png")
    mark_path = os.path.join(out_dir, "tex_mark_mask.png")
    height_path = os.path.join(out_dir, "tex_height.png")
    normal_path = os.path.join(out_dir, "tex_normal.png")

    with stage('image_encode_io'):
        img_T = save_numpy_to_image(T, T_path, is_color=True)
        img_h = save_numpy_to_image(h, h_path, is_color=False)
        img_mark = save_numpy_to_image(mark, mark_path, is_color=False)
        img_height = save_numpy_to_image(height, height_path, is_color=False)
        img_normal = save_numpy_to_image(normal, normal_path, is_color=True)

    return img_T, img_h, img_mark, img_height, img_normal, bump_distance


def create_glass_textures(recipe, out_dir, size=1536, seed=42, cache=None):
    """Back-compat entry point: author (or fetch from `cache`) + encode in
    one call. `cache` is an optional dict the caller keeps alive across
    light variations, keyed by (recipe, seed) -- see main()."""
    key = (recipe, seed, size)
    if cache is not None and key in cache:
        T, h, mark, height, normal, bump_distance = cache[key]
    else:
        T, h, mark, height, normal, bump_distance = author_glass_arrays(recipe, size=size, seed=seed)
        if cache is not None:
            cache[key] = (T, h, mark, height, normal, bump_distance)
    return encode_glass_textures(out_dir, T, h, mark, height, normal, bump_distance)

def download_polyhaven_hdri(out_dir):
    """Downloads a small outdoor HDRI from polyhaven if not present."""
    import requests
    hdri_path = os.path.join(out_dir, "sunflowers_1k.hdr")
    if not os.path.exists(hdri_path):
        print("Downloading HDRI...")
        url = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/sunflowers_1k.hdr"
        r = requests.get(url)
        with open(hdri_path, 'wb') as f:
            f.write(r.content)
    return os.path.abspath(hdri_path)


def resolve_hdri_path(out_dir, hdri_dir=None, seed=0):
    """Report render-at-scale: at 20k-sample scale a single downloaded HDRI
    (the historical default) is a lighting-diversity bottleneck, and a live
    polyhaven.org download per fresh --out dir is a single point of failure
    on marketplace nodes with flaky/no egress. If --hdri-dir is given, deter-
    ministically pick one .hdr/.exr file from it (seed-keyed, so the same
    seed always picks the same HDRI -- required for the determinism check),
    no network call. Otherwise fall back to the original single-file
    download-into-out-dir behavior, unchanged, for backward compatibility.
    """
    with stage('hdri_download'):
        if hdri_dir:
            candidates = sorted(
                f for f in os.listdir(hdri_dir)
                if f.lower().endswith(('.hdr', '.exr'))
            )
            if not candidates:
                raise ValueError(f"--hdri-dir {hdri_dir} has no .hdr/.exr files")
            chosen = candidates[seed % len(candidates)]
            path = os.path.abspath(os.path.join(hdri_dir, chosen))
        else:
            path = download_polyhaven_hdri(out_dir)
    return path

# Realistic partial window-frame occluders (report review: the old full mullion
# cross was over-aggressive vs real captures -- a real handheld photo of a sheet
# near a window mostly shows a frame EDGE poking in from one border, not a
# symmetric cross covering the whole pane). Coordinates below are in the glass
# plane's local frame: after setup_scene's (90deg, 0, 0) rotation, local X maps
# 1:1 to world X and local Y maps 1:1 to world Z (world Y is depth/normal), so
# these bounds can be reasoned about as plain 2D image-plane coordinates.
#
# NOTE: the visible half-extent at the occluder's depth is NOT the glass
# plane's own half-size (0.25) -- the camera's default 50mm/36mm lens is
# actually narrower than that (the glass is deliberately oversized so it
# bleeds off all four edges, per the "no borders" comment below), and the
# horizontal/vertical FOV are not equal even for a square render. We must
# derive the true visible box from the camera's own FOV, or bars end up
# almost entirely outside frame (only a sliver of their corner visible).
FRAME_BORDERS = ['top', 'bottom', 'left', 'right']
OCCLUDER_Y = 0.01  # depth offset behind the glass (matches the old WindowFrame position)


def add_frame_occluders(cam):
    """Create 1-2 near-black bars hugging edge(s) of the frame, like a real
    photo of a sheet held near a window edge. Returns the occluder params
    (recorded into meta.json) so the dark-occluder-through-clear-glass trap
    stays auditable: these pixels must be visible in the photo but must NOT
    leak into the extracted T.

    `cam` must already be positioned/rotated (called after camera setup) so
    we can compute the true visible frustum box at the occluder's depth.
    """
    dist = abs(OCCLUDER_Y - cam.location.y)
    vis_half_x = dist * math.tan(cam.data.angle_x / 2.0)
    vis_half_z = dist * math.tan(cam.data.angle_y / 2.0)
    margin_x, margin_z = vis_half_x * 1.5, vis_half_z * 1.5  # bars run well past frame -> no floating inner edge

    # Mostly a single edge; occasionally two adjacent edges (a frame corner).
    n_borders = 1 if random.random() < 0.7 else 2
    borders = random.sample(FRAME_BORDERS, n_borders)

    params = []
    for i, border in enumerate(borders):
        reach_frac = random.uniform(0.08, 0.35)   # fraction of the visible half-extent
        jitter_frac = random.uniform(-0.04, 0.04)  # irregular inner edge, not perfectly flush
        darkness = random.uniform(0.005, 0.02)     # near-black, slightly varied

        if border in ('top', 'bottom'):
            thickness = max(0.005, (reach_frac + jitter_frac) * vis_half_z)
        else:
            thickness = max(0.005, (reach_frac + jitter_frac) * vis_half_x)

        lo_x, hi_x = -(vis_half_x + margin_x), (vis_half_x + margin_x)
        lo_z, hi_z = -(vis_half_z + margin_z), (vis_half_z + margin_z)
        if border == 'top':
            x0, x1 = lo_x, hi_x
            z0, z1 = vis_half_z - thickness, vis_half_z + margin_z
        elif border == 'bottom':
            x0, x1 = lo_x, hi_x
            z0, z1 = -(vis_half_z + margin_z), -(vis_half_z - thickness)
        elif border == 'left':
            x0, x1 = -(vis_half_x + margin_x), -(vis_half_x - thickness)
            z0, z1 = lo_z, hi_z
        else:  # right
            x0, x1 = vis_half_x - thickness, vis_half_x + margin_x
            z0, z1 = lo_z, hi_z

        cx, cz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
        bpy.ops.mesh.primitive_plane_add(size=1, location=(cx, OCCLUDER_Y, cz), rotation=(math.radians(90), 0, 0))
        bar = bpy.context.active_object
        bar.name = f"FrameOccluder_{border}"
        bar.scale = (x1 - x0, z1 - z0, 1.0)

        mat_frame = bpy.data.materials.new(name=f"FrameOccluderMat_{i}")
        mat_frame.use_nodes = True
        mat_frame.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (darkness, darkness, darkness, 1)
        bar.data.materials.append(mat_frame)

        params.append({"border": border, "thickness": round(thickness, 4),
                        "reach_frac": round(reach_frac, 4), "darkness": round(darkness, 4)})

    return params


def setup_scene(hdri_path, has_frame=False):
    _t0_scene = time.perf_counter()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    # Try GPU, fallback to CPU
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL' # For Mac
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    scene.cycles.device = 'GPU' if prefs.has_active_device() else 'CPU'
    scene.cycles.max_bounces = 24
    scene.cycles.transparent_max_bounces = 24
    scene.cycles.transmission_bounces = 24
    scene.cycles.use_denoising = True
    scene.cycles.samples = 64 # Use low samples with OpenImageDenoise to speed up rendering
    
    # Standard view transform
    scene.view_settings.view_transform = 'Standard'
    
    scene.render.resolution_x = 1536
    scene.render.resolution_y = 1536
    scene.render.resolution_percentage = 100
    
    # Environment HDRI
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    wnodes = world.node_tree.nodes
    wlinks = world.node_tree.links
    wnodes.clear()
    
    if hdri_path is None:
        # Validate mode: clean transmission target. World is perfectly black.
        wout = wnodes.new('ShaderNodeOutputWorld')
        wbg = wnodes.new('ShaderNodeBackground')
        wbg.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
        wbg.inputs['Strength'].default_value = 1.0
        wlinks.new(wbg.outputs['Background'], wout.inputs['Surface'])
        ev = 0.0
        z_rot = 0.0
        
        # Dedicated white emissive backlight behind the glass (+Y direction)
        bpy.ops.mesh.primitive_plane_add(size=50.0, location=(0, 2.0, 0), rotation=(math.radians(90), 0, 0))
        backlight = bpy.context.active_object
        backlight.name = "WhiteBacklight"
        mat_bl = bpy.data.materials.new(name="BacklightMat")
        mat_bl.use_nodes = True
        nodes_bl = mat_bl.node_tree.nodes
        links_bl = mat_bl.node_tree.links
        for n in nodes_bl: nodes_bl.remove(n)
        emission = nodes_bl.new('ShaderNodeEmission')
        emission.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
        emission.inputs['Strength'].default_value = 1.0
        out_bl = nodes_bl.new('ShaderNodeOutputMaterial')
        links_bl.new(emission.outputs['Emission'], out_bl.inputs['Surface'])
        backlight.data.materials.append(mat_bl)
    else:
        wout = wnodes.new('ShaderNodeOutputWorld')
        wbg = wnodes.new('ShaderNodeBackground')
        wtex = wnodes.new('ShaderNodeTexEnvironment')

        _record('scene_build', time.perf_counter() - _t0_scene)
        with stage('hdri_load'):
            wtex.image = bpy.data.images.load(hdri_path)
        _t0_scene = time.perf_counter()

        wmapping = wnodes.new('ShaderNodeMapping')
        wcoord = wnodes.new('ShaderNodeTexCoord')
        
        wlinks.new(wcoord.outputs['Generated'], wmapping.inputs['Vector'])
        wlinks.new(wmapping.outputs['Vector'], wtex.inputs['Vector'])
        wlinks.new(wtex.outputs['Color'], wbg.inputs['Color'])
        wlinks.new(wbg.outputs['Background'], wout.inputs['Surface'])
        
        # Randomize rotation and EV, tilt slightly so sky is visible
        wmapping.inputs['Rotation'].default_value[0] = random.uniform(math.radians(-5), math.radians(15))
        z_rot = random.uniform(0, math.pi * 2)
        wmapping.inputs['Rotation'].default_value[2] = z_rot
        ev = random.uniform(-1.5, 0.5) # Reduced max EV to prevent overexposure
        wbg.inputs['Strength'].default_value = 2.0 ** ev
    
    # Glass plane - size 0.5 ensures it completely fills the camera view (no borders)
    bpy.ops.mesh.primitive_plane_add(size=0.5, align='WORLD', location=(0, 0, 0), rotation=(math.radians(90), 0, 0))
    glass_obj = bpy.context.active_object
    glass_obj.name = "GlassSheet"

    # Camera - zoomed in so the glass perfectly fills the frame
    bpy.ops.object.camera_add(location=(0, -0.4, 0), rotation=(math.radians(90), 0, 0))
    cam = bpy.context.active_object
    scene.camera = cam

    # Randomize camera slightly
    cam.location.x += random.uniform(-0.02, 0.02)
    cam.location.z += random.uniform(-0.02, 0.02)
    cam.rotation_euler.x += random.uniform(-0.05, 0.05)
    cam.rotation_euler.z += random.uniform(-0.05, 0.05)

    frame_params = []
    if has_frame:
        # Partial window-frame edge(s) entering from the image border(s) --
        # see add_frame_occluders() above. Replaces the old full mullion cross.
        # Needs the camera (for its true FOV/frustum), so must run after it exists.
        frame_params = add_frame_occluders(cam)

    # Dark wall behind camera to block HDRI reflections on the front face (simulates dim interior)
    bpy.ops.mesh.primitive_plane_add(size=5.0, location=(0, -2.0, 0), rotation=(math.radians(90), 0, 0))
    wall = bpy.context.active_object
    wall.name = "DarkWall"
    mat_wall = bpy.data.materials.new(name="WallMat")
    mat_wall.use_nodes = True
    bsdf = mat_wall.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.00, 0.00, 0.00, 1)
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.0
    wall.data.materials.append(mat_wall)

    _record('scene_build', time.perf_counter() - _t0_scene)
    return glass_obj, cam, ev, z_rot, frame_params

def create_glass_material(glass_obj, img_T, img_h, img_mark, img_height, recipe, bump_distance, use_bump=True):
    mat = bpy.data.materials.new(name="GlassMat")
    
    # We must use nodes to set up the material
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    out_node = nodes.new('ShaderNodeOutputMaterial')
    
    tex_T = nodes.new('ShaderNodeTexImage')
    tex_T.image = img_T
    
    tex_h = nodes.new('ShaderNodeTexImage')
    tex_h.image = img_h
    
    tex_mark = nodes.new('ShaderNodeTexImage')
    tex_mark.image = img_mark

    tex_height = nodes.new('ShaderNodeTexImage')
    tex_height.image = img_height
    
    # Physically-based glass using Principled BSDF
    principled = nodes.new('ShaderNodeBsdfPrincipled')
    principled.inputs['IOR'].default_value = 1.5
    
    if 'Transmission Weight' in principled.inputs:
        principled.inputs['Transmission Weight'].default_value = 1.0
    elif 'Transmission' in principled.inputs:
        principled.inputs['Transmission'].default_value = 1.0
        
    # Square the input texture so that Principled BSDF's internal sqrt (for thin glass) cancels out!
    # This ensures the transmitted physical light perfectly matches the gt_T map.
    math_node = nodes.new('ShaderNodeVectorMath')
    math_node.operation = 'MULTIPLY'
    links.new(tex_T.outputs['Color'], math_node.inputs[0])
    links.new(tex_T.outputs['Color'], math_node.inputs[1])
    
    # The transmittance color drives the Base Color
    links.new(math_node.outputs['Vector'], principled.inputs['Base Color'])
    
    # Haze drives the roughness of the transmission
    links.new(tex_h.outputs['Color'], principled.inputs['Roughness'])
    
    # Add grease pencil marks on top
    mark_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    mark_bsdf.inputs['Base Color'].default_value = (0.01, 0.01, 0.01, 1)
    mark_bsdf.inputs['Roughness'].default_value = 0.8
    
    mix_mark = nodes.new('ShaderNodeMixShader')
    links.new(tex_mark.outputs['Color'], mix_mark.inputs['Fac'])
    links.new(principled.outputs['BSDF'], mix_mark.inputs[1])
    links.new(mark_bsdf.outputs['BSDF'], mix_mark.inputs[2])
    
    links.new(mix_mark.outputs['Shader'], out_node.inputs['Surface'])
    
    # Hammered/rolled surface relief (affects glossy and transmitted lensing).
    # Height-texture-driven (tracked material channel, UV-mapped so relief
    # corresponds between a flat sheet capture and pieces cut from it).
    # use_bump=False keeps rendered appearance == authored T,h exactly — used by
    # the assembled-pair benchmark (report 014) for purity; relief/glints are a
    # separate realism axis (Material v2).
    if use_bump:
        bump_node = nodes.new('ShaderNodeBump')
        bump_node.inputs['Distance'].default_value = bump_distance
        links.new(tex_height.outputs['Color'], bump_node.inputs['Height'])
        links.new(bump_node.outputs['Normal'], principled.inputs['Normal'])
    
    glass_obj.data.materials.append(mat)
    
    # Crucial: For Transparent BSDF to work in Cycles with a single plane, 
    # we don't need Solidify. Solidify makes it double-sided, squaring the transmittance.
    # So we remove Solidify completely.
    return mat

def generate_hand_mask(size=512):
    mask = np.zeros((size, size), dtype=np.float32)
    edge = random.choice(['top', 'bottom', 'left', 'right'])
    
    if edge == 'bottom':
        mask[470:512, 150:180] = 1.0 # Index
        mask[450:512, 200:230] = 1.0 # Middle
        mask[460:512, 250:280] = 1.0 # Ring
        mask[480:512, 300:330] = 1.0 # Pinky
    elif edge == 'top':
        mask[0:42, 150:180] = 1.0
        mask[0:62, 200:230] = 1.0
        mask[0:52, 250:280] = 1.0
        mask[0:32, 300:330] = 1.0
    elif edge == 'left':
        mask[150:180, 0:42] = 1.0
        mask[200:230, 0:62] = 1.0
        mask[250:280, 0:52] = 1.0
        mask[300:330, 0:32] = 1.0
    elif edge == 'right':
        mask[150:180, 470:512] = 1.0
        mask[200:230, 450:512] = 1.0
        mask[250:280, 460:512] = 1.0
        mask[300:330, 480:512] = 1.0
        
    # Blur heavily for soft shadow effect (reduced slightly to preserve thin finger shape)
    from scipy.ndimage import gaussian_filter
    mask = gaussian_filter(mask, sigma=10.0)
    return np.clip(mask, 0, 1)

def add_shadow_caster(out_dir):
    # Generate hand mask
    with stage('texture_authoring'):
        hand = generate_hand_mask()
    hand_path = os.path.join(out_dir, 'hand_mask.png')
    with stage('image_encode_io'):
        img_hand = save_numpy_to_image(hand, hand_path, is_color=False)

    _t0_scene = time.perf_counter()
    # Create a plane for the shadow caster
    # Size 0.3 covers the entire 0.28m camera FOV
    # Place it at the camera's X/Z location so it perfectly aligns with the visible frame
    cam = bpy.context.scene.camera
    bpy.ops.mesh.primitive_plane_add(size=0.3, location=(cam.location.x, 0.05, cam.location.z), rotation=(math.radians(90), 0, 0))
    caster = bpy.context.active_object
    caster.name = "ShadowCaster"
    
    mat = bpy.data.materials.new(name="CasterMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    out_node = nodes.new('ShaderNodeOutputMaterial')
    
    tex_hand = nodes.new('ShaderNodeTexImage')
    tex_hand.image = img_hand
    
    # Diffuse BSDF (black) for the hand shadow
    diffuse = nodes.new('ShaderNodeBsdfDiffuse')
    diffuse.inputs['Color'].default_value = (0, 0, 0, 1)
    
    transp = nodes.new('ShaderNodeBsdfTransparent')
    
    mix = nodes.new('ShaderNodeMixShader')
    links.new(tex_hand.outputs['Color'], mix.inputs['Fac'])
    links.new(transp.outputs['BSDF'], mix.inputs[1])
    links.new(diffuse.outputs['BSDF'], mix.inputs[2])
    
    links.new(mix.outputs['Shader'], out_node.inputs['Surface'])
    
    # Cycles handles transparency automatically via node setup.
    
    caster.data.materials.append(mat)
    
    # Rotate slightly for interesting pose
    caster.rotation_euler.z += random.uniform(-0.5, 0.5)
    caster.rotation_euler.x += random.uniform(-0.1, 0.1)

    _record('scene_build', time.perf_counter() - _t0_scene)
    return caster

def render_ground_truths(glass_obj, sample_dir, img_T, img_h, img_mark, img_height, img_normal):
    _t0_scene = time.perf_counter()
    scene = bpy.context.scene

    # Hide the world background for ground truths (make it black)
    world = bpy.context.scene.world
    bg_node = world.node_tree.nodes.get('Background')
    if bg_node:
        orig_strength = bg_node.inputs['Strength'].default_value
        bg_node.inputs['Strength'].default_value = 0.0
        
    # Hide the dark wall if it exists
    wall = bpy.data.objects.get("DarkWall")
    if wall:
        wall.hide_render = True
        
    # Create emission material
    mat_gt = bpy.data.materials.new(name="GT_Mat")
    mat_gt.use_nodes = True
    nodes = mat_gt.node_tree.nodes
    links = mat_gt.node_tree.links
    nodes.clear()
    
    out_node = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    tex_node = nodes.new('ShaderNodeTexImage')
    
    links.new(tex_node.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], out_node.inputs['Surface'])
    
    # Temporarily replace glass material
    orig_mat = glass_obj.data.materials[0]
    glass_obj.data.materials[0] = mat_gt
    
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_depth = '32'
    scene.view_settings.view_transform = 'Raw'
    # NOTE (report 025): 'Raw' here does not fully bypass the sRGB-shaped encode --
    # gt_T/gt_h/gt_mark_mask/gt_height all come out sRGB-shaped-encoded relative to
    # authored units, same mechanism as save_numpy_to_image's tex_*.exr above (see
    # its comment). Not fixed here; see report 025 for the read-side fix and why.

    # Emission shaders don't need many samples
    orig_samples = scene.cycles.samples
    scene.cycles.samples = 1

    _record('scene_build', time.perf_counter() - _t0_scene)

    # Render each GT channel ONCE and save the same render result to both
    # EXR (training/eval target) and PNG (viz/training fallback), instead of
    # the historical render-per-file (10 render calls per sample).
    #
    # Report render-at-scale: measured on the 6-sample M4 baseline, each
    # `bpy.ops.render.render()` call costs ~7s of essentially FIXED per-call
    # overhead at samples=1 (film/denoise/sync bookkeeping -- the emission
    # path-trace itself is trivial), so the 10 GT render calls (427.8s
    # total) cost MORE than the 12 real 64-sample main renders (394.1s).
    # Rendering once per channel and saving twice -- the exact pattern
    # render_sample() below has always used for photo.png/photo_linear.exr
    # -- halves that. Pixel content is unchanged: Cycles renders are
    # deterministic for a fixed scene/seed, so the old PNG (a second,
    # identical render of the same emission scene) had the same pixels as
    # the old EXR's render anyway; both files still go through the same
    # image_settings encode paths as before (EXR 32-bit / PNG 16-bit, per-
    # channel RGB/BW color_mode, view transform 'Raw' -- set above).
    # Verified old-vs-new by file hash (docs/RENDER_AT_SCALE.md,
    # determinism section) and by the --validate gate.
    gt_channels = [
        ("gt_T", img_T, 'RGB'),
        ("gt_h", img_h, 'BW'),
        ("gt_mark_mask", img_mark, 'BW'),
        ("gt_height", img_height, 'BW'),
        ("gt_normal", img_normal, 'RGB'),
    ]
    for gt_name, gt_img, color_mode in gt_channels:
        tex_node.image = gt_img
        with stage('gt_render'):
            bpy.ops.render.render(write_still=False)
        rr = bpy.data.images['Render Result']
        with stage('image_encode_io'):
            scene.render.image_settings.file_format = 'OPEN_EXR'
            scene.render.image_settings.color_depth = '32'
            scene.render.image_settings.color_mode = color_mode
            rr.save_render(os.path.abspath(os.path.join(sample_dir, f"{gt_name}.exr")))

            scene.render.image_settings.file_format = 'PNG'
            scene.render.image_settings.color_depth = '16'
            rr.save_render(os.path.abspath(os.path.join(sample_dir, f"{gt_name}.png")))

    # Restore
    _t1_scene = time.perf_counter()
    glass_obj.data.materials[0] = orig_mat
    scene.view_settings.view_transform = 'Standard'
    scene.cycles.samples = orig_samples
    if bg_node:
        bg_node.inputs['Strength'].default_value = orig_strength
    if wall:
        wall.hide_render = False
    _record('scene_build', time.perf_counter() - _t1_scene)

def render_sample(out_dir, prefix):
    scene = bpy.context.scene

    # Render once -- this is THE main render: full Cycles path trace at
    # scene.cycles.samples (64), 1536x1536, with the transmission/glass
    # bounce settings from setup_scene. The GPU-bound stage.
    with stage('main_render'):
        bpy.ops.render.render(write_still=False)
    img = bpy.data.images['Render Result']

    with stage('image_encode_io'):
        # Save sRGB PNG
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.color_depth = '8'
        img.save_render(os.path.abspath(os.path.join(out_dir, f"{prefix}photo.png")))

        # Save Linear EXR
        scene.render.image_settings.file_format = 'OPEN_EXR'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.color_depth = '32'
        img.save_render(os.path.abspath(os.path.join(out_dir, f"{prefix}photo_linear.exr")))

def parse_args():
    # Because blender consumes some arguments when run via `blender -b -P`, 
    # we filter them out if `--` is present. Otherwise, standard python execution.
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = sys.argv[1:]
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=str, required=True)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--light-variations', type=int, default=3, help="Number of lighting variations per glass piece")
    parser.add_argument('--validate', action='store_true', help="Run in uniform backlight validation mode")
    parser.add_argument('--recipe', type=str, default=None,
                        help="Render only this recipe (targeted top-up, e.g. extra dark-opaque shadow-pair samples)")
    parser.add_argument('--hdri-dir', type=str, default=None,
                        help="Directory of pre-fetched .hdr/.exr files; one is picked "
                             "deterministically per seed (no network call). Falls back to "
                             "the single-file polyhaven download into --out if omitted.")
    return parser.parse_args(argv)

def main():
    args = parse_args()
    
    recipes = ['cathedral-green', 'cathedral-amber', 'dark-opaque', 'streaky-mix', 'wispy-white',
               'dark-deep', 'dark-ruby', 'dark-slate',
               # Report 022: five gap recipes (021 §5)
               'cathedral-blue', 'cathedral-red', 'saturated-opalescent',
               'streaky-fine-texture', 'dark-textured']
    
    os.makedirs(args.out, exist_ok=True)

    # Report render-at-scale: texture authoring (numpy/scipy) depends only on
    # (recipe, seed), never on light variation, but every light-variation
    # iteration used to redo it from scratch because setup_scene()'s
    # read_factory_settings wipes bpy state each time. This cache keeps the
    # AUTHORED ARRAYS alive across a glass piece's light variations (a plain
    # dict, since a single generate_synthetic.py process only ever needs the
    # current glass piece's arrays -- unbounded growth is fine at the sizes
    # --count uses, and each process is short-lived under render_farm.py
    # sharding). The bpy image encode still runs every variation (see
    # encode_glass_textures' docstring) -- only the CPU-bound compute is
    # amortized.
    _texture_cache = {}

    # If count is exactly 5, generate one of each recipe. Otherwise, pick randomly.
    for i in range(args.count):
        seed = args.seed + i
        random.seed(seed)

        # Resolved per-glass-piece (keyed on seed) so an --hdri-dir pack gives
        # lighting diversity across the batch, not one fixed HDRI for the
        # whole run; deterministic (same seed -> same HDRI) for reproducibility.
        # Skipped entirely in --validate mode (setup_scene(None, ...) below
        # never uses it -- no point resolving/downloading).
        hdri_path = None if args.validate else resolve_hdri_path(
            args.out, hdri_dir=args.hdri_dir, seed=seed)

        if args.recipe is not None:
            if args.recipe not in recipes:
                raise ValueError(f"Unknown recipe: {args.recipe}")
            recipe = args.recipe
        elif args.count == 5:
            recipe = recipes[i]
        else:
            recipe = random.choice(recipes)
            
        for v in range(args.light_variations):
            has_shadow = True # Always generate pairs (with and without shadow)
            has_frame = random.random() < 0.20  # partial frame-edge occluder trap (report 012)
            if args.validate:
                has_frame = False # No window mullions blocking transmission during math evaluation
                has_shadow = False # Skip shadow pass entirely during validation
            lighting_id = f"light{random.randint(0, 9999):04d}"

            # Name directory with seed so identical glass pieces are grouped together, but have different lighting IDs
            sample_dir = os.path.join(args.out, f"{recipe}__seed{seed}__{lighting_id}")
            os.makedirs(sample_dir, exist_ok=True)

            print(f"Generating {sample_dir}...")

            # 1. Setup scene FIRST (clears factory settings)
            if args.validate:
                glass_obj, cam, ev, z_rot, frame_params = setup_scene(None, has_frame=has_frame)
            else:
                glass_obj, cam, ev, z_rot, frame_params = setup_scene(hdri_path, has_frame=has_frame)
        
            # 2. Create textures (numpy compute cached across this glass
            # piece's light variations; bpy encode always redone -- see
            # create_glass_textures/_texture_cache comments above)
            img_T, img_h, img_mark, img_height, img_normal, bump_distance = create_glass_textures(
                recipe, sample_dir, size=1536, seed=seed, cache=_texture_cache
            )
            
            # 3. Create material
            with stage('scene_build'):
                mat = create_glass_material(
                    glass_obj, img_T, img_h, img_mark, img_height, recipe, bump_distance
                )
        
            metadata = {
                "glass_name": f"{recipe}_{seed}",
                "class_label": recipe,
                "hdri_name": "UniformWhite" if args.validate else os.path.basename(hdri_path),
                "hdri_rotation": z_rot,
                "hdri_ev": ev,
                "has_frame": has_frame,
                "frame_occluders": frame_params,
                "camera_pose": {
                    "location": list(cam.location),
                    "rotation": list(cam.rotation_euler)
                },
                "blender_version": bpy.app.version_string,
                "seed": seed,
                "has_shadow": has_shadow,
                "material_v2": {
                    "channels": ["T", "h", "height", "normal", "mark_mask"],
                    "bump_distance_m": bump_distance,
                    "ior": 1.5
                }
            }
        
            if has_shadow:
                caster = add_shadow_caster(sample_dir)
                
                # Render with shadow
                metadata["shadow_mode"] = "with_shadow"
                render_sample(sample_dir, "with_shadow_")
                
                # Hide caster and render without
                caster.hide_render = True
                metadata["shadow_mode"] = "without_shadow"
                render_sample(sample_dir, "without_shadow_")
                
            else:
                metadata["shadow_mode"] = "none"
                render_sample(sample_dir, "without_shadow_")
                
            # Render aligned ground truths
            render_ground_truths(glass_obj, sample_dir, img_T, img_h, img_mark, img_height, img_normal)
                
            with stage('image_encode_io'):
                with open(os.path.join(sample_dir, 'meta.json'), 'w') as f:
                    json.dump(metadata, f, indent=2)

    dump_timings(args.out)

if __name__ == '__main__':
    main()
