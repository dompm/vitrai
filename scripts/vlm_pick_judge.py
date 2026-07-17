"""vlm_pick_judge.py -- pilot: does a VLM forced-choice judge fix the heuristic
swatch-picker's long-tail image-selection failures, and what does it cost at
corpus scale (1,269 products)?

STANDALONE PILOT SCRIPT -- lives outside scripts/swatch_picker.py and
scripts/build_swatch_library.py on purpose (another agent is concurrently
editing those two files on a different branch; this pilot must not touch
them). Read-only with respect to the registry: it re-scrapes each sampled
product's own gallery from the live vendor site (SGE / Bullseye Shopify
`<product_url>.json`) to get the FULL candidate set (the registry only keeps
the winning URL, not the runner-up candidates), builds a numbered contact
sheet per product, and asks a `claude -p` subprocess -- once per product per
model -- to forced-choice pick the one straight-on flat swatch photo.

=====================================================================================
JUDGE MECHANISM
=====================================================================================
The `claude` CLI's `-p` (print) mode has no dedicated "attach an image" flag
(checked `claude --help`: no `--image`/`--attach`, and passing a bare file path
as a second positional argument is NOT treated as an attachment -- verified
empirically, it just gets ignored and Claude asks "what image?"). What DOES
work: give the prompt the image's file path in prose and let the model's own
Read tool open it, with tool permission pre-granted so a non-interactive `-p`
call never blocks on a permission prompt:

    claude -p "Read the image at <path> and ..." \\
        --model sonnet|haiku --allowedTools Read \\
        --permission-mode bypassPermissions --output-format json

`--output-format json` is used (not the default text) because it hands back
`duration_ms` and `total_cost_usd` per call directly -- exactly the two numbers
this pilot needs for the latency/cost projection, with no separate token-price
bookkeeping required.

=====================================================================================
PIPELINE STAGES (each idempotent / checkpointed under data/vlm_judge_pilot/,
same "resume for free" posture as build_swatch_library.py's thumb cache)
=====================================================================================
  1. select_sample()   -- deterministic (seed 42) draw from the registry: the
                           4 user-named Oceanside failures + a mix of other
                           Oceanside/Bullseye/Wissmach/Youghiogheny products,
                           spanning both suspicious (low pick_score) and
                           clean-looking (high pick_score) heuristic picks.
  2. fetch_candidates() -- re-scrape each product's `.json` endpoint (Shopify
                           convention: `<product_url>.json` -> `product.images`)
                           for the FULL gallery (registry only kept the winner),
                           throttled ~1 req/s to each host.
  3. build_contact_sheet() -- numbered grid, each candidate downscaled to
                           ~400px, big index labels, saved per product.
  4. judge()            -- one `claude -p` subprocess per (product, model),
                           forced-choice prompt, strict parse with one retry.
  5. run()              -- orchestrates 1-4, writes results.json (this pilot's
                           only output data artifact; the review board + report
                           are built from it by vlm_judge_report.py).

No registry writes anywhere in this file.
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time

import requests
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
REGISTRY_FILE = os.path.join(REPO_ROOT, 'frontend/public/assets/glass_swatch_registry.json')

DATA_DIR = os.path.join(REPO_ROOT, 'data/vlm_judge_pilot')
THUMB_DIR = os.path.join(DATA_DIR, 'thumbs')
SHEET_DIR = os.path.join(DATA_DIR, 'contact_sheets')
SAMPLE_FILE = os.path.join(DATA_DIR, 'sample.json')
RESULTS_FILE = os.path.join(DATA_DIR, 'results.json')

for d in (DATA_DIR, THUMB_DIR, SHEET_DIR):
    os.makedirs(d, exist_ok=True)

HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
REQUEST_DELAY = 1.05  # throttle: ~1 req/s to any single host, per task guardrail

# the 4 user-reported failures this pilot must specifically resolve
NAMED_FAILURE_IDS = {
    'oceanside-of161rr',    # "96 COE Yellow Rough Rolled" -- perspective side view picked
    'oceanside-of23071s',   # "96 COE Hydrangea Blue Opal" -- shop shelf photo picked
    'oceanside-of3176s',    # "96 COE Dark Amber with White Wispy" -- garden/tree photo picked
    'oceanside-of3276s',    # "96 COE Dark Green with White" -- finished stained-glass window picked
    'oceanside-of3296s',    # same name, second SKU variant -- included for coverage, not double-counted as a 5th named failure
}

CONTACT_CELL = 400  # px, per task spec ("downscale each to ~400px")
LABEL_H = 46


# --------------------------------------------------------------------------------
# stage 1: sample selection
# --------------------------------------------------------------------------------

def select_sample(seed=42):
    """Deterministic ~40-product sample: the 4 named Oceanside failures + a mix
    of suspicious (low pick_score) and clean-looking (high pick_score) picks
    across Oceanside/Bullseye/Wissmach/Youghiogheny. Low/high pick_score is used
    as a cheap proxy for "looks suspicious" vs. "looks fine" since we don't have
    a labeled ground truth -- report 035's own floor (0.45) and the observed
    failures (which all still cleared the floor, see task) mean pick_score alone
    is NOT a reliable suspicion signal, just a way to get a spread rather than a
    uniform-random sample that might miss the failure mode entirely.
    """
    with open(REGISTRY_FILE) as f:
        registry = json.load(f)
    by_mfg = {}
    for x in registry:
        by_mfg.setdefault(x['manufacturer'], []).append(x)

    rng = random.Random(seed)

    def sample_mfg(mfg, n_low, n_high, exclude_ids=frozenset()):
        items = [x for x in by_mfg.get(mfg, []) if x['id'] not in exclude_ids and x.get('pick_score') is not None]
        items_sorted = sorted(items, key=lambda x: x['pick_score'])
        low_pool, high_pool = items_sorted[:30], items_sorted[-30:]
        rng.shuffle(low_pool)
        rng.shuffle(high_pool)
        return low_pool[:n_low] + high_pool[:n_high]

    named = [x for x in registry if x['id'] in NAMED_FAILURE_IDS]
    picked = (
        named
        + sample_mfg('Oceanside', 10, 6, exclude_ids=NAMED_FAILURE_IDS)
        + sample_mfg('Bullseye', 6, 4)
        + sample_mfg('Wissmach', 3, 2)
        + sample_mfg('Youghiogheny', 3, 2)
    )
    sample = [{
        'id': x['id'], 'manufacturer': x['manufacturer'], 'name': x['name'],
        'category': x.get('category'), 'product_url': x['product_url'],
        'heuristic_image_url': x['image_url'], 'heuristic_pick_score': x.get('pick_score'),
        'named_failure': x['id'] in NAMED_FAILURE_IDS,
    } for x in picked]
    with open(SAMPLE_FILE, 'w') as f:
        json.dump(sample, f, indent=2)
    print(f"Sample: {len(sample)} products -> {SAMPLE_FILE}")
    return sample


# --------------------------------------------------------------------------------
# stage 2: re-scrape full candidate gallery
# --------------------------------------------------------------------------------

def _strip_query(url):
    return (url or '').split('?')[0]


_last_request_at = {}


def _throttle(host):
    last = _last_request_at.get(host, 0)
    wait = REQUEST_DELAY - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    _last_request_at[host] = time.time()


def fetch_product_json(product_url):
    from urllib.parse import urlparse
    host = urlparse(product_url).netloc
    _throttle(host)
    try:
        r = requests.get(product_url.rstrip('/') + '.json', headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        return r.json().get('product')
    except Exception as e:
        print(f"  fetch_product_json failed for {product_url}: {e}")
        return None


def fetch_candidates(sample, cache_file=None):
    """Populate each sample row with `candidates`: [{'url', 'local_thumb'}], by
    re-scraping the product's live gallery. Idempotent: a product whose thumbs
    are all already on disk is not re-fetched or re-downloaded."""
    cache_file = cache_file or os.path.join(DATA_DIR, 'candidates_cache.json')
    cache = {}
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache = json.load(f)

    for row in sample:
        pid = row['id']
        if pid in cache and cache[pid].get('candidates'):
            row['candidates'] = cache[pid]['candidates']
            row['body_html'] = cache[pid].get('body_html', '')
            continue

        product = fetch_product_json(row['product_url'])
        if not product:
            print(f"  WARNING: could not re-scrape {pid} ({row['name']}) -- 0 candidates")
            row['candidates'] = []
            row['body_html'] = ''
            cache[pid] = {'candidates': [], 'body_html': ''}
            continue

        urls = []
        seen = set()
        for im in product.get('images', []):
            src = im.get('src', '')
            if src.startswith('//'):
                src = 'https:' + src
            key = _strip_query(src)
            if src and key not in seen:
                seen.add(key)
                urls.append(src)

        candidates = []
        from urllib.parse import urlparse
        for i, url in enumerate(urls):
            local = os.path.join(THUMB_DIR, f"{pid}_{i}.jpg")
            if not os.path.exists(local):
                host = urlparse(url).netloc
                _throttle(host)
                try:
                    sep = '&' if '?' in url else '?'
                    r = requests.get(f"{url}{sep}width={CONTACT_CELL}", headers=HEADERS, timeout=15)
                    if r.status_code == 200:
                        with open(local, 'wb') as f:
                            f.write(r.content)
                    else:
                        continue
                except Exception as e:
                    print(f"    thumb fetch failed {url}: {e}")
                    continue
            candidates.append({'url': url, 'local_thumb': local})

        row['candidates'] = candidates
        row['body_html'] = product.get('body_html', '') or ''
        cache[pid] = {'candidates': candidates, 'body_html': row['body_html']}
        print(f"  {pid}: {len(candidates)} candidates re-scraped")

        with open(cache_file, 'w') as f:
            json.dump(cache, f, indent=2)

    return sample


# --------------------------------------------------------------------------------
# stage 3: numbered contact sheet
# --------------------------------------------------------------------------------

def _font(size):
    for path in ('/System/Library/Fonts/Helvetica.ttc', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default(size=size)


def build_contact_sheet(row):
    pid = row['id']
    out_path = os.path.join(SHEET_DIR, f"{pid}.jpg")
    candidates = row['candidates']
    if not candidates:
        return None
    if os.path.exists(out_path) and row.get('_sheet_ok'):
        return out_path

    n = len(candidates)
    cols = min(4, n)
    rows_n = (n + cols - 1) // cols
    cell = CONTACT_CELL
    sheet = Image.new('RGB', (cols * cell, rows_n * (cell + LABEL_H)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    font = _font(30)

    for i, cand in enumerate(candidates):
        r, c = divmod(i, cols)
        x0, y0 = c * cell, r * (cell + LABEL_H)
        # label bar
        draw.rectangle([x0, y0, x0 + cell, y0 + LABEL_H], fill=(20, 90, 200))
        draw.text((x0 + 10, y0 + 6), f"#{i + 1}", fill=(255, 255, 255), font=font)
        try:
            im = Image.open(cand['local_thumb']).convert('RGB')
            im.thumbnail((cell, cell))
            px = x0 + (cell - im.width) // 2
            py = y0 + LABEL_H + (cell - im.height) // 2
            sheet.paste(im, (px, py))
        except Exception as e:
            draw.text((x0 + 10, y0 + LABEL_H + 10), f"(unreadable: {e})", fill=(255, 80, 80), font=_font(16))

    sheet.save(out_path, 'JPEG', quality=88)
    row['_sheet_ok'] = True
    return out_path


# --------------------------------------------------------------------------------
# stage 4: judge (claude CLI subprocess, forced-choice)
# --------------------------------------------------------------------------------

PROMPT_TMPL = """Read the numbered contact-sheet image at {sheet_path}. It contains {n} candidate product photos (numbered #1 to #{n}) scraped from a stained/fusible glass retailer's product gallery for one product.

Product: {name}
Description hint: {desc}

Which numbered image is a straight-on, flat, full-frame photograph of the GLASS SHEET/SWATCH ITSELF -- not a finished project (e.g. a window, ornament, or fused piece made FROM the glass), not a shop/warehouse shelf photo, not packaging or a label, not an angled/perspective/side view of the sheet, not a room or lifestyle scene, not a customer's hand/finger in frame, and not a comparison shot of two+ sheets side by side?

Answer with ONLY the number (e.g. "3"), or the single word NONE if no candidate qualifies. No other text, no explanation, no punctuation."""

RETRY_PROMPT_TMPL = """Your previous answer could not be parsed as a single number or the word NONE. Look again at {sheet_path} ({n} candidates, product: {name}). Reply with EXACTLY one token: either a bare integer between 1 and {n}, or the word NONE. Nothing else -- no sentence, no period, no explanation."""

_ANSWER_RE = re.compile(r'^\s*(\d{1,2}|NONE)\s*\.?\s*$', re.IGNORECASE)
_FALLBACK_NUM_RE = re.compile(r'\b(\d{1,2})\b')


def _parse_answer(text, n):
    text = (text or '').strip()
    m = _ANSWER_RE.match(text)
    if m:
        tok = m.group(1)
        if tok.upper() == 'NONE':
            return 'NONE'
        v = int(tok)
        return v if 1 <= v <= n else None
    if 'NONE' in text.upper() and len(text) < 40:
        return 'NONE'
    nums = [int(x) for x in _FALLBACK_NUM_RE.findall(text) if 1 <= int(x) <= n]
    if len(nums) == 1:
        return nums[0]
    return None


def _call_claude(prompt, model, timeout=120):
    cmd = ['claude', '-p', prompt, '--model', model, '--allowedTools', 'Read',
           '--permission-mode', 'bypassPermissions', '--output-format', 'json']
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=REPO_ROOT)
    except subprocess.TimeoutExpired:
        return {'error': 'timeout', 'latency_ms': int((time.time() - t0) * 1000)}
    latency_ms = int((time.time() - t0) * 1000)
    try:
        data = json.loads(proc.stdout)
    except Exception:
        return {'error': f'unparseable CLI output (rc={proc.returncode}): {proc.stdout[:300]!r} {proc.stderr[:300]!r}',
                'latency_ms': latency_ms}
    return {
        'text': data.get('result', ''),
        'latency_ms': data.get('duration_ms', latency_ms),
        'cost_usd': data.get('total_cost_usd'),
        'is_error': data.get('is_error'),
    }


def judge_one(row, model):
    sheet_path = row.get('_sheet_path')
    n = len(row['candidates'])
    desc = re.sub(r'<[^>]+>', ' ', row.get('body_html') or '').strip()[:400] or '(none)'
    prompt = PROMPT_TMPL.format(sheet_path=sheet_path, n=n, name=row['name'], desc=desc)
    resp = _call_claude(prompt, model)
    if 'error' in resp:
        return {'pick': None, 'raw': resp.get('error'), 'latency_ms': resp['latency_ms'],
                'cost_usd': None, 'parse_ok': False, 'retried': False}

    parsed = _parse_answer(resp['text'], n)
    retried = False
    total_latency = resp['latency_ms']
    total_cost = resp.get('cost_usd') or 0.0
    if parsed is None:
        retried = True
        retry_prompt = RETRY_PROMPT_TMPL.format(sheet_path=sheet_path, n=n, name=row['name'])
        resp2 = _call_claude(retry_prompt, model)
        total_latency += resp2.get('latency_ms', 0)
        total_cost += (resp2.get('cost_usd') or 0.0)
        parsed = _parse_answer(resp2.get('text', ''), n) if 'error' not in resp2 else None
        raw = f"{resp['text']!r} -> retry {resp2.get('text', resp2.get('error'))!r}"
    else:
        raw = resp['text']

    return {'pick': parsed, 'raw': raw, 'latency_ms': total_latency,
            'cost_usd': round(total_cost, 6), 'parse_ok': parsed is not None, 'retried': retried}


# --------------------------------------------------------------------------------
# heuristic-pick index resolution (which candidate # is what the heuristic shipped)
# --------------------------------------------------------------------------------

def resolve_heuristic_index(row):
    target = _strip_query(row.get('heuristic_image_url'))
    for i, c in enumerate(row['candidates']):
        if _strip_query(c['url']) == target:
            return i + 1  # 1-indexed to match judge's numbering
    return None


# --------------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------------

def run(models=('sonnet', 'haiku'), limit=None, resume=True):
    if resume and os.path.exists(SAMPLE_FILE):
        with open(SAMPLE_FILE) as f:
            sample = json.load(f)
        print(f"Resumed sample ({len(sample)} products) from {SAMPLE_FILE}")
    else:
        sample = select_sample()

    if limit:
        sample = sample[:limit]

    fetch_candidates(sample)

    results = []
    if resume and os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            prior = {r['id']: r for r in json.load(f)}
    else:
        prior = {}

    for idx, row in enumerate(sample):
        pid = row['id']
        print(f"[{idx + 1}/{len(sample)}] {pid} -- {row['name']} ({len(row['candidates'])} candidates)")
        if not row['candidates']:
            results.append({**row, 'skipped': 'no candidates re-scraped'})
            continue

        sheet_path = build_contact_sheet(row)
        row['_sheet_path'] = sheet_path
        heuristic_idx = resolve_heuristic_index(row)

        entry = prior.get(pid, {})
        entry.update({
            'id': pid, 'manufacturer': row['manufacturer'], 'name': row['name'],
            'category': row.get('category'), 'named_failure': row.get('named_failure', False),
            'product_url': row['product_url'],
            'n_candidates': len(row['candidates']),
            'candidate_urls': [c['url'] for c in row['candidates']],
            'heuristic_image_url': row['heuristic_image_url'],
            'heuristic_pick_score': row.get('heuristic_pick_score'),
            'heuristic_pick_index': heuristic_idx,
            'contact_sheet': os.path.relpath(sheet_path, REPO_ROOT) if sheet_path else None,
        })

        for model in models:
            key = f'judge_{model}'
            if key in entry and entry[key].get('parse_ok') is not None:
                continue  # already judged by this model, resume-skip
            print(f"    judging with {model}...")
            j = judge_one(row, model)
            entry[key] = j
            print(f"    {model} -> {j['pick']} ({j['latency_ms']}ms, ${j.get('cost_usd')}, parse_ok={j['parse_ok']})")
            with_results = [r for r in results if r['id'] != pid] + [entry]
            # incremental checkpoint save after every judge call (cheap insurance
            # against a mid-run interruption re-paying for already-answered calls)
            _save_results(with_results + [e for e in prior.values() if e['id'] not in {r['id'] for r in with_results}])

        results = [r for r in results if r['id'] != pid] + [entry]
        _save_results(results)

    _save_results(results)
    print(f"\nDone. {len(results)} products judged -> {RESULTS_FILE}")
    return results


def _save_results(results):
    # de-dup by id, keep insertion order stable-ish
    seen = {}
    for r in results:
        seen[r['id']] = r
    with open(RESULTS_FILE, 'w') as f:
        json.dump(list(seen.values()), f, indent=2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--models', default='sonnet,haiku', help='comma-separated claude CLI model aliases')
    ap.add_argument('--limit', type=int, default=None, help='cap sample size (debug)')
    ap.add_argument('--no-resume', action='store_true', help='ignore any existing sample/results checkpoints')
    ap.add_argument('--sample-only', action='store_true', help='just (re)generate the sample and exit')
    args = ap.parse_args()

    if args.sample_only:
        select_sample()
        return

    run(models=tuple(m.strip() for m in args.models.split(',') if m.strip()),
        limit=args.limit, resume=not args.no_resume)


if __name__ == '__main__':
    main()
