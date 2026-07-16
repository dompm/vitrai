"""050 REAL qualitative board: run relief auto-detection on a spread of real
corpus sheet photos + the CTO's difficult sheet, and show for each:
  photo | detected category + knob settings | resulting procedural normal | shade

Raw corpus images are LOCAL-ONLY; this writes only a downscaled JPEG board.
"""
import os, json, sys, glob
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import detect_relief as D
import relief_presets as RP
from preview_bank import shade

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "results", "050"))
ASSETS029 = os.path.abspath(os.path.join(HERE, "..", "reports", "assets_029"))
CTO = os.path.expanduser("~/Downloads/PXL_20260508_165112222 (1).jpg")


def gather():
    imgs = []
    for pat in ("corpus_*.jpg", "wild_sheets_*.jpg", "wild_panel_*.jpg"):
        imgs += sorted(glob.glob(os.path.join(ASSETS029, pat)))
    if os.path.exists(CTO):
        imgs.append(CTO)
    return imgs


def center_crop_square(im, s=256):
    w, h = im.size
    m = min(w, h)
    im = im.crop(((w - m) // 2, (h - m) // 2, (w + m) // 2, (h + m) // 2))
    return im.resize((s, s), Image.LANCZOS)


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "haiku"
    imgs = gather()
    results = []
    for p in imgs:
        try:
            r = D.detect(p, use_vlm_knobs=False, model=model)
        except Exception as e:
            print("FAIL", os.path.basename(p), e); continue
        results.append((p, r))
        print(f"{os.path.basename(p)[:34]:34s} -> {r['category']:12s} "
              f"amp={r['amplitude']:6s} scale={r['feature_scale']:6s}")

    # board
    cell = 220; pad = 10; cols = 4
    labels = ["real photo", "detected", "procedural normal", "relief shade"]
    rowh = cell + pad
    top = 26
    W = pad + cols * (cell + pad)
    Hh = top + len(results) * rowh + pad
    sheet = Image.new("RGB", (W, Hh), (18, 20, 24))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 12)
        fsm = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 11)
    except Exception:
        font = fsm = ImageFont.load_default()
    for j, lab in enumerate(labels):
        d.text((pad + j * (cell + pad) + 4, 6), lab, fill=(180, 188, 200), font=fsm)
    for i, (p, r) in enumerate(results):
        y = top + i * rowh + pad
        photo = center_crop_square(Image.open(p).convert("RGB"), cell)
        sheet.paste(photo, (pad, y))
        cat = r["category"]
        ang = r.get("angle_deg")
        nrm, meta = RP.make_normal(cat, size=cell, seed=3,
                                   amplitude=r["amplitude"],
                                   feature_scale=r["feature_scale"],
                                   angle_deg=ang)
        h, amp = RP.make_height(cat, size=cell, seed=3, amplitude=r["amplitude"],
                                feature_scale=r["feature_scale"], angle_deg=ang)
        nimg = Image.fromarray((nrm * 255).astype(np.uint8))
        simg = Image.fromarray((np.clip(shade(h, nrm), 0, 1) * 255).astype(np.uint8))
        # detected text panel
        panel = Image.new("RGB", (cell, cell), (26, 30, 36))
        pd = ImageDraw.Draw(panel)
        name = os.path.basename(p)
        pd.text((8, 10), name[:26], fill=(150, 160, 172), font=fsm)
        pd.text((8, 44), cat, fill=(140, 200, 255), font=font)
        pd.text((8, 66), f"amplitude: {r['amplitude']}", fill=(220, 225, 232), font=fsm)
        pd.text((8, 84), f"feat scale: {r['feature_scale']}", fill=(220, 225, 232), font=fsm)
        if ang is not None:
            pd.text((8, 102), f"angle: {ang:.0f}deg", fill=(220, 225, 232), font=fsm)
        sheet.paste(panel, (pad + (cell + pad), y))
        sheet.paste(nimg, (pad + 2 * (cell + pad), y))
        sheet.paste(simg.convert("RGB"), (pad + 3 * (cell + pad), y))
    path = os.path.join(OUT, "board_real_detection.jpg")
    sheet.save(path, quality=88)
    print("wrote", path, sheet.size)
    json.dump([{"file": os.path.basename(p), **{k: v for k, v in r.items() if k != "features"}}
               for p, r in results],
              open(os.path.join(OUT, "real_detection.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
