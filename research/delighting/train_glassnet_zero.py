#!/usr/bin/env python3
"""GlassNet-zero: a deliberately tiny neural inverse-rendering baseline.

This is the first high-risk neural track experiment. It trains a small U-Net-ish
model on the synthetic glass samples to predict:

  output[0:3] = T(x) RGB transmittance
  output[3]   = h(x) haze/diffusion
  output[4]   = shadow/source-contamination confidence proxy

It is *not* meant to be a product model. It is a research harness that answers:

  - Can a learned prior beat the classical extractor on held-out synthetic
    preview-invariance?
  - Does adding shadowed inputs teach the model not to bake hand shadows into T?
  - What scale of data/compute would make the neural path worth funding?

The model is intentionally small enough to train on CPU in minutes. If this
cannot show a signal, we should fix data/losses before asking for GPU/cloud.
"""
import argparse
import json
import os
import random
import sys
from dataclasses import dataclass

os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract  # noqa: E402
import eval_preview_invariance as preview_eval  # noqa: E402

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except Exception as exc:  # pragma: no cover - human-readable setup failure
    raise SystemExit(
        "GlassNet-zero requires PyTorch in the research venv. "
        "Install with: research/delighting/.venv/bin/python -m pip install torch"
    ) from exc


CLASS_MAP = preview_eval.CLASS_MAP
CLASS_LABELS = sorted(CLASS_MAP)
CLASS_TO_IDX = {label: i for i, label in enumerate(CLASS_LABELS)}
EPS = 1e-6


@dataclass
class Sample:
    name: str
    class_label: str
    glass_name: str
    kind: str
    image: np.ndarray       # H,W,3 linear RGB photo
    target: np.ndarray      # H,W,5 = T,h,shadow
    valid: np.ndarray       # H,W bool


def load_gt_h(sample_dir):
    h = preview_eval.load_gt_h(sample_dir)
    if h is None:
        return None
    if h.ndim == 3:
        h = h[..., 0]
    return h


def load_records(data_dir, size):
    records = []
    skipped = []
    for sample_dir in sorted(os.path.join(data_dir, d) for d in os.listdir(data_dir)):
        if not os.path.isdir(sample_dir):
            continue
        meta_path = os.path.join(sample_dir, "meta.json")
        if not os.path.exists(meta_path):
            skipped.append([os.path.basename(sample_dir), "no meta"])
            continue
        meta = json.load(open(meta_path))
        label = meta.get("class_label")
        if label not in CLASS_MAP:
            skipped.append([os.path.basename(sample_dir), "unknown class"])
            continue
        clean_path = preview_eval.clean_photo_path(sample_dir)
        shadow_path = preview_eval.shadow_photo_path(sample_dir)
        gtT = preview_eval.load_gt_T(sample_dir)
        gth = load_gt_h(sample_dir)
        if clean_path is None or shadow_path is None or gtT is None or gth is None:
            skipped.append([os.path.basename(sample_dir), "incomplete"])
            continue

        clean = extract.load_linear(clean_path, None, size)
        shadow = extract.load_linear(shadow_path, None, size)
        H, W = clean.shape[:2]
        gtT = preview_eval.resize_to(gtT, (H, W))
        gth = preview_eval.resize_to(gth[..., None], (H, W))
        if gth.ndim == 3:
            gth = gth[..., 0]
        valid = preview_eval.valid_mask(sample_dir, clean, gtT, gtT)
        shadow_mask = preview_eval.detect_shadow(clean, shadow) & valid

        base_target = np.concatenate([gtT, gth[..., None]], axis=-1)
        zeros = np.zeros((H, W, 1), dtype=np.float64)
        sh = shadow_mask.astype(np.float64)[..., None]
        for kind, image, smask in (
            ("clean", clean, zeros),
            ("shadow", shadow, sh),
        ):
            records.append(Sample(
                name=os.path.basename(sample_dir),
                class_label=label,
                glass_name=meta.get("glass_name", os.path.basename(sample_dir)),
                kind=kind,
                image=np.clip(image, 0, 1).astype(np.float32),
                target=np.clip(np.concatenate([base_target, smask], axis=-1), 0, 1).astype(np.float32),
                valid=valid.astype(bool),
            ))
    return records, skipped


def split_records(records):
    """Hold out one clean/shadow pair per recipe where possible."""
    by_label = {}
    for r in records:
        by_label.setdefault(r.class_label, []).append(r)
    hold_names = set()
    for label, rs in by_label.items():
        names = sorted({r.name for r in rs})
        if len(names) > 1:
            hold_names.add(names[-1])
    train = [r for r in records if r.name not in hold_names]
    test = [r for r in records if r.name in hold_names]
    return train, test, sorted(hold_names)


