# Report 002 — Mark-inpaint fix, contrast recovery, library batch, pair harness

Date: 2026-07-08. Code: `extract.py`, `contact_sheet.py`, `register_pair.py`,
`vlm_classify.py` @ this commit. Panels: `results/`, `results/library/`.

This iteration builds on report 001 (read it first — problem model, metric
definitions M1/M2/M3, and the keyed open-problem list are there). Four changes:
(1) fix the grease-pencil ghost in `h`, (2) recover wispy contrast lost to the
illumination envelope, (3) process the whole default glass library, (4) build
the cross-lighting validation harness (M3) so evaluation is one command when the
validation photo pairs arrive.

## 1. Mark-inpaint fix — WORKED (verified on the images, not just the diff)

**Root cause (confirmed).** 001 detected the SKU strokes, Telea-inpainted `R`,
then computed `h` and `T`. But Telea leaves a faint *tinted smudge* where the
strokes were; the downstream saturation/chroma cues re-read that smudge as glass
content, so `h` was effectively computed from the residue and then "healed" with
a halo too small to cover the wide faint part of the strokes. The SKU came back.

**Two fixes.** (a) Repair `R` by **diffusion fill** (normalized convolution from
clean neighbours) instead of Telea — no tinted residue to re-detect; `h` and `T`
are then computed from an already-clean `R` with no post-hoc healing. (b) When
the mark region is known (from the manifest or VLM localization), use
`remove_marks_in_region()`: inside that one 3x3 grid cell, lift every small dark
feature to its morphological closing (disk ≈ 2.2 % of width). Strokes — including
their wide faint smudge — are removed wholesale; structures larger than the disk
(streaks, veins) are untouched.

**Verdict — I compared `results/difficult_wispy_h.png` and `_T.png` against the
committed 001 versions (`git show 7c676e5:…`) pixel-region by region:**

- In `h`, 001 had discrete dark rounded blobs along the bottom-center/right —
  the ghosted "9000-81" loops. In 002 those blobs are **gone**, replaced by
  continuous wispy structure. Clear win.
- In `T` (bottom-right crop), 001 shows the digits **legible** as gray stroke
  outlines you can read as "9000 81". In 002 they are reduced to a faint, soft
  **light patch** — the strokes are no longer legible. The mark also no longer
  survives in either relit panel.
- **Honest cost:** the region-closing lifts *all* small dark features in that one
  grid cell, so real fine dark glass flecks inside the bottom-right cell are also
  brightened slightly, leaving a faintly-washed patch. Confined to one cell and
  far preferable to a readable SKU. This is the correct trade for a product whose
  job is to hide the shop's price marks.

So the fix is real and visible, not just a metric artifact. Mark-mask area on the
wispy case also dropped 11.2 % → 7.7 % (the region detector is tighter than the
old global one), and the clean-pixel recon MAE improved (next section).

## 2. Contrast recovery — envelope percentile 88 → 95 + confidence sharpen

Report 001 failure 4: wispy structure in `T` was lower-contrast than the
original, because some glass structure leaked into the illumination envelope and
the diffusion fill averaged mid-confidence pixels 50/50 with a smooth fill.

I did **not** go to the gradient-domain Poisson solve floated in 001 §9 — the
cheaper knobs closed most of the gap:

- **Envelope percentile 88 → 95** (`estimate_illumination`). A higher upper
  envelope keeps large-scale glass absorption in `T` instead of eating it into
  `L`. Chosen by sweep: 95 gave the best contrast without visible residual
  illumination on the easy case; above 95 the envelope starts clipping to
  speculars.
- **Confidence sharpen** (`assemble_T`): pass the fill confidence through a
  `smoothstep(0.08, 0.50)` so mid-confidence wispy pixels (h ≈ 0.5) are trusted
  fully and only genuine background is filled, instead of being blended half-and-
  half with the smooth fill.

**Tradeoff / verdict.** Both benchmark cases improved on every recon number, so
this was close to free rather than a real tradeoff:

| case | MAE 001 | MAE 002 | p95 001 | p95 002 |
|---|---|---|---|---|
| easy_amber | 2.67 | **2.22** | 13.85 | 12.08 |
| difficult_wispy (clean px) | 2.93 | **2.40** | 8.54 | 5.79 |
| difficult_wispy (all px) | 4.14 | **3.08** | — | — |

