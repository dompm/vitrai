# 042 — Agentic image-search retrieval loop: same glass product, multiple contexts

Branch `research/delighting-042-search-loop`. Companion to report 041 (retailer
pair-source scouting, concurrent). Scripts in `../search_loop/`; verified sets and
verdicts in `../search_loop/results/` (committed, URLs + JSON only); review board at
`../results/042/search_loop_board.jpg`. Raw scraped candidate images (62 MB) are
gitignored, local-disk only — same research-use posture as
`docs/REAL_PAIRS_DATASET.md` §5.

## 0. Framing — what these pairs ARE and ARE NOT

The loop finds images of the **same glass product** (same manufacturer SKU/colorway)
in multiple capture contexts via web image search. These are almost always
**different physical sheets** — a retailer's lightbox swatch and an Etsy seller's
window shot photograph different pieces of the same product line.

- **NOT eligible** for the registered same-coordinate consistency benchmark
  (`EVAL_PROTOCOL.md` §3c, `docs/REAL_PAIRS_DATASET.md`): that requires the same
  physical sheet, pixel-registrable across captures. Nothing here can feed the
  registrable cross-capture pair count.
- **Their value is**: (a) **weak material-invariance pairs** for the
  latent-material-code training signal (`docs/MATERIAL_MODEL_V3.md`) — same product
  means approximately the same material state `{T, σ_s, a_glow, height-family}` even
  across sheets, so a material encoder should map both captures near each other;
  (b) **real-domain "person holding glass" coverage** — handheld/shop/window phone
  photos, the capture style the delighting product actually receives and that the
  Delphi harvest covers only in that store's house style.

## 1. Pilot design

15 products hand-picked from `frontend/public/assets/glass_swatch_registry.json`
(branch `fix/sheet-drag-prop`, read-only; 1,269 products total), spanning all 4
manufacturers and 6 of 7 categories, mixing high-recognizability names (Red Flemish,
Vienna Spirit) with likely-hard cases (Copper Tint, White Opal Granite, uniform
Petal Pink):

| manufacturer | products |
|---|---|
| Bullseye (4) | Sunset Coral Transparent Irid, Alchemy Clear Silver-to-Gold, Copper Tint, Petal Pink Opalescent |
| Oceanside (4) | Vienna Spirit, Jungle Fog Fusers Reserve, "South Beach", Medium Blue Rough Rolled |
| Youghiogheny (3) | Yellow/Red True Dichro, White Opal Granite, White Ice Ruby Bubblegum Stipple |
| Wissmach (4) | Red Flemish, Evergreen Streaky, Thunderbird Opal, Clover Wisspy |

Reference swatches: the registry's own catalog images (local copies, gitignored).

## 2. The loop (scripts, in order)

1. **`search_candidates.py`** — 3 query variants per product
   (`<mfr> <name> stained glass sheet` / `<mfr> <name> glass` / reversed) via the
   `ddgs` python package (DuckDuckGo image search, no API key).
   **Engine reliability finding:** ddgs intermittently returns a completely
   unrelated "fallback gallery" with no error — our first test query for "Bullseye
   Sunset Coral stained glass sheet" returned ten photos of Hostess snack cakes.
   Added a title-vocabulary relevance guard (≥40% of batch titles must share a
   token with mfr/product name) with one retry. Measured: **4 of 45 base queries
   (~9%) hit the fallback**, all 4 recovered on retry. 25–43 unique URLs/product,
   509 total.
2. **`download_candidates.py`** — top ≤15 images/product, throttled ~1 req/s per
   host, skip <300 px, dedupe by sha256 + perceptual hash (hamming ≤4).
   Result: **225/225 slots filled** (15/product); attrition: 5 fetch failures,
   14 too-small, 1 phash dup.
3. **`vlm_verify.py`** — the collision guard. One `claude -p` CLI call per product
   (pinned `--model sonnet`, `--allowedTools Read`): the model Reads our reference
   swatch as image 1 and the 15 candidates as images 2–16, judges same-product
   plausibility per candidate, and classifies context
   (flat-swatch / held-in-hand / backlit-window / installed-project / other),
   answering strict JSON (parse + retry once). All 15 products parsed on the
   first attempt.
4. **`aggregate_042.py`** → `results/verified_sets.json` (per-product verified
   image sets with context labels + source URLs) and `aggregate_042.json`.
5. **`build_board.py`** → `../results/042/search_loop_board.jpg` (rows: reference |
   verified finds, context label baked into each tile).

## 3. Yield (measured)

**74/225 candidates admitted (33%), 4.9 verified images/product; 10/15 products
multi-context.**

