# Scouting coglassworks.com (and siblings) as a real cross-capture pair source — iteration 041

Branch: `research/delighting-041-pair-sources` (off `research/delighting`). Companion:
`../results/041/pair_sources_board.jpg` (preview contact sheet), `../results/041/raw_sample/`
(gitignored, ~76 images / 22 products, throttled sample — NOT a full crawl).

The lead: [coglassworks.com/collections/sheet-glass/products/amber-white-wispy-rk950](https://coglassworks.com/collections/sheet-glass/products/amber-white-wispy-rk950)
— Colorado Glass Works, a Denver stained-glass retailer whose product photos are taken by an
employee **holding the physical sheet up**, usually against the shop's street-facing window
(backlit by daylight), sometimes against an indoor shelf/rack (front-lit). Same discovery shape
as Delphi (report 030/033, `../docs/REAL_PAIRS_DATASET.md`): multiple photos of the *same physical
object*, different capture conditions — but this store sells **individual remnant/scrap pieces**,
not one-SKU-per-color-per-size sheets, which changes the identity math substantially (§2).

## 0. Headline

- **1,361 unique products** in the `sheet-glass` collection (measured via Shopify's own
  `/collections/sheet-glass/products.json`, not scraped HTML — see §1).
- Naive per-listing pair count is misleading: **43.6% of SKU-photo-named listings bundle photos
  of more than one distinct physical piece** under a single product page (§2.2) — the lead's own
  neighbors do this. Corrected for that, the measured yield is **~1,389 pairable physical-piece
  photo-pairs from the 815 cleanly-SKU-named listings alone** (§2.3), before any capture-type or
  quality filtering, with a further ~500-1,600 more plausible from the remaining 523 listings
  whose filenames don't support automatic identity grouping (§2.2).
- Identity-matching verdict: **name-alone matching is unsafe, confirmed with concrete
  collisions** (§3) — including on the lead's own glass. Brand+SKU matching to our registry or to
  Delphi's manufacturer catalog works for **~5% of listings at best** (§4); the store's own
  RK/RA-prefixed "SKU" is an internal intake code, not a manufacturer catalog number.
- Two best sibling sources found (§5): **Warner Art Glass** (consistent backlit studio photography,
  but mostly single-image-per-product — weak pair source, useful as a second "clean-ish" reference
  style) and, more speculatively, **Bradstreet Glass** (unconfirmed, promising collection
  structure, not deep-checked — see caveat). Delphi remains the strongest single source measured
  to date.
- **Recommendation: do a full scrape of coglassworks, but only after (a) building the
  SKU-token identity grouper described in §2.3/§6 so pairs are physical-piece-verified, not
  listing-verified, and (b) a maintainer call on the ToS tension in §7** (their own agents.md
  explicitly invites read-only `/products.json` access; their generic Shopify ToS boilerplate
  says no scraping — same shape of honest tension as the Delphi report flagged, not resolved here).

## 1. Scoping the collection (politeness note first)

`coglassworks.com` is a Shopify store that **publishes explicit agent-facing crawl instructions**:
`robots.txt` points to `/agents.md`, which documents a read-only JSON API intended for agents —
`GET /collections/{handle}/products.json`, `GET /products/{handle}.json` — as an alternative to
HTML scraping. This is a materially different situation from Delphi (which blocks the live site
entirely and had no comparable invitation): **all scoping in this report was done via that
documented JSON endpoint**, six paginated requests (`?limit=250&page=1..6`) at ~1 req/s, zero HTML
page loads. Total: **1,361 unique product records**, each with full `variants[].sku`, `vendor`,
`tags`, and a complete `images[]` array (src + native w/h) — no need to hit individual product
pages at all for the census.

**Image download sample:** 22 products, stratified across the store's declared vendors (2-3 per
brand: Bullseye, Wissmach, Youghiogheny, Oceanside, Kokomo, Uroboros, Spectrum, Lamberts,
Armstrong, Mouth Blown, Fremont, plus generic "Colorado Glassworks"), 76 images total, fetched
sequentially at 1 req/s (~80s wall time), normal descriptive UA identifying the research and a
contact email. Images live at `research/delighting/results/041/raw_sample/` — **gitignored**,
same posture as Delphi's raw data (§7).

