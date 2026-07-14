"""Report 043 item 3: exemplar-grounded colors for the four report-037 taxa
(baroque-rolling-wave, fracture-streamer, confetti-shard, ring-mottle).

Report 037 authored these recipes' colors as "plausible choices chosen for
corpus-hue diversity, not independently re-grounded" and flagged that honestly.
This script is the 039-method grounding pass those recipes were owed: find each
taxon's REAL corpus exemplars (manifest name/category matching, the same
clean_manifest.json + catalog_images read-only convention as reports 015/021/
039), measure their Lab color structure (2-means light/dark modes per sheet,
per the streak_color_pairs_039.py method), and emit the measured distribution
that generate_synthetic.py's sample_taxa_colors() constants are copied from.

Exemplar populations (queried from clean_manifest.json):
  ring-mottle       -> the literal 'Ring Mottle' category (8 Youghiogheny
                       'Mottle' sheets, all extractor-class opalescent).
  fracture-streamer -> Bullseye 'Collage' sheets whose name says Fracture or
                       Streamer (8 sheets).
  confetti-shard    -> Bullseye 'Collage' sheets (the same physical product
                       family, per report 031 sec5) minus the pure line-network
                       ones -- i.e. the color-shards-on-clear/white population.
  baroque-rolling-wave -> 'Textured/Baroque' category, extractor-class
                       cathedral-clear (the clear rolled-texture population:
                       Artique / Waterglass / Granite / Hammered etc.) --
                       T3 is a RELIEF taxon, so its color grounding target is
                       "what color is real textured cathedral glass", not a
                       figure pattern.

Iridescent/dichroic/luminescent-named sheets are excluded per report 021's
convention (their photographed color is a thin-film artifact, not T).

Outputs results/043/taxa_exemplar_colors.json + a labeled contact sheet per
taxon (results/043/taxa_exemplars_<taxon>.jpg).

Usage: python3 corpus/taxa_exemplars_043.py
"""
import json
import os
import re

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
_CANDS = [
    os.path.join(HERE, "..", "frontend", "public", "assets", "catalog_images"),
    "/Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/catalog_images",
]
CATALOG = next(p for p in _CANDS if os.path.isdir(p) and os.listdir(p))
RESULTS = os.path.join(HERE, "..", "results", "043")
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
    """2-means in full Lab; return (light_mode_Lab, dark_mode_Lab, light_frac).
    Same as streak_color_pairs_039.two_modes_by_L."""
    X = lab.reshape(-1, 3)
    lo = X[X[:, 0] <= np.percentile(X[:, 0], 20)].mean(0)
    hi = X[X[:, 0] >= np.percentile(X[:, 0], 80)].mean(0)
    a = X[:, 0] >= np.median(X[:, 0])
    for _ in range(15):
        dlo = ((X - lo) ** 2).sum(1)
        dhi = ((X - hi) ** 2).sum(1)
        a = dhi <= dlo
        if a.sum() in (0, len(X)):
            break
        hi, lo = X[a].mean(0), X[~a].mean(0)
    return hi, lo, float(a.mean())


def sheet_lab(path, res=160):
    pic = Image.open(path).convert("RGB")
    w, h = pic.size
    s = int(min(w, h) * 0.7)
    pic = pic.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((res, res))
    return srgb_to_lab(np.asarray(pic, np.float32) / 255.0), pic