| pid | verified | contexts |
|---|---:|---|
| bullseye Sunset Coral Irid | 8 | flat×8 |
| bullseye Alchemy Silver-to-Gold | 11 | other×5, flat×3, backlit×3 |
| bullseye Copper Tint | 0 | — (correct rejection; see §5) |
| bullseye Petal Pink Opal | 5 | flat×5 |
| oceanside Vienna Spirit | 6 | flat×4, backlit×1, hand×1 |
| oceanside Jungle Fog FR | 7 | flat×4, hand×2, backlit×1 |
| oceanside South Beach | 1 | other×1 |
| oceanside Medium Blue Rough Rolled | 7 | backlit×4, hand×2, flat×1 |
| youghiogheny Yellow/Red Dichro | 6 | flat×5, backlit×1 |
| youghiogheny White Opal Granite | 0 | — (correct rejection; see §5) |
| youghiogheny White Ice Ruby Stipple | 8 | flat×4, other×2, backlit×2 |
| wissmach Red Flemish | 6 | flat×3, backlit×1, hand×1, other×1 |
| wissmach Evergreen Streaky | 2 | flat×1, hand×1 |
| wissmach Thunderbird Opal | 2 | flat×1, other×1 |
| wissmach Clover Wisspy | 5 | flat×3, backlit×1, other×1 |

Context mix of admits: **flat-swatch 42 (57%), backlit-window 14 (19%),
other 11 (15%), held-in-hand 7 (9%)**, installed-project 0.

**Honesty note on the flat-swatch majority:** many flat-swatch admits are the
manufacturer's own catalog photo re-hosted by resellers (Bullseye CDN, Delphi,
creativeglassshop, etc.) — i.e. near-duplicates of our reference image, not new
captures. The genuinely novel material is the wild slice: **21 hand/window images
(28% of admits, 1.4/product)** plus non-duplicate flat shots (Etsy sellers' own
photos). A production run should phash-compare admits against the reference and
manufacturer CDN variants to separate "same photo re-hosted" from "new capture."

## 4. Precision spot-check (my own eyeballing)

Method: contact sheets for 5 products (3 judged blind before reading VLM verdicts:
Red Flemish, Vienna Spirit, Petal Pink; 2 targeted after: White Opal Granite,
Alchemy) — 75 verifications reviewed, plus full-resolution adjudication of 8
disputed candidates. Of the **47 admits examined, 6 were confirmed wrong and 3–5
questionable → measured admit precision ≈ 81–87%.**

Confirmed wrong admissions, all sharing one failure signature (right texture family
or right brand, wrong color):

1. `wissmach-wwo708` idx13, conf 0.8 — reason says "bright green wispy…"; the image
   is a **pink/orange sheet whose in-frame label literally reads "Selenium Orange
   Wisspy Opal"**. The funniest false positive of the run, and diagnostic: the
   stated reason doesn't describe the image, i.e. index/description misalignment
   inside a 16-image batch.
2. `wissmach-wwo708` idx11, conf 0.7 — deep purple/blue streaky admitted as "green
   streaky wispy backlit."
3. `oceanside-of134rr` idx10, conf 0.9 — **turquoise** rough-rolled admitted as
   "medium blue rough-rolled" (same Oceanside texture line, different colorway).
4. `oceanside-ofr85` idx7, conf 0.9 — dark blue glitter/aventurine handheld sheet
   admitted as "glossy green/teal swirl," context also wrong (flat-swatch).
5. `oceanside-ofr85` idx14, conf 0.7 — a black **Fusers Reserve promo card showing
   three RED/ORANGE glasses** admitted because it carries the Fusers Reserve badge —
   brand-text matching over visual evidence.
6. `wissmach-wi18flem` idx11, conf 0.8 — smooth red sheet propped in a shop admitted
   as "hand holding glass with matching bumpy cell texture" (no hand, no flemish
   texture; hallucinated description).

Questionable: Vienna Spirit idx8/14 (diagonal blue wispy cousins vs. the reference's
dash/spot pattern), of134rr idx13 (darker handheld), Alchemy idx7/9/14 (golden-dot
backlit shots — plausibly the same striker glass fired, unverifiable).

Notable wins (why VLM verification earns its keep):
- Read retailer labels to **reject the within-brand lookalike** Bullseye Pink Opal
  000301 vs. our Petal Pink 000421 (visually near-identical pale pinks), and to
  admit a labeled `000421-0030-F` sheet at 0.98.
- Rejected the Alchemy Silver-to-**Bronze** (001016) sibling SKU by label.
- Spotted a handwritten "43176" product code in a Vienna Spirit held-in-hand shot.
- Conservative rejections were sensible; recall loss vs. my blind judgment was ~2–3
  borderline cases per product, acceptable for a precision-first pipeline.

