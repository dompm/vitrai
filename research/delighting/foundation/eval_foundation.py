#!/usr/bin/env python3
"""Iteration 038 / deliverable 4 — EVAL a trained FoundationDelighter through the
FROZEN instruments and emit the EVAL_PROTOCOL baseline-ladder table.

Runs a trained checkpoint over the held-out-IDENTITY synthetic test split (seed%5==0
/ 800-812, enforced by dataset.py) and scores it with the SAME callables the frozen
protocol uses, so the new-model row is directly comparable to the frozen reference row:

  * PRIMARY (family 1) cross-capture consistency: model's per-capture T predictions of
    the SAME (recipe,seed) glass under different lightings must agree — pairwise mean
    |T_i - T_j| (linear T units, the eval_cross_lighting / EVAL_PROTOCOL §5 convention).
  * GT accuracy: T-MAE / h-MAE vs authored gt (eval_synthetic convention).
  * texture preservation (family 2): eval_texture_preservation.evaluate(gt_T, pred_T)
    — fine grad-corr / retained-energy / FCS. Retained-energy is the FLATTENING gate:
    the frozen 8σ-blur control collapses it to 0.03 vs classical 1.27, so a model that
    drives it toward zero has flattened (the sub-floor violation, §1a).
  * calibration (family 4): Spearman(conf, -err) + ECE at τ=8/255 (§1d).

Baseline ladder (§4): raw / exposure-norm / quotient / frozen-classical / GlassNet rows
are read from the FROZEN reference numbers (EVAL_PROTOCOL §5, reports 026/034); only the
new-model row is computed here. Continuation gate (consultant plan): the model must beat
BOTH classical AND quotient on the PRIMARY criterion on held-out identities WITHOUT
firing the flattening sub-floor flag.

Usage:
  eval_foundation.py --ckpt results/038_smoke/adapter.pt --backbone tiny \
                     --data <render_022> --out results/038_smoke/eval
"""
import argparse
import json
import os
import sys

import numpy as np
import torch

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402  (module-level: σ_s structured-relight helpers, report 053)

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, DELIGHT)
from dataset import GlassDelightDataset  # noqa: E402
from backbone import FoundationDelighter  # noqa: E402
import eval_texture_preservation as etp  # noqa: E402  (frozen family-2 instrument)

# FROZEN reference rows (EVAL_PROTOCOL.md §5 / reports 026, 034). Not recomputed.
FROZEN = {
    # family 1 — synthetic cross-lighting T-dispersion macro (lower=more consistent)
    "invariance_T": {"raw": 0.0946, "exposure_norm": None, "quotient": 0.0815,
                     "classical": 0.0932, "glassnet": None},
    # family 3/GT — synthetic accuracy (classical macro), for context
    "T_mae": {"raw": None, "quotient": None, "classical": 0.108, "glassnet": None},
    "h_mae": {"classical": 0.155},
    # family 2 — texture preservation (macro fine retained-energy; flatten control=0.03)
    "retained_energy": {"classical": 1.27, "quotient": 1.24, "flatten_control": 0.03},
    "fcs": {"classical": 0.509, "quotient": 0.589, "flatten_control": 0.00},
}
# gate thresholds (EVAL_PROTOCOL §1a/§1b). Fine retained-energy must sit in a healthy
# band: too LOW = flattening (the 8σ-blur control is 0.03; classical 1.27); too HIGH =
# texture HALLUCINATION (report 012's "invented not measured" — a map that injects far
# more high-freq than the authored gt_T has). Classical/quotient live ~1.2-1.3.
FLATTEN_RETAINED_FLOOR = 0.5
HALLUCINATE_RETAINED_CEIL = 2.5


def _to_t(a, device):
    return torch.from_numpy(a).permute(2, 0, 1)[None].float().to(device)


