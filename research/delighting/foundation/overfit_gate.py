#!/usr/bin/env python3
"""Iteration 040 — the overfit-one-image / overfit-few-image GATE.

The maintainer's explicit ask: "in multiple projects I've found my loop couldn't even
do that" — before spending any real compute on a pilot LoRA, prove the train.py loop
(dataset.py loading + backbone.py model + train.py's compute_losses) can drive
reconstruction loss to ~0 on a FIXED, memorized set of 1 (gate1) or 5-10 (gate2)
samples. Failure to overfit here is a real, reportable outcome — it means something in
data plumbing / loss / conditioning / decoder range is broken, and no amount of extra
steps on more data will fix it.

Design choices (see report 040):
  * The batch is fixed ONCE (one crop per identity, sampled at step 0) and REUSED every
    step — the strictest version of "can the model memorize this exact tensor," not
    "can it memorize the distribution of crops from this image." Re-cropping every step
    would make failure ambiguous (bad luck on crops vs. a broken loop).
  * Uses the REAL train.py.compute_losses and backbone.py.FoundationDelighter — this is
    not a toy stand-in loop, it is the literal code path the pilot/cloud run will use.
  * A pre-flight VAE-floor diagnostic (encode+decode gt_T through ONLY the frozen VAE,
    no UNet) is run first: T is emitted via VAE decode, so if the frozen VAE itself
    cannot reconstruct this class of image, no LoRA training can close that gap. This
    isolates "decoder range" from "the LoRA/UNet didn't learn."

Usage:
  overfit_gate.py --tag gate1 --samples render_pilot_v1/cathedral-green__seed6001__light9015 \
      --steps 600 --snapshot-every 50 --backbone marigold-iid
  overfit_gate.py --tag gate2 --samples render_037_review/*__seed42__light0409 \
      --steps 600 --snapshot-every 100 --backbone marigold-iid
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time

import numpy as np

# Must be set before `import torch` (transitively pulled in by the `backbone` import
# below) — the MPS allocator reads this once at first use. Caps the driver allocation
# so this job leaves headroom for the concurrent Blender render on the 16GB box (team
# guidance: try 0.5 => ~8GB ceiling; bump to 0.6 if that raises allocation errors).
# A pre-set value from the launching shell always wins (setdefault).
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.6")
# torch's MPS allocator defaults the low watermark to 1.4 (effectively "disabled") when
# unset, which conflicts with a HIGH ratio below that (RuntimeError: invalid low
# watermark ratio 1.4) -- must set both together.
os.environ.setdefault("PYTORCH_MPS_LOW_WATERMARK_RATIO", "0.5")
# 0.5 hit its ceiling (5.92GB) once the decode() gradient-flow fix (report 040) made
# backward pass through the frozen VAE decoder too, needing ~5.81GB -- bumped to 0.6
# per team guidance's fallback.
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, DELIGHT)

import cv2  # noqa: E402
import torch  # noqa: E402

from dataset import GlassDelightDataset, parse_seed, seed_is_test  # noqa: E402
from backbone import FoundationDelighter  # noqa: E402
from train import compute_losses  # noqa: E402
from extract import lin_to_srgb  # noqa: E402

try:
    import psutil
except ImportError:
    psutil = None


# ------------------------------------------------------------------ RAM/disk guards
#
# History: first cut used macOS "free %" (not a real signal — cached/inactive/purgeable
# pages count as "used" by design, so free% near zero is normal). Second cut used
# kern.memorystatus_vm_pressure_level with a 3-strike debounce on "warn" — still wrong:
# on a 16GB box running Blender + a 951M-param model concurrently, SUSTAINED warn is the
# expected operating point (macOS compressing memory / dropping caches), not danger, and
# it kept false-tripping. FINAL policy: warn is LOGGED, never trips. Only trip on
# critical (level 4, immediate), swap GROWING (not swap being high — that's normal here
# too) > ~2GB over a rolling 15-minute window, this process's own footprint (RSS or MPS
# driver allocation) > 9GB, or disk < 10GB. Load average is logged every check so the
# report can show whether the box got sluggish, even though it isn't a trip criterion.
_swap_history = []  # [(timestamp, used_mb), ...] rolling window, module-level


def vm_pressure_level():
    """1=normal, 2=warn, 4=critical (kern.memorystatus_vm_pressure_level). Unreadable
    -> 1 (normal) so a sysctl hiccup never false-trips the guard."""
    try:
        out = subprocess.run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return int(out)
    except Exception:
        return 1


def swap_used_mb():
    try:
        out = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True,
                             timeout=5).stdout
        m = re.search(r"used\s*=\s*([\d.]+)M", out)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def swap_growth_mb(window_sec=900):
    """Growth in swap-used over the trailing `window_sec` (default 15min per the final
    guard policy), or None until the window has enough history. A high-but-flat swap
    reading never trips this — only growth does."""
    now = time.time()
    used = swap_used_mb()
    if used is None:
        return None
    _swap_history.append((now, used))
    while len(_swap_history) > 1 and now - _swap_history[0][0] > window_sec:
        _swap_history.pop(0)
    if len(_swap_history) < 2 or (now - _swap_history[0][0]) < 30:
        return None  # not enough history yet to judge a trend
    return used - _swap_history[0][1]


def load_avg():
    try:
        return tuple(round(x, 2) for x in os.getloadavg())
    except Exception:
        return None


def proc_rss_gb():
    if psutil is None:
        return 0.0
    return psutil.Process(os.getpid()).memory_info().rss / 1e9


def disk_free_gb(path="/"):
    import shutil
    return shutil.disk_usage(path).free / 1e9


def mps_mem_stats():
    """Real GPU-side (Metal/unified-memory) allocation, distinct from process RSS —
    MPS buffers largely live outside the anon-RSS accounting psutil reports, which is
    why a real 866M-param backbone can show <1GB process RSS (see report 040)."""
    if not torch.backends.mps.is_available():
        return {}
    try:
        return {"mps_current_alloc_gb": round(torch.mps.current_allocated_memory() / 1e9, 3),
                "mps_driver_alloc_gb": round(torch.mps.driver_allocated_memory() / 1e9, 3)}
    except Exception:
        return {}


def guard_or_exit(log_path, tag):
    """Trip ONLY on: pressure level 4 (critical, immediate), swap growing > 2GB over a
    rolling 15-minute window, this process's own footprint (RSS or MPS driver
    allocation) > 9GB, or disk < 10GB. Sustained "warn" (level 2) is logged, never trips
    — it's the expected steady state when Blender and a 951M-param model share 16GB."""
    level = vm_pressure_level()
    rss = proc_rss_gb()
    mps_driver_gb = mps_mem_stats().get("mps_driver_alloc_gb", 0.0)
    free_disk = disk_free_gb()
    growth = swap_growth_mb()
    la = load_avg()

    def trip(reason):
        msg = f"[{tag}] RAM/DISK GUARD TRIPPED: {reason} — stopping cleanly."
        print(msg)
        with open(log_path, "a") as f:
            f.write(msg + "\n")
        return False

    if level >= 4:
        return trip(f"memorystatus_vm_pressure_level={level} CRITICAL rss={rss:.2f}GB")
    if growth is not None and growth > 2048:
        return trip(f"swap growing fast (+{growth:.0f}MB over ~15min)")
    if rss > 9.0:
        return trip(f"process rss={rss:.2f}GB > 9GB")
    if mps_driver_gb > 9.0:
        return trip(f"MPS driver allocation={mps_driver_gb:.2f}GB > 9GB")
    if free_disk < 10.0:
        return trip(f"disk free={free_disk:.1f}GB < 10GB")

    if level == 2:
        with open(log_path, "a") as f:
            f.write(f"[{tag}] guard: pressure=warn (expected/normal, not tripping) "
                   f"rss={rss:.2f}GB mps_driver={mps_driver_gb:.2f}GB load_avg={la} "
                   f"swap_used={swap_used_mb()}MB\n")
    return True


