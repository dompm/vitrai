# Real cross-capture pairs from Delphi Glass product photography — dataset spec

Iteration 030 (spec), iteration 033 (dataset BUILT — see §9, the dataset
card; §9 supersedes §6's estimates with measured numbers). Branches:
`research/delighting-030` (spec + census), `research/delighting-033` (full
harvest). Companions: `../reports/030-real-pairs.md`,
`../reports/033-pairs-harvest.md`, `../realpairs/` (code).

## 0. The discovery, restated

Delphi Glass (delphiglass.com) product pages frequently carry **multiple photos of the
same physical sheet** shot under **different conditions**: a clean studio/lightbox swatch,
plus one or more "in the wild" shots — held up to a window (backlit by daylight/sky), held
in the shop under indoor front-lighting (often with a hand and other sheets visible), or
propped/leaning on a shelf or table among other stock. Some products add tight close-up
crops of interesting sub-regions (streaks, granite texture). See `../reports/030-real-pairs.md`
§2 for the worked example (product 234414, 9 images spanning 5 distinct conditions) — this
is REAL same-glass-different-capture data, the structure the whole consistency research
line has been assuming only synthetic rendering could supply.

## 1. Access reality (read before building a crawler)

- **The live storefront (`www.delphiglass.com`) 403s every request from this research
  environment** — confirmed via both `curl` and the `WebFetch` tool, with a Cloudflare
  "Attention Required" block page. Unrelated sites, and even another Shopify storefront
  (`shop.bullseyeglass.com`), respond normally, so this is Delphi-specific bot management,
  not a general egress problem.
- **What DOES work:**
  1. The **Wayback Machine** (`web.archive.org`) has extensive archived snapshots of
     `www.delphiglass.com/stained-glass/<brand>/<slug>` product pages, fetchable via its
     public CDX API (`web.archive.org/cdx/search/cdx`) for discovery and
     `archive.org/wayback/available` + the snapshot URL for page HTML. This is public
     infrastructure, not Delphi's, so politeness there is about not hammering archive.org,
     not about Delphi's bot rules.
  2. **Delphi's own image hosts** (`images.delphiglass.com/image_new|image_1500/<id>.jpg`,
     `www.delphiglass.com/syscat/image_add/<id>_<n>[0].jpg`, `www.delphiglass.com/syscat/
     image_160/<id>.jpg`) are **not** behind the same WAF rule and return normal 200s to a
     plain `curl` with a normal desktop User-Agent.
  3. `robots.txt` on delphiglass.com disallows admin/cart/checkout/sort-query paths — it
     does **not** disallow `/stained-glass/` product or category pages, or the image hosts.
- **Practical crawler shape that follows from this:** discover + parse product pages
  through Wayback (zero live-site page loads); download only image bytes directly from
  Delphi's CDN, throttled (~1 req/s, normal UA — see §5 for why this matters more than
  usual here). This is a lighter live-site footprint than a single real visitor browsing
  the same number of product galleries in a browser (which loads all gallery images in
  parallel on page load, not throttled).

## 2. Product page image structure

Each product ID (`<id>`, a 6-digit SKU-photo id, e.g. `234414`) exposes:

| role | URL pattern | size |
|---|---|---|
| hero (medium) | `images.delphiglass.com/image_new/<id>.jpg` | ~300×300 |
| hero (full) | `images.delphiglass.com/image_1500/<id>.jpg` | 1500×1500 |
| hero thumb | `images.delphiglass.com/image_new/<id>_t.jpg` | 90×90 |
| gallery item *n* thumb | `www.delphiglass.com/syscat/image_add/<id>_<n>.jpg` | ~70×55 |
| gallery item *n* full | `www.delphiglass.com/syscat/image_add/<id>_<n>0.jpg` | 1500×1500 |
| listing thumb | `www.delphiglass.com/syscat/image_160/<id>.jpg` | 160×160 (hero only) |

No medium-resolution variant exists for gallery items — only the tiny 70×55 thumb or the
full 1500×1500. This shaped the census design (§4 below): thumbnails for the broad census,
full-res only for the hand-picked pair-quality sample.

## 3. Capture-type taxonomy

Six labels, defined operationally (see `../realpairs/classify.py` for the heuristic
detector and its features):

- **`lightbox`** — clean, uniform-backlit studio swatch. Near-white or near-black border,
  low border variance, no visible hand/background object.
- **`window`** — held up against a window or outdoors, backlit by daylight/sky. Border
  shows high hue diversity (sky/foliage/building tones) and/or a bright-top/dark-bottom
  luminance gradient; often (not always) a hand visible at one edge.
- **`shop_held`** — held indoors by a hand, front-lit, shop background (shelving, other
  sheets, price stickers, wood tones). Detected primarily by a localized skin-tone blob.
