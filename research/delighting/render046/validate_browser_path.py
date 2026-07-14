"""Validate the WebGL prototype's math WITHOUT a browser: decode the exact 256px
PNGs embedded in webgl_assets.json and reproduce the shader path in numpy --
SRGB8 auto-decode to linear, LINEAR box mip pyramid (== generateMipmap on an
sRGB texture), textureLod trilinear, L=T*scatter, sRGB out -- then compute the
same 0-255 sRGB MAE the in-page JS computes, at each family's fitted sigma_scale.
If these land near the 1024 numpy ceiling, the shader logic is faithful."""
import base64
import io
import json
import os

import numpy as np
from PIL import Image

from browser_render_046 import (build_mip_pyramid, texture_lod, sigma_to_lod,
                                srgb_to_lin, lin_to_srgb)

ASSETS = os.path.join(os.path.dirname(__file__), "..", "results", "046", "webgl_assets.json")


def decode(datauri):
    b = base64.b64decode(datauri.split(",", 1)[1])
    return np.asarray(Image.open(io.BytesIO(b))).astype(np.float32) / 255.0


def main():
    A = json.load(open(ASSETS))
    TEX = A["tex"]
    print(f"{'recipe':26s} {'sigfit':>7s} {'browser256':>11s} {'ceiling1024':>12s} {'delta':>7s}")
    deltas = []
    for f in A["families"]:
        B = srgb_to_lin(decode(f["B"])[..., :3])          # SRGB8 -> linear
        T = srgb_to_lin(decode(f["T"])[..., :3])          # SRGB8 -> linear
        h = decode(f["h"])
        if h.ndim == 3:
            h = h[..., 0]
        truth_srgb = decode(f["truth"])[..., :3]          # already sRGB (display space)

        _, up = build_mip_pyramid(B)                      # linear box pyramid
        nlev = up.shape[0]
        sig = f["sigma_scale"]
        sigma_px = sig * h * (TEX / 1024.0)               # shader mapping
        lod = np.clip(np.log2(np.maximum(sigma_px, 1.0)), 0.0, np.log2(TEX))
        scattered = texture_lod(up, lod)
        L = T * scattered
        out_srgb = lin_to_srgb(np.clip(L, 0, 1))
        mae = float(np.abs(out_srgb - truth_srgb).mean() * 255.0)
        d = mae - f["mae_scatter"]
        deltas.append(d)
        print(f"{f['recipe']:26s} {sig:7.0f} {mae:11.2f} {f['mae_scatter']:12.2f} {d:+7.2f}")
    d = np.array(deltas)
    print(f"\nbrowser256 vs numpy1024 ceiling: mean {d.mean():+.2f}, "
          f"abs-max {np.abs(d).max():.2f} MAE")


if __name__ == "__main__":
    main()