**CDN pattern:** plain Shopify CDN, `cdn.shopify.com/s/files/1/0723/2533/3293/files/<name>.jpg`.
Two filename conventions coexist (this matters a lot, see §2):
- `<SKU>.jpg`, `<SKU>_2.jpg`, `<SKU>_3.jpg`, ... — direct SKU-named uploads, one SKU token per
  physical piece.
- `IMG_<n>.jpg` or `IMG_<n>_<uuid>.jpg` — raw phone camera-roll filenames, uploaded straight from
  a bulk multi-photo session; the SKU is not recoverable from the filename at all.

## 2. Product/image structure and the "one listing, multiple physical pieces" trap

### 2.1 It's a remnant/scrap retailer, not a per-color-per-size catalog

Product bodies read "Approx. size: 5.5x12in" and nearly every physical sheet in every photo has a
**paper sticker taped to it** reading the SKU and a hand-written dimension (e.g. "RA395 / 8.5x5").
This is the single most useful and most dangerous fact about this source:

- **Useful:** the sticker is baked into the pixels — an OCR/VLM read of the sticker is a
  ground-truth identity anchor independent of (and a cross-check on) the URL/metadata SKU.
- **Dangerous:** because pieces are individual remnants, a "product listing" is not guaranteed to
  be one physical object. Adjacent remnants cut from a shipment often get **listed together, and
  photographed together, under one product page**.

### 2.2 Measured: how often one listing bundles multiple physical pieces

Splitting the 1,361 products by which filename convention their images use:

| filename convention | # products | usable for automatic identity grouping? |
|---|---:|---|
| SKU-named only (`<SKU>.jpg`, `<SKU>_2.jpg`, ...) | 815 (59.9%) | yes — group by SKU token |
| `IMG_####`-style camera-roll only | 523 (38.4%) | no — SKU not in filename |
| mixes both | 23 (1.7%) | partial |

Restricting to the 815 SKU-named-only listings (the reliable subset) and grouping each listing's
images by their literal SKU token:

- **460 listings (56.4%) = exactly one physical piece** (1+ photos of it).
- **355 listings (43.6%) = more than one physical piece** bundled in one product page — this is
  not a rare edge case, it is nearly half the reliable subset. Concrete example, captured in the
  preview board: `white-mottled-oceana-ra395` shows 4 images that are actually **two different
  pieces**, `RA395` (8.5×5in, images 1-2) and `RA396` (5×6in, images 3-4) — different shard shape,
  different hand-written size, confirmed by reading the in-frame sticker on each. A naive
  "all images in this listing = one sheet, register them against each other" pipeline would
  silently manufacture a false cross-capture pair between two different pieces of glass here.
- Across those 815 listings there are **1,636 distinct physical-piece SKU tokens**, of which
  **1,389 (84.9%) have ≥2 images** — i.e. **1,389 measured, filename-verified, same-physical-piece
  photo pairs**, before any capture-type-diversity or registration-quality filtering.

The other 523 `IMG_####`-only listings (38.4% of the catalog) can't be identity-grouped this way;
their images could be one piece shot in a multi-photo burst (the common case in the sample — see
`light-amber-white-wispy-vintage-spectrum`, 11 sequential `IMG_83xx`/`IMG_84xx`/`IMG_86xx` frames
of what looks like one piece held at slightly different angles) or could silently mix pieces the
same way the SKU-style listings do. Treat pairs from this subset as **identity-unverified** unless
corroborated by sticker OCR.

### 2.3 Corrected yield estimate

- **Filename-verified same-piece pairs (SKU-named subset): 1,389**, from 815 listings /
  1,636 distinct pieces.
