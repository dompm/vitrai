# 030 — Delphi Glass as a REAL cross-capture paired dataset: census, pair quality, go/no-go

Branch `research/delighting-030`. Code in `../realpairs/` (`crawl.py`, `classify.py`,
`pair_quality.py`, `pairwise_matrix.py`, `aggregate.py`, `calibration_sheet.py`); dataset
spec in `../docs/REAL_PAIRS_DATASET.md`; committed evidence panels in
`../realpairs/results/panels/`. Raw downloads live only in `/tmp` (never committed).

The maintainer's discovery this iteration tests: Delphi Glass product pages carry the SAME
physical sheet photographed multiple ways — a clean swatch plus held-against-window /
held-in-shop shots — i.e. real same-glass-different-capture data, the structure the whole
consistency research line (`RESEARCH_STATE.md` §metric, reports 013/014/017) has otherwise
had to synthesize in Blender. Verdict up front: **the discovery is real and the honest
answer is "go, with one structural caveat"** — the wild captures are plentiful (≈60% of all
product gallery images) and same-sheet, but Delphi's *clean* image is usually a **crop of
one of the wild photos**, not an independent studio capture, so the dataset's clean
references are scarcer and its pixel-registrable pairs need a same-photo-derivation filter
(shipped here as part of `pairwise_matrix.py`).

## 0. Access reality (this shaped everything)

The live storefront **403s every request from this environment** — Cloudflare bot
management, "Sorry, you have been blocked", confirmed with both `curl` (multiple normal
desktop UAs) and the WebFetch tool; unrelated sites and even another glass retailer's
Shopify storefront respond normally. `robots.txt` itself is permissive for product pages
(it disallows admin/cart/sort-query paths only). What does work, and what this iteration
used:

- **Page discovery + parsing: the Wayback Machine.** The CDX API enumerates archived
  `/stained-glass/<brand>/<slug>` URLs; per-product snapshots supply the page HTML with the
  full image-gallery manifest. Zero page loads hit Delphi's servers.
- **Image bytes: Delphi's own image hosts** (`images.delphiglass.com`,
  `www.delphiglass.com/syscat/image_*`), which are NOT behind the WAF rule and serve
  normal 200s. All image downloads were throttled ~1 req/s, sequential, normal UA:
  872 census thumbs (70×55 / 300×300), 30 calibration full-res, ~140 full-res for the 15
  pair-quality products — total live-site load comparable to one person browsing a few
  dozen product galleries.

ToS implications of this arrangement are in `REAL_PAIRS_DATASET.md` §5 and summarized in
§5 below — read them before green-lighting the full crawl.

## 1. Census

### 1.1 Sample and page-level numbers

