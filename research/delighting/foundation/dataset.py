#!/usr/bin/env python3
"""Iteration 038 / deliverable 2 — DATA PIPELINE for the Bet-2 foundation fine-tune.

Reads the generator's sample dirs (render_022 / render_023_holdout / the 037 GT-v3
production runs) and yields training crops of the photo + the OUTPUT_CONTRACT tier-1
ground-truth channels, with the camera-pipeline augmentations the consultant specified
as loader-side (tone-map jitter, JPEG recompression, sensor noise, exposure jitter),
and STRICT identity-holdout split enforcement per EVAL_PROTOCOL.md §3b.

--------------------------------------------------------------------- holdout rule
EVAL_PROTOCOL.md §3b: a synthetic identity = (recipe, seed). A model may NEVER be
tuned against a `seed % 5 == 0` identity, and the report-023 holdout batch (seeds
800-812) is reserved TEST wholesale. This loader enforces both: in split="train" a
test identity is NEVER returned; in split="test" only test identities are. The rule
is a pure function of the seed parsed from meta.json (authoritative) so a freshly
rendered batch auto-partitions with no shared list to maintain.

--------------------------------------------------------------------- channels
Per OUTPUT_CONTRACT.md §1 tier-1 (what train.py predicts):
  photo   input  : scene-linear RGB (without/with-shadow capture; the nuisance-laden obs)
  T       target : transmitted colour, rendered units == raw gt_T.exr (the space every
                   frozen instrument scores against; NOT srgb_to_lin-decoded, matching
                   eval_synthetic.load_gt_T)
  h       target : haze/scatter, authored-linear (srgb_to_lin-decoded per report 025 /
                   eval_synthetic.load_gt_h)
  sigma_s target : haze-driven subsurface-scatter radius (report 048; the (T,h)->(T,h,sigma_s)
                   material-target extension of the oracle-045 gate). Same authored-linear
                   space + srgb_to_lin decode as h; emitted by the generator as gt_sigma_s
                   (report 043 decompose_haze). `has_sigma_s` flag false on pre-043 renders,
                   so old batches (render_022/037) still load (sigma_s zero-filled, unsupervised).
  B       target : through-glass background layer, scene-linear (gt_B.exr; GT-v3 only,
                   `has_B` flag false when absent)
  shadow  target : cast-shadow mask, derived from the with/without-shadow pair diff
                   (0 everywhere when the input is the clean capture)
  mark    target : grease-pencil / paint-pen mask (gt_mark_mask)
  valid          : score mask (sheet minus marks)
  veil    target : front-surface reflection veil (gt_veil, GT-v3 multilayer AOV;
                   `has_veil` flag; report 037 found it is non-zero on ALL existing data)

Confidence is NOT a loaded channel — it is a model output supervised against its own
error (EVAL_PROTOCOL §1d), handled in train.py.

Usage (smoke): GlassDelightDataset([render_022], split="train", crop=256)
"""
import glob
import json
import os
import sys

import numpy as np

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.dirname(HERE)
sys.path.insert(0, DELIGHT)
from extract import srgb_to_lin, lum  # noqa: E402  (frozen colour helpers)
sys.path.insert(0, HERE)
from phone_pipeline import PRESET_NAMES, apply_phone_pipeline  # noqa: E402  (report 053)
from crop_sim import warp_channel  # noqa: E402  (report 053b: THE crop-warp convention)


def _maybe_warp(a, M, name):
    """Report 053b lazy GT crop: apply the stored user-crop homography to a decoded FILE-space
    array (i.e. BEFORE any nonlinear decode like srgb_to_lin), exactly mirroring what the old
    materialized crop/ files contained. No-op when M is None. Preserves the trailing channel
    axis for single-channel arrays (cv2 drops it)."""
    if M is None or a is None:
        return a
    squeeze = a.ndim == 3 and a.shape[2] == 1
    w = warp_channel(a[..., 0] if squeeze else a, M, name)
    return w[..., None] if squeeze else w

# report-023 reserved holdout batch (EVAL_PROTOCOL §3b): TEST wholesale.
HOLDOUT_BATCH = range(800, 813)

