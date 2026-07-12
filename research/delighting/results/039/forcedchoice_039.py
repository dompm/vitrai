"""Report 039 forced-choice realism test. Each lineup = a 2x2 grid of 4 crops
(3 real corpus Wispy/Streaky + 1 our rendered synthetic, position shuffled),
numbered 1-4. Ask the `claude` CLI: which panel is the computer-generated render?
Ideal detection rate ~= chance (25%); the rejected version was detected ~always.

Usage: python3 forcedchoice_039.py [--model sonnet] [--n 10]
"""
import argparse
import glob
import json
import os
import random
import subprocess

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.abspath(os.path.join(HERE, "..", ".."))
_CANDS = [os.path.join(DELIGHT, "frontend", "public", "assets", "catalog_images"),
          "/Users/dominiquepiche-meunier/Documents/vitraux/frontend/public/assets/catalog_images"]
CATALOG = next(p for p in _CANDS if os.path.isdir(p) and os.listdir(p))
MANIFEST = os.path.join(DELIGHT, "results", "corpus", "clean_manifest.json")
RENDERS = os.path.join(HERE, "board_renders")
LINEUPS = os.path.join(HERE, "forcedchoice")
TILE = 300

PROMPT = ("Read the image file at {path}. It is a 2x2 grid of four numbered crops "
          "(1 top-left, 2 top-right, 3 bottom-left, 4 bottom-right), each a close-up "
          "of streaky/wispy art glass. Exactly ONE is a computer-generated 3D render; "
          "the other three are photographs of real glass. Which number is the "
          "computer-generated render? Reply with ONLY the single digit 1, 2, 3, or 4.")


def center_crop(im, frac=0.55):
    w, h = im.size
    s = int(min(w, h) * frac)
    return im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((TILE, TILE), Image.LANCZOS)


def build_lineup(idx, real_files, synth_png, rng):
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
    path = os.path.join(LINEUPS, f"lineup_{idx:02d}.png")
    grid.save(path)
    return path, synth_pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--n", type=int, default=10)
    args = ap.parse_args()
    os.makedirs(LINEUPS, exist_ok=True)
    rng = random.Random(39)

    man = json.load(open(MANIFEST))
    reals = [i["file"] for i in man["images"]
             if i["category"] == "Wispy/Streaky" and i["extractor_class"] == "wispy"
             and os.path.exists(os.path.join(CATALOG, i["file"]))]
    synths = sorted(glob.glob(os.path.join(RENDERS, "*", "without_shadow_photo.png")))
    if not synths:
        raise SystemExit("no board renders yet")

    results = []
    for k in range(args.n):
        synth = synths[k % len(synths)]
        rf = rng.sample(reals, 3)
        path, synth_pos = build_lineup(k, rf, synth, rng)
        try:
            out = subprocess.run(["claude", "-p", PROMPT.format(path=os.path.abspath(path)),
                                  "--allowedTools", "Read", "--model", args.model],
                                 capture_output=True, text=True, timeout=180)
            digits = [c for c in out.stdout if c in "1234"]
            guess = int(digits[-1]) if digits else None
        except Exception as e:
            guess = None
            out = type("x", (), {"stdout": str(e)})
        detected = (guess == synth_pos)
        results.append({"lineup": os.path.basename(path), "synth_pos": synth_pos,
                        "guess": guess, "detected": detected,
                        "synth_src": os.path.basename(os.path.dirname(synth)),
                        "raw": out.stdout.strip()[:40]})
        print(f"  lineup {k:02d}: synth@{synth_pos} guess={guess} "
              f"{'DETECTED' if detected else 'fooled' if guess else 'unparsed'}")

    n_valid = sum(1 for r in results if r["guess"] is not None)
    n_det = sum(1 for r in results if r["detected"])
    rate = n_det / n_valid if n_valid else float("nan")
    summary = {"model": args.model, "n": args.n, "n_valid": n_valid,
               "n_detected": n_det, "detection_rate": rate, "chance": 0.25,
               "results": results}
    json.dump(summary, open(os.path.join(HERE, "forcedchoice_results.json"), "w"), indent=1)
    print(f"\nDetection rate: {n_det}/{n_valid} = {rate:.0%}  (chance 25%)")


if __name__ == "__main__":
    main()
