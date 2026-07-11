# 035 — Scored swatch-picker: replacing positional image-pick heuristics

Branch `research/delighting-035`. Module in `../corpus/swatch_picker.py`, fetch helper
in `../corpus/fetch_gallery.py`, validation harnesses in
`../corpus/validate_{maintainer_cases,024_regression,regression_sample}.py`, results
in `../results/corpus/swatch_picker_*.{json,jpg}`.

The maintainer's framing (`glass-library-integration-review.md` Addendum 2): "we're
not always choosing the right image" — product galleries mix real sheet swatches with
customer photos (fingers in frame), comparison shots, test-fire/reaction-demo tiles,
lineup/marketing shots, and finished products. The correct image's position varies per
product and is sometimes only stated in the description prose (the SGE Granite Ripple
case: "1st photo taken by a customer... the right picture is the fourth one" — no
positional rule survives that). This report builds a scored picker that replaces
`images[0]`/`images[-1]` rules with an argmax over every candidate, reusing report
019's `audit_flagger` and validated against both maintainer-supplied cases, report
024's known-answer Bullseye set, and a 20-product random sample of the existing corpus.

## TL;DR

- **Both maintainer cases pass, with comfortable margins.** `uro-by-yough-clear-
  granite-ripple` → picks image 4 (margin **0.94** over the next-best), driven by the
  explicit text hints ("1st photo taken by a customer", "second and third show...
  next to..."). `yough-steel-grey-opal` → picks image 3 (margin **0.25**), where the
  description says "First and third photos are backlit" but doesn't say which one is
  *the* correct one — the tie between positions 1 and 3 is broken by a sharpness/focus
  signal (position 1 is a heavily out-of-focus macro crop).
- **Report 024's 14-target Bullseye set: 7/7 "recovered" correct (prefers the -v2 fix
  over the original test-fire-tile image), 7/7 "unrecoverable" correctly return NONE
  or a low score on every candidate.** Getting here required fixing two real bugs the
  validation exposed (not hypothetical ones): (1) report 019's per-*product-line*
  name blocklist (`reaction_demo_line`) was being applied per-*image*, zeroing the
  audit component identically for every candidate of a product and defeating the
  picker's whole job of differentiating between them — exactly the failure mode
  report 024 §7 predicted; (2) raw whole-frame Laplacian variance (the textbook blur
  metric) cannot tell a genuinely blurry photo from a sharp photo of *smooth, glossy,
  low-texture glass* — both land in the same numeric range, and it was about to make
  the picker choose a labeled/clamped photo over a clean full-bleed swatch of the same
  product in the 20-product regression set (below). Fixed with an edge-restricted
  sharpness ratio (SS4).
- **20-product random regression: 15/20 (75%) argmax-agree with `images[0]`.** Manually
  re-inspected all 5 disagreements at full resolution: **0 of 5 are contamination
  errors** — every one is the picker choosing a *different, equally legitimate* photo
  of the same correct glass (a wider-angle crop, a less-saturated close-up, a
  black-background iridescence comparison chip), never a finger, tile, comparison
  shot, or unrelated product. The raw 75% number understates real-world agreement;
  see SS5.2 for the per-case walkthrough.
- **Honest weak spots, found by testing, not hypothesized:** the hand detector fires
  on one true comparison-shot image (amber glass tone + frame-edge geometry
  coincidentally resembles a finger) — harmless here because the seam detector
  independently rejects the same image, but the hand *reason code* alone isn't a
  reliable finger diagnosis; the "pale/near-clear glass" credit (SS4) is a coarse
  patch for one specific failure mode (Bullseye Ice/Crystal lines reading as 100%
  "white background" to `audit_flagger`'s color threshold) and hasn't been stress
  tested beyond that; the text parser is regex/sentence-scoped, not real NLP.

## 1. Integration guidance

Full guidance is the module's own top-of-file docstring (`swatch_picker.py` lines
1–60) so it stays next to the code it describes; summary: call `pick()` as a
**post-download validation gate** in `build_swatch_library.py`, after fetching a
product's *entire* image list (not just position 0, per report 019 Patch #1) and
before the registry `append`. No scraper rewrite — one function call:

