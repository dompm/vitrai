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

# ---------------------------------------------------------------------------
# Report 037 WP-A: GT export v3. Module-level (not threaded through every
# call signature -- see report 037 for the rationale) production-size flags,
# populated once from argparse in main(). All default OFF/None so a plain
# invocation (no new flags) stays byte-compatible with every existing
# dataset, exactly like report 032 WP-B's --specular convention.
#   no_tex_dump: drop tex_*.exr (58% of a validate sample, byte-regenerable
#     from (recipe, seed) -- docs/GT_SPEC.md sec 1a/3).
#   exr_codec:   None = leave Blender's stock ZIP codec; else one of the
#     scene.render.image_settings.exr_codec enum values (DWAA for prod).
#   gt_b:        render gt_B.exr (hidden-glass background, reduced samples).
#   gt_aov:      render gt_veil/gt_index/gt_uv/gt_depth off the main render's
#     compositor passes (docs/GT_SPEC.md sec 1e).
# ---------------------------------------------------------------------------
GT_OPTS = {"no_tex_dump": False, "exr_codec": None, "gt_b": False, "gt_aov": False,
           # Report 039 review-board flags (default None/False = byte-identical to
           # every existing dataset). fixed_ev pins the HDRI EV instead of the
           # per-seed random draw (representative mid-EV review, not seed-lottery
           # dim/bright); no_marks suppresses the grease-pencil marks so a texture
           # review board / forced-choice test isn't dominated by the mark tell.
           "fixed_ev": None, "no_marks": False}

# Report 037 item D (superseded 043/MMv3-G1, kept only for
# generate_relief_height's shared-relief grouping and comments below): the
# milky-diffuser family. Same two recipes generate_relief_height already
# groups as the "milky/diffusing glass families" (shared relief mechanism).
OPAL_SCATTER_RECIPES = {'wispy-white', 'saturated-opalescent'}


# ---------------------------------------------------------------------------
# Report 043 (MMv3-G1): split the single haze scalar h into a physical pair --
# sigma_s (forward-scatter PSF width, drives a genuine graded LOCAL blur via
# Roughness on the one transmission lobe) and a_glow (diffuse self-glow /
# opal opacity, mixed in via a dedicated Translucent BSDF, independent of
# blur width). docs/MATERIAL_MODEL_V3.md G1 / docs/OUTPUT_CONTRACT.md sec 0.
#
# Why this replaces the report-037 "opal-scatter stopgap": that stopgap mixed
# a second, near-fully-diffuse Principled lobe in at a hard-capped Fac
# (0.6*h) ONLY for the two opal recipes. Two BSDFs mixed at a single shading
# point is not a spatial blur -- Cycles either samples the (still fairly
# directional) primary lobe or jumps straight to the near-diffuse lobe, which
# for an HDRI environment (effectively at infinite distance) samples the
# WHOLE hemisphere uniformly, i.e. the GLOBAL mean of the environment, not a
# local neighborhood blur. There is no dial in between "sharp" and "full
# hemisphere average" -- exactly the "razor-edge damping" the report names:
# a sharp occluder edge gets locally dimmed toward the global mean, never
# actually blurred wider. Real GGX transmission roughness, by contrast, IS a
# continuous local blur (it samples a spread of directions around the ideal
# refraction direction, which maps to a spread of *nearby* background
# positions) that smoothly approaches full diffusion as roughness -> 1 --
# precisely MATERIAL_MODEL_V3.md's own math ("the binary h-mix becomes the
# sigma_s->infinity / a_glow limit"). So: let sigma_s alone drive Roughness on
# the (single) transmission lobe, generously -- for opal recipes this now
# gets real headroom it never had before (previously capped low to leave
# room under the second lobe) -- and keep a_glow as a SEPARATE, smaller,
# genuinely-independent Translucent-BSDF mix for the "hides B via self-glow"
# behavior that pure roughness blur alone doesn't fully capture (multiple
# internal scattering in real milky opal glass).
def decompose_haze(h, recipe):
    """Split authored h (the pre-043 roughness-only scalar) into (sigma_s,
    a_glow) per docs/MATERIAL_MODEL_V3.md G1. First-pass decomposition,
    grounded in the existing per-recipe h authoring (003-023 calibrated) and
    the physical roles each term now plays in the shader -- NOT yet
    independently re-grounded against corpus haze/scatter statistics (that
    full regrounding, MATERIAL_MODEL_V3.md's "re-ground sigma_s/a_glow
    against the corpus haze stats the same way 021/022 grounded color" is
    flagged as follow-up work, same honesty standard as report 037's new-taxa
    colors). Returns float32 arrays, same shape as h.
    """
    h = h.astype(np.float32)
    if recipe in OPAL_SCATTER_RECIPES:
        # Milky/opal family: genuinely wide LOCAL scatter (no longer capped
        # to leave headroom for a second lobe) plus a modest, independent
        # self-glow term.
        sigma_s = np.clip(h * 1.15, 0.0, 0.92).astype(np.float32)
        a_glow = np.clip(h * 0.35, 0.0, 0.35).astype(np.float32)
    else:
        # Every other family: h was already pure roughness (no stopgap) --
        # carries over as sigma_s unchanged (no visual regression vs the
        # existing, CTO-approved output), a_glow=0 (these stay genuinely
        # see-through, not self-glowing).
        sigma_s = h.copy()
        a_glow = np.zeros_like(h, dtype=np.float32)
    return sigma_s, a_glow


def project_h(sigma_s, a_glow):
    """OUTPUT_CONTRACT.md sec 0/1 compatibility projection: h_app =
    a_glow (+) g(sigma_s). g = identity -- sigma_s already lives on the same
    [0,1] roughness-like scale h always used. For every non-opal recipe
    (a_glow==0 everywhere) this is an exact identity on sigma_s, i.e. h_proj
    == the old authored h byte-for-byte -- the compatibility projection is
    only non-trivial where a_glow is genuinely nonzero (the opal family),
    which is precisely where the old h under-stated total haze (it only ever
    carried the primary lobe's roughness, never the second lobe's
    contribution)."""
    a_glow = np.asarray(a_glow, dtype=np.float32)
    sigma_s = np.asarray(sigma_s, dtype=np.float32)
    return np.clip(a_glow + (1.0 - a_glow) * sigma_s, 0.0, 1.0).astype(np.float32)


def apply_exr_codec(scene):
    """Set scene.render.image_settings.exr_codec from GT_OPTS, if requested.
    A no-op (leaves Blender's stock ZIP) when --exr-codec wasn't passed, so
    every existing EXR write site stays byte-compatible by default."""
    if GT_OPTS["exr_codec"]:
        scene.render.image_settings.exr_codec = GT_OPTS["exr_codec"]


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


def streak_selector(size, seed, angle, ws=320, curl=0.14, contrast=1.7, lam=0.18,
                    length=100, base_scale=5.0):
    """A [0,1] streak-blend selector authored at working resolution `ws`
    (streaks are large-scale, so LIC at 320 then upscale is exact-enough and
    ~5x cheaper) then bilinear-zoomed to `size`. `contrast` crisps the streak
    edges; `lam` blends in occasional SHARP lamination lines (thresholded then
    advected) -- the sharp laminations real rolled sheets show between color
    pulls.

    Report 039: real Oceanside/Wissmach streaky glass reads as LONG liquid pulls
    spanning most of the sheet (measured structure-tensor coherence ~0.49), not
    blobby mottle. Two changes make the pull long+coherent: (a) `length` (LIC
    advection steps) is now a large default (100, ~44% of ws) so a moderate-scale
    source noise smears into a full-length streak instead of a short dab; (b) the
    source noise is PRE-STRETCHED across-flow (anisotropic generation) so the
    starting blobs are already elongated bands, which advection then folds along
    the flow -- this is what produces the marbled swirl rather than a soft cloud.
    `base_scale` sets how many streaks span the sheet (source scale = ws/base)."""
    from scipy.ndimage import zoom
    fx, fy = flow_field(ws, seed, angle, curl=curl)
    # Pre-stretch: generate the source at coarse cross-flow / fine along-flow by
    # sampling an anisotropic grid, then rotate-advect. Cheap proxy: start from a
    # moderate isotropic field and give advection enough length to dominate.
    base = generate_noise(ws, ws / base_scale, seed + 11, octaves=2,
                          persistence=0.55, lacunarity=4.0)
    sel = advect_streaks(base, fx, fy, length=length)
    # Report 039: median/IQR recentering instead of min-max. Min-max is outlier-
    # driven; after long advection the field concentrates near its mean, and the
    # old additive lam term then pushed the median to ~0.84 -- the sheet went
    # ~80% light-mode and read WASHED (the rejection's 'washed colors'). Real
    # sheets split light/dark ~50/50 (results/039 light_frac p50 = 0.5); pinning
    # the median at 0.5 guarantees that split for every seed.
    med = np.percentile(sel, 50)
    spread = np.percentile(sel, 84) - np.percentile(sel, 16) + 1e-8
    sel = np.clip((sel - med) / spread * 0.55 * contrast + 0.5, 0, 1)
    if lam > 0:
        lam0 = (generate_noise(ws, ws / 9.0, seed + 29, octaves=1) > 0.82).astype(np.float64)
        lam_lines = np.clip(advect_streaks(lam0, fx, fy, length=int(length * 1.3)) * 3.0, 0, 1)
        # lamination lines push toward the light pull but are AREA-BALANCED:
        # subtract the mean shift they introduce so the 50/50 split holds.
        sel = np.clip(sel + lam * (lam_lines - lam_lines.mean()), 0, 1)
    return zoom(sel, size / ws, order=1)[:size, :size]


def filament_layer(size, seed, angle, fil_ws=768, curl=0.45, length=90,
                   thresh=0.90, gain=4.0):
    """Thin smoke-like filament veils (report 032, 2nd legibility round): the
    real wispy/streaky corpus exemplars (e.g. Bullseye 2-Color Mix,
    reports/assets_029/corpus_bullseye-0021000000f1010.jpg) carry razor-thin
    curved filaments folding through the broad veils -- the single strongest
    'streaky' cue, which broad-field LIC alone cannot produce. Mechanism:
    advect a SPARSE thresholded source (small blobs) along a high-curl flow;
    long advection stretches each blob into a thin feathered trail that curves
    with the local eddies. Authored at `fil_ws` (thin structure needs higher
    working res than the broad selector's 320). Returns [0,1] opacity."""
    from scipy.ndimage import zoom
    np.random.seed(seed + 7)
    fx, fy = flow_field(fil_ws, seed + 7, angle, curl=curl, curl_scale=3.0)
    src = (generate_noise(fil_ws, fil_ws / 22.0, seed + 3,
                          octaves=2, persistence=0.5, lacunarity=5.0) > thresh).astype(np.float64)
    fil = advect_streaks(src, fx, fy, length=length, step=1.2)
    fil = np.clip(fil * gain, 0, 1)
    return zoom(fil, size / fil_ws, order=1)[:size, :size]


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