# ------------------------------------------------------------------ fixed-sample dataset
class FixedSampleDataset(GlassDelightDataset):
    """Bypasses dataset.py's glob-based indexing: trains on EXACTLY the given sample
    directories, regardless of what else exists under the render roots. Still runs
    every sample's seed through seed_is_test() and refuses holdout identities (the
    overfit gate must never accidentally memorize a reserved test identity)."""

    def __init__(self, sample_dirs, **kw):
        self._explicit_dirs = [os.path.abspath(d) for d in sample_dirs]
        super().__init__(roots=[], split="all", **kw)

    def _index(self, roots):
        out = []
        for d in self._explicit_dirs:
            mp = os.path.join(d, "meta.json")
            if not os.path.exists(mp):
                raise SystemExit(f"no meta.json under {d} (not a complete sample dir)")
            meta = json.load(open(mp))
            seed = parse_seed(d, meta)
            if seed_is_test(seed):
                raise SystemExit(f"{d}: seed {seed} is a HELD-OUT identity — "
                                 f"refusing to train the overfit gate on it")
            out.append({"dir": d, "seed": seed, "recipe": meta.get("class_label", "?"),
                        "is_test": False})
        return out


def build_fixed_batch(ds, device, crop):
    """One crop per sample, sampled ONCE and reused every step (see module docstring).
    Returns (batch_dict_of_tensors, list_of_meta) — meta keeps recipe/seed/photo(np) for
    the contact sheet."""
    recs = [ds.sample_crop(idx=i) for i in range(len(ds))]
    bad = [i for i, r in enumerate(recs) if r is None]
    if bad:
        raise SystemExit(f"sample_crop returned None for indices {bad} — "
                         f"a required channel (photo/T/h) is missing on disk")

    def stack(key):
        a = np.stack([r[key] for r in recs])
        return torch.from_numpy(a).permute(0, 3, 1, 2).float().to(device)

    batch = {k: stack(k) for k in ("photo", "T", "h", "B", "shadow", "mark", "valid")}
    batch["has_B"] = torch.tensor([1.0 if r["has_B"] else 0.0 for r in recs], device=device)
    meta = [{"recipe": r["recipe"], "seed": r["seed"], "variant": r["variant"],
            "dir": ds.samples[i]["dir"]} for i, r in enumerate(recs)]
    return batch, meta


