"""swatch_picker.py -- scored swatch-picker: replaces positional image-pick heuristics.

VENDORED COPY -- provenance: research/delighting branch `research/delighting-035`,
commit 111e0d178a06e2b4c423402fa8826aedc7623a1e, path
`research/delighting/corpus/swatch_picker.py`, unmodified except for this header.
Vendored (iteration 036) so `feat/library-picker-rebuild` has no path dependency on the
research worktree. To pick up upstream fixes, re-copy from that commit (or later) on the
research/delighting trunk and diff against this file; do not hand-edit divergently.
Sibling dependency `audit_flagger.py` (report 019) is vendored alongside it in this same
directory, same convention.

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
# component (f): Bullseye grip-photo detector / flat-chip demotion
# --------------------------------------------------------------------------------
# LOCAL ADDITION -- branch fix/bullseye-grip-picks, not yet upstreamed to
# research/delighting (flag for re-sync at the next vendor refresh; see the module
# header's "do not hand-edit divergently" note -- this is a clearly-delineated new
# component, not a divergent edit of (a)-(e)).
#
# Diagnosis (10-product sample, see the task's report): Bullseye's own product
# photography mixes two very different shots for the "standard" Fusible sheet --
# (1) a tight full-bleed macro crop of the glass surface with NO background at all
# (reads to components (a)/(d) above as if it were a perfect edge-to-edge backlit
# sheet photo -- audit=1.0, coverage=1.0 -- even though it shows none of the sheet's
# actual silhouette/edges) and, where the vendor shot it, (2) a whole-sheet-on-white
# studio photo, sometimes with the sheet held in binder-clip grips (dark hardware on
# the right edge) plus a small warm/red product label and a sharpie-written batch
# number -- the far more representative "real sheet, real texture" photo. Because
# audit_flagger flags (2) as weak/advisory `product_on_white` (audit component drops
# to 0.35) or, even unflagged, (2)'s white studio border caps `fg_frac` well under
# 1.0 for the coverage component, the macro crop (1) was winning almost every time a
# real sheet-on-white candidate existed alongside it -- confirmed on Red Opalescent
# (both variants) and Spring Green Opalescent Double-rolled, where a genuine grip
# photo lost to the macro crop by a 0.04-0.28 base-score margin. (Mineral Green,
# Periwinkle, Mink and Artichoke Opalescent, also named in the original complaint,
# turned out on inspection to have NO grip/whole-sheet photo in their live galleries
# at all -- see the task report; this component is a no-op for those, by design,
# since `any_whole_sheet` never fires.)
#
# This is a signed, RELATIVE, Bullseye-only adjustment (same shape as component (e)'s
# text_adj) -- it never fires against a product's own images unless one of its
# sibling candidates is itself judged a whole-sheet-on-white photo, so a product with
# no real sheet-on-white photo at all is left untouched (its macro crop is still the
# best available image, and the floor/existing components still govern it).
#
# `bullseye_features()` returns NAMED, independently-interpretable signals (not a
# single opaque scalar) -- flat_chip_flag / grip_flag / grip_confidence / crop
# geometry -- so a downstream judge (a VLM re-ranker is being piloted separately,
# landing in its own file) can use them as priors/tiebreakers without re-deriving
# pixel signals itself.
_BE_WHITE_MIN = 0.80        # per-pixel near-white test (min channel) -- looser than
                             # 019's 228/255=0.894, since studio backdrops in this
                             # corpus run slightly warm/grey, not paper-white
_BE_WHITE_SAT_MAX = 0.12
_BE_DARK_VAL_MAX = 0.35     # clamp hardware: near-black
_BE_DARK_SAT_MAX = 0.35
BULLSEYE_GRIP_BONUS = 0.35        # pushes a confidently-detected grip photo (clamp
                                   # hardware visible) above a same-product flat-chip
                                   # macro crop -- calibrated to comfortably clear the
                                   # observed 0.04-0.28 base-score gaps
BULLSEYE_WHOLE_SHEET_BONUS = 0.15  # smaller bonus for a whole-sheet-on-white photo
                                    # without confirmed clamp hardware -- still a real
                                    # sheet photo, less certain than a grip
BULLSEYE_FLAT_CHIP_PENALTY = 0.30  # demotes a full-bleed macro crop, but ONLY when a
                                    # sibling candidate is itself whole-sheet/grip --
                                    # never applied in absolute terms


def _bullseye_sheet_signals(a):
    """Cheap numpy/PIL(+cv2)-only pixel signals for one Bullseye candidate. No ML."""
    h, w = a.shape[:2]
    af = a.astype(np.float32) / 255.0
    mx = af.max(-1); mn = af.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    val = mx
    white = (mn >= _BE_WHITE_MIN) & (sat <= _BE_WHITE_SAT_MAX)
    white_frac = float(white.mean())
    frame = h * w

    def _components(mask_bool):
        if cv2 is not None:
            u8 = (mask_bool.astype(np.uint8)) * 255
            u8 = cv2.morphologyEx(u8, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            n, lblimg = cv2.connectedComponents((u8 > 0).astype(np.uint8), connectivity=8)
            return [(lblimg == i) for i in range(1, n)]
        from scipy import ndimage  # pragma: no cover -- cv2 fallback
        lblimg, n = ndimage.label(mask_bool)
        return [(lblimg == i) for i in range(1, n + 1)]

    fg_comps = _components(~white)
    biggest_frac = 0.0
    sheet_bbox = (0.0, 0.0, 1.0, 1.0)
    if fg_comps:
        sizes = [int(c.sum()) for c in fg_comps]
        bi = int(np.argmax(sizes))
        biggest_frac = float(sizes[bi] / frame)
        ys, xs = np.where(fg_comps[bi])
        if len(xs):
            sheet_bbox = (float(xs.min() / w), float(ys.min() / h),
                          float((xs.max() + 1) / w), float((ys.max() + 1) / h))

    # dark clamp hardware: compact blobs touching the extreme right edge, not
    # spanning more than ~35% of the width (excludes a genuinely near-black sheet
    # color, which would span the whole frame edge-to-edge).
    dark = (val < _BE_DARK_VAL_MAX) & (sat < _BE_DARK_SAT_MAX)
    dark_comps = _components(dark)
    clamp_blobs = 0
    clamp_left = 1.0
    for c in dark_comps:
        frac = float(c.sum()) / frame
        if frac < 0.0015:
            continue
        ys, xs = np.where(c)
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        if x1 >= w - 2 and (x1 - x0) < 0.35 * w:
            clamp_blobs += 1
            clamp_left = min(clamp_left, x0 / w)

    return {
        'white_frac': round(white_frac, 4), 'biggest_frac': round(biggest_frac, 4),
        'clamp_blobs': clamp_blobs,
        'clamp_left_frac': round(clamp_left, 3) if clamp_blobs else None,
        'sheet_bbox_frac': tuple(round(v, 4) for v in sheet_bbox),
    }


# -- post-crop border scrub (lead review of the first board: most crops kept a thin
#    near-white sliver along the BOTTOM edge -- the sheet bbox's last rows are the
#    sheet's glossy cut edge + studio ground under it -- and a few kept a small white
#    corner wedge from slight sheet rotation) --
_SCRUB_WHITE_FRAC_MAX = 0.04   # a row/col is "contaminated" when >4% of it is near-white
_SCRUB_WINDOW_FRAC = 0.15      # how deep (as a fraction of the crop's own dimension) the scrub
                               # scans in from each edge for contaminated rows/cols. The bottom of
                               # these product photos is sheet color -> bright specular reflection
                               # band -> a DARK cut-edge line -> background, and both the band's
                               # depth and the dark line's thickness vary per photo (17px..38px at
                               # 1200px observed across the review boards) -- a shallow fixed band
                               # missed the deeper ones (second board review), so scan a generous
                               # window and cut past the DEEPEST contaminated row instead.
_SCRUB_SAFETY_INSET_FRAC = 0.003  # extra inset removed from ALL four sides after the scrub, as
                                   # a fraction of the frame's short side (min 1px => ~4px at
                                   # 1200px full res); sheets are hand-cut and slightly rotated,
                                   # so err toward cutting a sliver of sheet over keeping any
                                   # background
_SCRUB_VERIFY_BAND_FRAC = 0.02  # final self-verification band: after cutting + inset, no row/col
                                # within this band of any edge may still be contaminated -- if one
                                # is (e.g. white glass streaks running past the scan window), the
                                # scrub FAILS rather than ships a dirty crop
_SCRUB_MAX_AREA_LOSS = 0.20    # if scrubbing eats >20% of the crop area, the crop is not
                               # trustworthy -- fail it (caller keeps the shipped pick and
                               # lists the product as uncertain instead)


def _scrub_crop_box(a, crop_box_frac):
    """Border scrub: within a scan window from each edge of the crop, find every
    near-white-contaminated row/col and cut the edge past the deepest one; then
    apply a safety inset; then SELF-VERIFY that the final crop's border bands are
    clean.

    Returns (scrubbed_crop_box_frac | None, detail_dict). None = untrustworthy --
    either the scrub removed more than _SCRUB_MAX_AREA_LOSS of the area, or
    contamination survives the cut (background/white streaks deeper than a
    rectangle crop can excise); the caller treats the product as uncertain and
    keeps the currently-shipped pick. Run this on the FULL-RESOLUTION pixels: at
    320px thumb scale JPEG downsampling blends thin white slivers into the sheet
    color below the white threshold (second-board finding)."""
    h, w = a.shape[:2]
    af = a.astype(np.float32) / 255.0
    mx = af.max(-1); mn = af.min(-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    white = (mn >= _BE_WHITE_MIN) & (sat <= _BE_WHITE_SAT_MAX)

    x0 = int(crop_box_frac[0] * w); y0 = int(crop_box_frac[1] * h)
    x1 = int(crop_box_frac[2] * w); y1 = int(crop_box_frac[3] * h)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    orig_area = max(1, (x1 - x0) * (y1 - y0))
    inset = max(1, int(round(_SCRUB_SAFETY_INSET_FRAC * min(h, w))))
    trimmed = {'top': 0, 'bottom': 0, 'left': 0, 'right': 0}

    def _fail(reason, area):
        return None, {'trimmed_px': trimmed, 'area_kept': round(max(0, area) / orig_area, 3),
                      'failed': reason}

    if x1 - x0 < 4 or y1 - y0 < 4:
        return _fail('degenerate_box', 0)

    # cut top/bottom past the deepest contaminated row within its scan window
    row_bad = white[:, x0:x1].mean(axis=1) > _SCRUB_WHITE_FRAC_MAX   # indexed by absolute y
    win_y = max(4, int(round(_SCRUB_WINDOW_FRAC * (y1 - y0))))
    win_x = max(4, int(round(_SCRUB_WINDOW_FRAC * (x1 - x0))))

    top_bad = np.where(row_bad[y0:min(y0 + win_y, y1)])[0]
    if top_bad.size:
        trimmed['top'] = int(top_bad.max()) + 1
        y0 += trimmed['top']
    bot_bad = np.where(row_bad[max(y1 - win_y, y0):y1])[0]
    if bot_bad.size:
        trimmed['bottom'] = (y1 - max(y1 - win_y, y0)) - int(bot_bad.min())
        y1 -= trimmed['bottom']

    # cut left/right past the deepest contaminated col within its scan window --
    # LOCAL FIX (fix/bullseye-grip-sweep): recomputed AFTER the top/bottom cut
    # above, using the row-trimmed y0/y1, not the original. A contamination band
    # that spans nearly the full frame WIDTH but is confined to a narrow row
    # range near the top/bottom (the common case: a bright specular reflection
    # strip along the sheet's own cut edge, already documented in this
    # function's tunables block) was previously measured against the PRE-trim
    # row range, so the very rows the top/bottom cut above was about to remove
    # inflated col_bad for EVERY column and forced a false, symmetric left+right
    # trim on top of the already-correct top/bottom cut. Confirmed on 4 grip
    # photos during the fix/bullseye-grip-sweep task (Butterscotch, Marigold
    # Yellow, Plum Striker, Gold Purple Opalescent) -- all hard-rejected on
    # area_loss purely from this double-count; recomputing col_bad on the
    # post-row-trim range found zero genuine left/right contamination in any of
    # them. Safe change: the final self-verification band below still catches
    # any left/right contamination this misses, regardless of ordering -- this
    # only removes a false positive, never bypasses the safety net. Needs the
    # same upstream re-sync as component (f); see module header.
    col_bad = white[y0:y1, :].mean(axis=0) > _SCRUB_WHITE_FRAC_MAX   # indexed by absolute x
    left_bad = np.where(col_bad[x0:min(x0 + win_x, x1)])[0]
    if left_bad.size:
        trimmed['left'] = int(left_bad.max()) + 1
        x0 += trimmed['left']
    right_bad = np.where(col_bad[max(x1 - win_x, x0):x1])[0]
    if right_bad.size:
        trimmed['right'] = (x1 - max(x1 - win_x, x0)) - int(right_bad.min())
        x1 -= trimmed['right']

    x0 += inset; y0 += inset
    x1 -= inset; y1 -= inset
    area = (x1 - x0) * (y1 - y0)
    if x1 - x0 < 4 or y1 - y0 < 4 or area <= (1.0 - _SCRUB_MAX_AREA_LOSS) * orig_area:
        return _fail('area_loss', area)

    # self-verify: the final crop's border bands must be clean (recompute the
    # row/col profiles on the FINAL box, since the cuts changed both extents)
    vb_y = max(2, int(round(_SCRUB_VERIFY_BAND_FRAC * (y1 - y0))))
    vb_x = max(2, int(round(_SCRUB_VERIFY_BAND_FRAC * (x1 - x0))))
    rows = white[:, x0:x1].mean(axis=1)
    cols = white[y0:y1, :].mean(axis=0)
    if (rows[y0:y0 + vb_y].max() > _SCRUB_WHITE_FRAC_MAX
            or rows[y1 - vb_y:y1].max() > _SCRUB_WHITE_FRAC_MAX
            or cols[x0:x0 + vb_x].max() > _SCRUB_WHITE_FRAC_MAX
            or cols[x1 - vb_x:x1].max() > _SCRUB_WHITE_FRAC_MAX):
        return _fail('verify_contaminated', area)

    scrubbed = (round(x0 / w, 4), round(y0 / h, 4), round(x1 / w, 4), round(y1 / h, 4))
    return scrubbed, {'trimmed_px': trimmed, 'area_kept': round(area / orig_area, 3), 'failed': None}


def bullseye_features(path):
    """Public per-candidate feature dict for a Bullseye photo. Named, independently-
    interpretable signals -- see component-(f) docstring above for why (VLM judge
    priors/tiebreakers), not just a single scalar.

    Returns: {'is_full_bleed', 'is_whole_sheet_on_white', 'grip_flag',
              'grip_confidence', 'flat_chip_flag', 'crop_box_frac' (x0,y0,x1,y1 as
              fractions of the source image, or None -- None for a whole-sheet photo
              means the border scrub FAILED and the crop cannot be trusted, see
              'crop_scrub'), plus the raw pixel signals}.
    """
    a = _load(path)
    sig = _bullseye_sheet_signals(a)
    is_full_bleed = sig['white_frac'] <= 0.01 and sig['biggest_frac'] >= 0.97
    is_whole_sheet = (not is_full_bleed) and (0.45 <= sig['biggest_frac'] <= 0.95) and sig['white_frac'] >= 0.08
    grip_flag = bool(is_whole_sheet and sig['clamp_blobs'] >= 1)
    grip_confidence = round(min(1.0, sig['clamp_blobs'] / 2.0), 3) if grip_flag else 0.0

    crop_box_frac = None
    crop_scrub = None
    if is_whole_sheet:
        x0, y0, x1, y1 = sig['sheet_bbox_frac']
        # right cut: whichever is tightest of (a) detected clamp hardware and (b) a
        # fixed conservative 80%-of-sheet-width ratio -- the fixed ratio is the
        # primary defense against the label (small warm/red card) when the label's
        # own color is too close to the glass's own hue to separate by color alone
        # (observed on Red/Orange Opalescent during calibration -- a color-distance
        # label detector left a visible label sliver on those two specific hues).
        fixed_cut = x0 + 0.80 * (x1 - x0)
        cut = fixed_cut if sig['clamp_left_frac'] is None else min(fixed_cut, sig['clamp_left_frac'])
        crop_right = max(x0 + 0.30 * (x1 - x0), cut - 0.02)
        # top inset: best-effort sharpie-strip removal -- calibration sample showed
        # the batch number written within roughly the top 12% of the sheet's own
        # bbox (either corner); conservative inset per the task brief ("a slightly
        # smaller clean crop beats a full sheet with hardware").
        crop_top = y0 + 0.12 * (y1 - y0)
        # border scrub (first-board review finding): the sheet bbox's outer rows/
        # cols still contain studio ground -- a bottom-edge sliver especially --
        # so shrink any contaminated edge and apply a safety inset. A failed scrub
        # (background intrusion too deep) yields crop_box_frac=None, which the
        # churn gate treats as "uncertain -> keep the shipped pick".
        candidate_box = (x0, crop_top, crop_right, y1)
        crop_box_frac, crop_scrub = _scrub_crop_box(a, candidate_box)

    return {
        'is_full_bleed': is_full_bleed, 'is_whole_sheet_on_white': is_whole_sheet,
        'grip_flag': grip_flag, 'grip_confidence': grip_confidence,
        'flat_chip_flag': is_full_bleed, 'crop_box_frac': crop_box_frac,
        'crop_scrub': crop_scrub,
        **sig,
    }


def bullseye_photo_prior(candidates):
    """Signed per-position adjustment (same shape as component (e)'s text_adj) plus
    the raw feature dict per candidate (for logging/audit and the VLM judge pilot).
    Only meaningful for Bullseye -- callers gate this on manufacturer, see `pick()`."""
    feats = {}
    for i, c in enumerate(candidates):
        try:
            feats[i + 1] = bullseye_features(c)
        except Exception as e:
            feats[i + 1] = {'error': str(e), 'is_full_bleed': False,
                             'is_whole_sheet_on_white': False, 'grip_flag': False}
    any_whole_sheet = any(f.get('is_whole_sheet_on_white') for f in feats.values())
    adj = {}
    for pos, f in feats.items():
        a = 0.0
        if f.get('grip_flag'):
            a += BULLSEYE_GRIP_BONUS
        elif f.get('is_whole_sheet_on_white'):
            a += BULLSEYE_WHOLE_SHEET_BONUS
        if f.get('is_full_bleed') and any_whole_sheet:
            a -= BULLSEYE_FLAT_CHIP_PENALTY
        adj[pos] = a
    return adj, feats


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
             'override': bool, 'text_notes': [...], 'line_flags': [...],
             'bullseye_features': {pos: feature-dict} (empty unless manufacturer is
             Bullseye -- component (f), see its docstring)}.
    """
    n = len(candidates)
    if n == 0:
        return {'pick': None, 'scores': [], 'override': False, 'text_notes': [], 'line_flags': [],
                'bullseye_features': {}}

    per_image = [score_image(c) for c in candidates]
    text_adj, override_pos, text_notes = text_signals(text or '', n)
    line_reasons = line_flags(name, manufacturer)
    line_penalty = LINE_PENALTY if line_reasons else 0.0

    # component (f): Bullseye grip-photo prior -- see its docstring above. No-op
    # (empty dicts) for every other manufacturer.
    bullseye_adj, bullseye_feats = {}, {}
    if (manufacturer or '').strip().lower() == 'bullseye':
        bullseye_adj, bullseye_feats = bullseye_photo_prior(candidates)

    scores = []
    for i, si in enumerate(per_image):
        pos = i + 1
        # Only floor-clip here -- do NOT ceiling-clip to 1.0: a text bonus (e.g.
        # "backlit") can legitimately push two already-strong candidates past 1.0,
        # and clipping both to the same ceiling would destroy the ranking between
        # them (this was caught by the steel-gray-opal validation case, where a
        # sharp full-sheet photo and a blurry-but-backlit crop tied at 1.0 after
        # clipping until this was fixed -- see reports/035-swatch-picker.md).
        final = max(0.0, si['base_score'] + text_adj.get(pos, 0.0) + bullseye_adj.get(pos, 0.0) - line_penalty)
        scores.append({'index': i, 'position': pos, 'final_score': round(final, 4),
                        'base_score': si['base_score'], 'text_adjustment': round(text_adj.get(pos, 0.0), 3),
                        'line_penalty': line_penalty, 'bullseye_adjustment': round(bullseye_adj.get(pos, 0.0), 3),
                        'components': si['components'], 'reasons': si['reasons']})

    if override_pos is not None:
        return {'pick': override_pos - 1, 'scores': scores, 'override': True, 'text_notes': text_notes,
                'line_flags': line_reasons, 'bullseye_features': bullseye_feats}

    best = max(scores, key=lambda s: s['final_score'])
    pick_idx = best['index'] if best['final_score'] >= floor else None
    return {'pick': pick_idx, 'scores': scores, 'override': False, 'text_notes': text_notes,
            'line_flags': line_reasons, 'bullseye_features': bullseye_feats}


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
