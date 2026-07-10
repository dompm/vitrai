#!/usr/bin/env python3
"""Two-frame transparent-sheet inverse experiment.

Report 021 found:
  - known background B + displacement D recovers clean T well;
  - learned B from one image reconstructs but leaves T wrong.

This script asks the next identifiability question:

  If the same sheet T,D is observed over two different backgrounds, can shared
  T,D plus per-frame B_i recover the material better than the single-frame
  learned-B optimizer?

This is a capture/information experiment, not a product proposal.
"""
import argparse
import json
import os
import time

import cv2
import numpy as np
import torch
from PIL import Image, ImageDraw

import differentiable_sheet_inverse as inv

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "results", "differentiable_sheet_twoframe")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def make_second_background(n, rng):
    bg = inv.make_background(n, rng)
    # Different background, not just a shift: harsher cue for identifiability.
    bg = np.roll(bg, shift=int(n * 0.21), axis=1)
    tint = np.array([0.82, 1.06, 0.88], np.float32)
    bg = np.clip(bg * tint[None, None, :], 0, 1)
    # Add a diagonal-ish dark structure that cannot be explained by the same T.
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    line = np.abs((yy - 0.25 * n) - 0.42 * (xx - 0.15 * n)) < n * 0.018
    bg[line] *= 0.20
    return bg.astype(np.float32)


def render_np(T, B, D, ambient, leak, noise_rng=None):
    warped = inv.warp_np(B, D)
    obs = np.clip(T * (ambient + leak * warped), 0, 1).astype(np.float32)
    if noise_rng is not None:
        obs = np.clip(obs + noise_rng.normal(0, 0.0015, obs.shape).astype(np.float32), 0, 1)
    return obs, warped


def optimize_twoframe(obs_list, args, device):
    n = obs_list[0].shape[0]
    obs_t = [inv.np_to_torch_img(obs, device) for obs in obs_list]

    mean_obs = np.mean(np.stack(obs_list, axis=0), axis=0)
    neutral_B = np.ones_like(mean_obs, dtype=np.float32) * 0.82
    t0 = inv.init_low_T(mean_obs, neutral_B, args.ambient, args.leak, args.t_low_res)
    t_param = torch.nn.Parameter(torch.from_numpy(t0).permute(2, 0, 1)[None].to(device))

    b_params = []
    for obs in obs_list:
        b0 = inv.init_unknown_B(obs, args.b_low_res)
        b_params.append(torch.nn.Parameter(torch.from_numpy(b0).permute(2, 0, 1)[None].to(device)))

    disp_param = torch.nn.Parameter(torch.zeros((1, 2, args.disp_low_res, args.disp_low_res), device=device))
    opt = torch.optim.AdamW([
        {"params": [t_param], "lr": args.lr_t},
        {"params": b_params, "lr": args.lr_b},
        {"params": [disp_param], "lr": args.lr_d},
    ], weight_decay=0.0)

    log = []
    for step in range(args.steps_twoframe):
        T = torch.sigmoid(inv.upsample_param(t_param, n))
        disp = args.max_disp * torch.tanh(inv.upsample_param(disp_param, n, mode="bilinear"))
        Bs = [torch.sigmoid(inv.upsample_param(p, n)) for p in b_params]
        recon_losses = [torch.abs(inv.render(T, B, disp, args.ambient, args.leak) - obs).mean() for B, obs in zip(Bs, obs_t)]
        loss_recon = sum(recon_losses) / len(recon_losses)
        loss = (
            loss_recon
            + args.t_tv * inv.tv(T)
            + args.b_tv * sum(inv.tv(B) for B in Bs) / len(Bs)
            + args.disp_tv * inv.tv(disp / args.max_disp)
            + args.disp_lap * inv.lap(disp / args.max_disp).abs().mean()
            + args.disp_mag * (disp / args.max_disp).pow(2).mean()
        )
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_([t_param, disp_param] + b_params, 5.0)
        opt.step()
        if step % args.log_every == 0 or step == args.steps_twoframe - 1:
            log.append({
                "step": step,
                "loss": float(loss.item()),
                "recon": float(loss_recon.item()),
                "disp_abs": float(disp.abs().mean().item()),
            })

    T_np = inv.torch_to_np_img(torch.sigmoid(inv.upsample_param(t_param, n)))
    disp_np = disp.detach().cpu().numpy()[0].transpose(1, 2, 0).astype(np.float32)
    B_np = [inv.torch_to_np_img(torch.sigmoid(inv.upsample_param(p, n))) for p in b_params]
    return {"T": T_np, "disp": disp_np, "B": B_np, "log": log}


