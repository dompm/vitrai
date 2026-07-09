# Report 005 — Synthetic per-pixel ground-truth evaluation

Date: 2026-07-09. Code: `extract.py` @ this commit + new `eval_synthetic.py`.
Worktree on `research/delighting`. Deliverables: `eval_synthetic.py`,
`results/synthetic_eval/` (contact sheets + `summary.json`), this report. No PR.

**First iteration with real ground truth.** Reports 001–004 scored only
*self-reconstruction* (`I ≈ L·T·(…)`), which report 003 showed is structurally
blind to the L/T gauge — it cannot tell whether `T` is right, only whether `L·T`
refits the photo. This iteration compares extracted `T`/`h` against authored
**per-pixel** `gt_T`/`gt_h` rendered through the same camera, on the absolute scale.

## 0. TL;DR for the ship/no-ship decision

- **The primary "money question" (dark-opaque absolute scale) is UNANSWERABLE this
  run: the dataset has ZERO dark-opaque samples** (also zero wispy-white and zero
  cathedral-amber). Only `cathedral-green` (6) and `streaky-mix` (2 complete) exist
  so far. `eval_synthetic.py` is built to pick those recipes up automatically when
  they land — re-run the same command.
- Extractor accuracy, ORACLE class (true class from `meta.json`):

  | recipe | oracle class | n | T_mae | T_p95 | h_mae | h_p95 |
  |---|---|---|---|---|---|---|
  | cathedral-green | cathedral-clear | 6 | **0.167** | 0.429 | **0.084** | 0.092 |
  | streaky-mix | wispy | 2 | **0.115** | 0.309 | **0.299** | 0.693 |

  (linear absolute units, 0–1; T over RGB, h scalar.)
- **Both PHOTOS look physically correct** (my eyes on the contact sheets + boosted
  raw frames): streaky-mix milky streaks render **bright/transmitting** (physics fix
  confirmed), cathedral-green is plausible textured green glass over a real
  background. Neither shows the purple/magenta failure — **but I could not check
  dark-opaque, which is exactly the recipe that claim was about.**
- VLM classifier: **2/2 correct** (cathedral→cathedral-clear, streaky→wispy).
- Hand-shadow corruption of `T` (OP-1): **~0.31** inside the shadow for cathedral,
  **~0.08** for streaky; ~0.002 outside. Large and localized.

## 1. Ground-truth conventions — VERIFIED before trusting any number

- **`gt_T.exr` is LINEAR transmittance**, directly comparable to the extractor's
  linear `T`. Proof: `photo_linear / gt_T` yields a near-neutral backlight `L`
  (normalized RGB ≈ .32/.36/.32, G/R 1.10); treating `gt_T` as sRGB instead gives an
  implausible magenta `L` (G/R 0.55). `gt_T.png` stores the same values raw (no gamma).
- **`gt_h.png` is linear haze `/65535`.** (`gt_h.exr`/`gt_mark_mask.exr` fail to
  decode via OpenCV — return `None`; I used the PNGs. Minor generator nit.)
- **Alignment: confirmed camera-aligned, zero registration needed.**
  Luminance cross-correlation of photo vs `gt_T` peaks at offset (0,0). Extracted-`T`
  structure visibly registers with the photo in every contact row.
- Working resolution 700 px (extractor default); `gt` downscaled to match with area
  averaging. Marked pixels (`gt_mark_mask`) excluded from T/h error.

## 2. Primary result — extractor accuracy, and *what the error actually is*

The headline MAEs above are real, but the raw number conflates extractor fault with
a **task-definition gap**, so I decomposed each.

**`gt_T` is spatially near-FLAT.** For cathedral-green its per-channel std is ~**0.01**
— the generator defines transmittance as the *intrinsic material tint*, uniform
across the sheet; surface relief and the see-through background are **not** in `gt_T`.
The rendered photo, however, shows the glass as transparent: **blue sky in the top
panes, green grass/lawn in the bottom**, plus hammered-relief lensing. For
cathedral-clear the extractor passes `T = R = I/L` straight through (it assumes the
background is "featureless backlight"), so all that structured background lands in
`T`.

Decomposition (mean-tint error vs spatial residual):

| recipe | T_mae | tint error \|mean_ext−mean_gt\| | spatial residual |
|---|---|---|---|
| cathedral-green | 0.167 | **0.033** | ~0.134 |
| streaky-mix | 0.115 | **0.080** | ~0.035 |

- **cathedral-green: the average tint is accurate (0.033); ~0.13 of the 0.167 is
  structured-background/relief/frame bleed-through** — i.e. the extractor's
  featureless-backlight assumption meeting a realistic HDRI background. Whether you
  charge this to the extractor or to the (single-photo, genuinely ambiguous) problem
  is a judgment call, but the map is not delivering per-pixel intrinsic `T` on
  transparent glass over structure. `h` is **excellent (0.084)** and correctly
  near-zero.
- **streaky-mix: error is tint-dominated (0.08).** The extractor **greys out the
  blue-white tint** — it returns `T ≈ (.80,.81,.81)` vs `gt (.69,.79,.92)`, losing the
  blue. The spatial map is otherwise close (0.035). But **`h` is badly overestimated:
  ext 0.69 vs gt 0.48, h_p95 0.69** — the wispy prior calls the clear streaks milky.
  (`opalescent` would be worse: its 0.55 h-floor sits above streaky's true 0.24
  floor, which is exactly why I mapped streaky→**wispy**; documented in the script.)

