#!/usr/bin/env python3
"""Report 037 item E acceptance: does a fresh VLM independently read each of
the 4 new taxa recipes (item C) as its intended taxon, blind to the label?
Same one-`claude`-CLI-call-per-photo pattern as report 032's
vlm_legibility_032.py. Inputs are the uniform-backlight --validate renders
(the HARDEST case for pattern legibility -- no directional lighting to help,
same choice 032 made). Pass image paths as argv.
"""
import os, subprocess, sys

L2T = {
    "A": "T3-baroque-rolling-wave",
    "B": "T9-fracture-streamer",
    "C": "T10-confetti-shard",
    "D": "T7-ring-mottle",
    "E": "none of these (plain/other)",
}
EXPECT = {
    "baroque-rolling-wave": "T3-baroque-rolling-wave",
    "fracture-streamer": "T9-fracture-streamer",
    "confetti-shard": "T10-confetti-shard",
    "ring-mottle": "T7-ring-mottle",
}
PROMPT = """Read the image file at {path} and look at it. It is a photo of a \
stained-glass sheet against a light source. Classify its PATTERN structure into \
exactly one category:
A) baroque/rolling-wave - large-scale smooth rolling SURFACE relief (like gentle \
waves or dunes), no fine texture, no color pattern
B) fracture-streamer - thin dark or colored branching crack-like lines running \
through an otherwise fairly clear/plain body, like a network of cracks or veins
C) confetti-shard - flat angular non-overlapping pieces of DIFFERENT colors, like \
a mosaic or stained-glass patchwork of colored tiles
D) ring-mottle - dense overlapping round or oval blobs/spots of a similar color, \
no sharp angular edges
E) none of the above / plain glass with no distinctive pattern
Reply with ONLY the single letter (A, B, C, D or E)."""


def classify(path, model="haiku", timeout=150):
    path = os.path.abspath(path)
    out = subprocess.run(
        ["claude", "-p", PROMPT.format(path=path), "--allowedTools", "Read", "--model", model],
        capture_output=True, text=True, timeout=timeout)
    ans = out.stdout.strip().rstrip(".").upper()[-1:]
    return L2T.get(ans, f"UNPARSEABLE({out.stdout!r})")


if __name__ == "__main__":
    print("recipe(intended)                     -> VLM taxon")
    n_pass = 0
    paths = sys.argv[1:]
    for p in paths:
        recipe = os.path.splitext(os.path.basename(p))[0]
        v = classify(p)
        expect = EXPECT.get(recipe)
        ok = "PASS" if v == expect else "----"
        if ok == "PASS":
            n_pass += 1
        print(f"{recipe:28s} {ok} -> {v}")
    print(f"\n{n_pass}/{len(paths)} PASS")
