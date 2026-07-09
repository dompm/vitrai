#!/usr/bin/env python3
"""Shared config + helpers for the neural shadow-removal PoC (report 010).

The task: cast shadows in a photo become fake dark transmittance in the
classical extractor (T ~= I/L; a shadow darkens I but not L). Report 008 showed
this is where classical material-relight LOSES to a raw pixel copy on cathedral
glass INSIDE the shadow. We have supervised pairs (with/without shadow of the
identical sheet), so we learn a POST-PROCESS on top of the classical extractor:
detect the shadow and lift T back to its shadow-free value.

Everything here is class-agnostic; shadow removal is a low-level correction.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.dirname(HERE)  # research/delighting
sys.path.insert(0, DELIGHT)

import extract  # noqa: E402  (classical pipeline, reused verbatim)

DATA_SNAPSHOT = os.path.join(HERE, "data_snapshot")
CACHE_DIR = os.path.join(HERE, "cache")
WEIGHTS = os.path.join(HERE, "unet_shadow.pt")

# Working resolution for the cached maps (max dim). The classical extractor and
# the eval both run at this size.
SIZE = 512

# recipe -> classical glass_class (mirrors eval_preview_invariance.CLASS_MAP)
CLASS_MAP = {
    "cathedral-green": "cathedral-clear",
    "cathedral-amber": "cathedral-clear",
    "dark-opaque": "dark-opaque",
    "wispy-white": "wispy",
    "streaky-mix": "wispy",
}

# Held-out test split. Every test LIGHTING id is absent from training, so the
# test measures generalization to unseen shadows, not memorization. Cathedral
# (the class report 008 flagged) contributes the two primary test samples.
TEST_SAMPLES = {
    "cathedral-green__seed42__light7527",
    "cathedral-green__seed43__light1262",
    "streaky-mix__seed45__light7995",
    "wispy-white__seed46__light6553",
    "dark-opaque__seed44__light8879",
}


def list_samples():
    if not os.path.isdir(DATA_SNAPSHOT):
        raise SystemExit(f"missing snapshot dir {DATA_SNAPSHOT}; run prepare_data.py")
    out = []
    for name in sorted(os.listdir(DATA_SNAPSHOT)):
        d = os.path.join(DATA_SNAPSHOT, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "meta.json")):
            out.append(name)
    return out


def split(names):
    train = [n for n in names if n not in TEST_SAMPLES]
    test = [n for n in names if n in TEST_SAMPLES]
    return train, test