- **Plausible-but-unverified pairs (IMG-style subset):** 523 listings, mean 4.25 images/product
  catalog-wide → if a similar fraction of these listings are genuinely single-piece bursts as the
  eyeballed sample suggests, this subset could add roughly **500-1,600** more pairs, but every one
  of them needs a sticker-OCR or VLM same-piece check before use (§6) — do not count them without
  verification.
- **Total raw candidate: ~1,400-3,000 pairs**, an order of magnitude more than Delphi's 145
  registrable pairs (report 033) — but a large fraction of them are a *weaker* kind of pair than
  Delphi's headline number, per §2.4.

### 2.4 Capture-type diversity is lower than Delphi's — most pairs are same-rig, not same-sheet-different-light

Eyeballing all 76 downloaded sample images (see `pair_sources_board.jpg` and the full internal
contact sheet): **the overwhelming majority of a listing's photos are the *same* capture
condition** — held up against the shop's street window, backlit, shot within the same short
session, varying only the exact hand angle/framing/zoom. This is real image diversity (useful for
pose/registration robustness, occlusion-by-hand robustness, background-variety), but it is *not*
the illumination-domain-gap diversity that made Delphi's `lightbox`/`window`/`shop_held` taxonomy
valuable.

Only **~3-4 of the 22 sampled products (~15-18%)** show a genuinely different second condition —
typically the piece leaning on a shelf/rack, front-lit, indoors, no hand — paired with the usual
backlit window shot. Two clean examples are in the preview board: `white-wispy-oceanside-fusible-
96-coe-ra330` (shelf-rack vs. window) and `medium-blue-transparent-kokomo-ra630` (leaning-on-shelf
vs. window). Extrapolated (wide error bars, n=22): **roughly 150-250 products catalog-wide** carry
a Delphi-style clean-vs-wild pair; the rest are same-condition multi-angle bursts. **A full scrape
should run an automated capture-type classifier (reuse `../realpairs/classify.py`'s heuristics —
they should transfer reasonably, the taxonomy in `REAL_PAIRS_DATASET.md` §3 was built for exactly
this kind of photo) over a larger sample before committing to the corrected estimate.**

## 3. Identity matching — name-alone is unsafe, confirmed with concrete collisions

This was the user's explicit caution and it is thoroughly confirmed, on two independent axes:

**(a) Cross-brand name collisions (the caution as stated).** The lead product's own color name,
**"Amber White Wispy,"** is sold under the *identical* descriptive name by at least four different
real manufacturers in this same catalog:

| listing | vendor tag |
|---|---|
| `amber-white-wispy-rk950` (the lead) | *no manufacturer tag at all — see §4* |
| `amber-white-wispy-wissmach-rk860` | Wissmach Glass |
| `amber-white-wispy-armstrong-1` | Armstrong |
| `amber-white-wispy-spectrum` | Colorado Glassworks (title says Spectrum) |
| multiple `*-kokomo` variants | Kokomo Glass |

A name-only matcher would happily conflate Wissmach's amber/white wispy with Kokomo's or
Armstrong's — visually similar color family, different manufacturers, different glass. Other
confirmed collisions in the same 1,361-product set: **"Transparent Blue"** (Bullseye, Kokomo,
Wissmach — three brands), **"White Wispy"** (Spectrum, Oceanside), **"Medium Blue Transparent"**
(Bullseye, Kokomo), **"Mixed Brown"** (Spectrum, Armstrong) — 15 core-descriptive-name collisions
spanning ≥2 real manufacturers found in a single quick pass; likely undercounted since it only
checked exact-normalized-string matches.

**(b) Within-listing piece collisions (a second, distinct risk not in the original caution but
just as load-bearing).** Covered in §2.2 — 43.6% of SKU-named listings bundle >1 physical piece.
This is a "the images near each other aren't even the same object" risk, independent of naming.

**Verdict: matching must be brand+SKU where a real manufacturer SKU is extractable (§4), never
name-alone; and even brand-correct listings need the §2.2 piece-token check before treating their
images as a pair.**