# ------------------------------------------------------------------ VAE-floor diagnostic
def vae_floor(model, batch, device):
    """Encode+decode gt_T through ONLY the frozen VAE (no UNet). If this MAE is already
    large, the bottleneck is the frozen backbone's representational range for this image
    class, not the LoRA fit — a distinct failure mode from 'the loop is broken'."""
    with torch.no_grad():
        z = model.encode(batch["T"].clamp(0, 1))
        recon = model.decode(z).clamp(0, 1)
        mae = (recon - batch["T"]).abs().mean().item()
    return {"vae_roundtrip_T_mae": mae, "recon_min": float(recon.min()),
            "recon_max": float(recon.max()), "gt_min": float(batch["T"].min()),
            "gt_max": float(batch["T"].max())}


# ------------------------------------------------------------------ contact sheet
def _panel(img_chw, size=256):
    """CHW float tensor (any range) -> HxWx3 uint8 sRGB panel."""
    a = img_chw.detach().float().cpu().numpy()
    if a.shape[0] == 1:
        a = np.repeat(a, 3, 0)
    a = np.transpose(a, (1, 2, 0))
    a = np.clip(a, 0, 1)
    a = lin_to_srgb(a)
    a = (np.clip(a, 0, 1) * 255).astype(np.uint8)
    if a.shape[0] != size or a.shape[1] != size:
        a = cv2.resize(a, (size, size), interpolation=cv2.INTER_AREA)
    return a


