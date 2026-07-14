"""vlm_judge_striker.py -- corpus-wide sonnet-judge pass over every registry
row flagged `striker: true` by build_swatch_library.py's striker classifier
(see its cache_bullseye_strikers()/is_wissmach_striker() docstrings).

Policy (coordinator, 2026-07-13): striker/striking glass ships in a pale,
unfired/unstruck state and only develops its full named color once the
CUSTOMER fires it in a kiln. A product photo showing the vivid, fully
developed/struck color misrepresents what actually ships -- the registry
should show the pale, as-shipped sheet instead. Two concrete failures
motivated this: bullseye-0002430030f1010 (Translucent White, fixed in
vlm_judge_targeted.py's pass) and bullseye-0003050050f1010 (Salmon Pink,
2mm) which turned out to ship an entirely WRONG photo (a blue textured
sheet -- a gallery data error, not just a fired/unfired mismatch) whose OWN
gallery has no pale alternative at all.

Reuses scripts/vlm_pick_judge.py's fetch/contact-sheet/`claude -p` judge
machinery (as `pilot`) and scripts/vlm_judge_targeted.py's registry-patch
application (crop/border-scrub conventions, as `targeted`) -- this script
only supplies its own judge PROMPT_TMPL (pale-vs-fired instead of the
pilot's generic "which is a flat sheet photo") and its own target-selection
(every `striker: true` row, not a fixed list).

Checkpointed/resumable like its siblings: data/vlm_judge_striker/results.json
is loaded and skipped-past on every re-run unless --force is passed for a
specific id.
"""
import argparse
import json
import os
import re
import sys
import time

import requests
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vlm_pick_judge as pilot  # noqa: E402  (fetch/sheet/judge machinery)
import vlm_judge_targeted as targeted  # noqa: E402  (apply_winner, crop/scrub conventions)

REPO_ROOT = pilot.REPO_ROOT
REGISTRY_FILE = pilot.REGISTRY_FILE
IMAGE_DIR = os.path.join(REPO_ROOT, 'frontend/public/assets/catalog_images')
OUT_DIR = os.path.join(REPO_ROOT, 'docs/library-picker-rebuild')
DATA_DIR = os.path.join(REPO_ROOT, 'data/vlm_judge_striker')
THUMB_DIR = os.path.join(DATA_DIR, 'thumbs')
SHEET_DIR = os.path.join(DATA_DIR, 'contact_sheets')
CANDIDATES_CACHE = os.path.join(DATA_DIR, 'candidates_cache.json')
RESULTS_FILE = os.path.join(DATA_DIR, 'results.json')
BOARD_PATH = os.path.join(OUT_DIR, 'vlm_judge_striker_board.jpg')
for d in (DATA_DIR, THUMB_DIR, SHEET_DIR):
    os.makedirs(d, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)

# monkeypatch the pilot's thumb/sheet dirs so this run's fetches land under
# THIS script's own data dir rather than data/vlm_judge_pilot/ (separate,
# independently-resumable checkpoint state)
pilot.THUMB_DIR = THUMB_DIR
pilot.SHEET_DIR = SHEET_DIR

JUDGE_MODEL = 'sonnet'
PROVENANCE_TMPL = 'vlm-judge sonnet striker-audit pass 2026-07-13 (pale/unfired vs fired)'

PROMPT_TMPL = """Read the numbered contact-sheet image at {sheet_path}. It contains {n} candidate product photos (numbered #1 to #{n}) scraped from a stained/fusible glass retailer's product gallery for ONE product.

Product: {name}

This is a STRIKING glass color: it SHIPS to customers in a pale, muted, unfired/unstruck state and only develops its full named color ("{strikes_to}") after the customer fires it themselves in a kiln. A product photo showing the vivid, richly saturated, fully-developed/struck color misrepresents what the customer actually receives -- we want the photo that shows the glass in its PALE, muted, AS-SHIPPED (unfired) appearance instead.

Which numbered candidate is a straight-on, full-frame photo of the actual glass sheet/swatch itself (not a finished project, not a shop/warehouse shelf photo, not an angled/perspective/side view, not a room/lifestyle scene, not two-or-more sheets compared side by side, not packaging/label-only) that ALSO shows the glass in its PALE, muted, UNFIRED appearance rather than a vivid/richly-saturated fired appearance?

IMPORTANT gallery-mixup check: a candidate's product LABEL/sticker in the photo can be wrong or mismatched (a vendor data error). Judge the actual GLASS COLOR shown, not the label text. If a candidate shows a color that is not plausibly a paler/unfired version of "{strikes_to}" at all -- e.g. a completely different hue family (blue glass for a product that should be pink/red/orange/yellow, etc.) -- it is NOT a valid candidate even if its attached label says otherwise; do not pick it and do not let it count as "the pale option exists." A small correctly-matching price tag/spec label/sticker on the glass is fine and does not disqualify an otherwise-correct candidate.

If every candidate that is a valid, correctly-colored straight-on sheet photo only shows the vivid/fired color (no correctly-colored pale/unfired option exists in this gallery), answer NONE. If none of the candidates are even a valid, correctly-colored sheet photo at all, also answer NONE.

Answer with ONLY the number (e.g. "3"), or the single word NONE. No other text, no explanation, no punctuation."""

