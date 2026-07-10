#!/usr/bin/env python3
"""Iteration 029: VLM realism critique of synthetic renders vs real glass photos.

Blind, unlabeled pairwise/triplet critique prompt (`claude` CLI subprocess, following
`vlm_classify.py`'s subprocess pattern but free-text instead of multiple-choice). Every
call uses the SAME prompt template regardless of whether the images are actually
synthetic-vs-real, real-vs-real (calibration control), or a 3-way triplet -- this lets
the aggregation step measure the VLM's false-positive rate on real-vs-real pairs using
the identical instrument used on the diagnostic ours-vs-real pairs.

Usage: python3 vlm_realism_critique.py            # runs all calls in CALLS below
       python3 vlm_realism_critique.py <call_id>   # runs just one (debugging)
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OURS = os.path.join(HERE, "results/vlm_realism_029/downscaled/ours")
CORPUS = os.path.join(HERE, "results/vlm_realism_029/downscaled/corpus")
WILD = os.path.join(HERE, "results/vlm_realism_029/raw_wild")
OUTDIR = os.path.join(HERE, "results/vlm_realism_029/vlm_raw")
os.makedirs(OUTDIR, exist_ok=True)

MODEL = "sonnet"
TIMEOUT = 280

PROMPT_2 = """You are critiquing photographs of stained/art glass sheets for PHYSICAL \
REALISM -- the goal is to catch subtle cues that distinguish a REAL photograph from a \
computer-rendered (synthetic) image.

Read image 1 at: {p1}
Read image 2 at: {p2}

SET ASIDE these differences -- they are already known and NOT what I'm asking about, do \
not mention them:
- Different background/room content behind or around the glass
- Different sheet size, presence of price/SKU labels, tape, or hands
- Different camera angle, crop, or image resolution
- Different overall color of glass (different glass color/product is expected)

FOCUS ONLY on physical/optical realism cues, in these categories:
1. Front-surface reflections/specularity -- is there a plausible reflected highlight or \
environment veil on the glass's near surface? Where, how sharp/soft, how strong?
2. Texture statistics -- grain, waviness, hammer/ripple relief: does the fine texture \
look like real rolled/blown glass noise, or too smooth / too regular / obviously \
procedural?
3. Color depth & translucency gradients -- does color vary continuously with local \
thickness/texture the way real glass does, or does it look like a flat/uniform tint \
with a haze overlay?
4. Edge/rim effects -- at the sheet's physical edge, is there a plausible \
thickness-darkened rim, chip, or refraction effect?
5. Lighting plausibility -- does the apparent light source (backlight, room light) look \
physically consistent (falloff, direction, softness), or is it suspiciously uniform/\
flat/single-source?
6. Noise & camera optics -- is there sensor noise, depth-of-field falloff, chromatic \
aberration at high-contrast edges, or exposure roll-off/highlight clipping consistent \
with a real camera? Or does the image look "too clean"?

For EACH observation: name which image (1 or 2) it applies to, which category, and \
describe the SPECIFIC visual evidence (not a vibe) -- e.g. "image 1's right edge has a \
hard 2px color fringe" not "image 1 looks fake."

Then answer explicitly: Based on ALL evidence, which image (if either) do you believe is \
a computer-rendered synthetic image rather than a real photograph, and why? If you \
believe both are real, or you're unsure, say so plainly -- do not force a guess to be \
helpful.

Keep your answer under 300 words. Use this exact structure:
OBSERVATIONS:
- ...
VERDICT: [Image 1 synthetic / Image 2 synthetic / Both appear real / Uncertain] -- <one \
sentence reason>"""

PROMPT_3 = """You are critiquing photographs of stained/art glass sheets for PHYSICAL \
REALISM -- the goal is to catch subtle cues that distinguish a REAL photograph from a \
computer-rendered (synthetic) image.

Read image 1 at: {p1}
Read image 2 at: {p2}
Read image 3 at: {p3}

SET ASIDE these differences -- they are already known and NOT what I'm asking about, do \
not mention them:
- Different background/room content behind or around the glass
- Different sheet size, presence of price/SKU labels, tape, or hands
- Different camera angle, crop, or image resolution
- Different overall color of glass (different glass color/product is expected)