## 4. Cross-referencing to the registry / Delphi — low direct yield, here's why

`frontend/public/assets/glass_swatch_registry.json` (branch `fix/sheet-drag-prop`, read-only) has
1,269 entries across exactly four manufacturers: **Bullseye (504), Oceanside (283), Youghiogheny
(265), Wissmach (217)** — each keyed by a real manufacturer catalog SKU (e.g. Bullseye
`000009-0030-F-1010`, Oceanside `OF1009S`, Youghiogheny `Y1000HS`, Wissmach `EM4134`).

coglassworks carries all four brands (Bullseye 79, Wissmach 56, Youghiogheny 42, Oceanside 40
vendor-tagged, likely more under the generic "Colorado Glassworks" vendor bucket with the brand
only named in the title — see below), so brand overlap is good. **SKU overlap is not:**

- The store's own `variants[].sku` field is populated with **Colorado Glass Works' internal
  intake code** (`RK950`, `RA847`, ...) or a barcode-style tag (`WM-93169453`) — confirmed by the
  same RK/RA numbering sequence being reused indiscriminately across Bullseye, Wissmach,
  Youghiogheny, Oceanside, Kokomo, Uroboros, Spectrum, Lamberts, Armstrong and Fremont listings.
  It is not the manufacturer's catalog SKU and cannot be looked up against the registry or
  Delphi's manufacturer catalog.
- A real manufacturer style/catalog code is only recoverable when it happens to be typed into the
  product **title** in parentheses (e.g. `(WI 96 270L)`, `(130.8RRF)`, `(Y6600SPI)`) — measured at
  roughly **63 of 1,361 products (4.6%)** across the four registry brands, and even that requires
  building a style-number → registry-SKU crosswalk (Oceanside's `130.8RRF`-style numbers are not
  the same string format as the registry's `OF1009S`-style SKUs — unverified whether a clean 1:1
  mapping exists without checking Oceanside's own published cross-reference, not done here).
- **57.8% of the whole catalog (786/1,361) carries no manufacturer vendor tag at all** (bucketed
  as "Colorado Glassworks"/"Colorado Glass Works"/"Unknown"); of those, 468 are brand-inferable
  from a manufacturer name appearing in the title text, but **318 (23.4% of the entire catalog) —
  including the lead product itself, `amber-white-wispy-rk950`** — have no manufacturer signal
  anywhere in the record. For this slice, brand is simply unknown without a color/pattern
  fingerprint match against the registry's own catalog images (feasible in principle — the
  registry has `local_image` crops — but that's a visual-similarity project, not a lookup, and
  carries exactly the name-collision-style false-positive risk documented in §3).

**Bottom line for task 3:** a small number of coglassworks products (order of dozens, not
hundreds) can be reliably tied to a registry entry via an embedded manufacturer style code today.
The bulk of the overlap-in-principle (same four brands, ~1,300+ listings) is blocked on either (a)
a Wissmach/Oceanside/Youghiogheny style-number crosswalk table, which may or may not already
exist publicly, or (b) visual matching, which needs the same collision-safety design as §3 before
it can be trusted. **Not a near-term unlock; flag as a follow-up worth ~1 day to check whether the
manufacturers publish style-number cross-references, before investing in visual matching.**

Delphi cross-reference: not checked in this pass (would need Delphi's `manifest_033.json` brand
tags cross-matched against coglassworks' vendor+style-code slice above) — same blocker (coglassworks
mostly lacks manufacturer SKUs), likely similarly low yield; flagged as a follow-up, not measured
here to stay inside the task's scope.

## 5. Sibling sources surveyed (~25 min, one example URL each)