class TinyGlassNet(nn.Module):
    def __init__(self, base=24, in_ch=3):
        super().__init__()
        self.enc1 = nn.Sequential(nn.Conv2d(in_ch, base, 3, padding=1), nn.GELU(),
                                  nn.Conv2d(base, base, 3, padding=1), nn.GELU())
        self.enc2 = nn.Sequential(nn.Conv2d(base, base * 2, 3, stride=2, padding=1), nn.GELU(),
                                  nn.Conv2d(base * 2, base * 2, 3, padding=1), nn.GELU())
        self.enc3 = nn.Sequential(nn.Conv2d(base * 2, base * 4, 3, stride=2, padding=1), nn.GELU(),
                                  nn.Conv2d(base * 4, base * 4, 3, padding=1), nn.GELU())
        self.mid = nn.Sequential(nn.Conv2d(base * 4, base * 4, 3, padding=1), nn.GELU(),
                                 nn.Conv2d(base * 4, base * 4, 3, padding=1), nn.GELU())
        self.up2 = nn.Conv2d(base * 4 + base * 2, base * 2, 3, padding=1)
        self.up1 = nn.Conv2d(base * 2 + base, base, 3, padding=1)
        self.out = nn.Conv2d(base, 5, 1)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        m = self.mid(e3)
        u2 = F.interpolate(m, size=e2.shape[-2:], mode="bilinear", align_corners=False)
        u2 = F.gelu(self.up2(torch.cat([u2, e2], dim=1)))
        u1 = F.interpolate(u2, size=e1.shape[-2:], mode="bilinear", align_corners=False)
        u1 = F.gelu(self.up1(torch.cat([u1, e1], dim=1)))
        return torch.sigmoid(self.out(u1))


def class_planes(record, H, W):
    planes = np.zeros((H, W, len(CLASS_LABELS)), dtype=np.float32)
    planes[..., CLASS_TO_IDX[record.class_label]] = 1.0
    return planes


def model_input(record, image):
    H, W = image.shape[:2]
    return np.concatenate([image, class_planes(record, H, W)], axis=-1)


def random_crop_batch(records, batch, crop, device):
    xs, ys, masks = [], [], []
    for _ in range(batch):
        r = random.choice(records)
        H, W = r.image.shape[:2]
        if H < crop or W < crop:
            raise ValueError(f"crop {crop} too large for sample {r.name} {H}x{W}")
        y = random.randint(0, H - crop)
        x = random.randint(0, W - crop)
        img = r.image[y:y + crop, x:x + crop]
        tgt = r.target[y:y + crop, x:x + crop]
        valid = r.valid[y:y + crop, x:x + crop].astype(np.float32)
        if random.random() < 0.5:
            img = img[:, ::-1].copy()
            tgt = tgt[:, ::-1].copy()
            valid = valid[:, ::-1].copy()
        if random.random() < 0.5:
            img = img[::-1].copy()
            tgt = tgt[::-1].copy()
            valid = valid[::-1].copy()
        inp = model_input(r, img)
        xs.append(np.transpose(inp, (2, 0, 1)))
        ys.append(np.transpose(tgt, (2, 0, 1)))
        masks.append(valid[None, ...])
    x = torch.tensor(np.stack(xs), device=device)
    y = torch.tensor(np.stack(ys), device=device)
    m = torch.tensor(np.stack(masks), device=device)
    return x, y, m


def loss_fn(pred, target, valid):
    valid5 = valid.expand_as(pred)
    l1 = torch.abs(pred[:, :4] - target[:, :4])
    # T is the money map; h is important but currently noisier in the generator.
    weights = torch.tensor([1.0, 1.0, 1.0, 0.55], device=pred.device).view(1, 4, 1, 1)
    map_loss = (l1 * weights * valid.expand_as(l1)).sum() / (valid.expand_as(l1).sum() + EPS)
    shadow_target = target[:, 4:5]
    shadow_loss = F.binary_cross_entropy(pred[:, 4:5], shadow_target, reduction="none")
    shadow_loss = (shadow_loss * valid).sum() / (valid.sum() + EPS)

    # Smoothness on T/h where the image is not changing much; keeps the toy model
    # from hallucinating high-frequency source background as material.
    dx = torch.abs(pred[:, :4, :, 1:] - pred[:, :4, :, :-1]).mean()
    dy = torch.abs(pred[:, :4, 1:, :] - pred[:, :4, :-1, :]).mean()
    return map_loss + 0.12 * shadow_loss + 0.015 * (dx + dy)


def tensor_from_image(image, device):
    x = torch.tensor(np.transpose(image, (2, 0, 1))[None, ...], dtype=torch.float32, device=device)
    return x


