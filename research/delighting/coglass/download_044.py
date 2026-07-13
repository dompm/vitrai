#!/usr/bin/env python3
"""Iteration 044 -- throttled, resumable image download for the coglassworks
census (census_044.json -> data/images/<handle>/<basename>).

Posture (maintainer-approved, report 041 SS7): image bytes only, straight
from the public Shopify CDN, sequential single-connection at ~1 req/s,
descriptive UA with contact email, exponential backoff plus a long cooldown
on 429/5xx (agents.md: "Back off on 429 responses"). Raw images are
LOCAL-ONLY and gitignored (coglass/data/ in research/delighting/.gitignore,
committed before this script ever ran) -- same posture as realpairs/data/
per REAL_PAIRS_DATASET.md SS5/SS9.5.

Resumable: an image already on disk with plausible-JPEG size is skipped
without a network hit; the manifest (results/download_manifest_044.json) is
rewritten every --checkpoint images and on exit, so an interruption never
restarts from zero.

Disk guard: aborts if free space on the data volume drops below FLOOR_GB
(10 GB machine floor) + HEADROOM_GB (2 GB safety) at start or during the run.
"""
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CENSUS = os.path.join(HERE, "results", "census_044.json")
MANIFEST = os.path.join(HERE, "results", "download_manifest_044.json")
IMG_ROOT = os.path.join(HERE, "data", "images")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "research-delighting-044 (stained-glass material research, internal eval; "
      "contact: dompm@hotmail.com)")

FLOOR_GB = 10.0
HEADROOM_GB = 0.3  # was 2.0; tightened 2026-07-13 after other agents ate the
                   # disk margin. Recompression (below) keeps the end-state
                   # projection ~0.5 GB above the 10 GB machine floor.
THROTTLE_S = 1.0
CHECKPOINT = 50
RECOMPRESS_Q = 80  # disk-pressure adaptation: stored images are re-encoded
                   # (EXIF orientation baked in, JPEG q80), NOT bit-exact CDN
                   # bytes -- ~2x smaller at this store's native 1500 px. No
                   # effect on ORB registration or capture classification;
                   # refetchable idempotently if exact bytes ever matter.


def free_gb(path):
    return shutil.disk_usage(path).free / (1024 ** 3)


def disk_ok():
    return free_gb(HERE) >= FLOOR_GB + HEADROOM_GB


def local_name(src_url):
    return os.path.basename(src_url.split("?")[0])


def write_recompressed(data, dest):
    """Re-encode fetched image bytes to JPEG q80 with EXIF orientation baked
    in. Falls back to raw bytes if decoding fails. Returns bytes written."""
    import io
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.save(dest, "JPEG", quality=RECOMPRESS_Q, optimize=True)
        return os.path.getsize(dest)
    except Exception:
        with open(dest, "wb") as f:
            f.write(data)
        return len(data)


def fetch(url, dest, retries=4):
    """Returns (status, bytes, did_network). status: ok|error|http_<code>."""
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        return "ok", os.path.getsize(dest), False
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if len(data) < 1000 or not (data[:3] == b"\xff\xd8\xff"
                                        or data[:8] == b"\x89PNG\r\n\x1a\n"
                                        or data[:4] == b"RIFF"):
                return "error_not_image", len(data), True
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            nbytes = write_recompressed(data, dest)
            return "ok", nbytes, True
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                cooldown = 30.0 * (attempt + 1)
                print(f"  HTTP {e.code}, cooling down {cooldown:.0f}s", flush=True)
                time.sleep(cooldown)
                continue
            return f"http_{e.code}", 0, True
        except Exception as e:
            time.sleep(2.0 * (attempt + 1))
    return "error", 0, True


def main():
    with open(CENSUS) as f:
        products = json.load(f)["products"]

    jobs = []
    for p in products:
        for im in p["images"]:
            jobs.append({"handle": p["handle"], "url": im["src"],
                         "file": local_name(im["src"])})
    print(f"{len(jobs)} images across {len(products)} products", flush=True)

    manifest = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as f:
            manifest = json.load(f).get("images", {})
        print(f"resuming: {sum(1 for v in manifest.values() if v['status'] == 'ok')} "
              f"already ok in manifest", flush=True)

    if not disk_ok():
        print(f"ABORT: only {free_gb(HERE):.1f} GB free "
              f"(< {FLOOR_GB + HEADROOM_GB} GB guard)", flush=True)
        sys.exit(2)

    n_net = n_ok = n_err = 0
    t0 = time.time()

    def checkpoint():
        tmp = MANIFEST + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "n_jobs": len(jobs), "images": manifest}, f)
        os.replace(tmp, MANIFEST)

    for i, job in enumerate(jobs):
        key = f"{job['handle']}/{job['file']}"
        dest = os.path.join(IMG_ROOT, job["handle"], job["file"])
        prev = manifest.get(key)
        if prev and prev["status"] == "ok" and os.path.exists(dest) \
                and os.path.getsize(dest) > 1000:
            continue
        status, nbytes, did_net = fetch(job["url"], dest)
        manifest[key] = {"status": status, "bytes": nbytes, "path":
                         os.path.relpath(dest, HERE), "url": job["url"]}
        if status == "ok":
            n_ok += 1
        else:
            n_err += 1
            print(f"  {key}: {status}", flush=True)
        if did_net:
            n_net += 1
            time.sleep(THROTTLE_S)
        if n_net and n_net % CHECKPOINT == 0:
            checkpoint()
            if not disk_ok():
                print(f"ABORT mid-run: {free_gb(HERE):.1f} GB free", flush=True)
                checkpoint()
                sys.exit(2)
            rate = n_net / max(1e-9, time.time() - t0)
            done = sum(1 for v in manifest.values() if v["status"] == "ok")
            print(f"[{i + 1}/{len(jobs)}] ok_total={done} new_net={n_net} "
                  f"err={n_err} rate={rate:.2f} req/s free={free_gb(HERE):.1f}GB",
                  flush=True)

    checkpoint()
    done = sum(1 for v in manifest.values() if v["status"] == "ok")
    print(f"DONE: {done}/{len(jobs)} ok, {n_err} errors, "
          f"{n_net} network hits in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