**Name-collision cases found (the user-flagged risk, confirmed real):**
- **"Copper Tint"** → Etsy antique/salvage window glass ("copper tint" is vintage
  glazing vocabulary). All 15 candidates were vintage amber sheets; VLM correctly
  admitted none. Root cause is compounded by our reference being a nearly blank
  pale swatch (~zero discriminative content).
- **"White Opal Granite"** → token-overlap retrieval of Youghiogheny "White Opal
  Turquoise Green" and other Y-RG SKUs; all correctly rejected by label+color.
- **"Spirit" / "Streaky" / "Opal" line names** pollute retrieval with sibling
  colorways — the dominant residual false-positive source (see §6 fix 2).

## 5. Cost / time per product (measured)

| stage | per product | notes |
|---|---|---|
| search | ~16 s | 3 queries + 1.5 s throttle; +retry on ~9% fallback batches |
| download | ~22 s | ≤15 imgs, 1 req/s/host; wall time overlaps across hosts |
| VLM verify | 81 s wall (mean; 35–153 s) | sonnet via `claude` CLI, 16 images/call; 3-way pool → ~27 s/product effective |
| **total** | **~2 min sequential, ~1.1 min pooled** | |

Token cost: ~16 images ≈ 20–26k image tokens + prompt/loop overhead → roughly
$0.10–0.25/product at Sonnet API list rates ($3/MTok in, $15/MTok out; intro
$2/$10 through 2026-08-31). Run here on the subscription CLI, so marginal dollar
cost was zero but rate-limit budget is real.

## 6. Projection to the full 1,269-product corpus

Straight-line from pilot means (±: the pilot is 15 products, so ±30% at least):

- **Search:** 3,807 queries ≈ 2.5 h throttled; expect ~350 fallback-gallery retries.
- **Download:** ~19,000 images, ~5.3 GB local (never committed); ~8 h at current
  politeness settings.
- **VLM:** ~29 h sequential / ~10 h at 3-way pool; ~$150–320 at Sonnet API rates.
- **Yield:** ~6,250 admitted images; at 81–87% precision → **~5,100–5,400 true
  same-product images**; wild contexts (hand+window) ≈ **~1,800 images**;
  multi-context coverage ≈ **~840 products (2/3 of corpus)**. After same-photo
  dedupe vs. references (§3 note), expect the *novel-capture* count to be roughly
  half the admit count: **~2,500–3,000 genuinely new captures**, of which the
  ~1,800 wild ones are the training payoff.

## 7. Recommendation: **scale-with-changes**

The loop works: 33% admit rate, ~85% precision, 2 min/product, and the VLM guard
demonstrably catches both name collisions and within-brand lookalikes (label
reading is a real capability win). But do not scale as-is; the six confirmed false
positives all funnel through fixable mechanisms:

1. **Batch ≤8 candidates per VLM call, and require a per-image color/texture
   statement before the verdict.** All description-hallucination/misalignment
   failures (§4 items 1, 2, 6) occurred deep in 16-image batches. Smaller batches
   + forced per-image grounding ("state the dominant color of image N, then judge")
   should eliminate them at ~2× call count (~$0.4/product, still cheap).
2. **Add a cheap hue-histogram gate before the VLM.** 5 of 6 confirmed false
   positives are wrong-color admits; a reference-vs-candidate hue-chroma centroid
   distance check (infrastructure already exists in `realpairs/`) would have
   rejected all 5 for pennies, and also hard-blocks the colorway-cousin trap.
3. **Pre-filter low-information references.** Copper Tint's near-blank swatch can
   verify nothing; flag references with low channel variance and either skip or
   substitute the manufacturer product photo.
4. **Prompt: "a different colorway of the same texture line is NOT a match."**
   Directly targets the Spirit/Rough-Rolled sibling problem.
5. **Keep the ddgs relevance guard** (9% silent-garbage rate is too high to run
   unguarded) and the 1 req/s host throttle.
6. **Post-admit phash dedupe against the reference + manufacturer CDN** to split
   "same catalog photo re-hosted" (dedup metadata) from "new capture" (training
   data) before anything feeds the material-invariance set.

Licensing posture: candidate images are retailer/marketplace product photography;
raw downloads stay gitignored and local, only the small downscaled review board is
committed, captioned as third-party photography — same maintainer-approved posture
as the Delphi harvest (REAL_PAIRS_DATASET.md §5). A corpus-wide run distributes
nothing but adds ~19k downloads across many hosts; per-host volume stays trivially
polite, but the §5 sign-off logic applies here too.