def voronoi_cells(size, seed, n_points):
    """Voronoi partition of the texture plane: `n_points` random seeds,
    per-pixel nearest-seed id and a 'distance to the cell boundary' scalar
    (2nd-nearest minus nearest seed distance -- small near edges, growing
    toward cell interiors). Report 037 item C: the shared generator behind
    the fracture-streamer (T9, thin boundary lines) and confetti-shard (T10,
    filled cells) taxa -- report 031 sec5 recommends exactly this ("often
    the SAME physical product as T9... authoring both together in one
    Voronoi-cell generator is the efficient path"). Uses
    scipy.spatial.cKDTree for the nearest/2nd-nearest query -- cheap even at
    n_points in the dozens and size 1536 (one vectorized query).
    Returns (cell_id int array, edge_dist float32 array), both (size,size)."""
    from scipy.spatial import cKDTree
    rng = np.random.RandomState(seed)
    pts = rng.uniform(0, size, size=(n_points, 2))
    tree = cKDTree(pts)
    yy, xx = np.mgrid[0:size, 0:size]
    query = np.stack([yy.ravel(), xx.ravel()], axis=-1).astype(np.float64)
    dist, idx = tree.query(query, k=2)
    cell_id = idx[:, 0].reshape(size, size)
    edge_dist = (dist[:, 1] - dist[:, 0]).reshape(size, size)
    return cell_id, edge_dist.astype(np.float32)


def ring_mottle_blobs(size, seed, n_blobs, r_range=(28.0, 90.0)):
    """Dense overlapping round/oval opacity field for the ring-mottle taxon
    (T7, report 031 sec2/3/4/5) -- report 037 item C, an explicit blob-
    placement model replacing dark-ruby's accidental fBm resemblance (031
    sec3: "dark-ruby unintentionally reads as this"). Same 'stamp a local
    radial profile, localized to a bounding box' pattern as micro_events(),
    scaled up to body-filling size/density/opacity instead of micro_events'
    sparse subtle donuts. Blobs are alpha-composited (later draws partially
    occlude earlier ones, like real overlapping opaque deposits), each
    slightly oval (independent x/y radius after rotation) and soft-edged.
    Returns an opacity field in [0,1] -- 0 = base body color, 1 = fully
    blob color (see the ring-mottle recipe branch for the color composite)."""
    rng = np.random.RandomState(seed)
    opacity = np.zeros((size, size), dtype=np.float32)
    for _ in range(n_blobs):
        cx, cy = rng.uniform(0, size, 2)
        rx = rng.uniform(*r_range)
        ry = rx * rng.uniform(0.6, 1.3)  # oval, not perfectly round
        ang = rng.uniform(0, math.pi)
        R = int(math.ceil(max(rx, ry) * 1.4))
        x0, x1 = max(0, int(cx - R)), min(size, int(cx + R))
        y0, y1 = max(0, int(cy - R)), min(size, int(cy + R))
        if x1 <= x0 or y1 <= y0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        dx, dy = xx - cx, yy - cy
        ca, sa = math.cos(ang), math.sin(ang)
        u = (dx * ca + dy * sa) / rx
        v = (-dx * sa + dy * ca) / ry
        d = np.sqrt(u * u + v * v)
        alpha = np.clip(1.5 - 1.5 * d, 0, 1) ** 2  # soft radial falloff, opaque core
        sub = opacity[y0:y1, x0:x1]
        opacity[y0:y1, x0:x1] = sub + alpha * (1 - sub)  # alpha-over compositing
    return opacity


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


# ===========================================================================
# Report 039: exemplar-grounded streak color + haze authoring. The maintainer
# rejected the streaky family (3rd attempt) against real Oceanside/Wissmach
# swatches: our streaks read as soft pastel cloud-mottle, real ones are LIQUID
# (long glossy marbled swirls, sharp filament edges coexisting with smooth
# gradients, strong tonal range, SATURATED color pairs) and our gt_h rendered
# near-uniform. The constants below are measured from all 152 clean, non-
# iridescent Wispy/Streaky corpus sheets (corpus/streak_color_pairs_039.py,
# results/039/color_pairs_summary.json) -- NOT invented pastels:
#   light (milky/white pull) mode: L* p25-75 = 53-78 (p50 66), C* p25-75 = 14-41
#   dark  (saturated color)  mode: L* p25-75 = 31-64 (p50 47), C* p25-75 = 16-42,
#                                  C* p90 = 62 (real sheets get very saturated)
#   L*-separation between modes:  p50 14, p75 23, p90 31
#   dark-mode hue mass (chroma-weighted): amber 30-60, yellow-green 60-90,
#     green 120-150, blue/purple 270-300, red 0-30 -- the real streaky palette.
# Old streaky-mix sat at authored L*84 / C*15 (021 grounding): far too pale and
# washed. The rebuild samples a real-grounded pair per seed so each streaky sheet
# is a different real color combination, exactly like the 158-sheet corpus.
# ===========================================================================

# Dark-mode hue anchors (deg) with relative weight ~ measured chroma mass.
_STREAK_DARK_HUES = [
    (45, 3.0), (75, 1.7), (135, 1.6), (285, 1.7), (15, 1.4), (105, 1.4),
    (165, 0.8), (255, 0.5),
]


