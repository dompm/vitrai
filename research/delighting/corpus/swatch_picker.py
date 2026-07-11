"""swatch_picker.py -- scored swatch-picker: replaces positional image-pick heuristics.

Report 035. The maintainer's framing: "we're not always choosing the right image" --
product galleries mix real sheet swatches with customer photos (fingers in frame),
comparison shots (two sheets side-by-side), test-fire/reaction-demo tiles, lineup/
marketing shots, finished products; the correct image's POSITION varies per product
and is sometimes only stated in the description prose (see the SGE
"1st photo taken by a customer... the right picture is the fourth one" case in
glass-library-integration-review.md Addendum 2). Positional rules (`images[0]`,
`images[-1]`) cannot be correct across every product -- this module scores EVERY
candidate image and returns the argmax, or NONE if nothing clears a floor.

=====================================================================================
INTEGRATION GUIDANCE (read this before wiring into scripts/build_swatch_library.py)
=====================================================================================
This is a POST-DOWNLOAD VALIDATION GATE, not a scraper rewrite. Call it after a
product's full image list has been fetched (not just position 0) and before the
registry `append`:

    from swatch_picker import pick

    # product_images: list of local file paths for ALL of the product's gallery
    # images (download every one, not just images[0] -- see report 019 Patch #1).
    result = pick(product_images, text=product.get('body_html', '') + ' ' + product.get('title', ''),
                  name=product.get('title', ''), manufacturer=mfg)
    if result['pick'] is None:
        # nothing cleared the floor -> Quarantined, same posture as 019 Patch #2:
        # keep the file(s) on disk for audit, skip the registry append.
        status = 'Quarantined'
    else:
        local_image = product_images[result['pick']]
        # result['scores'] / result['reasons'] are worth logging alongside the
        # registry row for future audits (same posture as swatch_quarantine.json).

Cheap enough to run on every candidate at scrape time (no network, no ML weights --
same "no ML" posture as report 019's audit_flagger, which this module wraps as one
of five components). Nothing here mutates or deletes source images; like 019/024/033,
this is advisory judgment over data the scraper already fetched.

=====================================================================================
SCORING COMPONENTS (each in [0, 1], each exposed individually in `reasons`)
=====================================================================================
  (a) audit   -- reuses report 019's `audit_flagger.analyze_image`/`flag_signals`
                 (test-fire tiles, product-on-white lineup, white-ground blob stats)
                 plus 019's `flag_name` (Bullseye reactive/alchemy/composite name
                 blocklist) when `name`/`manufacturer` are supplied.
  (b) hand    -- hand/finger detection. Report 030 found skin-tone color ALONE fails
                 on pink/amber/tan art glass (a pink wispy sheet scored inside every
                 practical skin-color gate). This uses shape+edge cues FIRST: a
                 finger enters the frame from exactly ONE border as a compact,
                 moderately-solid protrusion that does not span the whole edge and
                 does not reach the opposite edge; color (a loosened Peer et al. 2003
                 RGB skin rule) is then required only within that already-constrained
                 blob. See "Honest weak spots" below -- this is deliberately
                 imprecise and the module says so in its own reason codes.
  (c) seam    -- comparison-shot detection: two-or-more distinct sheet regions
                 separated by a vertical seam/gap (a strong, tall, roughly-central
                 column of gradient energy that is NOT at the extreme left/right
                 edge -- an edge-hugging gradient peak is usually just the sheet's
                 own silhouette against its background, not an internal seam).
  (d) coverage-- full-bleed sheet coverage: reuses 019's `fg_frac`/`biggest_blob_frac`
                 (a proper swatch is edge-to-edge, continuous, one blob) combined
                 with a sharpness/focus gate (edge-restricted Laplacian/gradient
                 ratio, NOT raw whole-frame Laplacian variance -- see tunables
                 block for why) -- a blurry
                 macro/detail crop is not a representative catalog swatch even when
                 it technically fills the frame (see the steel-gray-opal validation
                 case: position 1 is a 100%-frame but heavily out-of-focus crop).
  (e) text    -- description/title text hints, parsed sentence-by-sentence:
                 ordinal + "customer" -> negative (customer photo); ordinal(s) +
                 "next to"/"compare"/"vs"/"beside" -> negative (comparison-shot
                 corroboration); ordinal(s) + "backlit" -> positive (explicitly the
                 correct photography mode for a transmissive swatch, see the
                 glass-library-integration-review.md front-lit/backlit finding);
                 an explicit "the right/correct picture/photo/image is the Nth"
                 statement is an OVERRIDE -- it forces the pick outright, bypassing
                 the floor and the visual components entirely, because it is a
                 human (the merchandiser) telling us the answer directly.

Final score = weighted sum of (a)-(d) [weights below, sum to 1.0], then the text
component (e) is added as a signed adjustment on top (it can swing the ranking, per
the task's "text hints override visual scores when explicit" -- an explicit override
is absolute; a non-explicit hint (backlit/customer/comparison) is a strong but not
absolute nudge). A candidate whose final score is below FLOOR is not eligible for the
argmax; if no candidate clears FLOOR (and no explicit override fired), `pick` is None.

=====================================================================================
HONEST WEAK SPOTS
=====================================================================================
  - Hand detector: precision is NOT high. Calibration on the 7-image validation set
    (see reports/035-swatch-picker.md) shows it catches the true finger photo but
    also fires on one true comparison-shot image whose amber glass tone and
    frame-edge geometry coincidentally resemble a finger protrusion -- in that
    specific case the comparison-seam detector independently rejects the same image,
    so the overall pick survives, but the hand *reason code* alone should not be
    trusted as a precise finger-diagnosis in isolation. It will also miss fingers
    that don't enter from a frame edge (e.g. a hand fully inside the frame holding a
    small sheet) and gloved/dark-skinned hands under the RGB rule's lighting
    assumptions -- no attempt was made to build a general skin classifier.
  - Seam/comparison detector: tuned for a roughly-vertical single seam near frame
    center; a comparison laid out horizontally, or with the seam very close to an
    edge, will likely be missed (by design -- edge-hugging peaks are down-weighted
    to avoid flagging a sheet's own silhouette edge as a "seam").
  - Coverage/sharpness: penalizes legitimate close-up detail shots that happen to be
    slightly soft-focus; the Laplacian threshold is calibrated on exactly two
    real-world examples (see validation) and should be treated as directional, not
    precise.
  - Text parser: regex/sentence-scoped, not a real NLP parser. Ordinal words above
    "tenth" are not recognized; multi-clause sentences that separate an ordinal from
    its keyword by a long distance will be missed. It has no cross-sentence
    coreference ("the first one... it shows...").
  - None of this is ML; it inherits 019's "cheap, no ML" posture and its limits.
"""
import argparse
import html
import json
import os
import re
import sys

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_flagger as af  # noqa: E402  (report 019's flagger, reused as component 'a')

