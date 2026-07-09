#!/usr/bin/env python3
"""Report-010 flagged the shadow mask false-firing on dark mullions/leads.
The v2 data replaces the full mullion grid with rarer, border-only occluders;
this checks whether the (re)trained mask still over-fires on them.

For every sample whose meta.json has frame occluders, we build the occluder
region with the same rule the eval harness uses (photo near-black while the
authored glass is not: photo_y < 0.018 & gt_y > 0.07 on the CLEAN photo, so a
cast shadow cannot contaminate the region), run the net on the with-shadow
input, and report the predicted-mask firing rate inside the occluder region vs
the non-occluder non-shadow glass. Over-fire = the net calling frame pixels
"shadow" and lifting them; on real photos of dark GLASS that behavior would
brighten true material.
"""
import json
import os
import sys

import numpy as np
import torch

import common
sys.path.insert(0, common.DELIGHT)
import extract  # noqa: E402
from model import ShadowUNet  # noqa: E402


def main():
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    ckpt = torch.load(common.WEIGHTS, map_location=device, weights_only=False)
    net = ShadowUNet(in_ch=ckpt["in_ch"], base=ckpt["base"]).to(device).eval()
    net.load_state_dict(ckpt["state_dict"])

    names = common.list_samples()
    _, test_names = common.split(names)
    print(f"weights={common.WEIGHTS}")
    print(f"{'sample':44s} {'occl%':>6s} {'fire@occl':>9s} {'fire@glass':>10s} {'lift@occl':>9s} split")
    for name in names:
        meta = json.load(open(os.path.join(common.DATA_SNAPSHOT, name, "meta.json")))
        occl = meta.get("frame_occluders") or []
        if not occl:
            continue
        z = np.load(os.path.join(common.CACHE_DIR, name + ".npz"))
        lin_ws = z["lin_ws"].astype(np.float64)
        gt_T = z["gt_T"].astype(np.float64)
        shadow = z["shadow"]

        # occluder region from the CLEAN photo (same rule as epi.valid_mask)
        d = os.path.join(common.DATA_SNAPSHOT, name)
        lin_ns = extract.load_linear(os.path.join(d, "without_shadow_photo.png"), None, common.SIZE)
        py = extract.lum(lin_ns.astype(np.float64))
        gy = extract.lum(gt_T)
        occl_px = (py < 0.018) & (gy > 0.07)
        glass_px = ~occl_px & ~shadow

        x = np.concatenate([z["lin_ws"], z["T_ws"]], axis=-1)
        xt = torch.from_numpy(x).permute(2, 0, 1)[None].float().to(device)
        with torch.no_grad():
            mask_logit, T_pred = net(xt)
            mprob = torch.sigmoid(mask_logit)[0, 0].cpu().numpy()
            T_pred = T_pred[0].permute(1, 2, 0).cpu().numpy()

        T_ws = z["T_ws"].astype(np.float64)
        # how much the blended output would move T inside the occluder region
        m3 = mprob[..., None]
        T_final = (1 - m3) * T_ws + m3 * T_pred
        lift = np.abs(T_final - T_ws).mean(-1)

        fire_occl = float((mprob > 0.5)[occl_px].mean() * 100) if occl_px.any() else float("nan")
        fire_glass = float((mprob > 0.5)[glass_px].mean() * 100)
        lift_occl = float(lift[occl_px].mean()) if occl_px.any() else float("nan")
        split = "TEST" if name in set(test_names) else "train"
        print(f"{name:44s} {occl_px.mean()*100:6.1f} {fire_occl:9.1f} {fire_glass:10.1f} {lift_occl:9.3f} {split}")


if __name__ == "__main__":
    main()
