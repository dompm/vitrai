"""audit_flagger.py -- cheap non-swatch contamination flagger for the catalog corpus.

Report 019 (scrape-audit). Detects the "smoking-gun" contamination class found in the
Bullseye 'reactive' product lines: a *fused reaction-test photo* -- a handful of discrete,
rounded, high-contrast color tiles floating on a near-white studio ground -- picked by the
scraper's `images[0]` rule instead of the sheet-swatch photo.

The signal is deliberately cheap (no ML): near-white background fraction + connected-component
count / compactness on the non-white foreground. A clean backlit sheet swatch is edge-to-edge
color (low white fraction, one frame-filling component); a test-fire photo is mostly white with
a few small compact blobs. A single-sheet product photo on a white ground (front-lit, drop
shadow) is an intermediate case emitted under a separate, weaker reason code.

Usage:
    python3 audit_flagger.py --assets <path/to/frontend/public/assets> \
        --out ../results/corpus/swatch_quarantine.json
    # or import analyze_image / flag_signals for calibration.

Nothing is deleted; the output is an advisory quarantine list of {id, file, reason, signals}.
"""
import os
import sys
import json
import argparse
import numpy as np
from PIL import Image
from scipy import ndimage

# --- tunables (calibrated in report 019 against the hand-labeled reactive/random sample) ---
RESIZE = 256          # analyze at this longest edge
WHITE_MIN = 228       # a pixel is "near-white ground" if min(R,G,B) >= this ...
WHITE_SAT = 0.10      # ... and its HSV saturation is below this
BLOB_MIN_FRAC = 0.004 # ignore foreground components smaller than this fraction of the frame
# test-fire decision thresholds
TF_WHITE_MIN = 0.33   # background must be at least this white
TF_FG_MAX = 0.55      # foreground (the tiles) must not fill the frame
TF_BLOBS_LO = 1       # number of significant blobs in [lo, hi]
TF_BLOBS_HI = 8
TF_SOLIDITY_MIN = 0.55  # mean bbox-fill of the blobs (compact/rounded tiles pack their bbox)
TF_FG_SAT_MIN = 0.19    # the tiles carry vivid color; a pale near-clear sheet does not
TF_BIG_MIN = 0.02       # at least one real tile present
# product-on-white (front-lit single sheet, weaker signal) thresholds
PW_WHITE_MIN = 0.22
PW_BORDER_WHITE_MIN = 0.55  # frame border is mostly white


def analyze_image(path):
    """Return cheap contamination signals for one image."""
    im = Image.open(path).convert('RGB')
    im.thumbnail((RESIZE, RESIZE))
    a = np.asarray(im, dtype=np.float32) / 255.0
    h, w = a.shape[:2]
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx = a.max(-1)
    mn = a.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    # near-white studio ground: bright AND desaturated
    white = (mn >= WHITE_MIN / 255.0) & (sat <= WHITE_SAT)
    white_frac = float(white.mean())

    # border whiteness (outer 12% ring) -- product-on-white cue
    ring = np.ones((h, w), bool)
    m = max(1, int(0.12 * min(h, w)))
    ring[m:h - m, m:w - m] = False
    border_white = float(white[ring].mean()) if ring.any() else 0.0

    # foreground = non-white; clean up and label connected components
    fg = ~white
    fg = ndimage.binary_opening(fg, iterations=2)
    lbl, n = ndimage.label(fg)
    fg_frac = float(fg.mean())
    # mean saturation of the foreground -- reaction tiles are vivid, pale sheets are not
    fg_sat = float(sat[fg].mean()) if fg.any() else 0.0
    frame = h * w
    blobs = []
    if n:
        sizes = ndimage.sum(np.ones_like(lbl), lbl, index=np.arange(1, n + 1))
        objs = ndimage.find_objects(lbl)
        for i, sz in enumerate(sizes):
            frac = sz / frame
            if frac < BLOB_MIN_FRAC:
                continue
            sl = objs[i]
            bh = sl[0].stop - sl[0].start
            bw = sl[1].stop - sl[1].start
            bbox_area = max(1, bh * bw)
            solidity = sz / bbox_area           # how fully the blob packs its bounding box
            aspect = bw / bh if bh else 1.0
            # centroid distance from frame center, normalized
            cy = (sl[0].start + sl[0].stop) / 2 / h
            cx = (sl[1].start + sl[1].stop) / 2 / w
            blobs.append({
                'frac': float(frac), 'solidity': float(solidity),
                'aspect': float(aspect), 'cx': float(cx), 'cy': float(cy),
            })
    blobs.sort(key=lambda d: -d['frac'])
    n_blobs = len(blobs)
    biggest = blobs[0]['frac'] if blobs else 0.0
    mean_sol = float(np.mean([x['solidity'] for x in blobs])) if blobs else 0.0
    return {
        'white_frac': round(white_frac, 4),
        'border_white': round(border_white, 4),
        'fg_frac': round(fg_frac, 4),
        'n_blobs': n_blobs,
        'biggest_blob_frac': round(biggest, 4),
        'mean_blob_solidity': round(mean_sol, 4),
        'fg_sat': round(fg_sat, 4),
    }


