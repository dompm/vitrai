"""vlm_judge_targeted.py -- targeted sonnet-judge pass over the user-flagged
problem products, applying winning picks to the committed registry.

Follow-up to the 41-product pilot (scripts/vlm_pick_judge.py, whose fetch/
contact-sheet/judge machinery this reuses) while the full-corpus decision is
pending. Targets (from the coordinator, 2026-07-13):

  1. bullseye-0002430030f1010  Translucent White, Double-rolled 3 mm -- shipped
                                pick is the product-LABEL macro (_04.jpg).
  2. bullseye-0011010000f1010  Clear Transparent, Single-rolled 3 mm -- report.md
                                "needs-VLM-judge": gallery is one side-view image;
                                expected NONE -> keep shipped, note second-source.
  3. bullseye-0012470031f1010  Light Mineral Green Transparent Irid -- report.md
                                "needs-VLM-judge": all candidates washed; judge
                                confirming the shipped pick is a valid outcome.
  4. bullseye-0001130050f1010  White Opalescent, Thin-rolled 2 mm  \\ the white-glass
  5. bullseye-0002430050f1010  Translucent White, Thin-rolled 2 mm / detector blind spot

Application path (winner differs from shipped): download the full-res winner,
run scripts/swatch_picker.py's `bullseye_features` grip/whole-sheet detector on
it, and if it is a whole-sheet-on-white/grip photo apply the authoritative
full-res border scrub + crop -- byte-for-byte the same discipline as
scripts/sweep_uncropped_bullseye.py (PR #128), which is the direct precedent
for a targeted in-place registry patch outside a full build. The registry row
gets: new image_url, pick_score=None + vlm_judge provenance marker (same
posture as the manual-override rows, whose pick_score is also null because a
human/judge, not the heuristic, chose the image), cropped/crop_box/real-world
dims per the sweep's conventions.

NOTE: catalog_images/ is gitignored runtime data; this worktree does not have
the fleet's image files. The full-res winner is downloaded/cropped into THIS
worktree's catalog_images so the registry row's pixel fields (crop_box,
original px) are computed from real bytes; the main checkout picks up the new
image on its next `build_swatch_library.py` run (its Phase C force-refetch
triggers exactly when registry image_url != what's on disk).
"""
import json
import os
import sys
import time

import numpy as np
import requests
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from swatch_picker import bullseye_features, _scrub_crop_box  # noqa: E402
import vlm_pick_judge as pilot  # noqa: E402  (fetch/sheet/judge machinery)

REPO_ROOT = pilot.REPO_ROOT
REGISTRY_FILE = pilot.REGISTRY_FILE
IMAGE_DIR = os.path.join(REPO_ROOT, 'frontend/public/assets/catalog_images')
OUT_DIR = os.path.join(REPO_ROOT, 'docs/library-picker-rebuild')
DATA_DIR = os.path.join(REPO_ROOT, 'data/vlm_judge_targeted')
RESULTS_FILE = os.path.join(DATA_DIR, 'targeted_results.json')
BOARD_PATH = os.path.join(OUT_DIR, 'vlm_judge_targeted_board.jpg')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)

TARGET_IDS = [
    'bullseye-0002430030f1010',
    'bullseye-0011010000f1010',
    'bullseye-0012470031f1010',
    'bullseye-0001130050f1010',
    'bullseye-0002430050f1010',
]

JUDGE_MODEL = 'sonnet'
PROVENANCE = 'vlm-judge sonnet targeted pass 2026-07-13'


def load_registry():
    with open(REGISTRY_FILE) as f:
        return json.load(f)


def save_registry(registry):
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(registry, f, indent=2)


def fetch_fullres(url, dest):
    from urllib.parse import urlparse
    pilot._throttle(urlparse(url).netloc)
    r = requests.get(url, headers=pilot.HEADERS, timeout=20)
    r.raise_for_status()
    with open(dest, 'wb') as f:
        f.write(r.content)
    return dest


