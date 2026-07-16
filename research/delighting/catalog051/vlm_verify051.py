#!/usr/bin/env python3
"""Report 051, scope 5 — VLM top-k verification as a second-stage precision boost.

Embedding retrieval gives a shortlist; a VLM ("same physical glass product?")
can rerank it or reject a shortlist that contains no true match. We measure the
ADDED value over embedding top-1 on a stratified ~40-query budget:
  A) top-1 correct           — VLM should confirm the same product.
  B) correct in top-2..5     — rerank opportunity (embedding missed top-1).
  C) correct NOT in top-5    — VLM should answer "none" (precision on shortlists
                               that do not contain the answer — the OOC signal).

Uses `claude -p` print mode, model sonnet (project memory: batch subcalls must
not inherit/burn the fable limit), --allowedTools Read (the CLI renders image
files as image blocks), read-only single call. Candidate order is shuffled per
query to remove position bias; the shuffle map is recorded.
"""
import argparse
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "results", "051")

PROMPT = """You are matching stained-glass sheet photographs to a catalog.

Image 1 is a USER PHOTO of a single glass sheet (often held up to a window or
photographed in a shop, so it may have background, a hand, glare, or a colour
cast from the lighting).

Images 2..{n} are CATALOG reference photos of candidate glass products (clean
swatch or close-up crops).

Decide which ONE candidate, if any, is the SAME physical glass PRODUCT as
image 1 — same colour, same opacity/opalescence, and same surface texture /
streak pattern (allowing for different lighting, crop, and scale). Different
colourway or different texture family = not a match.

Read every image (1..{n}) with the Read tool, then respond with ONLY a JSON
object: {{"choice": <candidate number 2..{n}, or 0 if none match>,
"confidence": <0.0-1.0>}}. No other text."""


def call_vlm(query_path, candidate_paths, model="sonnet", timeout=300):
    paths = [query_path] + candidate_paths
    numbered = "\n".join(f"{i+1}. {os.path.abspath(p)}" for i, p in enumerate(paths))
    full = (PROMPT.format(n=len(paths)) +
            f"\n\nRead these files in order (1 is the user photo, 2..{len(paths)} "
            f"are candidates):\n{numbered}\n\nRespond with ONLY the JSON object.")
    cmd = ["claude", "-p", full, "--model", model,
           "--allowedTools", "Read", "--output-format", "text"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    txt = proc.stdout.strip()
    s, e = txt.find("{"), txt.rfind("}")
    if s == -1 or e == -1:
        return None, txt[:200]
    try:
        return json.loads(txt[s:e + 1]), None
    except Exception:
        return None, txt[:200]


def stratify(board, per_q, n_budget, seed=0):
    rng = random.Random(seed)
    # attach rank of gt from per_q (aligned by order)
    strata = {"A_top1": [], "B_in_top5": [], "C_miss": []}
    for b, pq in zip(board, per_q):
        rank = pq["rank"]
        if rank == 1:
            strata["A_top1"].append(b)
        elif rank in (2, 3, 4, 5):
            strata["B_in_top5"].append(b)
        else:
            strata["C_miss"].append(b)
    for k in strata:
        rng.shuffle(strata[k])
    # aim ~ 40/40/20 split of budget
    quota = {"A_top1": int(n_budget * 0.35), "B_in_top5": int(n_budget * 0.4),
             "C_miss": n_budget - int(n_budget * 0.35) - int(n_budget * 0.4)}
    picked = []
    for k, q in quota.items():
        picked += [(k, b) for b in strata[k][:q]]
    return picked, {k: len(v) for k, v in strata.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=os.path.join(OUT_DIR, "realpairs_bench_board.json"))
    ap.add_argument("--perquery", default=os.path.join(OUT_DIR, "realpairs_bench_perquery.json"))
    ap.add_argument("--budget", type=int, default=40)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "vlm_verify.json"))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    board = json.load(open(args.board))
    per_q = json.load(open(args.perquery))
    picked, avail = stratify(board, per_q, args.budget, args.seed)
    print(f"strata available: {avail}; running {len(picked)} VLM calls")

    rng = random.Random(args.seed + 1)
    records = []
    for i, (stratum, b) in enumerate(picked):
        cands = [c for c in b["candidates"] if c.get("path")]
        order = list(range(len(cands)))
        rng.shuffle(order)
        shuffled = [cands[j] for j in order]
        resp, err = call_vlm(b["query_path"], [c["path"] for c in shuffled], args.model)
        choice_pid, choice_correct = None, None
        if resp and isinstance(resp.get("choice"), int):
            ch = resp["choice"]
            if ch == 0:
                choice_pid = "NONE"
            elif 2 <= ch <= len(shuffled) + 1:
                choice_pid = shuffled[ch - 2]["product_id"]
        choice_correct = (choice_pid == b["query_product_id"])
        emb_top1_correct = b["candidates"][0]["correct"] if b["candidates"] else False
        gt_in_shortlist = any(c["correct"] for c in cands)
        rec = {"stratum": stratum, "query_product_id": b["query_product_id"],
               "query_capture": b["query_capture"], "query_brand": b["query_brand"],
               "vlm_choice_pid": choice_pid, "vlm_raw": resp, "err": err,
               "vlm_correct": choice_correct, "emb_top1_correct": emb_top1_correct,
               "gt_in_shortlist": gt_in_shortlist,
               "shuffle_order": order}
        records.append(rec)
        sys.stderr.write(f"\r  [{i+1}/{len(picked)}] {stratum} vlm={choice_pid} "
                         f"correct={choice_correct} err={err is not None}   ")
        sys.stderr.flush()
        json.dump({"records": records}, open(args.out, "w"), indent=1)
    sys.stderr.write("\n")

    # aggregate
    def acc(rs, key):
        rs = [r for r in rs if r["err"] is None]
        return round(sum(1 for r in rs if r[key]) / len(rs), 3) if rs else None
    ok = [r for r in records if r["err"] is None]
    summary = {
        "n_total": len(records), "n_ok": len(ok), "n_err": len(records) - len(ok),
        "emb_top1_acc": acc(records, "emb_top1_correct"),
        "vlm_choice_acc": acc(records, "vlm_correct"),
        "by_stratum": {},
    }
    for s in ("A_top1", "B_in_top5", "C_miss"):
        rs = [r for r in records if r["stratum"] == s]
        # C_miss: correct answer is "NONE"; VLM correct if it said NONE
        c_none = [r for r in rs if r["err"] is None and r["vlm_choice_pid"] == "NONE"]
        summary["by_stratum"][s] = {
            "n": len(rs), "emb_top1_acc": acc(rs, "emb_top1_correct"),
            "vlm_choice_acc": acc(rs, "vlm_correct"),
            "vlm_said_none_frac": round(len(c_none) / max(1, len([r for r in rs if r["err"] is None])), 3),
        }
    out = {"summary": summary, "records": records}
    json.dump(out, open(args.out, "w"), indent=1)
    print(json.dumps(summary, indent=1))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
