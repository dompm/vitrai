#!/usr/bin/env python3
"""Iteration 040 / stage 3 — pilot LoRA on the growing render_pilot_v1 batch.

`render_pilot_v1/` is filled all night by a concurrent Blender batch job (see the 040
overnight brief) — this script must keep discovering newly-completed sample dirs
without a restart. `generate_synthetic.py` writes `meta.json` LAST, after every photo
and GT render for a sample (confirmed by reading its write order — the
`image_encode_io` stage that dumps `meta.json` is the final line of the per-sample
loop), so `dataset.py`'s existing "a sample dir must have meta.json" indexing rule
already IS the completeness check. No extra polling/heuristic needed: this script just
rebuilds `GlassDelightDataset` from the render root every epoch.

Identity-holdout (seed%5==0 / 800-812) is enforced by dataset.py exactly as in
train.py — nothing here can leak a test identity.

Checkpointing: an adapter (LoRA+AuxHead, tens of MB) is saved every `--ckpt-every-min`
minutes (default 60, "checkpoint hourly" per the brief), rolling a window of the 3 most
recent so disk never grows unbounded. RAM/disk guards match overfit_gate.py.

Usage:
  pilot_train.py --data render_pilot_v1 --out results/040/pilot --max-hours 5 \
      --backbone marigold-iid --epoch-steps 200 --ckpt-every-min 60 --final-eval
"""
import argparse
import glob
import json
import os
import sys
import time

# must be set before `import torch` — see overfit_gate.py's note on this same setting
# (both ratios needed together or the MPS allocator errors: "invalid low watermark ratio")
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.6")
os.environ.setdefault("PYTORCH_MPS_LOW_WATERMARK_RATIO", "0.5")

import torch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, DELIGHT)

from dataset import GlassDelightDataset  # noqa: E402
from backbone import FoundationDelighter  # noqa: E402
from train import collate, compute_losses  # noqa: E402
# reuse the SAME pressure-based guard as overfit_gate.py (fixed after the gate1 false
# trip on macOS "free %", which is not a pressure signal — see overfit_gate.py's note)
from overfit_gate import guard_or_exit, proc_rss_gb, disk_free_gb  # noqa: E402


def prune_checkpoints(out_dir, keep=3):
    ckpts = sorted(glob.glob(os.path.join(out_dir, "pilot_ckpt_*.pt")))
    for p in ckpts[:-keep]:
        try:
            os.remove(p)
        except OSError:
            pass