# ------------------------------------------------------ report 053 multi-axis holdout
# The external review (docs/external/053-dataset-capture-review.md) warned that a pure
# seed%5 IDENTITY holdout still lets a model train on EVERY texture-generator family, glass
# taxon, HDRI, camera pipeline, and capture geometry it is tested on — so a strong test score
# can reflect "I have seen this generator / this device grammar before", not deployment
# generalization. EVAL_PROTOCOL §3b-ext (report 053) therefore RESERVES ENTIRE families of
# each nuisance/material axis to TEST, by deterministic documented rule. All rules are pure
# functions of meta.json (or, for the loader-side camera preset, of the split), so a freshly
# rendered batch auto-partitions with no shared list to maintain.

# (1) Whole texture-generator families / glass taxa reserved test-only. One generator family
#     that exists ONLY here (ring_mottle_blobs -> ring-mottle; the confetti compositor ->
#     confetti-shard) plus one cathedral and one dark taxon, so a held-out TAXON and a held-out
#     GENERATOR are both represented. A model never sees these recipes in training.
HOLDOUT_RECIPES = frozenset({
    "ring-mottle",        # entire ring_mottle_blobs generator family
    "confetti-shard",     # entire confetti-shard compositor family
    "cathedral-red",      # a held-out cathedral taxon
    "dark-slate",         # a held-out dark taxon
})

# (2) HDRIs / background scenes: reserve ~20% of distinct HDRIs by a deterministic hash of the
#     basename (same style as EVAL_PROTOCOL §3c's product-id rule). A reserved HDRI's lighting
#     environment is never seen in training.
def hdri_is_test(hdri_name):
    if not hdri_name or hdri_name == "UniformWhite":
        return False
    import hashlib
    base = os.path.splitext(os.path.basename(str(hdri_name)))[0]
    return int(hashlib.sha1(base.encode()).hexdigest(), 16) % 5 == 0

# (3) Camera-pipeline presets (loader-side): reserve one COMPLETE device preset to test-only,
#     so "can this model handle a phone tuning it never trained on" is a measurable axis.
TEST_ONLY_PRESETS = ("wide_edge",)
TRAIN_PRESETS = tuple(p for p in PRESET_NAMES if p not in TEST_ONLY_PRESETS)

# (4) Capture geometries (report 053 crop-workflow sim, meta['capture_geometry']): reserve the
#     four-corner perspective-rectified capture to test-only. Old batches lack the field ->
#     treated as the default 'axis_crop' (train-eligible), so this never retro-holds-out data.
HOLDOUT_GEOMETRIES = frozenset({"perspective_rectified"})


# ------------------------------------------------------------------ split rule
def seed_is_test(seed):
    """EVAL_PROTOCOL §3b: TEST iff seed%5==0 OR in the 800-812 reserved batch."""
    return (seed % 5 == 0) or (seed in HOLDOUT_BATCH)


def holdout_reason(meta, seed):
    """Report 053 / EVAL_PROTOCOL §3b-ext: return a short reason string if this sample is
    TEST (by ANY reserved-family axis), else None (train-eligible). Deterministic, documented.
    The camera-preset axis is enforced separately in the loader (it is loader-side, not a
    property of the render), so it is not decided here."""
    if seed_is_test(seed):
        return "seed%5" if seed % 5 == 0 else "seed800-812"
    recipe = (meta or {}).get("class_label")
    if recipe in HOLDOUT_RECIPES:
        return f"recipe:{recipe}"
    if hdri_is_test((meta or {}).get("hdri_name")):
        return f"hdri:{(meta or {}).get('hdri_name')}"
    geom = (meta or {}).get("capture_geometry", "axis_crop")
    if geom in HOLDOUT_GEOMETRIES:
        return f"geometry:{geom}"
    return None


def parse_seed(sample_dir, meta):
    if meta and "seed" in meta:
        return int(meta["seed"])
    base = os.path.basename(sample_dir.rstrip("/"))
    for tok in base.split("__"):
        if tok.startswith("seed"):
            try:
                return int(tok[4:])
            except ValueError:
                pass
    raise ValueError(f"cannot determine seed for {sample_dir}")


