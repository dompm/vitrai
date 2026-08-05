#!/usr/bin/env python3
"""055 — REAL cross-capture consistency: model vs the frozen classical extractor.

The external 053 review's scale criterion, clause 1: "Only scale if it improves REGISTERED
CONSISTENCY without flattening texture and its confidence reliably identifies clear-glass
failures." This scores clause 1 (and feeds clause 3) on the report-033 real pair corpus —
two catalog captures of the SAME product under different lighting/framing.

Method (both routes scored on the IDENTICAL registration and the IDENTICAL valid mask, so
the comparison isolates the T estimator):

  1. load capture A and capture B, ORB-register B onto A (`register_pair.orb_register` — the
     frozen 033 registration), so the two are pixel-aligned;
  2. CLASSICAL: `extract_maps` on each aligned capture -> T_a, T_b;
  3. MODEL: forward each aligned capture -> T_a, T_b (+ conf, h, sigma_s);
  4. score both with `register_pair.registered_t_agreement` (sRGB MAE / p95 over the mask),
     the frozen family-1 instrument. Lower = more consistent.

The valid mask comes from the CLASSICAL run (marks + speculars from both captures) and is
reused for the model, so neither route is scored on pixels the other excludes.

Pair pool: manifest cross_capture pairs, `registrable`, excluding `finished_product_flag`
(photos of finished lamps rather than raw sheets) -> 164 pairs / 79 products.

Glass class (needed by the classical extractor only — the model takes no class input, which
is itself part of what is being compared) is mapped from the catalog brand/caution flags.

Usage:
  realpairs_consistency.py --classical-only --out results/055/pairs
  realpairs_consistency.py --ckpt <adapter.pt> --out results/055/pairs
"""
import argparse
import json
import os
import sys

import numpy as np

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, DELIGHT)
from extract import srgb_to_lin, extract_maps  # noqa: E402
from register_pair import orb_register, registered_t_agreement, load_u8  # noqa: E402

DATA = "/Users/dominiquepiche-meunier/Documents/vitrai-datasets/realpairs-033-data"
MANIFEST = os.path.join(DATA, "manifest_033_restored.json")


def img_path(pid, key):
    """Manifest image_key -> file on disk: 'hero' -> hero_full.jpg, 'gallery_N' -> gN_full.jpg."""
    base = "hero_full.jpg" if key == "hero" else f"g{key.split('_')[1]}_full.jpg"
    return os.path.join(DATA, "images", str(pid), base)


def glass_class_for(product):
    """The classical extractor needs a class prior; the catalog has no glass-class field, so
    map it from the brand/caution flags. Documented heuristic, not ground truth:
      clear-textured-glass  -> cathedral-clear  (the CLEAR subset -- clause 3's failure case)
      opal_streaky_caution  -> opalescent
      everything else       -> wispy            (streaky/mixed art glass)"""
    if product["brand"] == "clear-textured-glass":
        return "cathedral-clear"
    if product.get("opal_streaky_caution"):
        return "opalescent"
    return "wispy"


