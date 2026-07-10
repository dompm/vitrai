# 019 — Scrape-audit: contamination in the catalog swatch corpus

Branch `research/delighting-scrape-audit`. Flagger in `../corpus/audit_flagger.py`; quarantine +
contact sheet in `../results/corpus/`. (Filename note: the task asked for `018-scrape-audit.md`,
but `018-luma-leakage-field.md` already exists on `research/delighting`, so this is `019`.)

Constructive-critical framing: the scraper is a hard-won, mostly-working harvester. This report
quantifies where it lets non-swatch imagery through, nails the root cause of the maintainer's
smoking gun, and proposes the **smallest** changes that would have caught each class. Nothing was
deleted; no scraper code was modified; the quarantine list is advisory.

## TL;DR

- **The smoking gun is real and has a one-line cause.** `get_best_image_url()` returns
  `product['images'][0]` unconditionally. For Bullseye's *reaction* product lines the Shopify
  merchandiser orders the **fired reaction-test tile photo first** and the actual sheet second, so
  the scraper stores the chemistry-demo, not the swatch. Confirmed end-to-end against the live
  product JSON (§1).
- **Reactive-line verdict: 6 of 20 registry `reactive` entries are test-fire images** — all six are
  Bullseye *non-iridescent* variants (Reactive Cloud ×2, Reactive Ice ×2, Red Reactive ×2). The 4
  Bullseye *iridescent* reactive variants lead with a real (pale) sheet and are clean; the 8
  Wissmach + 2 Youghiogheny "reactive" entries are all clean sheets. Add the sibling **Alchemy**
  line (8 entries, **all 8** are fired-tile demos) and the Bullseye reaction-demo contamination is
  **14 registered images** (+ their size-variant duplicates).
- **Random stratified audit (n=135, hand-verified): pooled contamination 4.4% [2.1–9.4%].** But it
  is wildly non-uniform: Wissmach/Oceanside/Youghiogheny ≈ 0%, Bullseye ≈ 3%, and **SGE ≈ 33%
  [15–58%]** — SGE is a different problem in kind (non-glass junk), not degree.
- **Flagger (`audit_flagger.py`, no ML): precision 1.00 / recall 0.86** for the test-fire class on
  the hand-labeled reactive+alchemy set (n=28); recall → 1.00 when unioned with a name-based
  blocklist. Ran corpus-wide → **168 advisory flags** in `swatch_quarantine.json`.
- **Registry↔file: 0 missing files, but 72 duplicate-image groups (145 rows) and 1,819 orphan
  files** (§5). The tracker's printed *"Purity Rate: 100% … zero non-sheet merchandise"* is
  falsified by this audit.

## 1. Root cause of the smoking gun (image-pick logic)

The scraper's image selection is a single function:

```python
def get_best_image_url(product):
    images = product.get('images', [])
    if images:
        src = images[0].get('src', '')   # <-- always position 1, no swatch check
        ...
```

Every manufacturer branch calls this once per product and stores the result. There is **no
inspection of what `images[0]` depicts** — no whiteness/tile check, no preference among a product's
images, no fallback.

End-to-end trace of the maintainer's case (`Reactive Ice Transparent, Thin-rolled, 2 mm`, registry
id `bullseye-0010090050f1010`, product handle `reactive-ice-transparent-thin-rolled-2-mm-fusible`):

| position | file | what it is |
|---|---|---|
| **1 (picked)** | `001009-0050-F_01.jpg` | fused reaction-test tiles (teal + blue rounded squares with dark reacted centers) on a near-white ground |
| 2 (skipped) | `001009-0050-F_02.jpg` | the actual product **sheet** swatch |

`crop_box: null`, `cropped: false` — Bullseye Cathedral images are stored uncropped, so the tile
photo is stored verbatim. The pattern generalizes because **for the non-iridescent reactive and all
alchemy products the merchandiser leads with the reaction demo** (it is the visually striking image
that sells a *reactive* glass); the iridescent reactive variants happen to lead with the sheet,
which is exactly why they escaped. This is a merchandising-order dependency the `[0]` rule cannot
survive.

## 2. Contamination taxonomy + stratified visual audit

Classes used (I inspected every tile in every sheet below; sheets archived in the scratchpad):

| class | what it is | where |
|---|---|---|
| clean sheet swatch | uniform, edge-to-edge glass | the corpus majority |
| reaction / test-fire tiles | fired color squares on white (chemistry demo) | Bullseye reactive/alchemy |
| composite / streamer / confetti | sparse frit/streamers on a clear/white base — correct photo, not a uniform sheet | Bullseye collage/fracture/chopstix |
| product-on-white | front-lit single sheet with drop shadow on white studio ground | Bullseye pale lines, SGE, some Oceanside |
| non-glass junk | jugs, ornaments, tools, came, charms, sunglasses, sealant cans, scrub pads | SGE only |
| installed / lifestyle | finished window/panel with a scene behind it | SGE only |
| iridized-surface / front-lit | rainbow coating shot to show the finish (per report 015 §2) | Oceanside/Youghiogheny/Wissmach subsets |