def build_contact_row(photo, pred_T, gt_T, pred_h, gt_h, step, loss, size=256, label_w=140):
    panels = [_panel(photo, size), _panel(pred_T, size), _panel(gt_T, size),
              _panel(pred_h, size), _panel(gt_h, size)]
    row = np.concatenate(panels, axis=1)
    label = np.full((size, label_w, 3), 30, np.uint8)
    cv2.putText(label, f"step {step}", (8, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
               (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(label, f"L={loss:.4f}", (8, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
               (200, 255, 200), 1, cv2.LINE_AA)
    return np.concatenate([label, row], axis=1)


HEADER_LABELS = ["input", "pred_T", "gt_T", "pred_h", "gt_h"]


def build_header(size=256, label_w=140):
    h = np.full((36, label_w + size * len(HEADER_LABELS), 3), 20, np.uint8)
    for i, name in enumerate(HEADER_LABELS):
        x = label_w + i * size + 8
        cv2.putText(h, name, (x, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1,
                   cv2.LINE_AA)
    return h


# ------------------------------------------------------------------ plot
def plot_loss_curve(log, out_path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    steps = [r["step"] for r in log]
    fig, ax = plt.subplots(figsize=(7, 4), dpi=130)
    for key, color in (("total", "#111827"), ("T", "#2563eb"), ("h", "#dc2626"),
                       ("B", "#059669")):
        ax.plot(steps, [r[key] for r in log], label=key, color=color, linewidth=1.6)
    ax.set_xlabel("step")
    ax.set_ylabel("loss")
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_yscale("log")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


# ------------------------------------------------------------------ main loop
def run_gate(sample_dirs, tag, steps, snapshot_every, crop, lr, lora_rank, backbone,
            out_dir, device, weights=None, max_minutes=None, log_path="/tmp/night_train.log",
            resume=True):
    """Guard trips are expected overnight on this shared machine (Blender's bursty
    CPU/GPU use can briefly push real kernel pressure to warn). Rather than fight the
    debounce further, state is persisted INCREMENTALLY so a trip just pauses progress:
    per-step log rows append to `{tag}_log.jsonl`, contact-sheet rows save as individual
    PNGs under `{tag}_snapshots/`, and the adapter checkpoints every snapshot. With
    `resume=True` (default), a relaunch of the SAME tag picks up where it left off — the
    fixed batch is deterministic (dataset seed=0) so the memorization target is identical
    across restarts. Final artifacts (contact sheet / loss curve / result.json) are
    always assembled from EVERYTHING on disk, not just this invocation's steps, so the
    output is correct whether the gate ran in one shot or was interrupted N times."""
    os.makedirs(out_dir, exist_ok=True)
    snap_dir = os.path.join(out_dir, f"{tag}_snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    jsonl_path = os.path.join(out_dir, f"{tag}_log.jsonl")
    adapter_path = os.path.join(out_dir, f"{tag}_adapter.pt")
    device = device or ("mps" if torch.backends.mps.is_available() else
                        "cuda" if torch.cuda.is_available() else "cpu")
    weights = weights or {"T": 6.0, "h": 2.0, "B": 2.0, "shadow": 1.0, "mark": 1.0, "conf": 1.0}
    t0 = time.time()

    def logline(s):
        print(s)
        with open(log_path, "a") as f:
            f.write(s + "\n")

    logline(f"[{tag}] === start {time.strftime('%Y-%m-%d %H:%M:%S')} "
           f"backbone={backbone} device={device} n_samples={len(sample_dirs)} "
           f"steps={steps} crop={crop} weights={weights} ===")

    ds = FixedSampleDataset(sample_dirs, crop=crop, work_size=768, augment=False,
                            input_variant="without")
    logline(f"[{tag}] fixed samples: " +
           ", ".join(f"{s['recipe']}/seed{s['seed']}" for s in ds.samples))

    model = FoundationDelighter(backbone=backbone, dtype=torch.float32, freeze_backbone=True,
                                lora_rank=lora_rank, cache_only=True).to(device)
    if hasattr(model.unet, "enable_gradient_checkpointing"):
        model.unet.enable_gradient_checkpointing()
        logline(f"[{tag}] gradient checkpointing enabled on the UNet "
               f"(trades ~30% speed for activation-memory headroom)")
    if hasattr(model.vae, "enable_gradient_checkpointing"):
        model.vae.enable_gradient_checkpointing()
        logline(f"[{tag}] gradient checkpointing enabled on the VAE too -- decode()'s "
               f"gradient-flow fix means backward now runs through it as well")
    tp = model.trainable_parameters()
    n_tr = sum(p.numel() for p in tp)
    n_total = sum(p.numel() for p in model.parameters())
    logline(f"[{tag}] trainable params: {n_tr/1e3:.1f}k  lora_ok={model.lora_ok}  "
           f"meta={model.meta}  unet_in/out={model.unet_in}/{model.unet_out}")
    logline(f"[{tag}] REAL-BACKBONE CHECK: total model params={n_total/1e6:.1f}M "
           f"(866M-UNet + 83.7M-VAE expected for marigold-iid) "
           f"proc_rss={proc_rss_gb():.2f}GB {mps_mem_stats()} — process RSS is NOT "
           f"GPU memory on MPS (unified-memory buffers live in the Metal driver's own "
           f"allocation, not anon RSS), so a small psutil RSS does not imply a small "
           f"model; total param count is the real check. "
           f"PYTORCH_MPS_HIGH_WATERMARK_RATIO={os.environ.get('PYTORCH_MPS_HIGH_WATERMARK_RATIO')}")

    batch, meta = build_fixed_batch(ds, device, crop)
    logline(f"[{tag}] fixed batch: photo[{batch['photo'].min():.3f},{batch['photo'].max():.3f}] "
           f"T[{batch['T'].min():.3f},{batch['T'].max():.3f}] "
           f"h[{batch['h'].min():.3f},{batch['h'].max():.3f}]")

    diag = vae_floor(model, batch, device)
    logline(f"[{tag}] VAE-floor (frozen VAE encode->decode of gt_T, no UNet): "
           f"MAE={diag['vae_roundtrip_T_mae']:.4f} "
           f"(recon range [{diag['recon_min']:.3f},{diag['recon_max']:.3f}])")
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()  # clear pre-training-loop scratch (VAE-floor pass etc.)

    opt = torch.optim.AdamW(tp, lr=lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)

    start_step = 0
    if resume and os.path.exists(adapter_path) and os.path.exists(jsonl_path):
        try:
            model.load_adapter(adapter_path, map_location=device)
            last = None
            with open(jsonl_path) as f:
                for line in f:
                    if line.strip():
                        last = line
            if last:
                start_step = json.loads(last)["step"] + 1
            for _ in range(start_step):  # keep the cosine schedule roughly in phase
                sched.step()
            logline(f"[{tag}] RESUMED from {adapter_path} at step {start_step} "
                   f"(a prior run was interrupted; optimizer moment estimates restart "
                   f"fresh, model weights do not)")
        except Exception as e:
            logline(f"[{tag}] resume load failed ({e}); starting fresh from step 0")
            start_step = 0

    header = build_header(size=256)
    model.train()
    stopped_reason = "completed"
    for step in range(start_step, steps):
        if step % 20 == 0:
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
            if not guard_or_exit(log_path, tag):
                stopped_reason = "ram_or_disk_guard"
                break
        if max_minutes and (time.time() - t0) / 60.0 > max_minutes:
            logline(f"[{tag}] time budget ({max_minutes}min) hit at step {step}")
            stopped_reason = "time_budget"
            break

        out = model(batch["photo"].clamp(0, None))
        loss, parts = compute_losses(out, batch, weights)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(tp, 2.0)
        opt.step()
        sched.step()

        if step % 10 == 0 or step == steps - 1:
            parts["step"] = step
            parts["sec"] = round(time.time() - t0, 1)
            parts["rss_gb"] = round(proc_rss_gb(), 2)
            with open(jsonl_path, "a") as f:
                f.write(json.dumps(parts) + "\n")
            logline(f"  [{tag}] step {step:4d}  total={parts['total']:.4f}  "
                   f"T={parts['T']:.4f} h={parts['h']:.4f} B={parts['B']:.4f}  "
                   f"{parts['sec']:.0f}s  rss={parts['rss_gb']}GB")
        if step % 100 == 0:
            logline(f"  [{tag}] guard telemetry: pressure_level={vm_pressure_level()} "
                   f"free_disk={disk_free_gb():.1f}GB swap_used={swap_used_mb()}MB "
                   f"load_avg={load_avg()} {mps_mem_stats()}")

        if step % snapshot_every == 0 or step == steps - 1:
            with torch.no_grad():
                row = build_contact_row(batch["photo"][0], out["T"][0], batch["T"][0],
                                        out["h"][0], batch["h"][0], step,
                                        parts["total"] if "total" in parts else float(loss))
            cv2.imwrite(os.path.join(snap_dir, f"step_{step:05d}.png"), row[..., ::-1])
            model.save_adapter(adapter_path)  # single rolling checkpoint (tens of MB)

    total_sec = time.time() - t0
    steps_this_run = max(0, step + 1 - start_step) if steps > start_step else 0
    logline(f"[{tag}] === done ({stopped_reason}) {total_sec:.0f}s this invocation, "
           f"{steps_this_run} steps this run ===")

    # assemble final artifacts from EVERYTHING on disk (survives any number of restarts)
    log = []
    if os.path.exists(jsonl_path):
        with open(jsonl_path) as f:
            log = [json.loads(l) for l in f if l.strip()]
    snap_files = sorted(glob.glob(os.path.join(snap_dir, "step_*.png")))
    rows = [cv2.imread(p)[..., ::-1] for p in snap_files]
    rows = [r for r in rows if r is not None]

    sheet_path = os.path.join(out_dir, f"{tag}_contact_sheet.png")
    if rows:
        sheet = np.concatenate([header] + rows, axis=0)
        cv2.imwrite(sheet_path, sheet[..., ::-1])
    curve_path = os.path.join(out_dir, f"{tag}_loss_curve.png")
    if log:
        plot_loss_curve(log, curve_path,
                        f"{tag}: overfit {len(sample_dirs)}-sample gate "
                        f"({backbone}, crop={crop})")

    final = log[-1] if log else {}
    result = {
        "tag": tag, "backbone": backbone, "n_samples": len(sample_dirs),
        "samples": [{"dir": m["dir"], "recipe": m["recipe"], "seed": m["seed"]} for m in meta],
        "steps_run": len(log) and log[-1]["step"] + 1 or 0,
        "stopped_reason": stopped_reason, "total_sec_this_invocation": round(total_sec, 1),
        "vae_floor": diag, "final_losses": final, "log": log,
        "trainable_params": int(n_tr), "lora_ok": model.lora_ok,
        "contact_sheet": sheet_path, "loss_curve": curve_path,
    }
    json_path = os.path.join(out_dir, f"{tag}_result.json")
    json.dump(result, open(json_path, "w"), indent=2)
    logline(f"[{tag}] wrote {sheet_path}, {curve_path}, {json_path} "
           f"(cumulative: {len(log)} logged steps, {len(rows)} snapshots)")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samples", nargs="+", required=True,
                    help="explicit sample directories (globs expanded)")
    ap.add_argument("--tag", default="gate1")
    ap.add_argument("--steps", type=int, default=600)
    ap.add_argument("--snapshot-every", type=int, default=50)
    ap.add_argument("--crop", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--lora-rank", type=int, default=8)
    ap.add_argument("--backbone", default="marigold-iid",
                    choices=["tiny", "marigold-iid", "marigold-depth", "sd2"])
    ap.add_argument("--out", default=os.path.join(DELIGHT, "results", "040"))
    ap.add_argument("--device", default=None)
    ap.add_argument("--max-minutes", type=float, default=None)
    ap.add_argument("--log", default="/tmp/night_train.log")
    ap.add_argument("--no-resume", action="store_true",
                    help="ignore any existing {tag}_adapter.pt/_log.jsonl and start over")
    ap.add_argument("--w-t", type=float, default=6.0, help="loss weight: T")
    ap.add_argument("--w-h", type=float, default=2.0, help="loss weight: h")
    ap.add_argument("--w-b", type=float, default=2.0, help="loss weight: B")
    ap.add_argument("--w-shadow", type=float, default=1.0, help="loss weight: shadow")
    ap.add_argument("--w-mark", type=float, default=1.0, help="loss weight: mark")
    ap.add_argument("--w-conf", type=float, default=1.0, help="loss weight: conf")
    args = ap.parse_args()

    sample_dirs = []
    for pat in args.samples:
        matches = sorted(glob.glob(pat))
        sample_dirs.extend(matches if matches else [pat])
    sample_dirs = sorted(set(os.path.abspath(d) for d in sample_dirs))

    weights = {"T": args.w_t, "h": args.w_h, "B": args.w_b, "shadow": args.w_shadow,
              "mark": args.w_mark, "conf": args.w_conf}
    run_gate(sample_dirs, args.tag, args.steps, args.snapshot_every, args.crop, args.lr,
             args.lora_rank, args.backbone, args.out, args.device, weights=weights,
             max_minutes=args.max_minutes, log_path=args.log, resume=not args.no_resume)


if __name__ == "__main__":
    main()