def predict(model, rec, device, work=512):
    """Model T,h,conf for one sample at working resolution `work` (max dim)."""
    import cv2
    photo = rec["photo"]
    H, W = photo.shape[:2]
    s = work / max(H, W)
    wh = (max(8, int(round(W * s))), max(8, int(round(H * s))))
    ph = cv2.resize(np.clip(photo, 0, None), wh, interpolation=cv2.INTER_AREA)
    # pad to /8 for the VAE
    ph8 = _pad8(ph)
    with torch.no_grad():
        out = model(_to_t(ph8, device).clamp(0, None))
    def np_(x, ch):
        a = x[0].permute(1, 2, 0).float().cpu().numpy()
        return a[:ph.shape[0], :ph.shape[1], :ch]
    T = np_(out["T"], 3)
    h = np_(out["h"], 1)
    conf = np_(out["conf"], 1)
    # report 053 (048 owed): σ_s head, scored below (MAE + structured-relight L1).
    sigma_s = np_(out["sigma_s"], 1) if "sigma_s" in out else None
    # resize GT to the same working grid
    gtT = cv2.resize(rec["T"], wh, interpolation=cv2.INTER_AREA)
    gth = cv2.resize(rec["h"][..., 0], wh, interpolation=cv2.INTER_AREA)[..., None]
    gtsig = cv2.resize(rec["sigma_s"][..., 0], wh, interpolation=cv2.INTER_AREA)[..., None]
    valid = cv2.resize(rec["valid"][..., 0], wh, interpolation=cv2.INTER_NEAREST)[..., None] > 0.5
    return {"T": T, "h": h, "conf": conf, "sigma_s": sigma_s,
            "gtT": gtT[:H0(ph), :W0(ph)], "gth": gth, "gt_sigma_s": gtsig,
            "has_sigma_s": bool(rec.get("has_sigma_s", False)),
            "valid": valid, "recipe": rec["recipe"], "seed": rec["seed"]}


def H0(a):
    return a.shape[0]


def W0(a):
    return a.shape[1]


def _pad8(a):
    H, W = a.shape[:2]
    ph = (8 - H % 8) % 8
    pw = (8 - W % 8) % 8
    if ph or pw:
        a = np.pad(a, ((0, ph), (0, pw), (0, 0)), mode="reflect")
    return a


def _spearman(x, y):
    try:
        from scipy.stats import spearmanr
        r = spearmanr(x, y).correlation
        return float(r) if r == r else 0.0
    except Exception:
        xr = np.argsort(np.argsort(x)).astype(np.float64)
        yr = np.argsort(np.argsort(y)).astype(np.float64)
        xr -= xr.mean(); yr -= yr.mean()
        d = np.sqrt((xr * xr).sum() * (yr * yr).sum())
        return float((xr * yr).sum() / d) if d > 0 else 0.0


# ------------------------------------------------ σ_s structured-relight (report 053 / 048 owed)
# EVAL_PROTOCOL §1c + the report-045/046 methodology: σ_s (haze-driven subsurface-scatter
# radius) is scored not just by map MAE but by its EFFECT on a STRUCTURED backdrop — the exact
# gap report 045 found the uniform-backlight validate gate cannot see. σ_s drives a per-pixel
# roughness-mip blur of a checker (report 045 `variable_blur`, sigma = SIGMA_MAX·σ_s); we relight
# the checker with the PREDICTED σ_s map and with the GT σ_s map and score the sRGB L1 between
# the two relights. Isolated to σ_s: same fixed checker + same SIGMA_MAX for both, so the score
# reflects only how faithfully the predicted scatter field reproduces the GT scatter field's
# structured-background softening. (Lower = better; 0 = identical relight.)
SIGMA_RELIGHT_MAX_PX = 24.0
_SIGMA_LEVELS = [0.0, 2.0, 4.0, 8.0, 16.0, 32.0]


