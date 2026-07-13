#!/usr/bin/env python3
"""
Step 2: download top ~N candidate images per product from candidates.json,
throttled ~1 req/s per host, skipping tiny thumbnails and duplicate images
(exact-content hash + perceptual hash dedupe).
"""
import hashlib
import io
import json
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import imagehash
import requests
from PIL import Image

HERE = Path(__file__).parent
RESULTS = HERE / "results"
IMG_DIR = HERE / "candidate_images"
IMG_DIR.mkdir(exist_ok=True)

MIN_DIM = 300
MAX_PER_PRODUCT = 15
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HOST_LAST_HIT = defaultdict(float)
MIN_HOST_INTERVAL = 1.0  # ~1 req/s per host


def throttle(host):
    now = time.time()
    wait = HOST_LAST_HIT[host] + MIN_HOST_INTERVAL - now
    if wait > 0:
        time.sleep(wait)
    HOST_LAST_HIT[host] = time.time()


def fetch(url, timeout=10):
    host = urlparse(url).netloc
    throttle(host)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r.content


def main():
    candidates = json.loads((RESULTS / "candidates.json").read_text())
    manifest = {}
    stats = defaultdict(int)

    for pid, data in candidates.items():
        product = data["product"]
        cands = data["candidates"]
        out_dir = IMG_DIR / pid
        out_dir.mkdir(exist_ok=True)
        kept = []
        seen_exact_hash = set()
        seen_phash = []
        print(f"=== {pid} ({len(cands)} candidates) ===")

        for i, c in enumerate(cands):
            if len(kept) >= MAX_PER_PRODUCT:
                break
            url = c["url"]
            try:
                content = fetch(url)
            except Exception as e:
                stats["fetch_fail"] += 1
                print(f"  [{i}] FETCH FAIL {url[:80]} :: {e}")
                continue

            # exact-content dedupe
            h = hashlib.sha256(content).hexdigest()
            if h in seen_exact_hash:
                stats["dup_exact"] += 1
                continue

            try:
                im = Image.open(io.BytesIO(content))
                im.load()
            except Exception as e:
                stats["decode_fail"] += 1
                print(f"  [{i}] DECODE FAIL {url[:80]} :: {e}")
                continue

            w, h_px = im.size
            if w < MIN_DIM or h_px < MIN_DIM:
                stats["too_small"] += 1
                continue

            # perceptual-hash dedupe (near-duplicate crops/resizes across hosts)
            try:
                ph = imagehash.phash(im.convert("RGB"))
            except Exception:
                ph = None
            is_dup = False
            if ph is not None:
                for existing in seen_phash:
                    if ph - existing <= 4:  # hamming distance threshold
                        is_dup = True
                        break
            if is_dup:
                stats["dup_phash"] += 1
                continue

            seen_exact_hash.add(h)
            if ph is not None:
                seen_phash.append(ph)

            ext = ".jpg" if im.format in ("JPEG", "MPO") else f".{(im.format or 'jpg').lower()}"
            fname = f"{len(kept):02d}{ext}"
            fpath = out_dir / fname
            im.convert("RGB").save(fpath, "JPEG", quality=90)

            kept.append(
                {
                    "file": str(fpath.relative_to(HERE)),
                    "url": url,
                    "title": c["title"],
                    "source_page": c["source_page"],
                    "width": w,
                    "height": h_px,
                    "query": c["query"],
                }
            )
            stats["kept"] += 1
            print(f"  [{i}] kept -> {fname}  ({w}x{h_px})  {url[:70]}")

        manifest[pid] = {"product": product, "images": kept}
        print(f"  -> {len(kept)} images kept for {pid}")

    (RESULTS / "downloaded_manifest.json").write_text(json.dumps(manifest, indent=2))
    print("\nSTATS:", dict(stats))
    print(f"Wrote {RESULTS / 'downloaded_manifest.json'}")


if __name__ == "__main__":
    main()
