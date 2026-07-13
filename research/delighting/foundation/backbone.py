#!/usr/bin/env python3
"""Iteration 038 / deliverable 3 (model) — the Bet-2 FoundationDelighter.

Bet 2 (report 027): stand on a pretrained latent-diffusion dense predictor (Marigold /
RGB<->X style) and fine-tune it with a LoRA adapter + a small multi-channel head to emit
the OUTPUT_CONTRACT tier-1 state, instead of training GlassNet from scratch. The natural-
image prior in the backbone is the "what does a background look like" knowledge the T*B
split needs (report 027 §Bet 2 rationale).

Architecture (deliberately a deterministic single-step reformulation of Marigold, so the
loop is cheap enough to smoke-test on an M4 and so a full sampling schedule is not on the
critical path — Garcia et al. "fine-tuning image-conditional diffusion is easier than you
think"):

  photo --(frozen VAE encode)--> z_rgb (Cx H/8 x W/8)
  [z_rgb ; z_init] --(pretrained UNet + LoRA, fixed timestep)--> z_T_hat
  z_T_hat --(frozen VAE decode)--> T                (the primary intrinsic, Marigold-faithful)
  [z_rgb ; z_T_hat] --(trainable AuxHead, learned x8 upsample)--> h,B,shadow,mark,conf

Backbones (see verify_backbone.py for what actually downloads):
  marigold-iid | marigold-depth : real transfer prior (VAE frozen, UNet LoRA-adapted)
  sd2                            : raw SD2 VAE+UNet
  tiny                           : randomly-initialised small VAE+UNet of the SAME diffusers
                                   classes — for the no-download local smoke test (proves the
                                   identical train/save/eval code path).

Only the LoRA params + AuxHead train by default (`freeze_backbone=True`) — the report-brief's
"frozen backbone + head only" smoke config and the cheapest real first run.
"""
import os

import torch
import torch.nn as nn
import torch.nn.functional as F

# tier-1 aux channels emitted alongside the VAE-decoded T
AUX_CHANNELS = ("h", "B", "shadow", "mark", "conf")
AUX_DIMS = {"h": 1, "B": 3, "shadow": 1, "mark": 1, "conf": 1}
AUX_TOTAL = sum(AUX_DIMS.values())  # 7


def build_vae_unet(backbone, dtype, cache_only=False):
    """Return (vae, unet, cross_attention_dim, empty_embed_or_None, meta)."""
    from diffusers import AutoencoderKL, UNet2DConditionModel

    if backbone == "tiny":
        # deterministic init so the frozen tiny base is IDENTICAL across train + eval
        # (save_adapter persists only LoRA+AuxHead; the real backbone is deterministic
        # from pretrained weights, so this only matters for the tiny stand-in).
        torch.manual_seed(0)
        vae = AutoencoderKL(
            in_channels=3, out_channels=3, latent_channels=4,
            down_block_types=("DownEncoderBlock2D", "DownEncoderBlock2D", "DownEncoderBlock2D"),
            up_block_types=("UpDecoderBlock2D", "UpDecoderBlock2D", "UpDecoderBlock2D"),
            block_out_channels=(32, 64, 64), layers_per_block=1,
        )
        unet = UNet2DConditionModel(
            sample_size=32, in_channels=8, out_channels=4,
            down_block_types=("CrossAttnDownBlock2D", "CrossAttnDownBlock2D", "DownBlock2D"),
            up_block_types=("UpBlock2D", "CrossAttnUpBlock2D", "CrossAttnUpBlock2D"),
            block_out_channels=(32, 64, 64), layers_per_block=1,
            cross_attention_dim=32, norm_num_groups=8,
        )
        return vae, unet, 32, None, {"backbone": "tiny", "downloaded": False}

    ids = {
        "marigold-iid": "prs-eth/marigold-iid-appearance-v1-1",
        "marigold-depth": "prs-eth/marigold-depth-v1-0",
        "sd2": "stabilityai/stable-diffusion-2-1",
    }
    model_id = ids[backbone]
    kw = {"torch_dtype": dtype}
    if cache_only:
        kw["local_files_only"] = True
    vae = AutoencoderKL.from_pretrained(model_id, subfolder="vae", **kw)
    unet = UNet2DConditionModel.from_pretrained(model_id, subfolder="unet", **kw)
    cad = int(unet.config.cross_attention_dim)
    # empty-text embedding: Marigold conditions on the empty prompt. Use the real one
    # when the text encoder is present; else zeros (documented scaffold fallback).
    empty = None
    try:
        from transformers import CLIPTextModel, CLIPTokenizer
        tok = CLIPTokenizer.from_pretrained(model_id, subfolder="tokenizer", **({"local_files_only": True} if cache_only else {}))
        te = CLIPTextModel.from_pretrained(model_id, subfolder="text_encoder", **kw)
        ids_ = tok("", padding="max_length", max_length=tok.model_max_length, return_tensors="pt").input_ids
        with torch.no_grad():
            empty = te(ids_)[0]  # (1,77,cad)
        del te
    except Exception:
        empty = None
    return vae, unet, cad, empty, {"backbone": backbone, "model_id": model_id, "downloaded": True}


