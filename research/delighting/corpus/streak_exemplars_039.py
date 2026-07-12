"""Report 039: exemplar-first measurement of the real Wispy/Streaky corpus.

Selects ~30 clean-manifest Wispy/Streaky sheets covering the maintainer's named
variety (white-on-color, color-on-white, multi-color flame, subtle vs dramatic),
measures the properties that make real streaky glass read as LIQUID, and writes
a labeled contact sheet + a per-sheet stats JSON + an aggregate summary.

Measured per sheet (center 70% crop, to avoid the sheet's cut edges/backdrop):
  - tonal_range: L* p5/p50/p95 and (p95-p5) within-sheet
  - color pair: 2-means on (a*,b*), chroma of each mode + Delta-ab between modes,
    and the population split (how two-tone vs continuous the sheet is)
  - anisotropy: structure-tensor coherence (0 isotropic .. 1 perfectly directional)
    and dominant orientation; flow coherence length via autocorrelation along flow
  - edge bimodality: gradient-magnitude distribution -- real streaky glass has BOTH
    smooth gradients (lots of near-zero gradient) AND sharp filament/lamination
    boundaries (a heavy high-gradient tail). Reported as p50 and p99 grad and the
    p99/p50 ratio (the 'bimodality' number: high = sharp edges coexist with smooth).
  - hf_energy_frac: same radial-FFT statistic as appearance_stats.py (comparable).
  - highlight_frac: fraction of near-white specular pixels (gloss along streaks).

Corpus read-only via the frontend symlink (reports 015/021 convention).
"""
import json
import os
import sys
import collections

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
# Corpus lives in the main checkout (gitignored on main); read-only. Prefer the
# worktree-local frontend symlink, fall back to the known main-checkout path.
_CANDIDATES = [
    os.path.join(HERE, "..", "frontend", "public", "assets", "catalog_images"),
    os.path.abspath(os.path.join(HERE, "..", "..", "..", "frontend", "public", "assets", "catalog_images")),
    "/Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/catalog_images",
]
CATALOG = next((p for p in _CANDIDATES if os.path.isdir(p) and os.listdir(p)), _CANDIDATES[0])
RESULTS = os.path.join(HERE, "..", "results", "039")
MANIFEST = os.path.join(HERE, "..", "results", "corpus", "clean_manifest.json")

# Curated exemplar set -- chosen by name to span the maintainer's variety.
# grp tags: woc=white-on-color, cow=color-on-white/subtle, flame=multi-color,
# dram=dramatic/dark-pair, irid=iridescent(color-caveat, structure ok)
CURATED = [
    # white-on-color, saturated single pairs (Oceanside "White Wispy" line)
    ("oceanside-of3591s.jpg", "Red+White Wispy", "woc"),
    ("oceanside-of83291s.jpg", "Caribbean Blue+White Wispy", "woc"),
    ("oceanside-of82392s.jpg", "Teal Green+White Wispy", "woc"),
    ("oceanside-of83896s.jpg", "Navy Blue+White Wispy", "woc"),
    ("oceanside-of3496s.jpg", "Dark Purple+White Wispy", "woc"),
    ("oceanside-of3791s.jpg", "Orange+White Wispy", "woc"),
    ("oceanside-of82692s.jpg", "Moss Green+White Wispy", "woc"),
    ("oceanside-of83872s.jpg", "Colonial Blue+White Wispy", "woc"),
    # Bullseye "2-Color Mix" white-on-color (crisper lamination)
    ("bullseye-0021240030f1010.jpg", "Red Opal+White Mix", "woc"),
    ("bullseye-0020470030f1010.jpg", "Clear+Deep Cobalt Mix", "woc"),
    ("bullseye-0021640030f1010.jpg", "Caribbean Blue+White Mix", "woc"),
    ("bullseye-0021160030f1010.jpg", "Turquoise+Royal Blue Mix", "dram"),
    ("bullseye-0021760030f1010.jpg", "Peacock+White Opal Mix", "woc"),
    ("bullseye-0021000030f1010.jpg", "Clear+Black Mix", "dram"),
    ("bullseye-0021290030f1010.jpg", "Charcoal+White Mix", "dram"),
    # subtle / pale (color-on-white, low drama end)
    ("oceanside-of309s.jpg", "Clear+White Wispy", "cow"),
    ("oceanside-of31902s.jpg", "Pale Amber+White Wispy", "cow"),
    ("oceanside-of3291s.jpg", "Pale Green+White Wispy", "cow"),
    ("oceanside-of89181s.jpg", "Pink Champagne+White", "cow"),
    ("bullseye-0004200030f1010.jpg", "Cream Opalescent", "cow"),
    # multi-color flame (Oceanside Fusers Reserve)
    ("oceanside-ofr73.jpg", "Phoenix", "flame"),
    ("oceanside-ofr72.jpg", "Fiesta", "flame"),
    ("oceanside-ofr93.jpg", "Antelope Canyon", "flame"),
    ("oceanside-ofr88.jpg", "Aurora", "flame"),
    ("oceanside-ofr71.jpg", "Stardust", "flame"),
    ("oceanside-ofr68s.jpg", "Riptide", "flame"),
    # Wissmach streaky (long liquid pulls)
    ("wissmach-w701ll.jpg", "Lotus Streaky", "dram"),
    ("wissmach-wi703ll.jpg", "Blue+Purple Streaky", "dram"),
    ("wissmach-w145sp.jpg", "Tiger Eye Streaky", "flame"),
    ("wissmach-wiwo59.jpg", "Dk Brown+Green+White", "flame"),
    # Youghiogheny streaky
    ("youghiogheny-yf1043.jpg", "Fern Green+White Streaky", "woc"),
    ("youghiogheny-yuf606125.jpg", "Grenadine+White Streaky", "woc"),
]