# --------------------------------------------------------------------------------
# tunables
# --------------------------------------------------------------------------------
RESIZE = 320

WEIGHTS = {'audit': 0.28, 'hand': 0.20, 'seam': 0.20, 'coverage': 0.32}
FLOOR = 0.45
LINE_PENALTY = 0.12   # uniform floor penalty when 019's name blocklist flags the product LINE
                       # (does not affect ranking between a product's own candidates, see pick())

# -- hand/finger geometry+color gate (component b) --
HAND_BORDER_FRAC = 0.03      # outer ring counted as "touching the border"
HAND_EDGES_MAX = 1           # a finger touches exactly one edge; 2+ = background band
HAND_SPAN = (0.03, 0.40)     # fraction of the touched edge the blob spans
HAND_DEPTH = (0.08, 0.65)    # how far the blob reaches into the frame
HAND_AREA = (0.008, 0.20)    # blob area as a fraction of the frame
HAND_SOLIDITY = (0.28, 0.78) # area / bbox-area -- rounded protrusion, not a rectangle

# -- comparison-shot seam gate (component c) --
SEAM_PEAK_RATIO_MIN = 1.8    # peak column gradient vs inner-frame median
SEAM_COL_FRAC = (0.15, 0.85) # seam must sit away from the extreme edges
SEAM_TALL_FRAC_MIN = 0.20    # the seam must run tall (not a short local edge)