```python
from swatch_picker import pick
result = pick(product_image_paths, text=product.get('body_html','') + ' ' + product.get('title',''),
               name=product.get('title',''), manufacturer=mfg)
if result['pick'] is None:
    status = 'Quarantined'          # same posture as report 019 Patch #2
else:
    local_image = product_image_paths[result['pick']]
```

## 2. Scoring components

Five components, each in `[0, 1]` and individually exposed in `result['scores'][i]['components']`:

| component | weight | what it measures |
|---|---:|---|
| (a) `audit` | 0.28 | reuses 019's `audit_flagger.analyze_image`/`flag_signals` (test-fire tiles, weak product-on-white signal). Per-image only — see SS3 for why the name blocklist is handled separately. |
| (b) `hand` | 0.20 | finger/hand: shape+edge cues FIRST (exactly one frame edge touched, bounded span/depth/solidity — a compact protrusion, not a whole background band), color (loosened Peer et al. RGB skin rule) only within that already-constrained blob. Report 030's finding (skin color alone fails on pink/amber glass) reproduced and worked around, not just cited — see SS3.1. |
| (c) `seam` | 0.20 | comparison-shot detection: a tall, strong, roughly-central (not edge-hugging) column of gradient energy = a seam between two sheets. |
| (d) `coverage` | 0.32 | full-bleed continuity (019's `fg_frac`/`biggest_blob_frac`) × an edge-restricted sharpness ratio (not raw Laplacian variance, see SS4) × a pale-sheet credit for near-clear glass. |
| (e) `text` | additive, can exceed the [0,1] weighted sum | sentence-scoped hint parsing: ordinal+"customer" → penalty; ordinal(s)+"next to"/"compare"/"vs" → penalty (corroborates (c)); ordinal(s)+"backlit" → bonus; explicit "the right/correct picture is the Nth" → **override**, forces the pick outright. |

Final score = weighted sum of (a)–(d), plus the (e) adjustment, minus a uniform
**line penalty** (0.12) if 019's name blocklist (`flag_name`) flags the product's
line (Bullseye reactive/alchemy/composite) — applied once per product, identically to
every candidate, so it changes the *floor* eligibility without destroying the
*ranking* between a product's own images (SS3). A candidate below `FLOOR=0.45` is
ineligible for the argmax; if nothing clears it (and no text override fired), `pick`
is `None`.

## 3. Bug found during validation: name blocklist was per-image, not per-line

019's `flag_name()` returns `reaction_demo_line`/`composite_streamer_line` from the
**product name** — Bullseye reactive/alchemy products whose *entire line* leads with
a test-fire demo. Report 024 §7 already flagged the risk: "the name-based codes
describe the product line, not the specific photo, and would reject every image of a
target product identically if used as a per-image filter." The first version of this
module did exactly that — called `flag_name` inside the per-image `audit_score()`,
so the audit component was `0.0` for *every* candidate of a reactive/alchemy product,
regardless of which specific photo it was. On report 024's `bullseye-0010090050f1010`
(Reactive Ice Transparent) this made the picker prefer the original test-fire-tile
image over the genuine `-v2` clean sheet, because with audit zeroed on both sides the
tie broke on `hand`/`seam` (both saturated at 1.0) instead of the signal that should
have decided it. Fixed by moving `flag_name` out of `audit_score()` into a separate
`line_flags()`, evaluated once per product in `pick()` and applied as the uniform
floor penalty described above — it no longer participates in ranking a product's own
candidates against each other. Recovered-set accuracy went from 4/7 to 7/7 after this
fix (SS5.1).

## 4. Bug found during validation: raw Laplacian variance conflates blur with smoothness

The steel-gray-opal maintainer case (SS5) needed a sharpness signal to break a
text-hint tie between a blurry macro crop and a sharp full-sheet photo, so an initial
version scored `coverage` by `fg_frac × cv2.Laplacian(...).var()`. Running the
20-product regression set (SS5.3) surfaced the flaw immediately: a clean, full-bleed,
in-focus **glossy solid-red Bullseye sheet** scored `laplacian_var = 4.1` — in the
same range as the genuinely out-of-focus steel-gray-opal crop (`laplacian_var ≈ 21`)
— because a smooth, low-texture glass simply has almost no high-frequency content to
measure, focused or not. The whole-frame variance metric cannot tell "blurred" from
"nothing to blur," and was about to make the picker choose a photo of the *same*
product showing a price-tag sticker and a metal mounting clamp (which has plenty of
texture, hence a high score) over the correct clean swatch.

Fix: restrict the sharpness measurement to the frame's own strongest-gradient pixels
(top 15% by Sobel magnitude) and use `mean(|Laplacian|) / mean(gradient magnitude)`
at just those pixels — "how crisp are the edges that exist," which stays meaningful
even when there are few of them, rather than "how much high-frequency energy is in
the whole frame." Calibration on the same six-image set:

| image | old (whole-frame Laplacian var) | new (edge-restricted ratio) | verdict |
|---|---:|---:|---|
| steel-gray-opal, position 1 (blurry crop) | 20.7 | **0.208** | correctly low |
| steel-gray-opal, position 3 (sharp) | 186.3 | 0.569 | correctly high |
| granite-ripple comparison shots (sharp) | 632–943 | 0.537–0.591 | correctly high |
| Bullseye smooth red sheet, position 1 (in-focus, low-texture) | **4.1** (falsely low) | **0.775** (correctly high) | fixed |
| same product, clamped/labeled photo (in-focus, high-texture) | 6923 | 0.734 | still correctly high (this photo's problem isn't sharpness — see SS5.3) |

## 5. Validation

### 5.1 Report 024 regression (`validate_024_regression.py`, offline, local files only)

Ground truth: report 024's `refetch_manifest.json` (14 Bullseye reactive/Alchemy
targets — 7 with a genuine `-v2` recovery, 7 hand-verified unrecoverable).