def _checker(H, W, tiles=8):
    """Warm-white / cool-dark checker (report 045's 0.2 m squares), scene-linear HxWx3."""
    ts = max(4, min(H, W) // tiles)
    yy, xx = np.mgrid[0:H, 0:W]
    board = ((xx // ts + yy // ts) % 2).astype(np.float32)
    warm = np.array([0.85, 0.80, 0.62], np.float32)   # warm white
    cool = np.array([0.06, 0.08, 0.12], np.float32)   # cool dark
    return board[..., None] * warm + (1.0 - board[..., None]) * cool


def _blur_stack(B, sigmas):
    out = []
    for sg in sigmas:
        out.append(B if sg <= 0 else cv2.GaussianBlur(B, (0, 0), sigmaX=float(sg),
                                                       borderType=cv2.BORDER_REPLICATE))
    return np.stack(out, 0)


def _variable_blur(stack, sigmas, sigma_map):
    """Per-pixel lerp between the two nearest blur levels (report 045 recon_bench)."""
    sig = np.clip(sigma_map, sigmas[0], sigmas[-1])
    idx = np.clip(np.searchsorted(sigmas, sig, side="right") - 1, 0, len(sigmas) - 2)
    lo = np.array(sigmas)[idx]; hi = np.array(sigmas)[idx + 1]
    w = np.where(hi > lo, (sig - lo) / np.maximum(hi - lo, 1e-9), 0.0)[..., None]
    H, W = sig.shape
    rows, cols = np.mgrid[0:H, 0:W]
    return stack[idx, rows, cols] * (1 - w) + stack[idx + 1, rows, cols] * w


def _relight_checker(sigma_map, checker, stack):
    return _variable_blur(stack, _SIGMA_LEVELS, SIGMA_RELIGHT_MAX_PX * np.clip(sigma_map, 0, 1))


def sigma_s_relight_l1(pred_sigma, gt_sigma, valid):
    """sRGB L1 (0-255) between the checker relit by predicted σ_s vs by GT σ_s. Both maps are
    HxW (single channel). `valid` masks marks. Returns (l1_255, gt_vs_uniform_255) where the
    second is the GT-relight vs a NO-SCATTER (σ_s=0) relight — a per-sample scale telling how
    much structured softening the GT σ_s actually induces (a near-zero scale = a see-through
    sample where σ_s barely matters, read the L1 against it)."""
    H, W = gt_sigma.shape[:2]
    checker = _checker(H, W)
    stack = _blur_stack(checker, _SIGMA_LEVELS)
    from extract import lin_to_srgb
    relit_pred = lin_to_srgb(np.clip(_relight_checker(pred_sigma, checker, stack), 0, 1))
    relit_gt = lin_to_srgb(np.clip(_relight_checker(gt_sigma, checker, stack), 0, 1))
    relit_zero = lin_to_srgb(np.clip(checker, 0, 1))
    v = valid.astype(bool)
    if v.ndim == 3:
        v = v[..., 0]
    l1 = float(np.abs(relit_pred - relit_gt)[v].mean() * 255.0)
    scale = float(np.abs(relit_gt - relit_zero)[v].mean() * 255.0)
    return l1, scale


def calibration(preds, tau=8 / 255.0, nbins=10):
    """§1d: Spearman(conf, -err) + ECE at τ. Pooled over all test pixels (subsampled)."""
    confs, errs = [], []
    for p in preds:
        v = p["valid"][..., 0]
        err = np.abs(p["T"] - p["gtT"]).mean(-1)[v]
        cf = p["conf"][..., 0][v]
        confs.append(cf); errs.append(err)
    conf = np.concatenate(confs); err = np.concatenate(errs)
    if len(conf) > 200000:
        idx = np.random.default_rng(0).choice(len(conf), 200000, replace=False)
        conf, err = conf[idx], err[idx]
    sp = _spearman(conf, -err)
    acc = (err < tau).astype(np.float64)
    ece = 0.0
    for b in range(nbins):
        lo, hi = b / nbins, (b + 1) / nbins
        m = (conf >= lo) & (conf < hi if b < nbins - 1 else conf <= hi)
        if m.sum() == 0:
            continue
        ece += (m.mean()) * abs(acc[m].mean() - conf[m].mean())
    return {"spearman_conf_negerr": sp, "ece_tau8": float(ece), "n_pixels": int(len(conf))}


def evaluate(ckpt, backbone, data_roots, out_dir, device=None, work=512, cache_only=False):
    os.makedirs(out_dir, exist_ok=True)
    device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
    model = FoundationDelighter(backbone=backbone, freeze_backbone=True, cache_only=cache_only).to(device)
    model.load_adapter(ckpt, map_location=device)
    model.eval()

    ds = GlassDelightDataset(data_roots, split="test", augment=False, input_variant="without")
    print(f"[eval] {len(ds)} HELD-OUT test samples (seed%5==0 / 800-812) | backbone={backbone}")
    preds = []
    for i in range(len(ds)):
        rec = ds.load_full(i, variant="without")
        if rec is None:
            continue
        try:
            preds.append(predict(model, rec, device, work))
            print(f"  {preds[-1]['recipe']:22s} seed{preds[-1]['seed']}")
        except RuntimeError as e:
            print(f"  [skip {rec['recipe']} seed{rec['seed']}] {str(e)[:80]}")
        if device == "mps":
            torch.mps.empty_cache()

    # --- GT accuracy + texture family 2 (per sample) ---
    T_maes, h_maes, retained, fcs, fine_corr = [], [], [], [], []
    sig_maes, sig_relight_l1, sig_relight_scale = [], [], []
    for p in preds:
        v = p["valid"][..., 0]
        T_maes.append(float(np.abs(p["T"] - p["gtT"])[v].mean()))
        h_maes.append(float(np.abs(p["h"] - p["gth"])[v].mean()))
        tex = etp.evaluate(p["gtT"], p["T"], mask=v)          # ref=authored gt_T, test=pred T
        retained.append(tex["mgp"]["fine_retained_energy"])
        fine_corr.append(tex["mgp"]["fine_grad_corr"])
        if tex["fcs"]["survival"] is not None:
            fcs.append(tex["fcs"]["survival"])
        # report 053 / 048-owed: σ_s MAE + structured-checker relight L1 (held-out identities
        # only). Scored where the model emits σ_s AND the sample carries a supervised gt_σ_s.
        if p.get("sigma_s") is not None and p.get("has_sigma_s"):
            sig_maes.append(float(np.abs(p["sigma_s"] - p["gt_sigma_s"])[v].mean()))
            l1, scale = sigma_s_relight_l1(p["sigma_s"][..., 0], p["gt_sigma_s"][..., 0], v)
            sig_relight_l1.append(l1)
            sig_relight_scale.append(scale)

    # --- PRIMARY family 1: cross-capture consistency over same-(recipe,seed) groups ---
    groups = {}
    for p in preds:
        groups.setdefault((p["recipe"], p["seed"]), []).append(p)
    per_recipe_inv = {}
    for (recipe, seed), members in groups.items():
        if len(members) < 2:
            continue
        diffs = []
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                va = members[a]["valid"][..., 0] & members[b]["valid"][..., 0]
                if va.sum() == 0:
                    continue
                diffs.append(float(np.abs(members[a]["T"] - members[b]["T"])[va].mean()))
        if diffs:
            per_recipe_inv.setdefault(recipe, []).extend(diffs)
    recipe_inv = {r: float(np.mean(v)) for r, v in per_recipe_inv.items()}
    inv_macro = float(np.mean(list(recipe_inv.values()))) if recipe_inv else None

    cal = calibration(preds)

    model_row = {
        "invariance_T": inv_macro,
        "T_mae": float(np.mean(T_maes)), "h_mae": float(np.mean(h_maes)),
        "retained_energy": float(np.mean(retained)), "fine_grad_corr": float(np.mean(fine_corr)),
        "fcs": float(np.mean(fcs)) if fcs else None,
        # report 053: σ_s accuracy (MAE like h) + structured-background relight L1 (045/046
        # methodology). n_sigma_s counts held-out samples with a supervised gt_σ_s.
        "sigma_s_mae": float(np.mean(sig_maes)) if sig_maes else None,
        "sigma_s_relight_l1": float(np.mean(sig_relight_l1)) if sig_relight_l1 else None,
        "sigma_s_relight_scale": float(np.mean(sig_relight_scale)) if sig_relight_scale else None,
        "n_sigma_s": len(sig_maes),
        "n_cross_lighting_groups": sum(1 for m in groups.values() if len(m) >= 2),
    }

    # --- continuation gate ---
    re = model_row["retained_energy"]
    flattened = re < FLATTEN_RETAINED_FLOOR
    hallucinated = re > HALLUCINATE_RETAINED_CEIL
    texture_ok = (not flattened) and (not hallucinated)
    beat_classical = inv_macro is not None and inv_macro < FROZEN["invariance_T"]["classical"]
    beat_quotient = inv_macro is not None and inv_macro < FROZEN["invariance_T"]["quotient"]
    gate = {
        "sub_floor_flatten_flag": bool(flattened),
        "texture_hallucination_flag": bool(hallucinated),
        "texture_ok": bool(texture_ok),
        "beats_classical_primary": bool(beat_classical),
        "beats_quotient_primary": bool(beat_quotient),
        "GO": bool(beat_classical and beat_quotient and texture_ok),
        "note": ("held-out-identity synthetic; GO requires beating classical AND quotient "
                 "on invariance_T with fine retained-energy in the healthy band "
                 f"[{FLATTEN_RETAINED_FLOOR}, {HALLUCINATE_RETAINED_CEIL}] — neither "
                 "flattening nor hallucinating texture"),
    }

    report = {"backbone": backbone, "ckpt": ckpt, "work_res": work,
              "n_test": len(preds), "model": model_row, "calibration": cal,
              "per_recipe_invariance": recipe_inv, "frozen_reference": FROZEN, "gate": gate}
    with open(os.path.join(out_dir, "eval.json"), "w") as f:
        json.dump(report, f, indent=2)
    _write_table(report, os.path.join(out_dir, "baseline_ladder.md"))
    print(json.dumps({"model": model_row, "calibration": cal, "gate": gate}, indent=2))
    print(f"[eval] wrote {out_dir}/eval.json + baseline_ladder.md")
    return report


def _fmt(x):
    return "—" if x is None else f"{x:.4f}"


def _write_table(rep, path):
    m = rep["model"]
    F = rep["frozen_reference"]
    lines = [
        "# EVAL_PROTOCOL baseline ladder — foundation model (iteration 038)",
        "",
        f"Backbone `{rep['backbone']}` · {rep['n_test']} held-out-identity test samples "
        f"(seed%5==0 / 800-812) · {m['n_cross_lighting_groups']} cross-lighting groups.",
        "",
        "**Family 1 — cross-capture consistency (invariance_T macro, lower = more consistent).**",
        "Frozen rows read from EVAL_PROTOCOL §5; model row computed here.",
        "",
        "| route | invariance_T | source |",
        "|---|---|---|",
        f"| raw copy | {_fmt(F['invariance_T']['raw'])} | frozen §5 |",
        f"| luma quotient α=1 | {_fmt(F['invariance_T']['quotient'])} | frozen §5 |",
        f"| classical (frozen) | {_fmt(F['invariance_T']['classical'])} | frozen §5 |",
        f"| **foundation ({rep['backbone']})** | **{_fmt(m['invariance_T'])}** | **this run** |",
        "",
        "**Family 3/GT accuracy + Family 2 texture preservation (model row; classical frozen).**",
        "",
        "| metric | classical (frozen) | quotient (frozen) | flatten control | foundation |",
        "|---|---|---|---|---|",
        f"| T-MAE ↓ | {_fmt(F['T_mae']['classical'])} | — | — | {_fmt(m['T_mae'])} |",
        f"| h-MAE ↓ | {_fmt(F['h_mae']['classical'])} | — | — | {_fmt(m['h_mae'])} |",
        f"| fine retained-energy (flatten gate) | {_fmt(F['retained_energy']['classical'])} | "
        f"{_fmt(F['retained_energy']['quotient'])} | {_fmt(F['retained_energy']['flatten_control'])} | {_fmt(m['retained_energy'])} |",
        f"| FCS survival ↑ | {_fmt(F['fcs']['classical'])} | {_fmt(F['fcs']['quotient'])} | "
        f"{_fmt(F['fcs']['flatten_control'])} | {_fmt(m['fcs'])} |",
        "",
        f"**σ_s (haze-driven scatter) — report 053 / 048-owed metric, {m.get('n_sigma_s', 0)} "
        "held-out samples with supervised gt_σ_s.**",
        "",
        "| metric | foundation | note |",
        "|---|---|---|",
        f"| σ_s-MAE ↓ | {_fmt(m.get('sigma_s_mae'))} | authored-linear, like h-MAE |",
        f"| σ_s structured-relight L1 (sRGB, 0-255) ↓ | {_fmt(m.get('sigma_s_relight_l1'))} | "
        "checker relit by pred σ_s vs GT σ_s (045/046) |",
        f"| — GT-relight scale (context) | {_fmt(m.get('sigma_s_relight_scale'))} | GT σ_s vs "
        "no-scatter; read L1 against this |",
        "",
        "**Family 4 — confidence calibration (§1d).**",
        "",
        f"- Spearman(conf, −err): {_fmt(rep['calibration']['spearman_conf_negerr'])} (higher = better)",
        f"- ECE @ τ=8/255: {_fmt(rep['calibration']['ece_tau8'])} (lower = better)",
        "",
        "**Continuation gate (consultant plan).**",
        "",
        f"- beats classical on primary: {rep['gate']['beats_classical_primary']}",
        f"- beats quotient on primary: {rep['gate']['beats_quotient_primary']}",
        f"- sub-floor flatten flag: {rep['gate']['sub_floor_flatten_flag']}",
        f"- texture-hallucination flag: {rep['gate'].get('texture_hallucination_flag')}",
        f"- **GO: {rep['gate']['GO']}**",
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--backbone", default="tiny",
                    choices=["tiny", "marigold-iid", "marigold-depth", "sd2"])
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "results", "038_smoke", "eval"))
    ap.add_argument("--device", default=None)
    ap.add_argument("--work", type=int, default=512, help="working resolution (max dim)")
    ap.add_argument("--cache-only", action="store_true")
    args = ap.parse_args()
    evaluate(args.ckpt, args.backbone, args.data, args.out, device=args.device,
             work=args.work, cache_only=args.cache_only)


if __name__ == "__main__":
    main()
