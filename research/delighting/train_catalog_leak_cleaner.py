#!/usr/bin/env python3
"""Train a tiny neural inverse-rendering cleaner from catalog sheets.

Mira track, report 017:

The catalog is not treated as a product destination. It is used as a weak source
of "clean-ish purchasable sheet" examples. We deliberately contaminate those
sheets with transmitted-background structure, then train a small residual U-Net
to recover the original sheet.

Product target:
  - the glass panel stores a raw purchasable sheet;
  - the preview should reuse that sheet without local window/garden/shadow bias;
  - the model must preserve real relief/texture and should be provenance-labeled
    before shipping because catalog priors can invent smoothness.
"""
import argparse
import json
import os
import time
from dataclasses import dataclass

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.join(HERE, "results", "catalog_leak_cleaner")

import catalog_texture_audit as audit_lib  # noqa: E402
import extract as ex  # noqa: E402
import sheet_texture_prior as prior_exp  # noqa: E402
import suncatcher_bench as sb  # noqa: E402


CATALOG_CATEGORIES = ("Cathedral", "Textured/Baroque")
CONDS = ("raw", "raw_neural", "relit", "relit_neural", "prior")


def seed_all(seed):
    np.random.seed(seed)
    torch.manual_seed(seed)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def resize_min(rgb, min_dim):
    h, w = rgb.shape[:2]
    if min(h, w) >= min_dim:
        return rgb
    s = min_dim / max(1, min(h, w))
    return cv2.resize(rgb, (int(round(w * s)), int(round(h * s))), interpolation=cv2.INTER_CUBIC)


def random_crop(rgb, ps, rng):
    rgb = resize_min(rgb, ps)
    h, w = rgb.shape[:2]
    if h == ps and w == ps:
        return rgb.copy()
    y0 = int(rng.integers(0, h - ps + 1))
    x0 = int(rng.integers(0, w - ps + 1))
    return rgb[y0:y0 + ps, x0:x0 + ps].copy()


def maybe_flip_rot(rgb, rng):
    out = rgb
    if rng.random() < 0.5:
        out = out[:, ::-1]
    if rng.random() < 0.5:
        out = out[::-1]
    k = int(rng.integers(0, 4))
    if k:
        out = np.rot90(out, k)
    return np.ascontiguousarray(out)


def lum_lin(lin):
    return lin[..., 0] * ex.LUM[0] + lin[..., 1] * ex.LUM[1] + lin[..., 2] * ex.LUM[2]


@dataclass
class CatalogSample:
    id: str
    category: str
    rgb: np.ndarray


def load_catalog_samples(registry_path, max_images, max_dim, seed):
    registry = json.load(open(registry_path))
    public_root = audit_lib.public_root_for_registry(registry_path)

    rows = []
    for item in registry:
        local = item.get("local_image", "")
        rel = local[1:] if local.startswith("/") else local
        path = os.path.join(public_root, rel)
        if item.get("status") != "Downloaded":
            continue
        if item.get("category") not in CATALOG_CATEGORIES:
            continue
        if not os.path.exists(path):
            continue
        rows.append(item)

    rng = np.random.default_rng(seed)
    rng.shuffle(rows)
    if max_images:
        rows = rows[:max_images]

    samples = []
    for item in rows:
        try:
            rgb, _ = audit_lib.load_catalog_image(public_root, item, max_dim=max_dim)
            if min(rgb.shape[:2]) < 80:
                continue
            samples.append(CatalogSample(item["id"], item.get("category", "unknown"), rgb.astype(np.float32)))
        except Exception:
            continue
    if len(samples) < 40:
        raise RuntimeError(f"Only found {len(samples)} usable catalog samples at {registry_path}")
    return samples


def split_samples(samples, test_frac=0.18):
    n_test = max(24, int(round(len(samples) * test_frac)))
    return samples[n_test:], samples[:n_test]


