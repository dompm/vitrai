#!/usr/bin/env python3
"""Report 051 — shared self-supervised visual embedder for catalog retrieval.

DINOv2-small (facebook/dinov2-small, 384-d) via HF transformers on MPS.
Verified runnable in this env before building around it (lab lesson, report 028):
loads in ~10 s, forward pass on MPS, returns a 384-d CLS/pooler embedding.

The embedder accepts image *paths*, PIL images, or HxWx3 uint8/float arrays, so
the same code embeds catalog swatches, wild query photos, and derived query
representations (delighted-T, luma-quotient) that live only in memory.

CLIP (openai ViT-B/32) is provided as an alternative backbone behind the same
interface for the backbone-choice ablation.
"""
import os
import sys
import numpy as np
from PIL import Image

import torch


def _to_pil(x):
    if isinstance(x, Image.Image):
        return x.convert("RGB")
    if isinstance(x, str):
        return Image.open(x).convert("RGB")
    if isinstance(x, np.ndarray):
        a = x
        if a.dtype != np.uint8:
            a = np.clip(a, 0.0, 1.0) * 255.0 if a.max() <= 1.0 + 1e-6 else np.clip(a, 0, 255)
            a = a.astype(np.uint8)
        if a.ndim == 2:
            a = np.stack([a] * 3, axis=-1)
        return Image.fromarray(a).convert("RGB")
    raise TypeError(f"cannot coerce {type(x)} to PIL image")


class Embedder:
    def __init__(self, backbone="dinov2-small", device=None, batch_size=16):
        self.backbone = backbone
        self.batch_size = batch_size
        if device is None:
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.device = device
        if backbone.startswith("dinov2"):
            from transformers import AutoImageProcessor, AutoModel
            name = f"facebook/{backbone}"
            self.proc = AutoImageProcessor.from_pretrained(name)
            self.model = AutoModel.from_pretrained(name).eval().to(device)
            self.dim = self.model.config.hidden_size
            self._kind = "dinov2"
        elif backbone.startswith("clip"):
            from transformers import CLIPProcessor, CLIPModel
            name = "openai/clip-vit-base-patch32"
            self.proc = CLIPProcessor.from_pretrained(name)
            self.model = CLIPModel.from_pretrained(name).eval().to(device)
            self.dim = self.model.config.projection_dim
            self._kind = "clip"
        else:
            raise ValueError(f"unknown backbone {backbone}")

    @torch.no_grad()
    def embed(self, items, normalize=True, progress=False):
        """items: iterable of path|PIL|ndarray. Returns (N, dim) float32."""
        items = list(items)
        out = np.zeros((len(items), self.dim), dtype=np.float32)
        for start in range(0, len(items), self.batch_size):
            chunk = items[start:start + self.batch_size]
            pil = [_to_pil(x) for x in chunk]
            if self._kind == "dinov2":
                inp = self.proc(images=pil, return_tensors="pt").to(self.device)
                res = self.model(**inp)
                # pooler_output = layernorm(CLS); robust global descriptor
                feat = res.pooler_output if res.pooler_output is not None else res.last_hidden_state[:, 0]
            else:  # clip
                inp = self.proc(images=pil, return_tensors="pt").to(self.device)
                feat = self.model.get_image_features(**inp)
            feat = feat.float().cpu().numpy()
            out[start:start + len(chunk)] = feat
            if progress:
                sys.stderr.write(f"\r  embedded {start + len(chunk)}/{len(items)}")
                sys.stderr.flush()
        if progress:
            sys.stderr.write("\n")
        if normalize:
            n = np.linalg.norm(out, axis=1, keepdims=True)
            n[n == 0] = 1.0
            out = out / n
        return out


if __name__ == "__main__":
    # self-test
    emb = Embedder()
    x = (np.random.rand(300, 300, 3) * 255).astype(np.uint8)
    v = emb.embed([x, x])
    print(f"backbone={emb.backbone} dim={emb.dim} device={emb.device} "
          f"out={v.shape} norm={np.linalg.norm(v[0]):.3f} "
          f"selfsim={float(v[0] @ v[1]):.4f}")
