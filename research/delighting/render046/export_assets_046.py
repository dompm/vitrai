"""046 -- export per-family maps as base64 PNG data-URIs + fitted params for the
self-contained WebGL prototype (render046.html). All maps downscaled to TEX px.

Color-space contract (must match browser_render_046 numpy exactly):
  B, T   : scene-linear -> sRGB-encoded 8-bit PNG; the shader sRGB-decodes them
           back to the linear multiplier/backdrop (raw gt_T is used LINEARLY per
           oracle 045, and the sRGB round-trip preserves it to 8-bit).
  h      : linear grayscale 8-bit (used directly as sigma_s = scale*h driver).
  normal : raw gt_normal clipped [0,1], linear 8-bit; shader decodes n = 2v-1.
  truth  : Cycles struct_photo_linear -> sRGB 8-bit (display + JS diff/MAE ref).
"""
import base64
import io
import json
import os

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np
from PIL import Image

from browser_render_046 import read_exr, lin_to_srgb, FAMILY, run_sample

TEX = 256
ORDER = ["cathedral-green", "cathedral-amber", "streaky-mix", "streaky-fine-texture",
         "wispy-white", "saturated-opalescent", "ring-mottle", "dark-ruby",
         "dark-textured", "baroque-rolling-wave", "confetti-shard", "fracture-streamer"]


def png_datauri(arr_u8, mode):
    im = Image.fromarray(arr_u8, mode)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def ds(a, interp=cv2.INTER_AREA):
    return cv2.resize(a, (TEX, TEX), interpolation=interp)


def main():
    data = os.environ.get("DATA046")
    out = os.path.join(os.path.dirname(__file__), "..", "results", "046")
    os.makedirs(out, exist_ok=True)
    dirs = {os.path.basename(d).split("__")[0]: os.path.join(data, os.path.basename(d))
            for d in os.listdir(data)
            if os.path.isdir(os.path.join(data, d))
            and os.path.exists(os.path.join(data, d, "meta.json"))}

    families = []
    for recipe in ORDER:
        d = dirs[recipe]
        T = np.clip(read_exr(os.path.join(d, "gt_T.exr")), 0, 1)
        h = read_exr(os.path.join(d, "gt_h.exr"))
        if h.ndim == 3:
            h = h[..., 0]
        h = np.clip(h, 0, 1)
        normal = np.clip(read_exr(os.path.join(d, "gt_normal.exr")), 0, 1)
        B = read_exr(os.path.join(d, "struct_B.exr"))
        truth = read_exr(os.path.join(d, "struct_photo_linear.exr"))

        B_u8 = (lin_to_srgb(ds(B)) * 255 + 0.5).astype(np.uint8)
        T_u8 = (lin_to_srgb(ds(T)) * 255 + 0.5).astype(np.uint8)
        h_u8 = (ds(h) * 255 + 0.5).astype(np.uint8)
        n_u8 = (ds(normal) * 255 + 0.5).astype(np.uint8)
        tr_u8 = (lin_to_srgb(ds(truth)) * 255 + 0.5).astype(np.uint8)

        # fitted per-family params from the numpy ceiling run
        res, _, _ = run_sample(d)
        families.append({
            "recipe": recipe,
            "family": FAMILY[recipe],
            "sigma_scale": res["sigma_scale"],
            "refr_gain": res["refr_gain"],
            "mae_scatter": round(res["tiers"]["t1_scatter"]["mae"], 2),
            "ssim_scatter": round(res["tiers"]["t1_scatter"]["ssim"], 4),
            "B": png_datauri(B_u8, "RGB"),
            "T": png_datauri(T_u8, "RGB"),
            "h": png_datauri(h_u8, "L"),
            "normal": png_datauri(n_u8, "RGB"),
            "truth": png_datauri(tr_u8, "RGB"),
        })
        print(f"{recipe:26s} sig={res['sigma_scale']:6.1f} refr={res['refr_gain']:5.1f} "
              f"mae={res['tiers']['t1_scatter']['mae']:.2f}", flush=True)

    payload = {"tex": TEX, "families": families}
    p = os.path.join(out, "webgl_assets.json")
    with open(p, "w") as fp:
        json.dump(payload, fp)
    kb = os.path.getsize(p) / 1024
    print(f"\nwrote {p}  ({kb:.0f} KB, {len(families)} families)")


if __name__ == "__main__":
    main()