# -- coverage/sharpness gate (component d) --
# Raw Laplacian variance (the textbook "blur metric") CANNOT distinguish a blurry
# photo from a sharp photo of a genuinely smooth/glossy subject -- a solid-color
# transparent Bullseye sheet has almost no texture at all, so its whole-frame
# Laplacian variance can land in the SAME range as an out-of-focus macro crop (both
# ~20 in this module's units; caught during the 20-product regression validation,
# where a clean smooth-red sheet was scoring near-zero on sharpness alongside a
# genuinely bad clamped/labeled photo of the same product -- see reports/035). Fix:
# restrict the ratio to only the frame's strongest-gradient pixels (top 15%) --
# "how crisp are the edges that DO exist," which stays meaningful even when the
# subject has very few edges, instead of "how much high-frequency energy is there
# in the whole frame," which conflates "blurred" with "nothing to blur."
EDGE_SHARP_PERCENTILE = 85
EDGE_SHARP_LO, EDGE_SHARP_HI = 0.22, 0.55   # calibrated on the maintainer + regression sets
# a pale/near-clear sheet (Bullseye "Ice"/"Crystal" lines, report 019 SS2) can read as
# ~100% white_frac to audit_flagger's color threshold -- optically indistinguishable
# from a blank studio background by color alone. Disambiguate by whole-frame
# grayscale std: a blank background is nearly flat (camera-noise-only, std ~2-4 in
# calibration); genuine pale glass still carries faint ripple/refraction texture
# (std ~8 in the validation case that exposed this, report 035).
PALE_SHEET_FG_MAX = 0.02
PALE_SHEET_STD_MIN = 4.5
PALE_SHEET_CREDIT = 0.55

# --------------------------------------------------------------------------------
# image loading
# --------------------------------------------------------------------------------

def _load(path):
    im = Image.open(path).convert('RGB')
    im.thumbnail((RESIZE, RESIZE))
    return np.asarray(im, dtype=np.uint8)


# --------------------------------------------------------------------------------
# component (b): hand / finger
# --------------------------------------------------------------------------------

def _skin_mask_rgb(a):
    """Loosened Peer et al. (2003) RGB skin rule. Deliberately permissive on its
    own -- see module docstring; it is only trustworthy once shape-gated."""
    R = a[..., 0].astype(np.int16)
    G = a[..., 1].astype(np.int16)
    B = a[..., 2].astype(np.int16)
    mx = a.max(-1).astype(np.int16)
    mn = a.min(-1).astype(np.int16)
    rule = (R > 95) & (G > 40) & (B > 20) & ((mx - mn) > 15) & (np.abs(R - G) > 15) & (R > G) & (R > B)
    return rule.astype(np.uint8)


