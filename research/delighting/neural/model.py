#!/usr/bin/env python3
"""Compact U-Net for shadow detection + transmittance correction (PoC).

Deliberately small (base=16 channels, 3 levels). This is a PoC on ~12 training
sheets; a big network would only memorize. The task is low-level and local
(find the darker-than-it-should-be patch, lift T back up), so a small receptive
field with skip connections is the right prior.

Input  (6ch): with-shadow photo linear RGB (3) + classical T from that photo (3)
Output (4ch): shadow-mask logit (1) + corrected transmittance T_pred (3, sigmoid)

Inference blends by the predicted mask so non-shadow pixels keep the classical
T exactly:  T_final = (1 - m) * T_ws + m * T_pred.
"""
import torch
import torch.nn as nn


def _block(cin, cout):
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1),
        nn.GroupNorm(min(8, cout), cout),
        nn.SiLU(inplace=True),
        nn.Conv2d(cout, cout, 3, padding=1),
        nn.GroupNorm(min(8, cout), cout),
        nn.SiLU(inplace=True),
    )


class ShadowUNet(nn.Module):
    def __init__(self, in_ch=6, base=16):
        super().__init__()
        self.enc1 = _block(in_ch, base)
        self.enc2 = _block(base, base * 2)
        self.enc3 = _block(base * 2, base * 4)
        self.pool = nn.MaxPool2d(2)
        self.bott = _block(base * 4, base * 4)
        self.up3 = nn.ConvTranspose2d(base * 4, base * 4, 2, stride=2)
        self.dec3 = _block(base * 8, base * 2)
        self.up2 = nn.ConvTranspose2d(base * 2, base * 2, 2, stride=2)
        self.dec2 = _block(base * 4, base)
        self.up1 = nn.ConvTranspose2d(base, base, 2, stride=2)
        self.dec1 = _block(base * 2, base)
        self.head = nn.Conv2d(base, 4, 1)

    def forward(self, x):
        # x[:, 3:6] is the classical T; the correction head is a residual on it.
        T_in = x[:, 3:6]
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        b = self.bott(self.pool(e3))
        d3 = self.dec3(torch.cat([self.up3(b), e3], 1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], 1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], 1))
        out = self.head(d1)
        mask_logit = out[:, 0:1]
        # residual correction, bounded, added to the classical T then clamped
        resid = torch.tanh(out[:, 1:4])
        T_pred = torch.clamp(T_in + resid, 0.0, 1.0)
        return mask_logit, T_pred


def blend(T_ws, mask_prob, T_pred):
    """Mask-gated output: non-shadow pixels keep the classical T exactly."""
    return (1 - mask_prob) * T_ws + mask_prob * T_pred
