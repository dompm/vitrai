#!/usr/bin/env python3
"""Track C: glass-class prior from a real VLM (the `claude` CLI as subprocess).

Multiple-choice ONLY -- another team validated empirically that small models
answer A/B/C/D reliably but collapse on numeric regression. Keep call volume
low: one call per photo, cached in .vlm_cache.json next to this file.

Validated on the two benchmark photos (2026-07): amber swatch -> C
(cathedral-clear), wispy sheet -> B (wispy). Both correct, ~15 s/call on haiku.
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".vlm_cache.json")

LETTER_TO_CLASS = {
    "A": "opalescent",
    "B": "wispy",
    "C": "cathedral-clear",
    "D": "dark-opaque",
}

PROMPT = """Read the image file at {path} and look at it. It is a photo of a \
stained-glass sheet held against a light source. Classify the glass into exactly \
one category:
A) opalescent - milky/opal glass, diffuses light strongly, background not visible through it
B) wispy - mostly white/light translucent glass with wispy streaks, partly diffusing
C) cathedral-clear - transparent colored glass, background clearly visible through it, often textured
D) dark-opaque - very dark glass, transmits little light
Reply with ONLY the single letter (A, B, C or D)."""


def classify_glass(image_path, model="haiku", timeout=120):
    image_path = os.path.abspath(image_path)
    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE))
        except Exception:
            cache = {}
    key = f"{image_path}:{os.path.getmtime(image_path):.0f}"
    if key in cache:
        return cache[key]

    out = subprocess.run(
        ["claude", "-p", PROMPT.format(path=image_path),
         "--allowedTools", "Read", "--model", model],
        capture_output=True, text=True, timeout=timeout,
    )
    ans = out.stdout.strip().rstrip(".").upper()[-1:]  # tolerate "Answer: B"
    cls = LETTER_TO_CLASS.get(ans)
    if cls is None:
        raise RuntimeError(f"VLM gave unparseable answer {out.stdout!r} for {image_path}")
    cache[key] = cls
    with open(CACHE, "w") as f:
        json.dump(cache, f, indent=1)
    return cls


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        print(p, "->", classify_glass(p))