def hand_signals(a):
    """Return (flagged: bool, confidence: float, blobs: list) for hand/finger cues."""
    h, w = a.shape[:2]
    skin = _skin_mask_rgb(a)
    if cv2 is not None:
        skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        skin = cv2.morphologyEx(skin, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, lbl, stats, _ = cv2.connectedComponentsWithStats(skin, connectivity=8)
        comps = [(stats[i][0], stats[i][1], stats[i][2], stats[i][3], stats[i][4]) for i in range(1, n)]
    else:  # pragma: no cover -- scipy fallback if cv2 unavailable
        from scipy import ndimage
        lbl, n = ndimage.label(skin)
        objs = ndimage.find_objects(lbl)
        comps = []
        for sl in objs:
            y0, y1 = sl[0].start, sl[0].stop
            x0, x1 = sl[1].start, sl[1].stop
            area = int((lbl[sl] > 0).sum())
            comps.append((x0, y0, x1 - x0, y1 - y0, area))

    frame = h * w
    border = max(1, int(HAND_BORDER_FRAC * min(h, w)))
    qualifying = []
    all_blobs = []
    for x, y, bw, bh, area in comps:
        area_frac = area / frame
        if area_frac < 0.003:
            continue
        touches = []
        if x <= border:
            touches.append('L')
        if (x + bw) >= w - border:
            touches.append('R')
        if y <= border:
            touches.append('T')
        if (y + bh) >= h - border:
            touches.append('B')
        if not touches:
            continue
        spans = []
        if 'L' in touches or 'R' in touches:
            spans.append(bh / h)
        if 'T' in touches or 'B' in touches:
            spans.append(bw / w)
        span_frac = min(spans) if spans else 1.0
        depth = (bw / w) if ('L' in touches or 'R' in touches) else (bh / h)
        bbox_area = max(1, bw * bh)
        solidity = area / bbox_area
        blob = {'area_frac': round(float(area_frac), 4), 'span_frac': round(float(span_frac), 3),
                'depth': round(float(depth), 3), 'solidity': round(float(solidity), 3),
                'n_edges': len(touches), 'edges': touches}
        all_blobs.append(blob)
        if (len(touches) <= HAND_EDGES_MAX
                and HAND_SPAN[0] <= span_frac <= HAND_SPAN[1]
                and HAND_DEPTH[0] <= depth <= HAND_DEPTH[1]
                and HAND_AREA[0] <= area_frac <= HAND_AREA[1]
                and HAND_SOLIDITY[0] <= solidity <= HAND_SOLIDITY[1]):
            qualifying.append(blob)

    flagged = len(qualifying) > 0
    confidence = max((b['area_frac'] for b in qualifying), default=0.0)
    confidence = float(min(1.0, confidence / 0.10))  # saturate around a "big thumb" blob
    return flagged, confidence, (qualifying or all_blobs[:3])


# --------------------------------------------------------------------------------
# component (c): comparison-shot seam
# --------------------------------------------------------------------------------

def seam_signals(a):
    h, w = a.shape[:2]
    if cv2 is not None:
        gray = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32)
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    else:  # pragma: no cover
        gray = np.asarray(Image.fromarray(a).convert('L'), dtype=np.float32)
        gx = np.zeros_like(gray)
        gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    col_energy = np.mean(np.abs(gx), axis=0)
    m = max(1, int(0.05 * w))
    inner = col_energy[m:w - m]
    if inner.size == 0:
        return False, 0.0, {}
    med = float(np.median(inner))
    peak_idx = int(np.argmax(inner))
    peak_val = float(inner[peak_idx])
    peak_ratio = peak_val / (med + 1e-6)
    peak_col_frac = (peak_idx + m) / w
    col = np.abs(gx[:, peak_idx + m])
    thresh = np.percentile(col, 60)
    tall_frac = float(np.mean(col > thresh * 1.5))
    sig = {'peak_ratio': round(peak_ratio, 2), 'peak_col_frac': round(float(peak_col_frac), 3),
           'tall_frac': round(tall_frac, 3)}
    flagged = (peak_ratio >= SEAM_PEAK_RATIO_MIN
               and SEAM_COL_FRAC[0] <= peak_col_frac <= SEAM_COL_FRAC[1]
               and tall_frac >= SEAM_TALL_FRAC_MIN)
    confidence = float(min(1.0, max(0.0, (peak_ratio - SEAM_PEAK_RATIO_MIN) / 3.0))) if flagged else 0.0
    return flagged, confidence, sig


# --------------------------------------------------------------------------------
# component (d): full-bleed coverage + sharpness
# --------------------------------------------------------------------------------

def edge_sharpness(a):
    """Mean |Laplacian| / mean gradient-magnitude, restricted to the frame's own
    strongest-gradient pixels. See tunables block for why this (not raw Laplacian
    variance) is used. Returns (edge_sharp, n_edge_pixels)."""
    gray_u8 = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY) if cv2 is not None else \
        np.asarray(Image.fromarray(a).convert('L'), dtype=np.uint8)  # pragma: no cover
    gray_f = gray_u8.astype(np.float32)
    if cv2 is not None:
        lap = cv2.Laplacian(gray_u8, cv2.CV_64F, ksize=3)
        gx = cv2.Sobel(gray_f, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray_f, cv2.CV_32F, 0, 1, ksize=3)
    else:  # pragma: no cover -- pure-numpy fallback
        lap = (-4 * gray_f + np.roll(gray_f, 1, 0) + np.roll(gray_f, -1, 0)
               + np.roll(gray_f, 1, 1) + np.roll(gray_f, -1, 1))
        gx = np.roll(gray_f, -1, 1) - np.roll(gray_f, 1, 1)
        gy = np.roll(gray_f, -1, 0) - np.roll(gray_f, 1, 0)
    grad_mag = np.sqrt(gx ** 2 + gy ** 2)
    thresh = max(float(np.percentile(grad_mag, EDGE_SHARP_PERCENTILE)), 2.0)
    mask = grad_mag > thresh
    if mask.sum() < 20:
        return 0.0, int(mask.sum())  # near-featureless frame -- treat as unsharp/uninformative
    edge_sharp = float(np.abs(lap[mask]).mean() / (grad_mag[mask].mean() + 1e-6))
    return edge_sharp, int(mask.sum())