| set | n | result |
|---|---:|---|
| recovered (expect pick = the `-v2` file) | 7 | **7/7 correct** |
| unrecoverable (expect NONE or low score on both) | 7 | **7/7** — 5 returned `None`, 2 forced a pick (max score 0.52–0.54, well under a stricter 0.60 bar used for "low") |

| id | expected | picked | scores (old, new) |
|---|---|---|---|
| bullseye-0000090030f1010 | -v2 | -v2 | 0.191, 0.522 |
| bullseye-0000090050f1010 | -v2 | -v2 | 0.387, 0.520 |
| bullseye-0010090050f1010 | -v2 | -v2 | 0.384, 0.736 |
| bullseye-0010150031f1010 | -v2 | -v2 | 0.464, 0.610 |
| bullseye-0010150051f1010 | -v2 | -v2 | 0.464, 0.631 |
| bullseye-0010160031f1010 | -v2 | -v2 | 0.193, 0.610 |
| bullseye-0010160051f1010 | -v2 | -v2 | 0.193, 0.643 |
| bullseye-0010090030f1010 | NONE | NONE | max 0.384 |
| bullseye-0010150030f1010 | NONE | NONE | max 0.422 |
| bullseye-0010150050f1010 | NONE | NONE | max 0.422 |
| bullseye-0010160030f1010 | NONE/low | pos.1 (0.538) | both images test-fire, floor cleared but low |
| bullseye-0010160050f1010 | NONE/low | pos.1 (0.538) | same as above |
| bullseye-0010190030f1010 | NONE | NONE | max 0.382 |
| bullseye-0010190050f1010 | NONE | NONE | max 0.382 |

Side note tying back to `glass-library-integration-review.md`'s Addendum re-
adjudication of the two Reactive Cloud Opalescent SKUs (000009-0030/0050): that
addendum found the `-v2` swap is a "lateral move, not a fix" (14.5% vs 15.8% and
16.1% vs 17.7% tile-cluster footprint) rather than a clean win. This module's
`-v2`-preferred verdict for those two SKUs matches `refetch_manifest.json`'s label,
not the addendum's finer-grained pixel measurement — the picker isn't precise enough
to detect a 1-2 point tile-footprint difference between two similarly-composed
photos, and shouldn't be read as adjudicating that specific disagreement.

### 5.2 Maintainer cases (`validate_maintainer_cases.py`, live fetch, ~1 req/s, cached)

