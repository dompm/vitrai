#!/usr/bin/env python
"""Bullseye texture-scale audit (report: docs/library-picker-rebuild/scale_report.md).

WHAT IT FINDS
  Bullseye product galleries share one photo set across cart size variants. The
  library builder stamped real_world_width_in from the cart size (=10in for the
  10x10 variant) onto whichever gallery image the picker chose -- but ~45% of picks
  are zoomed detail/macro crops covering far less than a full sheet, so those
  textures render 2-3x too coarse when placed at physical scale in the app.

WHAT IT DOES
  For every Bullseye product it downloads the full gallery (throttled, local-only,
  gitignored), detects the whole-sheet studio shot (backdrop-framed on ~4 sides),
  measures the sheet, classifies the CURRENT pick (whole-sheet vs detail vs macro),
  audits iridized picks for transmission-mode / split-backdrop-seam errors, and
  emits docs/library-picker-rebuild/scale_audit.json. With --apply it also writes
  the safe registry corrections (null the known-wrong ~10in stamps on detail picks;
  make whole-sheet heights aspect-consistent).

CALIBRATION (documented assumption)
  The whole-sheet product photo is a FIXED studio sample: measured aspect is a very
  tight 1.326 (p10-p90 1.318-1.331) across 361 products, matching none of the sale
  sizes (10x10=1.0, half 17x20=1.176, full 35x20=1.75). Its absolute long side is
  NOT recoverable from pixels; we adopt SAMPLE_LONG_IN=10.0in (anchored to the 10x10
  convention + the geometric short-side<=20in bound). Every RELATIVE correction is
  independent of this constant; retune it globally if a physical reference lands.

Idempotent. Run from repo root. venv: ~/Documents/fastbook/.venv (cv2+SIFT).
"""
import json, os, re, sys, time, argparse, collections, statistics
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scale_audit_lib as A

REGISTRY = 'frontend/public/assets/glass_swatch_registry.json'
SIDECAR = 'docs/library-picker-rebuild/scale_audit.json'
GAL = 'data/scale_audit_gallery'                       # gitignored
CACHE = 'data/scale_audit_gallery/_bullseye_products.json'
UA = {'User-Agent': 'Vitrai-lab-research/1.0 (stained-glass texture scale audit; contact dompm@hotmail.com)'}
SAMPLE_LONG_IN = 10.0

def _handle(url):
    m = re.search(r'/products/([^/?#]+)', url or ''); return m.group(1) if m else None

def ensure_products():
    os.makedirs(GAL, exist_ok=True)
    if os.path.exists(CACHE):
        return json.load(open(CACHE))
    prods, page = [], 1
    while page <= 12:
        r = requests.get(f'https://shop.bullseyeglass.com/products.json?page={page}&limit=250',
                         headers=UA, timeout=25)
        if r.status_code != 200: break
        batch = r.json().get('products', [])
        if not batch: break
        prods += batch; page += 1; time.sleep(1.0)
    json.dump(prods, open(CACHE, 'w'))
    return prods

def ensure_galleries(reg, byh):
    for r in [x for x in reg if x['manufacturer'] == 'Bullseye']:
        p = byh.get(_handle(r['product_url']))
        if not p: continue
        for im in p.get('images', []):
            fn = im['src'].split('/')[-1].split('?')[0]
            dst = os.path.join(GAL, fn)
            if os.path.exists(dst) and os.path.getsize(dst) > 1000: continue
            try:
                resp = requests.get(im['src'], headers=UA, timeout=25)
                if resp.status_code == 200:
                    open(dst, 'wb').write(resp.content); time.sleep(1.0)
            except Exception: pass

# ---------- per-product analysis ----------
def score_ws(cls):
    b = cls['box']
    if not b or not cls['is_whole_sheet']: return -1
    return (4 - b['touch']) * 100 + b['n_sides'] * 30 + b['fill'] * 40 + (b['w'] * b['h']) / 1440000 * 20

