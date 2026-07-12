"""Report 039: real color-pair distribution over ALL 158 clean Wispy/Streaky
sheets, so the rebuilt streak recipes sample color pairs from the measured real
distribution (maintainer: 'not invented pastels').

For each sheet: 2-means on Lab -> a LIGHT mode (higher L, the milky/white pull)
and a DARK mode (lower L, the saturated color pull). Emits per-sheet Lab of each
mode + the population, and aggregate percentiles used directly as authoring
targets.  Iridescent/dichroic/luminescent-named sheets are flagged (color-caveat)
per report 021's convention and excluded from the color aggregate.
"""
import json
import os
import re

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
_CANDS = [
    os.path.join(HERE, "..", "frontend", "public", "assets", "catalog_images"),
    "/Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/catalog_images",
]
CATALOG = next(p for p in _CANDS if os.path.isdir(p) and os.listdir(p))
RESULTS = os.path.join(HERE, "..", "results", "039")
MANIFEST = os.path.join(HERE, "..", "results", "corpus", "clean_manifest.json")
CAVEAT = re.compile(r"irid|dichro|lumin", re.I)


def srgb_to_linear(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def srgb_to_lab(rgb):
    lin = srgb_to_linear(rgb)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = (lin @ M.T) / np.array([0.95047, 1.0, 1.08883])
    d = 6.0 / 29.0
    f = np.where(xyz > d ** 3, np.cbrt(xyz), xyz / (3 * d * d) + 4.0 / 29.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def two_modes_by_L(lab):
    """2-means in full Lab; return (light_mode_Lab, dark_mode_Lab, light_frac)."""
    X = lab.reshape(-1, 3)
    lo = X[X[:, 0] <= np.percentile(X[:, 0], 20)].mean(0)
    hi = X[X[:, 0] >= np.percentile(X[:, 0], 80)].mean(0)
    for _ in range(15):
        dlo = ((X - lo) ** 2).sum(1)
        dhi = ((X - hi) ** 2).sum(1)
        a = dhi <= dlo  # assigned to hi (light)
        if a.sum() in (0, len(X)):
            break
        hi, lo = X[a].mean(0), X[~a].mean(0)
    return hi, lo, float(a.mean())


def main():
    m = json.load(open(MANIFEST))
    ws = [i for i in m["images"] if i["category"] == "Wispy/Streaky" and i["extractor_class"] == "wispy"]
    rows = []
    for im in ws:
        p = os.path.join(CATALOG, im["file"])
        if not os.path.exists(p):
            continue
        pic = Image.open(p).convert("RGB")
        w, h = pic.size
        s = int(min(w, h) * 0.7)
        pic = pic.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((160, 160))
        lab = srgb_to_lab(np.asarray(pic, np.float32) / 255.0)
        hi, lo, lf = two_modes_by_L(lab)
        rows.append({
            "file": im["file"], "name": im["name"],
            "caveat": bool(CAVEAT.search(im["name"]) or CAVEAT.search(im["file"])),
            "light_L": float(hi[0]), "light_a": float(hi[1]), "light_b": float(hi[2]),
            "light_C": float(np.hypot(hi[1], hi[2])),
            "dark_L": float(lo[0]), "dark_a": float(lo[1]), "dark_b": float(lo[2]),
            "dark_C": float(np.hypot(lo[1], lo[2])),
            "light_frac": lf, "L_sep": float(hi[0] - lo[0]),
        })
    clean = [r for r in rows if not r["caveat"]]
    os.makedirs(RESULTS, exist_ok=True)
    json.dump(rows, open(os.path.join(RESULTS, "color_pairs.json"), "w"), indent=1)

    def pct(key, ps=(10, 25, 50, 75, 90)):
        v = np.array([r[key] for r in clean])
        return {f"p{p}": round(float(np.percentile(v, p)), 1) for p in ps}

    summary = {
        "n_total": len(rows), "n_clean": len(clean), "n_caveat": len(rows) - len(clean),
        "light_mode": {k: pct(f"light_{k}") for k in ["L", "C"]},
        "dark_mode": {k: pct(f"dark_{k}") for k in ["L", "C"]},
        "L_separation": pct("L_sep"),
        "light_frac": pct("light_frac"),
        # hue of the dark (color) mode as chroma-weighted circular stats
    }
    # dark-mode hue histogram (the saturated color's hue)
    hues = np.degrees(np.arctan2([r["dark_b"] for r in clean], [r["dark_a"] for r in clean])) % 360
    Cs = np.array([r["dark_C"] for r in clean])
    bins = np.arange(0, 361, 30)
    hist = np.histogram(hues, bins=bins, weights=Cs)[0]
    summary["dark_hue_weighted_hist_30deg"] = {f"{bins[i]}-{bins[i+1]}": round(float(hist[i]), 0) for i in range(len(hist))}
    json.dump(summary, open(os.path.join(RESULTS, "color_pairs_summary.json"), "w"), indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
