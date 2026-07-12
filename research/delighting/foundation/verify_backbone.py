#!/usr/bin/env python3
"""Iteration 038 / deliverable 1 — BACKBONE VERIFICATION for Bet 2.

Report-028's lesson: verify the weights actually exist and load BEFORE building a
training project on top of them. This script tries, in order, to download and load
the Bet-2 foundation backbone candidates (report 027 §Bet 2: a Marigold-class latent-
diffusion dense predictor / RGB<->X-style intrinsic estimator), runs one forward pass
on MPS, and records exact model ids + licenses + param counts + what actually ran.

Candidates (decided from what is ACTUALLY downloadable via the HF Hub + diffusers,
not from the paper list):

  PRIMARY   prs-eth/marigold-iid-appearance-v1-1  (Marigold-IID, the intrinsic-image
            -decomposition / RGB<->X-style variant: albedo + material from one RGB
            image; the closest published thing to "emit our T,h" — Apache-2.0,
            diffusers-native MarigoldIntrinsicsPipeline, SD2-based single UNet).
  FALLBACK  prs-eth/marigold-depth-v1-0  (Marigold depth; same SD2 backbone + VAE,
            proven diffusers pipeline, Apache-2.0 — used if the IID weights are
            unavailable; we only need its VAE+UNet as the transfer backbone).
  BACKBONE-ONLY  stabilityai/stable-diffusion-2-1  (the raw SD2 VAE+UNet Marigold is
            fine-tuned from — the ultimate fallback if both Marigold repos are gated;
            CreativeML-Open-RAIL++-M).

Usage:
  verify_backbone.py --download            # really pull weights + forward (the deliverable)
  verify_backbone.py --candidate depth     # force a specific candidate
  verify_backbone.py --dry                 # no network: just prove classes import + a
                                           #   tiny stand-in constructs + forwards on MPS

Writes results/038_backbone/verification.json.
"""
import argparse
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.dirname(HERE)
OUT = os.path.join(DELIGHT, "results", "038_backbone")

# model id -> license (recorded so the runbook/report cite the exact terms)
CANDIDATES = {
    "iid": ("prs-eth/marigold-iid-appearance-v1-1", "Apache-2.0", "MarigoldIntrinsicsPipeline"),
    "depth": ("prs-eth/marigold-depth-v1-0", "Apache-2.0", "MarigoldDepthPipeline"),
    "sd2": ("stabilityai/stable-diffusion-2-1", "CreativeML-Open-RAIL++-M", "components"),
}


def _device():
    import torch
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _count_params(module):
    return int(sum(p.numel() for p in module.parameters()))


def verify_pipeline(candidate, device, dtype):
    """Download + load a Marigold pipeline; forward one 256x256 image."""
    import torch
    import numpy as np
    from diffusers import MarigoldDepthPipeline, MarigoldIntrinsicsPipeline

    model_id, license_, klass = CANDIDATES[candidate]
    Pipe = MarigoldIntrinsicsPipeline if candidate == "iid" else MarigoldDepthPipeline
    t0 = time.time()
    pipe = Pipe.from_pretrained(model_id, torch_dtype=dtype)
    pipe = pipe.to(device)
    load_s = time.time() - t0

    rec = {
        "ok": True, "model_id": model_id, "license": license_, "pipeline": klass,
        "load_seconds": round(load_s, 1), "device": device, "dtype": str(dtype),
        "vae_params": _count_params(pipe.vae),
        "unet_params": _count_params(pipe.unet),
        "vae_latent_channels": int(pipe.vae.config.latent_channels),
        "unet_in_channels": int(pipe.unet.config.in_channels),
        "unet_cross_attention_dim": int(pipe.unet.config.cross_attention_dim),
    }
    # one real forward through the pipeline (few steps) on a synthetic gradient image
    gx, gy = np.meshgrid(np.linspace(0, 1, 256), np.linspace(0, 1, 256))
    img = (np.stack([gx, gy, np.ones((256, 256)) * 0.5], -1) * 255).astype("uint8")
    from PIL import Image
    t1 = time.time()
    with torch.no_grad():
        out = pipe(Image.fromarray(img), num_inference_steps=2, ensemble_size=1,
                   processing_resolution=256, output_type="np")
    rec["forward_seconds"] = round(time.time() - t1, 1)
    pred = getattr(out, "prediction", None)
    if pred is None:  # intrinsics pipeline returns a list of targets
        pred = getattr(out, "albedo", out)
    try:
        arr = pred[0] if isinstance(pred, (list, tuple)) else pred
        import numpy as _np
        rec["forward_output_shape"] = list(_np.asarray(arr).shape)
    except Exception:
        rec["forward_output_shape"] = "n/a"
    del pipe
    return rec