def coverage_signals(a, af_sig):
    fg_frac = af_sig['fg_frac']
    biggest = af_sig['biggest_blob_frac']
    edge_sharp, n_edge_px = edge_sharpness(a)
    sharp_sat = (edge_sharp - EDGE_SHARP_LO) / (EDGE_SHARP_HI - EDGE_SHARP_LO)
    sharp_sat = float(np.clip(sharp_sat, 0.0, 1.0))
    pale_sheet = False
    gray_std = None
    if fg_frac <= PALE_SHEET_FG_MAX:
        gray = np.asarray(Image.fromarray(a).convert('L'), dtype=np.float32)
        gray_std = float(gray.std())
        if gray_std >= PALE_SHEET_STD_MIN:
            pale_sheet = True
    if pale_sheet:
        score = PALE_SHEET_CREDIT * (0.3 + 0.7 * sharp_sat)
        continuity = 1.0
    else:
        continuity = biggest / max(fg_frac, 1e-6)
        score = float(np.clip(fg_frac, 0.0, 1.0)) * (0.35 + 0.65 * float(np.clip(continuity, 0, 1))) \
            * (0.15 + 0.85 * sharp_sat)
    return score, {'fg_frac': fg_frac, 'continuity': round(float(continuity), 3),
                    'edge_sharp': round(edge_sharp, 4), 'n_edge_px': n_edge_px, 'sharp_sat': round(sharp_sat, 3),
                    'pale_sheet_credit': pale_sheet, 'gray_std': round(gray_std, 2) if gray_std is not None else None}


# --------------------------------------------------------------------------------
# component (a): audit_flagger reuse
# --------------------------------------------------------------------------------

def audit_score(path):
    """Per-IMAGE audit score. Deliberately does NOT fold in 019's `flag_name`
    (Bullseye reactive/alchemy/composite name blocklist) -- that blocklist is a
    per-PRODUCT-LINE signal (same verdict for every image of the product), so
    folding it in here would zero out every candidate identically and destroy
    this module's whole job of differentiating BETWEEN a product's own images.
    Report 024 SS7 hit exactly this: "the name-based reaction_demo_line/
    composite_streamer_line codes describe the product line, not the specific
    photo, and would reject every image of a target product identically if used
    as a per-image filter." See `line_flags()` / `pick()` for how the name
    blocklist is used instead (a uniform floor penalty, not a ranking signal)."""
    try:
        sig = af.analyze_image(path)
    except Exception as e:
        return 0.0, {'error': str(e)}, {'fg_frac': 0.0, 'biggest_blob_frac': 0.0}
    reasons = af.flag_signals(sig)
    if 'test_fire_tiles' in reasons:
        score = 0.0
    elif 'product_on_white' in reasons:
        score = 0.35  # weak/advisory per 019 -- could be a legit front-lit sheet
    else:
        score = 1.0
    return score, {'reasons': reasons, 'signals': sig}, sig


def line_flags(name, manufacturer):
    """Per-PRODUCT-LINE reasons (019's name blocklist) -- see `audit_score` docstring
    for why these are kept separate from the per-image score."""
    if name is None and manufacturer is None:
        return []
    return af.flag_name(name, manufacturer)


# --------------------------------------------------------------------------------
# component (e): text hints
# --------------------------------------------------------------------------------
_ORDINAL_WORDS = {
    'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
    'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
}
_ORDINAL_RE = re.compile(
    r'\b(' + '|'.join(_ORDINAL_WORDS) + r'|\d+(?:st|nd|rd|th))\b', re.IGNORECASE)
_OVERRIDE_RE = re.compile(
    r'\b(right|correct|winning)\s+(picture|photo|image)\s+is\s+the\s+'
    r'(' + '|'.join(_ORDINAL_WORDS) + r'|\d+(?:st|nd|rd|th))\b', re.IGNORECASE)