def srgb_to_linear(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def srgb_to_lab(rgb):
    lin = srgb_to_linear(rgb)
    M = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    d = 6.0 / 29.0
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4.0 / 29.0)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def high_freq_energy_fraction(luma):
    f = np.fft.fftshift(np.fft.fft2(luma - luma.mean()))
    p = np.abs(f) ** 2
    n = luma.shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.sqrt((yy - n / 2) ** 2 + (xx - n / 2) ** 2)
    outer = r > n / 4.0
    return float(p[outer].sum() / (p.sum() + 1e-12))


def two_mode_color(lab):
    """2-means on (a,b). Returns chroma of each mode, delta-ab between them,
    minority fraction (how balanced the two colors are)."""
    ab = lab[..., 1:].reshape(-1, 2)
    # init at 5th/95th percentile of the first principal direction
    c = ab - ab.mean(0)
    u, s, vt = np.linalg.svd(c, full_matrices=False)
    proj = c @ vt[0]
    m0 = ab[proj <= np.percentile(proj, 15)].mean(0)
    m1 = ab[proj >= np.percentile(proj, 85)].mean(0)
    for _ in range(12):
        d0 = ((ab - m0) ** 2).sum(1)
        d1 = ((ab - m1) ** 2).sum(1)
        a0 = d0 <= d1
        if a0.sum() == 0 or a0.sum() == len(ab):
            break
        m0 = ab[a0].mean(0)
        m1 = ab[~a0].mean(0)
    frac0 = float(a0.mean())
    return {
        "mode0_chroma": float(np.hypot(*m0)),
        "mode1_chroma": float(np.hypot(*m1)),
        "delta_ab": float(np.hypot(*(m1 - m0))),
        "minority_frac": float(min(frac0, 1 - frac0)),
    }


def structure_tensor_coherence(luma):
    """Coherence in [0,1]: 1 = perfectly directional (streaky), 0 = isotropic.
    Plus dominant orientation degrees."""
    gy, gx = np.gradient(luma)
    Jxx = float((gx * gx).mean())
    Jyy = float((gy * gy).mean())
    Jxy = float((gx * gy).mean())
    tr = Jxx + Jyy
    det = Jxx * Jyy - Jxy * Jxy
    disc = max(0.0, (tr / 2) ** 2 - det)
    l1 = tr / 2 + np.sqrt(disc)
    l2 = tr / 2 - np.sqrt(disc)
    coh = float((l1 - l2) / (l1 + l2 + 1e-12))
    theta = 0.5 * np.degrees(np.arctan2(2 * Jxy, Jxx - Jyy))
    return coh, float(theta)


