#!/usr/bin/env python3
"""Iteration 030 -- exhaustive within-product pairwise registration on the 15
downloaded full-res image sets. Purpose: separate three cases the single-pair
check conflated (report 030 SS2.2):

  same_photo   -- ORB registers AND the aligned central-region residual is
                  tiny (median |diff| < 10/255) with high gradient correlation:
                  one file is a crop/rescale of the other (Delphi's hero is
                  routinely a crop of gallery_1). Useless as a pair; useful as
                  dedup metadata.
  cross_capture-- ORB registers (>= 20 RANSAC inliers both ways max) but the
                  residual is substantial: same sheet region under a different
                  capture. THE prize.
  none         -- ORB fails; possibly same sheet, different region/zoom
                  (statistics-only pair) or different subject entirely.

All local compute on already-downloaded files; no network.
"""
import itertools
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from register_pair import orb_register, load_u8  # noqa: E402

IMG_ROOT = "/tmp/delphi_pairs_images"
INLIER_THRESH = 20
SAME_PHOTO_MAD = 10.0


def full_path(pid, key):
    if key == "hero":
        return os.path.join(IMG_ROOT, f"{pid}_hero_full.jpg")
    n = key.split("_")[1]
    return os.path.join(IMG_ROOT, f"{pid}_{n}_full.jpg")


def central_residual(ref, warped):
    H, W = ref.shape[:2]
    cy, cx = H // 2, W // 2
    ch, cw = H // 3, W // 3
    r = ref[cy - ch // 2:cy + ch // 2, cx - cw // 2:cx + cw // 2].astype(np.float32)
    w_ = warped[cy - ch // 2:cy + ch // 2, cx - cw // 2:cx + cw // 2].astype(np.float32)
    mad = float(np.median(np.abs(r - w_)))
    gr = cv2.Sobel(cv2.cvtColor(r.astype(np.uint8), cv2.COLOR_RGB2GRAY), cv2.CV_32F, 1, 1)
    gw = cv2.Sobel(cv2.cvtColor(w_.astype(np.uint8), cv2.COLOR_RGB2GRAY), cv2.CV_32F, 1, 1)
    denom = gr.std() * gw.std()
    cc = float((gr * gw).mean() / denom) if denom > 1e-6 else 0.0
    return mad, cc


def main(pq_path="results/pair_quality.json", census_path="results/census.json",
         out_path="results/pairwise_matrix.json", size=700):
    pq = json.load(open(pq_path))
    census = {c["product_id"]: c for c in json.load(open(census_path))}
    results = []
    for rec in pq:
        pid = rec["product_id"]
        if pid not in census:
            continue
        labels = {c["key"]: c["label"] for c in census[pid]["classifications"]}
        keys = [k for k in labels if os.path.exists(full_path(pid, k))]
        imgs = {}
        for k in keys:
            try:
                imgs[k] = load_u8(full_path(pid, k), size)
            except Exception:
                pass
        pairs = []
        for ka, kb in itertools.combinations(sorted(imgs), 2):
            a, b = imgs[ka], imgs[kb]
            w_ab, i_ab = orb_register(b, a)
            w_ba, i_ba = orb_register(a, b)
            if i_ab >= i_ba and w_ab is not None:
                inl, ref, warped = i_ab, a, w_ab
            elif w_ba is not None:
                inl, ref, warped = i_ba, b, w_ba
            else:
                inl, ref, warped = max(i_ab, i_ba), None, None
            if inl >= INLIER_THRESH and warped is not None:
                mad, cc = central_residual(ref, warped)
                kind = "same_photo" if (mad < SAME_PHOTO_MAD and cc > 0.35) else "cross_capture"
            else:
                mad, cc, kind = None, None, "none"
            pairs.append({"a": ka, "b": kb, "label_a": labels.get(ka), "label_b": labels.get(kb),
                          "inliers": int(inl), "mad": mad, "grad_corr": cc, "kind": kind})
        n_cross = sum(1 for p in pairs if p["kind"] == "cross_capture")
        n_same = sum(1 for p in pairs if p["kind"] == "same_photo")
        results.append({"product_id": pid, "brand": rec["brand"], "title": rec.get("title"),
                        "n_images": len(imgs), "n_pairs": len(pairs),
                        "n_cross_capture": n_cross, "n_same_photo": n_same, "pairs": pairs})
        print(f"{pid} ({rec['brand']}): {len(imgs)} imgs, {len(pairs)} pairs -> "
              f"cross_capture={n_cross} same_photo={n_same}")
        json.dump(results, open(out_path, "w"), indent=1)
    return results


if __name__ == "__main__":
    main()