def _lab_to_linear_rgb(L, a, b):
    """Single CIELab (D65) color -> linear-sRGB [0,1] (clipped to gamut). Matches
    corpus/appearance_stats.py's srgb_to_lab inverse so authored L*/C* land where
    the grounding harness measures them."""
    fy = (L + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0
    d = 6.0 / 29.0

    def finv(t):
        return t ** 3 if t > d else 3 * d * d * (t - 4.0 / 29.0)
    X = 0.95047 * finv(fx)
    Y = 1.0 * finv(fy)
    Z = 1.08883 * finv(fz)
    Minv = np.array([[3.2406, -1.5372, -0.4986],
                     [-0.9689, 1.8758, 0.0415],
                     [0.0557, -0.2040, 1.0570]])
    rgb = Minv @ np.array([X, Y, Z])
    return np.clip(rgb, 0.0, 1.0)


def sample_streak_colors(seed, kind="mix"):
    """Draw a (light_rgb, dark_rgb) LINEAR color pair from the report-039 measured
    real distribution. `kind` biases the palette per recipe:
      'mix'    -> dramatic two-color: bright milky light pull + a SATURATED color
                  (dark mode toward the high-chroma p75-90 the maintainer praised).
      'marble' -> single-hue marbled: both modes share a hue, light = a lighter/
                  desaturated pull of the same color (Wissmach 'Streaky' look).
      'wispy'  -> subtle milky: pale tinted light pull + a soft mid-chroma color.
    Deterministic in `seed`."""
    rng = np.random.RandomState(seed * 2654435761 % (2 ** 31))
    hues, ws = zip(*_STREAK_DARK_HUES)
    hue = float(rng.choice(hues, p=np.array(ws) / sum(ws)))
    hue += rng.uniform(-14, 14)
    # Targets anchored on results/039/color_pairs_summary.json: real streaky
    # sheets sit at L* median ~51 / C* median ~37, with the LIGHT pull a tinted
    # milky (C* p50 ~25, NOT paper-white) only ~14 L* above the dark pull. The
    # per-kind spread places streaky-mix at the dramatic (saturated, higher L*
    # separation) end, wispy-white at the subtle end.
    if kind == "mix":
        dL = rng.uniform(28, 44)
        dC = rng.uniform(44, 62)           # saturated color pull (p75-90 real);
        # sheet-median C dilutes through the sel blend, so the endpoint must sit
        # ABOVE the real per-sheet median for the blended sheet to land on it.
        lL = rng.uniform(60, 72)           # tinted milky, not bright white
        lC = rng.uniform(16, 28)
    elif kind == "marble":
        dL = rng.uniform(32, 48)
        dC = rng.uniform(40, 56)
        lL = rng.uniform(52, 66)           # lighter pull of the SAME hue
        lC = rng.uniform(24, 40)
    else:  # wispy
        dL = rng.uniform(44, 60)
        dC = rng.uniform(20, 34)           # softer color
        lL = rng.uniform(70, 82)
        lC = rng.uniform(10, 20)
    lh = hue if kind == "marble" else (hue + rng.uniform(-30, 30))
    dark = _lab_to_linear_rgb(dL, dC * math.cos(math.radians(hue)), dC * math.sin(math.radians(hue)))
    light = _lab_to_linear_rgb(lL, lC * math.cos(math.radians(lh)), lC * math.sin(math.radians(lh)))
    return light, dark


def streak_haze_field(sel, size, seed, milky_h=0.86, clear_h=0.07, tex_amp=0.10):
    """Report 039: exemplar-grounded haze field for the streak family. The OLD
    authoring made gt_h read near-uniform: streaky-fine-texture used a FLAT h
    (std 0), wispy-white FLOORED h at 0.5 (-> srgb 0.735, 55% of pixels white),
    and every *.exr is sRGB-encoded on write (0.5 authored -> 0.735 on disk),
    which lifts the whole field toward white and compresses the milky-vs-clear
    contrast. Here h FOLLOWS the streak structure -- milky/white pulls are hazy
    (`milky_h`), the saturated interstitial color is much CLEARER (`clear_h`) --
    with a fine multi-octave texture so it is neither flat nor perfectly
    T-correlated. clear_h is pushed genuinely low (0.07 -> srgb 0.29) so that
    after the write-encode the clear glass stays visibly darker than the milky
    streaks (0.86 -> srgb 0.94): a structured gt_h, not a white slab."""
    tex = generate_noise(size, scale=40, seed=seed + 517, octaves=3,
                         persistence=0.5, lacunarity=5.0)
    h = clear_h + (milky_h - clear_h) * np.clip(sel, 0, 1)
    h = h + (tex - 0.5) * tex_amp
    return np.clip(h, 0.02, 0.97).astype(np.float32)


def _stroke_segment_coverage(size, x0, y0, x1, y1, thickness, aa_px=1.1):
    """Anti-aliased distance-to-segment coverage for ONE stroke segment,
    localized to a bounding box (never allocates a full size-x-size field --
    matches the old generate_scribble_mask's per-step local-box approach, so
    a multi-segment scribble stays cheap). Returns (coverage, (y0,y1,x0,x1))
    or None if the segment's box falls entirely off-canvas. `coverage` is a
    true smoothstep falloff (not a hard threshold + blur), report 037 item B
    -- the old mask was a binary fill blurred by a fixed sigma=1.0, which
    doesn't scale with stroke thickness and isn't a real AA edge."""
    r = thickness / 2.0 + aa_px + 1.0
    bx0 = max(0, int(min(x0, x1) - r)); bx1 = min(size, int(max(x0, x1) + r) + 1)
    by0 = max(0, int(min(y0, y1) - r)); by1 = min(size, int(max(y0, y1) + r) + 1)
    if bx1 <= bx0 or by1 <= by0:
        return None
    yy, xx = np.mgrid[by0:by1, bx0:bx1].astype(np.float32)
    dx, dy = x1 - x0, y1 - y0
    seg_len2 = dx * dx + dy * dy
    if seg_len2 < 1e-6:
        t = np.zeros_like(xx)
    else:
        t = np.clip(((xx - x0) * dx + (yy - y0) * dy) / seg_len2, 0.0, 1.0)
    px, py = x0 + t * dx, y0 + t * dy
    dist = np.sqrt((xx - px) ** 2 + (yy - py) ** 2)
    edge0, edge1 = thickness / 2.0 - aa_px, thickness / 2.0 + aa_px
    s = np.clip((edge1 - dist) / max(edge1 - edge0, 1e-6), 0.0, 1.0)
    cov = (s * s * (3.0 - 2.0 * s)).astype(np.float32)  # smoothstep
    return cov, (by0, by1, bx0, bx1)


def _blend_into(canvas, piece):
    if piece is None:
        return
    cov, (y0, y1, x0, x1) = piece
    np.maximum(canvas[y0:y1, x0:x1], cov, out=canvas[y0:y1, x0:x1])


def _draw_scribble(canvas, rng, size, thickness):
    """Random-walk multi-segment stroke (the original shape), rebuilt as
    explicit AA segments with a start/end taper (pen lift-off)."""
    x, y = rng.uniform(0, size), rng.uniform(0, size)
    steps = rng.randint(18, 55)
    angle = rng.uniform(0, 2 * math.pi)
    for s in range(steps):
        angle += rng.gauss(0, 0.35)
        nx = x + math.cos(angle) * rng.uniform(6, 20)
        ny = y + math.sin(angle) * rng.uniform(6, 20)
        taper = min(1.0, 4.0 * s / steps, 4.0 * (steps - s) / steps)
        _blend_into(canvas, _stroke_segment_coverage(
            size, x, y, nx, ny, thickness * (0.5 + 0.5 * taper)))
        x, y = nx, ny


def _draw_straight(canvas, rng, size, thickness):
    """A single confident straight-ish stroke (e.g. an underline or a price
    tick), 1-2 segments with a slight kink, no random-walk wobble."""
    x0, y0 = rng.uniform(0, size), rng.uniform(0, size)
    length = rng.uniform(0.12, 0.4) * size
    angle = rng.uniform(0, 2 * math.pi)
    x1 = x0 + math.cos(angle) * length
    y1 = y0 + math.sin(angle) * length
    _blend_into(canvas, _stroke_segment_coverage(size, x0, y0, x1, y1, thickness))
    if rng.random() < 0.4:  # occasional kink -- a checkmark / bent tick
        angle2 = angle + rng.uniform(0.6, 1.4) * rng.choice([-1, 1])
        x2 = x1 + math.cos(angle2) * length * rng.uniform(0.3, 0.6)
        y2 = y1 + math.sin(angle2) * length * rng.uniform(0.3, 0.6)
        _blend_into(canvas, _stroke_segment_coverage(size, x1, y1, x2, y2, thickness))


def _draw_dot(canvas, rng, size, thickness):
    """A small blob / smudge -- a degenerate zero-length segment renders as
    a round dot via the same distance-field code."""
    x, y = rng.uniform(0, size), rng.uniform(0, size)
    r = thickness * rng.uniform(0.9, 1.6)
    _blend_into(canvas, _stroke_segment_coverage(size, x, y, x, y, r))


def _draw_tick(canvas, rng, size, thickness):
    """Two short crossing segments -- an X / tally-mark cue, distinct from
    the scribble and straight-line families."""
    cx, cy = rng.uniform(0, size), rng.uniform(0, size)
    half = rng.uniform(0.015, 0.035) * size
    a1 = rng.uniform(0, math.pi)
    a2 = a1 + rng.uniform(1.0, 2.1)
    for a in (a1, a2):
        _blend_into(canvas, _stroke_segment_coverage(
            size, cx - math.cos(a) * half, cy - math.sin(a) * half,
            cx + math.cos(a) * half, cy + math.sin(a) * half, thickness))


# report 021 gap recipes + dark family read markedly darker/more saturated in
# reality, where a real glazier's DARK pencil/marker is illegible -- white
# grease-pencil/paint-pen marks are the norm there instead (029's mark note).
# Clear/light recipes see the reverse: dark marker is what's legible. This
# dict is the fraction of a sample's marks (when it has any) drawn WHITE.
MARK_WHITE_PROB = {
    'dark-opaque': 0.75, 'dark-deep': 0.8, 'dark-ruby': 0.75, 'dark-slate': 0.75,
    'dark-textured': 0.75, 'cathedral-green': 0.35, 'cathedral-amber': 0.3,
    'cathedral-blue': 0.35, 'cathedral-red': 0.3, 'saturated-opalescent': 0.3,
    'streaky-mix': 0.2, 'streaky-fine-texture': 0.2, 'wispy-white': 0.05,
    # Report 037 item C new taxa: white-mark probability by base brightness,
    # same reasoning as the rest of the table (dark base -> dark marker
    # illegible -> white grease-pencil is the norm).
    'baroque-rolling-wave': 0.3, 'fracture-streamer': 0.25,
    'confetti-shard': 0.2, 'ring-mottle': 0.7,
}
MAX_MARKS = 4  # upper bound on generate_marks' num_marks; also the gt_mark_index normalization divisor

_MARK_SHAPES = [
    ('scribble', 0.45, _draw_scribble),
    ('straight', 0.25, _draw_straight),
    ('dot', 0.15, _draw_dot),
    ('tick', 0.15, _draw_tick),
]


def generate_marks(recipe, size, seed):
    """Report 037 item B mark overhaul (replaces generate_scribble_mask):
    AA strokes (smoothstep distance field, not a fixed-sigma blur), WHITE +
    dark marks (recipe-weighted -- real white grease-pencil is the norm on
    dark glass, dark marker/pencil on light glass), shape/thickness variety
    (scribble/straight/dot/tick), and a per-mark index so downstream GT can
    supervise mark INSTANCES, not just "any mark" coverage.

    Returns (mark_dark, mark_white, mark_index): each (size,size) float32.
    mark_dark/mark_white are per-color union coverage in [0,1] (what drives
    the two marker BSDFs in create_glass_material); mark_index is a 1-based
    per-pixel id of whichever mark has the strongest coverage there (0 =
    no mark) -- texture-space per-mark GT (marks are baked into the
    material, not separate geometry, so they can't use an object-index AOV;
    see docs/GT_SPEC.md sec 1e's gt_index_B row)."""
    rng = random.Random(seed)
    num_marks = 0 if GT_OPTS.get("no_marks") else rng.randint(1, MAX_MARKS)
    white_prob = MARK_WHITE_PROB.get(recipe, 0.3)

    mark_dark = np.zeros((size, size), dtype=np.float32)
    mark_white = np.zeros((size, size), dtype=np.float32)
    mark_index = np.zeros((size, size), dtype=np.float32)
    index_cov = np.zeros((size, size), dtype=np.float32)

    shape_names = [s[0] for s in _MARK_SHAPES]
    shape_weights = [s[1] for s in _MARK_SHAPES]
    shape_fns = {s[0]: s[2] for s in _MARK_SHAPES}

    for i in range(1, num_marks + 1):
        shape = rng.choices(shape_names, weights=shape_weights, k=1)[0]
        thickness = rng.uniform(4.0, 14.0) if shape == 'dot' else rng.uniform(2.0, 8.0)
        canvas = np.zeros((size, size), dtype=np.float32)
        shape_fns[shape](canvas, rng, size, thickness)

        is_white = rng.random() < white_prob
        if is_white:
            np.maximum(mark_white, canvas, out=mark_white)
        else:
            np.maximum(mark_dark, canvas, out=mark_dark)

        take = canvas > index_cov
        # Report 025's "sRGB-shaped on disk" bake (every gt_*/tex_* file
        # goes through it, this render_ground_truths' emission-passthrough
        # re-render included) is only exercised/verified for [0,1] inputs.
        # A raw integer id (1,2,3,4) would round-trip through that encode
        # out of its normal range with unknown clipping behavior -- so the
        # id is stored NORMALIZED (id / MAX_MARKS, MAX_MARKS matching this
        # function's num_marks upper bound) and must be decoded as
        # `round(srgb_to_lin(pixel) * MAX_MARKS)` (see docs/GT_SPEC.md sec 1b).
        mark_index = np.where(take, float(i) / MAX_MARKS, mark_index)
        index_cov = np.where(take, canvas, index_cov)

    return mark_dark, mark_white, mark_index

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
    elif recipe in ("dark-opaque", "dark-deep", "dark-ruby", "dark-slate", "dark-textured", "ring-mottle"):
        # Report 017: the three new dark-family recipes (very-dark neutral,
        # dark-tinted, medium-dark) share dark-opaque's hammered-relief
        # statistics -- same family of dense rolled glass at different
        # absolute darkness/tint, not a different surface finish. Report 022
        # adds dark-textured (021 gap recipe) to the same family -- it is
        # purely a T/h texture-detail fix, not a new relief profile. Report
        # 037 item C: ring-mottle (T7 formalized) joins the same family --
        # it shares dark-ruby's proven-convincing relief precedent (031
        # sec3), the blob body pattern is authored separately in T.
        height = 0.65 * hammered + 0.35 * generate_noise(size, scale=28, seed=seed + 104)
        bump_distance = rng.uniform(0.0010, 0.0030)
    elif recipe in ("streaky-mix", "streaky-fine-texture", "fracture-streamer"):
        # Streaky sheets are smoother, with relief that follows the pull
        # direction instead of isotropic hammered cells. Report 022:
        # streaky-fine-texture (021 gap recipe) is the same pulled-glass
        # relief family as streaky-mix, its gap is in T/h texture detail.
        # Report 037 item C: fracture-streamer (T9) joins the same family --
        # real "Collage"/streamer glass is typically a fairly flat cast/
        # pulled sheet, not heavily hammered, so the thin branching color
        # lines (authored in T) read against a comparably smooth surface.
        low = generate_noise(size, scale=220, seed=seed + 105)
        source_rows = max(1, size // 12)
        stretched = zoom(low[:source_rows, :], (size / source_rows, 1), order=3)[:size, :size]
        height = 0.70 * stretched + 0.30 * gaussian_filter(fine, sigma=5.0)
        bump_distance = rng.uniform(0.00015, 0.0007)
    elif recipe in ("wispy-white", "saturated-opalescent", "confetti-shard"):
        # Report 022: saturated-opalescent (021 gap recipe, the first
        # opalescent-class recipe) shares wispy-white's soft, cellular
        # diffuser relief -- both are milky/diffusing glass families: same
        # relief mechanism, different authored color/haze. Report 037 item
        # C: confetti-shard (T10) joins the same family -- real "Collage"
        # confetti glass is typically a smooth cast sheet (031 sec5/6: same
        # product family as fracture-streamer/T9's line-network variant),
        # closer to wispy-white's soft diffuser surface than the hammered
        # cathedral/dark families.
        height = 0.50 * hammered + 0.50 * generate_noise(size, scale=90, seed=seed + 106)
        bump_distance = rng.uniform(0.0008, 0.0025)
    elif recipe == 'baroque-rolling-wave':
        # T3 (031 sec2/4/5, rank #3): large-scale rolling-wave SURFACE
        # relief, cm-scale, COARSER than the T2 granite/hammered relief
        # every other recipe shares. 031 sec5: "a coarser-scale extension of
        # report 022's fBm octave system (lower octave count, larger
        # lacunarity/scale, higher amplitude)". Built from ONLY the
        # broadest-scale noise (no fine/mid layers -- that's what makes it
        # read as smooth rolling waves, not pebbled granite) at an even
        # larger scale than `broad` above, plus a much bigger bump_distance
        # so the wave amplitude is visually distinct from every hammered
        # family's mm-scale relief.
        rolling = generate_noise(size, scale=420, seed=seed + 108, octaves=2,
                                  persistence=0.65, lacunarity=4.0)
        secondary = generate_noise(size, scale=260, seed=seed + 109, octaves=1)
        height = 0.75 * rolling + 0.25 * secondary
        bump_distance = rng.uniform(0.006, 0.014)  # 2-8x every other family's amplitude
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
    """Report 037 WP-A note -- the disk write is LOAD-BEARING for rendering,
    not just an export: a controlled probe (flat 0.09 texture, emission
    passthrough, samples=1, Raw view) shows the renderer samples the
    file-backed image -- the saved-EXR case renders 0.3318 == srgb_encode
    (0.09) while an unsaved datablock with identical buffer + colorspace tag
    renders 0.0900 raw. So the sRGB-shaped units every downstream file
    carries (gt_T == srgb_encode(authored), the 003-023 T_ANCHOR convention)
    ENTER the pipeline here, through the shader sampling the sRGB-shape-
    encoded file this function writes -- a mechanism correction to report
    025's "the in-memory datablock the shader consumes is correct linear"
    inference (its practical conclusions -- decode files with srgb_to_lin --
    stand). Consequently `--no-tex-dump` must NOT skip this save (a first
    wiring tried that and every render silently changed units, caught by the
    validate gate: cathedral-green MAE 0.0232 -> 0.0142); it instead deletes
    the tex_* files AFTER the sample's renders complete (see main())."""
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

    # To avoid Blender's sRGB view transform on PNGs, ALWAYS save as EXR
    if filepath.endswith('.png'):
        filepath = filepath[:-4] + '.exr'

    img.pixels.foreach_set(pixels)
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
        # Report 039 EXEMPLAR-GROUNDED REBUILD (3rd streak attempt; maintainer
        # rejected the pale-pastel cloud-mottle look against real Oceanside/
        # Wissmach "White Wispy" / "2-Color Mix" swatches). Three fixes, each
        # grounded in results/039 measurements over the 152 real streaky sheets:
        #  (1) SATURATED color pair sampled from the real dark-mode distribution
        #      (C* 34-52, real p60-90) instead of the old washed [0.3,0.5,0.8]
        #      (authored C*15, L*84 -- far too pale, 021 grounding). Per-seed,
        #      so streaky-mix is now a family of real color combinations.
        #  (2) BIMODAL edges: smooth advected veils PLUS hard lamination lines
        #      (streak_selector lam boosted) -- real sheets show sharp filament/
        #      lamination boundaries coexisting with smooth gradients (measured
        #      grad p99/p50 ~8; the old contrast-only sel was too uniformly soft).
        #  (3) STRUCTURED gt_h via streak_haze_field: milky pulls hazy, saturated
        #      interstitial CLEAR -- fixes the near-uniform-white gt_h the
        #      maintainer measured (root cause: sRGB write-encode lifting a
        #      poorly-split h; NOT the 023/025/037 extractor haze retunes, which
        #      were all read-side).
        # Long liquid pulls: fine cross-flow source (base_scale 16 -> many thin
        # streaks) advected far (length 150) with gentle curl gives the marbled
        # swirl + sharp lamination boundaries the real sheets show (coherence
        # ~0.55, matching the measured flame/woc groups). The old isotropic
        # scale-22 fine-detail overlay is GONE -- it read as a fake sandy pebble
        # and washed out directionality (031/039 diagnosis); the thin streaks now
        # carry the high-frequency energy instead.
        angle = np.random.uniform(-20, 20)
        sel = streak_selector(size, seed, angle, curl=0.13, contrast=2.5,
                              lam=0.40, length=150, base_scale=16)
        light, dark = sample_streak_colors(seed, kind="mix")
        T = np.clip(light * sel[..., None] + dark * (1 - sel[..., None]), 0, 1)
        # Thin curved filaments folding through the pulls -- the single strongest
        # 'streaky' cue in the exemplars; lighten toward the milky pull along them.
        fil = filament_layer(size, seed, angle, gain=4.5)
        T = np.clip(T + (light - T) * (0.6 * fil[..., None]), 0, 1)
        sel_h = np.clip(sel + 0.5 * fil, 0, 1)
        h = streak_haze_field(sel_h, size, seed, milky_h=0.88, clear_h=0.06, tex_amp=0.08)

    elif recipe == 'wispy-white':
        # Report 039 rebuild: the milky/subtle end of the streak family (real
        # "Clear with White Wispy" / "Cream" sheets). Kept its soft advected
        # wisps, but (a) the light/dark pair is now sampled from the real
        # distribution (kind='wispy': pale tinted milky + a soft mid-chroma
        # color) instead of the fixed near-white, and (b) h no longer FLOORS at
        # 0.5 (which srgb-encoded to a 0.735 floor -> 55% of gt_h read white).
        # h now follows the wisp structure through streak_haze_field so the
        # clearer interstitial glass stays visibly less hazy in gt_h.
        from scipy.ndimage import zoom as _zoom
        ws = 320
        angle = np.random.uniform(-25, 25)
        fx, fy = flow_field(ws, seed, angle, curl=0.20)
        wisp0 = generate_noise(ws, ws / 9.0, seed + 1, octaves=3, persistence=0.5, lacunarity=5.0)
        wisp = advect_streaks(wisp0, fx, fy, length=95)
        wisp = (wisp - wisp.min()) / (wisp.max() - wisp.min() + 1e-8)
        wisp = np.clip((wisp - 0.38) * 2.4, 0, 1)
        wisp = _zoom(wisp, size / ws, order=1)[:size, :size]

        light, dark = sample_streak_colors(seed, kind="wispy")
        # light = the milky pull (high L), dark = the soft tint showing between
        # wisps. wisp=1 -> milky veil, wisp=0 -> tinted interstitial.
        T = dark * (1 - wisp[..., None]) + light * wisp[..., None]
        fil = filament_layer(size, seed, angle)
        T = np.clip(T + (light - T) * (0.5 * fil[..., None]), 0, 1)
        sel_h = np.clip(wisp + 0.5 * fil, 0, 1)
        # Milky veils hazier, interstitial clearer -- but this family is milkier
        # overall than streaky-mix, so a higher clear_h floor (still well below
        # the milky value, so gt_h keeps structure).
        h = streak_haze_field(sel_h, size, seed, milky_h=0.92, clear_h=0.28, tex_amp=0.08)

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
        # Report 039 rebuild: the single-hue MARBLED end of the streak family
        # (Wissmach "Streaky" -- long liquid pulls of ONE color, lighter/darker
        # marbling rather than a white-on-color two-tone). kind='marble' samples
        # a saturated hue with a lighter same-hue pull (light) and a deeper pull
        # (dark), so the streaks read as tonal marbling within one color, finer
        # than streaky-mix's two-tone. Keeps the recipe's namesake FINE detail
        # (hf ~0.05, above the wispy-class 0.017 median -- 021's original point).
        # The FLAT h=0.30 that made this recipe's gt_h perfectly uniform (std 0,
        # the maintainer's clearest 'lost haze contrast' case) is replaced by a
        # streak-following h so the marbling carries a real haze signal.
        # Finer, tighter pulls than streaky-mix (base_scale 22 -> many thin
        # same-hue striations; this recipe's namesake is FINE texture, hf ~0.05).
        # A small along-flow detail advection adds the fine grain WITHOUT the old
        # isotropic pebble (which mis-read as ring/oval mottle T7, 031/039).
        angle = np.random.uniform(-18, 18)
        sel = streak_selector(size, seed, angle, curl=0.15, contrast=2.2,
                              lam=0.22, length=120, base_scale=22)
        light, dark = sample_streak_colors(seed, kind="marble")
        T = np.clip(dark * (1 - sel[..., None]) + light * sel[..., None], 0, 1)
        fx_d, fy_d = flow_field(size, seed, angle, curl=0.15)
        detail = advect_streaks(generate_noise(size, scale=14, seed=seed + 902,
                                octaves=3, persistence=0.55, lacunarity=6.0),
                                fx_d, fy_d, length=18)
        detail = (detail - detail.min()) / (detail.max() - detail.min() + 1e-8)
        T = np.clip(T + ((detail * 0.12) - 0.06)[..., None], 0, 1)
        # thin curved filament threads over the soft marbling.
        fil = filament_layer(size, seed, angle, gain=4.5)
        T = np.clip(T + (light - T) * (0.5 * fil[..., None]), 0, 1)
        sel_h = np.clip(sel + 0.4 * fil, 0, 1)
        # Marbled single-hue glass is moderately hazy throughout (real wispy avg
        # 0.215) but the pulls still differ; keep the mean near 0.30 with real
        # streak-following structure instead of a flat slab.
        h = streak_haze_field(sel_h, size, seed, milky_h=0.48, clear_h=0.16, tex_amp=0.10)

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

    # ---- Report 037 item C: four new taxa recipes (report 031 sec2/4/5's
    # ranked missing-variety list; targets are STRUCTURAL, per 031 -- none of
    # these taxa has an explicit real-exemplar Lab centroid the way 021 sec5's
    # five gap recipes did, so authored colors below are plausible choices
    # chosen for corpus-hue diversity, not independently re-grounded via
    # nearest-neighbor search. Flagged honestly in report 037; a follow-up
    # gap_exemplars.py-style grounding pass is future work, not blocking.
    elif recipe == 'baroque-rolling-wave':
        # T3 (031 sec2/4/5, rank #3): large-scale rolling-wave SURFACE
        # relief, cm-scale, coarser than the T2 "granite" hammered relief
        # already in every other recipe. 031 sec5: "a coarser-scale
        # extension of report 022's fBm octave system... the generator
        # mechanism already exists" -- so T/h authoring here mirrors the
        # cathedral family (clear glass; T3 is a RELIEF-scale taxon, not a
        # color one) and the actual differentiator is generate_relief_height's
        # dedicated 'baroque-rolling-wave' branch below.
        base_color = np.array([0.30, 0.42, 0.36])  # pale seafoam/aqua-green -- distinct hue from the existing cathedral pair
        noise = generate_noise(size, scale=220, seed=seed, **CATHEDRAL_OCT)
        noise_scaled = (noise * 0.16) - 0.08
        T = np.clip(base_color * (1.0 + noise_scaled[..., None]), 0, 1)
        h = np.full((size, size), 0.10, dtype=np.float32)

    elif recipe == 'fracture-streamer':
        # T9 (031 sec2/4/5, rank #4): thin dark/colored branching crack-like
        # lines, BODY, over a lightly-tinted near-clear base. 031 sec5:
        # "(a) texture authoring only... a thin branching line-network mask
        # (Voronoi-cell-boundary or similar)".
        base_color = np.array([0.42, 0.40, 0.44])  # near-clear cool-grey base -- lets the streamer lines read
        noise = generate_noise(size, scale=200, seed=seed, **WISPY_OCT)
        noise_scaled = (noise * 0.10) - 0.05
        T = np.clip(base_color * (1.0 + noise_scaled[..., None]), 0, 1)
        n_pts = int(30 * (size / 1536.0) ** 2) + 18
        _cell_id, edge_dist = voronoi_cells(size, seed + 900, n_pts)
        line = np.clip(1.0 - edge_dist / 6.0, 0, 1) ** 2  # thin AA boundary network
        line_color = np.array([0.05, 0.03, 0.03])  # dark branching streamer tint
        T = np.clip(T * (1 - line[..., None]) + line_color * line[..., None], 0, 1)
        h = np.full((size, size), 0.12, dtype=np.float32)

    elif recipe == 'confetti-shard':
        # T10 (031 sec2/4/5, rank #5): flat angular non-overlapping color
        # pieces embedded in a clear/white BODY. 031 sec5: "a filled-region
        # variant of the same Voronoi-cell idea behind T9... often the
        # literal same product line as T9 (see exemplars)" -- shares
        # voronoi_cells with fracture-streamer, filled instead of outlined.
        base_color = np.array([0.72, 0.71, 0.68])  # near-white/clear cast base
        n_pts = int(22 * (size / 1536.0) ** 2) + 12
        cell_id, edge_dist = voronoi_cells(size, seed + 900, n_pts)
        rng_c = np.random.RandomState(seed + 901)
        n_cells = int(cell_id.max()) + 1
        palette = rng_c.uniform(0.05, 0.85, size=(n_cells, 3))
        fill_prob = 0.55  # not every cell is a colored "shard" -- some stay clear body
        is_shard = rng_c.random(n_cells) < fill_prob
        cell_color = np.where(is_shard[:, None], palette, base_color[None, :])
        T = cell_color[cell_id].astype(np.float64)
        edge = np.clip(1.0 - edge_dist / 2.5, 0, 1) ** 3  # thin AA seam between shards
        T = np.clip(T * (1 - 0.25 * edge[..., None]), 0, 1)  # subtle seam darkening, not a full boundary blackout
        h = np.full((size, size), 0.10, dtype=np.float32)

    elif recipe == 'ring-mottle':
        # T7 formalized (031 sec2/3/4/5): dense overlapping round/oval
        # opaque blobs, BODY -- an explicit generative model (ring_mottle_
        # blobs), replacing dark-ruby's accidental fBm resemblance (031
        # sec3: "dark-ruby unintentionally reads as this... unintended but
        # convincing"). Grounded on the same dark-tinted family as dark-ruby
        # (the one proven-convincing precedent for this taxon) but a
        # distinct warm amber/rose hue for corpus coverage diversity.
        base_color = np.array([0.10, 0.045, 0.03])
        blob_color = np.array([0.34, 0.12, 0.07])
        n_blobs = int(70 * (size / 1536.0) ** 2) + 30
        blobs = ring_mottle_blobs(size, seed + 950, n_blobs)
        T = (base_color[None, None, :] * (1 - blobs[..., None])
             + blob_color[None, None, :] * blobs[..., None])
        noise = generate_noise(size, scale=50, seed=seed, **DARK_OCT)
        T = np.clip(T + ((noise * 0.006) - 0.003)[..., None], 0, 1)
        h = np.full((size, size), 0.22, dtype=np.float32)

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
        # Report 037 item C: baroque-rolling-wave (cathedral-family clear
        # glass) gets a modest dose too; fracture-streamer/confetti-shard/
        # ring-mottle deliberately omitted (default 0) -- their authored
        # Voronoi/blob body pattern IS the taxon signal, and stacking
        # micro-event donuts on top risks diluting its legibility.
        'baroque-rolling-wave': 15,
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
        # Report 037 item C: baroque-rolling-wave (clear cathedral-family
        # glass, same physical rationale as the other cathedral recipes).
        # fracture-streamer/confetti-shard/ring-mottle deliberately omitted
        # (default 0) -- coupling T to height would blur their discrete
        # Voronoi/blob-authored color structure against the underlying
        # smooth relief field, undercutting the taxon's flat/crisp look.
        'baroque-rolling-wave': 0.20,
    }
    coupling = COUPLING.get(recipe, 0.0)
    if coupling > 0:
        T = couple_T_to_height(T, height, coupling).astype(np.float32)

    # ---- texture_authoring stage also covers the marks + normal derivation
    # below (EXCLUDING the bpy image encode/save -- image_encode_io). Report
    # 037 item B: generate_marks replaces generate_scribble_mask with AA
    # strokes, white+dark marks, shape/thickness variety, per-mark index.
    mark_dark, mark_white, mark_index = generate_marks(recipe, size, seed + 5)
    normal = height_to_normal(height, strength=18.0)

    # Report 043 (MMv3-G1): split h into (sigma_s, a_glow); h itself becomes
    # the OUTPUT_CONTRACT compatibility projection of the pair, not an
    # independently-authored field anymore.
    sigma_s, a_glow = decompose_haze(h, recipe)
    h = project_h(sigma_s, a_glow)
    _record('texture_authoring', time.perf_counter() - _t0_tex)

    return T, h, mark_dark, mark_white, mark_index, height, normal, bump_distance, sigma_s, a_glow


def encode_glass_textures(out_dir, T, h, mark_dark, mark_white, mark_index, height, normal, bump_distance, sigma_s, a_glow):
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
    mark_white_path = os.path.join(out_dir, "tex_mark_white.png")
    mark_index_path = os.path.join(out_dir, "tex_mark_index.png")
    height_path = os.path.join(out_dir, "tex_height.png")
    normal_path = os.path.join(out_dir, "tex_normal.png")
    # Report 043 (MMv3-G1): the two new authored channels, same
    # save_numpy_to_image path as tex_h (sRGB-shaped-on-disk, GT_SPEC sec 5).
    sigma_s_path = os.path.join(out_dir, "tex_sigma_s.png")
    a_glow_path = os.path.join(out_dir, "tex_a_glow.png")

    # Report 037 WP-A --no-tex-dump: the tex_* files are the 141.7MB/58%
    # prune (docs/GT_SPEC.md sec 1a/3) -- byte-regenerable from (recipe,
    # seed). They MUST still be written here (the renderer samples the
    # file-backed image; see save_numpy_to_image's docstring for the probe)
    # -- the flag deletes them after the sample's renders complete (main()).
    with stage('image_encode_io'):
        img_T = save_numpy_to_image(T, T_path, is_color=True)
        img_h = save_numpy_to_image(h, h_path, is_color=False)
        img_mark = save_numpy_to_image(mark_dark, mark_path, is_color=False)
        img_mark_white = save_numpy_to_image(mark_white, mark_white_path, is_color=False)
        img_mark_index = save_numpy_to_image(mark_index, mark_index_path, is_color=False)
        img_height = save_numpy_to_image(height, height_path, is_color=False)
        img_normal = save_numpy_to_image(normal, normal_path, is_color=True)
        img_sigma_s = save_numpy_to_image(sigma_s, sigma_s_path, is_color=False)
        img_a_glow = save_numpy_to_image(a_glow, a_glow_path, is_color=False)

    return (img_T, img_h, img_mark, img_mark_white, img_mark_index, img_height, img_normal, bump_distance,
            img_sigma_s, img_a_glow)


def create_glass_textures(recipe, out_dir, size=1536, seed=42, cache=None):
    """Back-compat entry point: author (or fetch from `cache`) + encode in
    one call. `cache` is an optional dict the caller keeps alive across
    light variations, keyed by (recipe, seed) -- see main()."""
    key = (recipe, seed, size)
    if cache is not None and key in cache:
        T, h, mark_dark, mark_white, mark_index, height, normal, bump_distance, sigma_s, a_glow = cache[key]
    else:
        T, h, mark_dark, mark_white, mark_index, height, normal, bump_distance, sigma_s, a_glow = author_glass_arrays(recipe, size=size, seed=seed)
        if cache is not None:
            cache[key] = (T, h, mark_dark, mark_white, mark_index, height, normal, bump_distance, sigma_s, a_glow)
    return encode_glass_textures(out_dir, T, h, mark_dark, mark_white, mark_index, height, normal, bump_distance, sigma_s, a_glow)

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


# Report 037 item D: textured window-frame material families (replaces the
# flat near-black-only bar). Half the weight stays near-black (dark_wood /
# black_metal) to preserve the original dark-occluder-through-clear-glass
# audit trait (029/031: these pixels must be visible but must NOT leak into
# extracted T -- a near-black occluder is the sharpest version of that test);
# the other half adds real wood/metal variety per the report 037 brief.
# (base_color, roughness, metallic, is_wood) -- is_wood picks the grain vs
# brushed-streak bump orientation below.
FRAME_MATERIAL_FAMILIES = [
    ("dark_wood", (0.012, 0.008, 0.006), 0.75, 0.0, True),
    ("black_metal", (0.010, 0.010, 0.011), 0.30, 0.65, False),
    ("weathered_wood", (0.30, 0.19, 0.11), 0.70, 0.0, True),
    ("white_trim", (0.55, 0.53, 0.48), 0.55, 0.0, True),
    ("brushed_aluminum", (0.42, 0.43, 0.45), 0.35, 0.85, False),
]


def _build_frame_material(name, rng):
    """Wood/metal window-frame material (report 037 item D): a color/
    roughness family (FRAME_MATERIAL_FAMILIES) plus procedural texture --
    wood grain (a stretched Noise Texture bump, elongated along the bar's
    long axis) or brushed-metal streaks (a high-frequency 1D-ish Noise
    Texture at low bump strength) -- and a Noise-driven Roughness so the
    surface isn't a flat single value. Metal families get nonzero Metallic
    (colored/mirror-like environment reflection = the "+ bounce" the brief
    asks for -- a plausible amount of light bouncing off the frame into the
    scene, distinct from the near-zero-reflectance flat matte bars before).
    Uses Blender's native procedural nodes (Noise Texture), not an authored/
    tracked numpy channel -- this is scene dressing, not Material-v2 GT."""
    label, base_color, roughness, metallic, is_wood = rng.choice(FRAME_MATERIAL_FAMILIES)
    # slight per-instance color jitter so repeated bars in one sample (or
    # across samples of the same family) aren't identical
    jitter = rng.uniform(0.85, 1.15)
    color = tuple(min(1.0, max(0.0, c * jitter)) for c in base_color)

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    principled = nodes["Principled BSDF"]
    principled.inputs["Base Color"].default_value = (*color, 1)
    principled.inputs["Metallic"].default_value = metallic
    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = rng.uniform(0.4, 0.7)

    tex_coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    links.new(tex_coord.outputs['Object'], mapping.inputs['Vector'])
    if is_wood:
        # grain: stretched along one axis (long, thin streaks)
        mapping.inputs['Scale'].default_value = (4.0, 60.0, 1.0)
        grain_scale = rng.uniform(8.0, 20.0)
    else:
        # brushed metal: fine, less anisotropic-stretched than wood grain
        mapping.inputs['Scale'].default_value = (10.0, 30.0, 1.0)
        grain_scale = rng.uniform(20.0, 40.0)

    noise_rough = nodes.new('ShaderNodeTexNoise')
    noise_rough.inputs['Scale'].default_value = grain_scale
    noise_rough.inputs['Detail'].default_value = 3.0
    links.new(mapping.outputs['Vector'], noise_rough.inputs['Vector'])

    rough_map = nodes.new('ShaderNodeMapRange')
    rough_map.inputs['To Min'].default_value = max(0.05, roughness - 0.18)
    rough_map.inputs['To Max'].default_value = min(1.0, roughness + 0.12)
    links.new(noise_rough.outputs['Fac'], rough_map.inputs['Value'])
    links.new(rough_map.outputs['Result'], principled.inputs['Roughness'])

    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.15 if is_wood else 0.06
    links.new(noise_rough.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], principled.inputs['Normal'])

    return mat, label


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
        bar.pass_index = 2  # report 037 gt_index: frame occluder label

        # Report 037 item D: textured wood/metal frame material (replaces
        # the flat near-black-only bar) -- see _build_frame_material and
        # FRAME_MATERIAL_FAMILIES above.
        mat_frame, material_label = _build_frame_material(f"FrameOccluderMat_{i}", random)
        bar.data.materials.append(mat_frame)
        approx_luminance = sum(mat_frame.node_tree.nodes["Principled BSDF"]
                                .inputs["Base Color"].default_value[:3]) / 3.0

        params.append({"border": border, "thickness": round(thickness, 4),
                        "reach_frac": round(reach_frac, 4),
                        "material": material_label,
                        "darkness": round(approx_luminance, 4)})

    return params


