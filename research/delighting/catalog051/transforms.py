#!/usr/bin/env python3
"""Report 051 — query/index REPRESENTATIONS for the delighting ablation (scope 3).

Three representations, all class-free so they apply to arbitrary user photos:
  raw           — the sRGB image as-is (baseline).
  delight_T     — the research classical-delighted transmission map
                  (research/delighting/extract.py, auto class prior, no VLM):
                  background removed, illumination envelope divided out.
  luma_quotient — report 019's deterministic homomorphic luminance quotient
                  (a single Gaussian-blur log-luminance envelope divided out),
                  a cheap capture-normalization with no material model.

Question: does delighting/normalization improve wild->clean retrieval? (A
product-grounded capture-invariance eval either way.)
"""
import hashlib
import os
import subprocess
import sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT_ROOT = os.path.join(HERE, "..", "delighting_root") if False else os.path.dirname(HERE)
EXTRACT = os.path.join(os.path.dirname(HERE), "extract.py")
sys.path.insert(0, os.path.dirname(HERE))  # to import extract's helpers
import extract as ex  # noqa: E402

PYEXE = os.environ.get("RP_PYEXE", sys.executable)


def _key(path):
    return hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:16]


class DelightCache:
    """Runs extract.py to produce delighted T maps, cached by source-path hash."""
    def __init__(self, cache_dir, size=384):
        self.cache_dir = cache_dir
        self.size = size
        self.link_dir = os.path.join(cache_dir, "_links")
        self.out_dir = os.path.join(cache_dir, "T")
        os.makedirs(self.link_dir, exist_ok=True)
        os.makedirs(self.out_dir, exist_ok=True)

    def _tpath(self, path):
        return os.path.join(self.out_dir, f"{_key(path)}_T.png")

    def ensure(self, paths, batch=64):
        todo = [p for p in paths if not os.path.exists(self._tpath(p))]
        if not todo:
            return
        # symlink farm with unique names so extract.py's <stem>_T.png don't collide
        for start in range(0, len(todo), batch):
            chunk = todo[start:start + batch]
            links = []
            for p in chunk:
                lp = os.path.join(self.link_dir, f"{_key(p)}.jpg")
                if not os.path.exists(lp):
                    try:
                        os.symlink(os.path.abspath(p), lp)
                    except FileExistsError:
                        pass
                links.append(lp)
            cmd = [PYEXE, EXTRACT] + links + ["--no-vlm", "--out", self.out_dir,
                                              "--size", str(self.size)]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            sys.stderr.write(f"\r  delighted {min(start+batch,len(todo))}/{len(todo)}")
            sys.stderr.flush()
        sys.stderr.write("\n")

    def transform(self, path):
        tp = self._tpath(path)
        if not os.path.exists(tp):
            self.ensure([path])
        return np.array(Image.open(tp).convert("RGB"))


def luma_quotient(path, size=512):
    """Report 019 homomorphic normalization applied to an sRGB photo:
    divide linear luminance by its log-Gaussian envelope, keep chroma, re-encode."""
    img = Image.open(path).convert("RGB")
    if size:
        img.thumbnail((size, size), Image.LANCZOS)
    a = np.asarray(img).astype(np.float64) / 255.0
    lin = ex.srgb_to_lin(a)
    Y = ex.lum(lin)
    env = ex.luminance_envelope_quotient(Y)          # positive scalar field
    lin_norm = lin / np.clip(env, 1e-3, None)[..., None]
    # rescale to keep median luminance ~ original (avoid global brightness drift)
    out = ex.lin_to_srgb(np.clip(lin_norm, 0, 1))
    return (np.clip(out, 0, 1) * 255).astype(np.uint8)


def center_crop(path, frac=0.5, size=518):
    """Central-fraction crop: a hypothesis probe for the scene-domination
    failure (wild window/shop photos are mostly background; the sheet tends to
    occupy the central region). frac=0.5 keeps the middle 50% per axis."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    cw, ch = int(w * frac), int(h * frac)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    img = img.crop((x0, y0, x0 + cw, y0 + ch))
    if size:
        img.thumbnail((size, size), Image.LANCZOS)
    return np.asarray(img)


def crop_then_quotient(path, frac=0.5, size=512):
    """Center-crop then 019 luma-quotient — the combined cheap normalization."""
    a = center_crop(path, frac, size=None)
    img = Image.fromarray(a)
    img.thumbnail((size, size), Image.LANCZOS)
    a = np.asarray(img).astype(np.float64) / 255.0
    lin = ex.srgb_to_lin(a)
    Y = ex.lum(lin)
    env = ex.luminance_envelope_quotient(Y)
    lin_norm = lin / np.clip(env, 1e-3, None)[..., None]
    out = ex.lin_to_srgb(np.clip(lin_norm, 0, 1))
    return (np.clip(out, 0, 1) * 255).astype(np.uint8)
