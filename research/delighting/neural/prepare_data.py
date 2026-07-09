#!/usr/bin/env python3
"""Precompute the per-sample training/eval cache.

For each snapshot sample we run the *classical* extractor twice -- on the
with-shadow photo and on the clean without-shadow photo -- and store the maps
plus ground truth as a compact .npz. This is the expensive step (classical
pipeline x2 per sample); doing it once keeps training fast and crash-cheap.

Cache contents (all float32, HxWx{1,3}, at common.SIZE):
  lin_ws     with-shadow photo, linear RGB           (network input)
  T_ws,h_ws  classical maps from the with-shadow photo (network input + baseline)
  T_ns       classical T from the clean photo        (shadow-removal TARGET)
  gt_T,gt_h  authored ground truth                    (eval preview target)
  shadow     bool: where the with-shadow photo is darker than clean (pair diff,
             same signal eval_preview_invariance.detect_shadow uses)  (mask target)
  valid      bool: glass pixels excluding marks/frame (eval mask)
  glass_class

The shadow mask is derived from the photo PAIR (train/eval only); at inference
the network sees only the single with-shadow photo -- no leakage.
"""
import glob
import json
import os

import numpy as np
from PIL import Image

import common
import extract
import eval_preview_invariance as epi


def _resize(a, hw):
    import cv2
    H, W = hw
    return cv2.resize(a.astype(np.float32), (W, H), interpolation=cv2.INTER_AREA)


def build_one(name):
    d = os.path.join(common.DATA_SNAPSHOT, name)
    meta = json.load(open(os.path.join(d, "meta.json")))
    label = meta["class_label"]
    glass_class = common.CLASS_MAP[label]

    ws_path = os.path.join(d, "with_shadow_photo.png")
    ns_path = os.path.join(d, "without_shadow_photo.png")

    lin_ws = extract.load_linear(ws_path, None, common.SIZE)
    lin_ns = extract.load_linear(ns_path, None, common.SIZE)

    maps_ws = extract.extract_maps(lin_ws, glass_class, mark_region="none")
    maps_ns = extract.extract_maps(lin_ns, glass_class, mark_region="none")

    H, W = maps_ws["h"].shape
    gtT = epi.load_gt_T(d)
    gth = epi.load_gt_h(d)
    gtT = _resize(gtT, (H, W)).astype(np.float32)
    if gth.ndim == 2:
        gth = gth[..., None]
    gth = _resize(gth, (H, W))
    if gth.ndim == 3:
        gth = gth[..., 0]

    # shadow region + valid glass mask (identical logic to the eval harness)
    shadow = epi.detect_shadow(lin_ns, lin_ws)
    valid = epi.valid_mask(d, lin_ns, gtT.astype(np.float64), gtT.astype(np.float64))
    shadow = shadow & valid

    return {
        "lin_ws": lin_ws.astype(np.float32),
        "T_ws": maps_ws["T"].astype(np.float32),
        "h_ws": maps_ws["h"].astype(np.float32),
        "T_ns": maps_ns["T"].astype(np.float32),
        "h_ns": maps_ns["h"].astype(np.float32),
        "gt_T": gtT.astype(np.float32),
        "gt_h": gth.astype(np.float32),
        "shadow": shadow.astype(np.bool_),
        "valid": valid.astype(np.bool_),
        "glass_class": glass_class,
        "class_label": label,
    }


def main():
    os.makedirs(common.CACHE_DIR, exist_ok=True)
    names = common.list_samples()
    for name in names:
        out = os.path.join(common.CACHE_DIR, name + ".npz")
        c = build_one(name)
        np.savez_compressed(
            out,
            lin_ws=c["lin_ws"], T_ws=c["T_ws"], h_ws=c["h_ws"],
            T_ns=c["T_ns"], h_ns=c["h_ns"], gt_T=c["gt_T"], gt_h=c["gt_h"],
            shadow=c["shadow"], valid=c["valid"],
            glass_class=c["glass_class"], class_label=c["class_label"],
        )
        print(f"{name:44s} shadow={c['shadow'].mean()*100:5.1f}%  valid={c['valid'].mean()*100:5.1f}%  class={c['glass_class']}")
    print(f"\ncached {len(names)} samples -> {common.CACHE_DIR}")


if __name__ == "__main__":
    main()
