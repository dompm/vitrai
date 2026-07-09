# Report 007 — Ground-truth extractor eval across ALL 5 recipes

Date: 2026-07-09. Code: `eval_synthetic.py` @ this commit (unchanged from 005),
`extract.py` @ this commit. In-house run: Blender 5.0.1 rendered the three
previously-missing recipes; `eval_synthetic.py` scored the whole dataset.
Deliverables: `results/synthetic_eval/` (contact sheets + summary), this report. No PR.

## 0. TL;DR for the ship/no-ship decision

- **The dataset gap from report 005 is CLOSED.** All 5 recipes now have samples and
  are scored per-pixel against authored ground truth. Report 005 could only score
  cathedral-green + streaky-mix; dark-opaque, wispy-white, cathedral-amber were empty.
- **Money question (a) — dark-opaque: PASS on both halves.**
  - Extracted `T` comes out **dark** (mean RGB `[0.08,0.08,0.06]`, ~7%), **not bright**.
    The old "dark glass extracted as ~0.97 bright" bug is gone. If anything it now
    *overshoots dark* (gt is `[0.19,0.21,0.19]`), i.e. too dark by ~0.11, not too bright.
  - The **rendered photo is a plausible dark neutral/greenish tint, NOT purple/magenta.**
    Measured linear mean `[0.05,0.06,0.04]` → green-dominant (R/G 0.93, B/G 0.78);
    magenta would need R and B *above* G. Confirmed by eye on the contact sheet. The
    absolute-HDRI-path fix is verified.
- **Money question (b) — wispy-white (opalescent product case): PASS, faithful.**
  Extractor recovers the opalescent character: near-neutral **milky-white** `T`
  (`[0.75,0.75,0.75]`, undershoots gt `[0.86,0.87,0.89]` brightness by ~0.11 but hue
  correct) **plus high, correctly-textured haze** (`h_ext 0.93` vs `h_gt 0.85`,
  h_mae 0.108). It reads as white + hazy, not clear and not colored. This is the
  strongest recipe after the cathedral pair.
- **Honest headline:** the generator/data are in good shape (validation floors in
  report 006, clean camera-aligned gt, no magenta). The residual errors are
  **overwhelmingly the extractor's**, and they are the *same* gauge issues report 003
  called out: an absolute-scale anchor that runs `T` too dark, and color-constancy that
  neutralizes real glass tint. Ship/no-ship is an *extractor* decision, not a data one.

## 1. Per-recipe results (ORACLE class from meta.json)

| recipe | n | T_mae | T_p95 | h_mae | h_p95 | T_mean_ext | T_mean_gt | h_ext | h_gt |
|---|---|---|---|---|---|---|---|---|---|
| cathedral-amber | 2 | 0.159 | 0.442 | 0.088 | 0.092 | 0.78,0.72,0.26 | 0.87,0.70,0.31 | 0.06 | 0.15 |
| cathedral-green | 7 | 0.163 | 0.415 | 0.084 | 0.092 | 0.42,0.79,0.42 | 0.42,0.76,0.48 | 0.07 | 0.15 |
| dark-opaque | 2 | 0.124 | 0.158 | 0.243 | 0.317 | 0.08,0.08,0.06 | 0.19,0.21,0.19 | 0.34 | 0.58 |
| streaky-mix | 4 | 0.127 | 0.324 | 0.352 | 0.704 | 0.77,0.78,0.78 | 0.64,0.77,0.92 | 0.63 | 0.39 |
| wispy-white | 2 | 0.147 | 0.284 | 0.108 | 0.200 | 0.75,0.75,0.75 | 0.86,0.87,0.89 | 0.93 | 0.85 |

(linear absolute units, 0–1; `T` over RGB, `h` scalar. Marked pixels excluded.)

Comparison to report 005 (same code, fewer samples then): cathedral-green
`T_mae 0.167 → 0.163`, streaky-mix `0.115 → 0.127` — stable, so the added samples did
not shift the picture, they filled it in.

## 2. What I saw on the contact sheets (my own eyes)

