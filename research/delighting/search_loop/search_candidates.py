#!/usr/bin/env python3
"""
Step 1 of the 042 search loop: query an image search engine for each pilot
product and collect raw candidate URLs.

Engine: ddgs (duckduckgo_search fork), no API key required.

IMPORTANT finding from manual testing (see report 042 sec 2): ddgs.images()
intermittently (~1 in 4-5 calls observed) returns a genuinely unrelated
"fallback gallery" (e.g. queried "Bullseye Sunset Coral transparent glass",
got Hostess snack-cake photos) instead of erroring. This is silent -- no
exception, no empty list, just wrong images with plausible-looking titles/
structure. We guard against this with a relevance check on returned titles
(must share a token with manufacturer/search_name) before accepting a batch;
a batch that fails the check is retried once, then logged and skipped.
"""
import json
import re
import sys
import time
from pathlib import Path

from ddgs import DDGS

HERE = Path(__file__).parent
OUT_DIR = HERE / "results"
OUT_DIR.mkdir(exist_ok=True)

STOPWORDS = {"the", "with", "and", "of", "coe", "glass", "sheet", "stained", "mm"}


def tokens(s):
    return {t for t in re.findall(r"[a-z]+", s.lower()) if t not in STOPWORDS and len(t) > 2}


def batch_is_relevant(results, product):
    """Cheap sniff test: do returned titles share vocabulary with the query?
    Catches the ddgs fallback-gallery failure mode (see module docstring)."""
    if not results:
        return False
    want = tokens(product["manufacturer"]) | tokens(product["search_name"])
    hits = 0
    for r in results:
        title = r.get("title", "")
        if tokens(title) & want:
            hits += 1
    # require at least 40% of the batch to share vocabulary with the query
    return hits / len(results) >= 0.4


def search_variants(product):
    name = product["search_name"]
    mfr = product["manufacturer"]
    return [
        f"{mfr} {name} stained glass sheet",
        f"{mfr} {name} glass",
        f"{name} {mfr} sheet glass",
    ]


def query_once(query, max_results=15):
    with DDGS() as ddgs:
        return list(ddgs.images(query, max_results=max_results))


def collect_for_product(product, per_variant=15, sleep_s=1.5):
    seen_urls = set()
    candidates = []
    log = []
    for q in search_variants(product):
        ok = False
        for attempt in (1, 2):
            try:
                results = query_once(q, max_results=per_variant)
            except Exception as e:
                log.append(f"query failed (attempt {attempt}): {q!r}: {e}")
                results = []
            relevant = batch_is_relevant(results, product)
            log.append(
                f"query={q!r} attempt={attempt} n_results={len(results)} "
                f"relevant_batch={relevant}"
            )
            if relevant:
                ok = True
                break
            time.sleep(sleep_s)  # backoff before retry
        if not ok:
            log.append(f"SKIPPED query (failed relevance check twice): {q!r}")
            time.sleep(sleep_s)
            continue
        for r in results:
            url = r.get("image")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append(
                {
                    "url": url,
                    "title": r.get("title", ""),
                    "source_page": r.get("url", ""),
                    "width": r.get("width"),
                    "height": r.get("height"),
                    "query": q,
                }
            )
        time.sleep(sleep_s)
    return candidates, log


def main():
    products = json.loads((HERE / "pilot_products.json").read_text())
    all_out = {}
    for p in products:
        print(f"=== {p['id']} :: {p['manufacturer']} {p['search_name']} ===", file=sys.stderr)
        cands, log = collect_for_product(p)
        for line in log:
            print("   ", line, file=sys.stderr)
        print(f"   -> {len(cands)} unique candidate URLs", file=sys.stderr)
        all_out[p["id"]] = {"product": p, "candidates": cands, "log": log}

    (OUT_DIR / "candidates.json").write_text(json.dumps(all_out, indent=2))
    print(f"Wrote {OUT_DIR / 'candidates.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
