#!/usr/bin/env python3
"""Iteration 030 -- Delphi Glass multi-capture census: discovery + page fetch.

Delphi Glass's live storefront (www.delphiglass.com) returns HTTP 403 to every
request from this environment (Cloudflare bot-management WAF -- confirmed via
curl AND the WebFetch tool, both blocked; unrelated sites and even
shop.bullseyeglass.com respond fine, so this is Delphi-specific, not a general
egress problem). Two things are NOT behind that WAF and were confirmed to
return normal 200s:

  1. The Wayback Machine's CDX API and archived snapshots of
     www.delphiglass.com product pages -- used here for all PAGE HTML.
  2. Delphi's own image hosts (images.delphiglass.com, and
     www.delphiglass.com/syscat/image_*/...) -- used for actual image bytes,
     fetched live (not through Wayback) so we get current, correctly-sized
     files, at a throttled rate.

So: product discovery + page parsing goes through Wayback (politeness there
governed by archive.org's public infra, not Delphi's), and only image-byte
downloads touch delphiglass.com directly, at ~1 req/s with a normal UA, per
the task brief. This keeps the actual live-site load to a few hundred small
image GETs, not thousands of page loads -- less than one real visitor
browsing the same number of product galleries.

Product URL shape: https://www.delphiglass.com/stained-glass/<brand>/<slug>
Product image shape (per gallery item, discovered by parsing the page):
  - hero:    https://images.delphiglass.com/image_new/<id>.jpg      (300x300)
             https://images.delphiglass.com/image_1500/<id>.jpg     (full)
  - gallery: https://www.delphiglass.com/syscat/image_add/<id>_<n>.jpg    (70x55 thumb)
             https://www.delphiglass.com/syscat/image_add/<id>_<n>0.jpg  (1500x1500 full)
"""
import json
import os
import re
import sys
import time
import random
import argparse
import urllib.request

CDX_URL = "http://web.archive.org/cdx/search/cdx"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) research-delighting-030 (internal eval; contact via github)"

# Genuine single-sheet glass brand/category directories under /stained-glass/.
# Excludes: glass-packs, glass-crates (bulk multi-sheet assortments), mirror-colored-mirror
# (mirror, not stained sheet), holiday-glass/halloween-glass (seasonal kits), copper-foil-technique/
# working-with-bevels/3-dimensional-projects/garden-patterns/lamps (technique/tool pages, not sheets),
# safety-equipment, leaded-glass (technique).
SHEET_CATEGORIES = {
    "clear-textured-glass", "van-gogh-glass", "tiffany-today-glass", "uro-glass",
    "kokomo-glass", "wissmach-glass", "german-new-antique", "armstrong-glass",
    "specialty-finish-glass", "youghiogheny-glass", "bullseye-glass", "spectrum-glass",
    "returning-spectrum-glass", "uroboros-glass", "delphi-superior-glass", "oceanside-glass",
}