def load_pairs():
    m = json.load(open(MANIFEST))
    out = []
    for p in m:
        for q in (p.get("pairs") or []):
            if q.get("kind") != "cross_capture" or not q.get("registrable"):
                continue
            if q.get("finished_product_flag"):
                continue
            a, b = img_path(p["product_id"], q["a"]), img_path(p["product_id"], q["b"])
            if os.path.exists(a) and os.path.exists(b):
                out.append({"product_id": p["product_id"], "brand": p["brand"],
                            "title": p.get("title", "")[:60],
                            "glass_class": glass_class_for(p),
                            "is_clear": p["brand"] == "clear-textured-glass",
                            "opal_caution": bool(p.get("opal_streaky_caution")),
                            "a_key": q["a"], "b_key": q["b"], "a": a, "b": b,
                            "manifest_inliers": q.get("inliers")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=None)
    ap.add_argument("--backbone", default="marigold-iid")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=700, help="working res (register_pair default)")
    ap.add_argument("--classical-only", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--sample", type=int, default=None,
                    help="stratified subsample: keep ALL clear-glass pairs (clause 3 needs "
                         "them) and randomly draw non-clear pairs, seed-fixed, to this total")
    ap.add_argument("--device", default=None)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    pairs = load_pairs()
    if args.sample:
        # Stratified, seed-fixed. The classical extractor costs ~1-2 min per capture at full
        # size, so the whole 164-pair pool is hours; a stratified subsample keeps the
        # clause-3 clear-glass evidence intact while bounding wall time. Clear pairs are kept
        # WHOLE because clause 3 is specifically about clear-glass failures.
        clear = [p for p in pairs if p["is_clear"]]
        other = [p for p in pairs if not p["is_clear"]]
        rng = np.random.default_rng(0)
        k = max(0, args.sample - len(clear))
        idx = rng.permutation(len(other))[:k]
        pairs = clear + [other[i] for i in sorted(idx)]
        print(f"[pairs] stratified subsample: ALL {len(clear)} clear + "
              f"{len(pairs)-len(clear)} of {len(other)} non-clear")
    if args.limit:
        pairs = pairs[:args.limit]
    print(f"[pairs] {len(pairs)} registrable cross-capture pairs / "
          f"{len({p['product_id'] for p in pairs})} products "
          f"({sum(p['is_clear'] for p in pairs)} clear-glass)")

    model = None
    if not args.classical_only:
        import torch
        from backbone import FoundationDelighter
        import eval_foundation as ef
        import eval_texture_preservation as etp  # noqa: F401  (clause-2 instrument)
        dev = args.device or ("mps" if torch.backends.mps.is_available() else "cpu")
        model = FoundationDelighter(backbone=args.backbone, freeze_backbone=True,
                                    cache_only=True).to(dev)
        model.load_adapter(args.ckpt, map_location=dev)
        model.eval()
        print(f"[pairs] model {args.ckpt} on {dev}")

        def model_maps(lin):
            ph = ef._pad8(np.ascontiguousarray(lin))
            with torch.no_grad():
                o = model(torch.from_numpy(ph).permute(2, 0, 1)[None].float().to(dev).clamp(0, None))

            def g(k, c):
                a = o[k][0].permute(1, 2, 0).float().cpu().numpy()
                return a[:lin.shape[0], :lin.shape[1], :c]
            return g("T", 3), g("h", 1), g("sigma_s", 1), g("conf", 1)

    rows = []
    for i, p in enumerate(pairs):
        try:
            a_u8 = load_u8(p["a"], args.size)
            b_u8 = load_u8(p["b"], args.size)
            b_reg, inl = orb_register(b_u8, a_u8)
            if b_reg is None or inl < 12:
                print(f"  [{i}] {p['product_id']} SKIP registration failed (inliers={inl})")
                continue
            a_lin = srgb_to_lin(a_u8.astype(np.float32) / 255.0)
            b_lin = srgb_to_lin(b_reg.astype(np.float32) / 255.0)

            ma = extract_maps(a_lin, p["glass_class"], mark_region="none")
            mb = extract_maps(b_lin, p["glass_class"], mark_region="none")
            valid = ~(ma["mark_mask"] | ma["spec_mask"] | mb["mark_mask"] | mb["spec_mask"])
            if valid.sum() < 1000:
                print(f"  [{i}] {p['product_id']} SKIP valid mask too small ({valid.sum()})")
                continue
            cl = registered_t_agreement(ma["T"], mb["T"], valid)

            row = {**{k: p[k] for k in ("product_id", "brand", "glass_class", "is_clear",
                                        "opal_caution", "a_key", "b_key")},
                   "orb_inliers": int(inl), "n_valid_px": int(valid.sum()),
                   "classical_mae": cl["T_agreement_mae_srgb255"],
                   "classical_p95": cl["T_agreement_p95_srgb255"],
                   "classical_T_std": float(np.std(ma["T"]))}

            if model is not None:
                Ta, ha, sa, ca = model_maps(a_lin)
                Tb, hb, sb, cb = model_maps(b_lin)
                md = registered_t_agreement(Ta, Tb, valid)
                # Clause 2 on REAL data. Real photos have no authored gt_T, so the frozen
                # family-2 instrument is run with the CLASSICAL T as reference and the model's
                # T as test: it measures how much of the fine structure the classical route
                # resolves that the model still carries. Read against the same landmarks as
                # the synthetic table — the 8-sigma blur control collapses retained-energy to
                # 0.03, so a model drifting toward zero here is flattening real texture.
                tex = etp.evaluate(ma["T"], Ta, mask=valid)
                row.update({
                    "rel_retained_energy_vs_classical": tex["mgp"]["fine_retained_energy"],
                    "rel_fine_grad_corr_vs_classical": tex["mgp"]["fine_grad_corr"],
                    "model_mae": md["T_agreement_mae_srgb255"],
                    "model_p95": md["T_agreement_p95_srgb255"],
                    "model_T_std": float(np.std(Ta)),
                    "model_conf_mean": float((ca[..., 0][valid].mean() + cb[..., 0][valid].mean()) / 2),
                    "model_conf_p10": float(np.percentile(
                        np.concatenate([ca[..., 0][valid], cb[..., 0][valid]]), 10)),
                    "model_h_mean": float(ha.mean()),
                    "model_sigma_s_mean": float(sa.mean()),
                })
            rows.append(row)
            msg = f"  [{i+1}/{len(pairs)}] {p['product_id']} {p['glass_class']:15s} classical={row['classical_mae']:6.2f}"
            if model is not None:
                msg += f" model={row['model_mae']:6.2f} conf={row['model_conf_mean']:.3f}"
            print(msg, flush=True)
        except Exception as e:
            print(f"  [{i}] {p['product_id']} ERROR {type(e).__name__}: {str(e)[:90]}", flush=True)

    # ---------------------------------------------------------------- aggregate
    def agg(sel, label):
        r = [x for x in rows if sel(x)]
        if not r:
            return None
        d = {"label": label, "n_pairs": len(r),
             "n_products": len({x["product_id"] for x in r}),
             "classical_mae_mean": float(np.mean([x["classical_mae"] for x in r])),
             "classical_mae_median": float(np.median([x["classical_mae"] for x in r]))}
        if "model_mae" in r[0]:
            d.update({
                "model_mae_mean": float(np.mean([x["model_mae"] for x in r])),
                "model_mae_median": float(np.median([x["model_mae"] for x in r])),
                "model_better_frac": float(np.mean([x["model_mae"] < x["classical_mae"] for x in r])),
                "model_T_std_mean": float(np.mean([x["model_T_std"] for x in r])),
                "classical_T_std_mean": float(np.mean([x["classical_T_std"] for x in r])),
                "model_conf_mean": float(np.mean([x["model_conf_mean"] for x in r])),
                "rel_retained_energy_vs_classical_mean": float(np.mean(
                    [x["rel_retained_energy_vs_classical"] for x in r
                     if x.get("rel_retained_energy_vs_classical") is not None])),
                "rel_fine_grad_corr_vs_classical_mean": float(np.mean(
                    [x["rel_fine_grad_corr_vs_classical"] for x in r
                     if x.get("rel_fine_grad_corr_vs_classical") is not None])),
            })
            # clause 3: does confidence TRACK error? (negative corr conf-vs-error = good)
            if len(r) >= 4:
                from register_pair import np as _np  # noqa
                c = np.array([x["model_conf_mean"] for x in r])
                e = np.array([x["model_mae"] for x in r])
                cr = np.argsort(np.argsort(c)).astype(float)
                er = np.argsort(np.argsort(e)).astype(float)
                cr -= cr.mean(); er -= er.mean()
                den = np.sqrt((cr * cr).sum() * (er * er).sum())
                d["spearman_conf_vs_error"] = float((cr * er).sum() / den) if den > 0 else 0.0
        return d

    summary = [s for s in [
        agg(lambda x: True, "ALL pairs"),
        agg(lambda x: x["is_clear"], "CLEAR glass (clear-textured-glass)"),
        agg(lambda x: not x["is_clear"], "non-clear (opal/streaky art glass)"),
        agg(lambda x: x["opal_caution"], "opal_streaky_caution products"),
    ] if s]

    json.dump({"n_pairs_scored": len(rows), "summary": summary, "rows": rows},
              open(os.path.join(args.out, "realpairs_consistency.json"), "w"), indent=2)
    print("\n=== SUMMARY (T-agreement MAE, sRGB 0-255, lower = more consistent) ===")
    for s in summary:
        line = f"{s['label']:42s} n={s['n_pairs']:3d} classical={s['classical_mae_mean']:6.2f}"
        if "model_mae_mean" in s:
            line += (f" model={s['model_mae_mean']:6.2f}"
                     f" model_better={s['model_better_frac']*100:4.0f}%"
                     f" spearman(conf,err)={s.get('spearman_conf_vs_error', float('nan')):+.3f}"
                     f" retained_vs_classical={s.get('rel_retained_energy_vs_classical_mean', float('nan')):.3f}")
        print(line)
    print(f"\n[pairs] wrote {args.out}/realpairs_consistency.json")


if __name__ == "__main__":
    main()