Direction of the `h` bias is opposite per class: extractor **under**-hazes cathedral
(ext 0.07 vs gt 0.15 — the synthetic cathedral has a ~0.15 haze floor the
cathedral-clear model never reaches) and **over**-hazes streaky.

## 3. Absolute-scale check (the iteration-003 money question)

**Cannot be answered: no dark-opaque samples exist yet.** The whole point — does
dark-opaque extracted `T` come out ≈ its `gt_T` (few %) and NOT bright — needs that
recipe. Flagging as the #1 gap; the harness will tabulate it automatically when the
recipe appears.

For the classes present there is **no brightness blow-up**: cathedral mean-`T`
tracks `gt` to ~0.03 (blue channel runs ~0.08 low); streaky sits at the right level
but desaturated. So nothing in the present data reproduces the old
dark-glass-glows-bright failure — but that failure was specific to dark-opaque,
which is untested.

## 4. Data sanity — my own eyes on the contact sheets (`results/synthetic_eval/`)

Columns per row: photo | ext T | gt T | \|T err\|×5 | ext h | gt h.

- **streaky-mix PHOTO: physically correct — physics fix CONFIRMED.** At native
  exposure the sheet is dim (its `hdri_ev` = −1.44), but exposure-normalized it is
  clearly a **milky translucent sheet: a bright vertical milky streak that diffuses
  and hides the background, flanked by wispier regions where blurred sky/grass shows
  through.** Milky streaks read bright/transmitting, not opaque. Correct.
- **cathedral-green PHOTO: physically correct.** Textured green cathedral glass with
  the real background transmitted (sky top, lawn bottom). The black cross on some
  samples is a **legitimate leaded frame** — it appears exactly on the
  `has_frame=True` samples (light4506/1262/2358) and is absent on `has_frame=False`.
  Not a bug.
- **dark-opaque: NOT VERIFIABLE — no samples.** I cannot confirm or refute the other
  agent's HDRI-path / purple-magenta fix. This is the one recipe whose physical
  correctness was in question, and it is the one absent from the batch.

**Generator notes (distinct from extractor error), for the maintainer:**
1. `gt_T` excludes relief and see-through background (near-flat tint). That is a
   legitimate definition, but it means per-pixel T-MAE on transparent classes mostly
   measures background bleed-through, not tint recovery — interpret §2 accordingly. A
   validity/crop mask or an alternative "photo-space T" target would separate the two.
2. `has_frame=True` frame pixels (~5%) are black in the photo, absent from `gt_T`, and
   inflate T-MAE; real use crops to the glass. Consider shipping crop corners in `meta`.
3. Photos are very dim (`hdri_ev` −1.3…−1.5). Harmless here (VLM still correct) but
   worth watching for any luminance-thresholded logic.
4. `gt_h.exr` and `gt_mark_mask.exr` don't decode in OpenCV; PNGs are fine.

## 5. VLM classifier accuracy (secondary)

One `claude` CLI call per recipe (haiku, cached in `.vlm_cache.json`):

| recipe photo | VLM answer | oracle target | match |
|---|---|---|---|
| cathedral-green | cathedral-clear | cathedral-clear | ✓ |
| streaky-mix | wispy | wispy | ✓ |

**2/2.** Notably the dim streaky photo was **not** misread as dark-opaque. Too few
recipes present to stress the classifier (no dark-opaque / wispy-white / amber to
try to confuse it), so this is encouraging but not a real confusion matrix yet.

## 6. Shadow gap (OP-1, secondary)

Extract `T` from `with_shadow` vs `without_shadow`; shadow region auto-detected as
where the photo darkened (no `gt_shadow_mask` ships). Mean \|ΔT\|:

| recipe | inside shadow | outside | shadow area |
|---|---|---|---|
| cathedral-green (6) | **0.311** | 0.0015 | ~4% |
| streaky-mix (2) | **0.078** | 0.0036 | ~4% |

The cast hand shadow corrupts recovered `T` by ~**0.31** (31 pp) inside the shadow for
cathedral-clear — because `T = I/L` and the shadow darkens `I` but not the smooth `L`,
so `T` collapses there. Wispy is **4× more robust** (0.078): its haze floor +
diffusion-fill `T` assembly absorbs the local darkening. Outside the shadow, both
are negligible (~0.002), so the corruption is well-localized — a mask-and-inpaint of
the shadow region (if it can be detected) would largely recover cathedral `T`.

## 7. Verdict

- **Extractor, oracle class:** `h` is trustworthy for cathedral (0.08) and poor for
  streaky (0.30, over-hazed). `T`'s *average tint* is good for cathedral (0.03) but
  greyed for streaky (0.08); the large cathedral per-pixel T-MAE (0.167) is mostly the
  featureless-backlight assumption failing against a real see-through background — a
  genuine limitation, arguably shared with the problem's inherent ambiguity.
- **The decision this iteration was meant to inform (dark-opaque absolute scale) is
  blocked on missing data.** Re-run `eval_synthetic.py --data … --vlm --shadow` once
  dark-opaque / wispy-white / amber samples exist; the tables regenerate.
- **Both testable recipes render physically correctly**, streaky-mix's milky-streak
  physics fix included. **Dark-opaque's rendering remains unverified** — the single
  most important thing still to check.