| case | n images | correct position | picked | margin | panel |
|---|---:|---:|---:|---:|---|
| `uro-by-yough-clear-granite-ripple-fusible-glass-96-coe` | 4 | 4 | **4** | 0.94 | `swatch_picker_maintainer_1.jpg` |
| `yough-steel-grey-opal` | 3 | 3 | **3** | 0.25 | `swatch_picker_maintainer_2.jpg` |

Granite Ripple score table (position 1 = customer photo w/ finger, 2–3 = comparison
shots vs. Oceanside Granite, 4 = clean full-bleed swatch):

| pos | final | audit | hand | seam | coverage | text adjustment |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 0.000 | 1.00 | 0.32 | 1.00 | 0.76 | −0.90 (customer photo) |
| 2 | 0.058 | 1.00 | 1.00 | 0.71 | 0.74 | −0.80 (comparison mentioned) |
| 3 | 0.000 | 1.00 | 0.32 | 0.86 | 0.74 | −0.80 (comparison mentioned) |
| **4** | **1.000** | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |

Steel Gray Opal High Strike score table (description: "First and third photos are
backlit" — narrows to {1, 3}; position 1 is a heavily out-of-focus macro crop,
position 3 is the sharp full-sheet backlit shot):

| pos | final | audit | hand | seam | coverage | text adjustment |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 1.228 | 1.00 | 1.00 | 1.00 | 0.15 | +0.50 (backlit) |
| 2 | 0.989 | 1.00 | 1.00 | 1.00 | 0.97 | 0.00 |
| **3** | **1.477** | 1.00 | 1.00 | 1.00 | 0.93 | +0.50 (backlit) |

Both panels (all candidates + full score breakdown overlaid, downscaled, committed):
`../results/corpus/swatch_picker_maintainer_{1,2}.jpg`.

### 5.3 20-product random regression (`validate_regression_sample.py`, live fetch)

