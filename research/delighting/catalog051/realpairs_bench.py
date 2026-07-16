#!/usr/bin/env python3
"""Report 051 — wild->clean catalog retrieval benchmark + confidence gate.

Query  = wild capture (window/shop) of a Delphi realpairs product.
Target = the product's clean captures (closeup/lightbox) in the index.
Index  = realpairs reference captures, optionally + the 1,281-image clean corpus
         as realistic distractors (a Delphi wild shot must beat Bullseye
         look-alikes to be a true positive).

Metrics: top-1 / top-5 PRODUCT accuracy, per-brand / per-capture / per-class
(opal-caution vs not) / holdout breakdowns.

Confidence gate: in-catalog vs OUT-OF-CATALOG separation. OOC is simulated by
leave-product-out (drop the query product's reference entries, re-score). A
calibrated threshold on the top-1 cosine yields measured precision/recall for
"confidently in-catalog", plus the prior-independent AUC. Low-confidence falls
back to photo-only detection (study 050) — this script only designs the gate.
"""
import argparse
import json
import os
import numpy as np

from rp_data import build_image_table, RP
from retrieve import Index, eval_retrieval
from embed_cache import EmbedCache

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "results", "051")
CLEAN_IDX = os.path.join(OUT_DIR, "clean_index_dinov2.npz")
CLEAN_META = os.path.join(OUT_DIR, "clean_index_meta.json")