def setup_scene(hdri_path, has_frame=False, wall_gray=0.0):
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
        if GT_OPTS.get("fixed_ev") is not None:
            ev = GT_OPTS["fixed_ev"]  # report 039: pinned mid-EV for review boards
        wbg.inputs['Strength'].default_value = 2.0 ** ev
    
    # Glass plane - size 0.5 ensures it completely fills the camera view (no borders)
    bpy.ops.mesh.primitive_plane_add(size=0.5, align='WORLD', location=(0, 0, 0), rotation=(math.radians(90), 0, 0))
    glass_obj = bpy.context.active_object
    glass_obj.name = "GlassSheet"
    # Report 037 WP-A gt_index (docs/GT_SPEC.md sec 1e): object-index labels
    # for the "sheet vs occluder vs background" AOV. Background stays the
    # default 0 (no object); marks are baked into the material texture, not
    # separate geometry, so they stay covered by the existing gt_mark_mask
    # channel, not gt_index (documented deviation, GT_SPEC updated).
    glass_obj.pass_index = 1

    # Camera - zoomed in so the glass perfectly fills the frame
    bpy.ops.object.camera_add(location=(0, -0.4, 0), rotation=(math.radians(90), 0, 0))
    cam = bpy.context.active_object
    scene.camera = cam

    # Randomize camera slightly. Report 037 item D: widened from the
    # original +-0.02m / +-0.05rad -- real handheld captures of a sheet
    # against a window show more pose variety than that tight a range, and
    # the old range was never meta-recorded so nobody could audit how much
    # jitter a given sample actually got. Now captured into `camera_jitter`
    # (returned below, folded into meta.json's camera_pose by main()).
    jx = random.uniform(-0.045, 0.045)
    jz = random.uniform(-0.045, 0.045)
    jrx = random.uniform(-0.09, 0.09)
    jrz = random.uniform(-0.09, 0.09)
    cam.location.x += jx
    cam.location.z += jz
    cam.rotation_euler.x += jrx
    cam.rotation_euler.z += jrz
    camera_jitter = {"loc_x": round(jx, 5), "loc_z": round(jz, 5),
                      "rot_x": round(jrx, 5), "rot_z": round(jrz, 5)}

    frame_params = []
    if has_frame:
        # Partial window-frame edge(s) entering from the image border(s) --
        # see add_frame_occluders() above. Replaces the old full mullion cross.
        # Needs the camera (for its true FOV/frustum), so must run after it exists.
        frame_params = add_frame_occluders(cam)

    # Dark wall behind camera to block HDRI reflections on the front face (simulates dim interior)
    # Report 032 WP-B: `wall_gray` > 0 turns the pure-black wall into a DIM
    # INTERIOR so the front face has something plausible to reflect when the
    # glass specular lobe is enabled (--specular). Default 0.0 = byte-compat
    # with every existing dataset.
    #
    # Report 043 (MMv3-G2, docs/GT_SPEC.md sec 6 finding): the old size=5.0
    # plane (half-extent 2.5m at ~2m from the glass) was NOT big enough to
    # isolate the veil -- the glass's bump-mapped shading normal fans the
    # glossy reflection cone well past the near-normal direction the
    # camera-aligned geometry assumes, so plenty of reflected rays missed
    # this wall's edges and saw the bright HDRI sky/sun directly. Measured on
    # two verification samples (both --specular OFF, i.e. the default the
    # extractor assumes carries NO veil): gt_veil was nonzero on 100% of
    # pixels, median veil share of the (transmission+veil) signal 40%
    # (cathedral-green) to 81% (dark-deep) -- not a rounding artifact, a real
    # unaccounted reflection baked into every sample generated to date.
    # Fix: make the occluding wall big enough that essentially no
    # bump-fanned reflection ray escapes past its edges. size=60 (half-extent
    # 30m at ~2m distance) subtends >168 degrees as seen from the glass --
    # only near-90-degree grazing rays (negligible Fresnel/foreshortening
    # weight) can still miss it. This is a scene-geometry fix only: it
    # changes what the (already-existing, always-on) front specular lobe
    # reflects, not the transmission/haze/T,h shader graph MMv3-G1 touches.
    bpy.ops.mesh.primitive_plane_add(size=60.0, location=(0, -2.0, 0), rotation=(math.radians(90), 0, 0))
    wall = bpy.context.active_object
    wall.name = "DarkWall"
    mat_wall = bpy.data.materials.new(name="WallMat")
    mat_wall.use_nodes = True
    bsdf = mat_wall.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (wall_gray, wall_gray, wall_gray, 1)
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.0
    wall.data.materials.append(mat_wall)

    _record('scene_build', time.perf_counter() - _t0_scene)
    return glass_obj, cam, ev, z_rot, frame_params, camera_jitter

