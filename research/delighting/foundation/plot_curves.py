#!/usr/bin/env python3
"""055 — per-channel training curves from train_log.jsonl.

Small multiples, one panel per supervised channel, because the channels live on
different scales (T latent-MSE ~1.0 vs h ~0.2) and a shared or dual axis would make
every panel but one unreadable. Each panel carries a single series (raw, thin) plus
its running mean (heavier, same hue), so identity never depends on colour alone —
the panel title names the channel.

Headline reads:
  * T must DECREASE. Under the report-040 severed-gradient bug this curve was
    bit-for-bit CONSTANT, so a moving T curve is the mechanical validation that the
    latent-space supervision actually reaches the LoRA.
  * sigma_s must DECREASE. It drifted UP in the 048 random-init smoke; if it climbs
    on the real backbone too, that is a finding, not a nuisance to smooth over.

Usage: plot_curves.py <train_log.jsonl> --out results/055/curves.png
"""
import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

INK = "#1c2024"
MUTED = "#8b949e"
GRID = "#e6e8eb"
RAW = "#9dc3e6"      # light step
TREND = "#1f6fb2"    # dark step of the same hue

CHANNELS = [("T", "T  (latent MSE) — the 040 regression check"),
            ("sigma_s", "sigma_s  (scatter radius) — the 048 drift check"),
            ("h", "h  (haze fraction)"),
            ("B", "B  (background layer, log1p L1)"),
            ("shadow", "shadow  (BCE)"),
            ("mark", "mark  (BCE)"),
            ("conf", "conf  (|conf - exp(-err/tau)|)"),
            ("total", "total  (weighted sum)")]


def running(y, w):
    if len(y) < 3:
        return y
    w = max(3, min(w, len(y) // 3))
    k = np.ones(w) / w
    return np.convolve(y, k, mode="valid")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="055 train-once pilot — per-channel loss")
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(args.jsonl) if l.strip()]
    recs.sort(key=lambda r: r["step"])
    step = np.array([r["step"] for r in recs])
    print(f"{len(recs)} logged steps, {step[0]}..{step[-1]}")

    fig, axes = plt.subplots(4, 2, figsize=(11, 12), sharex=True)
    fig.suptitle(f"{args.title}\n{len(recs)} logged steps · "
                 f"final step {int(step[-1])} · marigold-iid LoRA+AuxHead",
                 fontsize=12, color=INK, y=0.995)

    for ax, (key, label) in zip(axes.ravel(), CHANNELS):
        y = np.array([r[key] for r in recs], float)
        ax.plot(step, y, color=RAW, lw=1.0, zorder=2)
        w = max(3, len(y) // 25)
        t = running(y, w)
        ax.plot(step[len(step) - len(t):], t, color=TREND, lw=2.0, zorder=3)
        ax.set_title(label, fontsize=9.5, color=INK, loc="left", pad=6)
        ax.grid(True, color=GRID, lw=0.8, zorder=0)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=8)
        # first-vs-last annotation: the direction of travel is the whole point
        n0 = max(1, len(y) // 20)
        a, b = float(y[:n0].mean()), float(y[-n0:].mean())
        d = "down" if b < a else "UP"
        ax.annotate(f"first {a:.4f} -> last {b:.4f}  ({d} {abs(b-a)/max(a,1e-9)*100:.0f}%)",
                    xy=(0.98, 0.94), xycoords="axes fraction", ha="right", va="top",
                    fontsize=8, color=INK if b < a else "#b4341f")
    for ax in axes[-1]:
        ax.set_xlabel("step", fontsize=9, color=MUTED)

    fig.tight_layout(rect=[0, 0, 1, 0.975])
    fig.savefig(args.out, dpi=140, facecolor="white")
    print("wrote", args.out)

    # the two headline directions, as text, for the report
    for key in ("T", "sigma_s"):
        y = np.array([r[key] for r in recs], float)
        n0 = max(1, len(y) // 20)
        print(f"  {key}: first5%={y[:n0].mean():.5f} last5%={y[-n0:].mean():.5f} "
              f"min={y.min():.5f} n_distinct={len(np.unique(y))}")


if __name__ == "__main__":
    main()
