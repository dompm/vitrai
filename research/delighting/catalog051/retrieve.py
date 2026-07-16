#!/usr/bin/env python3
"""Report 051 — retrieval index + product-level scoring.

An Index holds L2-normalized embeddings and per-entry metadata. Scoring is
cosine similarity; PRODUCT score = max over that product's entries (max-pool is
the standard multi-view aggregation — a query need only match one of a product's
reference captures). Returns ranked products and the raw best-entry hit for
qualitative boards and the confidence gate.
"""
import json
import numpy as np


class Index:
    def __init__(self, embeddings, entries):
        assert len(embeddings) == len(entries)
        self.emb = np.asarray(embeddings, dtype=np.float32)
        self.entries = entries
        self.product_ids = np.array([e["product_id"] for e in entries])
        # map product_id -> row indices (for product-level max-pool)
        self._by_prod = {}
        for i, e in enumerate(entries):
            self._by_prod.setdefault(e["product_id"], []).append(i)

    @classmethod
    def load(cls, npz_path, meta_path):
        z = np.load(npz_path, allow_pickle=True)
        meta = json.load(open(meta_path))
        return cls(z["embeddings"], meta["entries"])

    def subset(self, keep_mask):
        """Return a new Index over rows where keep_mask is True."""
        idx = np.where(keep_mask)[0]
        return Index(self.emb[idx], [self.entries[i] for i in idx])

    def drop_products(self, product_ids):
        """Leave-product-out: return an Index with those products removed."""
        drop = set(product_ids)
        mask = np.array([pid not in drop for pid in self.product_ids])
        return self.subset(mask)

    @property
    def n(self):
        return len(self.entries)

    @property
    def n_products(self):
        return len(self._by_prod)

    def rank_products(self, qvecs, topk=5, exclude_rows=None):
        """qvecs: (Q, d) normalized. Returns list (per query) of dicts:
        {ranked: [(product_id, score, best_entry_idx), ...topk],
         best_entry_idx, best_score}. Product score = max-pool over entries.
        exclude_rows: optional list (len Q) of a row index to suppress for that
        query (leave-one-image-out, so a query cannot match its own entry)."""
        qvecs = np.asarray(qvecs, dtype=np.float64)
        # errstate guard: macOS Accelerate BLAS raises spurious div0/overflow
        # FP flags on this matmul even though both operands are verified finite
        # and outputs are exact (self-retrieval == 1.0). Data, not precision.
        with np.errstate(all="ignore"):
            sims = qvecs @ self.emb.astype(np.float64).T  # (Q, N)
        if exclude_rows is not None:
            for q, row in enumerate(exclude_rows):
                if row is not None:
                    sims[q, row] = -np.inf
        results = []
        prod_list = list(self._by_prod.items())
        for q in range(sims.shape[0]):
            s = sims[q]
            # product-level max-pool
            prod_scores = []
            for pid, rows in prod_list:
                j = rows[int(np.argmax(s[rows]))]
                prod_scores.append((pid, float(s[j]), j))
            prod_scores.sort(key=lambda x: -x[1])
            ranked = prod_scores[:topk]
            results.append({
                "ranked": ranked,
                "best_entry_idx": ranked[0][2],
                "best_score": ranked[0][1],
                # margin between top-1 and top-2 product (a gate feature)
                "margin": (ranked[0][1] - ranked[1][1]) if len(ranked) > 1 else float("nan"),
            })
        return results


def eval_retrieval(index, qvecs, q_product_ids, topk=(1, 5), groupers=None):
    """Compute top-k product accuracy. groupers: dict name-> list[str] parallel
    to queries, for per-group breakdowns (brand, class, capture, ...)."""
    maxk = max(topk)
    res = index.rank_products(qvecs, topk=maxk)
    per_q = []
    for r, gt in zip(res, q_product_ids):
        ranked_pids = [p for p, _, _ in r["ranked"]]
        rank = ranked_pids.index(gt) + 1 if gt in ranked_pids else None
        per_q.append({"gt": gt, "ranked_pids": ranked_pids,
                      "best_score": r["best_score"], "margin": r["margin"],
                      "top1_correct": rank == 1,
                      "rank": rank})
    out = {"n_queries": len(per_q)}
    for k in topk:
        hits = sum(1 for p in per_q if p["rank"] is not None and p["rank"] <= k)
        out[f"top{k}"] = round(hits / len(per_q), 4) if per_q else 0.0
    if groupers:
        out["breakdowns"] = {}
        for gname, gvals in groupers.items():
            byg = {}
            for p, gv in zip(per_q, gvals):
                d = byg.setdefault(gv, {"n": 0, **{f"top{k}": 0 for k in topk}})
                d["n"] += 1
                for k in topk:
                    if p["rank"] is not None and p["rank"] <= k:
                        d[f"top{k}"] += 1
            for gv, d in byg.items():
                for k in topk:
                    d[f"top{k}_acc"] = round(d[f"top{k}"] / d["n"], 3) if d["n"] else 0.0
            out["breakdowns"][gname] = byg
    return out, per_q