- **`standing`** — sheet propped/leaning on a shelf or table among other stock, no hand,
  structured indoor background (straight shelf/table edges, multiple hues).
- **`closeup`** — tight crop with no visible background at all; the whole frame is sheet
  texture (border statistics ≈ interior statistics).
- **`other`** — none of the above fit confidently (includes non-photo images, diagrams,
  and genuinely ambiguous shots).

## 4. Dataset structure a full crawl would produce

```
product:
  product_id        int, Delphi's numeric photo-id namespace (stable across snapshots)
  brand             str, the /stained-glass/<brand>/ category slug
  slug              str, product URL slug
  title             str
  source_snapshot   {url, timestamp}   -- which Wayback capture the parse came from
  images: [
    { image_key       str, e.g. "hero" / "gallery_3"
      url_thumb        str
      url_full         str
      capture_type     one of the §3 labels
      capture_conf     float, heuristic confidence (NOT ground truth; see report for
                        calibrated accuracy and where it fails)
      w, h              int, native full-res dimensions
    }, ...
  ]
pairs (derived, per product, generated not stored redundantly):
  { product_id, image_key_a, image_key_b,
    capture_type_a, capture_type_b,
    registration: {
       method: "orb_homography" | "corners" | "none",
       inliers: int,               -- ORB path
       registrable: bool,           -- inliers >= threshold (20, calibrated in report 030)
       homography: 3x3 (if registrable),
       residual_mad: float,         -- post-registration central-region median |diff|
       grad_corr: float             -- gradient correlation of the aligned regions
    },
    kind: "same_photo" | "cross_capture" | "statistics_only" | "unusable",
       -- same_photo: crop/rescale derivation (registrable AND residual_mad < 10/255
       --   with high grad_corr) -- Delphi's hero is routinely a crop of gallery_1;
       --   dedup metadata, NOT a pair (report 030 SS2.1);
       -- cross_capture: registrable with substantial residual = same sheet region,
       --   different capture (the prize);
       -- statistics_only: not registrable but same-sheet by eyeball/texture agreement;
       -- unusable: finished-product shot, collage, or different physical sheet.
    same_sheet_confidence: float,  -- eyeballed / heuristic-color-and-texture-agreement
                                       score when NOT registrable (statistics-only case)
  }
```

**Product ID is the join key**, not brand+slug — Delphi reuses the same photo-id across a
product's thickness/size variants (mirrors report 019's finding for Bullseye), so
dedup-by-id before counting "how many physical sheets" a crawl actually captured.

## 5. Politeness & licensing — read honestly, not defensively

**Politeness mechanics (the easy part):** page discovery/parsing never touches the live
storefront (Wayback only); image downloads are throttled ~1 req/s with a normal UA, well
under the load of a single browsing session. A Wayback-only full crawl (§6: ~350 products
× ~5.5 images ≈ 1,900 image GETs) at 1 req/s is ~35 minutes of trivial, sequential,
single-connection load; even a permission-unlocked live-catalog crawl (2-5× that) stays
a few hours of trickle — not a load concern for Delphi's infrastructure.

**The honest ToS flag (the part that needs a human call before a full crawl):** Delphi's
Terms of Use (archived snapshot, `page/main_terms`, checked 2026-07-10) contains two
clauses that this project's access pattern brushes against:

1. *"Bypass Delphi Glass's robot exclusion headers or other measures Delphi Glass may use
   to prevent or restrict access to Delphi Glass"* — the live site's Cloudflare bot-block
   IS such a measure. Routing page discovery through the Wayback Machine's public archive
   does not touch Delphi's servers or their block at all, so it is not a technical bypass
   of their protection — but the *intent* of that clause (don't work around access
   controls to get at their catalog data) is arguably in tension with using a third-party
   archive to reconstruct the same catalog structure they're blocking us from crawling
   live. This is a judgment call, not a clear violation, and is flagged here rather than
   resolved unilaterally.