def analyze(reg_row, prod):
    gal = [im['src'].split('/')[-1].split('?')[0] for im in prod.get('images', [])]
    recs = {}
    for name in gal:
        p = os.path.join(GAL, name)
        if os.path.exists(p):
            try: recs[name] = A.classify_image(A.load_bgr(p))
            except Exception: pass
    ws_name, best = None, -1
    for n, c in recs.items():
        s = score_ws(c)
        if s > best: ws_name, best = n, s
    ws = recs.get(ws_name)
    picked = reg_row['image_url'].split('/')[-1].split('?')[0]
    pc = recs.get(picked)
    o = dict(base_sku=reg_row['base_sku'], name=reg_row['name'], category=reg_row['category'],
             iridized=bool(reg_row.get('iridized')), picked_image=picked, gallery=gal,
             wholesheet_image=ws_name,
             reg_width_in=reg_row.get('real_world_width_in'),
             reg_height_in=reg_row.get('real_world_height_in'),
             reg_crop_box=reg_row.get('crop_box'))
    if ws:
        b = ws['box']
        o.update(ws_box=[b['x'], b['y'], b['w'], b['h']], ws_aspect=round(b['aspect'], 3),
                 ws_bg_mode=ws['bg']['mode'], ws_seam_x=ws['bg'].get('seam_x'),
                 ws_measurable=bool(b['touch'] == 0 and b['fill'] > 0.80))
    else:
        o.update(ws_box=None, ws_measurable=False)
    if pc:
        o['picked_bg_mode'] = pc['bg']['mode']
        o['picked_is_detail'] = not pc['is_whole_sheet']
        pb = pc['box']
        o['picked_measurable'] = bool(pb and pc['is_whole_sheet'] and pb['touch'] == 0 and pb['fill'] > 0.80)
    else:
        o['picked_bg_mode'] = None; o['picked_is_detail'] = None; o['picked_measurable'] = False
    return o, recs