**Stratified random sample (30 per registered manufacturer + 15 SGE, seed 42), hand-verified:**

| manufacturer | k/n contaminated | rate | 95% Wilson CI | notes |
|---|---:|---:|---|---|
| Bullseye | 1/30 | 3.3% | [0.6%, 16.7%] | the one hit was a reactive test-fire size-variant |
| Oceanside | 0/30 | 0.0% | [0.0%, 11.4%] | clean; some iridized-finish shots (glass, not junk) |
| Youghiogheny | 0/30 | 0.0% | [0.0%, 11.4%] | clean; note `yf7937` *looks* like a flower but is real streaky glass |
| Wissmach | 0/30 | 0.0% | [0.0%, 11.4%] | cleanest, matches 015's "uniformly backlit" read |
| **SGE** | **5/15** | **33.3%** | **[15.2%, 58.3%]** | glass gems, metal picks, installed scene, glass funnel, metal spatula |
| **pooled** | 6/135 | 4.4% | [2.1%, 9.4%] | dominated by SGE |

Caveats: (i) small n per cell — the CIs are wide, treat the point rates as order-of-magnitude;
(ii) samples are drawn per-**file**, so size-variant duplicates can be drawn (correct for a per-file
corpus rate); (iii) the random rate **understates** the risk of the specific Bullseye reaction/
composite product lines, which are a small corpus fraction that random sampling barely hits — see
the targeted audit below.

**Targeted suspect audit (all entries, not a sample):**

- `reactive` (20 entries): **6 test-fire** (Bullseye non-iridescent), 14 clean. → 30% of the family,
  60% of Bullseye's reactive.
- `alchemy` (8 entries): **8 test-fire** fired-tile demos (before/after silver→gold/bronze).
- `collage`/`fracture`/`streamer`/`chopstix`/`lacy`/`on white` (34 entries): a whole **composite/
  streamer class** — real Bullseye products, but the photo is sparse confetti or thin streamer lines
  on a clear/white base, *not* a uniform sheet; most are mis-labeled `Cathedral` by
  `classify_glass()`. The image is correct, so this is a taxonomy/coverage problem, not an
  image-pick bug.
- `ice` (66 entries): mostly fine (Clear Ice / Crystal Ice are near-clear glass); the reactive-ice
  subset is the test-fire one above.
- SGE (15 sampled of 236): non-glass junk as above; 015's qualitative "mixed bag" finding
  reproduced quantitatively.

Worst-offenders contact sheet (committed, downscaled): `../results/corpus/scrape_audit_worst_offenders.jpg`.

## 3. Automatic flagger — `audit_flagger.py`

Cheap, ML-free, designed around the smoking-gun signature: **near-white background fraction +
connected-component count/compactness on the non-white foreground**, with a foreground-saturation
gate to separate vivid reaction tiles from genuinely pale sheets. A clean backlit swatch is
edge-to-edge color (white_frac ≈ 0, one frame-filling component); a test-fire photo is mostly white
with a few compact, vivid blobs.

Reason codes emitted: `test_fire_tiles` (high-confidence image heuristic), `product_on_white`
(weak/advisory — front-lit single sheet **or** non-glass junk on white), plus two name-based codes
(`reaction_demo_line`, `composite_streamer_line`) that recover the frame-filling demos the image
heuristic misses.

**Validation (hand-labeled reactive+alchemy set, n=28; 14 true test-fire):**

| detector | TP | FP | FN | precision | recall |
|---|---:|---:|---:|---:|---:|
| image heuristic (`test_fire_tiles`) on reactive only (n=20, 6 pos) | 6 | 0 | 0 | **1.00** | **1.00** |
| image heuristic on reactive+alchemy (n=28, 14 pos) | 12 | 0 | 2 | **1.00** | **0.86** |
| image ∪ name blocklist (reactive+alchemy) | 14 | 0 | 0 | 1.00 | **1.00** |

The 2 recall misses are the frame-filling double-tile Alchemy amber shots (`001016-0030/0050`), whose
tiles are large enough to push `fg_frac` past threshold — the name rule catches them. No clean
swatch was flagged as `test_fire_tiles` in the whole corpus scan (precision held at 1.00).

**Corpus-wide run** (`--all-files`, includes unregistered): **168 flags** →
`../results/corpus/swatch_quarantine.json`.

