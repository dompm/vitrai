#!/usr/bin/env python3
"""Report 051 — path-keyed embedding cache.

Embeds a set of images once per (backbone, representation) and memoizes to an
npz so index build, query eval, the representation ablation and the confidence
gate all reuse the same vectors. Keyed by "repr::abspath" so raw / delighted-T /
luma-quotient variants of the same file never collide.
"""
import os
import numpy as np
from embed import Embedder


class EmbedCache:
    def __init__(self, cache_path, backbone="dinov2-small"):
        self.cache_path = cache_path
        self.backbone = backbone
        self.vecs = {}
        if os.path.exists(cache_path):
            z = np.load(cache_path, allow_pickle=True)
            keys = z["keys"]
            arr = z["vecs"]
            self.vecs = {str(k): arr[i] for i, k in enumerate(keys)}
        self._emb = None

    def _embedder(self):
        if self._emb is None:
            self._emb = Embedder(backbone=self.backbone)
        return self._emb

    def get(self, paths, repr_name="raw", transform=None, progress=True):
        """Return (N, d) for paths under repr_name. `transform(path)->image` is
        applied for non-raw representations (image can be path/PIL/ndarray)."""
        keys = [f"{repr_name}::{os.path.abspath(p)}" for p in paths]
        missing = [(i, p, k) for i, (p, k) in enumerate(zip(paths, keys)) if k not in self.vecs]
        if missing:
            emb = self._embedder()
            items = []
            for _, p, _ in missing:
                items.append(transform(p) if transform is not None else p)
            new = emb.embed(items, normalize=True, progress=progress)
            for (i, p, k), v in zip(missing, new):
                self.vecs[k] = v.astype(np.float32)
            self.save()
        d = len(next(iter(self.vecs.values())))
        out = np.zeros((len(paths), d), dtype=np.float32)
        for i, k in enumerate(keys):
            out[i] = self.vecs[k]
        return out

    def save(self):
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        keys = list(self.vecs.keys())
        arr = np.stack([self.vecs[k] for k in keys]) if keys else np.zeros((0, 384), np.float32)
        np.savez_compressed(self.cache_path, keys=np.array(keys), vecs=arr)
