#!/usr/bin/env python3
"""Report 051, scope 7 — qualitative board: query photo | top-3 retrieved | correct?

Rows are stratified (hits, near-misses, hard misses) and rendered as small
DOWNSCALED crops only (raw catalog/realpairs photography is local-only and never
redistributed; small board thumbnails are committed, consistent with prior
reports). A green frame = top-1 correct product; the correct candidate (if in
top-3) gets a green frame; wrong candidates are framed red.
"""
import argparse
import json
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "results", "051")
TH = 150      # thumbnail size
PAD = 8
LABEL_H = 34


def thumb(path, size=TH):
    try:
        im = Image.open(path).convert("RGB")
    except Exception:
        im = Image.new("RGB", (size, size), (40, 40, 40))
    im.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), (25, 25, 25))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return canvas


def framed(im, color, w=4):
    d = ImageDraw.Draw(im)
    for i in range(w):
        d.rectangle([i, i, im.width - 1 - i, im.height - 1 - i], outline=color)
    return im


def text_strip(width, lines, bg=(15, 15, 15), fg=(230, 230, 230)):
    strip = Image.new("RGB", (width, LABEL_H), bg)
    d = ImageDraw.Draw(strip)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 11)
    except Exception:
        font = ImageFont.load_default()
    for i, ln in enumerate(lines[:2]):
        d.text((3, 2 + i * 15), ln[:46], fill=fg, font=font)
    return strip


def make_row(entry, topk=3):
    cells = []
    # query cell
    q = thumb(entry["query_path"])
    framed(q, (90, 160, 255))
    lbl = text_strip(TH, [f"QUERY {entry['query_capture']}",
                          (entry["query_name"] or "")[:40]])
    cells.append((q, lbl))
    for c in entry["candidates"][:topk]:
        im = thumb(c.get("path"))
        framed(im, (60, 200, 90) if c["correct"] else (210, 70, 70))
        src = "cat" if c.get("source") == "clean_corpus" else "rp"
        cells.append((im, text_strip(TH, [f"#{'OK' if c['correct'] else 'x'} {c['score']:.3f} {src}",
                                          (c["name"] or "")[:40]])))
    row_w = len(cells) * TH + (len(cells) + 1) * PAD
    row_h = TH + LABEL_H + 2 * PAD
    row = Image.new("RGB", (row_w, row_h), (0, 0, 0))
    x = PAD
    for im, lbl in cells:
        row.paste(im, (x, PAD))
        row.paste(lbl, (x, PAD + TH))
        x += TH + PAD
    return row


def stratify_board(board, per_q, seed=0):
    import random
    rng = random.Random(seed)
    hits, near, miss = [], [], []
    for b, pq in zip(board, per_q):
        r = pq["rank"]
        (hits if r == 1 else near if r in (2, 3) else miss).append(b)
    for lst in (hits, near, miss):
        rng.shuffle(lst)
    return hits, near, miss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=os.path.join(OUT_DIR, "realpairs_bench_board.json"))
    ap.add_argument("--perquery", default=os.path.join(OUT_DIR, "realpairs_bench_perquery.json"))
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "board_qualitative.jpg"))
    ap.add_argument("--rows", type=int, default=15)
    args = ap.parse_args()

    board = json.load(open(args.board))
    per_q = json.load(open(args.perquery))
    hits, near, miss = stratify_board(board, per_q)
    n = args.rows
    sel = ([("HIT", b) for b in hits[:n // 3]] +
           [("NEAR", b) for b in near[:n // 3]] +
           [("MISS", b) for b in miss[:n - 2 * (n // 3)]])

    rows = [make_row(b) for _, b in sel]
    if not rows:
        print("no rows"); return
    W = max(r.width for r in rows)
    header_h = 24
    H = header_h + sum(r.height for r in rows) + PAD
    board_img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(board_img)
    d.text((6, 6), "051 wild->clean retrieval  |  blue=query  green=correct product  red=wrong  (cat=corpus distractor, rp=realpairs)",
           fill=(200, 200, 200))
    y = header_h
    for r in rows:
        board_img.paste(r, (0, y)); y += r.height
    board_img.save(args.out, quality=88)
    print(f"wrote {args.out} ({W}x{H}, {len(rows)} rows: "
          f"{len([s for s in sel if s[0]=='HIT'])} hit / "
          f"{len([s for s in sel if s[0]=='NEAR'])} near / "
          f"{len([s for s in sel if s[0]=='MISS'])} miss)")


if __name__ == "__main__":
    main()