def auc(pos, neg):
    """Probability a random positive scores above a random negative (Mann-Whitney)."""
    pos = np.asarray(pos, float); neg = np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    allv = np.concatenate([pos, neg])
    order = allv.argsort()
    ranks = np.empty_like(order, float)
    ranks[order] = np.arange(1, len(allv) + 1)
    # average ranks for ties
    _, inv, cnt = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt)); np.add.at(sums, inv, ranks)
    avg = sums / cnt
    ranks = avg[inv]
    r_pos = ranks[:len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def gate_sweep(pos_scores, neg_scores):
    """pos = in-catalog top-1 cosine; neg = out-of-catalog top-1 cosine.
    Balanced-prior precision/recall over thresholds. Returns curve + picks."""
    pos = np.asarray(pos_scores, float); neg = np.asarray(neg_scores, float)
    ths = np.unique(np.concatenate([pos, neg]))
    curve = []
    for t in ths:
        tp = int((pos >= t).sum()); fn = int((pos < t).sum())
        fp = int((neg >= t).sum()); tn = int((neg < t).sum())
        prec = tp / (tp + fp) if (tp + fp) else 1.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        spec = tn / (tn + fp) if (tn + fp) else 0.0
        curve.append({"t": float(t), "precision": prec, "recall": rec,
                      "specificity": spec, "youden": rec + spec - 1,
                      "f1": (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0})
    # pick: highest-recall threshold achieving >=0.90 precision; and max-Youden
    p90 = [c for c in curve if c["precision"] >= 0.90]
    pick_p90 = max(p90, key=lambda c: c["recall"]) if p90 else None
    pick_j = max(curve, key=lambda c: c["youden"])
    return {"auc": auc(pos, neg), "n_pos": len(pos), "n_neg": len(neg),
            "pos_median": float(np.median(pos)), "neg_median": float(np.median(neg)),
            "pick_precision90": pick_p90, "pick_youden": pick_j,
            "curve": curve}


def run(img_root, use_distractors=True, repr_name="raw", transform=None,
        cache_path=None, eval_scope="all", tag=""):
    products, images = build_image_table(img_root)
    refs = [i for i in images if i["role"] == "reference"]
    wilds = [i for i in images if i["role"] == "wild"]
    scorable = {pid for pid, p in products.items() if p["scorable"]}
    # only queries whose product is scorable (has >=1 reference on disk)
    wilds = [w for w in wilds if w["product_id"] in scorable]
    if eval_scope == "holdout":
        wilds = [w for w in wilds if w["holdout"]]
    elif eval_scope == "eval_eligible":
        wilds = [w for w in wilds if not w["holdout"]]

    cache = EmbedCache(cache_path or os.path.join(OUT_DIR, "rp_embed_cache.npz"))
    ref_vecs = cache.get([r["path"] for r in refs], repr_name, transform)
    wild_vecs = cache.get([w["path"] for w in wilds], repr_name, transform)

    # ---- index: realpairs references (+ optional clean-corpus distractors) ----
    rp_entries = [{"entry_id": f"rp::{r['product_id']}::{r['image_key']}",
                   "product_id": r["product_id"], "source": "realpairs",
                   "brand": r["brand"], "capture_type": r["capture_type"],
                   "path": r["path"],
                   "name": products[r["product_id"]]["title"]} for r in refs]
    emb_list = [ref_vecs]
    ent_list = list(rp_entries)
    if use_distractors and os.path.exists(CLEAN_IDX):
        cz = np.load(CLEAN_IDX, allow_pickle=True)
        cmeta = json.load(open(CLEAN_META))["entries"]
        emb_list.append(cz["embeddings"])
        ent_list += cmeta
    index = Index(np.concatenate(emb_list, axis=0), ent_list)

    gt = [w["product_id"] for w in wilds]
    groupers = {
        "brand": [w["brand"] for w in wilds],
        "capture": [w["capture_type"] for w in wilds],
        "opal_caution": ["opal" if w["opal_streaky_caution"] else "clean_id" for w in wilds],
        "holdout": ["holdout" if w["holdout"] else "eval_eligible" for w in wilds],
    }
    metrics, per_q = eval_retrieval(index, wild_vecs, gt, topk=(1, 5), groupers=groupers)

    # ---- board data: per query, query path + top-5 candidate entries w/ paths ----
    CATALOG_DIR = os.path.join("/Users/dominiquepiche-meunier/Documents/vitraux",
                               "frontend", "public", "assets", "catalog_images")

    def entry_path(e):
        if e.get("path"):
            return e["path"]
        if e.get("file"):
            return os.path.join(CATALOG_DIR, e["file"])
        return None
    ranked_full = index.rank_products(wild_vecs, topk=5)
    board = []
    for w, r in zip(wilds, ranked_full):
        cands = []
        for pid, sc, j in r["ranked"]:
            e = index.entries[j]
            cands.append({"product_id": pid, "score": round(sc, 4),
                          "source": e.get("source"), "brand": e.get("brand"),
                          "name": e.get("name"), "path": entry_path(e),
                          "correct": pid == w["product_id"]})
        board.append({"query_product_id": w["product_id"], "query_path": w["path"],
                      "query_capture": w["capture_type"], "query_brand": w["brand"],
                      "query_name": products[w["product_id"]]["title"],
                      "opal_caution": w["opal_streaky_caution"],
                      "candidates": cands})

    # ---- confidence gate: in-catalog vs out-of-catalog (leave-product-out) ----
    in_cat_scores = [p["best_score"] for p in per_q]           # product present
    in_cat_correct = [p["best_score"] for p in per_q if p["top1_correct"]]
    in_cat_wrong = [p["best_score"] for p in per_q if not p["top1_correct"]]
    ooc_scores = []
    for w, wv in zip(wilds, wild_vecs):
        idx_loo = index.drop_products([w["product_id"]])
        r = idx_loo.rank_products(wv[None, :], topk=1)[0]
        ooc_scores.append(r["best_score"])
    gate = gate_sweep(in_cat_scores, ooc_scores)
    # joint "confident AND top-1 correct" at the p90 pick threshold
    if gate["pick_precision90"]:
        t = gate["pick_precision90"]["t"]
        conf = [p for p in per_q if p["best_score"] >= t]
        gate["at_p90_threshold"] = {
            "t": t, "n_confident": len(conf),
            "frac_confident": round(len(conf) / len(per_q), 3) if per_q else 0,
            "top1_acc_among_confident": round(np.mean([p["top1_correct"] for p in conf]), 3) if conf else 0,
        }

    result = {
        "tag": tag, "repr": repr_name, "use_distractors": use_distractors,
        "eval_scope": eval_scope,
        "n_scorable_products": len(scorable),
        "n_reference_entries": len(refs),
        "n_wild_queries": len(wilds),
        "index_size": index.n, "index_products": index.n_products,
        "retrieval": metrics,
        "gate": {k: v for k, v in gate.items() if k != "curve"},
        "gate_score_summary": {
            "in_catalog_correct_median": float(np.median(in_cat_correct)) if in_cat_correct else None,
            "in_catalog_wrong_median": float(np.median(in_cat_wrong)) if in_cat_wrong else None,
            "ooc_median": float(np.median(ooc_scores)) if ooc_scores else None,
            "n_in_cat_correct": len(in_cat_correct), "n_in_cat_wrong": len(in_cat_wrong),
        },
    }
    return result, per_q, gate, board


def diagnostic_any_capture(img_root, use_distractors=True, cache_path=None):
    """Upper-bound diagnostic: target = ANY other capture of the product
    (leave-one-image-out), not just clean references. The gap vs the primary
    clean-target number isolates the closeup/lightbox 'clean-reference is hard'
    penalty from raw same-product matching ability."""
    products, images = build_image_table(img_root)
    usable = [i for i in images if i["role"] in ("reference", "wild")]
    scorable = {pid for pid, p in products.items()
                if (p["n_reference"] + p["n_wild"]) >= 2}
    usable = [i for i in usable if i["product_id"] in scorable]
    cache = EmbedCache(cache_path or os.path.join(OUT_DIR, "rp_embed_cache.npz"))
    vecs = cache.get([i["path"] for i in usable], "raw", None)
    entries = [{"entry_id": f"rp::{i['product_id']}::{i['image_key']}",
                "product_id": i["product_id"], "source": "realpairs",
                "brand": i["brand"], "path": i["path"]} for i in usable]
    emb_list, ent_list = [vecs], list(entries)
    if use_distractors and os.path.exists(CLEAN_IDX):
        cz = np.load(CLEAN_IDX, allow_pickle=True)
        emb_list.append(cz["embeddings"])
        ent_list += json.load(open(CLEAN_META))["entries"]
    index = Index(np.concatenate(emb_list, 0), ent_list)
    # queries = wild only (consistent w/ primary), exclude self row
    q_rows = [k for k, i in enumerate(usable) if i["role"] == "wild"]
    qv = vecs[q_rows]
    excl = q_rows  # self row in the (realpairs-first) index is the same position
    res = index.rank_products(qv, topk=5, exclude_rows=excl)
    gt = [usable[k]["product_id"] for k in q_rows]
    caps = [usable[k]["capture_type"] for k in q_rows]
    top1 = top5 = 0
    bycap = {}
    for r, g, cap in zip(res, gt, caps):
        pids = [p for p, _, _ in r["ranked"]]
        rank = pids.index(g) + 1 if g in pids else None
        d = bycap.setdefault(cap, {"n": 0, "t1": 0, "t5": 0})
        d["n"] += 1
        if rank == 1:
            top1 += 1; d["t1"] += 1
        if rank and rank <= 5:
            top5 += 1; d["t5"] += 1
    n = len(gt)
    return {"mode": "any_capture_leave1out", "n_queries": n,
            "top1": round(top1 / n, 4), "top5": round(top5 / n, 4),
            "by_capture": {c: {"n": d["n"], "top1": round(d["t1"] / d["n"], 3),
                               "top5": round(d["t5"] / d["n"], 3)}
                           for c, d in bycap.items()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img-root", default=os.path.join(RP, "data", "images"))
    ap.add_argument("--repr", default="raw")
    ap.add_argument("--no-distractors", action="store_true")
    ap.add_argument("--scope", default="all", choices=["all", "holdout", "eval_eligible"])
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "realpairs_bench.json"))
    ap.add_argument("--tag", default="raw_distractors")
    args = ap.parse_args()

    result, per_q, gate, board = run(args.img_root, use_distractors=not args.no_distractors,
                                     repr_name=args.repr, eval_scope=args.scope, tag=args.tag)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(result, open(args.out, "w"), indent=1)
    json.dump({"tag": args.tag, "gate_curve": gate["curve"]},
              open(args.out.replace(".json", "_gatecurve.json"), "w"))
    json.dump(per_q, open(args.out.replace(".json", "_perquery.json"), "w"), indent=1, default=str)
    json.dump(board, open(args.out.replace(".json", "_board.json"), "w"), indent=1, default=str)

    r = result
    print(f"\n[{r['tag']}] scope={r['eval_scope']} distractors={r['use_distractors']}")
    print(f"  products={r['n_scorable_products']} refs={r['n_reference_entries']} "
          f"queries={r['n_wild_queries']} index={r['index_size']} ({r['index_products']} prods)")
    print(f"  RETRIEVAL  top1={r['retrieval']['top1']:.3f}  top5={r['retrieval']['top5']:.3f}")
    g = r["gate"]; gs = r["gate_score_summary"]
    print(f"  GATE  AUC={g['auc']:.3f}  in-cat median={g['pos_median']:.3f}  OOC median={g['neg_median']:.3f}")
    print(f"        in-cat correct med={gs['in_catalog_correct_median']} "
          f"wrong med={gs['in_catalog_wrong_median']} OOC med={gs['ooc_median']}")
    if g.get("pick_precision90"):
        pp = g["pick_precision90"]; at = g.get("at_p90_threshold", {})
        print(f"        @prec>=0.90: t={pp['t']:.3f} recall={pp['recall']:.3f} "
              f"| confident frac={at.get('frac_confident')} top1-acc-among-confident={at.get('top1_acc_among_confident')}")
    print(f"  per-brand top1: " +
          ", ".join(f"{b}:{d['top1_acc']:.2f}(n{d['n']})"
                    for b, d in sorted(r['retrieval']['breakdowns']['brand'].items())))
    print(f"  per-capture top1: " +
          ", ".join(f"{c}:{d['top1_acc']:.2f}(n{d['n']})"
                    for c, d in r['retrieval']['breakdowns']['capture'].items()))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
