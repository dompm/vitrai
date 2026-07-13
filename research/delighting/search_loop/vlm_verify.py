#!/usr/bin/env python3
"""
Step 3: VLM verification -- the collision guard.

For each product, build a prompt showing the reference swatch (image 1) and
the numbered downloaded candidates, and ask a single `claude` CLI call to
judge which candidates plausibly show the SAME glass product (same color/
pattern family) and classify context (flat-swatch / held-in-hand /
backlit-window / installed-project / other). Parse strictly as JSON; retry
once on parse failure.

Uses `claude -p` (print mode) with image file args via the CLI's multimodal
input support: images are referenced by local file path in the prompt text
per the CLI's file-reading convention, so we pass paths and let the model's
built-in Read tool style ingestion work -- more robustly, we invoke `claude`
with the images attached as prompt content blocks using the -p flag and
inline file references (@path syntax supported by the CLI).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
RESULTS = HERE / "results"

PROMPT_TEMPLATE = """You are verifying stained-glass product image search results.

Image 1 is the REFERENCE swatch of {manufacturer} "{name}" (category: {category}).

The remaining numbered images (2..N, in the order attached) are CANDIDATES found by
web image search for this product. Some may show a genuinely different glass product
(possibly from a DIFFERENT manufacturer that happens to use a similar or identical color
name -- this happens frequently in stained glass, e.g. many brands sell something called
"Streaky" or "Opal" that are visually distinct products). Judge strictly on the actual
visual color/pattern family shown, not on the title/filename text.

For each candidate image (numbered 2..N), decide:
- match: true if it plausibly shows the SAME glass product as the reference (same color
  family AND same pattern/texture family -- allow for different lighting/angle/crop of
  the same physical glass type), false otherwise.
- if match is true, classify its capture context as exactly one of:
  "flat-swatch" (clean studio/lightbox shot of a flat sheet or small piece),
  "held-in-hand" (a hand is visibly holding the glass),
  "backlit-window" (held against a window/sky, backlit by daylight),
  "installed-project" (part of a finished piece: window, lamp, mosaic, suncatcher),
  "other" (doesn't fit the above, e.g. a stack of sheets, a diagram, a swatch card).
- confidence: your confidence in the match, 0.0-1.0.
- reason: one short phrase.

Respond with ONLY a JSON array, one object per candidate image in order, no prose before
or after:
[
  {{"index": 2, "match": true, "context": "flat-swatch", "confidence": 0.9, "reason": "..."}},
  {{"index": 3, "match": false, "context": null, "confidence": 0.8, "reason": "different color, looks like X"}},
  ...
]
"""


def build_image_args(ref_path, cand_paths):
    """Return list of (label, path) in the order they should be attached,
    plus the index mapping used in the prompt (candidates start at 2)."""
    items = [("1", ref_path)]
    for i, p in enumerate(cand_paths, start=2):
        items.append((str(i), p))
    return items


def call_claude_vlm(prompt_text, image_paths):
    """Invoke `claude` CLI in print mode, instructing it to Read each image
    file (the CLI's Read tool renders image files as image content blocks
    for the model). Restricting --allowedTools to Read keeps this a single
    non-interactive, read-only call with no other side effects."""
    numbered = "\n".join(f"{i+1}. {p}" for i, p in enumerate(image_paths))
    full_prompt = (
        f"{prompt_text}\n\n"
        f"First, use the Read tool to read EVERY one of these image files, in order "
        f"(image 1 is the reference, images 2..N are the candidates, matching the "
        f"numbering above):\n{numbered}\n\n"
        f"After reading all of them, respond with ONLY the JSON array as instructed above."
    )
    cmd = [
        "claude",
        "-p",
        full_prompt,
        "--model",
        "sonnet",  # per project memory: batch subcalls must not inherit/burn the fable limit
        "--allowedTools",
        "Read",
        "--output-format",
        "text",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return proc.stdout, proc.stderr, proc.returncode


def extract_json(text):
    text = text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON array found")
    return json.loads(text[start : end + 1])


def verify_product(pid, entry, ref_dir):
    product = entry["product"]
    images = entry["images"]
    if not images:
        return {"pid": pid, "error": "no downloaded images", "verifications": []}

    ref_path = ref_dir / f"{pid}.jpg"
    if not ref_path.exists():
        return {"pid": pid, "error": f"reference swatch missing: {ref_path}", "verifications": []}

    cand_paths = [str((HERE / im["file"]).resolve()) for im in images]
    prompt = PROMPT_TEMPLATE.format(
        manufacturer=product["manufacturer"], name=product["name"], category=product["category"]
    )

    all_paths = [str(ref_path.resolve())] + cand_paths

    for attempt in (1, 2):
        stdout, stderr, rc = call_claude_vlm(prompt, all_paths)
        try:
            parsed = extract_json(stdout)
            # basic shape check
            assert isinstance(parsed, list)
            for item in parsed:
                assert "index" in item and "match" in item
            return {
                "pid": pid,
                "product": product,
                "n_candidates": len(images),
                "verifications": parsed,
                "raw_stdout_len": len(stdout),
                "attempt": attempt,
            }
        except Exception as e:
            print(f"  [{pid}] parse failed attempt {attempt}: {e}", file=sys.stderr)
            print(f"  [{pid}] stdout head: {stdout[:300]!r}", file=sys.stderr)
            if stderr:
                print(f"  [{pid}] stderr head: {stderr[:300]!r}", file=sys.stderr)
            continue

    return {
        "pid": pid,
        "product": product,
        "n_candidates": len(images),
        "verifications": [],
        "error": "failed to parse JSON after 2 attempts",
    }


def main():
    from concurrent.futures import ThreadPoolExecutor

    manifest = json.loads((RESULTS / "downloaded_manifest.json").read_text())
    ref_dir = HERE / "reference_swatches"
    out = {}

    # resume support: skip products already verified
    out_path = RESULTS / "vlm_verifications.json"
    if out_path.exists():
        out = json.loads(out_path.read_text())

    def work(item):
        pid, entry = item
        if pid in out and out[pid].get("verifications"):
            print(f"=== {pid} already verified, skipping ===", file=sys.stderr)
            return pid, out[pid]
        print(f"=== verifying {pid} ({len(entry['images'])} candidates) ===", file=sys.stderr)
        t0 = time.time()
        result = verify_product(pid, entry, ref_dir)
        result["elapsed_s"] = round(time.time() - t0, 1)
        n_match = sum(1 for v in result.get("verifications", []) if v.get("match"))
        print(
            f"  -> {pid}: {n_match}/{result['n_candidates']} matched "
            f"({result['elapsed_s']}s)",
            file=sys.stderr,
        )
        return pid, result

    with ThreadPoolExecutor(max_workers=3) as pool:
        for pid, result in pool.map(work, list(manifest.items())):
            out[pid] = result
            out_path.write_text(json.dumps(out, indent=2))

    print(f"Wrote {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