DARK_THRESH = 60          # grayscale value under which a pixel counts as "black background"
DARK_COL_FRAC = 0.05      # a row/col is contaminated if >5% of its pixels are dark
DARK_SCAN_FRAC = 0.25     # only scan the outer quarter from each edge
DARK_INSET_PX = 8         # safety inset past the last contaminated row/col
DARK_MAX_AREA_LOSS = 0.20 # give up (ship uncropped) rather than eat >20% of the frame
DARK_VERIFY_BAND = 12     # post-crop border band that must be clean


def _dark_edge_trim(a):
    """Rectangular trim of near-black background bands at the frame edges, with
    self-verification -- the dark-mask analogue of swatch_picker._scrub_crop_box,
    and the generalization of report.md's bespoke dark-corner scrub for
    bullseye-0003130050f1010 ('flagging for a future pass to generalize if more
    products with this contamination class turn up' -- this targeted pass turned
    one up: the Translucent White winner sits on a black ground that the white-
    background scrub cannot see). Returns crop box [x0,y0,x1,y1] px or None
    (= nothing to trim, or trim untrustworthy)."""
    h, w = a.shape[:2]
    gray = a.mean(axis=2)
    dark = gray < DARK_THRESH
    colfrac = dark.mean(axis=0)
    rowfrac = dark.mean(axis=1)

    x0 = 0
    for x in range(int(w * DARK_SCAN_FRAC)):
        if colfrac[x] > DARK_COL_FRAC:
            x0 = x + 1
    x1 = w
    for x in range(w - 1, int(w * (1 - DARK_SCAN_FRAC)), -1):
        if colfrac[x] > DARK_COL_FRAC:
            x1 = x
    y0 = 0
    for y in range(int(h * DARK_SCAN_FRAC)):
        if rowfrac[y] > DARK_COL_FRAC:
            y0 = y + 1
    y1 = h
    for y in range(h - 1, int(h * (1 - DARK_SCAN_FRAC)), -1):
        if rowfrac[y] > DARK_COL_FRAC:
            y1 = y

    if (x0, y0, x1, y1) == (0, 0, w, h):
        return None  # clean frame, nothing to do
    x0 = min(x0 + DARK_INSET_PX, w // 3)
    y0 = min(y0 + DARK_INSET_PX, h // 3)
    x1 = max(x1 - DARK_INSET_PX, 2 * w // 3)
    y1 = max(y1 - DARK_INSET_PX, 2 * h // 3)
    if (x1 - x0) * (y1 - y0) < (1 - DARK_MAX_AREA_LOSS) * w * h:
        return None  # too much loss -- untrustworthy, ship uncropped instead
    # self-verify: the trimmed frame's own border bands must now be clean
    sub = dark[y0:y1, x0:x1]
    b = DARK_VERIFY_BAND
    for band in (sub[:b, :], sub[-b:, :], sub[:, :b], sub[:, -b:]):
        if band.mean() > DARK_COL_FRAC:
            return None
    return [x0, y0, x1, y1]


def apply_winner(row_reg, winner_url, judge_meta):
    """Registry-row patch for a judge-chosen image, sweep-script conventions."""
    fn = os.path.basename(row_reg['local_image'])
    path = os.path.join(IMAGE_DIR, fn)
    fetch_fullres(winner_url, path)

    img = Image.open(path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
        img.save(path, 'JPEG')
    w, h = img.size

    feats = bullseye_features(path)
    crop_frac = feats.get('crop_box_frac')
    applied_crop = None
    if feats.get('is_whole_sheet_on_white') and crop_frac is not None:
        a_full = np.asarray(img, dtype=np.uint8)
        scrubbed, detail = _scrub_crop_box(a_full, crop_frac)
        if scrubbed is not None:
            x0f, y0f, x1f, y1f = scrubbed
            crop_box = [int(x0f * w), int(y0f * h), int(x1f * w), int(y1f * h)]
            img.crop(crop_box).save(path, 'JPEG')
            is_half = 'HALF' in row_reg['base_sku'].upper()
            base_w = 17.0 if is_half else 10.0
            base_h = 20.0 if is_half else 10.0
            row_reg['cropped'] = True
            row_reg['crop_box'] = crop_box
            row_reg['real_world_width_in'] = round(base_w * (x1f - x0f), 2)
            row_reg['real_world_height_in'] = round(base_h * (y1f - y0f), 2)
            applied_crop = {'crop_box': crop_box, 'area_kept': detail.get('area_kept'),
                            'grip_flag': feats.get('grip_flag')}
        else:
            # scrub failed -> ship the winner uncropped rather than a dirty crop
            row_reg['cropped'] = False
            row_reg['crop_box'] = None
            row_reg['real_world_width_in'] = 10.0
            row_reg['real_world_height_in'] = 10.0
    else:
        # not a whole-sheet-on-WHITE photo -- check instead for black background
        # bands at the frame edges (dark-ground variant of the same contamination)
        a_full = np.asarray(img, dtype=np.uint8)
        crop_box = _dark_edge_trim(a_full)
        if crop_box is not None:
            img.crop(crop_box).save(path, 'JPEG')
            x0, y0, x1, y1 = crop_box
            row_reg['cropped'] = True
            row_reg['crop_box'] = crop_box
            row_reg['real_world_width_in'] = round(10.0 * (x1 - x0) / w, 2)
            row_reg['real_world_height_in'] = round(10.0 * (y1 - y0) / h, 2)
            applied_crop = {'crop_box': crop_box, 'kind': 'dark_edge_trim',
                            'area_kept': round((x1 - x0) * (y1 - y0) / (w * h), 4)}
        else:
            row_reg['cropped'] = False
            row_reg['crop_box'] = None
            row_reg['real_world_width_in'] = 10.0
            row_reg['real_world_height_in'] = 10.0

    row_reg['image_url'] = winner_url
    row_reg['pick_score'] = None  # heuristic did not choose this -- judge did
    row_reg['vlm_judge'] = PROVENANCE
    row_reg['original_width_px'] = w
    row_reg['original_height_px'] = h
    return applied_crop, feats


def main():
    registry = load_registry()
    by_id = {r['id']: r for r in registry}

    outcomes = []
    board_rows = []  # (label, old_thumb_path, new_thumb_path)

    for tid in TARGET_IDS:
        reg = by_id.get(tid)
        if not reg:
            outcomes.append({'id': tid, 'verdict': 'ERROR: not in registry'})
            continue
        print(f"=== {tid} -- {reg['name']}")

        row = {
            'id': tid, 'manufacturer': reg['manufacturer'], 'name': reg['name'],
            'product_url': reg['product_url'], 'heuristic_image_url': reg['image_url'],
        }
        pilot.fetch_candidates([row])
        if not row['candidates']:
            outcomes.append({'id': tid, 'verdict': 'ERROR: gallery re-scrape failed'})
            continue

        sheet = pilot.build_contact_sheet(row)
        row['_sheet_path'] = sheet
        shipped_idx = pilot.resolve_heuristic_index(row)
        j = pilot.judge_one(row, JUDGE_MODEL)
        print(f"  shipped=#{shipped_idx}  {JUDGE_MODEL}={j['pick']}  ({j['latency_ms']}ms ${j['cost_usd']})")

        outcome = {
            'id': tid, 'name': reg['name'], 'n_candidates': len(row['candidates']),
            'candidate_urls': [c['url'] for c in row['candidates']],
            'shipped_index': shipped_idx, 'judge_pick': j['pick'],
            'judge_raw': j['raw'], 'latency_ms': j['latency_ms'], 'cost_usd': j['cost_usd'],
        }

        old_thumb = None
        if shipped_idx:
            old_thumb = row['candidates'][shipped_idx - 1]['local_thumb']
        else:
            # shipped URL not in the current gallery -- fetch its own thumb for the board
            old_thumb = os.path.join(pilot.THUMB_DIR, f"{tid}_shipped.jpg")
            if not os.path.exists(old_thumb):
                try:
                    url = reg['image_url']
                    sep = '&' if '?' in url else '?'
                    r = requests.get(f"{url}{sep}width=400", headers=pilot.HEADERS, timeout=15)
                    r.raise_for_status()
                    with open(old_thumb, 'wb') as f:
                        f.write(r.content)
                except Exception:
                    old_thumb = None

        if j['pick'] == 'NONE':
            outcome['verdict'] = 'NONE -- no qualifying candidate; shipped pick left as-is (second-source case)'
        elif j['pick'] is None:
            outcome['verdict'] = 'PARSE FAILURE -- no action taken'
        elif j['pick'] == shipped_idx:
            outcome['verdict'] = 'CONFIRMED -- judge agrees with the shipped pick, no change'
        else:
            winner_url = row['candidates'][j['pick'] - 1]['url']
            crop_info, feats = apply_winner(reg, winner_url, j)
            outcome['verdict'] = f"CHANGED -- #{shipped_idx} -> #{j['pick']}"
            outcome['winner_url'] = winner_url
            outcome['applied_crop'] = crop_info
            outcome['detector'] = {k: feats.get(k) for k in
                                    ('is_full_bleed', 'is_whole_sheet_on_white', 'grip_flag')}
            new_thumb = row['candidates'][j['pick'] - 1]['local_thumb']
            board_rows.append((f"{reg['name'][:46]}", old_thumb, new_thumb, tid))

        outcomes.append(outcome)

    save_registry(registry)
    with open(RESULTS_FILE, 'w') as f:
        json.dump(outcomes, f, indent=2)
    print(f"\nOutcomes -> {RESULTS_FILE}; registry updated in place ({REGISTRY_FILE})")

    if board_rows:
        build_board(board_rows)


def build_board(board_rows):
    CELL, LABEL_H = 380, 62
    cols, n = 2, len(board_rows)
    W = cols * CELL
    H = n * (CELL + LABEL_H) + 44
    board = Image.new('RGB', (W, H), (16, 16, 16))
    draw = ImageDraw.Draw(board)
    font = pilot._font(24)
    small = pilot._font(18)
    draw.text((10, 8), 'old shipped pick', fill=(255, 160, 160), font=font)
    draw.text((CELL + 10, 8), 'VLM judge (sonnet) pick -> APPLIED', fill=(150, 230, 150), font=font)
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
    print(f"Mini board -> {BOARD_PATH}")


def rebuild_board():
    """Regenerate the mini board from targeted_results.json + the registry,
    using the FINAL on-disk image (post-crop) for the 'new' side."""
    with open(RESULTS_FILE) as f:
        outcomes = json.load(f)
    registry = load_registry()
    by_id = {r['id']: r for r in registry}
    rows = []
    for o in outcomes:
        if not o.get('winner_url'):
            continue
        reg = by_id[o['id']]
        old_idx = o.get('shipped_index')
        old_thumb = os.path.join(pilot.THUMB_DIR, f"{o['id']}_{old_idx - 1}.jpg") if old_idx else \
            os.path.join(pilot.THUMB_DIR, f"{o['id']}_shipped.jpg")
        new_img = os.path.join(IMAGE_DIR, os.path.basename(reg['local_image']))
        rows.append((reg['name'][:46], old_thumb, new_img, o['id']))
    if rows:
        build_board(rows)


def reapply(target_id):
    """Redo just the apply step (download/crop/registry patch) for an id whose
    judge verdict is already recorded in targeted_results.json -- no new judge
    call. Used after improving the crop path (e.g. the dark-edge trim) so the
    already-paid-for verdict doesn't need re-judging."""
    with open(RESULTS_FILE) as f:
        outcomes = json.load(f)
    outcome = next((o for o in outcomes if o['id'] == target_id), None)
    if not outcome or not outcome.get('winner_url'):
        raise SystemExit(f"{target_id} has no recorded CHANGED verdict to reapply")
    registry = load_registry()
    reg = next(r for r in registry if r['id'] == target_id)
    crop_info, feats = apply_winner(reg, outcome['winner_url'], None)
    outcome['applied_crop'] = crop_info
    save_registry(registry)
    with open(RESULTS_FILE, 'w') as f:
        json.dump(outcomes, f, indent=2)
    print(f"Reapplied {target_id}: crop={crop_info}")


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--reapply':
        reapply(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == '--board':
        rebuild_board()
    else:
        main()
