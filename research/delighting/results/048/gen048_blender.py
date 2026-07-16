#!/usr/bin/env python3
"""Report 048 generation shim.

Blender 5.0.1's bundled Python has numpy but not scipy, and the app-bundle
site-packages is read-only + Blender ignores PYTHONPATH -- so `generate_synthetic.py`
(which lazily `from scipy.ndimage import zoom`s inside author_glass_arrays) cannot be
driven directly. This wrapper injects an isolated scipy install onto sys.path BEFORE
running the generator, then hands off to its __main__.

Install scipy once (matched to Blender's numpy 2.0.x ABI) into a private dir:
    BLPY=".../Blender.app/Contents/Resources/5.0/python/bin/python3.11"
    "$BLPY" -m pip install --target=/tmp/bl_scipy_pkg --no-deps --only-binary=:all: scipy==1.13.1

Then render (from research/delighting):
    BL_SCIPY_PATH=/tmp/bl_scipy_pkg <blender> -b -P results/048/gen048_blender.py -- \
        --out results/048/gen_data --recipe wispy-white --seed 6001 --count 1 \
        --light-variations 1 --validate --no-tex-dump
"""
import os
import sys
import runpy

_sc = os.environ.get("BL_SCIPY_PATH")
if _sc and _sc not in sys.path:
    sys.path.insert(0, _sc)

HERE = os.path.dirname(os.path.abspath(__file__))
GEN = os.path.join(HERE, "..", "..", "generate_synthetic.py")
runpy.run_path(os.path.abspath(GEN), run_name="__main__")