def twoframe_metrics(name, rec, gt, args):
    frame_metrics = []
    recon_maes = []
    B_maes = []
    for i, (B_rec, B_gt, obs) in enumerate(zip(rec["B"], gt["B"], gt["obs"])):
        warped = inv.warp_np(B_rec, rec["disp"])
        pred = np.clip(rec["T"] * (args.ambient + args.leak * warped), 0, 1)
        recon_maes.append(float(np.mean(np.abs(pred - obs))))
        B_maes.append(float(np.mean(np.abs(B_rec - B_gt))))
        frame_gt = {
            "T": gt["T"],
            "bg": B_gt,
            "disp": gt["D"],
            "warped_bg": gt["warped"][i],
            "obs": obs,
        }
        frame_metrics.append(inv.metrics_for(f"{name}/frame{i+1}", rec["T"], rec["disp"], B_rec, frame_gt, args))

    lum_T = (rec["T"] * inv.LUM).sum(-1)
    lum_gt = (gt["T"] * inv.LUM).sum(-1)
    return {
        "name": name,
        "renderer_recon_mae": float(np.mean(recon_maes)),
        "T_mae": float(np.mean(np.abs(rec["T"] - gt["T"]))),
        "T_lum_mae": float(np.mean(np.abs(lum_T - lum_gt))),
        "B_mae": float(np.mean(B_maes)),
        "preview_lum_cv": inv.patch_lum_cv(rec["T"]),
        "T_highfreq_corr_with_bg_frame1": frame_metrics[0]["T_highfreq_corr_with_bg"],
        "T_highfreq_corr_with_bg_frame2": frame_metrics[1]["T_highfreq_corr_with_bg"],
        "disp_epe_px": float(np.linalg.norm(rec["disp"] - gt["D"], axis=-1).mean()),
        "disp_corr_x": inv.corr(rec["disp"][..., 0], gt["D"][..., 0]),
        "disp_corr_y": inv.corr(rec["disp"][..., 1], gt["D"][..., 1]),
    }


def tile(rgb, label, w=170):
    srgb = inv.lin_to_srgb(np.clip(rgb, 0, 1))
    img = (srgb * 255).astype(np.uint8)
    h0, w0 = img.shape[:2]
    img = cv2.resize(img, (w, max(1, int(round(h0 * w / max(w0, 1))))), interpolation=cv2.INTER_AREA)
    hdr = Image.new("RGB", (img.shape[1], 24), (0, 0, 0))
    d = ImageDraw.Draw(hdr)
    d.text((5, 6), label[:30], fill=(255, 230, 90))
    return np.concatenate([np.asarray(hdr), img], axis=0)


def heat_tile(a, label, w=170):
    a = np.asarray(a, np.float32)
    lo, hi = np.percentile(a, [2, 98])
    norm = np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)
    img = cv2.applyColorMap((norm * 255).astype(np.uint8), cv2.COLORMAP_TURBO)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h0, w0 = img.shape[:2]
    img = cv2.resize(img, (w, max(1, int(round(h0 * w / max(w0, 1))))), interpolation=cv2.INTER_AREA)
    hdr = Image.new("RGB", (img.shape[1], 24), (0, 0, 0))
    d = ImageDraw.Draw(hdr)
    d.text((5, 6), label[:30], fill=(255, 230, 90))
    return np.concatenate([np.asarray(hdr), img], axis=0)


