#!/usr/bin/env python3
"""Report 051 — build the DINOv2 retrieval index over the canonical CLEAN CORPUS.

The clean corpus (report 021/024, results/corpus/clean_manifest.json, 1,281
images across Bullseye/Oceanside/Youghiogheny/Wissmach) is the registry the app
actually ships. In the 051 benchmark it plays two roles:
  (1) a realistic DISTRACTOR pool for realpairs retrieval (the query's true
      product is a Delphi SKU not in this corpus; a good index must not rank a
      Bullseye look-alike above the real target), and
  (2) the substrate for the query-representation ablation and the out-of-catalog
      confidence-gate negatives.

One index entry per image; product key = registry_id (clean corpus is ~1
canonical image per SKU). Embeddings are gitignored (regenerate with this
script); the meta sidecar is small and committed.

Raw corpus images are LOCAL-ONLY (gitignored on main); read read-only via the
absolute main-repo path, never copied or committed (report 015/019/021 posture).
"""
import argparse
import json
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from embed import Embedder  # noqa: E402

# main-repo checkout holds the gitignored corpus (same convention as
# catalog_texture_audit.resolve_default_registry)
MAIN_REPO = "/Users/dominiquepiche-meunier/Documents/vitraux"
CATALOG_DIR = os.path.join(MAIN_REPO, "frontend", "public", "assets", "catalog_images")
CLEAN_MANIFEST = os.path.join(HERE, "..", "results", "corpus", "clean_manifest.json")
OUT_DIR = os.path.join(HERE, "..", "results", "051")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backbone", default="dinov2-small")
    ap.add_argument("--manifest", default=CLEAN_MANIFEST)
    ap.add_argument("--catalog-dir", default=CATALOG_DIR)
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "clean_index_dinov2.npz"))
    ap.add_argument("--meta-out", default=os.path.join(OUT_DIR, "clean_index_meta.json"))
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    man = json.load(open(args.manifest))
    imgs = man["images"]
    if args.limit:
        imgs = imgs[:args.limit]

    entries, paths, missing = [], [], 0
    for im in imgs:
        p = os.path.join(args.catalog_dir, im["file"])
        if not os.path.exists(p):
            missing += 1
            continue
        entries.append({
            "entry_id": f"clean::{im['registry_id']}",
            "product_id": im["registry_id"],
            "source": "clean_corpus",
            "brand": im["manufacturer"],
            "glass_class": im["extractor_class"],
            "category": im.get("category"),
            "name": im.get("name"),
            "confidence": im.get("confidence"),
            "file": im["file"],
        })
        paths.append(p)
    print(f"{len(paths)} images to embed ({missing} missing on disk)")

    emb = Embedder(backbone=args.backbone)
    vecs = emb.embed(paths, normalize=True, progress=True)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    np.savez_compressed(args.out, embeddings=vecs,
                        entry_ids=np.array([e["entry_id"] for e in entries]))
    json.dump({"backbone": args.backbone, "dim": int(vecs.shape[1]),
               "n": len(entries), "entries": entries},
              open(args.meta_out, "w"), indent=1)
    print(f"wrote {args.out} ({vecs.shape}) and {args.meta_out}")


if __name__ == "__main__":
    main()