def train_pilot(data_root, out_dir, backbone, epoch_steps, max_hours, bs, crop, lr,
                lora_rank, ckpt_every_min, device, log_path, final_eval, cache_only=True,
                check_grads=True):
    os.makedirs(out_dir, exist_ok=True)
    device = device or ("mps" if torch.backends.mps.is_available() else
                        "cuda" if torch.cuda.is_available() else "cpu")
    weights = {"T": 6.0, "h": 2.0, "B": 2.0, "shadow": 1.0, "mark": 1.0, "conf": 1.0}

    def logline(s):
        print(s)
        open(log_path, "a").write(s + "\n")

    logline(f"[pilot] === start {time.strftime('%Y-%m-%d %H:%M:%S')} data={data_root} "
           f"backbone={backbone} max_hours={max_hours} epoch_steps={epoch_steps} ===")

    if check_grads:
        from test_grad_flow import preflight_or_raise
        preflight_or_raise(backbone="tiny", device=device)

    model = FoundationDelighter(backbone=backbone, dtype=torch.float32, freeze_backbone=True,
                                lora_rank=lora_rank, cache_only=cache_only).to(device)
    if hasattr(model.unet, "enable_gradient_checkpointing"):
        model.unet.enable_gradient_checkpointing()
        logline("[pilot] gradient checkpointing enabled on the UNet")
    # NOTE: no VAE gradient checkpointing -- T is supervised in latent space, so
    # decode() is no_grad (visualization/eval only) and backward never touches the VAE.
    tp = model.trainable_parameters()
    logline(f"[pilot] trainable params: {sum(p.numel() for p in tp)/1e3:.1f}k  "
           f"lora_ok={model.lora_ok}  "
           f"PYTORCH_MPS_HIGH_WATERMARK_RATIO={os.environ.get('PYTORCH_MPS_HIGH_WATERMARK_RATIO')}")
    opt = torch.optim.AdamW(tp, lr=lr, weight_decay=1e-4)

    t_start = time.time()
    last_ckpt = t_start
    epoch = 0
    global_step = 0
    log = []
    stopped_reason = "max_hours"
    model.train()

    while (time.time() - t_start) / 3600.0 < max_hours:
        try:
            ds = GlassDelightDataset([data_root], split="train", crop=crop, augment=True)
        except SystemExit:
            logline(f"[pilot] no train samples yet under {data_root}; sleeping 60s")
            time.sleep(60)
            continue
        recipes = sorted({s["recipe"] for s in ds.samples})
        seeds = sorted({s["seed"] for s in ds.samples})
        logline(f"[pilot] epoch {epoch}: {len(ds)} train identities | seeds={seeds} | "
               f"recipes={recipes}")

        for _ in range(epoch_steps):
            if (time.time() - t_start) / 3600.0 >= max_hours:
                stopped_reason = "max_hours"
                break
            if global_step % 20 == 0 and not guard_or_exit(log_path, "pilot"):
                stopped_reason = "ram_or_disk_guard"
                break

            batch = collate(ds, bs, device)
            with torch.no_grad():
                batch["z_T_gt"] = model.encode(batch["T"].clamp(0, 1))
            out = model(batch["photo"].clamp(0, None))
            loss, parts = compute_losses(out, batch, weights)
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(tp, 2.0)
            opt.step()
            global_step += 1

            if global_step % 20 == 0:
                parts["step"] = global_step
                parts["epoch"] = epoch
                parts["sec"] = round(time.time() - t_start, 1)
                parts["rss_gb"] = round(proc_rss_gb(), 2)
                log.append(parts)
                logline(f"  [pilot] step {global_step:5d} (ep{epoch})  "
                       f"total={parts['total']:.4f} T={parts['T']:.4f} h={parts['h']:.4f} "
                       f"B={parts['B']:.4f}  {parts['sec']:.0f}s  rss={parts['rss_gb']}GB")

            if (time.time() - last_ckpt) / 60.0 >= ckpt_every_min:
                ck = os.path.join(out_dir, f"pilot_ckpt_{epoch:03d}_{global_step:06d}.pt")
                model.save_adapter(ck)
                prune_checkpoints(out_dir, keep=3)
                last_ckpt = time.time()
                logline(f"[pilot] checkpoint -> {ck}")

        if stopped_reason == "ram_or_disk_guard":
            break
        epoch += 1

    final_ck = os.path.join(out_dir, "pilot_adapter_final.pt")
    model.save_adapter(final_ck)
    prune_checkpoints(out_dir, keep=3)
    json.dump({"stopped_reason": stopped_reason, "epochs": epoch, "global_step": global_step,
              "total_sec": round(time.time() - t_start, 1), "log": log},
             open(os.path.join(out_dir, "pilot_train_log.json"), "w"), indent=2)
    logline(f"[pilot] === done ({stopped_reason}) epochs={epoch} steps={global_step} "
           f"{(time.time()-t_start)/3600.0:.2f}h -> {final_ck} ===")

    if final_eval:
        try:
            ds_test = GlassDelightDataset([data_root], split="test", crop=crop, augment=False)
            n_test = len(ds_test)
        except SystemExit:
            n_test = 0
        if n_test == 0:
            logline("[pilot] final-eval skipped: no held-out identities complete yet under "
                   f"{data_root}")
        else:
            eval_out = os.path.join(out_dir, "eval")
            logline(f"[pilot] final-eval: {n_test} held-out crops-source -> {eval_out}")
            import subprocess
            cmd = [sys.executable, os.path.join(HERE, "eval_foundation.py"),
                  "--ckpt", final_ck, "--backbone", backbone, "--data", data_root,
                  "--out", eval_out, "--cache-only"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            logline(f"[pilot] eval_foundation.py exit={r.returncode}")
            logline(r.stdout[-4000:])
            if r.returncode != 0:
                logline("[pilot] eval STDERR tail:\n" + r.stderr[-2000:])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="render root, rescanned every epoch")
    ap.add_argument("--out", default=os.path.join(DELIGHT, "results", "040", "pilot"))
    ap.add_argument("--backbone", default="marigold-iid",
                    choices=["tiny", "marigold-iid", "marigold-depth", "sd2"])
    ap.add_argument("--epoch-steps", type=int, default=200)
    ap.add_argument("--max-hours", type=float, default=5.0)
    ap.add_argument("--bs", type=int, default=1)
    ap.add_argument("--crop", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--lora-rank", type=int, default=16)
    ap.add_argument("--ckpt-every-min", type=float, default=60.0)
    ap.add_argument("--device", default=None)
    ap.add_argument("--log", default="/tmp/night_train.log")
    ap.add_argument("--final-eval", action="store_true")
    ap.add_argument("--no-check-grads", action="store_true",
                    help="skip the report-040 gradient-flow preflight (default: runs it)")
    args = ap.parse_args()
    train_pilot(args.data, args.out, args.backbone, args.epoch_steps, args.max_hours,
               args.bs, args.crop, args.lr, args.lora_rank, args.ckpt_every_min,
               args.device, args.log, args.final_eval,
               check_grads=not args.no_check_grads)


if __name__ == "__main__":
    main()