class AuxHead(nn.Module):
    """Small learned decoder: latent-resolution features -> full-res aux channels.
    Trained from scratch (the multi-channel extension of the denoising head)."""

    def __init__(self, in_ch, out_ch=AUX_TOTAL, base=64, upsample=8):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(in_ch, base, 3, padding=1), nn.GroupNorm(8, base), nn.SiLU(),
            nn.Conv2d(base, base, 3, padding=1), nn.GroupNorm(8, base), nn.SiLU(),
        )
        ups = []
        n = 0
        cur = base
        while (1 << n) < upsample:
            ups += [nn.Upsample(scale_factor=2, mode="nearest"),
                    nn.Conv2d(cur, max(cur // 2, 16), 3, padding=1),
                    nn.GroupNorm(8, max(cur // 2, 16)), nn.SiLU()]
            cur = max(cur // 2, 16)
            n += 1
        self.up = nn.Sequential(*ups)
        self.out = nn.Conv2d(cur, out_ch, 1)

    def forward(self, feat, out_hw):
        x = self.up(self.stem(feat))
        x = self.out(x)
        if x.shape[-2:] != out_hw:
            x = F.interpolate(x, size=out_hw, mode="bilinear", align_corners=False)
        return x


class FoundationDelighter(nn.Module):
    def __init__(self, backbone="tiny", dtype=torch.float32, freeze_backbone=True,
                 lora_rank=8, cache_only=False, fixed_timestep=1):
        super().__init__()
        self.backbone_name = backbone
        self.fixed_timestep = fixed_timestep
        vae, unet, cad, empty, meta = build_vae_unet(backbone, dtype, cache_only)
        self.meta = meta
        self.vae = vae
        self.unet = unet
        self.cross_attention_dim = cad
        self.latent_ch = int(vae.config.latent_channels)
        # Marigold-depth UNet is in=8/out=4 (rgb+depth); Marigold-IID is in=12/out=8
        # (rgb + albedo + material). Generalise: fill the non-rgb input latents with
        # zeros, and read the primary intrinsic from the first latent block of the out.
        self.unet_in = int(unet.config.in_channels)
        self.unet_out = int(unet.config.out_channels)
        self.vae_scale = float(getattr(vae.config, "scaling_factor", 0.18215))
        self.register_buffer("empty_embed", empty if empty is not None
                             else torch.zeros(1, 1, cad), persistent=False)

        # freeze VAE always (Marigold recipe); freeze UNet base weights, add LoRA
        for p in self.vae.parameters():
            p.requires_grad_(False)
        self.vae.eval()
        self.lora_ok = False
        if freeze_backbone:
            for p in self.unet.parameters():
                p.requires_grad_(False)
            self._add_lora(lora_rank)

        self.aux = AuxHead(in_ch=self.latent_ch * 2, out_ch=AUX_TOTAL)

    def _add_lora(self, rank):
        try:
            from peft import LoraConfig
            cfg = LoraConfig(r=rank, lora_alpha=rank,
                             target_modules=["to_q", "to_k", "to_v", "to_out.0"],
                             lora_dropout=0.0, bias="none")
            self.unet.add_adapter(cfg)
            self.lora_ok = True
        except Exception as e:  # pragma: no cover
            print(f"[backbone] LoRA injection failed ({e}); training AuxHead only")
            self.lora_ok = False

    # ------------------------------------------------------------------ forward
    def encode(self, img01):
        """img01 in [0,1] RGB (B,3,H,W) -> latent mean (scaled)."""
        x = img01 * 2.0 - 1.0
        x = x.to(dtype=self.vae.dtype)
        with torch.no_grad():
            z = self.vae.encode(x).latent_dist.mode()
        return z * self.vae_scale

    def decode(self, z):
        # NO `torch.no_grad()` here (bug found in report 040's gate1b): the VAE's own
        # weights are already frozen via `requires_grad_(False)` in __init__, which is
        # sufficient to keep them from updating. Wrapping this forward call in
        # `torch.no_grad()` additionally severs the gradient path from T's loss back to
        # `z`  (z_T_hat, the LoRA-adapted UNet's output) -- T's own reconstruction
        # signal could never reach the trainable LoRA parameters at all. Confirmed via
        # gate1b: with every other loss weight zeroed, T's loss was bit-for-bit frozen
        # for 100+ steps (zero gradient reaching ANY trainable parameter); in the full
        # multi-head loss, T only drifted as a side effect of h/B/shadow/mark/conf
        # gradients flowing through `z_T_hat` via the AuxHead (a path that never went
        # through this no-grad decode), never from its own supervision.
        img = self.vae.decode((z / self.vae_scale).to(self.vae.dtype)).sample
        return (img.float() * 0.5 + 0.5)  # -> [0,1]

    def forward(self, photo01):
        """photo01: (B,3,H,W) in [0,1] scene-referred-ish. Returns dict of full-res maps."""
        B, _, H, W = photo01.shape
        z_rgb = self.encode(photo01).float()
        extra = max(self.unet_in - z_rgb.shape[1], 0)
        z_init = torch.zeros(B, extra, z_rgb.shape[2], z_rgb.shape[3],
                             device=z_rgb.device, dtype=z_rgb.dtype)
        zc = torch.cat([z_rgb, z_init], dim=1)[:, :self.unet_in].to(self.unet.dtype)
        t = torch.full((B,), self.fixed_timestep, device=photo01.device, dtype=torch.long)
        ehs = self.empty_embed.to(self.unet.dtype).expand(B, -1, -1)
        # read the primary intrinsic latent from the first block of the UNet output
        z_T_hat = self.unet(zc, timestep=t, encoder_hidden_states=ehs).sample[:, :self.latent_ch].float()

        T = self.decode(z_T_hat).clamp(0, 1)                      # (B,3,H,W) via frozen VAE
        if T.shape[-2:] != (H, W):
            T = F.interpolate(T, size=(H, W), mode="bilinear", align_corners=False)

        feat = torch.cat([z_rgb, z_T_hat], dim=1)
        aux = self.aux(feat, (H, W))
        i = 0
        out = {"T": T}
        for name in AUX_CHANNELS:
            d = AUX_DIMS[name]
            ch = aux[:, i:i + d]
            i += d
            if name in ("shadow", "mark", "conf"):
                out[name + "_logit"] = ch
                out[name] = torch.sigmoid(ch)
            elif name == "h":
                out[name] = torch.sigmoid(ch)     # h in [0,1]
            else:                                 # B: non-negative linear
                out[name] = F.softplus(ch)
        return out

    def trainable_parameters(self):
        return [p for p in self.parameters() if p.requires_grad]

    def save_adapter(self, path):
        """Persist only the trained parts (LoRA + AuxHead + meta) — the artifact the
        Modal run pushes to HF Hub; the frozen backbone is re-fetched by id."""
        sd = {k: v for k, v in self.state_dict().items()
              if ("lora" in k) or k.startswith("aux.")}
        torch.save({"trained_state": sd, "meta": self.meta,
                    "backbone": self.backbone_name, "lora_ok": self.lora_ok}, path)

    def load_adapter(self, path, map_location="cpu"):
        ckpt = torch.load(path, map_location=map_location)
        missing, unexpected = self.load_state_dict(ckpt["trained_state"], strict=False)
        # only the trained subset is in the file; the rest are the frozen backbone
        return ckpt.get("meta", {})
