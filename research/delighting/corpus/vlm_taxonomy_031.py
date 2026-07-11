#!/usr/bin/env python3
"""Report 031: VLM taxonomy pass over contact-sheet grids. For each grid,
ask the VLM to enumerate the DISTINCT glass varieties visible, describing
each by visual STRUCTURE (texture type, opacity structure, surface vs body
feature), not by product name. Catalog names given as hints only.

Usage: vlm_taxonomy_031.py [batch_glob] [--model sonnet]
Writes results/variety_031/taxonomy_raw/batchNN.txt (raw VLM response).
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "results", "variety_031")
GRID_DIR = os.path.join(OUT_DIR, "grids")
RAW_DIR = os.path.join(OUT_DIR, "taxonomy_raw")

PROMPT_TMPL = """Read the image file at {img}. It is a contact sheet: a grid \
of {n} numbered tiles (#000 style labels), each tile a photo of a real \
stained-glass sheet held up to backlight (a manufacturer product photo). \
The tiles are cropped square from the sheet and lightly resized -- ignore \
JPEG artifacts.

Catalog product names, as hints ONLY -- the name is metadata written by the \
manufacturer's marketing, it can be wrong, generic, or omit real visual \
structure. Judge every tile primarily by the PIXELS, not the name:
{hints}

TASK: enumerate the DISTINCT glass VARIETIES visible across this grid's \
tiles, from a bottom-up visual read (not from the catalog's own category \
system). A "variety" is a structural/optical pattern type: e.g. "ring \
mottle" (dense overlapping circular/oval opaque blobs), "seedy" (small \
round bubbles suspended in the body, visible as dark or bright dots), \
"granite/ripple relief" (fine all-over irregular pebbled surface relief, \
water-like), "baroque relief" (large-scale rolling wave-like surface \
relief), "drapery" (heavy folded/draped 3D surface undulation, like cloth), \
"fracture-streamer" (thin dark crack-like line network over a confetti or \
solid body), "streaky/wispy" (elongated color streaks partially blended \
into a translucent or opaque base), "iridized/dichroic surface" (a thin \
rainbow/metallic sheen sitting ON TOP of the glass, visually separate from \
the body color), "smooth cathedral" (flat uniform transmissive color, no \
surface or body texture), "opalescent smooth" (milky uniform opacity, no \
structure), etc. -- these are EXAMPLES to anchor your vocabulary, not an \
exhaustive list; name new varieties you see that don't fit.

For EACH distinct variety you identify in this grid:
1. Give it a short name (your own words, structural, not a brand name).
2. Describe its visual structure in 1-2 sentences: is the pattern in the \
BODY (color/opacity variation within the glass) or the SURFACE (relief/\
sheen sitting on top)? What is the shape/scale of the pattern (dots, \
blobs, lines, waves, streaks, cells)?
3. List which tile numbers (#000 style) show this variety (a tile may show \
more than one variety at once -- e.g. body streaks AND surface ripple -- \
list it under both).

Answer in this exact format, one block per variety, nothing else:
VARIETY: <short name>
STRUCTURE: <1-2 sentence description>
TILES: <comma-separated tile numbers>
---
"""


def build_prompt(img_path, hints_path):
    hints_lines = open(hints_path).read().strip().split("\n")
    n = len(hints_lines)
    hints = "\n".join(hints_lines)
    return PROMPT_TMPL.format(img=os.path.abspath(img_path), n=n, hints=hints)


def main():
    model = "sonnet"
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for a in sys.argv[1:]:
        if a.startswith("--model="):
            model = a.split("=", 1)[1]
    pattern = args[0] if args else os.path.join(GRID_DIR, "batch*.jpg")
    batches = sorted(glob.glob(pattern))
    os.makedirs(RAW_DIR, exist_ok=True)
    for img_path in batches:
        bname = os.path.splitext(os.path.basename(img_path))[0]
        out_path = os.path.join(RAW_DIR, f"{bname}.txt")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            print("skip (exists)", out_path)
            continue
        hints_path = os.path.join(GRID_DIR, f"{bname}_hints.txt")
        prompt = build_prompt(img_path, hints_path)
        print("calling VLM for", bname, "...")
        out = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", "Read", "--model", model],
            capture_output=True, text=True, timeout=300,
        )
        if out.returncode != 0:
            print("ERROR", bname, out.stderr[-2000:])
            continue
        with open(out_path, "w") as f:
            f.write(out.stdout)
        print("wrote", out_path, len(out.stdout), "chars")


if __name__ == "__main__":
    main()