| reason code | count | reading |
|---|---:|---|
| `test_fire_tiles` | 50 | reaction tiles + a few product-on-white leaks; 18 unique registered files |
| `reaction_demo_line` | 10 | Bullseye reactive/alchemy non-iridescent (name) |
| `composite_streamer_line` | 33 | Bullseye collage/streamer/fracture/chopstix (name) |
| `product_on_white` | 94 | **advisory**: front-lit pale sheets **and** SGE non-glass junk — review, don't auto-drop |

Honest limitation: the flagger targets the **white-ground** signature. It catches only **37/236
SGE** images — SGE's installed-window/lifestyle/streaky-glass junk is not on white and slips
through. Consistent with 015's verdict: **SGE needs manual curation**, not a heuristic.

## 4. Minimal patches (smallest change per class — descriptions, not a rewrite)

**Patch 1 — image-pick guard (fixes the smoking gun; ~10 lines).** Do not blindly take `images[0]`.
Minimal general form: after download, run the flagger and, if the picked image is flagged
`test_fire_tiles`, retry with the product's next image:

```python
# in download_and_calibrate_image, after saving `filepath` and before returning:
from audit_flagger import analyze_image, flag_signals
if 'test_fire_tiles' in flag_signals(analyze_image(filepath)) and len(product_images) > 1:
    # re-fetch product_images[1] into filepath and re-validate; fall through if still flagged
```

This requires threading the product's full image list into the download call (currently only the
one URL is passed). It would have fixed all 14 reaction-demo images with zero effect on clean
products (flagger precision 1.00). Cheaper name-only alternative if you don't want a runtime
image check: for Bullseye products whose title matches `reactive|alchemy` **and** not `iridescent`,
pick `images[-1]` (position 2 = the sheet) — narrower, but no PIL pass at scrape time.

**Patch 2 — post-download validation hook (defense in depth for the whole non-swatch class).**
Gate registration on the flagger: if `flag_signals(...)` returns anything other than
`product_on_white`, set `status = "Quarantined"` instead of `"Downloaded"` and skip the registry
`append` (keep the file on disk for audit). This turns the audit's advisory list into a build-time
guard and would stop test-fire tiles, composites, and on-white SGE junk from entering the registry,
while leaving borderline product-on-white pale sheets in with a review flag.

**Patch 3 — extend the junk filter + fix the composite taxonomy.** `EXCLUDE_TERMS` is title-keyword
based and misses SGE's non-glass merchandise: add `ornament, tree, wreath (present), gem, nugget,
bead, pick, charm, sunglass, spatula, scrubber, pad, sealant, rondel, ball`. Separately, stop
mis-labeling the Bullseye composite lines: give `classify_glass()` a `Composite` bucket for
`collage|fracture|streamer|chopstix|lacy|on white|frit` and either exclude it from the uniform-swatch
corpus or tag it so downstream code (color/texture stats, classifier training) can hold it out —
today they land in `Cathedral` and poison per-class color statistics with clear-plus-confetti.

(Bonus, non-top-3: the dedup key `(mfg, code+thickness)` treats identical-photo thickness variants
as distinct rows — add a content-hash collapse so 145 duplicate rows fold to ~73; and the 236
`sge-*` files are **orphans from a previous scraper generation** the current `main()` never
produces — either register SGE properly or purge the stale files, and correct the tracker's false
"100% purity" line.)

## 5. Registry ↔ file consistency

- **Missing files: 0.** All 1,381 registry `local_image` paths exist on disk.
- **Orphan files: 1,819** (57%) on disk with no registry row. This is 015's "43% naive coverage"
  restated: 1,381/3,200 = 43% are registered; the rest are `fhalf`/`ffull`/`6x12` size-variant
  crops of an *already registered* SKU (recoverable by suffix-stripping, per 015) **plus 236 SGE
  orphans** (unrecoverable — no metadata, and per §2 not even all glass).
- **Duplicate images: 1,082 byte-identical hash groups covering 2,746 files.** Most are
  size-variant crops re-saving the same source photo. Critically, **72 groups (145 registry rows)
  are duplicate images under *different registered SKUs*** — Bullseye reuses one photograph across a
  color's thickness variants (`-0030`/`-0050`/`-0060`), and the dedup formula key keeps thickness in
  the identifier, so they never collapse. Net: the registry over-represents ~73 distinct photos as
  145 rows (~5% inflation) — matters for any "one row = one physical sheet" assumption and for
  train/val splitting (identical images can straddle the split).

## Reproduction

```
cd research/delighting/corpus
python3 audit_flagger.py --assets <checkout>/frontend/public/assets \
    --out ../results/corpus/swatch_quarantine.json --all-files
# analyze_image / flag_signals are importable for per-image calibration.
```

Corpus (`frontend/public/assets/{catalog_images,glass_swatch_registry.json}`) is gitignored on
`main`; accessed read-only from an existing checkout, not committed, not modified. The scraper
(`scripts/build_swatch_library.py`) was read only — not modified.