RETRY_PROMPT_TMPL = """Your previous answer could not be parsed as a single number or the word NONE. Look again at {sheet_path} ({n} candidates, product: {name}, a striking glass color that should show its PALE unfired appearance, not its vivid fired color). Reply with EXACTLY one token: either a bare integer between 1 and {n}, or the word NONE. Nothing else -- no sentence, no period, no explanation."""


def judge_striker_one(row, model):
    sheet_path = row.get('_sheet_path')
    n = len(row['candidates'])
    prompt = PROMPT_TMPL.format(sheet_path=sheet_path, n=n, name=row['name'],
                                 strikes_to=row.get('strikes_to') or row['name'])
    resp = pilot._call_claude(prompt, model)
    if 'error' in resp:
        return {'pick': None, 'raw': resp.get('error'), 'latency_ms': resp['latency_ms'],
                'cost_usd': None, 'parse_ok': False, 'retried': False}

    parsed = pilot._parse_answer(resp['text'], n)
    retried = False
    total_latency = resp['latency_ms']
    total_cost = resp.get('cost_usd') or 0.0
    if parsed is None:
        retried = True
        retry_prompt = RETRY_PROMPT_TMPL.format(sheet_path=sheet_path, n=n, name=row['name'])
        resp2 = pilot._call_claude(retry_prompt, model)
        total_latency += resp2.get('latency_ms', 0)
        total_cost += (resp2.get('cost_usd') or 0.0)
        parsed = pilot._parse_answer(resp2.get('text', ''), n) if 'error' not in resp2 else None
        raw = f"{resp['text']!r} -> retry {resp2.get('text', resp2.get('error'))!r}"
    else:
        raw = resp['text']

    return {'pick': parsed, 'raw': raw, 'latency_ms': total_latency,
            'cost_usd': round(total_cost, 6), 'parse_ok': parsed is not None, 'retried': retried}


def select_targets(priority_only=False):
    """Every `striker: true` registry row. `priority_only` restricts to the
    literal-name "Striker" matches plus the hand-confirmed hidden cases -- used
    for a first, fast pass before the full sweep."""
    with open(REGISTRY_FILE) as f:
        registry = json.load(f)
    strikers = [r for r in registry if r.get('striker')]
    if not priority_only:
        return strikers
    KNOWN_HIDDEN = {
        'bullseye-0002430030f1010', 'bullseye-0002430050f1010',  # Translucent White
        'bullseye-0003050030f1010', 'bullseye-0003050050f1010',  # Salmon Pink
        'wissmach-wf40105', 'wissmach-wf40lum105', 'wissmach-wf41105',  # explicit Wissmach
    }
    out = []
    for r in strikers:
        if re.search(r'\bstriker\b', r['name'], re.IGNORECASE) or r['id'] in KNOWN_HIDDEN:
            out.append(r)
    return out


def _old_thumb_for(row, shipped_idx):
    if shipped_idx:
        return row['candidates'][shipped_idx - 1]['local_thumb']
    old_thumb = os.path.join(THUMB_DIR, f"{row['id']}_shipped.jpg")
    if not os.path.exists(old_thumb):
        try:
            url = row['heuristic_image_url']
            sep = '&' if '?' in url else '?'
            r = requests.get(f"{url}{sep}width=400", headers=pilot.HEADERS, timeout=15)
            r.raise_for_status()
            with open(old_thumb, 'wb') as f:
                f.write(r.content)
        except Exception:
            return None
    return old_thumb


