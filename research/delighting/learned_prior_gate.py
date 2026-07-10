#!/usr/bin/env python3
"""Learn a tiny prior-assistance gate from catalog negatives + synthetic leaks.

Catalog sheets are treated as "real material variation" negatives. We create
positive examples by adding broad low-frequency lighting/background contamination
to those same sheets, then train a logistic classifier over texture statistics.

This is not a final model. It is a cheap test of whether a learned
`prior_strength` head is plausible before spending effort on image-level neural
training.
"""
import argparse
import json
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_AUDIT = os.path.join(HERE, "results", "catalog_texture_audit", "metrics.json")
OUT = os.path.join(HERE, "results", "learned_prior_gate")

import catalog_texture_audit as audit_lib  # noqa: E402
import extract as ex  # noqa: E402


FEATURES = (
    "lum_cv",
    "lowfreq_cv",
    "highfreq_std",
    "highfreq_p95",
    "chroma_mad",
    "sat_mean",
    "low_to_high",
    "low_minus_chroma",
    "z_lum",
    "z_lowfreq",
    "z_chroma",
    "z_detail",
)


def robust_z(value, stats, key):
    s = stats[key]
    scale = max(s["p75"] - s["p25"], 1e-6)
    return float(np.clip((value - s["median"]) / scale, -8.0, 8.0))


def feature_row(metrics, category_stats):
    low = metrics["lowfreq_cv"]
    high = metrics["highfreq_std"]
    chroma = metrics["chroma_mad"]
    row = np.array([
        np.log1p(metrics["lum_cv"]),
        np.log1p(low),
        np.log1p(high),
        np.log1p(metrics["highfreq_p95"]),
        np.log1p(chroma),
        metrics["sat_mean"],
        np.log1p(low / max(high, 1e-5)),
        np.log1p(max(low - 1.8 * chroma, 0.0)),
        robust_z(metrics["lum_cv"], category_stats, "lum_cv"),
        robust_z(low, category_stats, "lowfreq_cv"),
        robust_z(chroma, category_stats, "chroma_mad"),
        robust_z(high, category_stats, "highfreq_std"),
    ], dtype=np.float64)
    return np.nan_to_num(row, nan=0.0, posinf=8.0, neginf=-8.0)


def contaminate(rgb01, seed):
    rng = np.random.default_rng(seed)
    h, w = rgb01.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    xx = xx / max(w - 1, 1) - 0.5
    yy = yy / max(h - 1, 1) - 0.5

    angle = rng.uniform(0, np.pi * 2)
    grad = np.cos(angle) * xx + np.sin(angle) * yy
    grad *= rng.uniform(0.45, 0.95)

    low = rng.normal(0, 1, (7, 7)).astype(np.float32)
    low = cv2.resize(low, (w, h), interpolation=cv2.INTER_CUBIC)
    low = cv2.GaussianBlur(low, (0, 0), max(12, min(h, w) / 9))
    low = low / (low.std() + 1e-6)
    field = np.exp(grad + rng.uniform(0.12, 0.36) * low)

    # Smooth color cast, like lawn/sky/window tint bleeding through clear glass.
    tint_a = rng.normal(0, 0.18, 3)
    tint_b = rng.normal(0, 0.12, 3)
    tint = np.exp(tint_a[None, None, :] + tint_b[None, None, :] * yy[..., None])

    lin = ex.srgb_to_lin(rgb01)
    aug = lin * field[..., None] * tint

    # Add a broad transmitted background component to mimic cathedral leakage.
    bg_color = np.array([rng.uniform(0.15, 0.55), rng.uniform(0.30, 0.85), rng.uniform(0.18, 0.70)])
    bg_strength = rng.uniform(0.04, 0.16)
    aug = (1 - bg_strength) * aug + bg_strength * bg_color[None, None, :] * field[..., None]
    return np.clip(ex.lin_to_srgb(np.clip(aug, 0, 1)), 0, 1)


def auc_score(y, score):
    y = np.asarray(y, dtype=np.int32)
    score = np.asarray(score, dtype=np.float64)
    order = np.argsort(score)
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(score) + 1)
    pos = y == 1
    n_pos = int(pos.sum())
    n_neg = int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def train_logistic(X, y, train_mask, steps=2200, lr=0.025):
    mu = X[train_mask].mean(axis=0)
    sigma = X[train_mask].std(axis=0) + 1e-6
    Xn = (X - mu) / sigma
    Xb = np.concatenate([np.ones((len(Xn), 1)), Xn], axis=1)
    w = np.zeros(Xb.shape[1], dtype=np.float64)
    Xt = Xb[train_mask]
    yt = y[train_mask]
    for _ in range(steps):
        logits = np.clip(np.sum(Xt * w[None, :], axis=1), -30, 30)
        p = 1 / (1 + np.exp(-logits))
        grad = np.mean(Xt * (p - yt)[:, None], axis=0)
        grad[1:] += 6e-3 * w[1:]
        norm = np.linalg.norm(grad)
        if norm > 5:
            grad *= 5 / norm
        w -= lr * grad
        w = np.clip(w, -12, 12)
    probs = 1 / (1 + np.exp(-np.clip(np.sum(Xb * w[None, :], axis=1), -30, 30)))
    return w, mu, sigma, probs


def score_metrics(metrics, category_stats, w, mu, sigma):
    x = feature_row(metrics, category_stats)
    xn = (x - mu) / sigma
    xb = np.concatenate([[1.0], xn])
    return float(1 / (1 + np.exp(-np.clip(np.sum(xb * w), -40, 40))))