def create_glass_material(glass_obj, img_T, img_h, img_mark, img_mark_white, img_height, recipe, bump_distance, use_bump=True,
                          specular_ior_level=None, img_sigma_s=None, img_a_glow=None):
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

    # Report 043 (MMv3-G1): sigma_s/a_glow are the new shader-driving
    # channels; tex_h stays in the graph as a datablock (some callers may
    # still pass it) but no longer feeds the shader -- see below.
    tex_sigma_s = nodes.new('ShaderNodeTexImage')
    tex_sigma_s.image = img_sigma_s if img_sigma_s is not None else img_h

    tex_a_glow = nodes.new('ShaderNodeTexImage')
    tex_a_glow.image = img_a_glow if img_a_glow is not None else img_h

    tex_mark = nodes.new('ShaderNodeTexImage')
    tex_mark.image = img_mark

    tex_mark_white = nodes.new('ShaderNodeTexImage')
    tex_mark_white.image = img_mark_white

    tex_height = nodes.new('ShaderNodeTexImage')
    tex_height.image = img_height
    
    # Physically-based glass using Principled BSDF
    principled = nodes.new('ShaderNodeBsdfPrincipled')
    principled.inputs['IOR'].default_value = 1.5

    # Report 032 WP-B (MMv3 G2, 029 gap G-4): front-surface specular lobe.
    # None (default) leaves the node's stock value -- byte-compatible with
    # every existing dataset (the pure-black DarkWall made the front lobe
    # invisible regardless). --specular passes an explicit 0.5-1.0 level and
    # pairs it with a dim-interior wall (setup_scene wall_gray) so the front
    # face carries a real reflected-environment veil. The extractor has no
    # veil term (that is MMv3's motivation) -- the point of the flag is to
    # MEASURE that degradation honestly, not to hide it.
    if specular_ior_level is not None:
        if 'Specular IOR Level' in principled.inputs:
            principled.inputs['Specular IOR Level'].default_value = specular_ior_level
        elif 'Specular' in principled.inputs:
            principled.inputs['Specular'].default_value = specular_ior_level
    
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
    
    # Report 043 (MMv3-G1): sigma_s (forward-scatter PSF width) drives the
    # ONE transmission lobe's Roughness directly -- a genuine, continuous,
    # LOCAL blur (Cycles' GGX roughness on a refractive BSDF samples a spread
    # of directions around the ideal refraction direction, which for a
    # background at some distance maps to a spread of nearby background
    # positions -- real optical blur, not the old stopgap's per-point jump
    # to a global hemisphere average). No cap: opal recipes get real
    # headroom they never had before, since the old code reserved roughness
    # headroom for a second lobe that no longer exists.
    links.new(tex_sigma_s.outputs['Color'], principled.inputs['Roughness'])

    # a_glow (diffuse self-glow / opal opacity) is a SEPARATE, independent
    # term -- multiple internal scattering in real milky opal glass that
    # pure roughness-blur alone doesn't reach even at Roughness=1. Mixed in
    # via a dedicated Translucent BSDF (true Lambertian transmission --
    # samples the whole hemisphere uniformly, i.e. genuinely diffuse "glow"),
    # weighted by a_glow(x). For every non-opal recipe a_glow==0 everywhere
    # (decompose_haze), so this mix is an exact no-op (Fac=0 -> output ==
    # principled_shader unchanged) -- no regression on the CTO-approved
    # clear/cathedral/streaky/dark families.
    #
    # Color = tex_T DIRECTLY, NOT the squared math_node vector: the squaring
    # trick above exists only to cancel the *Principled* thin-glass lobe's
    # internal sqrt; Translucent has no such sqrt (it transmits Color
    # linearly), so feeding it T^2 renders the glow at T^2 -- measured as a
    # 10x validate-gate regression on the opal recipes (wispy-white MAE
    # 0.0109 -> 0.1065) before this link was corrected. With plain T both
    # lobes agree with gt_T under the uniform backlight.
    translucent = nodes.new('ShaderNodeBsdfTranslucent')
    links.new(tex_T.outputs['Color'], translucent.inputs['Color'])

    mix_glow = nodes.new('ShaderNodeMixShader')
    links.new(tex_a_glow.outputs['Color'], mix_glow.inputs['Fac'])
    links.new(principled.outputs['BSDF'], mix_glow.inputs[1])
    links.new(translucent.outputs['BSDF'], mix_glow.inputs[2])
    principled_shader = mix_glow.outputs['Shader']

    # Report 037 item B: dark grease-pencil/marker AND white grease-pencil/
    # paint-pen marks, each its own BSDF mixed in via its own coverage
    # channel (tex_mark / tex_mark_white -- generate_marks keeps the two
    # colors on disjoint per-mark coverage, so the two mixes rarely fight
    # over the same pixel). White grease pencil/paint-pen is matte and
    # slightly off-white/warm (chalky pigment), not a pure specular white.
    mark_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    mark_bsdf.inputs['Base Color'].default_value = (0.01, 0.01, 0.01, 1)
    mark_bsdf.inputs['Roughness'].default_value = 0.8

    mark_white_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    mark_white_bsdf.inputs['Base Color'].default_value = (0.88, 0.86, 0.80, 1)
    mark_white_bsdf.inputs['Roughness'].default_value = 0.9

    # A plain reflective BSDF for the white marker does NOT work in this
    # scene: measured directly (dark-deep, white-mark pixels vs background)
    # the "white" mark rendered DARKER than the surrounding glass (0.055 vs
    # 0.247 mean photo luminance) -- the front hemisphere this material
    # would need to reflect is near-unlit by construction (DarkWall
    # wall_gray=0 without --specular; see report 032/037's veil notes), so
    # ANY opaque reflector there renders black regardless of its base color
    # (the dark marker "worked" only by coincidence: dark base + no light =
    # dark result, which is also what a light base + no light gives). Real
    # white grease-pencil/paint-pen is legible because SOME front-side
    # ambient/flash light exists in an actual photo shoot, which this
    # scene's lighting model deliberately doesn't provide. Modeled instead
    # as a modest constant self-emission (the pigment "catches" a baseline
    # amount of light regardless of scene front-lighting), added to the
    # BSDF so a real front light source (a future --specular/IBL pass)
    # still makes it brighter, not capped.
    mark_white_emit = nodes.new('ShaderNodeEmission')
    mark_white_emit.inputs['Color'].default_value = (0.85, 0.83, 0.77, 1)
    mark_white_emit.inputs['Strength'].default_value = 0.6
    mark_white_add = nodes.new('ShaderNodeAddShader')
    links.new(mark_white_bsdf.outputs['BSDF'], mark_white_add.inputs[0])
    links.new(mark_white_emit.outputs['Emission'], mark_white_add.inputs[1])

    mix_mark = nodes.new('ShaderNodeMixShader')
    links.new(tex_mark.outputs['Color'], mix_mark.inputs['Fac'])
    links.new(principled_shader, mix_mark.inputs[1])
    links.new(mark_bsdf.outputs['BSDF'], mix_mark.inputs[2])

    mix_mark_white = nodes.new('ShaderNodeMixShader')
    links.new(tex_mark_white.outputs['Color'], mix_mark_white.inputs['Fac'])
    links.new(mix_mark.outputs['Shader'], mix_mark_white.inputs[1])
    links.new(mark_white_add.outputs['Shader'], mix_mark_white.inputs[2])

    links.new(mix_mark_white.outputs['Shader'], out_node.inputs['Surface'])
    
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
    caster.pass_index = 3  # report 037 gt_index: shadow-caster label
    
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