def save_contact(out_dir, gt, single, two):
    rows = []
    first = [
        tile(gt["T"], "GT clean T"),
        tile(gt["B"][0], "GT B1"),
        tile(gt["obs"][0], "obs frame1"),
        tile(gt["B"][1], "GT B2"),
        tile(gt["obs"][1], "obs frame2"),
        heat_tile(np.linalg.norm(gt["D"], axis=-1), "GT disp"),
    ]
    h = max(t.shape[0] for t in first)
    rows.append(np.concatenate([np.pad(t, ((0, h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in first], 1))

    for rec, label in ((single, "single learnedB"), (two, "two-frame learnedB")):
        err = np.clip(6.0 * np.abs(rec["T"] - gt["T"]), 0, 1)
        row = [
            tile(rec["T"], f"{label} T"),
            tile(rec["B"][0], f"{label} B1"),
            tile(rec["B"][1], f"{label} B2"),
            tile(err, f"{label} |Terr|x6"),
            heat_tile(np.linalg.norm(rec["disp"], axis=-1), f"{label} disp"),
        ]
        h = max(t.shape[0] for t in row)
        rows.append(np.concatenate([np.pad(t, ((0, h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in row], 1))

    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    Image.fromarray(np.concatenate(rows, 0)).save(os.path.join(out_dir, "contact.jpg"), quality=92)


def run_case(args, out_dir, case_name="single"):
    ensure_dir(out_dir)
    rng = np.random.default_rng(args.seed)
    rng2 = np.random.default_rng(args.seed + 1009)
    device = "mps" if torch.backends.mps.is_available() and not args.cpu else "cpu"

    T = inv.make_material_T(args.size, rng)
    D, height = inv.make_displacement(args.size, rng, amp_px=args.max_disp * 0.92)
    B1 = inv.make_background(args.size, rng)
    B2 = make_second_background(args.size, rng2)
    obs1, warped1 = render_np(T, B1, D, args.ambient, args.leak, rng)
    obs2, warped2 = render_np(T, B2, D, args.ambient, args.leak, rng2)

    t0 = time.time()
    single1 = inv.optimize_lowT_disp_B(obs1, args, device)
    single2 = inv.optimize_lowT_disp_B(obs2, args, device)
    single = {"T": single1["T"], "disp": single1["disp"], "B": [single1["bg"], single2["bg"]], "log": single1["log"]}
    two = optimize_twoframe([obs1, obs2], args, device)
    elapsed = time.time() - t0

    gt = {
        "T": T,
        "D": D,
        "height": height,
        "B": [B1, B2],
        "obs": [obs1, obs2],
        "warped": [warped1, warped2],
    }
    metrics = [
        twoframe_metrics("single-frame learned B", single, gt, args),
        twoframe_metrics("two-frame shared T,D learned B", two, gt, args),
    ]
    save_contact(out_dir, gt, single, two)
    payload = {
        "case": case_name,
        "claim": "Two observations with shared T,D should reduce single-image T/B ambiguity.",
        "config": vars(args) | {"device": device, "elapsed_s": elapsed},
        "metrics": metrics,
        "logs": {"single_frame1": single1["log"], "single_frame2": single2["log"], "twoframe": two["log"]},
    }
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(payload, f, indent=2)
    write_summary(out_dir, metrics)
    print(f"==== TWO-FRAME INVERSE: {case_name} ====")
    for m in metrics:
        print(
            f"{m['name']:32s} recon={m['renderer_recon_mae']:.4f} T={m['T_mae']:.4f} "
            f"B={m['B_mae']:.4f} cv={m['preview_lum_cv']:.3f} dispEPE={m['disp_epe_px']:.2f}"
        )
    print(f"device={device} elapsed={elapsed:.1f}s")
    return payload


def write_summary(out_dir, metrics):
    lines = [
        "# Two-frame inverse summary",
        "",
        "| method | recon MAE | T MAE | B MAE | preview lum CV | bg corr f1/f2 | disp EPE |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for m in metrics:
        lines.append(
            f"| {m['name']} | {m['renderer_recon_mae']:.4f} | {m['T_mae']:.4f} | {m['B_mae']:.4f} | "
            f"{m['preview_lum_cv']:.3f} | {m['T_highfreq_corr_with_bg_frame1']:.3f}/{m['T_highfreq_corr_with_bg_frame2']:.3f} | {m['disp_epe_px']:.2f} |"
        )
    with open(os.path.join(out_dir, "summary_table.md"), "w") as f:
        f.write("\n".join(lines))


def summarize_sweep(out_dir, cases):
    by_method = {}
    for case in cases:
        for m in case["metrics"]:
            by_method.setdefault(m["name"], []).append(m)

    def mean_std(rows, key):
        vals = np.array([r[key] for r in rows], dtype=np.float64)
        return float(vals.mean()), float(vals.std())

    summary = {}
    lines = [
        "# Two-frame inverse sweep",
        "",
        "| method | T MAE mean | T MAE std | B MAE mean | preview CV mean | disp EPE mean | n |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for method, rows in sorted(by_method.items()):
        t_mu, t_sd = mean_std(rows, "T_mae")
        b_mu, _ = mean_std(rows, "B_mae")
        cv_mu, _ = mean_std(rows, "preview_lum_cv")
        epe_mu, _ = mean_std(rows, "disp_epe_px")
        summary[method] = {
            "T_mae_mean": t_mu,
            "T_mae_std": t_sd,
            "B_mae_mean": b_mu,
            "preview_lum_cv_mean": cv_mu,
            "disp_epe_px_mean": epe_mu,
            "n": len(rows),
        }
        lines.append(f"| {method} | {t_mu:.4f} | {t_sd:.4f} | {b_mu:.4f} | {cv_mu:.3f} | {epe_mu:.2f} | {len(rows)} |")

    with open(os.path.join(out_dir, "sweep_summary.md"), "w") as f:
        f.write("\n".join(lines))
    with open(os.path.join(out_dir, "sweep_metrics.json"), "w") as f:
        json.dump({"cases": cases, "summary": summary}, f, indent=2)
    return summary


def parse_seeds(text):
    return [int(x.strip()) for x in text.split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--size", type=int, default=144)
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--ambient", type=float, default=0.12)
    ap.add_argument("--leak", type=float, default=0.88)
    ap.add_argument("--max-disp", type=float, default=10.0)
    ap.add_argument("--t-low-res", type=int, default=26)
    ap.add_argument("--disp-low-res", type=int, default=54)
    ap.add_argument("--b-low-res", type=int, default=72)
    ap.add_argument("--steps-joint", type=int, default=950)
    ap.add_argument("--steps-twoframe", type=int, default=1100)
    ap.add_argument("--lr-t", type=float, default=0.08)
    ap.add_argument("--lr-d", type=float, default=0.05)
    ap.add_argument("--lr-b", type=float, default=0.035)
    ap.add_argument("--t-tv", type=float, default=0.010)
    ap.add_argument("--b-tv", type=float, default=0.0015)
    ap.add_argument("--disp-tv", type=float, default=0.004)
    ap.add_argument("--disp-lap", type=float, default=0.004)
    ap.add_argument("--disp-mag", type=float, default=0.001)
    ap.add_argument("--log-every", type=int, default=400)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--sweep-seeds", default="31,32,33,34")
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()

    if not args.sweep:
        run_case(args, args.out)
        return

    ensure_dir(args.out)
    cases = []
    for seed in parse_seeds(args.sweep_seeds):
        case_args = argparse.Namespace(**(vars(args) | {"seed": seed}))
        case_name = f"seed{seed}"
        payload = run_case(case_args, os.path.join(args.out, case_name), case_name=case_name)
        cases.append({"case": case_name, "seed": seed, "metrics": payload["metrics"], "config": payload["config"]})
    summary = summarize_sweep(args.out, cases)
    print("==== TWO-FRAME SWEEP SUMMARY ====")
    for method, row in summary.items():
        print(f"{method}: T={row['T_mae_mean']:.4f} B={row['B_mae_mean']:.4f} disp={row['disp_epe_px_mean']:.2f}")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