# ------------------------------------------------------------------ io helpers
def _imread_exr(path):
    a = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if a is None:
        return None
    if a.ndim == 3:
        a = a[..., ::-1]  # BGR->RGB
    return a.astype(np.float32)


def load_aov_exr(path):
    """Read a Blender-5 OPEN_EXR_MULTILAYER AOV (gt_veil etc.), which cv2 cannot
    parse (report 037 §6). Returns HxWx{1,3} float32 or None. Self-contained OpenEXR
    reader so this branch does not depend on the 037 `extract.load_aov_exr`."""
    try:
        import OpenEXR
        import Imath
    except Exception:
        return None
    try:
        f = OpenEXR.InputFile(path)
        dw = f.header()["dataWindow"]
        W = dw.max.x - dw.min.x + 1
        H = dw.max.y - dw.min.y + 1
        chans = list(f.header()["channels"].keys())
        pt = Imath.PixelType(Imath.PixelType.FLOAT)

        def _pick(suffix):
            for c in chans:
                if c.endswith(suffix):
                    return c
            return None
        rgb = [_pick(".R"), _pick(".G"), _pick(".B")]
        if all(rgb):
            out = [np.frombuffer(f.channel(c, pt), np.float32).reshape(H, W) for c in rgb]
            return np.stack(out, -1)
        c0 = chans[0]
        return np.frombuffer(f.channel(c0, pt), np.float32).reshape(H, W)[..., None]
    except Exception:
        return None


def _photo_linear(sample, variant, M=None):
    """scene-linear photo. variant in {without,with}. Falls back to png->srgb_to_lin.
    Report 053b: `M` = user-crop homography; the warp is a LINEAR-space op, so warping the
    linear EXR photo commutes with the decode; on the png path it is applied to the raw sRGB
    array BEFORE srgb_to_lin (mirroring crop_sim's file-space warp)."""
    exr = os.path.join(sample, f"{variant}_shadow_photo_linear.exr")
    if os.path.exists(exr):
        a = _imread_exr(exr)
        if a is not None:
            return _maybe_warp(a, M, "photo_linear")
    png = os.path.join(sample, f"{variant}_shadow_photo.png")
    if not os.path.exists(png):
        png = os.path.join(sample, "photo.png")
    if os.path.exists(png):
        a = cv2.imread(png, cv2.IMREAD_COLOR)[..., ::-1].astype(np.float32) / 255.0
        return srgb_to_lin(_maybe_warp(a, M, "photo"))
    return None


def _load_gt_T(sample, M=None):
    p = os.path.join(sample, "gt_T.exr")
    if os.path.exists(p):
        return _maybe_warp(_imread_exr(p), M, "gt_T")
    p = os.path.join(sample, "gt_T.png")
    if os.path.exists(p):
        a = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        if a is None:
            return None
        a = a[..., ::-1].astype(np.float32)
        return _maybe_warp(a / (65535.0 if a.max() > 255 else 255.0), M, "gt_T")
    return None


def _load_gt_h(sample, M=None):
    p = os.path.join(sample, "gt_h.png")
    if os.path.exists(p):
        raw = cv2.imread(p, cv2.IMREAD_UNCHANGED).astype(np.float32) / 65535.0
        if raw.ndim == 3:
            raw = raw[..., 0]
        raw = _maybe_warp(raw, M, "gt_h")     # 053b: warp in FILE space, before srgb_to_lin
        return srgb_to_lin(raw)[..., None]
    p = os.path.join(sample, "gt_h.exr")
    if os.path.exists(p):
        a = _imread_exr(p)
        if a is None:
            return None
        if a.ndim == 3:
            a = a[..., 0]
        a = _maybe_warp(a, M, "gt_h")
        return srgb_to_lin(a)[..., None]
    return None