def render_ground_truths(glass_obj, sample_dir, img_T, img_h, img_mark, img_mark_white, img_mark_index, img_height, img_normal,
                          img_sigma_s=None, img_a_glow=None):
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
        # Report 037 item B: white-mark coverage (disjoint from gt_mark_mask
        # -- generate_marks keeps dark/white marks on separate channels) and
        # a per-mark index (0 = no mark, else 1-based id of the strongest-
        # coverage mark at that pixel) -- texture-space per-mark GT, since
        # marks are baked into the material and can't use an object-index AOV.
        ("gt_mark_white", img_mark_white, 'BW'),
        ("gt_mark_index", img_mark_index, 'BW'),
        ("gt_height", img_height, 'BW'),
        ("gt_normal", img_normal, 'RGB'),
    ]
    # Report 043 (MMv3-G1): the two new authored channels, rendered the same
    # camera-aligned emission-passthrough way as gt_h.
    if img_sigma_s is not None:
        gt_channels.append(("gt_sigma_s", img_sigma_s, 'BW'))
    if img_a_glow is not None:
        gt_channels.append(("gt_a_glow", img_a_glow, 'BW'))
    for gt_name, gt_img, color_mode in gt_channels:
        tex_node.image = gt_img
        with stage('gt_render'):
            bpy.ops.render.render(write_still=False)
        rr = bpy.data.images['Render Result']
        with stage('image_encode_io'):
            scene.render.image_settings.file_format = 'OPEN_EXR'
            scene.render.image_settings.color_depth = '32'
            scene.render.image_settings.color_mode = color_mode
            apply_exr_codec(scene)  # report 037 WP-A --exr-codec (default: no-op)
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
        apply_exr_codec(scene)  # report 037 WP-A --exr-codec (default: no-op)
        img.save_render(os.path.abspath(os.path.join(out_dir, f"{prefix}photo_linear.exr")))


