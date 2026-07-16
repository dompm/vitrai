"""Characterise the category-detection ceiling on the HOLDOUT: an improved,
ripple-de-biased prompt, on haiku vs sonnet. Reports fine 6-way + coarse
(flat/isotropic/directional/wavy) accuracy."""
import os, json, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
import detect_relief as D
from score050 import collect, COARSE

CAT_LETTERS = D.CAT_LETTERS
PROMPT2 = """Read the image file at {path} and look at it closely. It is a photo \
of one sheet of art glass. Judge ONLY the SURFACE TEXTURE relief, not the colour. \
Decide FIRST whether the texture is DIRECTIONAL (features clearly line up and run \
one way -- parallel streaks/reeds/pulls) or ISOTROPIC (features look the same in \
all directions -- an all-over field of bumps/cells/seeds with no single direction). \
Only choose ripple if the direction is unmistakable. Then pick exactly one:
A) smooth - flat/float/cast, clean surface, essentially no relief
B) hammered - ISOTROPIC all-over field of small rounded dimples/cells (classic cathedral)
C) granite - ISOTROPIC dense fine sandy/stippled tooth, busier and finer than hammered
D) seedy - ISOTROPIC scattered discrete round bumps/seeds/bubbles on a soft surface
E) ripple - DIRECTIONAL parallel streaks/reeds/pulled lines running one way
F) rolling_wave - large coarse smooth waves/folds, centimetre-scale undulation
Reply with ONLY the single letter (A-F)."""


def ask(path, model):
    path = os.path.abspath(path)
    out = subprocess.run(["claude", "-p", PROMPT2.format(path=path),
                          "--allowedTools", "Read", "--model", model],
                         capture_output=True, text=True, timeout=180)
    return CAT_LETTERS.get(out.stdout.strip().rstrip(".").upper()[-1:])


def main():
    photos = os.path.abspath(os.path.join(HERE, "..", "results", "050", "photos_v2"))
    rows = [r for r in collect(photos) if r["split"] == "holdout"]
    for model in sys.argv[1:] or ["sonnet"]:
        fine = coarse = 0
        conf = []
        for r in rows:
            det = ask(r["file"], model)
            ok = det == r["gt_category"]
            cok = COARSE[det] == COARSE[r["gt_category"]]
            fine += ok; coarse += cok
            conf.append((r["gt_category"], det, "OK" if ok else "x"))
        n = len(rows)
        print(f"\n[{model}] fine {fine}/{n}={fine/n:.2f}  coarse {coarse}/{n}={coarse/n:.2f}")
        for g, d, s in conf:
            print(f"   {g:12s} -> {d:12s} {s}")


if __name__ == "__main__":
    main()