def flag_signals(s):
    """Return a list of reason codes (possibly empty) for a signals dict."""
    reasons = []
    # --- test-fire / reaction-demo tiles: white ground + a few compact blobs ---
    if (s['white_frac'] >= TF_WHITE_MIN
            and s['fg_frac'] <= TF_FG_MAX
            and TF_BLOBS_LO <= s['n_blobs'] <= TF_BLOBS_HI
            and s['mean_blob_solidity'] >= TF_SOLIDITY_MIN
            and s.get('fg_sat', 0) >= TF_FG_SAT_MIN
            and TF_BIG_MIN <= s['biggest_blob_frac'] <= 0.45):
        reasons.append('test_fire_tiles')
    # --- single sheet photographed on a white ground (front-lit product shot) ---
    # one dominant blob that does NOT fill the frame, sitting on a mostly-white border.
    elif (s['white_frac'] >= PW_WHITE_MIN
          and s['border_white'] >= PW_BORDER_WHITE_MIN
          and s['n_blobs'] <= 3
          and 0.20 <= s['biggest_blob_frac'] <= 0.85):
        reasons.append('product_on_white')
    return reasons


# --- name-based blocklist for product lines whose catalog photo is systematically
#     not a uniform sheet swatch (the image heuristic misses the frame-filling ones).
#     Only applied to Bullseye, where these lines live. Report 019 §2/§4. ---
_COMPOSITE_KW = ('collage', 'fracture', 'streamer', 'chopstix', 'lacy',
                 ' on white', ' on clear', 'frit', 'confetti')


def flag_name(name, mfg):
    """Reason codes derived from the product name (complements the image heuristic)."""
    reasons = []
    if (mfg or '').lower() != 'bullseye':
        return reasons
    n = (name or '').lower()
    # reaction test-fire demo lines: their lead photo is a fired reaction tile, not a sheet.
    # the iridescent variants happen to lead with a real sheet, so exclude them.
    if ('reactive' in n or 'alchemy' in n) and 'iridescent' not in n:
        reasons.append('reaction_demo_line')
    # sparse composite / streamer / fracture designs: correct photo, but not a uniform sheet.
    if any(k in n for k in _COMPOSITE_KW):
        reasons.append('composite_streamer_line')
    return reasons


def _iter_registered(assets):
    reg = json.load(open(os.path.join(assets, 'glass_swatch_registry.json')))
    for x in reg:
        fn = x['local_image'].split('/')[-1]
        yield x['id'], x.get('manufacturer', '?'), x.get('name', ''), fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--assets', required=True, help='frontend/public/assets dir')
    ap.add_argument('--out', required=True)
    ap.add_argument('--all-files', action='store_true',
                    help='also scan on-disk files with no registry entry (e.g. SGE)')
    args = ap.parse_args()
    imgdir = os.path.join(args.assets, 'catalog_images')

    quarantine = []
    seen = set()
    for rid, mfg, name, fn in _iter_registered(args.assets):
        seen.add(fn)
        p = os.path.join(imgdir, fn)
        if not os.path.exists(p):
            continue
        try:
            sig = analyze_image(p)
        except Exception as e:
            quarantine.append({'id': rid, 'file': fn, 'manufacturer': mfg,
                               'reason': ['unreadable'], 'error': str(e)})
            continue
        reasons = flag_signals(sig) + flag_name(name, mfg)
        if reasons:
            quarantine.append({'id': rid, 'file': fn, 'manufacturer': mfg,
                               'name': name, 'reason': reasons, 'signals': sig})

    if args.all_files:
        for fn in sorted(os.listdir(imgdir)):
            if fn in seen or not fn.lower().endswith('.jpg'):
                continue
            p = os.path.join(imgdir, fn)
            try:
                sig = analyze_image(p)
            except Exception as e:
                continue
            reasons = flag_signals(sig)
            if reasons:
                mfg = fn.split('-')[0]
                quarantine.append({'id': None, 'file': fn, 'manufacturer': mfg,
                                   'name': None, 'reason': reasons, 'signals': sig,
                                   'unregistered': True})

    quarantine.sort(key=lambda d: (d.get('manufacturer') or '', d['file']))
    with open(args.out, 'w') as f:
        json.dump({'flagger': 'audit_flagger.py',
                   'note': 'ADVISORY quarantine list -- nothing deleted. See report 019. '
                           'test_fire_tiles = high-confidence reaction/test-fire tile-on-white '
                           '(the smoking gun). reaction_demo_line/composite_streamer_line = '
                           'name-based, Bullseye product lines whose catalog photo is not a '
                           'uniform sheet. product_on_white = weak/advisory: front-lit '
                           'single-sheet-on-white OR non-glass junk (mostly SGE) -- review before use.',
                   'reason_codes': ['test_fire_tiles', 'reaction_demo_line',
                                    'composite_streamer_line', 'product_on_white', 'unreadable'],
                   'n_flagged': len(quarantine),
                   'items': quarantine}, f, indent=2)
    print(f'flagged {len(quarantine)} images -> {args.out}')


if __name__ == '__main__':
    main()