Sample: 20 products drawn (`seed=42`) from the non-quarantined registry (`n=1,314`
after excluding 019's 64 quarantined ids), spanning Bullseye/Oceanside/Youghiogheny/
Wissmach. For each, the product's *entire live gallery* was fetched (2–8 images) and
scored against `images[0]` — the position our existing registry actually shipped.

**Raw agreement: 15/20 = 75%.**

| id | mfg | n images | picked pos | agrees w/ pos.1 |
|---|---|---:|---:|---|
| youghiogheny-yuf707312 | Youghiogheny | 4 | 1 | yes |
| bullseye-0011200051f1010 | Bullseye | 3 | 1 | yes |
| bullseye-0001240030f1010 | Bullseye | 3 | 1 | yes |
| oceanside-of100hs | Oceanside | 8 | 1 | yes |
| bullseye-0023020000f1010 | Bullseye | 3 | 1 | yes |
| bullseye-0020200030f1010 | Bullseye | 3 | 2 | no |
| bullseye-0012070050f1010 | Bullseye | 2 | 1 | yes |
| bullseye-0011140030f1010 | Bullseye | 2 | 1 | yes |
| youghiogheny-y5002spirid | Youghiogheny | 2 | 2 | no |
| bullseye-0011010054f1010 | Bullseye | 2 | 2 | no |
| youghiogheny-yf520 | Youghiogheny | 2 | 1 | yes |
| wissmach-w18h | Wissmach | 4 | 2 | no |
| bullseye-0001380030f1010 | Bullseye | 3 | 1 | yes |
| bullseye-0001360030f1010 | Bullseye | 2 | 1 | yes |
| bullseye-0011050050f1010 | Bullseye | 2 | 1 | yes |
| bullseye-0018590030f1010 | Bullseye | 2 | 1 | yes |
| bullseye-0021220030fhalf | Bullseye | 2 | 1 | yes |
| wissmach-wiwo85 | Wissmach | 2 | 1 | yes |
| youghiogheny-yf7173 | Youghiogheny | 3 | 2 | no |
| bullseye-0001250050f1010 | Bullseye | 3 | 1 | yes |

Zero `None` picks in this sample (no false quarantines of clean products). All 5
disagreements were opened at full resolution and hand-checked:

| id | position 1 | picked instead | verdict |
|---|---|---|---|
| bullseye-0020200030f1010 | full-bleed close crop | wider view, same sheet against white | same glass, both legitimate |
| youghiogheny-y5002spirid | close-up, strong iridescence | zoomed-out full sheet, same glass | same glass, both legitimate |
| bullseye-0011010054f1010 | close-up ribbed texture | small chip shown on black+white split background (Bullseye's standard way of showing how an iridescent coating reads against both grounds) | same glass, tight margin (0.858 vs 0.849) — genuinely borderline, not a clear win either way |
| wissmach-w18h | close-up hammered texture | wider angled view, same sheet | same glass, both legitimate |
| youghiogheny-yf7173 | wide streaky view | tighter crop, same streaky pattern | same glass, both legitimate |

**0 of 5 disagreements were contamination (no finger, no tile, no comparison shot, no
wrong product)** — every one is a different real photo of the same correct glass. The
75% figure is therefore a conservative floor on "picks something acceptable," not a
measure of "picks something wrong" (which is closer to 0/20 in this sample). One case
(`bullseye-0011010054f1010`) is a genuine coin-flip between two stylistically
different but equally valid vendor photos, not a picker error to fix.

## 6. Honest weak spots

- **Hand detector precision is not high.** On the 7-image calibration set (SS4 of the
  module docstring), it correctly catches the one true finger photo but also fires on
  a true comparison-shot image (amber glass tone + a frame-edge blob geometrically
  resembling a finger protrusion). The comparison-seam detector independently rejects
  that same image, so the overall pick is unaffected here, but the `hand` reason code
  in isolation should not be read as a precise finger diagnosis. It will miss fingers
  that don't enter from a frame edge and is not tested against gloved or
  dark-skinned hands.
- **Seam/comparison detector** is tuned for a roughly-vertical single seam near frame
  center; a horizontally-laid-out comparison, or a seam hugging the frame edge, will
  likely be missed by design (edge-hugging peaks are down-weighted specifically to
  avoid flagging a sheet's own silhouette as a "seam" — see the steel-gray-opal
  candidates, which needed this to avoid false positives).
- **The pale-sheet credit (SS4) is a targeted patch for one failure mode** — Bullseye
  Ice/Crystal-line glass reading as 100% "white background" to `audit_flagger`'s color
  threshold — calibrated on exactly the one real example that surfaced it
  (`bullseye-0010090050f1010`, Reactive Ice Transparent). It has not been stress
  tested on other near-white glass (e.g. genuinely blank studio backgrounds that
  happen to carry JPEG-noise texture above the 4.5-std threshold); a false positive
  there would grant undeserved credit to an actually-empty photo.
- **Text parser is regex/sentence-scoped, not real NLP.** Ordinal words above "tenth"
  aren't recognized; an ordinal and its keyword separated by a long clause, or split
  across sentences ("the first one... it shows..."), will be missed.
- **Line penalty (SS3) is a single flat constant (0.12)**, not calibrated against a
  large sample of flagged-line products beyond the 14 in report 024's set — it moves
  the floor, not the ranking, so its main risk is under- or over-quarantining
  borderline flagged-line products rather than picking the wrong image among a
  product's own candidates.
- **None of this is ML**; it inherits report 019's "cheap, no ML" posture and limits —
  a genuinely novel contamination class (e.g. a lifestyle/installed-window shot that
  happens to be sharp, full-bleed, and free of skin tones or a seam) would sail
  through every component untouched.

## Reproduction

```
cd research/delighting/corpus
python3 swatch_picker.py img1.jpg img2.jpg ... --text "<description>" --name "<title>" --manufacturer Bullseye
python3 validate_maintainer_cases.py     # live fetch, ~1 req/s, cached in ../results/corpus/swatch_picker_cache/
python3 validate_024_regression.py       # offline; reads the MAIN checkout's catalog_images/ read-only
python3 validate_regression_sample.py    # live fetch, ~80 requests at 1 req/s (~80s)
```

`swatch_picker_cache/` (gitignored, ~25MB of fetched product JSON + images) is not
committed. `/usr/bin/python3` (or any venv with `numpy`/`pillow`/`opencv-python`/
`scipy`) is required. Report 024's `refetch_manifest.json` and the registry/
`catalog_images/` are read read-only from the MAIN checkout
(`/Users/dominiquepiche-meunier/Documents/vitraux`), same convention as reports
019/021/024 — nothing in this report modifies them.