def load_registry_by_id(registry_path):
    registry = json.load(open(registry_path))
    return {item["id"]: item for item in registry}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default=DEFAULT_AUDIT)
    ap.add_argument("--max-images", type=int, default=900)
    ap.add_argument("--seed", type=int, default=20260709)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    audit = json.load(open(args.audit))
    registry_path = audit["registry"]
    public_root = audit_lib.public_root_for_registry(registry_path)
    registry_by_id = load_registry_by_id(registry_path)

    rng = np.random.default_rng(args.seed)
    rows = list(audit["catalog_rows"])
    rng.shuffle(rows)
    rows = rows[:min(args.max_images, len(rows))]

    X, y, groups, meta = [], [], [], []
    for idx, row in enumerate(rows):
        item = registry_by_id[row["id"]]
        rgb, _ = audit_lib.load_catalog_image(public_root, item, max_dim=320)
        clean_metrics = audit_lib.texture_metrics_from_rgb01(rgb)
        leak_metrics = audit_lib.texture_metrics_from_rgb01(contaminate(rgb, args.seed + idx))
        for label, metrics in ((0, clean_metrics), (1, leak_metrics)):
            X.append(feature_row(metrics, audit["category_summary"][row["category"]]))
            y.append(label)
            groups.append(row["id"])
            meta.append({
                "id": row["id"],
                "category": row["category"],
                "label": label,
                **metrics,
            })

    X = np.stack(X)
    y = np.asarray(y, dtype=np.float64)
    group_ids = np.array(groups)
    unique = np.array(sorted(set(groups)))
    rng.shuffle(unique)
    test_groups = set(unique[:max(1, int(0.2 * len(unique)))])
    test_mask = np.array([g in test_groups for g in group_ids])
    train_mask = ~test_mask

    w, mu, sigma, probs = train_logistic(X, y, train_mask)
    train_auc = auc_score(y[train_mask], probs[train_mask])
    test_auc = auc_score(y[test_mask], probs[test_mask])
    test_pred = probs[test_mask] > 0.5
    test_acc = float((test_pred == y[test_mask]).mean())

    clean_test = test_mask & (y == 0)
    leak_test = test_mask & (y == 1)
    clean_fp_050 = float((probs[clean_test] > 0.5).mean())
    clean_fp_070 = float((probs[clean_test] > 0.7).mean())
    leak_tp_050 = float((probs[leak_test] > 0.5).mean())
    leak_tp_070 = float((probs[leak_test] > 0.7).mean())

    suncatcher_scores = []
    for row in audit["suncatcher_conditions"]:
        suncatcher_scores.append({
            "id": row["id"],
            "score": score_metrics(row, audit["category_summary"]["Textured/Baroque"], w, mu, sigma),
            "lowfreq_cv": row["lowfreq_cv"],
            "highfreq_std": row["highfreq_std"],
            "chroma_mad": row["chroma_mad"],
        })

    coef = [{"feature": "bias", "weight": float(w[0])}]
    coef.extend({"feature": name, "weight": float(weight)} for name, weight in zip(FEATURES, w[1:]))
    payload = {
        "audit": args.audit,
        "n_groups": len(unique),
        "n_train_groups": int(len(unique) - len(test_groups)),
        "n_test_groups": int(len(test_groups)),
        "train_auc": train_auc,
        "test_auc": test_auc,
        "test_accuracy_050": test_acc,
        "clean_false_positive_050": clean_fp_050,
        "clean_false_positive_070": clean_fp_070,
        "leak_true_positive_050": leak_tp_050,
        "leak_true_positive_070": leak_tp_070,
        "coefficients": coef,
        "suncatcher_scores": suncatcher_scores,
    }
    with open(os.path.join(OUT, "learned_gate_metrics.json"), "w") as f:
        json.dump(payload, f, indent=2)
    write_summary(payload)

    print(f"test_auc={test_auc:.3f} acc={test_acc:.3f} fp50={clean_fp_050:.3f} tp50={leak_tp_050:.3f}")
    for row in suncatcher_scores:
        print(f"{row['id']:14s} {row['score']:.2f}")
    print("wrote", OUT)


def write_summary(payload):
    lines = [
        "# Learned prior gate",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| train AUC | {payload['train_auc']:.3f} |",
        f"| test AUC | {payload['test_auc']:.3f} |",
        f"| test accuracy @0.50 | {payload['test_accuracy_050']:.3f} |",
        f"| clean false positive @0.50 | {payload['clean_false_positive_050']:.3f} |",
        f"| clean false positive @0.70 | {payload['clean_false_positive_070']:.3f} |",
        f"| synthetic leak true positive @0.50 | {payload['leak_true_positive_050']:.3f} |",
        f"| synthetic leak true positive @0.70 | {payload['leak_true_positive_070']:.3f} |",
        "",
        "## Suncatcher scores",
        "",
        "| sample | learned score | lowfreq_cv | highfreq_std | chroma_mad |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in payload["suncatcher_scores"]:
        lines.append(
            f"| {row['id']} | {row['score']:.2f} | {row['lowfreq_cv']:.3f} | "
            f"{row['highfreq_std']:.3f} | {row['chroma_mad']:.3f} |"
        )
    lines.extend([
        "",
        "## Coefficients",
        "",
        "| feature | weight |",
        "|---|---:|",
    ])
    for row in payload["coefficients"]:
        lines.append(f"| {row['feature']} | {row['weight']:.3f} |")
    lines.append("")
    with open(os.path.join(OUT, "learned_gate_summary.md"), "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
