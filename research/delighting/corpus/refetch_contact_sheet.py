#!/usr/bin/env python3
"""refetch_contact_sheet.py -- before/after visual verification grid for report 024.

For each of the 14 target ids: old contaminated pick (left) vs new -v2 fetch (right,
or a gray "UNRECOVERABLE" placeholder if no candidate passed). This is the "VERIFY
with your own eyes" artifact -- every recovered tile must visibly be a flat sheet
swatch, not a repeat of the eyeballing already done ad hoc during development.

Usage: python3 refetch_contact_sheet.py
Writes: ../results/corpus/refetch_before_after_contact_sheet.jpg
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
RESULTS_DIR = os.path.join(HERE, "..", "results", "corpus")
MANIFEST_PATH = os.path.join(RESULTS_DIR, "refetch_manifest.json")
QUARANTINE_PATH = os.path.join(RESULTS_DIR, "swatch_quarantine.json")
MAIN_CATALOG_DIR = os.path.join(REPO_ROOT, "frontend", "public", "assets", "catalog_images")

TILE = 220
PAD = 10
LABEL_H = 34
ROW_H = TILE + LABEL_H + PAD


def load_tile(path, size=TILE):
    im = Image.open(path).convert("RGB")
    im.thumbnail((size, size))
    canvas = Image.new("RGB", (size, size), (60, 60, 60))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return canvas


def placeholder(text, size=TILE, bg=(40, 40, 40), fg=(230, 90, 90)):
    canvas = Image.new("RGB", (size, size), bg)
    d = ImageDraw.Draw(canvas)
    d.text((10, size // 2 - 10), text, fill=fg)
    return canvas


def main():
    manifest = json.load(open(MANIFEST_PATH))
    quarantine = json.load(open(QUARANTINE_PATH))
    reason_by_id = {it["id"]: it["reason"] for it in quarantine["items"] if it.get("id")}

    recovered_by_id = {r["old_id"]: r for r in manifest["recovered"]}
    unrecoverable_by_id = {u["id"]: u for u in manifest["unrecoverable"]}
    all_ids = sorted(set(recovered_by_id) | set(unrecoverable_by_id))

    n = len(all_ids)
    W = PAD + 340 + PAD + TILE + PAD + TILE + PAD  # label col + old + new
    H = PAD + n * ROW_H + PAD

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 11)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    sheet = Image.new("RGB", (W, H), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    y = PAD
    for rid in all_ids:
        old_file = rid + ".jpg"
        old_path = os.path.join(MAIN_CATALOG_DIR, old_file)
        label_x = PAD
        old_x = PAD + 340 + PAD
        new_x = old_x + TILE + PAD

        d.text((label_x, y), rid, fill=(230, 230, 230), font=font)
        d.text((label_x, y + 18), f"quarantine: {reason_by_id.get(rid, [])}", fill=(160, 160, 160), font=font_small)

        if os.path.exists(old_path):
            sheet.paste(load_tile(old_path), (old_x, y + LABEL_H))
        else:
            sheet.paste(placeholder("missing"), (old_x, y + LABEL_H))
        d.text((old_x, y), "OLD (contaminated)", fill=(230, 140, 140), font=font_small)

        if rid in recovered_by_id:
            r = recovered_by_id[rid]
            new_path = os.path.join(MAIN_CATALOG_DIR, r["new_file"])
            sheet.paste(load_tile(new_path), (new_x, y + LABEL_H))
            caveat = " [CAVEAT]" if r["human_verification_caveat"] else ""
            d.text((new_x, y), f"NEW v2: pos {r['image_position_picked']} {r['flagger_verdict']}{caveat}",
                   fill=(140, 230, 160), font=font_small)
        else:
            sheet.paste(placeholder("UNRECOVERABLE"), (new_x, y + LABEL_H))
            d.text((new_x, y), "no candidate passed", fill=(230, 90, 90), font=font_small)

        y += ROW_H

    out_path = os.path.join(RESULTS_DIR, "refetch_before_after_contact_sheet.jpg")
    sheet.save(out_path, "JPEG", quality=88)
    print(f"wrote {out_path} ({W}x{H}, {n} rows)")


if __name__ == "__main__":
    main()
