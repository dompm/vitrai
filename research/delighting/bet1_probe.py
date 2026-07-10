#!/usr/bin/env python3
"""Bet-1 falsification probe (report 028): off-the-shelf reflection removal in log space.

Hypothesis (report 027 Bet 1): our see-through split  photo = T_glass * B_background
is the multiplicative mirror of single-image reflection removal  I = T_layer + R_layer.
Take log:  log(photo) = log(T_glass) + log(B).  So a pretrained reflection-removal net,
fed normalized log(photo), might separate the flat glass tint from the transmitted
background with ZERO training, because its deep prior already knows natural backgrounds.

MODEL: DSRNet (ICCV 2023, "Single Image Reflection Separation via Component Synergy"),
the XReflection model-zoo checkpoint (dsr-25.8915.ckpt, PSNR 25.89 dB). Chosen because it
(a) has directly downloadable public weights (checkpoints.mingjia.li, no Google-Drive gate),
(b) EXPLICITLY emits BOTH a transmission layer and a reflection layer (component synergy),
which is exactly what the "is the background layer degenerate?" kill-check needs, and
(c) is a feed-forward CNN, fast enough to run many images on this M4 (MPS/CPU).

This script is inference-only. It needs, via env vars:
  XREFLECTION_DIR  = local clone of github.com/hainuo-wang/XReflection (for the arch + Vgg19)
  DSRNET_CKPT      = path to dsr-25.8915.ckpt
It reuses the report-014 assembled_bench.drag_test verbatim for scoring, so the numbers are
directly comparable to the standing raw 0.292 / classical 0.140 / grain 0.0085 (cathedral).

INPUT ADAPTATION (documented in the report):
  linear photo I -> logI = log(clip(I, EPS, inf))
  per-image robust min-max: lo,hi = percentile(logI, [PLO, PHI]); x = clip((logI-lo)/(hi-lo),0,1)
  feed x (a [0,1] "image") to DSRNet. Invert a returned layer y by:  exp(y*(hi-lo)+lo).
The two model outputs are un-normalized+exp'd back to LINEAR and treated as candidate
de-lit glass maps (both interpretations tested, since which layer catches the flat tint vs
the natural-looking background is precisely what the probe must discover).
"""
import os
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
XREF = os.environ.get("XREFLECTION_DIR")
CKPT = os.environ.get("DSRNET_CKPT")
EPS = 1e-3
PLO, PHI = 0.5, 99.5

_net = None
_vgg = None
_dev = None


def _load_model():
    global _net, _vgg, _dev
    if _net is not None:
        return
    assert XREF and os.path.isdir(XREF), "set XREFLECTION_DIR to the XReflection clone"
    assert CKPT and os.path.isfile(CKPT), "set DSRNET_CKPT to dsr-25.8915.ckpt"
    sys.path.insert(0, XREF)
    from xreflection.archs.dsrnet_arch import DSRNet
    from xreflection.losses.vgg import Vgg19
    _dev = "mps" if torch.backends.mps.is_available() else "cpu"
    net = DSRNet(width=64, middle_blk_num=12, enc_blk_nums=[2, 2, 4, 8],
                 dec_blk_nums=[2, 2, 2, 2], lrm_blk_nums=[2, 4])
    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    sd = {k[len("net_g."):]: v for k, v in ck["state_dict"].items() if k.startswith("net_g.")}
    miss, unexp = net.load_state_dict(sd, strict=False)
    assert not miss and not unexp, (len(miss), len(unexp))
    net.eval().to(_dev)
    vgg = Vgg19().eval().to(_dev)
    _net, _vgg = net, vgg


def _run_net(x_hw3):
    """x_hw3: HxWx3 float in [0,1]. Returns (t_layer, r_layer, recon) each HxWx3 in [0,1]-ish."""
    _load_model()
    x = torch.from_numpy(np.ascontiguousarray(x_hw3.transpose(2, 0, 1)[None])).float().to(_dev)
    with torch.no_grad():
        t, r, rr = _net(x, _vgg(x))
    to = lambda z: z[0].clamp(0, 1).cpu().numpy().transpose(1, 2, 0).astype(np.float64)
    return to(t), to(r), to(rr)


