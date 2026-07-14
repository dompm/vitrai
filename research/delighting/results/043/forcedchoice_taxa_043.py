"""Report 043 item 3 forced-choice color-grounding test (the 039 protocol,
per-taxon). Each lineup = a 2x2 grid: 3 real corpus exemplars of one taxon +
1 our render of that taxon's recipe (position shuffled), luminance-normalized
(so the test measures palette/structure, not the corpus-vs-render exposure
gap -- 039's _normalize). Ask the `claude` CLI which panel is the render.
Detection ~ chance (25%) = our palette sits inside the real family.

Run for --renders /tmp/043_taxa_after (the exemplar-grounded rebuild) and
--renders /tmp/043_taxa_before --tag before (the 037 authored-guess colors).

Usage: python3 results/043/forcedchoice_taxa_043.py [--model sonnet] [--tag after]
"""
import argparse
import glob
import json
import os
import random
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.abspath(os.path.join(HERE, "..", ".."))
_CANDS = [os.path.join(DELIGHT, "frontend", "public", "assets", "catalog_images"),
          "/Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/catalog_images"]
CATALOG = next(p for p in _CANDS if os.path.isdir(p) and os.listdir(p))
MANIFEST = os.path.join(DELIGHT, "results", "corpus", "clean_manifest.json")
TILE = 300
CAVEAT = re.compile(r"irid|dichro|lumin", re.I)

PROMPT = ("Read the image file at {path}. It is a 2x2 grid of four numbered crops "
          "(1 top-left, 2 top-right, 3 bottom-left, 4 bottom-right), each a close-up "
          "of {family} art glass. Exactly ONE is a computer-generated 3D render; "
          "the other three are photographs of real glass. Which number is the "
          "computer-generated render? Reply with ONLY the single digit 1, 2, 3, or 4.")

FAMILY_DESC = {
    "baroque-rolling-wave": "textured rolled cathedral",
    "fracture-streamer": "fracture-and-streamer collage",
    "confetti-shard": "confetti collage",
    "ring-mottle": "ring-mottle opalescent",
}


def _normalize(im, tgt_mean=0.5, tgt_std=0.20):
    a = np.asarray(im, np.float32) / 255.0
    lum = a @ np.array([0.2126, 0.7152, 0.0722])
    m, s = lum.mean(), lum.std() + 1e-6
    gain = tgt_std / s
    new_lum = np.clip((lum - m) * gain + tgt_mean, 0, 1)
    ratio = (new_lum / (lum + 1e-6))[..., None]
    return Image.fromarray((np.clip(a * ratio, 0, 1) * 255).astype(np.uint8))


def center_crop(im, frac=0.55):
    w, h = im.size
    s = int(min(w, h) * frac)
    c = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((TILE, TILE), Image.LANCZOS)
    return _normalize(c)


def real_pool(ims, taxon):
    """The same exemplar populations corpus/taxa_exemplars_043.py grounded on."""
    frac_re = re.compile(r"fract|streamer", re.I)
    collage_re = re.compile(r"collage", re.I)
    if taxon == "ring-mottle":
        pool = [i for i in ims if i["category"] == "Ring Mottle"]
    elif taxon == "fracture-streamer":
        pool = [i for i in ims if collage_re.search(i["name"] or "") and frac_re.search(i["name"] or "")]
    elif taxon == "confetti-shard":
        pool = [i for i in ims if collage_re.search(i["name"] or "")
                and re.search(r"\bon (Clear|White)\b", i["name"] or "", re.I)]
    else:  # baroque-rolling-wave
        pool = [i for i in ims if i["category"] == "Textured/Baroque"
                and i["extractor_class"] == "cathedral-clear"]
    pool = [i["file"] for i in pool
            if not (CAVEAT.search(i["name"] or "") or CAVEAT.search(i["file"] or ""))
            and os.path.exists(os.path.join(CATALOG, i["file"]))]
    return pool


def build_lineup(outdir, idx, taxon, real_files, synth_png, rng):
    crops = [("real", center_crop(Image.open(os.path.join(CATALOG, f)).convert("RGB"))) for f in real_files]
    crops.append(("synth", center_crop(Image.open(synth_png).convert("RGB"))))
    rng.shuffle(crops)
    synth_pos = [i for i, (k, _) in enumerate(crops) if k == "synth"][0] + 1
    grid = Image.new("RGB", (2 * TILE + 6, 2 * TILE + 6), (255, 255, 255))
    d = ImageDraw.Draw(grid)
    for i, (_, c) in enumerate(crops):
        r, cc = divmod(i, 2)
        x, y = cc * (TILE + 6), r * (TILE + 6)
        grid.paste(c, (x, y))
        d.rectangle([x + 4, y + 4, x + 26, y + 24], fill=(0, 0, 0))
        d.text((x + 10, y + 8), str(i + 1), fill=(255, 255, 0))
    path = os.path.join(outdir, f"lineup_{taxon}_{idx:02d}.png")
    grid.save(path)
    return path, synth_pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--renders", default="/tmp/043_taxa_after")
    ap.add_argument("--tag", default="after")
    ap.add_argument("--per-taxon", type=int, default=3)
    args = ap.parse_args()
    lineups_dir = os.path.join(HERE, f"forcedchoice_taxa_{args.tag}")
    os.makedirs(lineups_dir, exist_ok=True)
    rng = random.Random(43)

    man = json.load(open(MANIFEST))
    results = []
    for taxon in FAMILY_DESC:
        pool = real_pool(man["images"], taxon)
        synths = sorted(glob.glob(os.path.join(args.renders, f"{taxon}__*", "without_shadow_photo.png")))
        if not synths:
            print(f"!! no render for {taxon} in {args.renders}, skipping")
            continue
        for k in range(args.per_taxon):
            rf = rng.sample(pool, min(3, len(pool)))
            path, synth_pos = build_lineup(lineups_dir, k, taxon, rf, synths[k % len(synths)], rng)
            try:
                out = subprocess.run(["claude", "-p", PROMPT.format(path=os.path.abspath(path),
                                                                    family=FAMILY_DESC[taxon]),
                                      "--allowedTools", "Read", "--model", args.model],
                                     capture_output=True, text=True, timeout=180)
                digits = [c for c in out.stdout if c in "1234"]
                guess = int(digits[-1]) if digits else None
            except Exception as e:
                guess = None
                out = type("x", (), {"stdout": str(e)})
            detected = (guess == synth_pos)
            results.append({"taxon": taxon, "lineup": os.path.basename(path),
                            "synth_pos": synth_pos, "guess": guess, "detected": detected,
                            "raw": out.stdout.strip()[:40]})
            print(f"  {taxon} lineup {k}: synth@{synth_pos} guess={guess} "
                  f"{'DETECTED' if detected else 'fooled' if guess else 'unparsed'}")

    n_valid = sum(1 for r in results if r["guess"] is not None)
    n_det = sum(1 for r in results if r["detected"])
    rate = n_det / n_valid if n_valid else float("nan")
    summary = {"model": args.model, "renders": args.renders, "n_valid": n_valid,
               "n_detected": n_det, "detection_rate": rate, "chance": 0.25,
               "results": results}
    json.dump(summary, open(os.path.join(HERE, f"forcedchoice_taxa_results_{args.tag}.json"), "w"), indent=1)
    print(f"\n[{args.tag}] detection rate: {n_det}/{n_valid} = {rate:.0%} (chance 25%)")


if __name__ == "__main__":
    main()