def _load_gt_sigma_s(sample, M=None):
    """Report 048: haze-driven subsurface-scatter radius, emitted by the generator as
    gt_sigma_s (report 043 decompose_haze) on the byte-identical encode path as gt_h --
    so it decodes exactly like h (16-bit PNG / EXR, srgb_to_lin to authored-linear).
    Returns HxWx1 float32, or None on pre-043 renders (handled as has_sigma_s=False)."""
    p = os.path.join(sample, "gt_sigma_s.png")
    if os.path.exists(p):
        raw = cv2.imread(p, cv2.IMREAD_UNCHANGED).astype(np.float32) / 65535.0
        if raw.ndim == 3:
            raw = raw[..., 0]
        raw = _maybe_warp(raw, M, "gt_sigma_s")   # 053b: file space, before srgb_to_lin
        return srgb_to_lin(raw)[..., None]
    p = os.path.join(sample, "gt_sigma_s.exr")
    if os.path.exists(p):
        a = _imread_exr(p)
        if a is None:
            return None
        if a.ndim == 3:
            a = a[..., 0]
        a = _maybe_warp(a, M, "gt_sigma_s")
        return srgb_to_lin(a)[..., None]
    return None


def _load_mask(sample, name, M=None):
    p = os.path.join(sample, name)
    if not os.path.exists(p):
        return None
    a = cv2.imread(p, cv2.IMREAD_UNCHANGED).astype(np.float32)
    if a.ndim == 3:
        a = a.mean(-1)
    a = _maybe_warp(a, M, name)                    # 053b: NEAREST via name (gt_mark_* = label)
    return (a / (65535.0 if a.max() > 255 else 255.0))[..., None]