The one place to watch: percentile 95 is nearer the specular ceiling, so on a
sheet with large blown-out speculars the envelope could latch onto a glint and
push a dark halo into `T`. None of the 11 sheets here show it, but it is the
failure mode to check first on new inputs. `h_mean` on the wispy case dropped
0.78 → 0.69, consistent with more structure (including clear-streak dips) now
surviving into the maps rather than being smoothed flat.

## 3. Library batch — all 9 default-library sheets

`benchmark/library/` holds the 9 app swatches (cropped to glass, corners in
`manifest.json`, all `mark_region: none`). Contact sheet:
**`results/library/contact_sheet.jpg`** (rows = sheets; columns original | T | h
| relit warm | relit cool; MAE/p95/h_mean in each row label).

| sheet | class | MAE /255 | p95 /255 | one-line verdict vs "reproduce the easy case faithfully" |
|---|---|---|---|---|
| green | cathedral-clear | **0.67** | 3.5 | pass — texture and hue clean, best in set |
| black | dark-opaque | **0.80** | 4.4 | pass — recovers hammered texture from near-black; `h` has real structure |
| white | cathedral-clear | **0.90** | 4.9 | pass — texture preserved, slight haze (h_mean 0.09) plausible for frosted white |
| turquoise | cathedral-clear | 1.73 | 10.1 | pass |
| orange | cathedral-clear | 2.14 | 11.8 | pass |
| amber | cathedral-clear | 2.16 | 11.9 | pass (matches the standalone easy_amber case) |
| pink | cathedral-clear | 2.17 | 13.9 | pass — `T` a touch desaturated vs original but faithful |
| red | cathedral-clear | 3.07 | 16.6 | pass with a caveat — deep-red hotspot residue raises p95 |
| blue | cathedral-clear | **3.56** | **24.6** | weakest — see below |

**Nothing looks broken.** All nine relight plausibly in both warm and cool.

**Blue is the one to flag.** MAE 3.56 and p95 24.6 are both the worst in the set.
Cause (from the panel + error map): blue is heavily-hammered "glue-chip" texture
with a strong light-table **hotspot** bottom-center that the envelope does not
fully remove, so a bright cyan patch leaks into `T` and dominates the error map.
It is not wrong — the hue and texture are right and it relights sensibly — but it
is the least faithful reproduction and the clearest example of the envelope
under-fitting a concentrated backlight hotspot (report 001 §6 easy-case residual,
worse here). Red has a milder version of the same.

**One reading note on the contact sheet:** the `h` column is near-black for the 8
cathedral-clear sheets. That is not a render failure — `h` is the class default
≈ 0.06 there (flat, unmeasured, exactly as 001 §6 noted), so it encodes to ~15/255.
Only `black` (h_mean 0.26) and `white` (0.09) show visible `h` structure.

## 4. Cross-lighting validation harness (M3) — built and smoke-tested

`register_pair.py` implements M3 so that when the validation pairs land in
`~/Downloads` (cross-lighting pairs + a shadow/no-shadow pair) evaluation is one
command. Given two handheld photos of the **same** sheet under **different**
lighting it:

1. **registers B onto A** — homography from the four sheet corners
   (`--corners-a`/`--corners-b`, order TL,TR,BR,BL; each photo rectified to a
   canonical rectangle so they are pixel-aligned by construction), or ORB +
   RANSAC auto-registration when corners are omitted and the framing is close;
2. **extracts `T,h` independently from A and from B** (reusing the exact pipeline
   via the new `extract_maps()` — single source of truth with the CLI);