def _pad16(x):
    h, w = x.shape[:2]
    ph, pw = (-h) % 16, (-w) % 16
    if ph or pw:
        x = np.pad(x, ((0, ph), (0, pw), (0, 0)), mode="reflect")
    return x, h, w


def separate_log(I_lin, run_size=None):
    """The Bet-1 pipeline: normalized log(photo) -> DSRNet -> both layers back in LINEAR.

    Returns dict with candidate de-lit maps in linear space (RENDER-A resolution):
      'trans'  = exp(inv(model transmission layer))   -- SIRR's "clean natural image" output
      'refl'   = exp(inv(model reflection layer))      -- SIRR's "overlay/veil" output
      'trans_raw'/'refl_raw' = the raw [0,1] model layers (normalized-log space, for panels)
    """
    import cv2
    H, W = I_lin.shape[:2]
    work = I_lin
    if run_size and (H != run_size or W != run_size):
        work = cv2.resize(I_lin.astype(np.float32), (run_size, run_size),
                          interpolation=cv2.INTER_AREA).astype(np.float64)
    logI = np.log(np.clip(work, EPS, None))
    lo, hi = np.percentile(logI, PLO), np.percentile(logI, PHI)
    x = np.clip((logI - lo) / (hi - lo), 0, 1)
    xp, h0, w0 = _pad16(x)
    t_raw, r_raw, rr = _run_net(xp)
    t_raw, r_raw, rr = t_raw[:h0, :w0], r_raw[:h0, :w0], rr[:h0, :w0]

    def inv(y):
        lin = np.exp(y * (hi - lo) + lo)
        if lin.shape[:2] != (H, W):
            lin = cv2.resize(lin.astype(np.float32), (W, H),
                             interpolation=cv2.INTER_LINEAR).astype(np.float64)
        return lin

    def up(y):
        if y.shape[:2] != (H, W):
            return cv2.resize(y.astype(np.float32), (W, H),
                              interpolation=cv2.INTER_LINEAR).astype(np.float64)
        return y

    return {"trans": inv(t_raw), "refl": inv(r_raw),
            "trans_raw": up(t_raw), "refl_raw": up(r_raw),
            "logI_norm": up(x), "lo": float(lo), "hi": float(hi)}


def separate_srgb(I_lin, run_size=None):
    """CONTROL: run DSRNet natively on the sRGB display image (NO log). Tests whether the
    log-space reframing is what matters vs plain reflection removal on the multiplicative
    photo. Returns candidate de-lit maps back in LINEAR space."""
    import cv2
    import extract
    H, W = I_lin.shape[:2]
    work = I_lin
    if run_size and (H != run_size or W != run_size):
        work = cv2.resize(I_lin.astype(np.float32), (run_size, run_size),
                          interpolation=cv2.INTER_AREA).astype(np.float64)
    x = np.clip(extract.lin_to_srgb(np.clip(work, 0, 1)), 0, 1)
    xp, h0, w0 = _pad16(x)
    t_raw, r_raw, rr = _run_net(xp)
    t_raw, r_raw = t_raw[:h0, :w0], r_raw[:h0, :w0]

    def inv(y):
        lin = extract.srgb_to_lin(np.clip(y, 0, 1))
        if lin.shape[:2] != (H, W):
            lin = cv2.resize(lin.astype(np.float32), (W, H),
                             interpolation=cv2.INTER_LINEAR).astype(np.float64)
        return lin

    def up(y):
        return cv2.resize(y.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float64) \
            if y.shape[:2] != (H, W) else y

    return {"trans": inv(t_raw), "refl": inv(r_raw),
            "trans_raw": up(t_raw), "refl_raw": up(r_raw)}