def decide(o, recs):
    """Add confidence tier, flags, corrected dims, recommendation."""
    flags, irid = [], o['iridized']
    cb = o.get('reg_crop_box')
    ws_ok = o.get('ws_measurable')
    ipp = SAMPLE_LONG_IN / o['ws_box'][2] if (ws_ok and o.get('ws_box')) else None
    if ipp:
        o['sample_long_in'] = SAMPLE_LONG_IN
        o['sample_short_in'] = round(o['ws_box'][3] * ipp, 2)

    # transmission-mode audit (iridized)
    if irid:
        if o.get('picked_bg_mode') == 'black':
            flags.append('irid_reflection_pick')
        else:
            pc = recs.get(o['picked_image'])
            bg = pc['bg'] if pc else {}
            if bg.get('mode') == 'split' and bg.get('seam_x') is not None:
                seam, white = bg['seam_x'], bg.get('white_side')
                x0, x1 = (cb[0], cb[2]) if cb else (0, 1200)
                if x0 < seam - 15 and x1 > seam + 15: flags.append('crop_spans_seam')
                elif white == 'right' and x1 <= seam + 15: flags.append('irid_reflection_pick')
                elif white == 'left' and x0 >= seam - 15: flags.append('irid_reflection_pick')

    corr_w, corr_h = o.get('reg_width_in'), o.get('reg_height_in')
    tier, recommend = 'D_other', None
    picked_ws = (o.get('picked_is_detail') is False)
    if picked_ws and o.get('picked_measurable'):
        tier = 'A_wholesheet_pick'
        if corr_w and corr_h and abs(corr_h - corr_w) < 0.05:
            corr_h = round(corr_w / A.SAMPLE_ASPECT, 2)      # fix square 10x10 stamp
    elif picked_ws:
        tier = 'A_wholesheet_lowconf'; flags.append('wholesheet_unmeasurable')
    elif o.get('picked_is_detail') and o.get('picked_bg_mode') == 'none':
        tier = 'C_macro_fullbleed'; corr_w = corr_h = None
        flags.append('scale_bad_macro'); recommend = 'repick_wholesheet'
    elif o.get('picked_is_detail'):
        tier = 'C_detail_crop'; flags.append('scale_partial_crop'); recommend = 'repick_wholesheet'
        if (corr_w or 0) >= 9.5:
            corr_w = corr_h = None; flags.append('scale_stale_10in')
    if not o.get('wholesheet_image'):
        flags.append('no_wholesheet_available')
    elif not picked_ws:
        flags.append('pick_not_wholesheet')

    if irid:
        clean = (tier == 'A_wholesheet_pick' and o.get('picked_bg_mode') in ('white', 'split')
                 and 'irid_reflection_pick' not in flags and 'crop_spans_seam' not in flags)
        if not clean:
            flags.append('irid_needs_transmission'); recommend = 'repick_transmission_wholesheet'

    if ipp and o.get('ws_box'):
        x, y, w, h = o['ws_box']; seam = o.get('ws_seam_x')
        if irid and o.get('ws_bg_mode') == 'split' and seam and x < seam < x + w:
            crop_w = (x + w) - seam; o['repick_note'] = 'crop transmission (white-bg) side'
        else:
            crop_w = w; o['repick_note'] = 'crop sheet interior of whole-sheet shot'
        o['repick_real_world_width_in'] = round(crop_w * ipp, 2)
        o['repick_real_world_height_in'] = round(h * ipp * 0.9, 2)

    o['flags'] = sorted(set(flags))
    o['confidence_tier'] = tier
    o['corrected_width_in'] = corr_w
    o['corrected_height_in'] = corr_h
    o['recommendation'] = recommend
    return o

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='write corrected dims into the registry')
    ap.add_argument('--no-fetch', action='store_true', help='skip CDN fetch, use cached galleries only')
    args = ap.parse_args()

    reg = json.load(open(REGISTRY))
    prods = ensure_products()
    byh = {p['handle']: p for p in prods}
    if not args.no_fetch:
        ensure_galleries(reg, byh)

    be = [r for r in reg if r['manufacturer'] == 'Bullseye']
    products, aspects = [], []
    for i, r in enumerate(be):
        p = byh.get(_handle(r['product_url']))
        if not p:
            products.append(dict(base_sku=r['base_sku'], error='no_product')); continue
        o, recs = analyze(r, p)
        if o.get('ws_measurable') and o.get('ws_aspect'):
            aspects.append(o['ws_aspect'])
        products.append(decide(o, recs))
        if i % 50 == 0: print(f'[{i}/{len(be)}] {r["base_sku"]}', flush=True)

    sample_aspect = round(statistics.median(aspects), 3) if aspects else 1.326
    meta = dict(sample_aspect=sample_aspect, sample_long_in=SAMPLE_LONG_IN,
                sample_short_in=round(SAMPLE_LONG_IN / sample_aspect, 2), n_products=len(products),
                aspect_p10=round(sorted(aspects)[len(aspects)//10], 3) if aspects else None,
                aspect_p90=round(sorted(aspects)[len(aspects)*9//10], 3) if aspects else None,
                field_semantics='real_world_{width,height}_in = the IMAGE physical footprint '
                     '(inches of glass the swatch spans; app needs in/px), NOT the cart sale size.',
                calibration='Whole-sheet photo is a fixed studio sample, true aspect ~%.3f '
                     '(rotation ruled out: minAreaRect rectified aspect == bbox, tilt ~0deg). '
                     'Absolute long side is NOT pixel-recoverable (detail->sheet SIFT/NCC/FFT '
                     'bridge fails; reeded-rib anchor consistent at ~82 ribs/sheet but no ribs/in '
                     'reference). SAMPLE_LONG_IN=%.1f in is a documented assumption; retune '
                     'globally to rescale all Bullseye scales together.'
                     % (sample_aspect, SAMPLE_LONG_IN),
                sample_size_candidate='UNVERIFIED: 1.327 ~= 4:3 within rolled-edge slop -> '
                     'possibly a 40x30cm studio blank (15.75x11.8in). If so SAMPLE_LONG_IN~15.75 '
                     '(1.57x rescale). Rib pitch under each: 10in->~3.1mm, 15.75in->~4.9mm. '
                     'One tape-measure reading (rib pitch or sample size) adjudicates.')
    os.makedirs(os.path.dirname(SIDECAR), exist_ok=True)
    json.dump(dict(meta=meta, products=products), open(SIDECAR, 'w'), indent=1)

    tiers = collections.Counter(p.get('confidence_tier') for p in products)
    flags = collections.Counter(f for p in products for f in p.get('flags', []))
    nulled = sum(1 for p in products if p.get('confidence_tier', '').startswith('C') and p.get('corrected_width_in') is None)
    print('\n===== SCALE AUDIT =====')
    print('products:', len(products))
    print('tiers:', dict(tiers))
    print('flags:', dict(flags))
    print('dims nulled (known-wrong):', nulled)
    print('sample aspect', sample_aspect, 'long', SAMPLE_LONG_IN, 'short', meta['sample_short_in'])
    print('sidecar ->', SIDECAR)

    if args.apply:
        by_sku = {p['base_sku']: p for p in products}
        changed = 0
        for row in reg:
            pr = by_sku.get(row['base_sku'])
            if not pr or 'confidence_tier' not in pr: continue
            nw, nh = pr['corrected_width_in'], pr['corrected_height_in']
            if nw != row.get('real_world_width_in') or nh != row.get('real_world_height_in'):
                row['real_world_width_in'] = nw
                row['real_world_height_in'] = nh
                changed += 1
            if pr.get('recommendation'):
                row['needs_repick'] = True     # detail in the scale_audit.json sidecar
        json.dump(reg, open(REGISTRY, 'w'), indent=2)
        print(f'registry: {changed} rows re-dimensioned, needs_repick flags written -> {REGISTRY}')

if __name__ == '__main__':
    main()
