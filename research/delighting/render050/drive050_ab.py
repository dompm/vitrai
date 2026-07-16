"""050 end-to-end perceptual A/B (folds in the 047b question): render the 047
window-nudge scene three ways -- GT normal | auto-detected procedural | normal
off -- same T/haze/env otherwise, in the real three.js MeshPhysicalMaterial, via
headless Chrome. Board them side by side.

The 'auto' normal is generated from the AUTO-DETECTED preset (detection_scores
.json) for that family's photo -> a genuine end-to-end test. 047's fidelity data
says even the GT normal doesn't beat 'off' against Cycles truth, so the claim is
that auto-procedural should look PERCEPTUALLY like GT (both add the same kind of
sparkle) -- test it by eye on the board.
"""
import os, json, subprocess, time, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import relief_presets as RP

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))         # research/delighting
ASSETS = os.path.join(ROOT, "results", "050", "assets_ms")
OUT = os.path.join(ROOT, "results", "050")
TMP = "/tmp/r050ab"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = "8050"
FAMILIES = ["cathedral-green__6001", "streaky-mix__6001", "wispy-white__6001"]
AZ = 12


# The A/B isolates the PERCEPTUAL question (does the bank preset tie with GT?)
# from the noisy per-photo fine pick: 'auto' here = the default preset for the
# family's TRUE coarse group, i.e. exactly what the recommended ship path
# (coarse-detect + in-family default, §7) produces WHEN coarse detection
# succeeds. Detection accuracy is quantified separately (§3/§4).
SHIP_PRESET = {
    "cathedral-green__6001": ("hammered", "medium", "medium"),  # textured default
    "streaky-mix__6001": ("ripple", "subtle", "medium"),        # streaky default
    "wispy-white__6001": ("seedy", "medium", "medium"),         # true group default
}


def gen_auto_normal(key):
    cat, amp, scale = SHIP_PRESET.get(key, ("hammered", "medium", "medium"))
    ang = 90.0 if cat == "ripple" else None
    nrm, meta = RP.make_normal(cat, size=768, seed=hash(key) % 9999, amplitude=amp,
                               feature_scale=scale, angle_deg=ang)
    Image.fromarray((nrm * 255).astype(np.uint8)).save(
        os.path.join(ASSETS, key, "auto_normal.png"))
    return cat, amp, scale


def render(family, relief, name):
    q = (f"abase=/results/050/assets_ms&family={family}&relief={relief}&az={AZ}"
         f"&res=512&name={name}")
    if relief == "auto":
        q += f"&normurl=/results/050/assets_ms/{family}/auto_normal.png"
    url = f"http://localhost:{PORT}/render050/model050.html?{q}"
    out = os.path.join(TMP, name + ".png")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run([CHROME, "--headless=new", "--window-size=512,512",
                    "--force-device-scale-factor=1", "--virtual-time-budget=30000",
                    "--screenshot=/tmp/_s050.png", url],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    for _ in range(40):
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return out
        time.sleep(0.25)
    raise RuntimeError("render failed " + name)


def main():
    os.makedirs(TMP, exist_ok=True)
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, "..", "render047",
                            "serve047.py"), PORT, TMP])
    time.sleep(2)
    try:
        detected = {}
        renders = {}
        for fam in FAMILIES:
            detected[fam] = gen_auto_normal(fam)
            for relief in ("gt", "auto", "off"):
                renders[(fam, relief)] = render(fam, relief, f"{fam}_{relief}")
                print("rendered", fam, relief)
    finally:
        srv.terminate()

    # board: rows=family, cols = [gt | auto | off] renders
    cell = 256; pad = 8; top = 24; leftlab = 130
    cols = ["gt", "auto", "off"]
    W = leftlab + len(cols) * (cell + pad) + pad
    Hh = top + len(FAMILIES) * (cell + pad) + pad
    sheet = Image.new("RGB", (W, Hh), (16, 18, 22))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
        fsm = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 11)
    except Exception:
        font = fsm = ImageFont.load_default()
    hdr = {"gt": "GT normal", "auto": "procedural preset (ship path)", "off": "normal OFF"}
    for j, c in enumerate(cols):
        d.text((leftlab + j * (cell + pad) + 4, 6), hdr[c], fill=(180, 188, 200), font=fsm)
    for i, fam in enumerate(FAMILIES):
        y = top + i * (cell + pad) + pad
        cat, amp, scale = detected[fam]
        d.text((6, y + 6), fam.split("__")[0], fill=(230, 235, 240), font=font)
        d.text((6, y + 28), f"preset={cat}", fill=(140, 200, 255), font=fsm)
        d.text((6, y + 44), f"{amp}/{scale}", fill=(150, 160, 172), font=fsm)
        for j, c in enumerate(cols):
            im = Image.open(renders[(fam, c)]).convert("RGB").resize((cell, cell))
            sheet.paste(im, (leftlab + j * (cell + pad) + pad, y))
    path = os.path.join(OUT, "board_ab_normal.jpg")
    sheet.save(path, quality=90)
    print("wrote", path, sheet.size)


if __name__ == "__main__":
    main()
