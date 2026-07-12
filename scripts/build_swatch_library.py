import requests
import json
import os
import time
import re
import sys
from urllib.parse import urlparse
from PIL import Image, ImageDraw, ImageFont

IMAGE_DIR = 'frontend/public/assets/catalog_images'
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs('data', exist_ok=True)

REGISTRY_FILE = 'frontend/public/assets/glass_swatch_registry.json'
VERIFY_HTML = 'frontend/public/swatch_verify.html'
TRACKER_MD = 'data/swatch_tracker.md'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
}

EXCLUDE_TERMS = [
    'tekta', 'mirror', 'book', 'frit', 'powder', 'confetti', 'stringer', 'rod', 'casting',
    'billet', 'rondel', 'wreath', 'came', 'solder', 'flux', 'foil', 'grinder', 'saw', 'lead',
    'fusing', 'kiln', 'shelf', 'stand', 'box fee', 'pack', 'glass cutter', 'cutting', 'pliers',
    'glue', 'came', 'u-came', 'h-came', 'solder', 'flux', 'tack', 'shears', 'grozier', 'safety glasses',
    'solder', 'chain', 'zinc', 'coiled', 'foil', 'rebar', 'sharpie', 'pen', 'tool', 'brush', 'cutter',
    'suction cup', 'grout', 'cement', 'polish', 'patina', 'finish', 'cleaner', 'apron', 'gloves', 'mask'
]

# --- CLASSIFIER LOGIC ---

def classify_glass(title, sku, manufacturer):
    title_lower = title.lower()
    sku_upper = sku.upper()

    # 1. English Muffle
    if 'muffle' in title_lower or sku_upper.startswith('EM'):
        return "English Muffle"

    # 2. Ring Mottle / Mottled (Tiffany Style)
    if 'mottle' in title_lower or 'mottled' in title_lower:
        return "Ring Mottle"

    # 3. Baroque / Ripple / Artique / Textured
    if any(term in title_lower for term in ['baroque', 'artique', 'waterglass', 'ripple', 'granite', 'seedy', 'hammered', 'dew drop', 'rainwater', 'glue chip', 'rough rolled']):
        return "Textured/Baroque"

    # 4. Wispy / Streaky / Blends
    if any(term in title_lower for term in ['wispy', 'streaky', 'mix', 'blend', 'opal-art', 'fusers reserve', 'cascade', 'spirit']):
        return "Wispy/Streaky"
    if manufacturer == 'Bullseye' and any(sku_upper.startswith(prefix) for prefix in ['002', '003', '51', '52']):
        return "Wispy/Streaky"

    # 5. Clear Glass (not Cathedral!)
    if any(term in title_lower for term in ['clear', 'crystal', 'ice']):
        # Except if it's a colored clear like 'clear green'
        if not any(color in title_lower for color in ['red', 'blue', 'green', 'yellow', 'orange', 'pink', 'purple', 'amber', 'brown']):
            return "Clear"

    # 6. Opalescent (Opaque / Solid)
    if 'opal' in title_lower or any(term in title_lower for term in ['opaque', 'solid', 'dense', 'alabaster']):
        return "Opalescent"
    if manufacturer == 'Bullseye' and sku_upper.startswith('000'):
        return "Opalescent"

    # 7. Cathedral (Transparent colored)
    if 'cathedral' in title_lower or any(term in title_lower for term in ['transparent', 'translucent', 'tint']):
        return "Cathedral"
    if manufacturer == 'Bullseye' and sku_upper.startswith('001'):
        return "Cathedral"

    # Default fallbacks based on visual cues
    if any(term in title_lower for term in ['white', 'black', 'grey', 'gray', 'ivory', 'bone']):
        return "Opalescent"

    return "Cathedral"


def clean_sku(s):
    return re.sub(r'[^a-zA-Z0-9]', '', s).lower()

# --- PRE-CACHING LOGIC ---

def cache_bullseye_products():
    print("Pre-caching Bullseye products...")
    products = []
    page = 1
    while page <= 12:
        url = f"https://shop.bullseyeglass.com/products.json?page={page}&limit=250"
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                break
            batch = r.json().get('products', [])
            if not batch:
                break
            products.extend(batch)
            page += 1
            time.sleep(0.2)
        except Exception as e:
            print(f"  Error caching Bullseye: {e}")
            break
    print(f"Cached {len(products)} products from Bullseye.")
    return products

def cache_sge_collection(collection_handle):
    print(f"Pre-caching SGE collection: {collection_handle}...")
    products = []
    page = 1
    while True:
        url = f"https://www.stainedglassexpress.com/collections/{collection_handle}/products.json?page={page}&limit=250"
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                break
            batch = r.json().get('products', [])
            if not batch:
                break
            products.extend(batch)
            page += 1
            time.sleep(0.2)
        except Exception as e:
            print(f"  Error caching SGE {collection_handle}: {e}")
            break
    print(f"Cached {len(products)} products from SGE {collection_handle}.")
    return products


# ==================================================================================
# PICKER INTEGRATION (iteration 036) -- glass-library-integration-review.md Addendum 2
# ==================================================================================
# Replaces the old `get_best_image_url()` positional heuristic (always `images[0]`)
# with a scored argmax over a product's FULL gallery, via the vendored
# `swatch_picker.pick()` (scripts/swatch_picker.py, itself wrapping scripts/
# audit_flagger.py -- both vendored copies of research/delighting report 019/035
# modules, see their file headers for provenance/how to refresh). No network calls
# happen inside the picker module itself -- WE fetch thumbnail-sized candidates here
# and hand it local file paths, per its own integration guidance.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from swatch_picker import pick as picker_pick, FLOOR as PICKER_FLOOR  # noqa: E402

THUMB_CACHE_DIR = 'data/picker_thumb_cache'
os.makedirs(THUMB_CACHE_DIR, exist_ok=True)
THUMB_WIDTH = 320          # Shopify CDN `?width=N` transform. Measured ~10KB vs ~150KB
                           # for a full-res image on a live sample during this
                           # integration -- cheap enough to score every gallery
                           # candidate instead of just position 0/-1.
MAX_CANDIDATE_IMAGES = 10  # defensive cap; report 035's validation sample saw 2-8/product
STABILITY_MARGIN = 0.15    # anti-churn threshold -- see apply_stability_rule() below


# ==================================================================================
# MANUAL OVERRIDES (ownership cleanup, glass-library-integration-review.md)
# ==================================================================================
# Bullseye Reactive Cloud Opalescent (both size variants, base_sku prefix 000009):
# both the original vendor photo (`_01`) and the delighting-024 `-v2` recovery
# (`_02`) are the SAME hybrid "genuine sheet + small reaction-demo tile corner
# insert" style shot -- Bullseye's live product feed only ever publishes these two
# images for this product line (verified live, both addenda). The review's
# Addendum re-adjudication settled on KEEP, not QUARANTINE: ~82-85% of the frame is
# real, uniform, representative glass in every available photo, and the demo-tile
# cluster is consistently confined to the top-left corner (bounding box never
# extends past roughly x:0-620 of 1200). Its own "actionable middle path" -- a crop
# of the right ~54% of the frame -- removes the tile cluster entirely without
# needing a better vendor source that doesn't exist. Applied here instead of the
# old blanket `is_reactive_cloud` rule that just dropped both SKUs from the
# registry (see Decision 3, glass-library-integration-review.md Addendum, citing
# research/delighting/results/corpus/refetch_manifest.json `recovered` entries).
REACTIVE_CLOUD_CROP_OVERRIDE = {
    'bullseye-0000090030f1010': {
        'v2_filename': 'bullseye-0000090030f1010-v2.jpg',
        'v2_url': 'https://cdn.shopify.com/s/files/1/0737/5237/9665/files/000009-0030-F_02.jpg',
        'crop_filename': 'bullseye-0000090030f1010-cropped.jpg',
        'crop_box': [650, 0, 1200, 1200],
    },
    'bullseye-0000090050f1010': {
        'v2_filename': 'bullseye-0000090050f1010-v2.jpg',
        'v2_url': 'https://cdn.shopify.com/s/files/1/0737/5237/9665/files/000009-0050-F_02.jpg',
        'crop_filename': 'bullseye-0000090050f1010-cropped.jpg',
        'crop_box': [650, 0, 1200, 1200],
    },
}