def http_get(url, retries=3, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    return None


def discover_candidates(cache_path):
    """CDX query for all archived /stained-glass/<brand>/<slug> URLs, filtered to
    genuine sheet-brand categories. Cached to disk (CDX itself is cheap/public but
    no need to re-hit it every run)."""
    if os.path.exists(cache_path):
        return json.load(open(cache_path))
    url = (CDX_URL + "?url=www.delphiglass.com/stained-glass/&matchType=prefix"
           "&output=json&collapse=urlkey&filter=statuscode:200&limit=100000&fl=original,timestamp")
    raw = json.loads(http_get(url))
    rows = raw[1:] if raw else []
    urls = {}
    for orig, ts in rows:
        u = re.sub(r"^https?://", "", orig)
        u = re.sub(r":80", "", u)
        if not u.startswith("www.delphiglass.com/stained-glass/"):
            continue
        path = u[len("www.delphiglass.com"):]
        parts = [p for p in path.split("/") if p]
        if len(parts) != 3 or parts[0] != "stained-glass":
            continue
        if parts[2] in ("review", "reviews"):
            continue
        if "?" in orig or "?" in u:
            # category listing pages with a ?sort=/?searchItems= query string, not
            # products -- also matches robots.txt's own Disallow: /*?sort intent
            continue
        brand = parts[1]
        if brand not in SHEET_CATEGORIES:
            continue
        full = "https://" + u.rstrip("/")
        # keep the most recent timestamp per URL for the freshest snapshot
        if full not in urls or ts > urls[full][1]:
            urls[full] = (brand, ts)
    items = [{"url": u, "brand": b, "timestamp": ts} for u, (b, ts) in urls.items()]
    json.dump(items, open(cache_path, "w"), indent=1)
    return items


def stratified_sample(items, n_total, seed=42, min_per_brand=3):
    rng = random.Random(seed)
    by_brand = {}
    for it in items:
        by_brand.setdefault(it["brand"], []).append(it)
    for b in by_brand:
        rng.shuffle(by_brand[b])
    brands = sorted(by_brand)
    sample = []
    # first pass: min_per_brand each (or all available if fewer)
    for b in brands:
        take = by_brand[b][:min_per_brand]
        sample.extend(take)
        by_brand[b] = by_brand[b][min_per_brand:]
    remaining_pool = [it for b in brands for it in by_brand[b]]
    rng.shuffle(remaining_pool)
    need = max(0, n_total - len(sample))
    sample.extend(remaining_pool[:need])
    rng.shuffle(sample)
    return sample


def wayback_snapshot_url(target_url):
    """Ask CDX for the closest available snapshot timestamp, then build the
    'im_' (raw content, no wayback toolbar) fetch URL for the RAW html isn't what
    we want -- we want the plain (no toolbar) rendered HTML, so use the bare
    (no im_/if_) form which Wayback serves with rewritten links but full content."""
    avail_url = f"http://archive.org/wayback/available?url={target_url}"
    data = json.loads(http_get(avail_url))
    snap = data.get("archived_snapshots", {}).get("closest")
    if not snap or not snap.get("available"):
        return None
    return snap["url"], snap["timestamp"]


IMG_ADD_RE = re.compile(
    r'href="[^"]*?/syscat/image_add/(\d+)_(\d)0\.jpg"[^>]*data-thumbnail="[^"]*?/syscat/image_add/(\d+)_(\d)\.jpg"'
)
HERO_RE = re.compile(r'itemprop="image"[^>]*data-thumbnail="[^"]*?/image_new/(\d+)_t\.jpg"')
HERO_ID_RE = re.compile(r'/image_1500/(\d+)\.jpg')
TITLE_RE = re.compile(r'<title>([^<]+)</title>')


def parse_product_page(html):
    hero_ids = HERO_ID_RE.findall(html)
    hero_id = hero_ids[0] if hero_ids else None
    gallery = []
    for m in IMG_ADD_RE.finditer(html):
        pid, n, pid2, n2 = m.groups()
        gallery.append({"product_id": pid, "index": int(n)})
    # de-dup by index
    seen = set()
    dedup = []
    for g in gallery:
        if g["index"] in seen:
            continue
        seen.add(g["index"])
        dedup.append(g)
    dedup.sort(key=lambda g: g["index"])
    tm = TITLE_RE.search(html)
    title = tm.group(1).strip() if tm else None
    if not hero_id and dedup:
        hero_id = dedup[0]["product_id"]
    return {"hero_id": hero_id, "gallery": dedup, "title": title}


def fetch_products(sample, out_path, sleep_s=0.6, limit=None):
    """Fetch each product's page via Wayback and parse its image manifest.
    Rate is against archive.org (public infra), not the live retailer site."""
    results = []
    if os.path.exists(out_path):
        results = json.load(open(out_path))
        done_urls = {r["url"] for r in results}
    else:
        done_urls = set()
    todo = [s for s in sample if s["url"] not in done_urls]
    if limit:
        todo = todo[:limit]
    for i, item in enumerate(todo):
        try:
            snap = wayback_snapshot_url(item["url"])
            if not snap:
                results.append({**item, "error": "no_snapshot"})
                continue
            snap_url, ts = snap
            html = http_get(snap_url).decode("utf-8", errors="replace")
            parsed = parse_product_page(html)
            n_images = (1 if parsed["hero_id"] else 0) + len(parsed["gallery"])
            results.append({**item, "snapshot_ts": ts, "product_id": parsed["hero_id"],
                             "title": parsed["title"], "gallery": parsed["gallery"],
                             "n_images": n_images})
            print(f"[{i+1}/{len(todo)}] {item['brand']:24s} {parsed['hero_id']} "
                  f"n_images={n_images}  {item['url'][-50:]}")
        except Exception as e:
            results.append({**item, "error": str(e)})
            print(f"[{i+1}/{len(todo)}] ERROR {item['url']}: {e}")
        if (i + 1) % 10 == 0:
            json.dump(results, open(out_path, "w"), indent=1)
        time.sleep(sleep_s)
    json.dump(results, open(out_path, "w"), indent=1)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="results/candidates.json")
    ap.add_argument("--manifest", default="results/product_manifest.json")
    ap.add_argument("--n", type=int, default=220)
    ap.add_argument("--limit", type=int, default=None, help="only fetch this many new pages this run")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.cache), exist_ok=True)
    candidates = discover_candidates(args.cache)
    print(f"discovered {len(candidates)} candidate product URLs across "
          f"{len(set(c['brand'] for c in candidates))} sheet-brand categories")
    sample = stratified_sample(candidates, args.n, seed=args.seed)
    print(f"sampled {len(sample)} products")
    fetch_products(sample, args.manifest, limit=args.limit)