def run(target_ids=None, priority_only=False, force_ids=None, limit=None):
    force_ids = set(force_ids or [])
    targets = select_targets(priority_only=priority_only)
    if target_ids:
        want = set(target_ids)
        targets = [t for t in targets if t['id'] in want]
    if limit:
        targets = targets[:limit]
    print(f"Auditing {len(targets)} striker rows ({'priority subset' if priority_only else 'full sweep'}).")

    results = {}
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            results = {r['id']: r for r in json.load(f)}

    registry = targeted.load_registry()
    by_id = {r['id']: r for r in registry}
    board_rows = []
    changed_this_run = []

    for idx, reg in enumerate(targets):
        tid = reg['id']
        if tid in results and tid not in force_ids:
            print(f"[{idx+1}/{len(targets)}] {tid} -- already audited ({results[tid].get('verdict')}), skip")
            continue
        print(f"[{idx+1}/{len(targets)}] {tid} -- {reg['name']}  (strikes_to={reg.get('strikes_to')!r})")

        row = {
            'id': tid, 'manufacturer': reg['manufacturer'], 'name': reg['name'],
            'product_url': reg['product_url'], 'heuristic_image_url': reg['image_url'],
            'strikes_to': reg.get('strikes_to'),
        }
        pilot.fetch_candidates([row], cache_file=CANDIDATES_CACHE)
        if not row['candidates']:
            outcome = {'id': tid, 'name': reg['name'], 'verdict': 'ERROR: gallery re-scrape failed'}
            results[tid] = outcome
            _save(results)
            continue

        sheet = pilot.build_contact_sheet(row)
        row['_sheet_path'] = sheet
        shipped_idx = pilot.resolve_heuristic_index(row)
        j = judge_striker_one(row, JUDGE_MODEL)
        print(f"  shipped=#{shipped_idx}  {JUDGE_MODEL}={j['pick']}  ({j['latency_ms']}ms ${j.get('cost_usd')})")

        outcome = {
            'id': tid, 'name': reg['name'], 'manufacturer': reg['manufacturer'],
            'strikes_to': reg.get('strikes_to'), 'n_candidates': len(row['candidates']),
            'candidate_urls': [c['url'] for c in row['candidates']],
            'shipped_index': shipped_idx, 'judge_pick': j['pick'], 'judge_raw': j['raw'],
            'latency_ms': j['latency_ms'], 'cost_usd': j['cost_usd'],
        }

        if j['pick'] == 'NONE':
            outcome['verdict'] = 'NONE -- no pale/unfired candidate in this gallery; shipped pick left as-is'
        elif j['pick'] is None:
            outcome['verdict'] = 'PARSE FAILURE -- no action taken'
        elif j['pick'] == shipped_idx:
            outcome['verdict'] = 'CONFIRMED -- judge agrees the shipped pick already shows the pale/unfired look'
        else:
            winner_url = row['candidates'][j['pick'] - 1]['url']
            live_reg = by_id.get(tid)
            if live_reg is None:
                outcome['verdict'] = 'ERROR: id not found in live registry at apply time'
            else:
                provenance = PROVENANCE_TMPL
                crop_info, feats = targeted.apply_winner(live_reg, winner_url, j)
                live_reg['vlm_judge'] = provenance
                outcome['verdict'] = f"CHANGED -- #{shipped_idx} -> #{j['pick']}"
                outcome['winner_url'] = winner_url
                outcome['applied_crop'] = crop_info
                changed_this_run.append(tid)
                old_thumb = _old_thumb_for(row, shipped_idx)
                new_thumb = row['candidates'][j['pick'] - 1]['local_thumb']
                board_rows.append((f"{reg['name'][:46]}", old_thumb, new_thumb, tid))
                targeted.save_registry(registry)
                print(f"  -> APPLIED: pick changed to pale candidate #{j['pick']}, registry patched")

        results[tid] = outcome
        _save(results)

    print(f"\nDone. {len(results)} striker rows audited -> {RESULTS_FILE}")
    print(f"Changed this run: {len(changed_this_run)}")
    if board_rows:
        build_board(board_rows)
    return results


def _save(results):
    with open(RESULTS_FILE, 'w') as f:
        json.dump(list(results.values()), f, indent=2)


def build_board(board_rows):
    CELL, LABEL_H = 380, 62
    cols, n = 2, len(board_rows)
    W = cols * CELL
    H = n * (CELL + LABEL_H) + 44
    board = Image.new('RGB', (W, H), (16, 16, 16))
    draw = ImageDraw.Draw(board)
    font = pilot._font(24)
    small = pilot._font(18)
    draw.text((10, 8), 'old shipped pick (fired/wrong)', fill=(255, 160, 160), font=font)
    draw.text((CELL + 10, 8), 'VLM judge pick -> APPLIED (pale/unfired)', fill=(150, 230, 150), font=font)
    y = 44
    for label, old_t, new_t, tid in board_rows:
        draw.rectangle([0, y, W, y + LABEL_H], fill=(30, 30, 30))
        draw.text((10, y + 6), label, fill=(255, 255, 255), font=font)
        draw.text((10, y + 34), tid, fill=(160, 160, 160), font=small)
        for i, t in enumerate((old_t, new_t)):
            x0 = i * CELL
            yy = y + LABEL_H
            if t and os.path.exists(t):
                im = Image.open(t).convert('RGB')
                im.thumbnail((CELL - 4, CELL - 4))
                board.paste(im, (x0 + (CELL - im.width) // 2, yy + (CELL - im.height) // 2))
            else:
                draw.text((x0 + 12, yy + 20), '(unavailable)', fill=(255, 90, 90), font=small)
        y += CELL + LABEL_H
    board.save(BOARD_PATH, 'JPEG', quality=90)
    print(f"Board -> {BOARD_PATH}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--priority-only', action='store_true',
                     help='only the 29 literal-"Striker"-named + hand-confirmed hidden cases')
    ap.add_argument('--ids', default=None, help='comma-separated registry ids to restrict to')
    ap.add_argument('--force', default=None, help='comma-separated ids to re-audit even if already in results.json')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()
    target_ids = [x.strip() for x in args.ids.split(',')] if args.ids else None
    force_ids = [x.strip() for x in args.force.split(',')] if args.force else None
    run(target_ids=target_ids, priority_only=args.priority_only, force_ids=force_ids, limit=args.limit)


if __name__ == '__main__':
    main()