FOCUS ONLY on physical/optical realism cues, in these categories:
1. Front-surface reflections/specularity -- is there a plausible reflected highlight or \
environment veil on the glass's near surface? Where, how sharp/soft, how strong?
2. Texture statistics -- grain, waviness, hammer/ripple relief: does the fine texture \
look like real rolled/blown glass noise, or too smooth / too regular / obviously \
procedural?
3. Color depth & translucency gradients -- does color vary continuously with local \
thickness/texture the way real glass does, or does it look like a flat/uniform tint \
with a haze overlay?
4. Edge/rim effects -- at the sheet's physical edge, is there a plausible \
thickness-darkened rim, chip, or refraction effect?
5. Lighting plausibility -- does the apparent light source (backlight, room light) look \
physically consistent (falloff, direction, softness), or is it suspiciously uniform/\
flat/single-source?
6. Noise & camera optics -- is there sensor noise, depth-of-field falloff, chromatic \
aberration at high-contrast edges, or exposure roll-off/highlight clipping consistent \
with a real camera? Or does the image look "too clean"?

For EACH observation: name which image (1, 2 or 3) it applies to, which category, and \
describe the SPECIFIC visual evidence (not a vibe).

Then answer explicitly: Based on ALL evidence, which image(s), if any, do you believe are \
computer-rendered synthetic rather than real photographs, and why? If you're unsure, say \
so plainly -- do not force a guess to be helpful.