# ===========================================================================
# Report 037 WP-A: GT export v3 wiring -- `gt_veil/gt_index/gt_uv/gt_depth`
# multilayer AOVs and `gt_B` (hidden-glass background). Spec: docs/GT_SPEC.md
# sec 1e/4. Both are gated by GT_OPTS so a plain invocation is unaffected.
# ===========================================================================

def setup_aov_outputs(sample_dir):
    """Build a compositor graph that writes gt_veil/gt_index/gt_uv/gt_depth
    off the SAME main-render call (near-zero extra cost -- render-eff: cost
    scales with render *calls*, not passes). Must be called AFTER setup_scene
    (needs the glass/occluder/caster objects' pass_index to exist) and BEFORE
    the targeted render_sample() call; pair with teardown_aov_outputs()
    immediately after so the GT emission passes / gt_B / with-shadow render
    don't redundantly re-evaluate this graph.

    Blender 5.0 API note (probed empirically, docs/GT_SPEC.md sec 4): the
    compositor's File Output node (`CompositorNodeOutputFile`) is
    MULTILAYER-ONLY in this Blender version -- the old plain-EXR "one file
    per socket" mode is gone. A multilayer file with items named
    "<name>.R/.G/.B/.A" is NOT readable by cv2 (confirmed: cv2.imread
    returns None even for a single-item multilayer EXR), so `extract.py`
    readers need the `OpenEXR` python package (pip-installed into both the
    project .venv and Blender's PYTHONPATH site-packages this iteration) --
    NOT cv2 -- for these four files specifically. gt_T/gt_h/gt_height/
    gt_normal/gt_mark_mask/photo_linear/gt_B are UNCHANGED (still written via
    plain img.save()/save_render(), still cv2-readable) -- only the four NEW
    AOV files need the new reader path. One output node per AOV (rather than
    one shared multilayer file) keeps each file single-channel-set and named
    exactly `gt_<name>.exr`, matching the GT_SPEC table.
    """
    scene = bpy.context.scene
    vl = bpy.context.view_layer
    vl.use_pass_glossy_direct = True
    vl.use_pass_glossy_indirect = True
    vl.use_pass_object_index = True
    vl.use_pass_uv = True
    vl.use_pass_z = True

    ng = bpy.data.node_groups.new("GTv3_AOV", 'CompositorNodeTree')
    scene.compositing_node_group = ng
    scene.use_nodes = True
    tree = scene.compositing_node_group
    nodes = tree.nodes
    links = tree.links
    nodes.clear()

    rl = nodes.new('CompositorNodeRLayers')
    # Cache the socket objects immediately: probing showed the RLayers node's
    # `.outputs` collection can transiently drop entries (e.g. "Transmission
    # Direct") after other graph edits before the depsgraph re-syncs; caching
    # right after creation and linking from the cache (rather than re-
    # indexing rl.outputs by name later) sidesteps that.
    rl_outs = {o.name: o for o in rl.outputs}

    codec = GT_OPTS["exr_codec"] or 'ZIP'

    def make_output(name, socket_type):
        fo = nodes.new('CompositorNodeOutputFile')
        fo.format.file_format = 'OPEN_EXR_MULTILAYER'
        fo.format.color_depth = '32'
        fo.format.exr_codec = codec
        item = fo.file_output_items.new(socket_type=socket_type, name=name)
        fo.directory = os.path.abspath(sample_dir)
        fo.file_name = name
        return fo, item

    # gt_veil: front-surface reflection veil r_f*E_front (029 gap G-4 / MMv3
    # G2) = glossy direct + indirect, summed via a compositor Add so a single
    # RGBA item carries the full front-surface reflection contribution.
    fo_veil, _ = make_output("gt_veil", 'RGBA')
    # Blender 5.0 note: the compositor tree no longer registers its own
    # Mix/Math nodes (`CompositorNodeMixRGB`/`CompositorNodeMath` are gone --
    # probed: not in dir(bpy.types)); the "Everything Nodes" unification
    # lets a `ShaderNodeMixRGB` be instantiated inside a CompositorNodeTree
    # instead, confirmed working here.
    add = nodes.new('ShaderNodeMixRGB')
    add.blend_type = 'ADD'
    add.inputs[0].default_value = 1.0
    links.new(rl_outs['Glossy Direct'], add.inputs[1])
    links.new(rl_outs['Glossy Indirect'], add.inputs[2])
    links.new(add.outputs['Color'], fo_veil.inputs['gt_veil'])

    # NOTE (measured on the seed-503 verification sample): in the MAIN render
    # this pass is effectively a SHEET-ALPHA mask -- the deliberately
    # oversized glass sheet is the camera's first-hit surface across the
    # whole frame, and the Object Index pass does not see through
    # transmission, so frame occluders (pass_index 2) and the shadow caster
    # (3), both placed BEHIND the glass, never appear here (verified: unique
    # value 1.0 on a sample whose meta records two occluder bars). The
    # occluder labels come from `gt_index_B` instead -- the same pass
    # attached to the hidden-glass gt_B render (render_hidden_background).
    fo_index, _ = make_output("gt_index", 'FLOAT')
    links.new(rl_outs['Object Index'], fo_index.inputs['gt_index'])

    fo_uv, _ = make_output("gt_uv", 'VECTOR')
    links.new(rl_outs['UV'], fo_uv.inputs['gt_uv'])

    fo_depth, _ = make_output("gt_depth", 'FLOAT')
    links.new(rl_outs['Depth'], fo_depth.inputs['gt_depth'])

    return [fo_veil, fo_index, fo_uv, fo_depth]


def teardown_aov_outputs():
    """Disable the compositor graph after the one targeted render so the
    with-shadow render, the 5 GT emission-passthrough renders, and gt_B don't
    redundantly re-evaluate/re-write these files (they'd overwrite the same
    paths with scene states that don't correspond to the intended AOVs).

    Blender 5.0 note (found by testing, not assumed): `scene.use_nodes =
    False` alone does NOT stop the compositor from evaluating -- the
    AOV files kept being re-written on every subsequent render call in a
    first pass of this code. The compositor is actually gated by whether
    `scene.compositing_node_group` is assigned; clearing it to None is what
    stops evaluation. `use_nodes = False` is kept too (belt-and-suspenders,
    harmless deprecation warning) in case a future Blender restores the old
    semantics."""
    scene = bpy.context.scene
    scene.compositing_node_group = None
    scene.use_nodes = False