2. *"Copy, reproduce, modify, create derivative works from, distribute or publicly display
   any... Content... from the Site without the prior expressed written permission of
   Delphi Glass"* — this squarely covers their product photography. The mitigations
   already in place for this iteration (raw images gitignored, never committed; only
   small downscaled panels committed for internal reviewer eyeballing, captioned as
   Delphi's photography; no redistribution outside this research repo) reduce but do not
   eliminate the exposure — internal research/eval use of copyrighted product photography
   without a license is still a use, even if not publication.

**Recommendation:** before scaling to a full crawl (§6), get explicit maintainer/legal
sign-off that (a) internal-only research use of catalog photography for a consistency
benchmark is acceptable, and (b) whether reaching out to Delphi for a research-use
permission (given the modest ask — read-only derived statistics, no redistribution) is
worth doing before or instead of a larger unlicensed crawl. Nothing in this iteration was
redistributed or published beyond this repo's internal reports.

## 6. Estimated yield of a full crawl

Measured (report 030): mean **5.5 images/product**; **73%** of census products have both
a clean (lightbox/closeup) and a wild (window/shop) image (calibration-corrected band
60-80%); **60%** of deep-checked products yield ≥1 pixel-registrable same-region
cross-capture sheet pair (~1.9 pairs each) and **73%** at least a statistics-only
same-sheet pair. The CDX discovery pass found **394** distinct product URLs with a
Wayback snapshot in the sheet-brand directories — a **lower bound** on catalog size:
(a) Wayback coverage is opportunistic, (b) 40 of the 220 sampled had only pre-2015
snapshots this parser doesn't handle (a legacy-template parser recovers most), and
(c) the live catalog (marketing: "1,000+ glass varieties") is likely 2-5× the Wayback
slice but inaccessible without permission or the WAF lifting.

**Wayback-only yield (no new access needed):** ~330-350 parseable products ≈ 1,900
images ≈ **~200 products / ~380 registrable cross-capture pairs / ~700-1,000
statistics-only pairs** before attrition; a conservative planning number after
finished-product and sheet-identity attrition is **~150 products / ~300 registrable /
~600 statistics-only** — versus the project's current real-pair inventory of one
suncatcher pair (report 013). Live-catalog access multiplies this 2-5×.

**Two mandatory filters, measured in report 030 §2:** (i) same-photo derivation
detection — Delphi's hero image is routinely a CROP of gallery_1 (4/15 products), so
registration alone over-counts pairs; keep a pair only if the post-registration
central-region residual is substantial (median |diff| ≥ 10/255 or low gradient
correlation). (ii) finished-product screening — gallery tail slots (6-9) often show
suncatchers/mosaics MADE from the glass (5/22 registrable pairs in the probe);
these register but are not sheet data.

## 7. How the pairs feed the research

**(a) Real cross-capture consistency benchmark.** Extends `register_pair.py`'s existing
T-agreement metric (currently run on the maintainer's own handheld photo pairs, report
013) with many more (sheet, capture_a, capture_b) triples spanning the taxonomy in §3.
Registrable pairs (ORB succeeds) give the strong pixel-aligned T-agreement number;
non-registrable same-sheet pairs (different crop/zoom of the same sheet) still support the
weaker but still real **distribution-level** statistic register_pair.py doesn't currently
compute — e.g. matching per-channel histograms / hue-chroma centroids of the two crops
under the assumption they're the same material, which is exactly what report 013 already
had to do by hand for the suncatcher benchmark (no ground truth, style-distance only).
This closes the "real photos still un-shot" gap flagged as open at the end of
`RESEARCH_STATE.md`, without needing the maintainer to physically shoot anything new.

**(b) Consistency-loss training data.** Registrable pairs are the first source of REAL
(not synthetic) same-material, different-illumination, pixel-aligned crops available at
any scale — exactly the supervision `eval_cross_lighting.py`/`train_glassnet_zero.py` have
only ever had from Blender renders. A held-out-product split (train on some sheets' pairs,
evaluate cross-capture invariance on others) is the natural next step for the neural track,
answering `RESEARCH_STATE.md`'s "For GlassNet: generate many material seeds per class, then
evaluate a held-out-material split" item with real rather than synthetic seeds.

**(c) (wild, clean-reference) sim-to-real supervision.** Every product with a `lightbox`
image (clean, ~studio-uniform illumination — the thing the synthetic generator's own
`Standard` view-transform renders approximate) paired with a `window`/`shop_held`/
`standing` capture of the SAME sheet is a (clean-reference, wild-capture) pair for exactly
the kind of domain-gap supervision `RESEARCH_STATE.md`'s Track A/learned-track split cares
about: does a model trained mostly on synthetic (clean Cycles glass, report 022's honest
caveat) transfer to real phone-photo-style captures? These pairs are a direct real-world
eval for that transfer, and (for registrable pairs) a direct real fine-tuning signal.

## 8. What this spec does NOT claim

It does not claim same-sheet identity is guaranteed without verification — Delphi (like
Bullseye per report 019) sometimes reuses one photo across size/thickness SKU variants, and
occasionally a gallery slot is a swatch-adjacent shot (a ruler, a stack of several colors)
rather than the same physical piece — the capture-type classifier and the ORB registrability
check are both about IDENTIFYING which claimed pairs are trustworthy, not asserting all of
them are. Every number in report 030 is reported with its verification method attached.

## 9. DATASET CARD — as built (iteration 033, 2026-07-11)

### 9.1 Contents and location

- **Manifest (committed):** `../realpairs/results/manifest_033.json` —
  254 products (unique product_ids, variant-deduped), 1,491 images with
  full-res capture-type labels, 4,668 pair records with ORB inlier counts,
  registration verdicts and derivation-filter outcomes.
- **Screens (committed):** `../realpairs/results/contamination_033.json` —
  advisory flags per product/image/pair for six contamination modes
  (report 033 §3); `vangogh_validation.json` — the finished-product screen's
  measured recall (96% combined, 0 false positives on 99 hand-labeled
  images); `aggregate_033.json` — headline stats.
- **Raw images (NOT committed):** `../realpairs/data/images/<pid>/` —
  368 MB of 1500×1500 JPEGs, gitignored, local-disk only, per the
  research-use posture (§5). Refetchable idempotently by `harvest_033.py`.
- **Evidence panels (committed, downscaled):** `../realpairs/results/panels_033/`.

### 9.2 Headline counts (measured, not estimated)

| | raw | after all screens |
|---|---:|---:|
| products | 254 | 245 usable (3 mirror, 6 pack listings excluded) |
| images | 1,491 | 1,245 unflagged |
| registrable cross-capture sheet pairs | 213 | **145** (64 products) |
| statistics-only same-product pair candidates | — | ~1,850 (213 products; 805 clean×wild) |
| same-photo derivation pairs (dedup metadata) | 45 + 16 suspect | — |

Capture-type mix (full-res classifier): window 42.9%, closeup 36.8%,
shop 18.2%, **lightbox 1.8%**, other 0.2%. 76% of products have ≥1 clean
(lightbox/closeup) and ≥1 wild (window/shop) image.

### 9.3 How to consume pairs (the load-bearing predicate)

A pair from `manifest_033.json` is a trustworthy registrable sheet pair iff:
`kind == "cross_capture"` AND `finished_product_flag == false` AND neither
image key appears in `contamination_033.json` products[pid].images AND the
product has neither `non_transmissive_mirror` nor `multi_sheet_listing` in
products[pid].flags AND NOT (`residual_mad < 15 AND inliers >= 200`)
(the clear-glass same-photo leak, report 033 §3 mode 5). Products with
`opal_streaky_caution` (31.5%) additionally carry unverified sheet identity
across captures (030 §2.3): usable for texture-statistics work, "sheet-
identity-unverified" for registered-consistency positives per
`EVAL_PROTOCOL.md` §3c.

### 9.4 Known biases (measure before believing a benchmark number)

- **Wild-wild rich, clean-reference poor:** 27 lightbox images TOTAL (1.8%).
  There is effectively no per-product studio reference; sim-to-real
  (wild, clean) evaluation gets only a handful of products.
- **Brand skew in registrable pairs:** uro (65) + tiffany-today (40) +
  clear-textured (29) = 92% of surviving pairs; van-gogh has 29 products but
  contributes 1 pair (stock-photo-dominated galleries); kokomo/armstrong/
  wissmach/specialty contribute 10 combined; delphi-superior none.
- **Texture skew:** ripples/mottles/textured clears register best, smooth
  cathedrals worst — 32 of the 64 pair-bearing products carry the
  opal/streaky caution.
- **Window-shot house style:** most wild captures share Delphi's storefront
  composition (sheet on windowsill, trees/sky above) — illumination variety
  within `window` is real but scene variety is limited.
- **Label noise:** capture labels are heuristic (87% clean/wild binary at
  full res; window/shop confusion is the dominant error — 5/8 shop-rack
  shots in the Van Gogh eyeball set were labeled window).
- **Holdout (frozen, EVAL_PROTOCOL.md §3c — v1.1 final):** base rule
  reserve iff `int(sha1(product_id_string).hexdigest(),16) % 5 == 0` →
  55/254 products (21.7%; per-brand: armstrong 5/13, clear-textured 19/88,
  delphi-superior 0/2, kokomo 2/17, specialty-finish 0/7, tiffany-today
  10/42, uro 7/30, van-gogh 8/29, wissmach 4/26), plus the v1.1 top-up of
  three eval-eligible products for brands under the 15% floor: 239270
  (delphi-superior; opal-caution, scores identity-unverified), 203533
  (kokomo), 220043 (specialty-finish) → **final holdout 58/254 = 22.8%**,
  13 of the 64 pair-bearing products (the top-ups add identity coverage,
  not pair volume). Frozen in research/delighting-034 commit 94f2d01; any
  further change needs first-results-grade justification per that
  protocol's §6.

### 9.5 Provenance & usage posture

Pages: Wayback Machine only (zero live page loads). Images: Delphi's
unprotected image hosts, 1,485 GETs at 0.42 req/s measured, normal UA,
2026-07-10/11. Internal research evaluation only; raw photography
gitignored and never redistributed; committed panels are small downscales
captioned as Delphi's photography (report 030 §5 posture, maintainer-
approved for research use). The live catalog (2-5× this slice) remains
inaccessible without Delphi's permission.
