#!/usr/bin/env python3
"""Tiny differentiable transparent-sheet inverse-renderer.

Report 021 starts the real Bet B/C path:

  observed = render(T, background B, displacement D)

The goal is not "clean up RGB". The goal is to test whether an explicit
background/refraction representation can keep background structure out of the
material map. This script generates a known synthetic sheet, then compares:

  1. raw RGB trap: treat the observation as T;
  2. low-T/no-displacement: known B, but no refraction field;
  3. low-T + learned displacement: known B and optimized D.

If (3) does not beat the raw RGB trap on T recovery while reconstructing the
observation, the representation is not pulling its weight.
"""
import argparse
import json
import os
import time

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "results", "differentiable_sheet_inverse")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def srgb_to_lin(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.maximum(x, 0) ** (1 / 2.4) - 0.055)


LUM = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def make_background(n, rng):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    x = xx / (n - 1)
    y = yy / (n - 1)
    sky = np.array([0.50, 0.72, 0.95], np.float32)
    leaves = np.array([0.06, 0.34, 0.10], np.float32)
    brick = np.array([0.72, 0.38, 0.20], np.float32)
    bg = (1 - y[..., None]) * sky + y[..., None] * leaves
    blob = np.exp(-(((x - 0.72) / 0.20) ** 2 + ((y - 0.62) / 0.18) ** 2))
    bg = bg * (1 - 0.65 * blob[..., None]) + brick * (0.65 * blob[..., None])

    # Window/railing structure: high-contrast scene content behind the glass.
    bars = np.ones((n, n), np.float32)
    for pos, width, val in ((0.28, 0.020, 0.18), (0.55, 0.014, 0.28), (0.80, 0.018, 0.20)):
        bars[np.abs(x - pos) < width] *= val
    for pos, width, val in ((0.34, 0.012, 0.30), (0.74, 0.015, 0.22)):
        bars[np.abs(y - pos) < width] *= val
    bg *= bars[..., None]

    noise = rng.normal(0, 1, (18, 18, 3)).astype(np.float32)
    noise = cv2.resize(noise, (n, n), interpolation=cv2.INTER_CUBIC)
    bg = np.clip(bg + 0.045 * noise, 0, 1)
    return srgb_to_lin(bg).astype(np.float32)


def make_material_T(n, rng):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    x = xx / (n - 1)
    y = yy / (n - 1)
    base = np.array([0.030, 0.58, 0.13], np.float32)
    low = 0.92 + 0.08 * np.sin(2 * np.pi * (0.55 * x + 0.2 * y))
    # Real material variation is deliberately low-frequency and chromatic, not
    # the high-contrast window/leaf structure in B.
    wisp = np.exp(-(((x - 0.22) / 0.22) ** 2 + ((y - 0.70) / 0.16) ** 2))
    chroma = base[None, None, :] * low[..., None]
    chroma = chroma + wisp[..., None] * np.array([0.015, 0.08, 0.018], np.float32)
    fine = rng.normal(0, 1, (n, n)).astype(np.float32)
    fine = cv2.GaussianBlur(fine, (0, 0), 1.2)
    fine = fine / max(float(np.std(fine)), 1e-6)
    T = chroma * (1.0 + 0.025 * fine[..., None])
    return np.clip(T, 0.006, 0.92).astype(np.float32)