def load_photo_rgb(path, max_dim=1200):
    img = Image.open(path).convert("RGB")
    rgb = np.asarray(img).astype(np.float32) / 255.0
    h, w = rgb.shape[:2]
    s = max_dim / max(h, w)
    if s < 1:
        rgb = cv2.resize(rgb, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return rgb


def load_backgrounds():
    backgrounds = []
    for path in (sb.PATTERN,):
        if os.path.exists(path):
            backgrounds.append(load_photo_rgb(path))
    return backgrounds


def procedural_background(ps, rng):
    yy, xx = np.mgrid[0:ps, 0:ps].astype(np.float32)
    xx = xx / max(ps - 1, 1)
    yy = yy / max(ps - 1, 1)

    c1 = rng.uniform([0.08, 0.15, 0.12], [0.75, 0.85, 1.0])
    c2 = rng.uniform([0.55, 0.45, 0.25], [1.0, 0.95, 0.75])
    grad = (0.35 + 0.65 * (rng.random() * xx + rng.random() * yy))
    bg = c1[None, None, :] * (1 - grad[..., None]) + c2[None, None, :] * grad[..., None]

    noise = rng.normal(0, 1, (max(6, ps // 18), max(6, ps // 18), 3)).astype(np.float32)
    noise = cv2.resize(noise, (ps, ps), interpolation=cv2.INTER_CUBIC)
    bg = np.clip(bg + 0.10 * noise, 0, 1)

    # Window/railing-like hard structure, later blurred/distorted through glass.
    if rng.random() < 0.75:
        bars = np.ones((ps, ps), np.float32)
        for _ in range(int(rng.integers(1, 4))):
            vertical = rng.random() < 0.65
            pos = int(rng.integers(ps // 8, max(ps // 8 + 1, ps - ps // 8)))
            width = int(rng.integers(max(2, ps // 80), max(3, ps // 24)))
            if vertical:
                bars[:, max(0, pos - width):min(ps, pos + width)] *= rng.uniform(0.18, 0.55)
            else:
                bars[max(0, pos - width):min(ps, pos + width), :] *= rng.uniform(0.18, 0.55)
        bg *= bars[..., None]
    return np.clip(bg, 0, 1).astype(np.float32)


def background_patch(ps, backgrounds, rng):
    if backgrounds and rng.random() < 0.65:
        bg = backgrounds[int(rng.integers(0, len(backgrounds)))]
        patch = random_crop(bg, min(ps, min(bg.shape[:2])), rng)
        patch = cv2.resize(patch, (ps, ps), interpolation=cv2.INTER_AREA)
        if rng.random() < 0.5:
            patch = patch[:, ::-1]
        return np.ascontiguousarray(patch.astype(np.float32))
    return procedural_background(ps, rng)


def distort_background(bg, rng):
    ps = bg.shape[0]
    yy, xx = np.mgrid[0:ps, 0:ps].astype(np.float32)
    amp = rng.uniform(1.5, 9.0)
    freq1 = rng.uniform(1.2, 4.5)
    freq2 = rng.uniform(1.2, 4.5)
    phase1 = rng.uniform(0, 2 * np.pi)
    phase2 = rng.uniform(0, 2 * np.pi)
    dx = amp * np.sin(2 * np.pi * yy / ps * freq1 + phase1)
    dy = amp * np.cos(2 * np.pi * xx / ps * freq2 + phase2)
    mapx = np.clip(xx + dx, 0, ps - 1).astype(np.float32)
    mapy = np.clip(yy + dy, 0, ps - 1).astype(np.float32)
    out = cv2.remap(bg, mapx, mapy, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    sigma = rng.uniform(1.0, 7.0)
    return cv2.GaussianBlur(out, (0, 0), sigma).astype(np.float32)


def synthetic_leak(clean_rgb, backgrounds, rng):
    """Return contaminated_rgb, clean_rgb.

    The contamination is deliberately closer to cathedral see-through leakage
    than the earlier generic gradients: distorted background luminance,
    chromatic leakage, smooth exposure rolloff, occasional glare.
    """
    ps = clean_rgb.shape[0]
    clean_rgb = maybe_flip_rot(clean_rgb, rng)

    # Identity examples teach the residual network that "no cleanup needed" is a
    # valid answer, preventing the catalog prior from becoming an airbrush.
    if rng.random() < 0.12:
        noisy = np.clip(clean_rgb + rng.normal(0, 0.006, clean_rgb.shape), 0, 1).astype(np.float32)
        return noisy, clean_rgb.astype(np.float32)

    bg = distort_background(background_patch(ps, backgrounds, rng), rng)
    clean_lin = ex.srgb_to_lin(clean_rgb).astype(np.float32)
    bg_lin = ex.srgb_to_lin(bg).astype(np.float32)

    bg_y = np.clip(lum_lin(bg_lin), 1e-4, None)
    bg_y = cv2.GaussianBlur(bg_y, (0, 0), rng.uniform(2.0, 9.0))
    bg_y = bg_y / max(float(bg_y.mean()), 1e-4)
    bg_y = np.clip(bg_y, 0.22, 3.2)

    yy, xx = np.mgrid[0:ps, 0:ps].astype(np.float32)
    xx = xx / max(ps - 1, 1)
    yy = yy / max(ps - 1, 1)
    slope = rng.uniform(-0.55, 0.55) * (xx - 0.5) + rng.uniform(-0.55, 0.55) * (yy - 0.5)
    exposure = np.exp(slope.astype(np.float32))

    strength = rng.uniform(0.18, 0.62)
    mult = np.exp(strength * np.clip(np.log(bg_y), -1.1, 1.1)) * exposure
    mult = cv2.GaussianBlur(mult.astype(np.float32), (0, 0), rng.uniform(1.5, 5.0))

    contam_lin = clean_lin * mult[..., None]

    # Chromatic see-through: keep the sheet luminance but bend chroma toward the
    # leaked scene in low-frequency regions.
    if rng.random() < 0.78:
        bg_chroma = bg_lin / np.maximum(lum_lin(bg_lin)[..., None], 1e-4)
        bg_chroma = cv2.GaussianBlur(bg_chroma, (0, 0), rng.uniform(3.0, 10.0))
        bg_chroma = bg_chroma / max(float(np.dot(bg_chroma.reshape(-1, 3).mean(0), ex.LUM)), 1e-4)
        clean_y = lum_lin(clean_lin)[..., None]
        leak = clean_y * bg_chroma
        beta = rng.uniform(0.03, 0.24)
        contam_lin = (1 - beta) * contam_lin + beta * leak

    if rng.random() < 0.28:
        cx, cy = rng.uniform(0.1, 0.9, 2)
        sx, sy = rng.uniform(0.10, 0.32), rng.uniform(0.05, 0.24)
        glare = np.exp(-(((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2)).astype(np.float32)
        color = rng.uniform(0.6, 1.0, 3).astype(np.float32)
        contam_lin = contam_lin + rng.uniform(0.015, 0.08) * glare[..., None] * color[None, None, :]

    contam_lin *= rng.uniform(0.86, 1.16)
    contam_rgb = ex.lin_to_srgb(np.clip(contam_lin, 0, 1)).astype(np.float32)
    contam_rgb = np.clip(contam_rgb + rng.normal(0, rng.uniform(0.002, 0.010), contam_rgb.shape), 0, 1)
    return contam_rgb.astype(np.float32), clean_rgb.astype(np.float32)


def to_torch_batch(arrs, device):
    x = torch.from_numpy(np.stack(arrs)).permute(0, 3, 1, 2).float()
    return x.to(device)


def make_batch(samples, backgrounds, bs, ps, rng, device):
    xs, ys = [], []
    for _ in range(bs):
        sample = samples[int(rng.integers(0, len(samples)))]
        clean = random_crop(sample.rgb, ps, rng)
        x, y = synthetic_leak(clean, backgrounds, rng)
        xs.append(x)
        ys.append(y)
    return to_torch_batch(xs, device), to_torch_batch(ys, device)


def conv_block(cin, cout):
    groups = max(g for g in range(1, min(8, cout) + 1) if cout % g == 0)
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1),
        nn.GroupNorm(groups, cout),
        nn.SiLU(inplace=True),
        nn.Conv2d(cout, cout, 3, padding=1),
        nn.GroupNorm(groups, cout),
        nn.SiLU(inplace=True),
    )


class TinyMaterialCleaner(nn.Module):
    """Residual U-Net: change only what the input gives evidence for."""

    def __init__(self, base=18, smooth_residual=0):
        super().__init__()
        self.smooth_residual = int(smooth_residual)
        self.enc1 = conv_block(3, base)
        self.enc2 = conv_block(base, base * 2)
        self.enc3 = conv_block(base * 2, base * 4)
        self.pool = nn.MaxPool2d(2)
        self.bott = conv_block(base * 4, base * 4)
        self.up3 = nn.ConvTranspose2d(base * 4, base * 4, 2, stride=2)
        self.dec3 = conv_block(base * 8, base * 2)
        self.up2 = nn.ConvTranspose2d(base * 2, base * 2, 2, stride=2)
        self.dec2 = conv_block(base * 4, base)
        self.up1 = nn.ConvTranspose2d(base, base, 2, stride=2)
        self.dec1 = conv_block(base * 2, base)
        self.head = nn.Conv2d(base, 3, 1)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        b = self.bott(self.pool(e3))
        d3 = self.dec3(torch.cat([self.up3(b), e3], 1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], 1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], 1))
        resid = 0.42 * torch.tanh(self.head(d1))
        if self.smooth_residual > 1:
            k = self.smooth_residual
            resid = F.avg_pool2d(resid, k, stride=1, padding=k // 2)
        return torch.clamp(x + resid, 0.0, 1.0)


def lowpass_torch(x, k=25):
    return F.avg_pool2d(x, k, stride=1, padding=k // 2)


def train_model(train, test, backgrounds, args, out_dir):
    device = "mps" if torch.backends.mps.is_available() and not args.cpu else "cpu"
    rng = np.random.default_rng(args.seed + 100)
    net = TinyMaterialCleaner(base=args.base, smooth_residual=args.smooth_residual).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, args.steps)
    n_params = sum(p.numel() for p in net.parameters())
    print(f"catalog samples: train={len(train)} test={len(test)}")
    print(f"model params: {n_params/1e3:.1f}k device={device}")

    log = []
    t0 = time.time()
    net.train()
    for step in range(args.steps):
        x, y = make_batch(train, backgrounds, args.bs, args.patch, rng, device)
        pred = net(x)
        pred_low = lowpass_torch(pred)
        y_low = lowpass_torch(y)
        x_low = lowpass_torch(x)
        pred_hi = pred - pred_low
        y_hi = y - y_low

        l_rgb = F.l1_loss(pred, y)
        l_low = F.l1_loss(pred_low, y_low)
        l_hi = F.l1_loss(pred_hi, y_hi)
        # Penalize unnecessary broad edits on already similar inputs.
        l_edit = torch.mean(torch.abs(pred_low - x_low)) * 0.08
        loss = l_rgb + 0.90 * l_low + 0.35 * l_hi + l_edit

        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 4.0)
        opt.step()
        sched.step()

        if step % args.log_every == 0 or step == args.steps - 1:
            row = {
                "step": int(step),
                "loss": float(loss.item()),
                "rgb": float(l_rgb.item()),
                "low": float(l_low.item()),
                "hi": float(l_hi.item()),
                "edit": float(l_edit.item()),
                "elapsed_s": float(time.time() - t0),
            }
            log.append(row)
            print(
                f"step {step:5d} loss={row['loss']:.4f} rgb={row['rgb']:.4f} "
                f"low={row['low']:.4f} hi={row['hi']:.4f} {row['elapsed_s']:.0f}s"
            )

    torch.save({
        "state_dict": net.state_dict(),
        "base": args.base,
        "smooth_residual": args.smooth_residual,
        "args": vars(args),
    }, os.path.join(out_dir, "catalog_leak_cleaner.pt"))
    json.dump(log, open(os.path.join(out_dir, "train_log.json"), "w"), indent=2)
    return net, device, log


def highpass_np(rgb, sigma):
    low = cv2.GaussianBlur(rgb.astype(np.float32), (0, 0), sigma)
    return rgb.astype(np.float32) - low


def lowpass_np(rgb, sigma):
    return cv2.GaussianBlur(rgb.astype(np.float32), (0, 0), sigma)


def eval_pair_metrics(raw, pred, target):
    raw = raw.astype(np.float32)
    pred = pred.astype(np.float32)
    target = target.astype(np.float32)
    raw_mae = float(np.mean(np.abs(raw - target)))
    pred_mae = float(np.mean(np.abs(pred - target)))

    raw_low = lowpass_np(raw, 10.0)
    pred_low = lowpass_np(pred, 10.0)
    tgt_low = lowpass_np(target, 10.0)
    low_raw = float(np.mean(np.abs(raw_low - tgt_low)))
    low_pred = float(np.mean(np.abs(pred_low - tgt_low)))

    raw_hi = highpass_np(raw, 6.0)
    pred_hi = highpass_np(pred, 6.0)
    tgt_hi = highpass_np(target, 6.0)
    hi_raw = float(np.mean(np.abs(raw_hi - tgt_hi)))
    hi_pred = float(np.mean(np.abs(pred_hi - tgt_hi)))

    y_t = lum_lin(ex.srgb_to_lin(target))
    y_p = lum_lin(ex.srgb_to_lin(pred))
    target_detail = float(np.std(highpass_np(y_t[..., None], 5.0)))
    pred_detail = float(np.std(highpass_np(y_p[..., None], 5.0)))

    return {
        "mae_raw": raw_mae,
        "mae_neural": pred_mae,
        "low_mae_raw": low_raw,
        "low_mae_neural": low_pred,
        "high_mae_raw": hi_raw,
        "high_mae_neural": hi_pred,
        "detail_ratio_neural_to_target": pred_detail / max(target_detail, 1e-6),
    }


def run_model_rgb(net, device, rgb):
    h, w = rgb.shape[:2]
    pad_h = (8 - h % 8) % 8
    pad_w = (8 - w % 8) % 8
    rgb_pad = np.pad(rgb, ((0, pad_h), (0, pad_w), (0, 0)), mode="reflect")
    x = torch.from_numpy(rgb_pad[None].transpose(0, 3, 1, 2)).float().to(device)
    with torch.no_grad():
        y = net(x).detach().cpu().numpy()[0].transpose(1, 2, 0)
    return np.clip(y[:h, :w], 0, 1).astype(np.float32)


def summarize_metric_rows(rows):
    out = {}
    for key in rows[0]:
        vals = np.array([r[key] for r in rows], dtype=np.float64)
        out[key] = {
            "mean": float(vals.mean()),
            "median": float(np.median(vals)),
            "p90": float(np.percentile(vals, 90)),
        }
    out["mae_reduction_pct"] = float(100.0 * (out["mae_raw"]["mean"] - out["mae_neural"]["mean"]) / max(out["mae_raw"]["mean"], 1e-9))
    out["low_mae_reduction_pct"] = float(100.0 * (out["low_mae_raw"]["mean"] - out["low_mae_neural"]["mean"]) / max(out["low_mae_raw"]["mean"], 1e-9))
    return out


def labeled_tile(rgb, text, w=180):
    rgb8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    h0, w0 = rgb8.shape[:2]
    scale = w / max(w0, 1)
    tile = cv2.resize(rgb8, (w, max(1, int(round(h0 * scale)))), interpolation=cv2.INTER_AREA)
    hdr = Image.new("RGB", (tile.shape[1], 24), (0, 0, 0))
    draw = ImageDraw.Draw(hdr)
    draw.text((5, 6), text[:34], fill=(255, 230, 90))
    return np.concatenate([np.asarray(hdr), tile], axis=0)


def save_synthetic_contact(examples, path):
    rows = []
    for i, exm in enumerate(examples[:6]):
        err = np.clip(4.0 * np.abs(exm["pred"] - exm["target"]), 0, 1)
        tiles = [
            labeled_tile(exm["target"], f"{i} clean catalog"),
            labeled_tile(exm["raw"], "leaked input"),
            labeled_tile(exm["pred"], "neural clean"),
            labeled_tile(err, "4x abs error"),
        ]
        h = max(t.shape[0] for t in tiles)
        tiles = [np.pad(t, ((0, h - t.shape[0]), (0, 8), (0, 0)), constant_values=248) for t in tiles]
        rows.append(np.concatenate(tiles, axis=1))
    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    Image.fromarray(np.concatenate(rows, axis=0)).save(path, quality=92)


def eval_synthetic(net, device, test, backgrounds, args, out_dir):
    rng = np.random.default_rng(args.seed + 2000)
    rows = []
    examples = []
    for i in range(args.eval_patches):
        sample = test[int(rng.integers(0, len(test)))]
        clean = random_crop(sample.rgb, args.patch, rng)
        raw, target = synthetic_leak(clean, backgrounds, rng)
        pred = run_model_rgb(net, device, raw)
        metric = eval_pair_metrics(raw, pred, target)
        metric["sample_id"] = sample.id
        metric["category"] = sample.category
        rows.append(metric)
        if len(examples) < 6:
            examples.append({"raw": raw, "pred": pred, "target": target})
    save_synthetic_contact(examples, os.path.join(out_dir, "synthetic_contact.jpg"))
    return rows, summarize_metric_rows([{k: v for k, v in r.items() if isinstance(v, float)} for r in rows])


def apply_neural_to_sheets(net, device, sheets):
    for name, sheet in sheets.items():
        x0, y0, x1, y1 = [int(v) for v in sheet["interior"]]
        for src, dst in (("raw", "raw_neural"), ("relit", "relit_neural")):
            material = sheet[src].copy()
            roi_rgb = np.clip(ex.lin_to_srgb(material[y0:y1, x0:x1]), 0, 1).astype(np.float32)
            pred_rgb = run_model_rgb(net, device, roi_rgb)
            material[y0:y1, x0:x1] = np.clip(ex.srgb_to_lin(pred_rgb), 0, 1)
            sheet[dst] = material
            sheet[f"{dst}_flatness"] = prior_exp.robust_flatness(material, sheet["interior"])


def metric_position_ext(polys, cens, sheets, scales):
    out = {}
    for n in polys:
        s = prior_exp.ASSIGN[n]
        centers = sb.grid_centers(sb.valid_center_range(polys[n], sheets[s]["interior"], scales[s]), 3, 3)
        entry = {"label": prior_exp.LABELS[n], "sheet": s, "n_positions": len(centers)}
        for cond in CONDS:
            means = [
                sb.piece_mean_lin(sheets[s][cond], polys[n], cens[n], center, scales[s])[0]
                for center in centers
            ]
            entry[cond] = sb.dispersion(means)
        out[n] = entry
    return out


def metric_consistency_ext(polys, cens, sheets, scales, place, by_sheet):
    out = {}
    for s, names in by_sheet.items():
        if len(names) < 2:
            continue
        entry = {"n_pieces": len(names)}
        for cond in CONDS:
            means = [
                sb.piece_mean_lin(sheets[s][cond], polys[n], cens[n], place[n], scales[s])[0]
                for n in names
            ]
            entry[cond] = sb.dispersion(means)
        out[s] = entry
    return out


def summarize_position(position):
    out = {}
    for cond in CONDS:
        out[cond] = {
            "mean_dE": float(np.mean([position[n][cond]["mean_dE_to_centroid"] for n in position])),
            "lum_cv": float(np.mean([position[n][cond]["lum_cv"] for n in position])),
            "hue_std_deg": float(np.mean([position[n][cond]["hue_std_deg"] for n in position])),
        }
    return out


def sheet_texture_row(sheet, cond):
    x0, y0, x1, y1 = [int(v) for v in sheet["interior"]]
    rgb = np.clip(ex.lin_to_srgb(sheet[cond][y0:y1, x0:x1]), 0, 1)
    return audit_lib.texture_metrics_from_rgb01(rgb)


def save_suncatcher_sheet_contact(sheets, out_path):
    rows = []
    for name in ("green", "orange"):
        sheet = sheets[name]
        x0, y0, x1, y1 = [int(v) for v in sheet["interior"]]
        tiles = []
        for cond, label in (
            ("raw", "raw photo"),
            ("raw_neural", "raw+neural"),
            ("relit", "fixed T/h"),
            ("relit_neural", "T/h+neural"),
            ("prior", "hand sheet prior"),
        ):
            rgb = np.clip(ex.lin_to_srgb(sheet[cond][y0:y1, x0:x1]), 0, 1)
            tiles.append(labeled_tile(rgb, f"{name} {label}", w=220))
        h = max(t.shape[0] for t in tiles)
        tiles = [np.pad(t, ((0, h - t.shape[0]), (0, 8), (0, 0)), constant_values=245) for t in tiles]
        rows.append(np.concatenate(tiles, axis=1))
    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    Image.fromarray(np.concatenate(rows, axis=0)).save(out_path, quality=92)


def eval_suncatcher(net, device, out_dir):
    sheets = prior_exp.prep_sheets()
    apply_neural_to_sheets(net, device, sheets)

    polys = sb.parse_gt_polygons(sb.TUT_TYPES)
    cens = {n: sb.centroid(p) for n, p in polys.items()}
    by_sheet, scales, place = prior_exp.setup_geometry(polys, sheets)
    position = metric_position_ext(polys, cens, sheets, scales)
    consistency = metric_consistency_ext(polys, cens, sheets, scales, place, by_sheet)
    aggregate = summarize_position(position)

    sheet_metrics = {}
    for s, sheet in sheets.items():
        sheet_metrics[s] = {}
        for cond in CONDS:
            flat = prior_exp.robust_flatness(sheet[cond], sheet["interior"])
            tex = sheet_texture_row(sheet, cond)
            sheet_metrics[s][cond] = {
                "cv": flat["cv"],
                "lowfreq_cv": flat["lowfreq_cv"],
                "highfreq_std": tex["highfreq_std"],
                "chroma_mad": tex["chroma_mad"],
            }

    save_suncatcher_sheet_contact(sheets, os.path.join(out_dir, "suncatcher_sheet_contact.jpg"))
    return {
        "metric1_cross_piece_consistency": consistency,
        "metric2_position_sensitivity": position,
        "metric2_aggregate": aggregate,
        "sheet_metrics": sheet_metrics,
    }


def write_summary(out_dir, metrics):
    syn = metrics["synthetic_summary"]
    agg = metrics["suncatcher"]["metric2_aggregate"]
    lines = [
        "# Catalog leak cleaner summary",
        "",
        "Tiny residual U-Net trained on clean-ish manufacturer sheets with synthetic transmitted-background leakage.",
        "",
        "## Synthetic held-out",
        "",
        "| metric | contaminated | neural | change |",
        "|---|---:|---:|---:|",
        f"| RGB MAE | {syn['mae_raw']['mean']:.4f} | {syn['mae_neural']['mean']:.4f} | {syn['mae_reduction_pct']:.1f}% lower |",
        f"| low-frequency MAE | {syn['low_mae_raw']['mean']:.4f} | {syn['low_mae_neural']['mean']:.4f} | {syn['low_mae_reduction_pct']:.1f}% lower |",
        f"| high-frequency MAE | {syn['high_mae_raw']['mean']:.4f} | {syn['high_mae_neural']['mean']:.4f} | {(100 * (syn['high_mae_raw']['mean'] - syn['high_mae_neural']['mean']) / max(syn['high_mae_raw']['mean'], 1e-9)):.1f}% lower |",
        f"| detail energy ratio | 1.000 target | {syn['detail_ratio_neural_to_target']['mean']:.3f} | closer is better |",
        "",
        "## Real suncatcher position sensitivity",
        "",
        "| condition | mean dE | luminance CV | hue std deg |",
        "|---|---:|---:|---:|",
    ]
    for cond in CONDS:
        lines.append(f"| {cond} | {agg[cond]['mean_dE']:.2f} | {agg[cond]['lum_cv']:.3f} | {agg[cond]['hue_std_deg']:.1f} |")
    lines.extend([
        "",
        "## Read",
        "",
        "- `raw_neural` applies the learned cleaner directly to the raw sheet photo; `relit_neural` applies it after fixed `T/h` extraction.",
        "- `prior` is the earlier hand sheet-level prior. It remains the consistency ceiling but can over-flatten true sheet variation.",
        "- A useful neural result is not only lower dE/CV; it must also keep high-frequency texture near the source. See `suncatcher.sheet_metrics` in `metrics.json`.",
        "",
    ])
    with open(os.path.join(out_dir, "summary_table.md"), "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default=audit_lib.resolve_default_registry())
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--max-images", type=int, default=420)
    ap.add_argument("--max-dim", type=int, default=420)
    ap.add_argument("--steps", type=int, default=900)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--patch", type=int, default=128)
    ap.add_argument("--base", type=int, default=18)
    ap.add_argument("--smooth-residual", type=int, default=0,
                    help="If >1, blur the predicted residual so the net edits only low-frequency leakage.")
    ap.add_argument("--lr", type=float, default=1.5e-3)
    ap.add_argument("--eval-patches", type=int, default=96)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--log-every", type=int, default=100)
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args()

    seed_all(args.seed)
    out_dir = ensure_dir(args.out)
    print("registry:", args.registry)
    samples = load_catalog_samples(args.registry, args.max_images, args.max_dim, args.seed)
    train, test = split_samples(samples)
    backgrounds = load_backgrounds()
    net, device, train_log = train_model(train, test, backgrounds, args, out_dir)
    syn_rows, syn_summary = eval_synthetic(net, device, test, backgrounds, args, out_dir)
    suncatcher = eval_suncatcher(net, device, out_dir)

    metrics = {
        "claim": "Catalog sheets can act as weak clean-material examples for a neural cleaner trained to remove transmitted-background leakage.",
        "honesty": "This is not measured ground truth for a user's sheet; it is a learned plausible prior and needs confidence/provenance before product use.",
        "config": vars(args),
        "catalog": {
            "categories": list(CATALOG_CATEGORIES),
            "n_samples": len(samples),
            "n_train": len(train),
            "n_test": len(test),
        },
        "train_log": train_log,
        "synthetic_rows": syn_rows,
        "synthetic_summary": syn_summary,
        "suncatcher": suncatcher,
    }
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    write_summary(out_dir, metrics)

    print("\n==== SYNTHETIC HELD-OUT ====")
    print(f"MAE raw {syn_summary['mae_raw']['mean']:.4f} -> neural {syn_summary['mae_neural']['mean']:.4f}")
    print(f"lowfreq raw {syn_summary['low_mae_raw']['mean']:.4f} -> neural {syn_summary['low_mae_neural']['mean']:.4f}")
    print(f"detail ratio neural/target {syn_summary['detail_ratio_neural_to_target']['mean']:.3f}")
    print("\n==== REAL SUNCATCHER POSITION SENSITIVITY ====")
    for cond, row in suncatcher["metric2_aggregate"].items():
        print(f"{cond:6s}: dE={row['mean_dE']:.2f} lumCV={row['lum_cv']:.3f} hue={row['hue_std_deg']:.1f}")
    print("wrote", out_dir)


if __name__ == "__main__":
    main()
