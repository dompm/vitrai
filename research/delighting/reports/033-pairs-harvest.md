# 033 — FULL Delphi real-pairs harvest: dataset built, unbiased numbers vs 030's estimates

Branch `research/delighting-033`. Code in `../realpairs/` (`harvest_033.py`,
`contamination_033.py`, `aggregate_033.py`, `contact_sheet_033.py`,
`vangogh_panels_033.py`); dataset card in `../docs/REAL_PAIRS_DATASET.md` §9;
committed evidence in `../realpairs/results/` (manifest_033.json,
contamination_033.json, aggregate_033.json, vangogh_validation.json,
panels_033/). Raw full-res images live ONLY in the gitignored
`../realpairs/data/images/` (local disk, same posture as synthetic renders);
only downscaled panels are committed; nothing is redistributed.

Executed under the maintainer-approved Wayback-based research-use posture
(report 030 §5-6's GO conditions). Live-site load: 1,485 image GETs at a
measured 0.42 req/s average (sequential, ~1 s sleep between requests, normal
UA), ~59 minutes — under the census's planned envelope, pages never touched
the live storefront (Wayback only).

## 0. Headline

**254 unique products, 1,491 full-res images, 4,668 within-product pairs
examined. After all contamination screens: 145 registrable same-region
cross-capture sheet pairs across 64 products, plus ~1,850 statistics-only
same-product pair candidates (805 of them clean×wild).** That is two orders
of magnitude more real cross-capture data than the project had before 030
(one suncatcher pair), but materially below 030's forecast (~300 registrable
after attrition). The gap decomposes cleanly — see §4: 030's 60%
registrability was measured on a favorably-selected 15-product sample, and
its attrition guess (~20%) badly underestimated how much of the naive pair
count is stock photos, finished products, and disguised same-photo crops
(32% of raw cross_capture pairs died in screens).

## 1. What was run

1. **Discovery, full set:** crawl.py against all 394 Wayback-discoverable
   sheet-product URLs (030 had sampled 220). 366 fetched, 276 parsed with
   images, **254 unique product_ids** after dedup (Delphi reuses a photo-id
   across thickness/size variants). The 90 parse failures are pre-2015 page
   templates (older markup without the `data-thumbnail` gallery structure) —
   recoverable with a legacy parser, not attempted this iteration.
2. **Fetch:** full-res (1500×1500) hero + gallery images per product, ~1 req/s,
   resumable/idempotent keyed by product_id, checkpoint commits every ~10 min
   during the ~1 h background run.
3. **Classify:** classify.py's calibrated capture-type heuristic at full res
   (report 030 §1.2: 87% clean/wild binary accuracy at full res).
