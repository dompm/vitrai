#!/usr/bin/env python3
"""validate_maintainer_cases.py -- swatch_picker acceptance test #1 (report 035).

Fetches the two maintainer-supplied SGE product galleries live (politely, ~1 req/s,
disk-cached via fetch_gallery.py), runs swatch_picker.pick() on each with the
product's description text, and asserts the pick matches the maintainer's stated
correct answer:
  - uro-by-yough-clear-granite-ripple-fusible-glass-96-coe -> correct = image 4
  - yough-steel-grey-opal                                   -> correct = image 3

Writes a score-table panel per case (all candidates + scores overlaid, downscaled)
to ../results/corpus/swatch_picker_maintainer_{1,2}.jpg and a summary JSON to
../results/corpus/swatch_picker_maintainer_validation.json.
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

import fetch_gallery
from swatch_picker import pick

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")
CACHE_DIR = os.path.join(RESULTS_DIR, "swatch_picker_cache")

CASES = [
    {
        "name": "uro-by-yough-clear-granite-ripple",
        "url": "https://www.stainedglassexpress.com/products/uro-by-yough-clear-granite-ripple-fusible-glass-96-coe",
        "correct_position": 4,
        "note": "1st=customer photo (finger), 2nd/3rd=comparison shots vs Oceanside Granite",
    },
    {
        "name": "yough-steel-grey-opal",
        "url": "https://www.stainedglassexpress.com/en-ca/products/yough-steel-grey-opal",
        "correct_position": 3,
        "note": "description: 'First and third photos are backlit'; 1st is a blurry macro crop, "
                "3rd is the sharp full-sheet backlit shot",
    },
]

TILE = 260
PAD = 12
LABEL_H = 90
ROW_H = TILE + LABEL_H + PAD


def _font(size=14):
    for path in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def build_panel(case, result, images, out_path):
    n = len(images)
    W = n * (TILE + PAD) + PAD
    H = ROW_H + 50
    canvas = Image.new("RGB", (W, H), (24, 24, 24))
    d = ImageDraw.Draw(canvas)
    f_title = _font(18)
    f_body = _font(13)
    picked = result["pick"]
    d.text((PAD, 8), f"{case['name']}  --  maintainer-correct = position {case['correct_position']}"
                      f"  --  picker chose = position {(picked + 1) if picked is not None else 'NONE'}"
                      f"  {'OVERRIDE' if result['override'] else ''}",
           fill=(255, 255, 255), font=f_title)
    for i, path in enumerate(images):
        x = PAD + i * (TILE + PAD)
        y = 44
        im = Image.open(path).convert("RGB")
        im.thumbnail((TILE, TILE))
        border = (60, 200, 90) if i == picked else (90, 90, 90)
        if picked is not None and (i + 1) == case["correct_position"] and i != picked:
            border = (220, 60, 60)
        canvas_tile = Image.new("RGB", (TILE, TILE), (45, 45, 45))
        canvas_tile.paste(im, ((TILE - im.width) // 2, (TILE - im.height) // 2))
        canvas.paste(canvas_tile, (x, y))
        d.rectangle([x - 2, y - 2, x + TILE + 2, y + TILE + 2], outline=border, width=4)
        s = result["scores"][i]
        c = s["components"]
        lines = [
            f"pos {i+1}  final={s['final_score']:.3f}",
            f"audit={c['audit']:.2f} hand={c['hand']:.2f}",
            f"seam={c['seam']:.2f} cover={c['coverage']:.2f}",
            f"text_adj={s['text_adjustment']:+.2f}",
        ]
        ty = y + TILE + 4
        for line in lines:
            d.text((x, ty), line, fill=(230, 230, 230), font=f_body)
            ty += 16
    canvas.save(out_path, quality=88)


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    summary = {"cases": []}
    all_pass = True
    for i, case in enumerate(CASES, 1):
        print(f"fetching {case['name']} ...")
        g = fetch_gallery.fetch_gallery(case["url"], CACHE_DIR)
        text = g["title"] + ". " + g["body_html"]
        result = pick(g["images"], text=text)
        picked = result["pick"]
        correct = picked is not None and (picked + 1) == case["correct_position"]
        all_pass = all_pass and correct
        margin = None
        if result["scores"]:
            sorted_scores = sorted((s["final_score"] for s in result["scores"]), reverse=True)
            margin = sorted_scores[0] - (sorted_scores[1] if len(sorted_scores) > 1 else 0.0)
        print(f"  n_images={len(g['images'])}  pick={picked+1 if picked is not None else None}  "
              f"correct={correct}  margin={margin}")
        out_path = os.path.join(RESULTS_DIR, f"swatch_picker_maintainer_{i}.jpg")
        build_panel(case, result, g["images"], out_path)
        summary["cases"].append({
            "name": case["name"], "product_url": case["url"],
            "correct_position": case["correct_position"],
            "picked_position": (picked + 1) if picked is not None else None,
            "correct": correct, "margin": margin, "override": result["override"],
            "text_notes": result["text_notes"],
            "scores": [{"position": s["position"], "final_score": s["final_score"],
                        "components": s["components"]} for s in result["scores"]],
            "panel": os.path.basename(out_path),
        })
    summary["all_pass"] = all_pass
    out_json = os.path.join(RESULTS_DIR, "swatch_picker_maintainer_validation.json")
    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nALL PASS: {all_pass}")
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
