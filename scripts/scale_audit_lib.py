"""Core detectors for the Bullseye texture-scale audit.
Pure functions over gallery image paths; no repo side-effects.
"""
import cv2, numpy as np, os
from PIL import Image

# Measured median aspect of the fixed whole-sheet studio sample (w/h). See
# scripts/scale_audit.py header for the calibration rationale.
SAMPLE_ASPECT = 1.326

# ------------------------------------------------------------------ loaders
# Load through PIL (correctly handles CMYK / ICC / EXIF Shopify JPEGs that
# cv2.imread can silently misread).
def load_bgr(path):
    rgb = np.array(Image.open(path).convert('RGB'))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

def load_gray(path):
    return np.array(Image.open(path).convert('L'))

# ------------------------------------------------------------------ sheet box
def _canny_box(gray):
    g = cv2.GaussianBlur(gray, (5, 5), 0)
    ed = cv2.Canny(g, 30, 90)
    ed = cv2.dilate(ed, np.ones((7, 7), np.uint8), 2)
    ed = cv2.morphologyEx(ed, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    cnts, _ = cv2.findContours(ed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape
    best = None
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < w * 0.3 or bh < h * 0.3:
            continue
        area = cv2.contourArea(c)
        if area < 0.15 * w * h:
            continue
        touch = sum([x <= 3, y <= 3, x + bw >= w - 3, y + bh >= h - 3])
        fill = area / (bw * bh)
        score = area * (1 - 0.15 * touch) * (fill ** 0.5)
        if best is None or score > best[0]:
            best = (score, x, y, bw, bh, touch, fill)
    return best

def _bright_box(gray):
    """Fallback for light glass on black/white split bg: threshold non-extreme."""
    h, w = gray.shape
    # background is pure black OR pure white AND flat; glass is intermediate or textured
    m = ((gray > 18) & (gray < 238)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((11, 11), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < w * 0.3 or bh < h * 0.3:
            continue
        area = cv2.contourArea(c)
        touch = sum([x <= 3, y <= 3, x + bw >= w - 3, y + bh >= h - 3])
        fill = area / (bw * bh)
        score = area * (1 - 0.15 * touch) * (fill ** 0.5)
        if best is None or score > best[0]:
            best = (score, x, y, bw, bh, touch, fill)
    return best

def _backdrop_mask(gray):
    """Flat + extreme (near-black or near-white) pixels connected to the image
    border. Texture-gating stops it leaking into dark/colored glass, which is not
    flat. Handles black, white and split backdrops uniformly."""
    h, w = gray.shape
    g = gray.astype(np.float32)
    m = cv2.blur(g, (9, 9)); sq = cv2.blur(g * g, (9, 9))
    std = np.sqrt(np.maximum(sq - m * m, 0))
    flat = std < 7.0
    extreme = (gray < 45) | (gray > 210)
    cand = (flat & extreme).astype(np.uint8)
    cand = cv2.morphologyEx(cand, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    # keep only components touching the border
    n, lab = cv2.connectedComponents(cand)
    border_ids = set(lab[0, :]).union(lab[-1, :], lab[:, 0], lab[:, -1]) - {0}
    bg = np.isin(lab, list(border_ids))
    return bg

def find_sheet_box(gray):
    bg = _backdrop_mask(gray)
    h, w = gray.shape
    sheet = (~bg).astype(np.uint8)
    sheet = cv2.morphologyEx(sheet, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    sheet = cv2.morphologyEx(sheet, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(sheet)
    if n <= 1:
        return None
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, bw, bh, area = stats[idx]
    if bw < w * 0.25 or bh < h * 0.25:
        return None
    ring = _border_ring_fraction(bg)
    sides = _side_backdrop(bg)
    # genuine Bullseye studio shots always include a pure-white backdrop region
    # (the transmission side). Dark/tan full-bleed macros cannot fake >245 flat white,
    # so this is the precision guard against calling a macro a whole-sheet.
    g = gray.astype(np.float32)
    m = cv2.blur(g, (9, 9)); sq = cv2.blur(g * g, (9, 9))
    flat = np.sqrt(np.maximum(sq - m * m, 0)) < 6.0
    pure_white = float(((gray > 245) & flat).mean())
    return dict(x=int(x), y=int(y), w=int(bw), h=int(bh),
                touch=int((x <= 3) + (y <= 3) + (x + bw >= w - 3) + (y + bh >= h - 3)),
                fill=float(area / (bw * bh)) if bw * bh else 0.0,
                aspect=float(bw / bh) if bh else 0.0,
                backdrop_ring=float(ring), n_sides=sides['n_sides'], sides=sides,
                pure_white=pure_white)

def _border_ring_fraction(bg):
    h, w = bg.shape
    t = max(4, int(0.06 * min(h, w)))
    ring = np.zeros_like(bg)
    ring[:t, :] = ring[-t:, :] = ring[:, :t] = ring[:, -t:] = True
    return bg[ring].mean() if ring.any() else 0.0

def _side_backdrop(bg):
    """Fraction of each image edge strip that is backdrop, and count of sides
    that are predominantly backdrop (a whole-sheet is framed on ~4 sides)."""
    h, w = bg.shape
    t = max(4, int(0.05 * min(h, w)))
    top, bot = bg[:t, :].mean(), bg[-t:, :].mean()
    lft, rgt = bg[:, :t].mean(), bg[:, -t:].mean()
    sides = [top, bot, lft, rgt]
    return dict(top=float(top), bot=float(bot), lft=float(lft), rgt=float(rgt),
                n_sides=int(sum(s > 0.45 for s in sides)))

# ------------------------------------------------------------ background mode
def background_analysis(bgr, box):
    """Classify the backdrop the sheet sits on, sampling only *outside* the box."""
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    outside = np.ones((h, w), bool)
    if box:
        x, y, bw, bh = box['x'], box['y'], box['w'], box['h']
        outside[max(0, y):y + bh, max(0, x):x + bw] = False
    vals = gray[outside]
    if vals.size < 200:
        # full-bleed: no visible backdrop; sample nothing
        return dict(mode='none', black_frac=0.0, white_frac=0.0, seam_x=None)
    black = float((vals < 40).mean())
    white = float((vals > 215).mean())
    if black > 0.15 and white > 0.15:
        mode = 'split'
    elif white > 0.5:
        mode = 'white'
    elif black > 0.5:
        mode = 'black'
    else:
        mode = 'mixed'
    seam_x = None
    white_side = None
    if mode == 'split':
        # find vertical column where the background transitions black<->white.
        # Use the top strip (above the sheet) which is pure backdrop.
        y0 = box['y'] if box else 0
        strip = gray[:max(8, y0 - 5), :] if (box and y0 > 12) else gray[:h // 6, :]
        colmean = strip.mean(axis=0)
        # seam = steepest gradient in column means
        if colmean.size > 20:
            grad = np.abs(np.diff(cv2.GaussianBlur(colmean.reshape(1, -1), (1, 31), 0).ravel()))
            seam_x = int(np.argmax(grad))
            if seam_x is not None:
                lmean = colmean[:seam_x].mean() if seam_x > 5 else 0
                rmean = colmean[seam_x:].mean() if seam_x < w - 5 else 0
                white_side = 'right' if rmean > lmean else 'left'
    return dict(mode=mode, black_frac=black, white_frac=white, seam_x=seam_x,
                white_side=white_side)

# --------------------------------------------------- within-sheet side luminance
def sheet_side_luma(bgr, box, seam_x):
    """Mean luminance of the sheet interior on each side of the seam (transmission
    side reads bright, reflection side reads darker for clear iridized glass)."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    x, y, bw, bh = box['x'], box['y'], box['w'], box['h']
    inner = gray[y + bh // 6: y + 5 * bh // 6, x + bw // 12: x + 11 * bw // 12]
    if seam_x is None:
        return dict(left=float(inner.mean()), right=float(inner.mean()))
    rel = seam_x - (x + bw // 12)
    rel = max(1, min(inner.shape[1] - 1, rel))
    return dict(left=float(inner[:, :rel].mean()), right=float(inner[:, rel:].mean()))

# -------------------------------------------------------------- image class
def true_white_frac(bgr):
    """Fraction of pixels that are true studio white: every channel high AND nearly
    neutral. Grayscale luminance alone is fooled by bright cream/tan iridescent glass
    (high R,G but lower B), so require low channel spread too."""
    b, g, r = bgr[:, :, 0].astype(np.int16), bgr[:, :, 1].astype(np.int16), bgr[:, :, 2].astype(np.int16)
    mn = np.minimum(np.minimum(b, g), r)
    mx = np.maximum(np.maximum(b, g), r)
    return float(((mn > 240) & ((mx - mn) < 14)).mean())

def classify_image(bgr):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    box = find_sheet_box(gray)
    bg = background_analysis(bgr, box)
    white = true_white_frac(bgr)
    if box is not None:
        box['true_white'] = white
    is_ws = bool(box and box.get('n_sides', 0) >= 3 and box['fill'] > 0.55
                 and box['touch'] <= 1 and 0.55 <= box['aspect'] <= 1.85
                 and white > 0.05)
    return dict(box=box, bg=bg, is_whole_sheet=is_ws)

# -------------------------------------------------------------- SIFT scale
_sift = cv2.SIFT_create(nfeatures=4000)
def sift_scale(pa, pb):
    ia = load_gray(pa)
    ib = load_gray(pb)
    ka, da = _sift.detectAndCompute(ia, None)
    kb, db = _sift.detectAndCompute(ib, None)
    if da is None or db is None or len(ka) < 10 or len(kb) < 10:
        return dict(good=0, inliers=0, scale=None)
    good = [m for m, n in cv2.BFMatcher().knnMatch(da, db, k=2) if m.distance < 0.75 * n.distance]
    if len(good) < 12:
        return dict(good=len(good), inliers=0, scale=None)
    src = np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=5.0)
    if M is None:
        return dict(good=len(good), inliers=0, scale=None)
    return dict(good=len(good), inliers=int(inl.sum()),
                scale=float(np.sqrt(M[0, 0] ** 2 + M[0, 1] ** 2)))
