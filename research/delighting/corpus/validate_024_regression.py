#!/usr/bin/env python3
"""validate_024_regression.py -- swatch_picker acceptance test #2 (report 035).

Report 024's `refetch_manifest.json` already has known-correct answers for the 14
Bullseye reactive/Alchemy targets from report 019's smoking-gun taxonomy:
  - 7 "recovered": a genuine -v2 replacement exists -- swatch_picker should prefer
    it over the original contaminated (test_fire_tiles) position-1 image.
  - 7 "unrecoverable": report 024 hand-verified NO candidate on the vendor's live
    feed is a real sheet -- swatch_picker should return NONE (nothing clears the
    floor), or at minimum score both candidates low.

Candidates for the "recovered" set are both already on disk (original + -v2, no
network needed). Candidates for the "unrecoverable" set are fetched from the two
candidate URLs already recorded in refetch_manifest.json (politely, cached).

Writes ../results/corpus/swatch_picker_024_regression.json.
"""
import json
import os

import fetch_gallery
from swatch_picker import pick

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")
CACHE_DIR = os.path.join(RESULTS_DIR, "swatch_picker_cache")
# The MAIN checkout -- where the registry/catalog_images actually live (gitignored,
# never committed to this research branch). Same convention as report 024's
# refetch_contaminated.py: read-only, absolute path, not this worktree's own tree.
MAIN_CHECKOUT = "/Users/dominiquepiche-meunier/Documents/vitraux"
MAIN_CATALOG_DIR = os.path.join(MAIN_CHECKOUT, "frontend", "public", "assets", "catalog_images")
MANIFEST_PATH = os.path.join(RESULTS_DIR, "refetch_manifest.json")


def main():
    manifest = json.load(open(MANIFEST_PATH))
    os.makedirs(CACHE_DIR, exist_ok=True)
    out = {"recovered": [], "unrecoverable": []}

    n_recovered_correct = 0
    for r in manifest["recovered"]:
        old_path = os.path.join(MAIN_CATALOG_DIR, r["old_file"])
        new_path = os.path.join(MAIN_CATALOG_DIR, r["new_file"])
        if not (os.path.exists(old_path) and os.path.exists(new_path)):
            print(f"SKIP {r['old_id']} -- local file missing")
            continue
        candidates = [old_path, new_path]  # position 1 = old contaminated, position 2 = -v2
        result = pick(candidates, name=r.get("name"), manufacturer="Bullseye")
        picked = result["pick"]
        correct = picked == 1  # expect the -v2 (index 1) to win
        n_recovered_correct += int(correct)
        print(f"recovered {r['old_id']:35s} pick={picked}  correct(=-v2)={correct}  "
              f"scores={[s['final_score'] for s in result['scores']]}")
        out["recovered"].append({
            "id": r["old_id"], "name": r.get("name"), "candidates": candidates,
            "pick": picked, "correct": correct,
            "scores": [{"position": s["position"], "final_score": s["final_score"],
                        "components": s["components"]} for s in result["scores"]],
        })

    n_unrec_none_or_low = 0
    for u in manifest["unrecoverable"]:
        old_path = os.path.join(MAIN_CATALOG_DIR, u["old_file"])
        cands = u.get("candidates", [])
        local_paths = []
        for c in cands:
            if c["position"] == 1 and os.path.exists(old_path):
                local_paths.append(old_path)
            else:
                local_paths.append(fetch_gallery.fetch_image_url(c["url"], CACHE_DIR))
        if not local_paths:
            print(f"SKIP {u['id']} -- no candidates")
            continue
        result = pick(local_paths, name=u.get("name"), manufacturer="Bullseye")
        picked = result["pick"]
        max_score = max((s["final_score"] for s in result["scores"]), default=0.0)
        # "expect NONE or low scores on everything" -- accept either outcome.
        ok = picked is None or max_score < 0.60
        n_unrec_none_or_low += int(ok)
        print(f"unrecoverable {u['id']:31s} pick={picked}  max_score={max_score:.3f}  ok={ok}")
        out["unrecoverable"].append({
            "id": u["id"], "name": u.get("name"), "candidates": local_paths,
            "pick": picked, "max_score": round(max_score, 4), "acceptable": ok,
            "scores": [{"position": s["position"], "final_score": s["final_score"],
                        "components": s["components"]} for s in result["scores"]],
        })

    out["summary"] = {
        "n_recovered": len(manifest["recovered"]),
        "n_recovered_correct": n_recovered_correct,
        "n_unrecoverable": len(manifest["unrecoverable"]),
        "n_unrecoverable_none_or_low": n_unrec_none_or_low,
    }
    print()
    print(out["summary"])
    out_path = os.path.join(RESULTS_DIR, "swatch_picker_024_regression.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