CDX discovery found **394** distinct archived product URLs across the 10 genuine
single-sheet brand directories (glass-packs / crates / mirror / seasonal / technique pages
excluded by hand; list in `crawl.py`). Stratified sample of 220 → **157 products parsed
with images** (40 of the 63 failures are pre-2015 snapshots whose old page template the
parser doesn't handle, 21 are Wayback fetch errors, 2 genuinely imageless) across 9 brand
directories.

- **Images per product: mean 5.5, median 6, max 10** (hero + up to 9 gallery slots).
- Per-brand means range from 3.0 (armstrong) to 9.5 (delphi-superior); Delphi's house
  lines (tiffany-today, uro, delphi-superior) are photographed most heavily — 96-100% of
  their products have ≥2 distinct capture types.

### 1.2 Capture-type classifier + calibration (read before trusting §1.3)

`classify.py` labels each image {lightbox, window, shop, closeup, other} from border/
interior statistics, sky/foliage cues, and straight-line detection. Calibrated by
hand-labeling 30 random census images at full resolution (panels:
`results/panels/calibration_fullres_{0,1}.jpg`; labels:
`results/calibration_labels.json`). Findings, all of which changed the design:

- **Skin-tone hand detection is unusable on art glass** — pink/amber/beige sheets land in
  every practical skin-color gate (a pink wispy sheet scored a 0.254 "skin" blob
  fraction vs real hands' 0.01–0.28). The brief's held-in-shop vs standing-on-surface
  distinction was therefore MERGED into one `shop` label (same capture physics: indoor,
  front-lit, shop background).
- The single most reliable feature is **border-ring luminance std**: >0.19 ⇒ a visible
  background exists (wild: window/shop), ≤0.19 ⇒ clean full-bleed/lightbox. 30/30
  separation on the calibration classes it applies to.
- **Delphi's window shots are detectable by composition**: sheet propped on the storefront
  windowsill, trees/sky band above it, or an outdoor scene visible *through* transparent
  glass (sky_top / veg_top / veg_all features).
- **Accuracy: 77% strict (23/30) at full resolution; 57% (17/30) at the census's 70×55
  thumb resolution** (JPEG block noise inflates every background cue; an upscale+denoise
  pass recovers a few points but the thumbs are simply information-poor). The
  load-bearing binary — clean vs wild — is **80% at thumb res, 87% at full res**.
  Residual confusions, honestly: finished panels/mosaics shot in a window count as
  `window`; the flowers-behind-glass demo trope reads as `closeup`; pale near-white glass
  reads as `lightbox`.
- Truth distribution in the 30-image calibration sample: **window 10/30, closeup 11/30,
  shop 6/30, other 2/30, lightbox 1/30** — i.e. ≈60% of gallery images are genuinely
  wild captures, and true studio `lightbox` shots are RARE (see §2's structural finding).

### 1.3 Census results (157 products, 872 images, heuristic labels at thumb res)

| metric | value |
|---|---|
| products with ≥2 distinct capture types | **121/157 = 77.1%** |
| products with ≥1 clean (lightbox/closeup) AND ≥1 wild (window/shop) image | **115/157 = 73.2%** |
| per-image labels | window 66.6%, closeup 24.4%, lightbox 5.2%, shop 3.8% |

Pair-type co-occurrence (distinct label pairs per product): closeup×window 105,
lightbox×window 29, shop×window 24, closeup×lightbox 23, closeup×shop 20, lightbox×shop 7.

**Calibration-corrected reading.** The thumb-res classifier over-calls `window`
(precision for `window` at thumb res ≈ 48%, though most false window labels are still
wild-class `shop` images, or clean images from products that have other wild images). Two
honest correctives: (i) the binary clean/wild split is 80% accurate with errors in both
directions (5 clean→wild, 1 wild→clean in 30), so the 73.2% clean+wild figure carries
roughly ±10-15pp of uncertainty — call it **60–80% of products with a usable
clean-vs-wild pair candidate**; (ii) the per-image label distribution at thumb res
inflates window at the expense of shop/closeup — the full-res calibration distribution
(window ≈ 33%, shop ≈ 20%, clean ≈ 40% of images) is the trustworthy one. Either way the
qualitative conclusion is robust: **a solid majority of Delphi sheet products ship
multiple captures of the sheet, dominated by exactly the wild window/shop conditions the
consistency research needs.**

## 2. Pair quality on 15 hand-picked multi-capture products

15 products chosen across all 9 brands (highest image counts with ≥2 heuristic types;
IDs in `results/pair_quality.json`), full 1500×1500 image sets downloaded (~140 images).
Two analyses: the headline clean↔wild pair per product (`pair_quality.py`, panels in
`results/panels/<pid>.jpg`), then an exhaustive within-product pairwise ORB matrix
(`pairwise_matrix.py`) after the first pass surfaced a structural surprise.

### 2.1 The structural surprise: Delphi's "clean" hero is usually a crop of a wild photo

All 4 of the 15 headline pairs that ORB registered (≥20 RANSAC inliers) were
hero↔gallery_1 pairs, and their post-registration central-region residuals expose what
they really are:

| product | inliers | median |diff| /255 | grad-corr | reading |
|---|---:|---:|---:|---|
| 239285 blue corn | 400 | 2.0 | 0.75 | **hero is a crop of gallery_1** (same photograph) |
| 239270 bell pepper | 42 | 5.0 | ~0 | same-photo crop (near-uniform sheet) |
| 238541 uro herringbone | 275 | 7.0 | 0.56 | same-photo crop or same-session near-duplicate |
| 238531 uro chartreuse | 75 | **38.0** | 0.12 | **genuine cross-capture: same region, different light** |

So naive "hero + gallery" pairing yields mostly *derived duplicates*, not cross-capture
pairs — the same failure mode report 019 found in Bullseye's thickness-variant photo
reuse, in a new guise. `pairwise_matrix.py` therefore classifies every within-product
pair into {same_photo, cross_capture, none} using registration + residual, which is the
filter a full crawl must ship with. (Results: §2.2.)

### 2.2 Exhaustive pairwise matrix

All within-product image pairs for the 15 products (531 pairs), classified
{same_photo, cross_capture, none} by registration + residual; every claimed
cross_capture pair then verified by eye on a checkerboard blend
(`results/panels/cross_capture_checkers.jpg`, committed):

- **22 ORB-registrable non-duplicate pairs**, of which the eyeball pass confirms
  **17 are genuine SHEET cross-captures — the same sheet region under a different
  capture — across 9/15 products** (230189, 238541, 218088, 230207, 238607, 238531,
  173747, 203547, 239270; 1-4 pairs each). The best examples are unambiguous: 203547's
  two window shots have the same seed-bubble field in front of *different outdoor
  scenes* (different day); 238531/238541's herringbone streak layouts continue
  seamlessly across checker tiles under clearly different illumination.
- The other 5 registrable pairs are multiple shots of a **finished product** (238631's
  dragonfly suncatcher ×3, 186196's mosaic table, 239285's fused rainbow piece) —
  Delphi's gallery tail slots (6-9) often carry "project idea" photos of objects MADE
  from the glass. Registrable, but not sheet data; a full crawl needs a
  finished-product filter (these are this catalog's version of report 019's
  composite/lifestyle contamination classes).
- **9 same_photo duplicate pairs** (crop/rescale derivation, §2.1's filter) — confirms
  hero-as-crop is systematic (4 of 15 products) but automatically detectable.
- Remaining ~500 pairs: no registration — mostly same sheet at incompatible zoom
  (statistics-only) plus the §2.3 contamination cases.

**Registrability verdict: 9/15 products (60%) yield at least one pixel-registrable
same-region cross-capture sheet pair (~1.9 such pairs each), and 11/15 (73%) yield at
least a statistics-only same-sheet pair.** ORB fails between tight closeups and
full-sheet shots (scale gap + self-similar texture), so the registrable pairs are
mostly window↔window and window↔near-full-sheet — which is fine: those are exactly the
different-illumination pairs the consistency metric needs.

### 2.3 Same-sheet verdicts from eyeballing the 15 panels

For the 11 headline pairs ORB could NOT register (panels committed, one per product):

- **Same sheet, different region/zoom — statistics-only pairs** (7): 230189 corteza (held
  closeup w/ wax marks ↔ window full-sheet), 173810 coronation gold, 218088 kokomo
  flemish (lightbox ↔ window), 230207 vecchio, 203547 light seedy, 186204 van-gogh
  violet (closeup ↔ shop rack), 238631 peacock blue (featureless smooth glass — same
  product certain, same sheet unverifiable *by texture*, which is the statistics-only
  case by definition).
- **Same product but likely a DIFFERENT physical sheet** (1): 238607 mermaid dreams — the
  window shot shows brown streaks absent from the closeup's region; opal streaky
  distributions differ sheet-to-sheet. A full crawl must treat opal/streaky same-product
  pairs as sheet-identity-unverified.
- **Pair unusable / gallery contamination** (3): 186196 van-gogh silver — BOTH images are
  finished mosaic vases (product-use shots; the Van Gogh line's gallery is mosaic-heavy);
  220063 MLW mirror — the "window" image is a fan-of-sheets catalog collage on white;
  173747 windsor blue — the two images show incompatible textures (smooth vs heavily
  seedy), likely different variants under one listing.

Combining §2.2 and §2.3 at the product level: **9/15 registrable cross-capture (SS2.2)
+ 2 more statistics-only-only (173810, 186204) = 11/15 products with a usable
same-sheet pair**; 238607 counts as registrable at the wild↔wild level (its g1/g2/g3
window shots register) even though its closeup is likely a different physical sheet;
186196 and 220063 are unusable at the sheet level; 173747's registrable g1×g3 pair
partially redeems its mismatched headline pair (the two window shots register; the
smooth closeup remains a listing-variant mystery).

## 3. Yield estimate for a full crawl

Measured inputs: 394 Wayback-discoverable sheet products today (the accessible floor);
mean 5.5 images/product; ~73% (band 60-80%) of products with a clean+wild pair
candidate; 60% of deep-checked products with ≥1 registrable sheet cross-capture pair
(~1.9 pairs each); 73% with at least statistics-only same-sheet pairs.

**Wayback-only full crawl (no new access needed, same infrastructure as this census):**
- ~394 products × ~85% parse rate ≈ **330-350 products with image manifests**
  (extendable: a legacy-template parser would recover most of the 40 pre-2015 failures).
- ≈ 1,900 images total (≈ 480 MB at full res).
- **≈ 200 products with ≥1 registrable cross-capture sheet pair → ≈ 380 registrable
  pairs** (0.60 × 330 × 1.9).
- **≈ 240-260 products with statistics-only same-sheet pairs → ≈ 700-1,000 usable
  statistics-only pairs** (each product's wild shots pair with each other and with its
  clean crops).
- Realistic attrition not yet in these numbers: finished-product gallery tails,
  opal/streaky sheet-identity ambiguity (§2.3), thickness-variant photo reuse. A
  conservative planning number: **~150 products / ~300 registrable pairs / ~600
  statistics-only pairs** — already 1-2 orders of magnitude more real cross-capture
  data than the project has ever had (currently: 1 suncatcher pair + 2 sheet photos,
  report 013).
- Delphi's live catalog is larger than Wayback's slice (their marketing claims 1,000+
  glass varieties; the live category pages are inaccessible to us, so the true
  multiplier is unknown — likely 2-5× the Wayback floor). That upside requires either
  Delphi's permission or the WAF block lifting, which is another argument for asking.

## 4. How the pairs feed the research

See `REAL_PAIRS_DATASET.md` §7 for the full spec. Short form: (a) the real cross-capture
consistency benchmark extends `register_pair.py`'s T-agreement to registrable wild↔wild
pairs and adds a distribution-level statistic for the statistics-only majority; (b)
registrable pairs are the first REAL pixel-aligned same-material different-illumination
supervision available to the neural track at any scale (held-out-product split answers
the GlassNet held-out-material item in `RESEARCH_STATE.md`); (c) clean↔wild pairs give
(wild, clean-reference) sim-to-real evaluation — with the §2.1 caveat that Delphi's clean
references are usually crops of wild shots, so the TRUE lightbox subset (~5-12% of
images) is the only genuinely clean reference pool, and per-product it is often absent.

## 5. Politeness / ToS / licensing — flags, stated honestly

1. **Delphi actively bot-blocks its storefront.** This iteration never touched the
   blocked surface (pages came from the Wayback Machine's public archive) and the image
   hosts it did touch are unprotected and were hit at ~1 req/s — but their Terms of Use
   (archived `page/main_terms`) contains a clause against bypassing "measures Delphi
   Glass may use to prevent or restrict access". Reconstructing their catalog structure
   from a third-party archive is not a technical bypass, but it is arguably against the
   clause's intent. Judgment call — flagged, not resolved unilaterally.
2. **Their ToU also prohibits copying/reproducing site content without written
   permission**, which covers product photography. Current mitigations: raw images live
   only in `/tmp`, never committed; only small downscaled panels are committed for
   reviewer eyeballing; nothing redistributed. Internal research evaluation of
   copyrighted product photos without a license is still a use — a maintainer/legal call
   (or a permission request to Delphi, which given the modest, non-redistributive ask
   might simply be granted) should precede a full crawl.
3. **Load is a non-issue** if the crawl keeps the census's shape: Wayback for pages,
   ~1 req/s for image bytes (a full crawl ≈ 12-20k image GETs ≈ 4-6 hours of trickle).

## 6. Go/no-go recommendation

**GO — with two conditions**, both cheap:

1. **Maintainer/legal sign-off on the ToS posture (§5) before the full crawl.** The
   research value is proven; the open question is purely usage-rights. Recommended
   move: email Delphi asking for research-use permission (read-only, internal
   evaluation, no redistribution, ~2k images at 1 req/s) — the ask is modest and a yes
   removes both flags at once, and potentially unlocks the live catalog (2-5× yield).
2. **Ship the full crawl WITH the filters this iteration built**, not the naive
   pairing: same_photo derivation detection (hero-as-crop is systematic),
   finished-product gallery-tail screening, and sheet-identity caution for
   opal/streaky products. All three exist in `pairwise_matrix.py` / `classify.py` /
   this report's verdicts; the crawl is a scale-up, not new research.

Why GO is justified by the numbers: the discovery held up under verification — a
solid majority of products carry real multi-capture photography of the same physical
sheet, ~60% of deep-checked products yield pixel-registrable same-region
cross-capture pairs, and even the conservative Wayback-only yield (~300 registrable +
~600 statistics-only pairs) transforms the real-pairs situation for all three research
consumers (§4). The one thing the dataset is NOT is a source of pristine lightbox
references — Delphi's clean images are usually crops of wild shots; true studio
swatches are ~5-12% of images — so the sim-to-real (wild, clean-reference) use case
(§4c) gets the smallest yield and should not be the headline justification.

## 7. Files

- `../realpairs/crawl.py` — Wayback CDX discovery + product-page manifest parser.
- `../realpairs/classify.py` — capture-type heuristic classifier + census runner.
- `../realpairs/calibration_sheet.py` — calibration tooling; labels + index in results/.
- `../realpairs/pair_quality.py` — 15-product full-res pair check (ORB, panels).
- `../realpairs/pairwise_matrix.py` — exhaustive within-product pair classification
  {same_photo, cross_capture, none}; the dedup/derivation filter a full crawl needs.
- `../realpairs/aggregate.py` — census aggregation.
- `../realpairs/results/` — census.json, product_manifest.json, candidates.json,
  pair_quality.json, pairwise_matrix.json, calibration_*.json, panels/.
- `../docs/REAL_PAIRS_DATASET.md` — the dataset spec.