def predict_full(model, sample, device):
    model.eval()
    inp = model_input(sample, sample.image)
    with torch.no_grad():
        pred = model(tensor_from_image(inp, device))[0].cpu().numpy()
    pred = np.transpose(pred, (1, 2, 0))
    T = np.clip(pred[..., :3], 0, 1)
    h = np.clip(pred[..., 3], 0, 1)
    shadow = np.clip(pred[..., 4], 0, 1)
    return T, h, shadow


def mae255(a, b, valid):
    return preview_eval.srgb_mae255(a, b, valid)


def p95255(a, b, valid):
    return preview_eval.srgb_p95255(a, b, valid)


def evaluate(model, records, device, size):
    rows = []
    by_name = {}
    for r in records:
        by_name.setdefault(r.name, {})[r.kind] = r

    contacts = []
    for name, pair in sorted(by_name.items()):
        if "clean" not in pair:
            continue
        clean = pair["clean"]
        shadow = pair.get("shadow")
        H, W = clean.image.shape[:2]
        bg = preview_eval.preview_background(H, W)
        gtT = clean.target[..., :3]
        gth = clean.target[..., 3]
        target_preview = preview_eval.render_preview(gtT, gth, bg)

        glass_class = CLASS_MAP[clean.class_label]
        classical_clean = extract.extract_maps(clean.image.astype(np.float64), glass_class, mark_region="none")
        classical_preview = preview_eval.render_preview(classical_clean["T"], classical_clean["h"], bg)
        raw_preview = preview_eval.exposure_match(clean.image.astype(np.float64), target_preview, clean.valid)

        Tn, hn, shadow_pred = predict_full(model, clean, device)
        neural_preview = preview_eval.render_preview(Tn, hn, bg)

        row = {
            "sample": name,
            "class_label": clean.class_label,
            "raw_mae": mae255(raw_preview, target_preview, clean.valid),
            "classical_mae": mae255(classical_preview, target_preview, clean.valid),
            "neural_mae": mae255(neural_preview, target_preview, clean.valid),
            "raw_p95": p95255(raw_preview, target_preview, clean.valid),
            "classical_p95": p95255(classical_preview, target_preview, clean.valid),
            "neural_p95": p95255(neural_preview, target_preview, clean.valid),
            "T_mae": float(np.abs(Tn - gtT)[clean.valid[..., None] * np.ones((1, 1, 3), bool)].mean()),
            "h_mae": float(np.abs(hn - gth)[clean.valid].mean()),
        }

        if shadow is not None:
            classical_shadow = extract.extract_maps(shadow.image.astype(np.float64), glass_class, mark_region="none")
            classical_shadow_preview = preview_eval.render_preview(classical_shadow["T"], classical_shadow["h"], bg)
            Ts, hs, shadow_pred_s = predict_full(model, shadow, device)
            neural_shadow_preview = preview_eval.render_preview(Ts, hs, bg)
            raw_shadow_preview = preview_eval.exposure_match(shadow.image.astype(np.float64), target_preview, clean.valid)
            row.update({
                "raw_shadow_gap": mae255(raw_preview, raw_shadow_preview, clean.valid),
                "classical_shadow_gap": mae255(classical_preview, classical_shadow_preview, clean.valid),
                "neural_shadow_gap": mae255(neural_preview, neural_shadow_preview, clean.valid),
                "shadow_mask_iou": shadow_iou(shadow_pred_s > 0.5, shadow.target[..., 4] > 0.5, clean.valid),
            })
        rows.append(row)
        contacts.append(contact_row(clean, target_preview, raw_preview, classical_preview, neural_preview,
                                    shadow_pred, row))
    return rows, contacts


def shadow_iou(pred, target, valid):
    pred = pred & valid
    target = target & valid
    union = pred | target
    if not union.any():
        return None
    return float((pred & target).sum() / union.sum())


def image_tile(img, label, linear=True, gain=1.0, size=160):
    arr = np.clip(img * gain, 0, 1)
    if linear:
        arr = extract.lin_to_srgb(arr)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    arr = cv2.resize((arr * 255).astype(np.uint8), (size, size), interpolation=cv2.INTER_AREA)
    im = Image.fromarray(arr)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(label), 16], fill=(0, 0, 0))
    d.text((4, 2), label, fill=(255, 255, 90))
    return np.asarray(im)


def contact_row(sample, target, raw, classical, neural, shadow_pred, metrics):
    err_classical = np.abs(extract.lin_to_srgb(np.clip(classical, 0, 1)) -
                           extract.lin_to_srgb(np.clip(target, 0, 1)))
    err_neural = np.abs(extract.lin_to_srgb(np.clip(neural, 0, 1)) -
                        extract.lin_to_srgb(np.clip(target, 0, 1)))
    cols = [
        image_tile(sample.image, "input"),
        image_tile(target, "target"),
        image_tile(raw, "raw"),
        image_tile(classical, "classical"),
        image_tile(neural, "glassnet"),
        image_tile(err_classical, "class err x4", linear=False, gain=4.0),
        image_tile(err_neural, "net err x4", linear=False, gain=4.0),
        image_tile(shadow_pred, "shadow pred", linear=False),
    ]
    row = np.concatenate([np.pad(c, ((2, 18), (2, 2), (0, 0)), constant_values=20) for c in cols], axis=1)
    im = Image.fromarray(row)
    ImageDraw.Draw(im).text(
        (4, 162),
        f"{metrics['sample']} raw={metrics['raw_mae']:.1f} class={metrics['classical_mae']:.1f} "
        f"net={metrics['neural_mae']:.1f}",
        fill=(225, 225, 225),
    )
    return np.asarray(im)


