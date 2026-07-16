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

# report-023 reserved holdout batch (EVAL_PROTOCOL §3b): TEST wholesale.
HOLDOUT_BATCH = range(800, 813)


# ------------------------------------------------------------------ split rule
def seed_is_test(seed):
    """EVAL_PROTOCOL §3b: TEST iff seed%5==0 OR in the 800-812 reserved batch."""
    return (seed % 5 == 0) or (seed in HOLDOUT_BATCH)


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


def _photo_linear(sample, variant):
    """scene-linear photo. variant in {without,with}. Falls back to png->srgb_to_lin."""
    exr = os.path.join(sample, f"{variant}_shadow_photo_linear.exr")
    if os.path.exists(exr):
        a = _imread_exr(exr)
        if a is not None:
            return a
    png = os.path.join(sample, f"{variant}_shadow_photo.png")
    if not os.path.exists(png):
        png = os.path.join(sample, "photo.png")
    if os.path.exists(png):
        a = cv2.imread(png, cv2.IMREAD_COLOR)[..., ::-1].astype(np.float32) / 255.0
        return srgb_to_lin(a)
    return None


def _load_gt_T(sample):
    p = os.path.join(sample, "gt_T.exr")
    if os.path.exists(p):
        return _imread_exr(p)
    p = os.path.join(sample, "gt_T.png")
    if os.path.exists(p):
        a = cv2.imread(p, cv2.IMREAD_UNCHANGED)
        if a is None:
            return None
        a = a[..., ::-1].astype(np.float32)
        return a / (65535.0 if a.max() > 255 else 255.0)
    return None


def _load_gt_h(sample):
    p = os.path.join(sample, "gt_h.png")
    if os.path.exists(p):
        raw = cv2.imread(p, cv2.IMREAD_UNCHANGED).astype(np.float32) / 65535.0
        if raw.ndim == 3:
            raw = raw[..., 0]
        return srgb_to_lin(raw)[..., None]
    p = os.path.join(sample, "gt_h.exr")
    if os.path.exists(p):
        a = _imread_exr(p)
        if a is None:
            return None
        if a.ndim == 3:
            a = a[..., 0]
        return srgb_to_lin(a)[..., None]
    return None


def _load_gt_sigma_s(sample):
    """Report 048: haze-driven subsurface-scatter radius, emitted by the generator as
    gt_sigma_s (report 043 decompose_haze) on the byte-identical encode path as gt_h --
    so it decodes exactly like h (16-bit PNG / EXR, srgb_to_lin to authored-linear).
    Returns HxWx1 float32, or None on pre-043 renders (handled as has_sigma_s=False)."""
    p = os.path.join(sample, "gt_sigma_s.png")
    if os.path.exists(p):
        raw = cv2.imread(p, cv2.IMREAD_UNCHANGED).astype(np.float32) / 65535.0
        if raw.ndim == 3:
            raw = raw[..., 0]
        return srgb_to_lin(raw)[..., None]
    p = os.path.join(sample, "gt_sigma_s.exr")
    if os.path.exists(p):
        a = _imread_exr(p)
        if a is None:
            return None
        if a.ndim == 3:
            a = a[..., 0]
        return srgb_to_lin(a)[..., None]
    return None


def _load_mask(sample, name):
    p = os.path.join(sample, name)
    if not os.path.exists(p):
        return None
    a = cv2.imread(p, cv2.IMREAD_UNCHANGED).astype(np.float32)
    if a.ndim == 3:
        a = a.mean(-1)
    return (a / (65535.0 if a.max() > 255 else 255.0))[..., None]


