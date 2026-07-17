"""One-off sweep: apply the grip/whole-sheet detector + authoritative full-res
border scrub (scripts/swatch_picker.py) to every Bullseye registry row that is
currently cropped=false. PR #124 only ran the crop phase on picks that CHANGED
this run; products whose shipped pick was already a grip/whole-sheet photo
never got the crop. This sweep closes that gap for the pre-existing 217
(fix/bullseye-grip-sweep). Run from the repo root: `python3 scripts/sweep_uncropped_bullseye.py`.

Old (pre-crop) bytes are copied to a review-board cache dir before any
in-place overwrite, so the addendum board can still show a true before/after.
"""
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, 'scripts')
from swatch_picker import bullseye_features, _scrub_crop_box  # noqa: E402

IMAGE_DIR = 'frontend/public/assets/catalog_images'
REGISTRY_FILE = 'frontend/public/assets/glass_swatch_registry.json'
OLD_CACHE_DIR = 'data/sweep_old_pick_cache'
os.makedirs(OLD_CACHE_DIR, exist_ok=True)

# handled by hand elsewhere (special cases a/b/c from the task) -- skip here
SPECIAL_IDS = {
    'bullseye-0003130050f1010',  # (a) black-corner scrub, bespoke
    'bullseye-0011010000f1010',  # (b) perspective side view, no flat alt
    'bullseye-0012470031f1010',  # (c) washed gradient, no clean alt
}


def main():
    with open(REGISTRY_FILE) as f:
        registry = json.load(f)

    bull_uncropped = [r for r in registry if r.get('manufacturer') == 'Bullseye'
                      and not r.get('cropped') and r['id'] not in SPECIAL_IDS]
    print(f"Sweeping {len(bull_uncropped)} uncropped Bullseye rows (excluding {len(SPECIAL_IDS)} special cases)")

    cropped_ids = []
    uncertain = []  # {'id','name','reason','detail'}
    left_alone = []  # correctly-uncropped (flat chip / other), no action

    for r in bull_uncropped:
        fn = os.path.basename(r['local_image'])
        path = os.path.join(IMAGE_DIR, fn)
        if not os.path.exists(path):
            uncertain.append({'id': r['id'], 'name': r['name'], 'reason': 'local_file_missing'})
            continue

        try:
            feats = bullseye_features(path)
        except Exception as e:
            uncertain.append({'id': r['id'], 'name': r['name'], 'reason': f'detector_error: {e}'})
            continue

        if not feats.get('is_whole_sheet_on_white'):
            left_alone.append(r['id'])
            continue

        crop_frac = feats.get('crop_box_frac')
        if crop_frac is None:
            uncertain.append({'id': r['id'], 'name': r['name'], 'reason': 'thumb_scrub_failed',
                               'detail': feats.get('crop_scrub')})
            continue

        # authoritative full-res scrub, same discipline as Phase C
        img = Image.open(path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        a_full = np.asarray(img, dtype=np.uint8)
        scrubbed, detail = _scrub_crop_box(a_full, crop_frac)
        if scrubbed is None:
            uncertain.append({'id': r['id'], 'name': r['name'], 'reason': f"fullres_scrub_failed:{detail.get('failed')}",
                               'detail': detail})
            continue

        # save an old-pixel copy for the review board before the in-place overwrite
        shutil.copy(path, os.path.join(OLD_CACHE_DIR, f"{r['id']}_old.jpg"))

        x0f, y0f, x1f, y1f = scrubbed
        w, h = img.size
        crop_box = [int(x0f * w), int(y0f * h), int(x1f * w), int(y1f * h)]
        cropped_img = img.crop(crop_box)
        cropped_img.save(path, "JPEG")

        is_half = 'HALF' in r['base_sku'].upper()
        base_w = 17.0 if is_half else 10.0
        base_h = 20.0 if is_half else 10.0

        r['cropped'] = True
        r['crop_box'] = crop_box
        r['real_world_width_in'] = round(base_w * (x1f - x0f), 2)
        r['real_world_height_in'] = round(base_h * (y1f - y0f), 2)
        # original_width_px/height_px stay as the PRE-crop dimensions, matching the
        # existing Phase C convention (see bullseye-0000240030f1010 in the registry).
        r['original_width_px'], r['original_height_px'] = w, h

        cropped_ids.append({'id': r['id'], 'name': r['name'], 'grip_flag': feats.get('grip_flag'),
                             'crop_box': crop_box, 'area_kept': detail.get('area_kept')})
        print(f"  CROPPED {r['id']} ({r['name']}) grip={feats.get('grip_flag')} area_kept={detail.get('area_kept')}")

    with open(REGISTRY_FILE, 'w') as f:
        json.dump(registry, f, indent=2)

    print(f"\nDone. Newly cropped: {len(cropped_ids)}. Uncertain: {len(uncertain)}. Left alone (flat chip/other): {len(left_alone)}.")

    out = {'cropped': cropped_ids, 'uncertain': uncertain, 'left_alone_count': len(left_alone)}
    with open('data/sweep_uncropped_bullseye_result.json', 'w') as f:
        json.dump(out, f, indent=2)


if __name__ == '__main__':
    main()
