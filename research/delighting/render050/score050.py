"""050 synthetic validation: score relief auto-detection against the generator's
authored relief (the free synthetic ground truth).

GT category  = the relief family the recipe belongs to (families.json 'category',
               grounded in generate_relief_height's shared-relief groupings).
GT amplitude = binned bump_distance_m (the authored relief height in metres).
GT scale     = the recipe family's dominant relief feature scale (category-tied
               in the generator -> flagged as a limitation).

Holdout discipline: seed 6001 = TUNING (used while shaping prompts/thresholds),
seeds 7001/7002 = HOLDOUT (never used for tuning). Headline accuracy is HOLDOUT.
"""
import os, json, sys, argparse
import numpy as np
import detect_relief as D

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.abspath(os.path.join(HERE, "..", "results", "050", "assets_ms"))
OUT = os.path.abspath(os.path.join(HERE, "..", "results", "050"))

# GT scale per relief family (generator's dominant relief feature scale)
GT_SCALE = {"smooth": "fine", "hammered": "medium", "granite": "fine",
            "seedy": "medium", "ripple": "medium", "rolling_wave": "coarse"}

# product-facing coarse taxonomy: the 6 fine categories collapse to 4 groups
# that map to distinct presentation looks (flat / all-over texture / directional
# streaks / coarse waves). Fine hammered<->granite<->seedy differences are the
# hardest to see in a photo and matter least to the effect.
COARSE = {"smooth": "flat", "hammered": "isotropic", "granite": "isotropic",
          "seedy": "isotropic", "ripple": "directional", "rolling_wave": "wavy"}


def gt_amplitude(bd):
    if bd < 0.0009:
        return "subtle"
    if bd < 0.005:
        return "medium"
    return "strong"


def collect(PHOTOS):
    fam = json.load(open(os.path.join(ASSETS, "families.json")))
    rows = []
    for f in sorted(os.listdir(PHOTOS)):
        if not f.startswith("photo_") or not f.endswith(".png"):
            continue
        stem = f[len("photo_"):-4]
        smooth = stem.endswith("_smooth")
        key = stem[:-len("_smooth")] if smooth else stem
        meta = fam[key]
        cat = "smooth" if smooth else meta["category"]
        bd = 0.0 if smooth else meta["bump_distance_m"]
        seed = meta["seed"]
        rows.append({"file": os.path.join(PHOTOS, f), "key": key, "seed": seed,
                     "split": "tune" if seed == 6001 else "holdout",
                     "gt_category": cat, "gt_amplitude": gt_amplitude(bd),
                     "gt_scale": GT_SCALE[cat], "bd": bd})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vlm-knobs-split", default="holdout",
                    help="run VLM amp/scale on this split (all|holdout|none)")
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--photos", default=os.path.abspath(
        os.path.join(HERE, "..", "results", "050", "photos_v2")))
    a = ap.parse_args()
    rows = collect(a.photos)
    for r in rows:
        want_vlm = a.vlm_knobs_split == "all" or (
            a.vlm_knobs_split == "holdout" and r["split"] == "holdout")
        res = D.detect(r["file"], use_vlm_knobs=want_vlm, model=a.model)
        r["det_category"] = res["category"]
        r["gt_coarse"] = COARSE[r["gt_category"]]
        r["det_coarse"] = COARSE[res["category"]]
        r["cls_amplitude"] = res["amplitude"]
        r["cls_scale"] = res["feature_scale"]
        r["vlm_amplitude"] = res.get("vlm_amplitude")
        r["vlm_scale"] = res.get("vlm_scale")
        r["feat"] = {k: round(v, 4) for k, v in res["features"].items()}
        print(f"{r['key']:28s} [{r['split']:7s}] gt={r['gt_category']:12s} "
              f"det={r['det_category']:12s} {'OK' if r['det_category']==r['gt_category'] else 'X '} "
              f"amp gt={r['gt_amplitude']:6s} cls={r['cls_amplitude']:6s} "
              f"vlm={r['vlm_amplitude']}")

    def acc(rs, gk, dk):
        rs = [r for r in rs if r.get(dk) is not None]
        if not rs:
            return None
        return round(sum(r[gk] == r[dk] for r in rs) / len(rs), 3), len(rs)

    def block(rs, label):
        return {
            "n": len(rs),
            "category_acc": acc(rs, "gt_category", "det_category"),
            "coarse_acc": acc(rs, "gt_coarse", "det_coarse"),
            "cls_amp_acc": acc(rs, "gt_amplitude", "cls_amplitude"),
            "cls_scale_acc": acc(rs, "gt_scale", "cls_scale"),
            "vlm_amp_acc": acc(rs, "gt_amplitude", "vlm_amplitude"),
            "vlm_scale_acc": acc(rs, "gt_scale", "vlm_scale"),
        }

    hold = [r for r in rows if r["split"] == "holdout"]
    tune = [r for r in rows if r["split"] == "tune"]
    # confusion for category (holdout)
    cats = D.RP.CATEGORIES
    conf = {g: {d: 0 for d in cats} for g in cats}
    for r in hold:
        conf[r["gt_category"]][r["det_category"]] += 1
    summary = {"holdout": block(hold, "holdout"), "tune": block(tune, "tune"),
               "all": block(rows, "all"), "category_confusion_holdout": conf}
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    json.dump({"summary": summary, "rows": [
        {k: v for k, v in r.items() if k != "feat"} for r in rows],
        "features": {r["key"] + ("_smooth" if r["gt_category"] == "smooth" else ""): r["feat"] for r in rows}},
        open(os.path.join(OUT, "detection_scores.json"), "w"), indent=2)
    print("wrote", os.path.join(OUT, "detection_scores.json"))


if __name__ == "__main__":
    main()