_CUSTOMER_KW = ('customer',)
_COMPARISON_KW = ('next to', 'compare', 'compared', 'comparison', 'versus', ' vs ', ' vs.', 'beside', 'side by side', 'side-by-side')
_BACKLIT_KW = ('backlit', 'back-lit', 'back lit')

CUSTOMER_PENALTY = -0.9
COMPARISON_PENALTY = -0.8
BACKLIT_BONUS = 0.5


def _ordinal_to_int(tok):
    tok = tok.lower()
    if tok in _ORDINAL_WORDS:
        return _ORDINAL_WORDS[tok]
    m = re.match(r'(\d+)', tok)
    return int(m.group(1)) if m else None


_TAG_RE = re.compile(r'<[^>]+>')


def strip_html(text):
    """Callers commonly pass raw Shopify `body_html` straight through -- strip
    tags and unescape entities so sentence splitting / keyword matching sees
    plain prose. `<p>`/`<br>` become sentence-ish breaks (a period) so ordinals
    in one HTML block don't bleed into the next block's keywords."""
    text = re.sub(r'</p>|<br\s*/?>', '. ', text, flags=re.IGNORECASE)
    text = _TAG_RE.sub(' ', text)
    return html.unescape(text)


def _split_sentences(text):
    return re.split(r'(?<=[.!?])\s+', text)


def text_signals(text, n_candidates):
    """Return (adjustments: dict[1-indexed pos -> float], override_pos: int|None, notes: list)."""
    adj = {i: 0.0 for i in range(1, n_candidates + 1)}
    notes = []
    override_pos = None
    if not text:
        return adj, override_pos, notes
    text = strip_html(text)

    m = _OVERRIDE_RE.search(text)
    if m:
        pos = _ordinal_to_int(m.group(3))
        if pos is not None and 1 <= pos <= n_candidates:
            override_pos = pos
            notes.append(f'explicit override: "{m.group(0)}" -> position {pos}')

    for sent in _split_sentences(text):
        low = sent.lower()
        toks = [_ordinal_to_int(t) for t in _ORDINAL_RE.findall(sent)]
        toks = [t for t in toks if t and 1 <= t <= n_candidates]
        if not toks:
            continue
        if any(kw in low for kw in _CUSTOMER_KW):
            for t in toks:
                adj[t] += CUSTOMER_PENALTY
                notes.append(f'position {t}: customer photo ("{sent.strip()}")')
        if any(kw in low for kw in _COMPARISON_KW):
            for t in toks:
                adj[t] += COMPARISON_PENALTY
                notes.append(f'position {t}: comparison mentioned ("{sent.strip()}")')
        if any(kw in low for kw in _BACKLIT_KW):
            for t in toks:
                adj[t] += BACKLIT_BONUS
                notes.append(f'position {t}: backlit ("{sent.strip()}")')
    return adj, override_pos, notes


# --------------------------------------------------------------------------------
# per-image scoring + pick
# --------------------------------------------------------------------------------

def score_image(path):
    """Score one candidate image. Returns a dict with 'components' (each in [0,1])
    and 'reasons' (human-readable detail per component). Does not know the
    product's name/manufacturer -- see `line_flags()` for that (product-level,
    applied once in `pick()`, not per image)."""
    a = _load(path)
    a_score, a_detail, af_sig = audit_score(path)
    hand_flag, hand_conf, hand_blobs = hand_signals(a)
    seam_flag, seam_conf, seam_detail = seam_signals(a)
    cov_score, cov_detail = coverage_signals(a, af_sig)

    hand_score = 1.0 - hand_conf if hand_flag else 1.0
    seam_score = 1.0 - seam_conf if seam_flag else 1.0

    components = {'audit': a_score, 'hand': hand_score, 'seam': seam_score, 'coverage': cov_score}
    base = sum(WEIGHTS[k] * v for k, v in components.items())
    reasons = {
        'audit': a_detail,
        'hand': {'flagged': hand_flag, 'confidence': round(hand_conf, 3), 'blobs': hand_blobs},
        'seam': {'flagged': seam_flag, 'confidence': round(seam_conf, 3), **seam_detail},
        'coverage': cov_detail,
    }
    return {'components': components, 'base_score': round(float(base), 4), 'reasons': reasons}