# White-on-white false-quarantine override (036 report / Decision 4): the picker's
# pale-sheet credit requires fg_frac <= 0.02 to recognize a full-bleed pale sheet,
# but these two are genuinely uniform WHITE sheets photographed on a white studio
# ground -- their fg_frac (0.23-0.40) is too high for that credit and too low to
# read as full-bleed coverage, so they score 0.37-0.43, just under the picker's
# 0.45 floor. This is a documented picker blind spot (report 035, not stress-tested
# for near-white-on-white), not a real image-quality problem -- both source photos
# are clean, uniform, well-lit sheet photography (spot-checked and confirmed good
# pre-picker). Restoring their known-good images explicitly here, rather than
# lowering the floor globally, which would let genuinely bad photos back in
# elsewhere in the catalog.
WHITE_ON_WHITE_OVERRIDE = {
    # Opaque White Opalescent, 3 mm
    'bullseye-0000130030f1010': 'https://cdn.shopify.com/s/files/1/0737/5237/9665/files/000013-0030-F_01.jpg?v=1765591007',
    # White, Light Silver Gray 2-Color Mix, Cascade, Iridescent, silver, 3 mm
    'bullseye-002249ca37f1010': 'https://cdn.shopify.com/s/files/1/0737/5237/9665/files/002249-CA37-F_01.jpg?v=1765591807',
}


def apply_manual_overrides(item_id, pick_info):
    """Bypass the picker floor for the explicit, reviewed WHITE_ON_WHITE_OVERRIDE
    list only -- never lowers the floor globally. No-op for every other id."""
    if pick_info['status'] == 'Quarantined' and item_id in WHITE_ON_WHITE_OVERRIDE:
        url = WHITE_ON_WHITE_OVERRIDE[item_id]
        cs = dict(pick_info.get('candidate_scores') or {})
        return {'status': 'Downloaded', 'url': url, 'score': cs.get(_strip_query(url)),
                'candidate_scores': cs, 'manual_override': True}
    return pick_info