def render_hidden_background(glass_obj, sample_dir):
    """gt_B (docs/GT_SPEC.md sec 1e): the scene with the glass sheet hidden,
    so the pure transmitted/lensed background B is a supervised layer (MMv3 /
    report 027 Bet 1's `(T, B, veil)` log-space split). Everything else
    (world/HDRI, dark wall, frame occluders) stays exactly as the real photo
    saw it -- only the glass geometry is removed. Converges fast (no
    transmission/caustic paths through glass left to resolve), so this runs
    at a quarter of the main sample count. Must run AFTER the main photo
    render (uses the same world/wall state) and BEFORE render_ground_truths
    (which zeroes the world strength for the emission-GT trick)."""
    scene = bpy.context.scene
    orig_samples = scene.cycles.samples
    orig_hide = glass_obj.hide_render

    glass_obj.hide_render = True
    scene.cycles.samples = max(8, orig_samples // 4)

    # gt_index_B: the occluder/background object-index labels, which the
    # MAIN render's gt_index cannot capture (the full-frame glass is always
    # the first hit -- see setup_aov_outputs). With the glass hidden, the
    # first-hit surface IS the frame occluder (2) / backlight geometry /
    # world (0), so this render is where the occluder mask lives. Only wired
    # when --gt-aov is also on (it's part of the AOV set, and needs the same
    # OpenEXR-reader caveat).
    if GT_OPTS["gt_aov"]:
        vl = bpy.context.view_layer
        vl.use_pass_object_index = True
        ng = bpy.data.node_groups.new("GTv3_B_index", 'CompositorNodeTree')
        scene.compositing_node_group = ng
        scene.use_nodes = True
        nodes, links = ng.nodes, ng.links
        rl = nodes.new('CompositorNodeRLayers')
        rl_outs = {o.name: o for o in rl.outputs}
        fo = nodes.new('CompositorNodeOutputFile')
        fo.format.file_format = 'OPEN_EXR_MULTILAYER'
        fo.format.color_depth = '32'
        fo.format.exr_codec = GT_OPTS["exr_codec"] or 'ZIP'
        fo.file_output_items.new(socket_type='FLOAT', name="gt_index_B")
        links.new(rl_outs['Object Index'], fo.inputs['gt_index_B'])
        fo.directory = os.path.abspath(sample_dir)
        fo.file_name = "gt_index_B"

    with stage('gt_render'):
        bpy.ops.render.render(write_still=False)
    rr = bpy.data.images['Render Result']

    if GT_OPTS["gt_aov"]:
        teardown_aov_outputs()

    with stage('image_encode_io'):
        scene.render.image_settings.file_format = 'OPEN_EXR'
        scene.render.image_settings.color_depth = '32'
        scene.render.image_settings.color_mode = 'RGB'
        apply_exr_codec(scene)
        rr.save_render(os.path.abspath(os.path.join(sample_dir, "gt_B.exr")))

    glass_obj.hide_render = orig_hide
    scene.cycles.samples = orig_samples


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
    parser.add_argument('--specular', action='store_true',
                        help="Report 032 WP-B: enable the glass front-surface specular lobe "
                             "(Specular IOR Level drawn 0.5-1.0 per sample from a dedicated "
                             "RNG) and lift the DarkWall to a dim-interior gray so the front "
                             "face has something plausible to reflect. Default OFF = "
                             "byte-compatible with all existing datasets.")
    # Report 037 WP-A: GT export v3 production flags (docs/GT_SPEC.md).
    # Production flag set for the 20k run: --no-tex-dump --exr-codec DWAA
    # --gt-b --gt-aov (measured <=100MB/sample, see report 037 sec A).
    parser.add_argument('--no-tex-dump', action='store_true',
                        help="Report 037: drop tex_*.exr (58%% of a validate sample) -- "
                             "byte-regenerable from (recipe, seed); the in-memory Image "
                             "datablocks the shader needs are still built.")
    parser.add_argument('--exr-codec', type=str, default=None,
                        choices=['NONE', 'ZIP', 'PIZ', 'DWAA', 'DWAB', 'ZIPS', 'RLE', 'PXR24', 'B44', 'B44A'],
                        help="Report 037: EXR compression codec for gt_*/photo_linear/gt_B/"
                             "AOV writes (and tex_*.exr if not dumped-off). Default: Blender's "
                             "stock ZIP (unset = byte-compatible). DWAA is the production choice.")
    parser.add_argument('--gt-b', action='store_true',
                        help="Report 037: render gt_B.exr, the hidden-glass background "
                             "(reduced samples) -- MMv3/Bet-1's (T,B,veil) split.")
    parser.add_argument('--gt-aov', action='store_true',
                        help="Report 037: render gt_veil/gt_index/gt_uv/gt_depth off the "
                             "main render's compositor passes (multilayer EXR per channel; "
                             "read with OpenEXR, not cv2 -- see setup_aov_outputs docstring).")
    parser.add_argument('--fixed-ev', type=float, default=None,
                        help="Report 039: pin the HDRI EV to this value instead of the "
                             "per-seed random draw (-1.5..0.5). For representative mid-EV "
                             "review renders. Default: unset = random draw (dataset default).")
    parser.add_argument('--no-marks', action='store_true',
                        help="Report 039: suppress grease-pencil marks (texture review "
                             "board / forced-choice test). Default OFF = dataset default.")
    return parser.parse_args(argv)

def main():
    args = parse_args()

    GT_OPTS["no_tex_dump"] = args.no_tex_dump
    GT_OPTS["exr_codec"] = args.exr_codec
    GT_OPTS["gt_b"] = args.gt_b
    GT_OPTS["gt_aov"] = args.gt_aov
    GT_OPTS["fixed_ev"] = args.fixed_ev
    GT_OPTS["no_marks"] = args.no_marks

    recipes = ['cathedral-green', 'cathedral-amber', 'dark-opaque', 'streaky-mix', 'wispy-white',
               'dark-deep', 'dark-ruby', 'dark-slate',
               # Report 022: five gap recipes (021 §5)
               'cathedral-blue', 'cathedral-red', 'saturated-opalescent',
               'streaky-fine-texture', 'dark-textured',
               # Report 037 item C: four new taxa (031 §2/4/5 ranked gaps)
               'baroque-rolling-wave', 'fracture-streamer', 'confetti-shard', 'ring-mottle']
    
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

            # Report 032 WP-B: front-surface specular params from a DEDICATED
            # RNG stream (keyed on seed+variation) so enabling --specular does
            # not perturb the global `random` stream -- an OFF and an ON run of
            # the same seed produce IDENTICAL scenes except the specular lobe
            # and wall gray (required for the extractor A/B in report 032).
            spec_level, wall_gray = None, 0.0
            if args.specular:
                _spec_rng = random.Random(seed * 7919 + v * 13 + 5)
                spec_level = _spec_rng.uniform(0.5, 1.0)
                wall_gray = _spec_rng.uniform(0.02, 0.08)

            # 1. Setup scene FIRST (clears factory settings)
            if args.validate:
                glass_obj, cam, ev, z_rot, frame_params, camera_jitter = setup_scene(None, has_frame=has_frame)
            else:
                glass_obj, cam, ev, z_rot, frame_params, camera_jitter = setup_scene(
                    hdri_path, has_frame=has_frame, wall_gray=wall_gray)

            # 2. Create textures (numpy compute cached across this glass
            # piece's light variations; bpy encode always redone -- see
            # create_glass_textures/_texture_cache comments above)
            (img_T, img_h, img_mark, img_mark_white, img_mark_index, img_height, img_normal, bump_distance,
             img_sigma_s, img_a_glow) = create_glass_textures(
                recipe, sample_dir, size=1536, seed=seed, cache=_texture_cache
            )

            # 3. Create material
            with stage('scene_build'):
                mat = create_glass_material(
                    glass_obj, img_T, img_h, img_mark, img_mark_white, img_height, recipe, bump_distance,
                    specular_ior_level=spec_level, img_sigma_s=img_sigma_s, img_a_glow=img_a_glow
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
                    "rotation": list(cam.rotation_euler),
                    # Report 037 item D: the +-0.02m/+-0.05rad jitter was
                    # widened to +-0.045m/+-0.09rad and is now meta-recorded
                    # (previously untracked -- nobody could audit how much
                    # pose variety a given sample actually got).
                    "jitter": camera_jitter,
                },
                "blender_version": bpy.app.version_string,
                "seed": seed,
                "has_shadow": has_shadow,
                "specular": {
                    "enabled": bool(args.specular),
                    "ior_level": spec_level,
                    "wall_gray": wall_gray,
                },
                "material_v2": {
                    "channels": ["T", "h", "height", "normal", "mark_mask", "mark_white", "mark_index"],
                    "bump_distance_m": bump_distance,
                    "ior": 1.5
                },
                # Report 043: MMv3-G1 channels. h remains the OUTPUT_CONTRACT
                # compatibility projection of (sigma_s, a_glow) -- see
                # project_h/decompose_haze.
                "material_v3": {
                    "channels": ["sigma_s", "a_glow"],
                    "note": "h = a_glow + (1-a_glow)*sigma_s (OUTPUT_CONTRACT.md sec 0)"
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
                # Report 037 WP-A: attach the AOV compositor graph to THIS
                # (without-shadow, canonical) main render only, then detach
                # immediately -- see setup_aov_outputs/teardown_aov_outputs
                # docstrings for why it must not follow into the GT/gt_B
                # renders below.
                if GT_OPTS["gt_aov"]:
                    setup_aov_outputs(sample_dir)
                render_sample(sample_dir, "without_shadow_")
                if GT_OPTS["gt_aov"]:
                    teardown_aov_outputs()

            else:
                metadata["shadow_mode"] = "none"
                if GT_OPTS["gt_aov"]:
                    setup_aov_outputs(sample_dir)
                render_sample(sample_dir, "without_shadow_")
                if GT_OPTS["gt_aov"]:
                    teardown_aov_outputs()

            # Report 037 WP-A: gt_B, the hidden-glass background -- must run
            # while world/wall state still matches the real photo (before
            # render_ground_truths zeroes world strength for its emission
            # trick).
            if GT_OPTS["gt_b"]:
                render_hidden_background(glass_obj, sample_dir)

            # Render aligned ground truths
            render_ground_truths(glass_obj, sample_dir, img_T, img_h, img_mark, img_mark_white, img_mark_index, img_height, img_normal,
                                  img_sigma_s=img_sigma_s, img_a_glow=img_a_glow)

            # Report 037 WP-A --no-tex-dump: delete the authored-texture dump
            # AFTER all renders (they had to exist on disk during rendering --
            # the renderer samples the file-backed image, see
            # save_numpy_to_image). Byte-regenerable from (recipe, seed) in
            # meta.json, so nothing is lost; this is the GT_SPEC sec 3 prune.
            if GT_OPTS["no_tex_dump"]:
                for _tex in ("tex_T", "tex_h", "tex_mark_mask", "tex_mark_white", "tex_mark_index", "tex_height", "tex_normal",
                             "tex_sigma_s", "tex_a_glow"):
                    _p = os.path.join(sample_dir, _tex + ".exr")
                    if os.path.exists(_p):
                        os.remove(_p)

            with stage('image_encode_io'):
                with open(os.path.join(sample_dir, 'meta.json'), 'w') as f:
                    json.dump(metadata, f, indent=2)

    dump_timings(args.out)

if __name__ == '__main__':
    main()
