#!/usr/bin/env python3
"""Report 032 WP-A acceptance: does a fresh VLM read the reworked streaky
recipes as STREAKY (taxon T12), reversing report 031's misclassifications
(streaky-fine-texture -> ring mottle T7; wispy-white -> smooth opal T14)?

One `claude` CLI call per rendered photo (haiku), same subprocess pattern as
vlm_classify.py. Blind to the intended label. Pass image paths as argv.
"""
import os, subprocess, sys

L2T = {"A": "T12-streaky", "B": "T7-ring-mottle", "C": "T14-smooth-opal", "D": "T2-cathedral-textured"}
PROMPT = """Read the image file at {path} and look at it. It is a photo of a \
stained-glass sheet against a light source. Classify its PATTERN structure into \
exactly one category:
A) streaky - elongated, blended color streaks running in a direction (rolled/pulled glass)
B) ring-mottle - dense overlapping round/oval blobs, no direction
C) smooth-opal - uniform milky diffusion, no streaks, no blobs
D) cathedral-textured - transparent, fine even surface pebbling, no streaks
Reply with ONLY the single letter (A, B, C or D)."""


def classify(path, model="haiku", timeout=150):
    path = os.path.abspath(path)
    out = subprocess.run(
        ["claude", "-p", PROMPT.format(path=path), "--allowedTools", "Read", "--model", model],
        capture_output=True, text=True, timeout=timeout)
    ans = out.stdout.strip().rstrip(".").upper()[-1:]
    return L2T.get(ans, f"UNPARSEABLE({out.stdout!r})")


if __name__ == "__main__":
    print("recipe(intended)                     -> VLM taxon")
    for p in sys.argv[1:]:
        recipe = os.path.basename(os.path.dirname(p)).split("__")[0]
        v = classify(p)
        ok = "PASS" if v == "T12-streaky" else "----"
        print(f"{recipe:28s} {ok} -> {v}")