def edge_bimodality(luma):
    """Gradient-magnitude distribution. Real streaky glass: many smooth (low-grad)
    pixels AND a heavy tail of sharp filament/lamination edges. Ratio p99/p50 is
    the bimodality signal."""
    gy, gx = np.gradient(luma)
    g = np.hypot(gx, gy)
    p50 = float(np.percentile(g, 50))
    p90 = float(np.percentile(g, 90))
    p99 = float(np.percentile(g, 99))
    return {"grad_p50": p50, "grad_p90": p90, "grad_p99": p99,
            "bimodality_p99_p50": float(p99 / (p50 + 1e-6)),
            "sharp_frac": float((g > 5 * (p50 + 1e-6)).mean())}


def measure(path):
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = int(min(w, h) * 0.70)
    l, t = (w - s) // 2, (h - s) // 2
    im = im.crop((l, t, l + s, t + s)).resize((256, 256), Image.LANCZOS)
    rgb = np.asarray(im, np.float32) / 255.0
    lab = srgb_to_lab(rgb)
    L = lab[..., 0]
    luma = rgb @ np.array([0.2126, 0.7152, 0.0722])
    C = np.hypot(lab[..., 1], lab[..., 2])
    coh, theta = structure_tensor_coherence(luma)
    out = {
        "L_p5": float(np.percentile(L, 5)), "L_p50": float(np.median(L)),
        "L_p95": float(np.percentile(L, 95)),
        "L_range": float(np.percentile(L, 95) - np.percentile(L, 5)),
        "C_p50": float(np.median(C)), "C_p95": float(np.percentile(C, 95)),
        "hf_energy_frac": high_freq_energy_fraction(luma),
        "coherence": coh, "orientation_deg": theta,
        "highlight_frac": float((luma > 0.92).mean()),
    }
    out.update(two_mode_color(lab))
    out.update(edge_bimodality(luma))
    return out, im


def main():
    os.makedirs(RESULTS, exist_ok=True)
    rows = []
    thumbs = []
    for fn, label, grp in CURATED:
        p = os.path.join(CATALOG, fn)
        if not os.path.exists(p):
            print("MISSING", fn)
            continue
        st, thumb = measure(p)
        st["file"] = fn
        st["label"] = label
        st["group"] = grp
        rows.append(st)
        thumbs.append((thumb.resize((180, 180)), f"{label}", grp, st))

    # contact sheet
    cols = 6
    rowsN = (len(thumbs) + cols - 1) // cols
    cell = 180
    pad = 26
    sheet = Image.new("RGB", (cols * cell, rowsN * (cell + pad)), (245, 245, 245))
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    for i, (th, lab, grp, st) in enumerate(thumbs):
        r, c = divmod(i, cols)
        x, y = c * cell, r * (cell + pad)
        sheet.paste(th, (x, y))
        d.text((x + 2, y + cell + 1), f"{lab[:26]}", fill=(0, 0, 0))
        d.text((x + 2, y + cell + 12), f"{grp} coh{st['coherence']:.2f} bi{st['bimodality_p99_p50']:.0f} dab{st['delta_ab']:.0f}", fill=(90, 90, 90))
    sheet.save(os.path.join(RESULTS, "exemplar_contact_sheet.jpg"), quality=88)

    with open(os.path.join(RESULTS, "exemplar_stats.json"), "w") as f:
        json.dump(rows, f, indent=1)

    # aggregate by group + overall
    def agg(sub, keys):
        return {k: round(float(np.median([r[k] for r in sub])), 3) for k in keys}
    keys = ["L_p50", "L_range", "C_p50", "C_p95", "hf_energy_frac", "coherence",
            "delta_ab", "minority_frac", "bimodality_p99_p50", "grad_p99",
            "sharp_frac", "highlight_frac", "mode0_chroma", "mode1_chroma"]
    summary = {"overall": agg(rows, keys), "n": len(rows)}
    for g in sorted(set(r["group"] for r in rows)):
        sub = [r for r in rows if r["group"] == g]
        summary[g] = {"n": len(sub), **agg(sub, keys)}
    with open(os.path.join(RESULTS, "exemplar_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
