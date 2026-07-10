# Real cross-capture pairs from Delphi Glass product photography — dataset spec

Iteration 030. Branch `research/delighting-030`. Companion: `../reports/030-real-pairs.md`
(the census + pair-quality results this spec is grounded in), `../realpairs/` (code).

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
       homography: 3x3 (if registrable)
    },
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
under the load of a single browsing session. A full crawl at the yield estimated in §6
(≈2,500–4,000 products × ~5 images ≈ 12,500–20,000 image GETs) at 1 req/s is 3.5–5.5 hours
of trivial, sequential, single-connection load spread over however many days the crawl is
paced across — this is not a load concern for Delphi's infrastructure.

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

From the report-030 census (`../reports/030-real-pairs.md` §1): sampled products average
**N_bar images/product** (see report for the measured number) across the ~10 genuine
single-sheet brand/category directories under `/stained-glass/`; **X%** of products expose
≥2 distinct capture types. The CDX discovery pass alone found **~394** distinct product
URLs with at least one Wayback snapshot in those directories (report 030 §1 candidate
count) — this is a **lower bound**, not the true catalog size, because: (a) Wayback's
coverage of any given product page is opportunistic (only pages some crawler visited get
archived), (b) several brand directories (german-new-antique and others, see report 030
§1's coverage caveat) have only pre-2015 snapshots whose page template this parser does not
handle, undercounting live catalog size, and (c) Delphi's live catalog almost certainly
has more current SKUs than Wayback has ever captured. A conservative estimate: the true
`/stained-glass/` sheet catalog is on the order of **2,500–4,000 products** (extrapolating
from the ~394-with-any-snapshot floor and typical Wayback coverage rates of 10-20% for a
mid-size e-commerce catalog's long tail); at report 030's measured ≥2-capture-type rate,
that implies roughly **X% × catalog size** products yielding at least one real
cross-capture pair, and (from the 15 hand-picked pair-quality checks) a
**registrable-vs-statistics-only split** given in report 030 §2 that determines what
fraction of those pairs support pixel-aligned vs. distribution-only supervision.

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