def pick(candidates, text=None, name=None, manufacturer=None, floor=FLOOR):
    """Score every candidate image and return the argmax (or None).

    candidates: list of local file paths (fetch URLs to local files first -- this
                function does no network I/O by design, see fetch_gallery.py).
    text:       product description/title text for hint parsing (component e).
    name/manufacturer: the report-019 name blocklist (`flag_name`) is evaluated
                ONCE for the product (not per image, see `audit_score` docstring)
                and applied as a uniform floor penalty -- it flags product LINES
                whose photography is systematically suspect (Bullseye reactive/
                alchemy/composite), which should raise the bar for trusting even
                that line's best-looking image, but must not zero out every
                candidate identically (that would make it useless for picking
                between them).
    floor:      minimum final score to be eligible for the pick.

    Returns {'pick': int|None (0-indexed into candidates), 'scores': [...],
             'override': bool, 'text_notes': [...], 'line_flags': [...]}.
    """
    n = len(candidates)
    if n == 0:
        return {'pick': None, 'scores': [], 'override': False, 'text_notes': [], 'line_flags': []}

    per_image = [score_image(c) for c in candidates]
    text_adj, override_pos, text_notes = text_signals(text or '', n)
    line_reasons = line_flags(name, manufacturer)
    line_penalty = LINE_PENALTY if line_reasons else 0.0

    scores = []
    for i, si in enumerate(per_image):
        pos = i + 1
        # Only floor-clip here -- do NOT ceiling-clip to 1.0: a text bonus (e.g.
        # "backlit") can legitimately push two already-strong candidates past 1.0,
        # and clipping both to the same ceiling would destroy the ranking between
        # them (this was caught by the steel-gray-opal validation case, where a
        # sharp full-sheet photo and a blurry-but-backlit crop tied at 1.0 after
        # clipping until this was fixed -- see reports/035-swatch-picker.md).
        final = max(0.0, si['base_score'] + text_adj.get(pos, 0.0) - line_penalty)
        scores.append({'index': i, 'position': pos, 'final_score': round(final, 4),
                        'base_score': si['base_score'], 'text_adjustment': round(text_adj.get(pos, 0.0), 3),
                        'line_penalty': line_penalty,
                        'components': si['components'], 'reasons': si['reasons']})

    if override_pos is not None:
        return {'pick': override_pos - 1, 'scores': scores, 'override': True, 'text_notes': text_notes,
                'line_flags': line_reasons}

    best = max(scores, key=lambda s: s['final_score'])
    pick_idx = best['index'] if best['final_score'] >= floor else None
    return {'pick': pick_idx, 'scores': scores, 'override': False, 'text_notes': text_notes,
            'line_flags': line_reasons}


# --------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('images', nargs='+', help='candidate image paths, in gallery order')
    ap.add_argument('--text', default=None, help='product description/title text (hint parsing)')
    ap.add_argument('--name', default=None)
    ap.add_argument('--manufacturer', default=None)
    ap.add_argument('--floor', type=float, default=FLOOR)
    ap.add_argument('--json', action='store_true', help='print full JSON instead of a table')
    args = ap.parse_args()

    result = pick(args.images, text=args.text, name=args.name, manufacturer=args.manufacturer,
                  floor=args.floor)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return

    print(f"{'pos':>3}  {'final':>6}  {'audit':>6}  {'hand':>6}  {'seam':>6}  {'cover':>6}  file")
    for s in result['scores']:
        c = s['components']
        print(f"{s['position']:>3}  {s['final_score']:>6.3f}  {c['audit']:>6.3f}  {c['hand']:>6.3f}  "
              f"{c['seam']:>6.3f}  {c['coverage']:>6.3f}  {args.images[s['index']]}")
    if result['override']:
        print(f"\nTEXT OVERRIDE fired -> pick = position {result['pick'] + 1}")
        for n in result['text_notes']:
            print(f'  - {n}')
    elif result['pick'] is None:
        print(f"\nNO PICK -- nothing cleared the floor ({args.floor})")
    else:
        print(f"\nPICK = position {result['pick'] + 1} ({args.images[result['pick']]})")
    if result['text_notes'] and not result['override']:
        print('text notes:')
        for n in result['text_notes']:
            print(f'  - {n}')


if __name__ == '__main__':
    main()