3. **forward-renders A's material under B's illumination** and compares to photo
   B, reusing `extract.reconstruct()` unchanged (A's `T,h` crossed with B's `L`
   and B's quarter-res through-glass background).

It writes `<A>__<B>_pair.jpg` (A | registered B | T_A | T_B | predicted-B | err×5),
`<A>__<B>_reg.jpg` (checkerboard blend to eyeball alignment), and a metrics JSON
with **two** numbers:

- **T-agreement MAE** — `|sRGB(T_A) − sRGB(T_B)|` over the sheet. The *strong*
  test: material maps from two different lightings must match, and it needs no
  background model. **This is the number to trust.**
- **cross-recon MAE** — render-A-under-B vs photo B, directly comparable to the
  per-photo self-recon MAE in `results/`. Its through-glass background is an
  estimate, so it is corroboration, not proof.

**Status: functional, smoke-tested on a synthetic pair, not yet run on real
data** (the validation photos have not arrived). Smoke test: a perspective-warped
+ synthetically-relit copy of `easy_amber` registers correctly in both modes
(ORB found 400 inliers; the checkerboard blend aligns seamlessly), and the
columns/metrics populate sanely (T-agreement MAE 6–9/255, non-zero because of the
synthetic resample and the strong fake illumination change). Numbers on real
pairs are the actual test; treat T-agreement single digits as the pass bar to aim
for. Usage:

```sh
python3 register_pair.py A.jpg B.jpg --class wispy \
    --corners-a  TLx,TLy,TRx,TRy,BRx,BRy,BLx,BLy \
    --corners-b  TLx,TLy,TRx,TRy,BRx,BRy,BLx,BLy
# omit both --corners-* to auto-register via ORB (similar framing required)
```

## 5. Track C addition — mark localization

`vlm_classify.py` gained `locate_mark()`: a second multiple-choice question to
the `claude` CLI ("where is the handwritten marking: none / 3x3 grid cell"),
cached separately from the class question. `extract.py --vlm` now uses it to
drive the region-targeted mark remover automatically. Validated 2/2 on the
benchmark (wispy → bottom-right, amber → none). Still multiple-choice only — no
numeric regression, per the Track C rule in 001.

## 6. What changed in the code (for the reviewer)

- `estimate_illumination`: envelope percentile 88 → 95.
- `assemble_T`: added confidence `smoothstep(0.08, 0.50)`.
- `detect_marks` → kept as the "unknown region" conservative detector; new
  `remove_marks_in_region()` + `region_box_mask()` for the targeted case.
- `process`: mark repair is now diffusion-fill (not Telea) and the post-hoc `h`
  healing block is deleted; new `mark_region` argument threads through the CLI
  and manifest.
- `diffusion_fill`: now accepts HxW as well as HxWx3 (used for `h` and masks).
- **Refactor:** pipeline steps 1–4 extracted into `extract_maps()` and loading
  into `load_linear()`, so `process()` and `register_pair.py` share one
  implementation. Verified behavior-preserving: re-running the benchmark after the
  refactor reproduces both `_metrics.json` **byte-for-byte**.

## 7. Open problems — status against 001's list

- **OP-1 shadow-vs-wisp**: untouched. The hand-shadow smudge on the wispy case is
  still there. Needs the shadow/no-shadow validation pair (harness is ready) or a
  geometric cast-shadow detector. Highest-value unsolved item.
- **OP-2 mark generality**: partly better — region targeting removes the SKU
  cleanly *when its cell is known*, but the closing assumes marks are darker than
  the glass (white pencil on white opal would still be missed), and it lifts fine
  dark detail in that cell.
- **OP-3 `h` ground truth**: still none. M3 harness is the path; blocked on photos.
- **OP-4 tint/illuminant ambiguity**, **OP-5 sky-vs-milky**, **OP-6 sparkle**,
  **OP-7 T-relative**, **OP-8 metric**: unchanged from 001.
- **New**: envelope percentile 95 sits nearer the specular ceiling (§2) — the
  blue/red hotspot residue (§3) is the concrete instance to fix next, most likely
  with the gradient-domain illumination solve deferred from 001 §9.

## 8. Ship read

Against the maintainer's criterion — **"reproduce the easy case faithfully"** —
the library batch says yes: all 9 default-library sheets pass to my eye, 3 of 9
under MAE 1.0, worst 3.56. The 001 headline defect (legible SKU ghost) is fixed
and verified on the images. The remaining honest gaps are the wispy case's
hand-shadow (OP-1, single-photo-hard) and the backlight-hotspot residue on the
most heavily-textured sheets (blue/red). Neither blocks the easy-case ship
criterion; both are the top of the next iteration's list, and both become
measurable the moment the validation pairs arrive and `register_pair.py` runs.