# ------------------------------------------------------------------ dataset
class GlassDelightDataset:
    """Framework-agnostic (numpy) sample store + crop sampler. train.py wraps the
    tensors; keeping this torch-free means it also runs under the Modal image and in
    a plain numpy smoke test."""

    def __init__(self, roots, split="train", crop=512, work_size=768,
                 augment=None, input_variant="random", require_B=False, seed=0,
                 crop_view=False, patch_prob=0.2):
        assert split in ("train", "test", "all")
        self.crop = crop
        self.work_size = work_size
        self.split = split
        self.augment = (split == "train") if augment is None else augment
        self.input_variant = input_variant
        self.require_B = require_B
        # Report 053b: serve the user-CROPPED sheet view — photo and every GT channel warped
        # at load time by the sample's stored crop homography (meta.crop_sim, written by
        # crop_sim.py). GT crops are no longer materialized on disk; the warp here is
        # convention-identical to the old crop/ files (see crop_sim.warp_channel +
        # verify_lazy_crop_053b.py). Samples without crop_sim meta load unwarped (old batches).
        self.crop_view = crop_view
        # Report 053b addendum (CTO catch): the reviewer's training diet is "the full cropped
        # sheet AND local detail patches", but the 053 patches were emitted and never consumed.
        # With probability `patch_prob` a sample_crop draw serves a NATIVE-RESOLUTION detail
        # patch (photo + registered GT from <sample>/patches/) instead of a crop of the
        # work_size-downsampled sheet — patches carry the fine texture (seed bubbles, streak
        # edges -> the σ_s signal) that the 768-px downsample destroys. Patches inherit their
        # sample's holdout split (drawn from self.samples, which is already split-filtered).
        # Samples without patches on disk always serve the sheet view.
        self.patch_prob = patch_prob
        self.rng = np.random.default_rng(seed)
        # 053b pre-flight fix: the component cache was UNBOUNDED — ~30-40MB of work-res
        # channels per sample x a 268-468-sample pilot ≈ 10-19GB RAM (swap/OOM mid-run).
        # Bounded LRU now: oldest entry evicted past `cache_size` (~64 x ~35MB ≈ 2.2GB cap).
        from collections import OrderedDict
        self._cache = OrderedDict()   # idx -> downsampled component dict (LRU-bounded)
        self.cache_size = 64
        self.samples = self._index(roots if isinstance(roots, (list, tuple)) else [roots])
        if not self.samples:
            raise SystemExit(f"no {split} samples under {roots} "
                             f"(check the render root and the holdout split)")

    def _index(self, roots):
        out = []
        for root in roots:
            for d in sorted(glob.glob(os.path.join(root, "*"))):
                mp = os.path.join(d, "meta.json")
                if not (os.path.isdir(d) and os.path.exists(mp)):
                    continue
                try:
                    meta = json.load(open(mp))
                    seed = parse_seed(d, meta)
                except Exception:
                    continue
                reason = holdout_reason(meta, seed)   # report 053 multi-axis rule
                is_test = reason is not None
                if self.split == "train" and is_test:
                    continue
                if self.split == "test" and not is_test:
                    continue
                if self.require_B and not os.path.exists(os.path.join(d, "gt_B.exr")):
                    continue
                out.append({"dir": d, "seed": seed, "recipe": meta.get("class_label", "?"),
                            "is_test": is_test, "test_reason": reason,
                            "hdri": meta.get("hdri_name"),
                            "geometry": meta.get("capture_geometry", "axis_crop")})
        return out

    def __len__(self):
        return len(self.samples)

    # ---- component load (cached, downsampled to work_size) ----
    def _components(self, idx):
        """Read + downsample every channel once; cache. gt_T defines the grid."""
        if idx in self._cache:
            self._cache.move_to_end(idx)          # LRU touch (053b)
            return self._cache[idx]
        d = self.samples[idx]["dir"]
        # Report 053b: lazy crop warp — resolve the stored homography once for this sample.
        M = None
        if self.crop_view:
            try:
                cs = json.load(open(os.path.join(d, "meta.json"))).get("crop_sim")
                if cs and cs.get("homography_src_to_crop"):
                    M = np.asarray(cs["homography_src_to_crop"], dtype=np.float64)
            except Exception:
                M = None
        T = _load_gt_T(d, M)
        h = _load_gt_h(d, M)
        sigma_s = _load_gt_sigma_s(d, M)
        photo_wo = _photo_linear(d, "without", M)
        if T is None or h is None or photo_wo is None:
            self._cache_put(idx, None)
            return None
        H, W = T.shape[:2]
        has_with = os.path.exists(os.path.join(d, "with_shadow_photo_linear.exr")) or \
            os.path.exists(os.path.join(d, "with_shadow_photo.png"))
        photo_w = _photo_linear(d, "with", M) if has_with else None
        mark = _load_mask(d, "gt_mark_mask.png", M)
        mark = np.zeros((H, W, 1), np.float32) if mark is None else (mark > 0.5).astype(np.float32)
        Bp = os.path.join(d, "gt_B.exr")
        B = _maybe_warp(_imread_exr(Bp), M, "gt_B") if os.path.exists(Bp) else None
        Vp = os.path.join(d, "gt_veil.exr")
        veil = load_aov_exr(Vp) if os.path.exists(Vp) else None
        veil = _maybe_warp(veil, M, "gt_veil") if veil is not None else None

        # downsample everything to a common working grid (max dim == work_size)
        ws = self.work_size
        s = min(1.0, ws / max(H, W))
        tw, th = max(8, int(round(W * s))), max(8, int(round(H * s)))

        def _fit(a):
            if a is None:
                return None
            if a.ndim == 2:
                a = a[..., None]
            if a.shape[1] != tw or a.shape[0] != th:
                a = cv2.resize(a, (tw, th), interpolation=cv2.INTER_AREA)
                if a.ndim == 2:
                    a = a[..., None]
            return np.ascontiguousarray(a.astype(np.float32))

        comp = {
            "T": _fit(T), "h": _fit(h), "sigma_s": _fit(sigma_s),
            "photo_wo": _fit(photo_wo),
            "photo_w": _fit(photo_w), "mark": _fit(mark),
            "B": _fit(B), "veil": _fit(veil), "has_with": has_with,
            "has_B": B is not None, "has_veil": veil is not None,
            "has_sigma_s": sigma_s is not None,
        }
        self._cache_put(idx, comp)
        return comp

    def _cache_put(self, idx, val):
        """LRU insert with eviction (053b): keeps at most `cache_size` component dicts."""
        self._cache[idx] = val
        self._cache.move_to_end(idx)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def load_full(self, idx, variant=None):
        """Assemble a per-variant record from the cached components."""
        c = self._components(idx)
        if c is None:
            return None
        s = self.samples[idx]
        if variant is None:
            variant = self.input_variant
        if variant == "random":
            variant = "with" if (c["has_with"] and self.rng.random() < 0.5) else "without"
        if variant == "with" and not c["has_with"]:
            variant = "without"

        photo = c["photo_w"] if variant == "with" else c["photo_wo"]
        H, W = c["T"].shape[:2]
        shadow = np.zeros((H, W, 1), np.float32)
        if variant == "with":
            dY = lum(c["photo_wo"]) - lum(photo)
            if dY.ndim == 3:
                dY = dY[..., 0]
            shadow = (dY > 0.02).astype(np.float32)[..., None]
        valid = (1.0 - c["mark"]).astype(np.float32)
        return {
            "photo": photo, "T": c["T"], "h": c["h"], "shadow": shadow,
            "mark": c["mark"], "valid": valid, "recipe": s["recipe"], "seed": s["seed"],
            "variant": variant, "dir": s["dir"], "has_B": c["has_B"], "has_veil": c["has_veil"],
            "has_sigma_s": c["has_sigma_s"],
            "sigma_s": c["sigma_s"] if c["sigma_s"] is not None else np.zeros((H, W, 1), np.float32),
            "B": c["B"] if c["B"] is not None else np.zeros((H, W, 3), np.float32),
            "veil": c["veil"] if c["veil"] is not None else np.zeros((H, W, 3), np.float32),
        }

    # ---------------------------------------------------------- augmentations
    def _augment_photo(self, photo):
        """Loader-side camera pipeline. Report 053: replaced the four INDEPENDENTLY
        randomized effects (exposure + noise + gamma + JPEG) the external review flagged as
        "Blender glass grammar"-friendly with several COMPLETE, CORRELATED device ISP presets
        (foundation/phone_pipeline.py) applied in physical order — AWB error, lens shading,
        chromatic aberration, motion/defocus blur, local HDR/tonemap with halos, denoise,
        sharpen with overshoot, saturation/per-channel clip, rescale, JPEG/HEIC quantization.

        Applied to the INPUT photo ONLY; every target is the intrinsic and stays fixed, so
        this directly trains nuisance (N) invariance. In/out scene-linear (report 025).

        Holdout (EVAL_PROTOCOL §3b-ext): a TRAIN loader draws only from TRAIN_PRESETS, so the
        one test-only device tuning (TEST_ONLY_PRESETS) is never seen in training; a TEST
        loader may draw from ALL presets (the held-out device included) to measure preset
        generalization. Returns (photo_lin, preset_name); callers wanting only the array can
        index [0]."""
        allowed = None if self.split == "test" else TRAIN_PRESETS
        out, _preset = apply_phone_pipeline(photo, self.rng, allowed_presets=allowed)
        return out

    # ------------------------------------------------- 053b: detail-patch view
    def _load_patch(self, idx, patch_idx=None):
        """Load one native-resolution detail patch (photo + REGISTERED GT) emitted by
        crop_sim.py into <sample>/patches/. Decode conventions mirror the sheet loaders
        exactly (photo png -> srgb_to_lin; gt_T raw /65535; gt_h/gt_sigma_s /65535 ->
        srgb_to_lin; mark thresholded). B/veil have no patch files -> zero-filled with
        has_B/has_veil False (same contract as pre-GT-v3 batches). Returns None if the
        sample has no patches."""
        s = self.samples[idx]
        pdir = os.path.join(s["dir"], "patches")
        if not os.path.isdir(pdir):
            return None
        pids = sorted({os.path.basename(f).split("_")[0] for f in
                       glob.glob(os.path.join(pdir, "patch*_gt_T.png"))})
        if not pids:
            return None
        pid = pids[int(self.rng.integers(len(pids)))] if patch_idx is None else f"patch{patch_idx:02d}"

        def _rd(name):
            p = os.path.join(pdir, f"{pid}_{name}")
            a = cv2.imread(p, cv2.IMREAD_UNCHANGED) if os.path.exists(p) else None
            return a

        def _photo(name):
            a = _rd(name)
            if a is None:
                return None
            return srgb_to_lin(a[..., ::-1].astype(np.float32) / 255.0)

        photo_wo = _photo("without_shadow_photo.png")
        T = _rd("gt_T.png")
        h = _rd("gt_h.png")
        if photo_wo is None or T is None or h is None:
            return None
        T = T[..., ::-1].astype(np.float32) / (65535.0 if T.max() > 255 else 255.0)
        h = srgb_to_lin((h if h.ndim == 2 else h[..., 0]).astype(np.float32) / 65535.0)[..., None]
        sig = _rd("gt_sigma_s.png")
        has_sigma_s = sig is not None
        sig = (srgb_to_lin((sig if sig.ndim == 2 else sig[..., 0]).astype(np.float32) / 65535.0)[..., None]
               if has_sigma_s else np.zeros_like(h))
        mark = _rd("gt_mark_mask.png")
        if mark is not None:
            mark = ((mark if mark.ndim == 2 else mark.mean(-1)).astype(np.float32)
                    / (65535.0 if mark.max() > 255 else 255.0) > 0.5).astype(np.float32)[..., None]
        else:
            mark = np.zeros_like(h)

        photo_w = _photo("with_shadow_photo.png")
        variant = self.input_variant
        if variant == "random":
            variant = "with" if (photo_w is not None and self.rng.random() < 0.5) else "without"
        if variant == "with" and photo_w is None:
            variant = "without"
        photo = photo_w if variant == "with" else photo_wo
        P = photo.shape[0]
        shadow = np.zeros((P, P, 1), np.float32)
        if variant == "with":
            dY = lum(photo_wo) - lum(photo)
            shadow = (dY > 0.02).astype(np.float32)[..., None]
        valid = (1.0 - mark).astype(np.float32)
        out = {"photo": photo.astype(np.float32), "T": T, "h": h, "sigma_s": sig,
               "B": np.zeros((P, P, 3), np.float32), "veil": np.zeros((P, P, 3), np.float32),
               "shadow": shadow, "mark": mark, "valid": valid,
               "recipe": s["recipe"], "seed": s["seed"], "variant": variant,
               "has_B": False, "has_veil": False, "has_sigma_s": has_sigma_s,
               "view": "patch", "patch_id": pid}

        # ---- size adaptation to self.crop (see report 053b: reflect-pad, valid=0 in pad) ----
        c = self.crop
        keys = ("photo", "T", "h", "sigma_s", "B", "veil", "shadow", "mark", "valid")
        if P > c:      # patch bigger than the crop window: random-crop down
            y0 = int(self.rng.integers(0, P - c + 1))
            x0 = int(self.rng.integers(0, P - c + 1))
            for k in keys:
                out[k] = np.ascontiguousarray(out[k][y0:y0 + c, x0:x0 + c])
        elif P < c:    # patch smaller: reflect-pad (keeps input statistics glass-like,
            pad = c - P                                     # no invented black borders) and
            for k in keys:                                  # mask the pad out of every loss
                out[k] = np.pad(out[k], ((0, pad), (0, pad), (0, 0)), mode="reflect")
            out["valid"] = out["valid"].copy()
            out["valid"][P:, :] = 0.0
            out["valid"][:, P:] = 0.0
        return out

    def sample_crop(self, idx=None):
        """One augmented training draw (dict of HxWxC numpy). Identity-holdout is already
        enforced at index time, so any idx here is split-legal. Report 053b: with probability
        `patch_prob` (when the sample has crop_sim patches) the draw is a NATIVE-resolution
        detail patch instead of a window of the work_size-downsampled sheet — the two-view
        training diet the external review specified (full cropped sheet + local detail)."""
        if idx is None:
            idx = int(self.rng.integers(len(self.samples)))
        out = None
        if self.patch_prob > 0 and self.rng.random() < self.patch_prob:
            out = self._load_patch(idx)              # None if the sample has no patches
        if out is None:
            rec = self.load_full(idx)
            if rec is None:
                return None
            H, W = rec["T"].shape[:2]
            c = min(self.crop, H, W)
            y0 = int(self.rng.integers(0, H - c + 1))
            x0 = int(self.rng.integers(0, W - c + 1))
            sl = (slice(y0, y0 + c), slice(x0, x0 + c))
            out = {}
            for k in ("photo", "T", "h", "sigma_s", "B", "veil", "shadow", "mark", "valid"):
                out[k] = np.ascontiguousarray(rec[k][sl])
            for k in ("recipe", "seed", "variant", "has_B", "has_veil", "has_sigma_s"):
                out[k] = rec[k]
            out["view"] = "sheet"
            # 053b pre-flight fix 4: guarantee EXACT self.crop draws. Under crop_view a
            # non-square user crop (or a small work grid) can make c < self.crop, and
            # collate's np.stack crashes on mixed sizes mid-run. Same policy as the patch
            # path: reflect-pad to self.crop, valid=0 in the pad (no invented loss signal).
            ch, cw = out["T"].shape[:2]
            if ch < self.crop or cw < self.crop:
                py, px = self.crop - ch, self.crop - cw
                pmode = "reflect" if (py < ch and px < cw) else "edge"  # reflect needs pad<dim
                for k in ("photo", "T", "h", "sigma_s", "B", "veil", "shadow", "mark", "valid"):
                    out[k] = np.pad(out[k], ((0, py), (0, px), (0, 0)), mode=pmode)
                out["valid"] = out["valid"].copy()
                if py:
                    out["valid"][ch:, :] = 0.0
                if px:
                    out["valid"][:, cw:] = 0.0
        if self.augment:
            out["photo"] = self._augment_photo(out["photo"])
            if self.rng.random() < 0.5:
                for k in ("photo", "T", "h", "sigma_s", "B", "veil", "shadow", "mark", "valid"):
                    out[k] = np.ascontiguousarray(out[k][:, ::-1])
            if self.rng.random() < 0.5:
                for k in ("photo", "T", "h", "sigma_s", "B", "veil", "shadow", "mark", "valid"):
                    out[k] = np.ascontiguousarray(out[k][::-1])
        return out