4. **Register:** exhaustive within-product pairwise ORB + homography
   (pairwise_matrix.py's method), 4,668 pairs, with same-photo derivation
   classification per 030 §2.1.
5. **Screen:** six contamination modes (§3), four of them from the
   maintainer's review of the 030 preview, two found during this
   iteration's validation of those four.

## 2. Unbiased census numbers (full harvest, full-res classifier)

| metric | 030 (census/sample) | 033 (full, unbiased) |
|---|---|---|
| products parsed | 157 (of 220 sampled) | **254** (of 394 discovered) |
| images | 872 (thumbs) | **1,491** (full-res) |
| images/product | 5.5 | **5.9** |
| ≥2 distinct capture types | 77.1% | **77.6%** |
| ≥1 clean AND ≥1 wild image | 73.2% | **76.0%** |
| label mix | window 66.6% (thumb-res, inflated) | **window 42.9 / closeup 36.8 / shop 18.2 / lightbox 1.8%** |

030's structural claims survive at scale almost unchanged: three quarters of
products carry a clean+wild candidate, and true `lightbox` studio shots are
rare (1.8% — even below 030's 5-12% band), confirming the dataset is
wild-wild rich and clean-reference poor. The full-res label mix lands where
030's calibration predicted (its thumb-res window inflation is gone).

Per-brand products (images): clear-textured-glass 88 (474), tiffany-today 42
(303), uro 30 (199), van-gogh 29 (131), wissmach 26 (184), kokomo 17 (76),
armstrong 13 (60), specialty-finish 7 (48), delphi-superior 2 (16).

## 3. Contamination screens (maintainer-caught + validation-caught)

The maintainer's review of the 030-sample preview named four modes; building
their screens surfaced two more. All are advisory annotation layers in
`contamination_033.json` — nothing deleted. Cross-capture pair kills below
overlap (a pair can die of several causes); the survivor count is exact.

| mode | screen | scale | cross-capture pairs killed |
|---|---|---:|---:|
| finished-product gallery shots | tail-slot flag (index ≥ 6), positional proxy | 45 pairs flagged | 45 |
| **line stock photos** (validation-caught) | cross-product perceptual-dhash duplicates | 142 images / 38 groups | 12 |
| lineup / product-on-white | report 019's audit_flagger reused verbatim | 133 images | 30 |
| mirror (non-transmissive) | title keyword | 3 products (all MLW) | 0 |
| multi-sheet listings (packs/samplers) | title keyword | 6 products | 0 |
| **suspect same-photo** (validation-caught) | mad<15 ∧ inliers≥200 | 16 pairs | 16 |
| **total** | | | **213 → 145 surviving** |

**Mode-1 validation on the Van Gogh line** (the maintainer's 186196 example),
against 99 eyeball-labeled images across all 29 Van Gogh products
(`vangogh_validation.json`, panels committed): 67 of 99 images are finished
mosaics/vanities/collages — the line's galleries are 2/3 non-sheet. Screen
recall on those 67: tail-slot alone **34%** (the maintainer was right: the
vases sit in slots 2-4), lineup screen 16%, **dhash stock screen 91%,
combined 96% (64/67), zero false positives** on the 32 real sheet images.
The decisive discovery: Delphi reuses the SAME stock photos across every
product in a line (byte-identical or re-encoded), so cross-product duplicate
hashing catches finished-product shots position-independently. The 3 misses
are one vase re-encode with a divergent dhash and two pack-lineup shots
unique to 193881 (whose product-level multi_sheet_listing flag covers them
anyway).

Other maintainer items, resolved: **220063's fan-of-sheets collage** — caught
by the reused audit_flagger (`product_on_white`), and the product itself is
mirror-excluded. **Mirror exclusion** removes 3 products / 21 images; no
other non-transmissive finish appears in the crawled categories (the other 4
MLW "hand-stained" products are transmissive). **186204's window→shop
mislabel** — confirmed and systematic: in the Van Gogh eyeball set, 5 of 8
shop-rack sheet shots are labeled `window`; window/shop confusion at this
severity was already in 030's calibration (77% strict accuracy; clean/wild
binary unaffected — all these images are correctly wild).

Validation-caught mode 5 (suspect same-photo) matters for anyone consuming
`kind == "cross_capture"` raw: on low-gradient CLEAR glass, hero-as-crop
duplicates pass the 030 same-photo gate (mad<10 ∧ grad_corr>0.35) because
grad_corr collapses on smooth texture (corpus median 0.12). Eyeball-confirmed
on 174075 (mad 4.0 at 400 inliers = crop of the same photograph). The 16
flagged pairs are 7.5% of raw cross_capture, concentrated in
clear-textured-glass (9).

Mode 6 (variant relistings): dhash also exposed Delphi's Spectrum→Oceanside
"96 COE" relistings sharing hero+gallery photos across two product_ids
(175010/234263 detected conservatively; 174130/230307 and 174974/234255 are
the same phenomenon but hero-less in shared groups, so their shared images
sit in the stock list — the safe direction, pairs killed rather than
double-counted).

## 4. Honest reconciliation vs 030's forecast

030 §3 forecast for this crawl: ~330-350 parsed products, ≈1,900 images,
~200 products / ~380 registrable pairs before attrition, "conservative
planning number ~150 products / ~300 registrable pairs". Actuals:

- **Products: 254 vs 330-350.** 030 extrapolated its 85% parse rate to all
  394 URLs, but the unsampled remainder skewed old: 25% of the full URL set
  parses only to pre-2015 templates vs 18% in 030's sample, and variant
  dedup (not in 030's arithmetic at all) removes 22 more.
- **Images: 1,491 vs ≈1,900** — follows directly from the product shortfall
  (images/product actually came in higher, 5.9 vs 5.5).
- **Registrable pairs: 145 surviving (213 raw) vs ~300-380; products with
  ≥1: 64 (25%) vs 030's 60%.** Two compounding over-estimates: (i) 030's
  registrability was measured on 15 products hand-picked for high image
  count and ≥2 capture types — a favorable stratum. The unbiased rate on all
  254 is 38.6% raw, 25% after screens. (ii) 030 guessed attrition from
  finished-product/opal/reuse at ~20%; measured, the screens kill 32% of raw
  cross_capture pairs, and the two modes 030 didn't know about (stock
  photos, clear-glass same-photo leaks) account for 28 of the 68 kills.
- **Statistics-only: ~1,850 candidate pairs across 213 products vs 030's
  ~700-1,000 across 240-260.** The one number that came in ABOVE forecast —
  exhaustive pairwise enumeration finds more non-registrable same-product
  pairs per product than 030's per-product estimate assumed. Caveat: these
  are same-PRODUCT pairs with both images unflagged; same-SHEET identity is
  unverified for the 31.5% of products with the opal/streaky caution
  (report 030 §2.3's 238607 lesson).
- **Pair-type mix:** of the 145 survivors, window×window and window×closeup
  dominate (consistent with 030 §2.2's finding that ORB succeeds between
  wild shots at compatible zoom). Brand skew is severe: uro 65 + tiffany-
  today 40 + clear-textured 29 = 92% of surviving pairs; van-gogh
  contributes 1 despite 29 products (its galleries are stock-photo-heavy),
  and 32 of the 64 products with survivors carry the opal/streaky caution
  (ripples/mottles register best — they are also the sheets where identity
  needs care; for herringbone ripples the visible layout IS per-sheet, so
  these are mostly usable, unlike smooth opal mottles).

Take the planning number as: **145 registrable pairs / 64 products (13 of
them in iter-034's frozen holdout), ~800 clean×wild statistics-only pairs**
— roughly half of 030's conservative guess on the registrable axis, 1.5-3×
on the statistics-only axis.

## 5. Contact sheets (committed evidence)

`results/panels_033/best_01..10_*.jpg` — the 10 best surviving pairs
(A | B | checkerboard blend), max 2 per product, post-screen: e.g. 203548
Kokomo Wavolite window↔window reframe (400 inliers, mad 19), 230189 Corteza,
239940 Uro herringbone, 235106 Wissmach Flemish closeup↔window (mad 71 —
strongly different illumination, cleanly registered). One flagged-in-caption
borderline kept deliberately: 230233 Van Gogh "Sparkle Shift" — its closeup
is a multi-hue demo collage of the color-shift glass; one collage tile
registers against the window shot. `worst_01..04_*.jpg` are the borderline
diet: threshold-inlier (21) registrations including an opal-mottle
shop↔closeup with mad 9 (identity-suspect per §3) and a finished-product
tail pair.

## 6. Consumption notes (what changed for the three consumers in 030 §4)

- The **real cross-capture benchmark** should read pairs from
  `manifest_033.json` filtered by: `kind == cross_capture` AND none of the
  §3 flags (helper predicate documented in the dataset card §9.3). 145 pairs,
  64 products.
- The **neural track** gets its held-out-product split from iter-034's
  frozen reservation (sha1(pid)%5==0): 55/254 products reserved, 13 of the
  64 pair-bearing products land in the holdout — per-brand counts recorded
  in §9.4 of the dataset card. armstrong (38%) and kokomo (12%) deviate most
  from 20%; iter-034 owns any topping-up decision (protocol v1.1).
- **Sim-to-real (clean-reference) remains the weak axis, now with a number:**
  27 lightbox images in the whole corpus (1.8%). 030's warning stands
  stronger — do not plan work that needs per-product studio references.

## 7. Files

- `../realpairs/harvest_033.py` — full-scale fetch+classify+register (resumable).
- `../realpairs/contamination_033.py` — the six screens; writes contamination_033.json.
- `../realpairs/aggregate_033.py`, `contact_sheet_033.py`, `vangogh_panels_033.py`.
- `../realpairs/results/manifest_033.json` — the committed dataset manifest (254 products).
- `../realpairs/results/{aggregate,contamination}_033.json`, `vangogh_validation.json`.
- `../realpairs/results/panels_033/` — best/worst contact sheets + Van Gogh validation panels.
- `../realpairs/data/` — gitignored raw images (368 MB) + full manifest with retry stubs.