| source | verdict | example | why |
|---|---|---|---|
| **coglassworks.com** | promising (this report) | (above) | held-sheet photos, large catalog, explicit agent-facing JSON API |
| **Warner Art Glass** (`warnerartglass.com`) | promising, but weaker | `warnerartglass.com/youghiogheny-deep-cobalt-opal-coe96-glass` | Consistent **backlit studio photography** (filenames literally say `backlight_1.jpg`/`backlit2_1.jpg`) — clean, deliberate lighting condition, good "reference" style — but the two products checked had only **one image each**, so it's a single-capture source per product, not a pair source, unless deeper products turn out to have both a backlit and a non-backlit shot. `robots.txt` present, empty body (no disallow directives found) — technically open. Worth a deeper 20-product check before ruling in/out, not done here. |
| **Bradstreet Glass** (`bradstreetglass.com`) | unconfirmed / not deep-checked | `bradstreetglass.com/collections/kokomo-stained-glass` | Sells Kokomo/other-brand sheet glass; the specific sub-collection URL guessed for this check 404'd, didn't find a working product page in the time budget. Flagged as worth a second look, not ruled out. |
| **Stained Glass For Less** (`stainedglassforless.com`) | not promising for this task | `stainedglassforless.com/light-purple-white-wispy-ogt-349-2sf-6-6-x-12-sheet/` | Flat studio swatches only (BigCommerce standard product photography) — no held-sheet shots seen. Notably its URLs *do* embed real Oceanside-style catalog codes (`ogt-349-2sf`) — could be useful later purely as a **SKU crosswalk source** for §4, not as a pair source. |
| **Anything In Stained Glass** (`anythinginstainedglass.com`) | not recommended | `anythinginstainedglass.com/glass/index.html` | Old ShopSite platform; `robots.txt` explicitly **disallows `/images`, `/wissmach`, `/spectrum`** — the exact paths that would matter for this task. Respect it; don't pursue. |
| **Kokomo Opalescent Glass** (`kog.com`, manufacturer direct) | not promising | `kog.com/kokomo-opalescent-glass/` | Manufacturer's own site; product images are lazy-loaded/placeholder in a plain fetch, and manufacturer-direct sites in this space tend toward promotional/finished-piece photography rather than remnant hand-held shots. Not deep-checked with a real browser render — could be revisited. |
| **Franklin Art Glass** (`franklinartglass.com`) | blocked | — | 403 to both `curl` and `WebFetch` with a normal UA — same shape as Delphi's live-site block. Would need a Wayback-style workaround; not attempted here (out of scope for a 30-min survey). |
| **Sunshine Glassworks** (`sunshineglass.com`) | inconclusive | `sunshineglass.com/shop/` | 403 on the shop path with a plain UA in this pass; the marketing site (`sunshineglass.com/`) itself is reachable. Worth retrying with a product-page URL directly rather than the shop index. |

**Two best: coglassworks (this report's main subject) and Warner Art Glass** (for its deliberate,
consistently-labeled backlit condition — even if it turns out to be single-image-per-product, it's
a good *third* clean/backlit reference style to diversify against Delphi's `lightbox` and
coglassworks' `window`, worth the ~20-product deeper check this pass didn't have time for).

## 6. Recommended scrape plan if greenlit

1. **Reuse, don't rebuild:** port `../realpairs/classify.py`'s capture-type heuristic and
   `../realpairs/harvest_033.py`'s throttled-fetch/manifest scaffolding; the taxonomy (§3 of
   `REAL_PAIRS_DATASET.md`) should transfer with minor tuning (this store never produces a true
   `lightbox` shot, `window`/`shop_held`/`standing` all apply, `closeup` and `other` unchanged).
2. **Identity grouping is the one genuinely new component needed** (Delphi didn't need this
   because Delphi's product_id already =1 physical listing reliably per report 030 §8): group each
   listing's images by SKU filename token where the SKU-named convention applies (815/1,361
   listings, §2.2); for the `IMG_####` convention (523/1,361), either (a) skip — leaves ~1,000
   filename-verified pairs, cheapest and safest, or (b) add a cheap VLM same-piece check (read
   the in-frame sticker text, or eyeball color/pattern/shard-shape match) — more pairs, more
   engineering, and the natural place to also cross-check the SKU-named subset's sticker text as a
   confirmation signal.