def make_displacement(n, rng, amp_px=7.5):
    noise = rng.normal(0, 1, (n, n)).astype(np.float32)
    height = cv2.GaussianBlur(noise, (0, 0), 4.5)
    for _ in range(65):
        cx, cy = rng.uniform(0, n, 2)
        sx, sy = rng.uniform(4, 16), rng.uniform(4, 16)
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        height += rng.uniform(-0.7, 0.7) * np.exp(-(((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))
    height = cv2.GaussianBlur(height, (0, 0), 2.0)
    height = height - float(height.mean())
    height = height / max(float(np.max(np.abs(height))), 1e-6)
    gy, gx = np.gradient(height)
    disp = np.stack([gx, gy], axis=-1).astype(np.float32)
    scale = amp_px / max(float(np.percentile(np.linalg.norm(disp, axis=-1), 98)), 1e-6)
    disp = disp * scale
    disp = np.clip(disp, -amp_px, amp_px)
    return disp.astype(np.float32), height.astype(np.float32)


def np_to_torch_img(a, device):
    return torch.from_numpy(a).permute(2, 0, 1)[None].float().to(device)


def torch_to_np_img(t):
    return t.detach().cpu().clamp(0, 1).numpy()[0].transpose(1, 2, 0)


def warp_image(bg, disp_px):
    # bg: 1x3xHxW, disp_px: 1x2xHxW in pixel units (x,y).
    _, _, h, w = bg.shape
    yy, xx = torch.meshgrid(
        torch.linspace(0, h - 1, h, device=bg.device),
        torch.linspace(0, w - 1, w, device=bg.device),
        indexing="ij",
    )
    x = xx[None] + disp_px[:, 0]
    y = yy[None] + disp_px[:, 1]
    gx = 2.0 * x / max(w - 1, 1) - 1.0
    gy = 2.0 * y / max(h - 1, 1) - 1.0
    grid = torch.stack([gx, gy], dim=-1)
    return F.grid_sample(bg, grid, mode="bilinear", padding_mode="border", align_corners=True)


def warp_np(bg, disp_px):
    h, w = bg.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    mapx = np.clip(xx + disp_px[..., 0], 0, w - 1)
    mapy = np.clip(yy + disp_px[..., 1], 0, h - 1)
    return cv2.remap(bg.astype(np.float32), mapx, mapy, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def render(T, bg, disp_px, ambient=0.16, leak=0.84):
    warped = warp_image(bg, disp_px)
    return torch.clamp(T * (ambient + leak * warped), 0, 1)


def tv(x):
    return (x[..., 1:, :] - x[..., :-1, :]).abs().mean() + (x[..., :, 1:] - x[..., :, :-1]).abs().mean()


def lap(x):
    return (
        -4 * x
        + torch.roll(x, 1, -1)
        + torch.roll(x, -1, -1)
        + torch.roll(x, 1, -2)
        + torch.roll(x, -1, -2)
    )


def logit_np(x):
    x = np.clip(x, 1e-4, 1 - 1e-4)
    return np.log(x / (1 - x)).astype(np.float32)


def init_low_T(obs, bg, ambient, leak, low_res):
    denom = np.clip(ambient + leak * bg, 0.08, 1.2)
    t0 = np.clip(obs / denom, 0.005, 0.96)
    t0_low = cv2.resize(t0, (low_res, low_res), interpolation=cv2.INTER_AREA)
    return logit_np(t0_low)


def upsample_param(p, n, mode="bicubic"):
    return F.interpolate(p, size=(n, n), mode=mode, align_corners=False)


def optimize_lowT_no_disp(obs_np, bg_np, args, device):
    n = obs_np.shape[0]
    obs = np_to_torch_img(obs_np, device)
    bg = np_to_torch_img(bg_np, device)
    zero_disp = torch.zeros((1, 2, n, n), device=device)
    t0 = init_low_T(obs_np, bg_np, args.ambient, args.leak, args.t_low_res)
    t_param = torch.nn.Parameter(torch.from_numpy(t0).permute(2, 0, 1)[None].to(device))
    opt = torch.optim.AdamW([t_param], lr=args.lr_t, weight_decay=0.0)
    log = []
    for step in range(args.steps_no_disp):
        T = torch.sigmoid(upsample_param(t_param, n))
        pred = render(T, bg, zero_disp, args.ambient, args.leak)
        loss_recon = (pred - obs).abs().mean()
        loss = loss_recon + args.t_tv * tv(T)
        opt.zero_grad()
        loss.backward()
        opt.step()
        if step % args.log_every == 0 or step == args.steps_no_disp - 1:
            log.append({"step": step, "loss": float(loss.item()), "recon": float(loss_recon.item())})
    return {"T": torch_to_np_img(torch.sigmoid(upsample_param(t_param, n))), "disp": np.zeros((n, n, 2), np.float32), "log": log}


def optimize_lowT_disp(obs_np, bg_np, args, device):
    n = obs_np.shape[0]
    obs = np_to_torch_img(obs_np, device)
    bg = np_to_torch_img(bg_np, device)
    t0 = init_low_T(obs_np, bg_np, args.ambient, args.leak, args.t_low_res)
    t_param = torch.nn.Parameter(torch.from_numpy(t0).permute(2, 0, 1)[None].to(device))
    disp_param = torch.nn.Parameter(torch.zeros((1, 2, args.disp_low_res, args.disp_low_res), device=device))
    opt = torch.optim.AdamW([
        {"params": [t_param], "lr": args.lr_t},
        {"params": [disp_param], "lr": args.lr_d},
    ], weight_decay=0.0)
    log = []
    for step in range(args.steps_disp):
        T = torch.sigmoid(upsample_param(t_param, n))
        disp = args.max_disp * torch.tanh(upsample_param(disp_param, n, mode="bilinear"))
        pred = render(T, bg, disp, args.ambient, args.leak)
        loss_recon = (pred - obs).abs().mean()
        loss = (
            loss_recon
            + args.t_tv * tv(T)
            + args.disp_tv * tv(disp / args.max_disp)
            + args.disp_lap * lap(disp / args.max_disp).abs().mean()
            + args.disp_mag * (disp / args.max_disp).pow(2).mean()
        )
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_([t_param, disp_param], 5.0)
        opt.step()
        if step % args.log_every == 0 or step == args.steps_disp - 1:
            log.append({
                "step": step,
                "loss": float(loss.item()),
                "recon": float(loss_recon.item()),
                "disp_abs": float(disp.abs().mean().item()),
            })
    T_np = torch_to_np_img(torch.sigmoid(upsample_param(t_param, n)))
    disp_np = disp.detach().cpu().numpy()[0].transpose(1, 2, 0).astype(np.float32)
    return {"T": T_np, "disp": disp_np, "log": log}


def init_unknown_B(obs, low_res):
    # Start from a blurry, normalized version of the observation. This is a bad
    # but realistic initialization: it contains both glass and background.
    p = np.percentile(obs, 96, axis=(0, 1))
    b = np.clip(obs / np.maximum(p[None, None, :], 0.05), 0.04, 0.96)
    b = cv2.GaussianBlur(b.astype(np.float32), (0, 0), 2.5)
    return logit_np(cv2.resize(b, (low_res, low_res), interpolation=cv2.INTER_AREA))


def optimize_lowT_disp_B(obs_np, args, device):
    n = obs_np.shape[0]
    obs = np_to_torch_img(obs_np, device)
    # Unknown background case: start with "B is probably bright/structured" and
    # let the optimizer decide what belongs in B versus T.
    bg_init = init_unknown_B(obs_np, args.b_low_res)
    b_param = torch.nn.Parameter(torch.from_numpy(bg_init).permute(2, 0, 1)[None].to(device))
    b0 = np.clip(np.ones_like(obs_np) * 0.82, 0.05, 0.95)
    t0 = init_low_T(obs_np, b0, args.ambient, args.leak, args.t_low_res)
    t_param = torch.nn.Parameter(torch.from_numpy(t0).permute(2, 0, 1)[None].to(device))
    disp_param = torch.nn.Parameter(torch.zeros((1, 2, args.disp_low_res, args.disp_low_res), device=device))
    opt = torch.optim.AdamW([
        {"params": [t_param], "lr": args.lr_t},
        {"params": [b_param], "lr": args.lr_b},
        {"params": [disp_param], "lr": args.lr_d},
    ], weight_decay=0.0)
    log = []
    for step in range(args.steps_joint):
        T = torch.sigmoid(upsample_param(t_param, n))
        B = torch.sigmoid(upsample_param(b_param, n))
        disp = args.max_disp * torch.tanh(upsample_param(disp_param, n, mode="bilinear"))
        pred = render(T, B, disp, args.ambient, args.leak)
        loss_recon = (pred - obs).abs().mean()
        loss = (
            loss_recon
            + args.t_tv * tv(T)
            + args.b_tv * tv(B)
            + args.disp_tv * tv(disp / args.max_disp)
            + args.disp_lap * lap(disp / args.max_disp).abs().mean()
            + args.disp_mag * (disp / args.max_disp).pow(2).mean()
        )
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_([t_param, b_param, disp_param], 5.0)
        opt.step()
        if step % args.log_every == 0 or step == args.steps_joint - 1:
            log.append({
                "step": step,
                "loss": float(loss.item()),
                "recon": float(loss_recon.item()),
                "disp_abs": float(disp.abs().mean().item()),
                "B_tv": float(tv(B).item()),
            })
    T_np = torch_to_np_img(torch.sigmoid(upsample_param(t_param, n)))
    B_np = torch_to_np_img(torch.sigmoid(upsample_param(b_param, n)))
    disp_np = disp.detach().cpu().numpy()[0].transpose(1, 2, 0).astype(np.float32)
    return {"T": T_np, "bg": B_np, "disp": disp_np, "log": log}


def corr(a, b):
    a = np.asarray(a, np.float64).reshape(-1)
    b = np.asarray(b, np.float64).reshape(-1)
    a = a - a.mean()
    b = b - b.mean()
    den = np.sqrt((a * a).mean() * (b * b).mean())
    if den < 1e-12:
        return 0.0
    return float((a * b).mean() / den)


def patch_lum_cv(T, k=4):
    h, w = T.shape[:2]
    vals = []
    for yi in np.linspace(0.15, 0.75, k):
        for xi in np.linspace(0.15, 0.75, k):
            y0 = int(yi * h)
            x0 = int(xi * w)
            patch = T[y0:y0 + h // 5, x0:x0 + w // 5]
            vals.append(float((patch * LUM).sum(-1).mean()))
    vals = np.array(vals)
    return float(vals.std() / max(vals.mean(), 1e-8))


def highpass(a, sigma=8.0):
    return a - cv2.GaussianBlur(a.astype(np.float32), (0, 0), sigma)


def metrics_for(name, T_rec, disp_rec, bg_rec, gt, args):
    warped_rec = warp_np(bg_rec, disp_rec)
    pred = np.clip(T_rec * (args.ambient + args.leak * warped_rec), 0, 1)
    obs = gt["obs"]
    T_gt = gt["T"]
    disp_gt = gt["disp"]
    bg_gt = gt["bg"]
    lum_T = (T_rec * LUM).sum(-1)
    lum_gt = (T_gt * LUM).sum(-1)
    bg_lum = (gt["warped_bg"] * LUM).sum(-1)
    disp_epe = float(np.linalg.norm(disp_rec - disp_gt, axis=-1).mean())
    return {
        "name": name,
        "renderer_recon_mae": float(np.mean(np.abs(pred - obs))),
        "T_mae": float(np.mean(np.abs(T_rec - T_gt))),
        "T_lum_mae": float(np.mean(np.abs(lum_T - lum_gt))),
        "B_mae": float(np.mean(np.abs(bg_rec - bg_gt))),
        "T_highfreq_corr_with_bg": corr(highpass(lum_T), highpass(bg_lum)),
        "T_lowfreq_corr_with_bg": corr(cv2.GaussianBlur(lum_T, (0, 0), 10), cv2.GaussianBlur(bg_lum, (0, 0), 10)),
        "preview_lum_cv": patch_lum_cv(T_rec),
        "disp_epe_px": disp_epe,
        "disp_corr_x": corr(disp_rec[..., 0], disp_gt[..., 0]),
        "disp_corr_y": corr(disp_rec[..., 1], disp_gt[..., 1]),
    }


def tile(rgb, label, w=180):
    srgb = lin_to_srgb(np.clip(rgb, 0, 1))
    img = (srgb * 255).astype(np.uint8)
    h0, w0 = img.shape[:2]
    img = cv2.resize(img, (w, max(1, int(round(h0 * w / max(w0, 1))))), interpolation=cv2.INTER_AREA)
    hdr = Image.new("RGB", (img.shape[1], 24), (0, 0, 0))
    d = ImageDraw.Draw(hdr)
    d.text((5, 6), label[:32], fill=(255, 230, 90))
    return np.concatenate([np.asarray(hdr), img], axis=0)


def heat_tile(a, label, w=180, cmap=cv2.COLORMAP_TURBO):
    a = np.asarray(a, np.float32)
    lo, hi = np.percentile(a, [2, 98])
    norm = np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)
    img = cv2.applyColorMap((norm * 255).astype(np.uint8), cmap)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h0, w0 = img.shape[:2]
    img = cv2.resize(img, (w, max(1, int(round(h0 * w / max(w0, 1))))), interpolation=cv2.INTER_AREA)
    hdr = Image.new("RGB", (img.shape[1], 24), (0, 0, 0))
    d = ImageDraw.Draw(hdr)
    d.text((5, 6), label[:32], fill=(255, 230, 90))
    return np.concatenate([np.asarray(hdr), img], axis=0)


def save_contact(out_dir, gt, results):
    rows = []
    row1 = [
        tile(gt["T"], "GT clean T"),
        tile(gt["bg"], "background B"),
        tile(gt["warped_bg"], "warped B through relief"),
        tile(gt["obs"], "observed sheet"),
        heat_tile(np.linalg.norm(gt["disp"], axis=-1), "GT disp mag"),
    ]
    h = max(t.shape[0] for t in row1)
    rows.append(np.concatenate([np.pad(t, ((0, h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in row1], 1))

    for key, label in (
        ("raw_trap", "raw RGB trap"),
        ("lowT_no_disp", "lowT no disp"),
        ("lowT_disp", "lowT + knownB + disp"),
        ("joint_B_disp", "lowT + learnedB + disp"),
    ):
        r = results[key]
        bg = r.get("bg", gt["bg"])
        warped = warp_np(bg, r["disp"])
        recon = np.clip(r["T"] * (gt["ambient"] + gt["leak"] * warped), 0, 1)
        err = np.clip(6.0 * np.abs(r["T"] - gt["T"]), 0, 1)
        row = [
            tile(r["T"], f"{label} T"),
            tile(bg, f"{label} B"),
            tile(recon, f"{label} recon"),
            tile(err, f"{label} |T err| x6"),
            heat_tile(np.linalg.norm(r["disp"], axis=-1), f"{label} disp mag"),
        ]
        h = max(t.shape[0] for t in row)
        rows.append(np.concatenate([np.pad(t, ((0, h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in row], 1))

    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    Image.fromarray(np.concatenate(rows, 0)).save(os.path.join(out_dir, "contact.jpg"), quality=92)


def write_summary(out_dir, metrics):
    lines = [
        "# Differentiable sheet inverse summary",
        "",
        "Synthetic known-ground-truth test for explicit background/refraction representation.",
        "",
        "| method | renderer recon MAE | T MAE | B MAE | preview lum CV | T-bg highfreq corr | disp EPE px | disp corr x/y |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in metrics:
        lines.append(
            f"| {m['name']} | {m['renderer_recon_mae']:.4f} | {m['T_mae']:.4f} | {m['B_mae']:.4f} | {m['preview_lum_cv']:.3f} | "
            f"{m['T_highfreq_corr_with_bg']:.3f} | {m['disp_epe_px']:.2f} | {m['disp_corr_x']:.2f}/{m['disp_corr_y']:.2f} |"
        )
    lines.extend([
        "",
        "Read: raw RGB copy can match the observed image directly, but if used as material T it leaks background into the map.",
        "The table's reconstruction column is renderer-space reconstruction after treating each candidate as material state.",
        "",
    ])
    with open(os.path.join(out_dir, "summary_table.md"), "w") as f:
        f.write("\n".join(lines))


def run_case(args, out_dir, case_name="single", verbose=True):
    ensure_dir(out_dir)
    rng = np.random.default_rng(args.seed)
    device = "mps" if torch.backends.mps.is_available() and not args.cpu else "cpu"

    T = make_material_T(args.size, rng)
    bg = make_background(args.size, rng)
    disp, height = make_displacement(args.size, rng, amp_px=args.max_disp * 0.92)
    with torch.no_grad():
        bg_t = np_to_torch_img(bg, device)
        disp_t = torch.from_numpy(disp).permute(2, 0, 1)[None].float().to(device)
        warped_bg = torch_to_np_img(warp_image(bg_t, disp_t))
        obs = np.clip(T * (args.ambient + args.leak * warped_bg), 0, 1).astype(np.float32)
        obs = np.clip(obs + rng.normal(0, 0.0015, obs.shape).astype(np.float32), 0, 1)

    t0 = time.time()
    raw_bg = np.ones_like(bg, dtype=np.float32)
    raw_trap = {"T": obs.copy(), "bg": raw_bg, "disp": np.zeros_like(disp), "log": []}
    no_disp = optimize_lowT_no_disp(obs, bg, args, device)
    no_disp["bg"] = bg
    lowT_disp = optimize_lowT_disp(obs, bg, args, device)
    lowT_disp["bg"] = bg
    joint_B_disp = optimize_lowT_disp_B(obs, args, device)
    elapsed = time.time() - t0

    gt = {
        "T": T,
        "bg": bg,
        "disp": disp,
        "height": height,
        "warped_bg": warped_bg,
        "obs": obs,
        "ambient": args.ambient,
        "leak": args.leak,
    }
    results = {
        "raw_trap": raw_trap,
        "lowT_no_disp": no_disp,
        "lowT_disp": lowT_disp,
        "joint_B_disp": joint_B_disp,
    }
    metrics = [
        metrics_for("raw RGB trap", raw_trap["T"], raw_trap["disp"], raw_trap["bg"], gt, args),
        metrics_for("low-T/no-displacement (known B)", no_disp["T"], no_disp["disp"], no_disp["bg"], gt, args),
        metrics_for("low-T + displacement (known B)", lowT_disp["T"], lowT_disp["disp"], lowT_disp["bg"], gt, args),
        metrics_for("low-T + displacement + learned B", joint_B_disp["T"], joint_B_disp["disp"], joint_B_disp["bg"], gt, args),
    ]

    save_contact(out_dir, gt, results)
    payload = {
        "claim": "Explicit background/refraction variables can keep scene leakage out of T better than raw RGB texture copying.",
        "case": case_name,
        "config": vars(args) | {"device": device, "elapsed_s": elapsed},
        "metrics": metrics,
        "logs": {
            "lowT_no_disp": no_disp["log"],
            "lowT_disp": lowT_disp["log"],
            "joint_B_disp": joint_B_disp["log"],
        },
    }
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(payload, f, indent=2)
    write_summary(out_dir, metrics)

    if verbose:
        print(f"==== DIFFERENTIABLE SHEET INVERSE: {case_name} ====")
        for m in metrics:
            print(
                f"{m['name']:28s} rendererRecon={m['renderer_recon_mae']:.4f} T={m['T_mae']:.4f} "
                f"cv={m['preview_lum_cv']:.3f} bgcorr={m['T_highfreq_corr_with_bg']:.3f} "
                f"dispEPE={m['disp_epe_px']:.2f}"
            )
        print(f"device={device} elapsed={elapsed:.1f}s")
        print("wrote", out_dir)
    return payload


def summarize_sweep(out_dir, cases):
    by_case = {}
    by_method = {}
    for case in cases:
        preset = case["preset"]
        by_case.setdefault(preset, []).append(case)
        for m in case["metrics"]:
            by_method.setdefault((preset, m["name"]), []).append(m)

    def mean_std(rows, key):
        vals = np.array([r[key] for r in rows], dtype=np.float64)
        return float(vals.mean()), float(vals.std())

    summary = {"presets": {}}
    lines = [
        "# Differentiable sheet inverse sweep",
        "",
        "Multi-seed known-ground-truth sweep for explicit background/refraction representation.",
        "",
        "| preset | method | T MAE mean | T MAE std | B MAE mean | preview CV mean | T-bg highfreq corr mean | disp EPE mean | n |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for (preset, method), rows in sorted(by_method.items()):
        t_mu, t_sd = mean_std(rows, "T_mae")
        b_mu, _ = mean_std(rows, "B_mae")
        cv_mu, _ = mean_std(rows, "preview_lum_cv")
        bg_mu, _ = mean_std(rows, "T_highfreq_corr_with_bg")
        de_mu, _ = mean_std(rows, "disp_epe_px")
        lines.append(f"| {preset} | {method} | {t_mu:.4f} | {t_sd:.4f} | {b_mu:.4f} | {cv_mu:.3f} | {bg_mu:.3f} | {de_mu:.2f} | {len(rows)} |")
        summary["presets"].setdefault(preset, {})[method] = {
            "T_mae_mean": t_mu,
            "T_mae_std": t_sd,
            "B_mae_mean": b_mu,
            "preview_lum_cv_mean": cv_mu,
            "T_highfreq_corr_with_bg_mean": bg_mu,
            "disp_epe_px_mean": de_mu,
            "n": len(rows),
        }
    lines.extend([
        "",
        "Read: compare methods within each preset. The displacement-aware optimizer should reduce T error and T-background correlation, not merely reconstruct RGB.",
        "",
    ])
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
    ap.add_argument("--size", type=int, default=160)
    ap.add_argument("--seed", type=int, default=21)
    ap.add_argument("--ambient", type=float, default=0.16)
    ap.add_argument("--leak", type=float, default=0.84)
    ap.add_argument("--max-disp", type=float, default=8.0)
    ap.add_argument("--t-low-res", type=int, default=26)
    ap.add_argument("--disp-low-res", type=int, default=54)
    ap.add_argument("--b-low-res", type=int, default=72)
    ap.add_argument("--steps-no-disp", type=int, default=450)
    ap.add_argument("--steps-disp", type=int, default=900)
    ap.add_argument("--steps-joint", type=int, default=950)
    ap.add_argument("--lr-t", type=float, default=0.08)
    ap.add_argument("--lr-d", type=float, default=0.05)
    ap.add_argument("--lr-b", type=float, default=0.035)
    ap.add_argument("--t-tv", type=float, default=0.010)
    ap.add_argument("--b-tv", type=float, default=0.0015)
    ap.add_argument("--disp-tv", type=float, default=0.004)
    ap.add_argument("--disp-lap", type=float, default=0.004)
    ap.add_argument("--disp-mag", type=float, default=0.001)
    ap.add_argument("--log-every", type=int, default=150)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--sweep-seeds", default="21,22,23,24")
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()

    if not args.sweep:
        run_case(args, args.out)
        return

    ensure_dir(args.out)
    presets = [
        ("easy", {"ambient": 0.20, "leak": 0.72, "max_disp": 5.5, "steps_disp": args.steps_disp, "steps_joint": args.steps_joint}),
        ("default", {"ambient": 0.16, "leak": 0.84, "max_disp": 8.0, "steps_disp": args.steps_disp, "steps_joint": args.steps_joint}),
        ("hard", {"ambient": 0.10, "leak": 0.90, "max_disp": 13.0, "steps_disp": max(args.steps_disp, 1100), "steps_joint": max(args.steps_joint, 1200)}),
    ]
    cases = []
    for preset, overrides in presets:
        for seed in parse_seeds(args.sweep_seeds):
            case_args = argparse.Namespace(**(vars(args) | overrides | {"seed": seed}))
            case_name = f"{preset}_seed{seed}"
            case_dir = os.path.join(args.out, case_name)
            payload = run_case(case_args, case_dir, case_name=case_name, verbose=True)
            cases.append({
                "preset": preset,
                "seed": seed,
                "case": case_name,
                "metrics": payload["metrics"],
                "config": payload["config"],
            })
    summary = summarize_sweep(args.out, cases)
    print("==== SWEEP SUMMARY ====")
    for preset, rows in summary["presets"].items():
        best = min(rows.items(), key=lambda kv: kv[1]["T_mae_mean"])
        print(f"{preset}: best T MAE {best[0]} = {best[1]['T_mae_mean']:.4f}")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