def verify_dry(device):
    """No-network sanity: prove the diffusers model classes import and a TINY
    randomly-initialised VAE+UNet (same classes the real backbone uses) constructs
    and forwards on MPS. This is what train.py --backbone tiny relies on for the
    local smoke test when a multi-GB download is impractical."""
    import torch
    from diffusers import AutoencoderKL, UNet2DConditionModel

    vae = AutoencoderKL(
        in_channels=3, out_channels=3, latent_channels=4,
        down_block_types=("DownEncoderBlock2D", "DownEncoderBlock2D"),
        up_block_types=("UpDecoderBlock2D", "UpDecoderBlock2D"),
        block_out_channels=(32, 64), layers_per_block=1,
    ).to(device).eval()
    unet = UNet2DConditionModel(
        sample_size=32, in_channels=8, out_channels=4,
        down_block_types=("CrossAttnDownBlock2D", "DownBlock2D"),
        up_block_types=("UpBlock2D", "CrossAttnUpBlock2D"),
        block_out_channels=(32, 64), layers_per_block=1,
        cross_attention_dim=32, norm_num_groups=8,
    ).to(device).eval()
    x = torch.randn(1, 3, 64, 64, device=device)
    with torch.no_grad():
        z = vae.encode(x).latent_dist.mean            # (1,4,16,16)
        zc = torch.cat([z, torch.randn_like(z)], 1)   # (1,8,16,16) rgb+noisy target
        eps = unet(zc, timestep=torch.tensor([1], device=device),
                   encoder_hidden_states=torch.zeros(1, 1, 32, device=device)).sample
        dec = vae.decode(z).sample
    return {
        "ok": True, "mode": "dry (no download)", "device": device,
        "vae_params": _count_params(vae), "unet_params": _count_params(unet),
        "latent_shape": list(z.shape), "unet_out_shape": list(eps.shape),
        "decode_shape": list(dec.shape),
        "note": "diffusers AutoencoderKL + UNet2DConditionModel import, construct, and "
                "forward on MPS; the real backbone uses these same classes.",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true", help="really download + load a real backbone")
    ap.add_argument("--candidate", choices=list(CANDIDATES), default="iid",
                    help="which backbone to try first when --download")
    ap.add_argument("--dry", action="store_true", help="no network; class-import + tiny stand-in forward")
    ap.add_argument("--fp32", action="store_true", help="load in float32 (default float16)")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    import torch
    device = _device()
    dtype = torch.float32 if args.fp32 else torch.float16
    report = {"device": device, "torch": torch.__version__, "attempts": []}

    if args.dry or not args.download:
        try:
            report["dry_run"] = verify_dry(device)
            print("[dry] OK:", json.dumps(report["dry_run"]))
        except Exception as e:
            report["dry_run"] = {"ok": False, "error": str(e), "trace": traceback.format_exc()}
            print("[dry] FAIL:", e)

    if args.download:
        # try the chosen candidate, then fall back down the ladder
        order = [args.candidate] + [c for c in ("iid", "depth", "sd2") if c != args.candidate]
        for cand in order:
            if cand == "sd2":
                # backbone-only path: just load VAE+UNet components, no pipeline
                try:
                    from diffusers import AutoencoderKL, UNet2DConditionModel
                    model_id, license_, _ = CANDIDATES["sd2"]
                    t0 = time.time()
                    vae = AutoencoderKL.from_pretrained(model_id, subfolder="vae", torch_dtype=dtype).to(device)
                    unet = UNet2DConditionModel.from_pretrained(model_id, subfolder="unet", torch_dtype=dtype).to(device)
                    rec = {"ok": True, "model_id": model_id, "license": license_,
                           "pipeline": "components(vae+unet)", "load_seconds": round(time.time() - t0, 1),
                           "vae_params": _count_params(vae), "unet_params": _count_params(unet),
                           "candidate": cand}
                    report["attempts"].append(rec)
                    report["verified"] = rec
                    print("[download] OK sd2 components:", json.dumps(rec))
                    del vae, unet
                    break
                except Exception as e:
                    report["attempts"].append({"ok": False, "candidate": cand, "error": str(e)})
                    print(f"[download] {cand} FAIL:", e)
                    continue
            try:
                rec = verify_pipeline(cand, device, dtype)
                rec["candidate"] = cand
                report["attempts"].append(rec)
                report["verified"] = rec
                print(f"[download] OK {cand}:", json.dumps(rec))
                break
            except Exception as e:
                report["attempts"].append({"ok": False, "candidate": cand, "error": str(e),
                                           "trace": traceback.format_exc().splitlines()[-3:]})
                print(f"[download] {cand} FAIL:", e)
                continue

    with open(os.path.join(OUT, "verification.json"), "w") as f:
        json.dump(report, f, indent=2)
    print("wrote", os.path.join(OUT, "verification.json"))


if __name__ == "__main__":
    main()