3. **Scale:** full catalog ≈ 5,780 images (1,361 products × measured mean 4.25 images/product),
   measured mean size ≈ 486 KB/image (from this pass's 76-image sample) ≈ **~2.7 GB**. At the same
   throttle used for this scoping pass (1 req/s, normal descriptive UA) that's **~96 minutes** of
   trickle image traffic, plus 6 trivial `products.json` page requests for discovery (no per-product
   HTML loads needed at all, unlike a naive crawler — the collection JSON already has full image
   arrays). Comparable order of magnitude to the Delphi harvest (33 minutes for ~1,900 images);
   larger here because the catalog itself is ~4x bigger.
4. **Store raw images gitignored**, same posture as `realpairs/data/` — add
   `research/delighting/pairsources/data/` (or similar) to `.gitignore` before the full pull;
   commit only manifests, derived stats, and small downscaled panels.
5. **Get the §7 sign-off first** — this is a bigger, more consequential pull than the scoping
   sample and the store's ToS text is a more direct "no scraping" statement than Delphi's, even
   though the store's own `agents.md`/`robots.txt` invite exactly this kind of read-only access.

## 7. Politeness & licensing — same honest framing as the Delphi report

**Mechanically polite:** all discovery in this pass used the store's own documented JSON API
(§1); all image fetches were sequential, ~1 req/s, with a UA string identifying the project and a
contact email; total footprint for this scoping pass was 6 JSON requests + 76 image GETs over
~2 minutes of wall time. A full scrape (§6.3) stays a comparably light trickle load.

**The honest ToS flag:** unlike Delphi, this store's `robots.txt` explicitly links to
`agents.md`, which explicitly documents `GET /collections/{handle}/products.json` and
`GET /products/{handle}.json` as **intended, sanctioned, read-only agent access** — the store
operator (via Shopify's agentic-commerce tooling) has deliberately published machine-readable
permission for exactly the kind of access this scoping pass used. At the same time, the store's
generic Shopify Terms of Service (boilerplate, not sheet-glass-specific) contains an unambiguous
clause prohibiting use of the Service "to spam, phish, pharm, pretext, spider, crawl, or scrape"
and a separate "you agree not to reproduce, duplicate, copy... any portion of the Service...
without express written permission." **These two documents point in different directions** — the
same shape of tension the Delphi report flagged (there: robots.txt silent + ToS restrictive; here:
robots.txt/agents.md affirmatively inviting + ToS boilerplate restrictive) — and it is not
resolved here, per this project's standing practice of surfacing rather than unilaterally deciding
this kind of call. **Recommendation, mirroring report 030 §5: get explicit maintainer sign-off
before scaling past this scoping sample**, noting in the maintainer's favor that (a) the site
itself publishes an agent-facing API for this exact use, (b) the ask (read-only derived
statistics + internal research use, no redistribution) is the same modest shape the Delphi
sign-off already covered, and (c) product photography here is even more clearly the retailer's
own (not the manufacturer's) work, arguably lower-stakes than reproducing manufacturer catalog
photography. Nothing from this pass was redistributed or published beyond this repo; the 76
sample images are gitignored, and the only committed visual artifact is the small downscaled
`pair_sources_board.jpg`, captioned as Colorado Glass Works' photography.

## 8. What this scout does NOT establish

It does not establish that the "true cross-capture" (different-lighting) subset is as large as
the raw pair count suggests (§2.4 — needs the classifier run at scale to tighten the ~150-250
estimate); it does not establish a working SKU crosswalk to the registry or to Delphi (§4 — flagged
as a follow-up, not attempted); it does not confirm Warner Art Glass or Bradstreet Glass one way or
the other beyond a single product each (§5); and it does not resolve the ToS tension in §7 — that
is a maintainer call, deliberately left open here as it was for Delphi.