def select_taxon_sheets(ims):
    """Return {taxon: [manifest entries]} per the module docstring queries."""
    frac_re = re.compile(r"fract|streamer", re.I)
    collage_re = re.compile(r"collage", re.I)
    out = {}
    out["ring-mottle"] = [i for i in ims if i["category"] == "Ring Mottle"]
    collage = [i for i in ims if collage_re.search(i["name"] or "")]
    out["fracture-streamer"] = [i for i in collage if frac_re.search(i["name"] or "")]
    # confetti-shard: the colored-shard collage population. Keep sheets whose
    # name lists colors-on-base ("X, Y on Clear/White"); the pure
    # fracture/streamer line sheets stay in the other taxon (overlap where a
    # sheet has both shards AND streamers is fine -- physically the same
    # product carries both).
    out["confetti-shard"] = [i for i in collage
                             if re.search(r"\bon (Clear|White)\b", i["name"] or "", re.I)]
    out["baroque-rolling-wave"] = [i for i in ims
                                   if i["category"] == "Textured/Baroque"
                                   and i["extractor_class"] == "cathedral-clear"]
    # 021 convention: drop thin-film-named sheets from COLOR grounding.
    for k in out:
        out[k] = [i for i in out[k]
                  if not (CAVEAT.search(i["name"] or "") or CAVEAT.search(i["file"] or ""))]
    return out


def hue_deg(a, b):
    return float(np.degrees(np.arctan2(b, a)) % 360.0)


def analyze(entries):
    rows = []
    for im in entries:
        p = os.path.join(CATALOG, im["file"])
        if not os.path.exists(p):
            continue
        lab, _pic = sheet_lab(p)
        hi, lo, lf = two_modes_by_L(lab)
        rows.append({
            "file": im["file"], "name": im["name"],
            "light_L": round(float(hi[0]), 1), "light_C": round(float(np.hypot(hi[1], hi[2])), 1),
            "light_hue": round(hue_deg(hi[1], hi[2]), 1),
            "dark_L": round(float(lo[0]), 1), "dark_C": round(float(np.hypot(lo[1], lo[2])), 1),
            "dark_hue": round(hue_deg(lo[1], lo[2]), 1),
            "L_sep": round(float(hi[0] - lo[0]), 1), "light_frac": round(lf, 3),
        })
    return rows


def summarize(rows):
    if not rows:
        return {}
    def pct(key):
        v = np.array([r[key] for r in rows])
        return {"p25": round(float(np.percentile(v, 25)), 1),
                "p50": round(float(np.percentile(v, 50)), 1),
                "p75": round(float(np.percentile(v, 75)), 1)}
    return {k: pct(k) for k in ("light_L", "light_C", "dark_L", "dark_C", "L_sep", "light_frac")}


def contact_sheet(entries, taxon, tile=200):
    entries = [e for e in entries if os.path.exists(os.path.join(CATALOG, e["file"]))]
    if not entries:
        return
    cols = min(6, len(entries))
    rows_n = (len(entries) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile, rows_n * (tile + 18)), (24, 24, 24))
    dr = ImageDraw.Draw(sheet)
    for i, e in enumerate(entries):
        pic = Image.open(os.path.join(CATALOG, e["file"])).convert("RGB").resize((tile, tile))
        x, y = (i % cols) * tile, (i // cols) * (tile + 18)
        sheet.paste(pic, (x, y))
        dr.text((x + 3, y + tile + 3), e["file"][:34], fill=(230, 230, 230))
    sheet.save(os.path.join(RESULTS, f"taxa_exemplars_{taxon}.jpg"), quality=88)


def main():
    os.makedirs(RESULTS, exist_ok=True)
    m = json.load(open(MANIFEST))
    sel = select_taxon_sheets(m["images"])
    out = {}
    for taxon, entries in sel.items():
        rows = analyze(entries)
        out[taxon] = {"n": len(rows), "sheets": rows, "summary": summarize(rows)}
        contact_sheet(entries, taxon)
        print(f"== {taxon}: n={len(rows)}")
        for r in rows:
            print(f"   {r['file'][:36]:36s} light L*{r['light_L']:5.1f} C*{r['light_C']:5.1f} h{r['light_hue']:5.0f} | "
                  f"dark L*{r['dark_L']:5.1f} C*{r['dark_C']:5.1f} h{r['dark_hue']:5.0f} | sep {r['L_sep']:5.1f}")
        print("   summary:", json.dumps(out[taxon]["summary"]))
    with open(os.path.join(RESULTS, "taxa_exemplar_colors.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("\nwrote", os.path.join(RESULTS, "taxa_exemplar_colors.json"))


if __name__ == "__main__":
    main()