Keep your answer under 350 words. Use this exact structure:
OBSERVATIONS:
- ...
VERDICT: [which image(s) synthetic, or "all appear real", or "uncertain"] -- <one \
sentence reason>"""


def P(*parts):
    return os.path.join(*parts)


# (call_id, kind, truth_label, [image paths...])
# truth_label documents ground truth for aggregation, NOT sent to the model:
#   "ours_vs_real" = image1 is our synthetic render, others real
#   "real_vs_real" = calibration control, all real (same or cross corpus)
#   "ours_vs_real_vs_real" = triplet, image1 synthetic, 2/3 real
CALLS = [
    # --- ours vs corpus (diagnostic) ---
    ("c01_amber_v_corpus", "ours_vs_real",
     [P(OURS, "cathedral-amber.jpg"), P(CORPUS, "bullseye-0011370050f1010.jpg")]),
    ("c02_red_v_corpus", "ours_vs_real",
     [P(OURS, "cathedral-red.jpg"), P(CORPUS, "bullseye-0041110000ffull.jpg")]),
    ("c03_darkopaque_v_corpus", "ours_vs_real",
     [P(OURS, "dark-opaque.jpg"), P(CORPUS, "bullseye-0001000047f1010.jpg")]),
    ("c04_wispy_v_corpus", "ours_vs_real",
     [P(OURS, "wispy-white.jpg"), P(CORPUS, "bullseye-0021000000f1010.jpg")]),
    ("c05_satopal_v_corpus", "ours_vs_real",
     [P(OURS, "saturated-opalescent.jpg"), P(CORPUS, "oceanside-of23072s.jpg")]),
    ("c06_streakymix_v_corpus", "ours_vs_real",
     [P(OURS, "streaky-mix.jpg"), P(CORPUS, "bullseye-0023050030f1010.jpg")]),
    ("c07_darkruby_v_corpus", "ours_vs_real",
     [P(OURS, "dark-ruby.jpg"), P(CORPUS, "wissmach-wblacki.jpg")]),
    # --- ours vs wild (diagnostic) ---
    ("w01_amber_v_wild", "ours_vs_real",
     [P(OURS, "cathedral-amber.jpg"), P(WILD, "sheets_waterglass_pair.jpg")]),
    ("w02_darktextured_v_wild", "ours_vs_real",
     [P(OURS, "dark-textured.jpg"), P(WILD, "sheets_shelf.jpg")]),
    ("w03_streakyfine_v_wild", "ours_vs_real",
     [P(OURS, "streaky-fine-texture.jpg"), P(WILD, "sheets_handblown.jpg")]),
    ("w04_wispy_v_wild", "ours_vs_real",
     [P(OURS, "wispy-white.jpg"), P(WILD, "panel_tungsten_backlit.jpg")]),
    ("w05_darkopaque_v_wild", "ours_vs_real",
     [P(OURS, "dark-opaque.jpg"), P(WILD, "sheets_shelf.jpg")]),
    # --- corpus vs wild (both real, different capture source -- secondary calibration) ---
    ("x01_corpus_v_wild", "real_vs_real",
     [P(CORPUS, "bullseye-0014260030f1010.jpg"), P(WILD, "sheets_waterglass_pair.jpg")]),
    ("x02_corpus_v_wild", "real_vs_real",
     [P(CORPUS, "oceanside-of22272s.jpg"), P(WILD, "panel_reflected_vs_transmitted.jpg")]),
    # --- same-set self-critique CALIBRATION controls (both real, same source) ---
    ("cal01_corpus_v_corpus", "real_vs_real",
     [P(CORPUS, "bullseye-0011370050f1010.jpg"), P(CORPUS, "bullseye-0041110000ffull.jpg")]),
    ("cal02_corpus_v_corpus", "real_vs_real",
     [P(CORPUS, "bullseye-0021000000f1010.jpg"), P(CORPUS, "bullseye-0023050030f1010.jpg")]),
    ("cal03_wild_v_wild", "real_vs_real",
     [P(WILD, "sheets_shelf.jpg"), P(WILD, "sheets_handblown.jpg")]),
    ("cal04_wild_v_wild", "real_vs_real",
     [P(WILD, "panel_lightbox.jpg"), P(WILD, "panel_green_bg_distortion.jpg")]),
    ("cal05_corpus_v_corpus_xclass", "real_vs_real",
     [P(CORPUS, "oceanside-of23072s.jpg"), P(CORPUS, "wissmach-wblacki.jpg")]),
    # --- triplets: ours vs corpus vs wild ---
    ("t01_cathedral_blue", "ours_vs_real_vs_real",
     [P(OURS, "cathedral-blue.jpg"), P(CORPUS, "bullseye-0014140051f1010.jpg"),
      P(WILD, "sheets_waterglass_pair.jpg")]),
    ("t02_dark", "ours_vs_real_vs_real",
     [P(OURS, "dark-ruby.jpg"), P(CORPUS, "wissmach-wblacki.jpg"),
      P(WILD, "panel_tungsten_backlit.jpg")]),
    ("t03_opalescent", "ours_vs_real_vs_real",
     [P(OURS, "saturated-opalescent.jpg"), P(CORPUS, "oceanside-of23072s.jpg"),
      P(WILD, "panel_lightbox.jpg")]),
    ("t04_wispy_streaky", "ours_vs_real_vs_real",
     [P(OURS, "streaky-mix.jpg"), P(CORPUS, "bullseye-0023050030f1010.jpg"),
      P(WILD, "sheets_handblown.jpg")]),
]


def run_call(call_id, truth_label, paths):
    out_path = P(OUTDIR, call_id + ".json")
    if os.path.exists(out_path):
        print(f"[skip, cached] {call_id}")
        return
    prompt = (PROMPT_2 if len(paths) == 2 else PROMPT_3).format(
        **{f"p{i+1}": p for i, p in enumerate(paths)})
    t0 = time.time()
    print(f"[running] {call_id} ({len(paths)} imgs, truth={truth_label}) ...")
    try:
        out = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", "Read", "--model", MODEL],
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        dt = time.time() - t0
        record = {
            "call_id": call_id,
            "truth_label": truth_label,
            "images": paths,
            "model": MODEL,
            "elapsed_s": round(dt, 1),
            "returncode": out.returncode,
            "stdout": out.stdout.strip(),
            "stderr": out.stderr.strip()[-2000:],
        }
    except subprocess.TimeoutExpired as e:
        record = {
            "call_id": call_id, "truth_label": truth_label, "images": paths,
            "model": MODEL, "elapsed_s": TIMEOUT, "returncode": -1,
            "stdout": (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
            "stderr": "TIMEOUT",
        }
    with open(out_path, "w") as f:
        json.dump(record, f, indent=2)
    print(f"[done] {call_id} in {record['elapsed_s']}s (rc={record['returncode']})")


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for call_id, truth_label, paths in CALLS:
        if only and call_id != only:
            continue
        run_call(call_id, truth_label, paths)