- **dark-opaque** — photos are dark grey-green tinted panes (row 1 has window mullions,
  both have the hand-drawn mark squiggle). Extracted `T` column is correspondingly dark.
  No purple anywhere. `T_p95` only 0.158 — the whole map is uniformly dark, exactly the
  intended behavior. Note `h` is under-read (0.34 vs 0.58): the extractor's dark-opaque
  haze model is conservative. Low priority vs. the T-is-dark result that mattered.
- **wispy-white** — milky white opalescent panes with a warm HDRI cast. `T` recovers
  as milky near-white; `h` recovers as high, cloud-textured haze matching the gt
  structure. Residual `T` error is (i) mild brightness undershoot and (ii) some HDRI
  color leaking into `T` (visible only when the error map is boosted ×5).
- **streaky-mix** — the streak *structure* is recovered in both `T` and `h`, but the
  gt is distinctly **blue** (`gt_T` `[0.64,0.77,0.92]`) and the extractor neutralizes it
  to grey `[0.77,0.78,0.78]` → the rainbow ×5 error map. Haze is over-read and
  over-contrasty (`0.63` vs `0.39`). Worst `h_mae` (0.352) of the set.
- **cathedral-green / -amber** — plausible textured cathedral glass over a real
  background; no magenta. `T` error is dominated by the glass **surface-relief texture**
  that the extractor keeps (it cannot know the flat authored tint behind the refraction),
  plus frame-mullion occlusion stripes.

## 3. Shadow corruption (OP-1), with/without-shadow pass

`dT` in the cast-hand-shadow region vs outside it (auto-detected as where the shadow
photo is darker):

| recipe | shadow area | dT_in_shadow | dT_outside |
|---|---|---|---|
| cathedral-green | 3–6% | 0.21–0.40 | ~0.001–0.003 |
| cathedral-amber | 3–6% | 0.30–0.35 | ~0.001 |
| streaky-mix | 1–5% | 0.05–0.11 | ~0.003–0.006 |
| wispy-white | 6–7% | 0.07–0.11 | ~0.003–0.006 |
| dark-opaque | 0–3% | 0.04 (n=1) | ~0.001 |

Outside the shadow `T` is essentially untouched (~0.1–0.6%); inside it is badly
corrupted, worst on cathedral (a cast shadow reads as reduced transmission because the
extractor has no shadow prior). Localized and large — an unaddressed extractor issue,
not a data problem.

## 4. Error attribution — extractor vs generator/data (brutally honest)

**Extractor (the real problem surface):**
1. **Absolute-scale anchor runs `T` too dark.** dark-opaque 0.08 vs 0.19, wispy 0.75 vs
   0.86, cathedral-amber 0.78 vs 0.87 — a systematic downward bias on `T` brightness.
   This is the report-003 gauge issue, still live.
2. **Color constancy / gauge.** streaky-mix's blue tint is neutralized; can't separate
   glass tint from illuminant. Largest single visible error in the set.
3. **Haze prior mismatch for streaky-mix** (mapped to `wispy` class) → over-read,
   over-contrasty `h`.
4. **Surface relief retained in `T`** for cathedral (refraction texture not flattened).
5. **No shadow prior** → severe localized `T` corruption under cast shadows (§3).

**Generator / data (minor):**
- gt is clean, camera-aligned, physically consistent (report 006 floors), and free of
  the magenta failure. No blocking issues found.
- Debatable *authoring*, not a bug: dark-opaque gt_T ~0.19–0.21 is "dim tinted," not
  near-black; if the product target is truly near-opaque, the recipe could go darker.
- One stale sample dir `streaky-mix__seed44__light4062` had no `meta.json` (leftover
  from an earlier aborted run) and was auto-skipped by the eval. Harmless; gitignored.

## 5. Environment / provenance

- **Blender 5.0.1** official macOS arm64 portable build (matches every `meta.json`),
  headless, Cycles on the Apple M4 Metal GPU. scipy+requests surfaced to Blender via
  `PYTHONPATH` + `--python-use-system-env` (bundle site-packages is read-only).
- Render: `--count 5 --light-variations 2` (one of each recipe × 2 lightings, shadow
  pairs) → 10 new samples, ~12 min total.
- Eval: `eval_synthetic.py --data synthetic_data --shadow`, run from repo `.venv`
  (cv2 + Pillow). Renders stay local (gitignored); only the 504 KB of downscaled
  contact sheets + summary are committed.