def summarize(roots):
    """CLI sanity: print the split partition and channel availability."""
    for split in ("train", "test"):
        try:
            ds = GlassDelightDataset(roots, split=split, augment=False)
        except SystemExit as e:
            print(f"{split}: {e}")
            continue
        seeds = sorted({s["seed"] for s in ds.samples})
        recipes = sorted({s["recipe"] for s in ds.samples})
        nB = sum(os.path.exists(os.path.join(s["dir"], "gt_B.exr")) for s in ds.samples)
        print(f"{split:5s}: {len(ds):3d} samples | seeds={seeds} | "
              f"{len(recipes)} recipes | gt_B present in {nB}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="index + split sanity for a render root")
    ap.add_argument("roots", nargs="+")
    ap.add_argument("--dump-crop", action="store_true", help="write one augmented crop panel")
    args = ap.parse_args()
    summarize(args.roots)
    if args.dump_crop:
        ds = GlassDelightDataset(args.roots, split="train", crop=256)
        c = ds.sample_crop()
        if c is not None:
            os.makedirs(os.path.join(DELIGHT, "results", "038_backbone"), exist_ok=True)
            from extract import lin_to_srgb
            cols = [lin_to_srgb(np.clip(c["photo"], 0, 1)), np.clip(c["T"], 0, 1),
                    np.repeat(np.clip(c["h"], 0, 1), 3, -1), np.repeat(c["shadow"], 3, -1)]
            panel = (np.clip(np.concatenate(cols, 1), 0, 1) * 255).astype(np.uint8)
            outp = os.path.join(DELIGHT, "results", "038_backbone", "crop_panel.png")
            cv2.imwrite(outp, panel[..., ::-1])
            print("wrote", outp, "| recipe", c["recipe"], "variant", c["variant"])
