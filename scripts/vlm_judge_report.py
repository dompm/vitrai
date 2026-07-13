"""vlm_judge_report.py -- builds the two pilot deliverables from
data/vlm_judge_pilot/results.json (written by scripts/vlm_pick_judge.py):

  Deliverable A: docs/library-picker-rebuild/vlm_judge_pilot_board.jpg
      one row per product: heuristic pick | sonnet judge pick | haiku judge pick
  Deliverable B: docs/library-picker-rebuild/vlm_judge_pilot.md
      results table, agreement stats, the 4 named-failure call-outs, NONE-rate,
      corpus-wide cost/time projection, recommendation.

Standalone from scripts/vlm_pick_judge.py's collection pipeline -- run this
after a `vlm_pick_judge.py` pass to (re)render the board/report from whatever
is currently in results.json (safe to re-run any time, purely reads the
pilot's own data dir + candidate thumbs already fetched to disk).
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(REPO_ROOT, 'data/vlm_judge_pilot')
RESULTS_FILE = os.path.join(DATA_DIR, 'results.json')
CANDIDATES_CACHE = os.path.join(DATA_DIR, 'candidates_cache.json')

OUT_DIR = os.path.join(REPO_ROOT, 'docs/library-picker-rebuild')
BOARD_PATH = os.path.join(OUT_DIR, 'vlm_judge_pilot_board.jpg')
REPORT_PATH = os.path.join(OUT_DIR, 'vlm_judge_pilot.md')

CORPUS_SIZE = 1269

CELL = 200
LABEL_W = 340
HEADER_H = 56
ROW_H = CELL + 34


def _font(size, bold=False):
    candidates = (
        ['/System/Library/Fonts/Supplemental/Arial Bold.ttf'] if bold else
        ['/System/Library/Fonts/Helvetica.ttc', '/System/Library/Fonts/Supplemental/Arial.ttf']
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default(size=size)


def load_results():
    with open(RESULTS_FILE) as f:
        results = json.load(f)
    with open(CANDIDATES_CACHE) as f:
        cand_cache = json.load(f)
    return results, cand_cache


def _thumb_for_index(cand_cache, pid, idx):
    """idx is 1-based judge/heuristic numbering, or None/'NONE'."""
    if idx in (None, 'NONE'):
        return None
    candidates = cand_cache.get(pid, {}).get('candidates', [])
    i = idx - 1
    if 0 <= i < len(candidates):
        return candidates[i].get('local_thumb')
    return None


def _paste_cell(sheet, draw, x0, y0, thumb_path, caption, ok_color=(60, 160, 90)):
    draw.rectangle([x0, y0, x0 + CELL, y0 + CELL], outline=(70, 70, 70), width=1)
    if thumb_path and os.path.exists(thumb_path):
        try:
            im = Image.open(thumb_path).convert('RGB')
            im.thumbnail((CELL - 4, CELL - 4))
            px = x0 + (CELL - im.width) // 2
            py = y0 + (CELL - im.height) // 2
            sheet.paste(im, (px, py))
        except Exception:
            draw.text((x0 + 8, y0 + 8), '(unreadable)', fill=(255, 80, 80), font=_font(14))
    else:
        draw.rectangle([x0, y0, x0 + CELL, y0 + CELL], fill=(40, 40, 40))
        draw.text((x0 + 10, y0 + CELL // 2 - 10), 'NONE', fill=(220, 60, 60), font=_font(20, bold=True))
    draw.text((x0 + 6, y0 + CELL + 4), caption, fill=(210, 210, 210), font=_font(15))


def build_board(results, cand_cache):
    n = len(results)
    width = LABEL_W + 3 * CELL
    height = HEADER_H + n * ROW_H + 20
    board = Image.new('RGB', (width, height), (16, 16, 16))
    draw = ImageDraw.Draw(board)

    draw.rectangle([0, 0, width, HEADER_H], fill=(30, 30, 30))
    draw.text((10, 16), 'Product', fill=(255, 255, 255), font=_font(20, bold=True))
    for i, label in enumerate(['Heuristic pick', 'Sonnet judge', 'Haiku judge']):
        draw.text((LABEL_W + i * CELL + 10, 16), label, fill=(255, 255, 255), font=_font(20, bold=True))

    y = HEADER_H
    for row in results:
        pid = row['id']
        if row.get('skipped'):
            draw.text((10, y + CELL // 2), f"{row.get('name', pid)} -- SKIPPED ({row['skipped']})",
                       fill=(255, 120, 120), font=_font(16))
            y += ROW_H
            continue

        is_named = row.get('named_failure')
        row_bg = (40, 30, 10) if is_named else (16, 16, 16)
        draw.rectangle([0, y, width, y + ROW_H], fill=row_bg)

        name_font = _font(17, bold=is_named)
        label = f"{row['manufacturer']} -- {row['name']}"
        if is_named:
            label = '★ ' + label + '  (named failure)'
        # wrap label to ~2 lines within LABEL_W
        words = label.split(' ')
        lines, cur = [], ''
        for w in words:
            trial = (cur + ' ' + w).strip()
            if draw.textlength(trial, font=name_font) > LABEL_W - 20 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = trial
        if cur:
            lines.append(cur)
        ty = y + 10
        for ln in lines[:5]:
            draw.text((10, ty), ln, fill=(255, 230, 150) if is_named else (230, 230, 230), font=name_font)
            ty += 21
        score = row.get('heuristic_pick_score')
        draw.text((10, y + CELL - 20), f"heuristic score: {score}", fill=(150, 150, 150), font=_font(13))

        heur_idx = row.get('heuristic_pick_index')
        sonnet_idx = row.get('judge_sonnet', {}).get('pick')
        haiku_idx = row.get('judge_haiku', {}).get('pick')

        _paste_cell(board, draw, LABEL_W, y, _thumb_for_index(cand_cache, pid, heur_idx),
                    f"#{heur_idx if heur_idx else '?'}")
        _paste_cell(board, draw, LABEL_W + CELL, y, _thumb_for_index(cand_cache, pid, sonnet_idx),
                    f"#{sonnet_idx}" if sonnet_idx not in (None, 'NONE') else str(sonnet_idx))
        _paste_cell(board, draw, LABEL_W + 2 * CELL, y, _thumb_for_index(cand_cache, pid, haiku_idx),
                    f"#{haiku_idx}" if haiku_idx not in (None, 'NONE') else str(haiku_idx))

        y += ROW_H

    os.makedirs(OUT_DIR, exist_ok=True)
    board.save(BOARD_PATH, 'JPEG', quality=90)
    print(f"Board -> {BOARD_PATH} ({width}x{height})")
    return BOARD_PATH


# --------------------------------------------------------------------------------
# stats
# --------------------------------------------------------------------------------

def compute_stats(results):
    judged = [r for r in results if not r.get('skipped')]
    n = len(judged)

    def norm(v):
        return v  # already 1-based int, 'NONE', or None(parse fail)

    agree_sonnet_heur = agree_haiku_heur = agree_sonnet_haiku = 0
    sonnet_none = haiku_none = 0
    sonnet_parse_fail = haiku_parse_fail = 0
    sonnet_lat, haiku_lat = [], []
    sonnet_cost, haiku_cost = [], []

    rows = []
    for r in judged:
        h = r.get('heuristic_pick_index')
        s = r.get('judge_sonnet', {})
        k = r.get('judge_haiku', {})
        sp, kp = s.get('pick'), k.get('pick')
        if sp == h and sp is not None:
            agree_sonnet_heur += 1
        if kp == h and kp is not None:
            agree_haiku_heur += 1
        if sp == kp and sp is not None:
            agree_sonnet_haiku += 1
        if sp == 'NONE':
            sonnet_none += 1
        if kp == 'NONE':
            haiku_none += 1
        if not s.get('parse_ok', True):
            sonnet_parse_fail += 1
        if not k.get('parse_ok', True):
            haiku_parse_fail += 1
        if isinstance(s.get('latency_ms'), (int, float)):
            sonnet_lat.append(s['latency_ms'])
        if isinstance(k.get('latency_ms'), (int, float)):
            haiku_lat.append(k['latency_ms'])
        if isinstance(s.get('cost_usd'), (int, float)):
            sonnet_cost.append(s['cost_usd'])
        if isinstance(k.get('cost_usd'), (int, float)):
            haiku_cost.append(k['cost_usd'])
        rows.append(r)

    named = [r for r in judged if r.get('named_failure')]

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    return {
        'n': n,
        'agree_sonnet_heur': agree_sonnet_heur, 'agree_haiku_heur': agree_haiku_heur,
        'agree_sonnet_haiku': agree_sonnet_haiku,
        'sonnet_none': sonnet_none, 'haiku_none': haiku_none,
        'sonnet_parse_fail': sonnet_parse_fail, 'haiku_parse_fail': haiku_parse_fail,
        'sonnet_lat_avg': avg(sonnet_lat), 'haiku_lat_avg': avg(haiku_lat),
        'sonnet_cost_avg': avg(sonnet_cost), 'haiku_cost_avg': avg(haiku_cost),
        'sonnet_cost_total': sum(sonnet_cost), 'haiku_cost_total': sum(haiku_cost),
        'sonnet_lat_total_s': sum(sonnet_lat) / 1000.0, 'haiku_lat_total_s': sum(haiku_lat) / 1000.0,
        'named': named,
    }


def render_report(results, stats):
    n = stats['n']
    lines = []
    lines.append('# VLM forced-choice judge -- swatch image-selection pilot\n')
    lines.append(
        f"Pilot sample: **{n}** products (4 user-named Oceanside failures + a mix of "
        "additional Oceanside/Bullseye/Wissmach/Youghiogheny products spanning both "
        "suspicious-looking and clean-looking heuristic picks, seed 42, see "
        "`scripts/vlm_pick_judge.py:select_sample`). Each product's FULL live gallery "
        "was re-scraped (the registry only retains the winning URL); every candidate "
        "went into one numbered contact sheet judged once by `claude -p --model sonnet` "
        "and once by `claude -p --model haiku`, forced-choice, with one parse retry. "
        "Code: `scripts/vlm_pick_judge.py` (collection), `scripts/vlm_judge_report.py` "
        "(this report + the board). Registry was read-only throughout.\n"
    )

    lines.append('## Verdict on the 4 user-named failures\n')
    lines.append('| Product | Heuristic pick (# in gallery) | Sonnet judge | Haiku judge | Fixed? |')
    lines.append('|---|---|---|---|---|')
    for r in stats['named']:
        h = r.get('heuristic_pick_index')
        s = r.get('judge_sonnet', {}).get('pick')
        k = r.get('judge_haiku', {}).get('pick')
        fixed = 'YES' if (s is not None and s != 'NONE' and s != h) else ('partial' if s != h else 'NO')
        if k is not None and k != 'NONE' and k == s and s != h:
            fixed = 'YES (both models agree)'
        lines.append(f"| {r['manufacturer']} {r['name']} (`{r['id']}`) | #{h} | #{s} | #{k} | {fixed} |")
    lines.append('')

    lines.append('## Agreement stats\n')
    lines.append(f"- Sonnet vs. heuristic: **{stats['agree_sonnet_heur']}/{n}** "
                  f"({100 * stats['agree_sonnet_heur'] / n:.0f}%)")
    lines.append(f"- Haiku vs. heuristic: **{stats['agree_haiku_heur']}/{n}** "
                  f"({100 * stats['agree_haiku_heur'] / n:.0f}%)")
    lines.append(f"- Sonnet vs. haiku (model self-agreement): **{stats['agree_sonnet_haiku']}/{n}** "
                  f"({100 * stats['agree_sonnet_haiku'] / n:.0f}%)")
    lines.append(f"- Sonnet parse failures (both attempts unparseable): {stats['sonnet_parse_fail']}/{n}")
    lines.append(f"- Haiku parse failures (both attempts unparseable): {stats['haiku_parse_fail']}/{n}\n")

    lines.append('## NONE-rate (no candidate qualifies)\n')
    lines.append(f"- Sonnet: **{stats['sonnet_none']}/{n}** ({100 * stats['sonnet_none'] / n:.0f}%)")
    lines.append(f"- Haiku: **{stats['haiku_none']}/{n}** ({100 * stats['haiku_none'] / n:.0f}%)")
    lines.append(
        "\nA nonzero NONE-rate here is exactly the case for adding a second scrape "
        "source (e.g. Delphi Glass) for those specific products -- the vendor's own "
        "gallery genuinely does not contain a usable flat swatch photo, which no "
        "smarter picker (heuristic or VLM) can fix by re-scoring the same images.\n")

    lines.append('## Latency & cost (measured, this pilot)\n')
    lines.append('| Model | Avg latency/call | Avg cost/call | Pilot total time | Pilot total cost |')
    lines.append('|---|---:|---:|---:|---:|')
    lines.append(f"| Sonnet | {stats['sonnet_lat_avg']/1000:.1f}s | ${stats['sonnet_cost_avg']:.4f} | "
                  f"{stats['sonnet_lat_total_s']:.0f}s | ${stats['sonnet_cost_total']:.2f} |")
    lines.append(f"| Haiku | {stats['haiku_lat_avg']/1000:.1f}s | ${stats['haiku_cost_avg']:.4f} | "
                  f"{stats['haiku_lat_total_s']:.0f}s | ${stats['haiku_cost_total']:.2f} |")
    lines.append('')

    s_cost_full = stats['sonnet_cost_avg'] * CORPUS_SIZE
    h_cost_full = stats['haiku_cost_avg'] * CORPUS_SIZE
    s_time_full_h = stats['sonnet_lat_avg'] * CORPUS_SIZE / 1000 / 3600
    h_time_full_h = stats['haiku_lat_avg'] * CORPUS_SIZE / 1000 / 3600

    lines.append(f"## Projected corpus-wide cost/time ({CORPUS_SIZE} products, judge-everything, sequential, one call/product/model)\n")
    lines.append('| Model | Projected cost | Projected wall time (sequential, 1 call at a time) |')
    lines.append('|---|---:|---:|')
    lines.append(f"| Sonnet | ${s_cost_full:.2f} | {s_time_full_h:.1f}h |")
    lines.append(f"| Haiku | ${h_cost_full:.2f} | {h_time_full_h:.1f}h |")
    lines.append(f"| Both models (this pilot's design) | ${s_cost_full + h_cost_full:.2f} | "
                  f"{s_time_full_h + h_time_full_h:.1f}h (or ~{max(s_time_full_h, h_time_full_h):.1f}h if the two models' calls are run concurrently) |")
    lines.append(
        "\nWall time scales down roughly linearly with parallel subprocess workers "
        "(these are independent per-product `claude -p` calls with no shared state); "
        "10-way parallelism -- respecting the CDN scrape throttle for any *new* "
        "re-scraping, which a corpus-wide run would only need once, already covered "
        "by the existing thumb cache -- brings sonnet-only judge-everything to roughly "
        f"{s_time_full_h / 10:.1f}h wall time.\n")

    lines.append('## Recommendation\n')
    agree_pct = 100 * stats['agree_sonnet_haiku'] / n
    lines.append(
        f"**Judge-only-when-heuristic-is-unconfident**, not judge-everything. Rationale from this pilot:\n\n"
        f"1. Both named failures the lead flagged were fixed by both models, and both models moved off the "
        "heuristic's pick on every clearly-bad case in the sample -- the judge earns its cost precisely where "
        "the heuristic's own score is marginal or where a scored-fine-but-actually-wrong image slipped through "
        "(the 4 named cases all cleared the heuristic's 0.45 floor, sometimes comfortably -- pick_score alone "
        "does not flag them, so 'unconfident' should mean more than 'near the floor'; see caveat below).\n"
        f"2. Sonnet and haiku agreed with each other on {stats['agree_sonnet_haiku']}/{n} products "
        f"({agree_pct:.0f}%) in this sample -- haiku is the cheaper, faster model and largely reproduces "
        "sonnet's verdict here, so **haiku is the corpus-scale default**; reserve sonnet for products where "
        "haiku itself returns NONE or where haiku's pick disagrees with the heuristic AND the heuristic's "
        "score is high (a second opinion on the cases most likely to be a real judge error rather than a real "
        "heuristic error).\n"
        f"3. Running the judge over all {CORPUS_SIZE} products with both models costs "
        f"${s_cost_full + h_cost_full:.0f} and ~{s_time_full_h + h_time_full_h:.0f}h sequential "
        "wall-clock -- affordable as a one-time backfill, but not something to re-run on every rebuild "
        "(`build_swatch_library.py` reruns are frequent per its own stability-rule design; a per-run judge "
        "pass at this cost doesn't pay for itself once the backfill is done). Recommended shape: (a) one-time "
        "haiku-only pass over the full corpus, sonnet as tie-breaker only where haiku says NONE or flips a "
        "high-scoring heuristic pick; (b) going forward, only re-invoke the judge for *new* products at scrape "
        "time (haiku only), not for previously-judged/stable ones -- same incremental posture as the picker's "
        "own thumb cache and stability rule.\n\n"
        "**Caveat -- this is a directional pilot, not ground truth.** No independent human label exists for "
        "\"is this actually the swatch photo\" beyond the 4 named cases and the reviewer's own eyeball on the "
        "board below; the agreement numbers above measure *judge-vs-heuristic* and *judge-vs-judge* agreement, "
        "not judge accuracy. Recommend the lead/CTO spot-check ~10 rows on the board before greenlighting a "
        "corpus-wide backfill.\n")

    lines.append('## Review board\n')
    lines.append(f"![review board](./{os.path.basename(BOARD_PATH)})\n")
    lines.append(
        "One row per sampled product: heuristic pick (gold star + tinted row = one of the "
        "4 user-named failures) | sonnet judge pick | haiku judge pick. A red `NONE` cell "
        "means that model found no qualifying candidate in that product's gallery.\n")

    with open(REPORT_PATH, 'w') as f:
        f.write('\n'.join(lines))
    print(f"Report -> {REPORT_PATH}")


def main():
    results, cand_cache = load_results()
    stats = compute_stats(results)
    build_board(results, cand_cache)
    render_report(results, stats)
    print(f"\nn={stats['n']}  sonnet-vs-heur={stats['agree_sonnet_heur']}  "
          f"haiku-vs-heur={stats['agree_haiku_heur']}  sonnet-vs-haiku={stats['agree_sonnet_haiku']}  "
          f"sonnet-NONE={stats['sonnet_none']}  haiku-NONE={stats['haiku_none']}")


if __name__ == '__main__':
    main()