# ------------------------------------------------------------------ dataset
class GlassDelightDataset:
    """Framework-agnostic (numpy) sample store + crop sampler. train.py wraps the
    tensors; keeping this torch-free means it also runs under the Modal image and in
    a plain numpy smoke test."""

    def __init__(self, roots, split="train", crop=512, work_size=768,
                 augment=None, input_variant="random", require_B=False, seed=0):
        assert split in ("train", "test", "all")
        self.crop = crop
        self.work_size = work_size
        self.split = split
        self.augment = (split == "train") if augment is None else augment
        self.input_variant = input_variant
        self.require_B = require_B
        self.rng = np.random.default_rng(seed)
        self._cache = {}   # idx -> downsampled component dict (avoids re-reading 50MB EXRs)
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
                is_test = seed_is_test(seed)
                if self.split == "train" and is_test:
                    continue
                if self.split == "test" and not is_test:
                    continue
                if self.require_B and not os.path.exists(os.path.join(d, "gt_B.exr")):
                    continue
                out.append({"dir": d, "seed": seed, "recipe": meta.get("class_label", "?"),
                            "is_test": is_test})
        return out

    def __len__(self):
        return len(self.samples)

    # ---- component load (cached, downsampled to work_size) ----
    def _components(self, idx):
        """Read + downsample every channel once; cache. gt_T defines the grid."""
        if idx in self._cache:
            return self._cache[idx]
        d = self.samples[idx]["dir"]
        T = _load_gt_T(d)
        h = _load_gt_h(d)
        sigma_s = _load_gt_sigma_s(d)
        photo_wo = _photo_linear(d, "without")
        if T is None or h is None or photo_wo is None:
            self._cache[idx] = None
            return None
        H, W = T.shape[:2]
        has_with = os.path.exists(os.path.join(d, "with_shadow_photo_linear.exr")) or \
            os.path.exists(os.path.join(d, "with_shadow_photo.png"))
        photo_w = _photo_linear(d, "with") if has_with else None
        mark = _load_mask(d, "gt_mark_mask.png")
        mark = np.zeros((H, W, 1), np.float32) if mark is None else (mark > 0.5).astype(np.float32)
        Bp = os.path.join(d, "gt_B.exr")
        B = _imread_exr(Bp) if os.path.exists(Bp) else None
        Vp = os.path.join(d, "gt_veil.exr")
        veil = load_aov_exr(Vp) if os.path.exists(Vp) else None

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
        self._cache[idx] = comp
        return comp

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
        """Loader-side camera pipeline (consultant brief): applied to the INPUT photo
        only; every target is the intrinsic and stays fixed, so this directly trains
        nuisance (N) invariance. All ops in scene-linear except the tone-map/JPEG round
        trip which goes through the sRGB view."""
        p = photo
        # 1) exposure jitter: global gain in stops
        p = p * float(2.0 ** self.rng.uniform(-0.7, 0.7))
        # 2) sensor noise: signal-dependent Gaussian in linear
        sigma = float(self.rng.uniform(0.0, 0.02))
        if sigma > 0:
            p = p + self.rng.normal(0, sigma, p.shape).astype(np.float32) * np.sqrt(np.clip(p, 0, None) + 1e-3)
        # 3) tone-map jitter + 4) JPEG recompress: round-trip through the sRGB view
        srgb = np.clip(p, 0, 1) ** (1.0 / self.rng.uniform(2.0, 2.8))   # gamma/tone jitter
        u8 = (np.clip(srgb, 0, 1) * 255).astype(np.uint8)
        if self.rng.random() < 0.8:
            q = int(self.rng.integers(35, 95))
            ok, enc = cv2.imencode(".jpg", u8[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, q])
            if ok:
                u8 = cv2.imdecode(enc, cv2.IMREAD_COLOR)[..., ::-1]
        p = srgb_to_lin(u8.astype(np.float32) / 255.0)
        return p.astype(np.float32)

    def sample_crop(self, idx=None):
        """One augmented training crop (dict of HxWxC numpy). Identity-holdout is
        already enforced at index time, so any idx here is split-legal."""
        if idx is None:
            idx = int(self.rng.integers(len(self.samples)))
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
