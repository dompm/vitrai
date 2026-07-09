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

# NEURAL_DATA_SNAPSHOT / NEURAL_WEIGHTS let a second dataset generation (report
# 012, v2 synthetic data with fixed frame occluders) run through the same
# pipeline without disturbing the v1 snapshot/weights this report 010/011 file
# set was trained on.
DATA_SNAPSHOT = os.environ.get("NEURAL_DATA_SNAPSHOT", os.path.join(HERE, "data_snapshot"))
# CACHE_DIR holds classical maps precomputed from a specific extract.py. The
# NEURAL_CACHE env var lets us build a second cache from the FIXED extractor
# (report 009) without disturbing the original one (report 010 was trained on
# the original extractor's T). See report 011 (combined run).
CACHE_DIR = os.environ.get("NEURAL_CACHE", os.path.join(HERE, "cache"))
WEIGHTS = os.environ.get("NEURAL_WEIGHTS", os.path.join(HERE, "unet_shadow.pt"))

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

# Held-out test split for the ORIGINAL v1 dataset (report 010/011). Every test
# LIGHTING id is absent from training, so the test measures generalization to
# unseen shadows, not memorization. Cathedral (the class report 008 flagged)
# contributes the two primary test samples. Kept verbatim for reproducibility
# of the v1 reports; NOT used for v2 (those sample names don't exist there --
# see split() below, which falls back to a data-driven rule in that case).
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
    """Train/test split, held out by UNSEEN LIGHTING id (same recipe+seed
    sheet may appear in both, under a different lighting -- generalization,
    not memorization).

    If every v1 TEST_SAMPLES name is present, use that exact legacy split
    (reproduces reports 010/011 bit-for-bit). Otherwise (e.g. the v2 dataset,
    report 012, whose sample names differ) fall back to a deterministic
    data-driven rule: group by recipe (the `__` prefix before the seed), and
    hold out the alphabetically-last lighting id in each group.
    """
    names_set = set(names)
    if TEST_SAMPLES <= names_set:
        train = [n for n in names if n not in TEST_SAMPLES]
        test = [n for n in names if n in TEST_SAMPLES]
        return train, test

    by_recipe = {}
    for n in names:
        recipe = n.split("__")[0]
        by_recipe.setdefault(recipe, []).append(n)
    test_set = {sorted(group)[-1] for group in by_recipe.values()}
    train = [n for n in names if n not in test_set]
    test = [n for n in names if n in test_set]
    return train, test
