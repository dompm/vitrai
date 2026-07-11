"""fetch_gallery.py -- polite Shopify product-gallery fetcher for swatch_picker validation.

Report 035. Both Bullseye (shop.bullseyeglass.com) and Stained Glass Express
(stainedglassexpress.com, which also fronts Oceanside/Wissmach/Youghiogheny per
glass-library-integration-review.md Finding 4) are Shopify stores: appending
`.json` to a product URL returns the full product record (every gallery image,
`body_html` description, `title`) without needing an API key. This is the same
convention report 024's `refetch_contaminated.py` used against Bullseye.

Stdlib-only (urllib), ~1 request/second, disk-cached so repeat runs don't re-hit
the vendor. Nothing here is a scraper rewrite -- it's a validation-harness helper
for swatch_picker.py's acceptance tests.

Usage:
    python3 fetch_gallery.py --product-url <url> --cache-dir <dir>
    # returns {'title':..., 'body_html':..., 'images': [local paths, in gallery order]}
"""
import argparse
import hashlib
import json
import os
import time
import urllib.request

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) swatch-picker-validation/035 (research, polite, 1req/s)'
_last_request = [0.0]
MIN_INTERVAL = 1.0  # seconds between requests, process-wide


def _throttled_get(url):
    wait = MIN_INTERVAL - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    _last_request[0] = time.time()
    return data


def _cache_path(cache_dir, url):
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    ext = os.path.splitext(url.split('?')[0])[1] or '.jpg'
    return os.path.join(cache_dir, f'{h}{ext}')


def fetch_product_json(product_url, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    base = product_url.split('?')[0].rstrip('/')
    json_url = base + '.json'
    cache_file = os.path.join(cache_dir, hashlib.sha1(json_url.encode()).hexdigest()[:16] + '.json')
    if os.path.exists(cache_file):
        return json.loads(open(cache_file).read())
    data = _throttled_get(json_url)
    obj = json.loads(data)
    with open(cache_file, 'w') as f:
        f.write(json.dumps(obj))
    return obj


def fetch_image_url(url, cache_dir):
    """Fetch and cache a single raw image URL (no product-page context needed).
    Used by validation scripts that already have a candidate URL list, e.g. from
    report 024's refetch_manifest.json."""
    os.makedirs(cache_dir, exist_ok=True)
    p = _cache_path(cache_dir, url)
    if not os.path.exists(p):
        data = _throttled_get(url)
        with open(p, 'wb') as f:
            f.write(data)
    return p


def fetch_gallery(product_url, cache_dir):
    """Fetch a product's full gallery. Returns dict with title/body_html/images
    (images = list of local cached file paths, in gallery order) and image_urls."""
    obj = fetch_product_json(product_url, cache_dir)
    product = obj['product']
    image_urls = [im['src'] for im in product.get('images', [])]
    local_paths = []
    for url in image_urls:
        p = _cache_path(cache_dir, url)
        if not os.path.exists(p):
            data = _throttled_get(url)
            with open(p, 'wb') as f:
                f.write(data)
        local_paths.append(p)
    return {'title': product.get('title', ''), 'body_html': product.get('body_html', '') or '',
            'images': local_paths, 'image_urls': image_urls, 'product_url': product_url}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--product-url', required=True)
    ap.add_argument('--cache-dir', required=True)
    args = ap.parse_args()
    g = fetch_gallery(args.product_url, args.cache_dir)
    print(json.dumps({k: v for k, v in g.items() if k != 'body_html'}, indent=2))
    print(f"body_html ({len(g['body_html'])} chars):")
    print(g['body_html'])


if __name__ == '__main__':
    main()