def aggregate(rows):
    by = {}
    for r in rows:
        by.setdefault(r["class_label"], []).append(r)
    out = {}
    for label, rs in sorted(by.items()):
        out[label] = {
            "n": len(rs),
            "raw_mae": float(np.mean([r["raw_mae"] for r in rs])),
            "classical_mae": float(np.mean([r["classical_mae"] for r in rs])),
            "neural_mae": float(np.mean([r["neural_mae"] for r in rs])),
            "raw_shadow_gap": float(np.mean([r.get("raw_shadow_gap", np.nan) for r in rs])),
            "classical_shadow_gap": float(np.mean([r.get("classical_shadow_gap", np.nan) for r in rs])),
            "neural_shadow_gap": float(np.mean([r.get("neural_shadow_gap", np.nan) for r in rs])),
            "T_mae": float(np.mean([r["T_mae"] for r in rs])),
            "h_mae": float(np.mean([r["h_mae"] for r in rs])),
        }
    return out


def write_table(per_recipe, path):
    lines = [
        "| recipe | n | raw MAE | classical MAE | GlassNet MAE | raw shadow gap | classical shadow gap | GlassNet shadow gap | T MAE | h MAE |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for label, v in per_recipe.items():
        lines.append(
            f"| {label} | {v['n']} | {v['raw_mae']:.1f} | {v['classical_mae']:.1f} | "
            f"{v['neural_mae']:.1f} | {v['raw_shadow_gap']:.1f} | "
            f"{v['classical_shadow_gap']:.1f} | {v['neural_shadow_gap']:.1f} | "
            f"{v['T_mae']:.3f} | {v['h_mae']:.3f} |"
        )
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.path.join(HERE, "synthetic_data"))
    ap.add_argument("--out", default=os.path.join(HERE, "results", "glassnet_zero"))
    ap.add_argument("--size", type=int, default=384)
    ap.add_argument("--crop", type=int, default=96)
    ap.add_argument("--steps", type=int, default=900)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--base", type=int, default=20)
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(max(1, min(6, os.cpu_count() or 1)))
    device = torch.device("cpu")

    os.makedirs(args.out, exist_ok=True)
    records, skipped = load_records(args.data, args.size)
    train, test, holdout = split_records(records)
    if not train or not test:
        raise SystemExit("Need at least one train and one test record.")
    print(f"records={len(records)} train={len(train)} test={len(test)} holdout={holdout} skipped={skipped}")

    model = TinyGlassNet(base=args.base, in_ch=3 + len(CLASS_LABELS)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    losses = []
    for step in range(1, args.steps + 1):
        model.train()
        x, y, valid = random_crop_batch(train, args.batch, args.crop, device)
        pred = model(x)
        loss = loss_fn(pred, y, valid)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        losses.append(float(loss.item()))
        if step == 1 or step % max(1, args.steps // 10) == 0:
            recent = np.mean(losses[-min(len(losses), 40):])
            print(f"step {step:04d}/{args.steps} loss={recent:.4f}")

    rows, contacts = evaluate(model, test, device, args.size)
    per_recipe = aggregate(rows)
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump({
            "args": vars(args),
            "class_labels": CLASS_LABELS,
            "holdout_samples": holdout,
            "skipped": skipped,
            "n_train_records": len(train),
            "n_test_records": len(test),
            "loss_tail_mean": float(np.mean(losses[-min(50, len(losses)):])),
            "per_recipe": per_recipe,
            "per_sample": rows,
        }, f, indent=2)
    table = write_table(per_recipe, os.path.join(args.out, "summary_table.md"))
    if contacts:
        width = max(c.shape[1] for c in contacts)
        padded = [np.pad(c, ((0, 0), (0, width - c.shape[1]), (0, 0)), constant_values=20)
                  for c in contacts]
        Image.fromarray(np.concatenate(padded, axis=0)).save(os.path.join(args.out, "contact_holdout.jpg"), quality=84)
    torch.save(model.state_dict(), os.path.join(args.out, "glassnet_zero.pt"))
    print("\n" + table)
    print(f"\noutputs in {args.out}")


if __name__ == "__main__":
    main()