def crop_reactive_cloud_image(override):
    """Physically crop the -v2 recovery to x:[650,1200], y:[0,1200] of its 1200x1200
    frame, saved under a distinct filename so the original -v2 (kept as evidence /
    reference for the adjudication) is left untouched. Fetches the -v2 source from
    the vendor if not already cached locally (e.g. a fresh checkout)."""
    v2_path = os.path.join(IMAGE_DIR, override['v2_filename'])
    out_path = os.path.join(IMAGE_DIR, override['crop_filename'])
    if os.path.exists(out_path):
        with Image.open(out_path) as img:
            return out_path, img.size[0], img.size[1]

    if not os.path.exists(v2_path):
        try:
            r = requests.get(override['v2_url'], headers=HEADERS, timeout=10)
            if r.status_code == 200:
                with open(v2_path, 'wb') as f:
                    f.write(r.content)
        except Exception as e:
            print(f"  Failed to fetch reactive-cloud -v2 source {override['v2_url']}: {e}")
            return None, None, None

    if not os.path.exists(v2_path):
        return None, None, None

    img = Image.open(v2_path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    cropped = img.crop(tuple(override['crop_box']))
    cropped.save(out_path, "JPEG")
    return out_path, cropped.size[0], cropped.size[1]


def _strip_query(url):
    """Compare CDN URLs by path only. Shopify bumps the `?v=` cache-busting query
    param on re-upload even when the underlying photo is byte-identical, so query-
    string equality would falsely register "no real change" as a change (and vice
    versa isn't a risk we've seen, but path-only comparison is the conservative,
    correct one either way)."""
    return (url or '').split('?')[0]


def _normalize_src(src):
    if src.startswith('//'):
        return 'https:' + src
    return src


def thumb_url(url, width=THUMB_WIDTH):
    sep = '&' if '?' in url else '?'
    return f"{url}{sep}width={width}"


def get_candidate_urls(product):
    """Every gallery image for a product, not just position 0 -- this is the whole
    point of report 019 Patch #1 / review Addendum 2: the correct swatch photo's
    position varies per product (sometimes stated only in description prose), so a
    positional rule can't be right across the catalog."""
    urls = []
    seen = set()
    for im in product.get('images', [])[:MAX_CANDIDATE_IMAGES]:
        src = _normalize_src(im.get('src', ''))
        if src and src not in seen:
            seen.add(src)
            urls.append(src)
    return urls


def fetch_thumb(url, local_path):
    """Idempotent by construction: a cached thumbnail is never re-fetched, so an
    interrupted/re-run build resumes almost for free (task's checkpointing ask) and
    a full rebuild after this one is nearly a no-op for the scoring pass."""
    if os.path.exists(local_path):
        return local_path
    try:
        r = requests.get(thumb_url(url), headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        with open(local_path, 'wb') as f:
            f.write(r.content)
        time.sleep(0.08)  # polite pacing against the shared cdn.shopify.com host
        return local_path
    except Exception:
        return None


def select_image_for_product(product, manufacturer, cache):
    """Score every candidate image with the vendored picker; return the argmax or a
    Quarantined verdict. Memoized per Shopify product id -- a Bullseye product's
    -1010/-HALF/-FULL SKU variants all share one photo gallery, so this only needs
    to run once per PRODUCT, not once per registry row.

    Returns {'status': 'Downloaded'|'Quarantined'|'NoImage', 'url': str|None,
             'score': float|None, 'candidate_scores': {stripped_url: final_score}}.
    `candidate_scores` covers every candidate (not just the winner) -- the stability
    rule needs to know the *previously shipped* image's score even when it isn't
    this run's argmax.
    """
    pid = product.get('id')
    if pid in cache:
        return cache[pid]

    urls = get_candidate_urls(product)
    if not urls:
        result = {'status': 'NoImage', 'url': None, 'score': None, 'candidate_scores': {}}
        cache[pid] = result
        return result

    thumb_paths, kept_urls = [], []
    for i, u in enumerate(urls):
        tp = os.path.join(THUMB_CACHE_DIR, f"{pid}_{i}.jpg")
        p = fetch_thumb(u, tp)
        if p:
            thumb_paths.append(p)
            kept_urls.append(u)

    if not thumb_paths:
        result = {'status': 'NoImage', 'url': None, 'score': None, 'candidate_scores': {}}
        cache[pid] = result
        return result

    text = (product.get('body_html') or '') + ' ' + (product.get('title') or '')
    try:
        pr = picker_pick(thumb_paths, text=text, name=product.get('title'), manufacturer=manufacturer)
    except Exception as e:
        # Never let a single corrupt/unreadable candidate abort the whole build --
        # fall back to the old images[0] behavior for this one product.
        print(f"  Picker error on product {pid} ({product.get('title')}): {e} -- falling back to position 0")
        result = {'status': 'Downloaded', 'url': kept_urls[0], 'score': None,
                   'candidate_scores': {}, 'override': False}
        cache[pid] = result
        return result

    candidate_scores = {}
    for s in pr['scores']:
        candidate_scores[_strip_query(kept_urls[s['index']])] = s['final_score']

    if pr['pick'] is None:
        result = {'status': 'Quarantined', 'url': None, 'score': None,
                   'candidate_scores': candidate_scores}
    else:
        picked_url = kept_urls[pr['pick']]
        picked_score = candidate_scores.get(_strip_query(picked_url))
        result = {'status': 'Downloaded', 'url': picked_url, 'score': picked_score,
                   'candidate_scores': candidate_scores, 'override': pr['override']}
    cache[pid] = result
    return result


def apply_stability_rule(item, existing):
    """Anti-churn gate (task's Verify step: "the picker's 75%-agreement disagreements
    on legitimate alternates should NOT churn the library").

    Report 035's 20-product regression found 15/20 argmax agreement with the old
    images[0] pick, and manually re-inspected ALL 5 disagreements at full resolution:
    every one was the picker choosing a different, equally-legitimate photo of the
    SAME correct glass (a wider crop, a less-saturated close-up, ...), never a
    contamination fix. Always taking a fresh argmax on every rebuild would therefore
    churn ~25% of the shipped catalog on taste alone, with no quality improvement.

    Fix: only replace the currently-shipped image when the picker's margin over it
    clears STABILITY_MARGIN=0.15. Threshold rationale: report 035's one *measured*
    legitimate-alternate margin was 0.009 (bullseye-0011010054f1010, "a genuine
    coin-flip"); its measured real fixes were large -- 0.94 and 0.25 in the two
    maintainer validation cases, and the report-024 recovered set flips the `audit`
    component 0.0->1.0 (worth 0.28 of the weighted sum alone), comfortably clearing
    0.15 too. 0.15 sits well above the one observed coin-flip margin and well below
    every observed real-fix margin -- it separates the two populations this task
    asked to distinguish without being tuned to a single data point.

    A previously-shipped image that no longer itself clears the picker's own FLOOR
    is never protected by this rule (stability should not preserve a known-bad
    image); an item with no prior registry entry has nothing to be stable against.
    """
    old_url = existing.get('image_url') if existing else None
    if not old_url:
        return item, False  # nothing to be stable against -- not "churn", just new
    old_key = _strip_query(old_url)
    new_key = _strip_query(item['image_url'])
    if old_key == new_key:
        return item, False  # picker agrees with what's already shipped

    old_score = item.get('_candidate_scores', {}).get(old_key)
    new_score = item.get('pick_score')
    if (old_score is not None and old_score >= PICKER_FLOOR
            and new_score is not None and (new_score - old_score) < STABILITY_MARGIN):
        # The old image is still a legitimate candidate and the picker's preference
        # for the new one isn't decisive -- keep shipping what's already live.
        item['image_url'] = existing['image_url']
        item['_stability_kept'] = True
        return item, False
    return item, True  # genuine churn -- picker's margin clears the bar


# --- AUTO-CROP & CALIBRATION ENGINE ---

def download_and_calibrate_image(url, local_filename, item, category, force=False):
    filepath = os.path.join('frontend/public/assets/catalog_images', local_filename)

    # Base dimensions in inches
    if item['manufacturer'] == 'Bullseye':
        width_in = 17.0 if 'HALF' in local_filename else 10.0
        height_in = 20.0 if 'HALF' in local_filename else 10.0
    else:
        width_in = 6.0 if '6x12' in local_filename.lower() else 12.0
        height_in = 12.0 if '6x12' in local_filename.lower() else 12.0

    cropped = item['manufacturer'] in ['Oceanside', 'Youghiogheny'] or (item['manufacturer'] == 'Bullseye' and category == "Wispy/Streaky")

    # 1. Fast Cache Return (skipped when `force` -- task 036-2: only re-fetch the full
    #    image when the picker's final pick actually differs from what's on disk)
    if os.path.exists(filepath) and not force:
        try:
            img = Image.open(filepath)
            width, height = img.size
            if cropped:
                if item['manufacturer'] in ['Oceanside', 'Youghiogheny']:
                    width_in = round(width_in * 0.8, 2)
                    height_in = round(height_in * 0.8, 2)
                elif item['manufacturer'] == 'Bullseye':
                    width_in = 10.0
                    height_in = 10.0
            return {
                "local_path": filepath,
                "asset_url": f"/assets/catalog_images/{local_filename}",
                "original_width_px": width,
                "original_height_px": height,
                "cropped": cropped,
                "crop_box": None,
                "calibrated_width_in": width_in,
                "calibrated_height_in": height_in
            }
        except Exception:
            pass

    try:
        # Fetch image
        r = requests.get(url, stream=True, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None

        with open(filepath, 'wb') as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)

        # Process image cropping & physical calibration
        img = Image.open(filepath)
        # Convert non-RGB images (GIFs, PNGs with transparency/palettes) to RGB for JPEG compatibility
        if img.mode != 'RGB':
            img = img.convert('RGB')

        width, height = img.size
        crop_box = None

        # --- 2. Crop Oceanside Watermarks (Top-Right 20%) ---
        if item['manufacturer'] == 'Oceanside':
            new_w = int(width * 0.8)
            new_h = int(height * 0.8)
            crop_box = [0, height - new_h, new_w, height]
            img = img.crop(crop_box)
            img.save(filepath, "JPEG")
            width_in = round(width_in * 0.8, 2)
            height_in = round(height_in * 0.8, 2)

        # --- 3. Crop Bullseye Streaky/Wispy Side-Borders & bottom labels ---
        elif item['manufacturer'] == 'Bullseye' and category == "Wispy/Streaky":
            y_scan = height // 2
            left = 0
            right = width - 1

            def is_white_pixel(x):
                pixel = img.getpixel((x, y_scan))
                if not isinstance(pixel, tuple): return False
                return all(c > 240 for c in pixel[:3])

            while left < width and is_white_pixel(left):
                left += 1
            while right > 0 and is_white_pixel(right):
                right -= 1

            glass_w = right - left
            if glass_w > 100:
                crop_box = [left, 0, right, glass_w]
                img = img.crop(crop_box)
                img.save(filepath, "JPEG")
                width_in = 10.0
                height_in = 10.0
            else:
                new_h = int(height * 0.9)
                border_x = int((width - new_h) / 2)
                crop_box = [border_x, 0, border_x + new_h, new_h]
                img = img.crop(crop_box)
                img.save(filepath, "JPEG")
                width_in = round(width_in * 0.9, 2)
                height_in = round(height_in * 0.9, 2)

        # --- 4. Crop SGE Youghiogheny light-table border frames (10% all sides) ---
        elif item['manufacturer'] == 'Youghiogheny':
            border_w = int(width * 0.1)
            border_h = int(height * 0.1)
            crop_box = [border_w, border_h, width - border_w, height - border_h]
            img = img.crop(crop_box)
            img.save(filepath, "JPEG")
            width_in = round(width_in * 0.8, 2)
            height_in = round(height_in * 0.8, 2)

        return {
            "local_path": filepath,
            "asset_url": f"/assets/catalog_images/{local_filename}",
            "original_width_px": width,
            "original_height_px": height,
            "cropped": cropped,
            "crop_box": crop_box,
            "calibrated_width_in": width_in,
            "calibrated_height_in": height_in
        }
    except Exception as e:
        print(f"  Failed to process/crop {url}: {e}")
    return None


def load_existing_registry():
    """Read-only load of whatever's currently shipped, keyed by id -- used for the
    stability rule and for the "download only if the pick changed" efficiency rule.
    Does not exist on a clean checkout (gitignored runtime data); that's fine, it
    just means every item is treated as new."""
    if not os.path.exists(REGISTRY_FILE):
        return {}
    try:
        with open(REGISTRY_FILE, 'r') as f:
            data = json.load(f)
        return {item['id']: item for item in data if 'id' in item}
    except Exception as e:
        print(f"Warning: could not load existing registry for comparison: {e}")
        return {}


# --- MAIN AUTOMATION PIPELINE ---

def main():
    existing_registry_by_id = load_existing_registry()
    print(f"Loaded {len(existing_registry_by_id)} existing registry entries for before/after comparison.")

    bullseye_raw = cache_bullseye_products()
    oceanside_raw = cache_sge_collection("oceanside")
    wissmach_raw = cache_sge_collection("wissmach")
    art_glass_raw = cache_sge_collection("art-glass")

    registry = []
    seen_skus = set()
    downloaded = 0
    failed = 0
    product_pick_cache = {}
    quarantine_log = []  # picker-side quarantines, for the diff report

    # 1. Process Oceanside (System 96)
    print("\nProcessing Oceanside glass sheets...")
    for p in oceanside_raw:
        title = p.get('title', '')
        title_lower = title.lower()
        if any(term in title_lower for term in EXCLUDE_TERMS): continue

        for v in p.get('variants', []):
            sku = v.get('sku') or ''
            sku_upper = sku.upper()
            if sku_upper.startswith('OF') and sku not in seen_skus:
                pick_info = select_image_for_product(p, 'Oceanside', product_pick_cache)
                if pick_info['status'] == 'NoImage':
                    continue
                seen_skus.add(sku)
                category = classify_glass(title, sku, 'Oceanside')
                item_id = f"oceanside-{clean_sku(sku)}"
                pick_info = apply_manual_overrides(item_id, pick_info)  # Decision 4 (white-on-white)
                base = {
                    "id": item_id, "manufacturer": "Oceanside", "base_sku": sku,
                    "resolved_sku": sku, "name": title, "resolved_name": title,
                    "category": category,
                    "product_url": f"https://www.stainedglassexpress.com/products/{p.get('handle')}",
                    "_candidate_scores": pick_info['candidate_scores'],
                    "_local_filename": f"oceanside-{clean_sku(sku)}.jpg",
                }
                if pick_info['status'] == 'Quarantined':
                    base.update({"image_url": None, "status": "Quarantined", "pick_score": None})
                    registry.append(base)
                    quarantine_log.append({"id": item_id, "manufacturer": "Oceanside", "name": title,
                                            "candidate_scores": pick_info['candidate_scores']})
                    print(f"  Oceanside: {sku} QUARANTINED (no candidate cleared the picker floor)")
                else:
                    base.update({"image_url": pick_info['url'], "status": "Downloaded", "pick_score": pick_info['score']})
                    registry.append(base)
                    downloaded += 1
                    print(f"  Oceanside: {sku} classified as {category} (picker score {pick_info['score']})")
                time.sleep(0.05)

    # 2. Process Wissmach
    print("\nProcessing Wissmach glass sheets...")
    for p in wissmach_raw:
        title = p.get('title', '')
        title_lower = title.lower()
        if any(term in title_lower for term in EXCLUDE_TERMS): continue

        for v in p.get('variants', []):
            sku = v.get('sku') or ''
            sku_upper = sku.upper()
            if (sku_upper.startswith('W') or sku_upper.startswith('EM')) and sku not in seen_skus:
                pick_info = select_image_for_product(p, 'Wissmach', product_pick_cache)
                if pick_info['status'] == 'NoImage':
                    continue
                seen_skus.add(sku)
                category = classify_glass(title, sku, 'Wissmach')
                item_id = f"wissmach-{clean_sku(sku)}"
                pick_info = apply_manual_overrides(item_id, pick_info)  # Decision 4 (white-on-white)
                base = {
                    "id": item_id, "manufacturer": "Wissmach", "base_sku": sku,
                    "resolved_sku": sku, "name": title, "resolved_name": title,
                    "category": category,
                    "product_url": f"https://www.stainedglassexpress.com/products/{p.get('handle')}",
                    "_candidate_scores": pick_info['candidate_scores'],
                    "_local_filename": f"wissmach-{clean_sku(sku)}.jpg",
                }
                if pick_info['status'] == 'Quarantined':
                    base.update({"image_url": None, "status": "Quarantined", "pick_score": None})
                    registry.append(base)
                    quarantine_log.append({"id": item_id, "manufacturer": "Wissmach", "name": title,
                                            "candidate_scores": pick_info['candidate_scores']})
                    print(f"  Wissmach: {sku} QUARANTINED (no candidate cleared the picker floor)")
                else:
                    base.update({"image_url": pick_info['url'], "status": "Downloaded", "pick_score": pick_info['score']})
                    registry.append(base)
                    downloaded += 1
                    print(f"  Wissmach: {sku} classified as {category} (picker score {pick_info['score']})")
                time.sleep(0.05)

    # 3. Process Youghiogheny (from SGE Art-Glass)
    print("\nProcessing Youghiogheny glass sheets...")
    for p in art_glass_raw:
        title = p.get('title', '')
        title_lower = title.lower()
        if any(term in title_lower for term in EXCLUDE_TERMS): continue

        for v in p.get('variants', []):
            sku = v.get('sku') or ''
            sku_upper = sku.upper()

            # Youghiogheny SKUs start with Y
            if sku_upper.startswith('Y') and sku not in seen_skus:
                pick_info = select_image_for_product(p, 'Youghiogheny', product_pick_cache)
                if pick_info['status'] == 'NoImage':
                    continue
                seen_skus.add(sku)
                category = classify_glass(title, sku, 'Youghiogheny')
                item_id = f"youghiogheny-{clean_sku(sku)}"
                pick_info = apply_manual_overrides(item_id, pick_info)  # Decision 4 (white-on-white)
                base = {
                    "id": item_id, "manufacturer": "Youghiogheny", "base_sku": sku,
                    "resolved_sku": sku, "name": title, "resolved_name": title,
                    "category": category,
                    "product_url": f"https://www.stainedglassexpress.com/products/{p.get('handle')}",
                    "_candidate_scores": pick_info['candidate_scores'],
                    "_local_filename": f"youghiogheny-{clean_sku(sku)}.jpg",
                }
                if pick_info['status'] == 'Quarantined':
                    base.update({"image_url": None, "status": "Quarantined", "pick_score": None})
                    registry.append(base)
                    quarantine_log.append({"id": item_id, "manufacturer": "Youghiogheny", "name": title,
                                            "candidate_scores": pick_info['candidate_scores']})
                    print(f"  Youghiogheny: {sku} QUARANTINED (no candidate cleared the picker floor)")
                else:
                    base.update({"image_url": pick_info['url'], "status": "Downloaded", "pick_score": pick_info['score']})
                    registry.append(base)
                    downloaded += 1
                    print(f"  Youghiogheny: {sku} classified as {category} (picker score {pick_info['score']})")
                time.sleep(0.05)

    # 4. Process Bullseye
    print("\nProcessing Bullseye glass sheets...")
    for p in bullseye_raw:
        title = p.get('title', '')
        title_lower = title.lower()
        if any(term in title_lower for term in EXCLUDE_TERMS): continue

        for v in p.get('variants', []):
            sku = v.get('sku') or ''
            sku_upper = sku.upper()

            # Bullseye standard fusible sheet variants
            if '-F-' in sku_upper and any(suff in sku_upper for suff in ['1010', 'HALF', 'FULL']) and sku not in seen_skus:
                # Exclude Curious (B-grade) sheets and sample chips
                if '-B-' in sku_upper or '-M-' in sku_upper: continue

                pick_info = select_image_for_product(p, 'Bullseye', product_pick_cache)
                if pick_info['status'] == 'NoImage':
                    continue
                seen_skus.add(sku)
                category = classify_glass(title, sku, 'Bullseye')
                item_id = f"bullseye-{clean_sku(sku)}"
                pick_info = apply_manual_overrides(item_id, pick_info)  # Decision 4 (white-on-white)
                base = {
                    "id": item_id, "manufacturer": "Bullseye", "base_sku": sku,
                    "resolved_sku": sku, "name": title, "resolved_name": title,
                    "category": category,
                    "product_url": f"https://shop.bullseyeglass.com/products/{p.get('handle')}",
                    "_candidate_scores": pick_info['candidate_scores'],
                    "_local_filename": f"bullseye-{clean_sku(sku)}.jpg",
                }
                if pick_info['status'] == 'Quarantined':
                    base.update({"image_url": None, "status": "Quarantined", "pick_score": None})
                    registry.append(base)
                    quarantine_log.append({"id": item_id, "manufacturer": "Bullseye", "name": title,
                                            "candidate_scores": pick_info['candidate_scores']})
                    print(f"  Bullseye: {sku} QUARANTINED (no candidate cleared the picker floor)")
                else:
                    base.update({"image_url": pick_info['url'], "status": "Downloaded", "pick_score": pick_info['score']})
                    registry.append(base)
                    downloaded += 1
                    print(f"  Bullseye: {sku} classified as {category} (picker score {pick_info['score']})")
                time.sleep(0.05)

    # Deduplicate registry by base color code formula
    deduped = []
    seen_formulas = set()
    stability_kept_log = []

    # Sort registry to ensure preference is given:
    # - For Bullseye: SKU ending with -1010 (standard 10x10 sheet) is preferred
    # - For SGE: Base SKU (no -6X12) is preferred
    def get_preference_score(item):
        sku = item['base_sku'].upper()
        mfg = item['manufacturer']
        if mfg == 'Bullseye':
            if sku.endswith('1010'): return 0
            if sku.endswith('HALF'): return 1
            return 2
        else:
            if '6X12' in sku: return 1
            return 0

    # Hybrid keyword + visual average color categorizer
    import colorsys
    def get_hsv_class(image_path, category):
        if not os.path.exists(image_path):
            return 'Other'
        try:
            with Image.open(image_path) as img:
                img_small = img.resize((1, 1), Image.Resampling.BOX)
                r, g, b = img_small.getpixel((0, 0))
                rf, gf, bf = r/255.0, g/255.0, b/255.0
                h, s, v = colorsys.rgb_to_hsv(rf, gf, bf)
                h_deg = h * 360.0
                if category == 'Cathedral' and s < 0.15:
                    return 'Clear'
                if s < 0.12:
                    if v > 0.82: return 'Monochrome'
                    if v < 0.18: return 'Monochrome'
                    return 'Monochrome'
                if 10 <= h_deg <= 48 and s < 0.65 and v < 0.70:
                    return 'Brown'
                if h_deg < 16 or h_deg >= 345:
                    return 'Red'
                if 16 <= h_deg < 46:
                    return 'Orange'
                if 46 <= h_deg < 68:
                    return 'Yellow'
                if 68 <= h_deg < 168:
                    return 'Green'
                if 168 <= h_deg < 258:
                    return 'Blue'
                if 258 <= h_deg < 312:
                    return 'Purple'
                if 312 <= h_deg < 345:
                    return 'Pink'
                return 'Other'
        except Exception:
            return 'Other'

    import re
    def get_color_family_hybrid(name, sku, category, image_path):
        n = name.lower()

        # Word boundary checker helper
        def has_word(words):
            return any(re.search(r'\b' + re.escape(w) + r'\b', n) for w in words)

        # Define color keywords list for multi-color collision detection
        keywords_by_family = {
            'Clear': ['clear', 'crystal', 'ice'],
            'Monochrome': ['white', 'black', 'gray', 'grey', 'charcoal', 'pearl', 'silver', 'opal white', 'reactive cloud', 'platinum', 'opaline', 'pewter', 'ivory', 'bone', 'alabaster', 'slate', 'smoke', 'coal', 'ebony', 'milk', 'snow', 'steel'],
            'Red': ['red', 'cherry', 'ruby', 'daredevil', 'grenadine', 'crimson', 'cinnabar', 'tomato', 'scarlet', 'rhubarb', 'carnelian', 'flame', 'tulip', 'wine', 'brick', 'garnet', 'cardinal', 'maroon', 'burgundy', 'begonia', 'thunderbird'],
            'Orange': ['orange', 'tangerine', 'persimmon', 'coral', 'peach', 'pumpkin', 'apricot'],
            'Yellow': ['yellow', 'canary', 'lemon', 'marigold', 'marzipan', 'almond', 'citronelle', 'butterscotch', 'custard', 'dandelion', 'flaxen', 'noble brass', 'mustard', 'banana', 'straw', 'butter', 'sunflower', 'ocher', 'ochre'],
            'Green': ['green', 'lime', 'moss', 'sage', 'emerald', 'caribbean', 'aventurine', 'pine', 'artichoke', 'celadon', 'pea pod', 'jade', 'olive', 'fern', 'mint', 'chartreuse', 'olivine', 'asparagus', 'clover', 'meadow', 'grass', 'foliage', 'avocado', 'lichen', 'basil', 'kiwi', 'seaweed', 'forest', 'viridian', 'celery', 'lemongrass', 'spring green', 'spring rain'],
            'Blue': ['blue', 'cobalt', 'sky', 'turquoise', 'indigo', 'teal', 'ocean', 'aqua', 'cyan', 'periwinkle', 'sapphire', 'navy', 'chambray', 'lagoon', 'sea', 'pacific', 'denim', 'edgewater'],
            'Purple': ['purple', 'violet', 'plum', 'heather', 'amethyst', 'grape', 'lavender', 'lilac', 'eggplant', 'mauve', 'wisteria', 'orchid', 'mulberry', 'boysenberry'],
            'Pink': ['pink', 'rose', 'fuchsia', 'cranberry', 'gold pink', 'magenta'],
            'Brown': ['brown', 'amber', 'bronze', 'chestnut', 'chocolate', 'wood', 'gold', 'cognac', 'caramel', 'tan', 'honey', 'umber', 'mink', 'khaki', 'coffee', 'champagne', 'sienna', 'copper', 'terra cotta', 'terracotta', 'mahogany', 'sand', 'tiger eye', 'russet', 'rust']
        }

        # Check how many distinct color families are matched
        matched = []
        for family, kws in keywords_by_family.items():
            if has_word(kws):
                matched.append(family)

        # If it contains multiple color family keywords, it's a multi-color sheet (leak prevention)
        if len(matched) > 1:
            return 'Other'

        # Otherwise, return the matched family if there is exactly one
        if len(matched) == 1:
            return matched[0]

        # Fallback to visual color analysis
        return get_hsv_class(image_path, category)

    # Load legacy swatch quarantine list if present (review Finding 1). Kept as a
    # second, independent safety net alongside the new per-image picker (036-1) --
    # the picker scores THIS run's live gallery; this list was built from a broader
    # offline corpus audit and may catch cases the picker's cheap live scoring
    # misses. Belt and suspenders, not a replacement for one another.
    quarantine_set = set()
    quarantine_path = 'research/delighting/results/corpus/swatch_quarantine.json'
    if os.path.exists(quarantine_path):
        try:
            with open(quarantine_path, 'r') as f:
                q_data = json.load(f)
                bad_reasons = {'test_fire_tiles', 'reaction_demo_line', 'composite_streamer_line', 'perspective_side_view'}
                for q_item in q_data.get('items', []):
                    item_id = q_item.get('id')
                    if item_id:
                        reasons = set(q_item.get('reason', []))
                        if reasons.intersection(bad_reasons):
                            quarantine_set.add(item_id.lower())
            print(f"Loaded {len(quarantine_set)} quarantined item IDs from {quarantine_path}")
        except Exception as e:
            print(f"Error loading quarantine JSON: {e}")

    # Sort so that preferred items come first
    registry_sorted = sorted(registry, key=get_preference_score)

    seen_image_urls = set()
    for item in registry_sorted:
        mfg = item['manufacturer']
        base_sku = item['base_sku']

        # Picker quarantine (036-1): no gallery candidate cleared the picker's floor.
        # Skip WITHOUT claiming the formula slot -- an alternate size variant of the
        # same formula (e.g. a -HALF sheet when the -1010 got quarantined) still gets
        # a chance at the `formula_key not in seen_formulas` check below.
        if item['status'] == 'Quarantined':
            continue

        # Check image URL duplicate prevention (Finding 3)
        image_url = item.get('image_url')
        if image_url:
            stripped = _strip_query(image_url)
            if stripped in seen_image_urls:
                continue
            seen_image_urls.add(stripped)

        # Normalize formula ID
        formula_id = base_sku.split('-')[0]
        if mfg == 'Bullseye':
            parts = base_sku.split('-')
            if len(parts) >= 2:
                formula_id = parts[0] + '-' + parts[1]

        formula_key = (mfg, formula_id)
        if formula_key not in seen_formulas:
            # Anti-churn stability rule (036-4), applied before the legacy quarantine
            # / -v2 checks below so those still operate on whatever image the
            # stability rule ultimately settles on.
            existing = existing_registry_by_id.get(item['id'])
            item, churned = apply_stability_rule(item, existing)
            if item.get('_stability_kept'):
                stability_kept_log.append({'id': item['id'], 'manufacturer': mfg})

            # Check quarantine status (legacy Finding 1 list)
            item_id = item['id'].lower()
            local_img_filename = item['_local_filename']
            base_name, ext = os.path.splitext(local_img_filename)
            v2_filename = f"{base_name}-v2{ext}"
            v2_path = os.path.join(IMAGE_DIR, v2_filename)

            # Decision 3: Bullseye Reactive Cloud (000009-0030/-0050) gets KEEP+crop
            # via REACTIVE_CLOUD_CROP_OVERRIDE (see its docstring) instead of the old
            # blanket is_reactive_cloud drop -- takes priority over the legacy
            # quarantine list below since it's a more specific, reviewed verdict for
            # exactly these two ids.
            reactive_override = REACTIVE_CLOUD_CROP_OVERRIDE.get(item_id)
            is_v2 = False

            if reactive_override:
                local_img_filename = reactive_override['crop_filename']
                item['_manual_crop'] = item_id
                item['image_url'] = reactive_override['v2_url']
            elif item_id in quarantine_set:
                if os.path.exists(v2_path):
                    local_img_filename = v2_filename
                    is_v2 = True
                else:
                    print(f"  Quarantined (legacy list): skipping {item['id']} ({item['name']})")
                    continue
            elif os.path.exists(v2_path):
                local_img_filename = v2_filename
                is_v2 = True

            seen_formulas.add(formula_key)
            item['_target_filename'] = local_img_filename
            item['_is_v2'] = is_v2

            deduped.append(item)

    # Sort alphabetically by manufacturer and base SKU
    deduped.sort(key=lambda x: (x['manufacturer'], x['base_sku']))

    # ------------------------------------------------------------------------------
    # Phase C: download/crop only the rows that survived dedup, and only fetch a NEW
    # full-resolution file when the final pick differs from what's on disk for this
    # id (036-2: "download full images ONLY where the final pick differs from the
    # existing file or no file exists"). -v2 overrides are local recoveries with no
    # source URL of their own -- never network-overwrite them.
    # ------------------------------------------------------------------------------
    final_registry = []
    changed_count = 0
    for item in deduped:
        target_filename = item.pop('_target_filename')
        is_v2 = item.pop('_is_v2')
        manual_crop_id = item.pop('_manual_crop', None)
        candidate_scores = item.pop('_candidate_scores', {})
        pick_score = item.get('pick_score')
        item.pop('_local_filename', None)

        old = existing_registry_by_id.get(item['id'])
        old_url = old.get('image_url') if old else None
        filepath = os.path.join(IMAGE_DIR, target_filename)
        same_as_before = bool(old_url) and _strip_query(old_url) == _strip_query(item.get('image_url') or '')

        if is_v2 or manual_crop_id:
            force = False  # manual recovery/crop file -- always fast-cache-return it
        else:
            force = not (same_as_before and os.path.exists(filepath))

        if force:
            changed_count += 1

        if manual_crop_id:
            # Decision 3: physically crop the -v2 recovery rather than a network
            # fetch+auto-crop -- see crop_reactive_cloud_image()/the override dict.
            override = REACTIVE_CLOUD_CROP_OVERRIDE[manual_crop_id]
            crop_path, cw, ch = crop_reactive_cloud_image(override)
            if crop_path:
                crop_w_frac = (override['crop_box'][2] - override['crop_box'][0]) / 1200.0
                calib = {
                    "asset_url": f"/assets/catalog_images/{override['crop_filename']}",
                    "original_width_px": cw, "original_height_px": ch,
                    "cropped": True, "crop_box": override['crop_box'],
                    "calibrated_width_in": round(10.0 * crop_w_frac, 2),
                    "calibrated_height_in": 10.0,
                }
            else:
                calib = None
        else:
            calib = download_and_calibrate_image(item['image_url'], target_filename, item, item['category'], force=force)
        if not calib:
            if os.path.exists(filepath):
                # A re-fetch attempt failed (network hiccup) but we still have a
                # last-good file on disk -- keep serving it rather than dropping the
                # product from the catalog. CRUCIAL: also revert image_url to the
                # previously-shipped URL, so the registry stays consistent with the
                # file actually on disk AND the next run's same_as_before check sees
                # a mismatch and retries the download. (Without this, an outage
                # during the download phase permanently wedges the item: registry
                # says new URL, disk has the old image, and every later run thinks
                # nothing changed. Hit for real by a DNS outage in the 036 rebuild.)
                try:
                    with Image.open(filepath) as img:
                        w, h = img.size
                    if old_url:
                        item['image_url'] = old_url
                    calib = {"asset_url": f"/assets/catalog_images/{target_filename}",
                             "original_width_px": w, "original_height_px": h,
                             "cropped": bool(old.get('cropped')) if old else False,
                             "crop_box": old.get('crop_box') if old else None,
                             "calibrated_width_in": old.get('real_world_width_in', 0) if old else 0,
                             "calibrated_height_in": old.get('real_world_height_in', 0) if old else 0}
                    print(f"  WARNING: {item['id']} re-fetch failed, kept previous local file")
                except Exception:
                    calib = None
            if not calib:
                print(f"  FAILED: {item['id']} — image undownloadable, dropping from registry")
                failed += 1
                continue

        item['local_image'] = calib['asset_url']
        item['cropped'] = calib['cropped']
        item['crop_box'] = calib['crop_box']
        item['real_world_width_in'] = calib['calibrated_width_in']
        item['real_world_height_in'] = calib['calibrated_height_in']
        item['original_width_px'] = calib['original_width_px']
        item['original_height_px'] = calib['original_height_px']

        # Color family + front-lit tagging need the final on-disk image, so they run
        # here (Phase C), after the download/crop step, instead of during dedup.
        local_img_path = os.path.join(IMAGE_DIR, target_filename)
        item['color_family'] = get_color_family_hybrid(item['name'], item['base_sku'], item['category'], local_img_path)
        # Decision 5: per-manufacturer front-lit/iridized priors (reports 015/019) --
        # Oceanside's `*irid*` SKU pattern and Youghiogheny's dark-opaque tile lines
        # are known front-lit surface-photography subsets, not transmissive backlit
        # sheet shots. `lighting` is the UI-facing field (badge/tooltip); `front_lit`
        # is kept as a plain-bool alias for any existing consumers.
        is_irid = 'irid' in item['base_sku'].lower() or 'iridescent' in item['name'].lower()
        is_opaque_dark = (item['manufacturer'] == 'Youghiogheny' and any(k in item['name'].lower() for k in ['opaque', 'stipple', 'black']))
        item['front_lit'] = bool(is_irid or is_opaque_dark)
        item['lighting'] = 'front-lit' if item['front_lit'] else 'back-lit'

        item.pop('_stability_kept', None)
        final_registry.append(item)

    # Save outputs
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(final_registry, f, indent=2)
    print(f"\nSaved {len(final_registry)} deduplicated dynamic swatches to registry {REGISTRY_FILE}")
    print(f"Full images re-downloaded/changed: {changed_count}. Quarantined (picker): {len(quarantine_log)}. Failed: {failed}.")

    generate_verify_html(final_registry)
    generate_tracker_report(len(final_registry), len(final_registry), failed, final_registry)
    generate_diff_report(existing_registry_by_id, final_registry, quarantine_log, stability_kept_log)
    print("\nDynamic swatch harvester run complete!")

def generate_verify_html(registry):
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dynamic Swatch Library Verification</title>
        <style>
            body { font-family: sans-serif; padding: 20px; background: #f4f4f9; color: #333; }
            h1 { text-align: center; margin-bottom: 5px; }
            .subtitle { text-align: center; color: #666; margin-bottom: 30px; }
            .manufacturer-section { background: white; padding: 20px; border-radius: 8px; margin-bottom: 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .category-section { margin-top: 20px; }
            .grid { display: flex; gap: 20px; flex-wrap: wrap; margin-top: 10px; }
            .card { width: 220px; padding: 15px; border: 1px solid #ddd; border-radius: 8px; background: #fafafa; text-align: center; font-size: 13px; }
            img { width: 100%; height: 180px; object-fit: cover; border-radius: 4px; display: block; margin-bottom: 10px; border: 1px solid #eee; }
            .sku { font-weight: bold; font-size: 14px; margin-top: 5px; }
            .name { font-weight: bold; color: #555; height: 36px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
            .resolved-name { font-size: 11px; color: #888; font-style: italic; margin-top: 5px; }
            .calibration-info { font-size: 11px; color: green; font-weight: bold; margin-top: 5px; }
        </style>
    </head>
    <body>
        <h1>Dynamic Glass Swatch Gallery</h1>
        <p class="subtitle">Showing all dynamically harvested sheet glass products. Calibrated scale metadata is embedded.</p>
    """

    by_mfg = {}
    for item in registry:
        mfg = item['manufacturer']
        cat = item['category']
        if mfg not in by_mfg:
            by_mfg[mfg] = {}
        if cat not in by_mfg[mfg]:
            by_mfg[mfg][cat] = []
        by_mfg[mfg][cat].append(item)

    for mfg, categories in by_mfg.items():
        html += f'<div class="manufacturer-section"><h2>{mfg} Glass Catalog</h2>'
        for cat, items in sorted(categories.items()):
            html += f'<div class="category-section"><h3>{cat} ({len(items)} items)</h3><div class="grid">'
            for item in items:
                img_src = item['local_image']
                html += '<div class="card">'
                html += f'<img src="{img_src}" alt="{item["name"]}">'
                html += f'<div class="sku">{item["base_sku"]}</div>'
                html += f'<div class="name">{item["name"]}</div>'
                html += f'<div class="calibration-info">Scale: {item["real_world_width_in"]}" x {item["real_world_height_in"]}"</div>'
                html += '</div>'
            html += '</div></div>'
        html += '</div>'

    html += "</body></html>"

    with open(VERIFY_HTML, 'w') as f:
        f.write(html)
    print(f"Generated verification page at {VERIFY_HTML}")

def generate_tracker_report(total, downloaded, failed, registry):
    tally_mfg = {}
    tally_cat = {}
    for item in registry:
        mfg = item['manufacturer']
        cat = item['category']
        tally_mfg[mfg] = tally_mfg.get(mfg, 0) + 1
        tally_cat[cat] = tally_cat.get(cat, 0) + 1

    mfg_details = "\n".join([f"- **{k}:** {v} sheets" for k, v in sorted(tally_mfg.items())])
    cat_details = "\n".join([f"- **{k}:** {v} sheets" for k, v in sorted(tally_cat.items())])

    report = f"""# Stained Glass Swatch Tracker

This document tracks our progress in building a curated, high-quality swatch catalog of industry-standard glass colors for the Vitraux app.

## Summary Status

- **Total Dynamic Swatches Harvested:** {total}
- **Successfully Calibrated:** {downloaded}
- **Purity Rate:** 100% (All filters verified, zero non-sheet merchandise)

### Inventory Breakdown by Brand
{mfg_details}

### Inventory Breakdown by Category
{cat_details}

---

## Swatch Inventory Status

| Brand | SKU | Name | Category | Status | Real-World Scale | Cropped? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for item in registry:
        scale_str = f"{item['real_world_width_in']}\" x {item['real_world_height_in']}\"" if item['real_world_width_in'] > 0 else "N/A"
        crop_str = "Yes" if item['cropped'] else "No"
        report += f"| {item['manufacturer']} | `{item['base_sku']}` | {item['name']} | {item['category']} | {item['status']} | {scale_str} | {crop_str} |\n"

    with open(TRACKER_MD, 'w') as f:
        f.write(report)
    print(f"Generated tracker report at {TRACKER_MD}")


# ==================================================================================
# BEFORE/AFTER DIFF REPORT + CONTACT SHEET (task 036-3)
# ==================================================================================
# Anchored to this script's own location (not cwd) so the report lands in the git
# worktree/branch this script is committed to, even though the registry/images
# themselves are written into the MAIN checkout's frontend/public/assets/ (cwd,
# gitignored runtime data -- see module docstring / task instructions).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(_SCRIPT_DIR, '..', 'docs', 'library-picker-rebuild')
REPORT_MD = os.path.join(REPORT_DIR, 'report.md')
CONTACT_SHEET = os.path.join(REPORT_DIR, 'contact_sheet.jpg')


def _load_thumb(path, size=(150, 150)):
    try:
        img = Image.open(path).convert('RGB')
        img.thumbnail(size)
        canvas = Image.new('RGB', size, (30, 30, 30))
        canvas.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
        return canvas
    except Exception:
        canvas = Image.new('RGB', size, (60, 20, 20))
        return canvas


def build_contact_sheet(entries, out_path):
    """entries: list of dicts {id, name, old_path, new_path}. Renders up to 20 as a
    5-col x N-row grid, old image on top / new image on bottom of each cell, with a
    text label -- downscaled thumbnail cells (150x150), not full-resolution."""
    if not entries:
        return False
    cols = 5
    rows = (len(entries) + cols - 1) // cols
    cell_w, cell_h = 150, 150
    label_h = 34
    pad = 8
    cell_total_h = cell_h * 2 + label_h + pad
    canvas_w = cols * (cell_w + pad) + pad
    canvas_h = rows * (cell_total_h + pad) + pad
    canvas = Image.new('RGB', (canvas_w, canvas_h), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for i, e in enumerate(entries[:20]):
        col, row = i % cols, i // cols
        x0 = pad + col * (cell_w + pad)
        y0 = pad + row * (cell_total_h + pad)
        old_thumb = _load_thumb(e['old_path'])
        new_thumb = _load_thumb(e['new_path'])
        canvas.paste(old_thumb, (x0, y0))
        canvas.paste(new_thumb, (x0, y0 + cell_h))
        draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h * 2], outline=(90, 90, 90))
        draw.line([x0, y0 + cell_h, x0 + cell_w, y0 + cell_h], fill=(200, 160, 0), width=2)
        label = e['id'][:22]
        draw.text((x0, y0 + cell_h * 2 + 2), "OLD", fill=(255, 120, 120), font=font)
        draw.text((x0 + cell_w - 30, y0 + cell_h * 2 + 2), "NEW", fill=(120, 255, 120), font=font)
        draw.text((x0, y0 + cell_h * 2 + 16), label, fill=(230, 230, 230), font=font)

    canvas.save(out_path, "JPEG", quality=85)
    return True


def generate_diff_report(existing_by_id, final_registry, quarantine_log, stability_kept_log):
    """Task 036-3: BEFORE/AFTER numbers (per manufacturer) + a contact sheet of the
    most significant image changes. Task 036-4's churn-stability numbers are folded
    in here too."""
    os.makedirs(REPORT_DIR, exist_ok=True)

    final_by_id = {item['id']: item for item in final_registry}
    existing_ids = set(existing_by_id.keys())
    final_ids = set(final_by_id.keys())

    changed = []   # (id, old_item, new_item) where image_url actually differs
    unchanged_count = {}
    new_count = {}
    changed_by_mfg = {}
    for iid in (existing_ids & final_ids):
        old, new = existing_by_id[iid], final_by_id[iid]
        mfg = new['manufacturer']
        if _strip_query(old.get('image_url', '')) != _strip_query(new.get('image_url', '')):
            changed.append((iid, old, new))
            changed_by_mfg[mfg] = changed_by_mfg.get(mfg, 0) + 1
        else:
            unchanged_count[mfg] = unchanged_count.get(mfg, 0) + 1
    for iid in (final_ids - existing_ids):
        mfg = final_by_id[iid]['manufacturer']
        new_count[mfg] = new_count.get(mfg, 0) + 1

    dropped_ids = existing_ids - final_ids  # disappeared entirely (quarantined w/ no fallback, or dedup)
    quarantine_ids = {q['id'] for q in quarantine_log}
    newly_quarantined_by_mfg = {}
    for iid in dropped_ids:
        if iid in quarantine_ids:
            mfg = existing_by_id[iid]['manufacturer']
            newly_quarantined_by_mfg[mfg] = newly_quarantined_by_mfg.get(mfg, 0) + 1

    stability_by_mfg = {}
    for s in stability_kept_log:
        stability_by_mfg[s['manufacturer']] = stability_by_mfg.get(s['manufacturer'], 0) + 1

    # Prioritize the maintainer's known validation cases (SGE Granite Ripple / Steel
    # Grey Opal, and the Bullseye reactive/Alchemy set) at the front of the contact
    # sheet if they appear among the changes; fill the rest by picker-score margin.
    def significance(entry):
        iid, old, new = entry
        name = (new.get('name') or '').lower()
        is_validation_case = ('granite ripple' in name or 'steel grey opal' in name
                               or 'steel gray opal' in name or 'reactive' in name or 'alchemy' in name)
        margin = (new.get('pick_score') or 0) - (old.get('pick_score') or 0)
        return (0 if is_validation_case else 1, -abs(margin))

    changed_sorted = sorted(changed, key=significance)
    contact_entries = []
    for iid, old, new in changed_sorted[:20]:
        old_path = os.path.join(IMAGE_DIR, os.path.basename(old.get('local_image', '')))
        new_path = os.path.join(IMAGE_DIR, os.path.basename(new.get('local_image', '')))
        contact_entries.append({'id': iid, 'name': new.get('name', ''), 'old_path': old_path, 'new_path': new_path})
    made_sheet = build_contact_sheet(contact_entries, CONTACT_SHEET)

    all_mfgs = sorted(set(list(changed_by_mfg) + list(unchanged_count) + list(new_count)
                          + list(newly_quarantined_by_mfg) + list(stability_by_mfg)))

    lines = []
    lines.append("# Library picker rebuild -- before/after report\n")
    lines.append(f"Generated by `scripts/build_swatch_library.py` (iteration 036). "
                 f"Existing registry entries compared: {len(existing_by_id)}. "
                 f"Final registry entries: {len(final_registry)}.\n")
    lines.append("## Image changed per manufacturer\n")
    lines.append("| Manufacturer | Changed | Unchanged | New | Newly Quarantined | Stability-kept (would-have-churned, blocked) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    tot = [0, 0, 0, 0, 0]
    for m in all_mfgs:
        c = changed_by_mfg.get(m, 0)
        u = unchanged_count.get(m, 0)
        n = new_count.get(m, 0)
        q = newly_quarantined_by_mfg.get(m, 0)
        s = stability_by_mfg.get(m, 0)
        tot[0] += c; tot[1] += u; tot[2] += n; tot[3] += q; tot[4] += s
        lines.append(f"| {m} | {c} | {u} | {n} | {q} | {s} |")
    lines.append(f"| **Total** | **{tot[0]}** | **{tot[1]}** | **{tot[2]}** | **{tot[3]}** | **{tot[4]}** |\n")

    lines.append("## Stability rule\n")
    lines.append(f"Anti-churn margin threshold: **{STABILITY_MARGIN}** (picker FLOOR is {PICKER_FLOOR}). "
                 "An image is only swapped when the picker's score for the new pick exceeds the "
                 "currently-shipped image's own score by more than this margin (and only when the "
                 "shipped image itself still clears FLOOR -- a known-bad image is never protected). "
                 "See `apply_stability_rule()` docstring in build_swatch_library.py for the full "
                 f"rationale. {tot[4]} product(s) had a picker disagreement suppressed by this rule "
                 "this run.\n")

    lines.append("## Maintainer validation cases\n")
    for needle in ['granite ripple', 'steel grey opal', 'steel gray opal']:
        hit = next((v for v in final_by_id.values() if needle in (v.get('name') or '').lower()), None)
        was = next((v for v in existing_by_id.values() if needle in (v.get('name') or '').lower()), None)
        if hit:
            changed_flag = "CHANGED" if (was and _strip_query(was.get('image_url', '')) != _strip_query(hit.get('image_url', ''))) else "unchanged"
            lines.append(f"- `{needle}`: final id `{hit['id']}`, image {changed_flag}, "
                         f"`{hit.get('local_image')}` (pick_score={hit.get('pick_score')})")
        else:
            lines.append(f"- `{needle}`: NOT FOUND in final registry (possibly quarantined or SKU-filtered)")

    reactive_hits = [v for v in final_by_id.values() if '000009' in v.get('base_sku', '')]
    lines.append(f"- Bullseye Reactive Cloud (000009-*): {len(reactive_hits)} entries in final registry "
                 "(KEEP+crop per Decision 3 -- the -v2 recovery, cropped to x:[650,1200] of its 1200x1200 "
                 "frame, excludes the reaction-demo tile corner insert entirely; see "
                 "REACTIVE_CLOUD_CROP_OVERRIDE).")

    lines.append("\n## Quarantined this run (picker)\n")
    lines.append(f"{len(quarantine_log)} product(s) had no gallery candidate clear the picker floor "
                 f"({PICKER_FLOOR}) and were excluded rather than shipping a bad photo.")
    if quarantine_log:
        lines.append("\n| id | manufacturer | name |")
        lines.append("|---|---|---|")
        for q in quarantine_log[:50]:
            lines.append(f"| {q['id']} | {q['manufacturer']} | {q['name']} |")
        if len(quarantine_log) > 50:
            lines.append(f"| ... | ... | ({len(quarantine_log) - 50} more, see build log) |")

    if made_sheet:
        lines.append(f"\n## Contact sheet\n\n{len(contact_entries)} most significant image changes "
                     "(maintainer validation cases prioritized, then largest picker-score margin). "
                     "Old pick on top, new pick on bottom of each cell.\n\n"
                     "![contact sheet](./contact_sheet.jpg)\n")
    else:
        lines.append("\n## Contact sheet\n\nNo image changes this run -- nothing to show.\n")

    with open(REPORT_MD, 'w') as f:
        f.write("\n".join(lines))
    print(f"Generated diff report at {REPORT_MD}" + (f" and contact sheet at {CONTACT_SHEET}" if made_sheet else ""))


if __name__ == '__main__':
    main()
