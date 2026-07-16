# 051 — Catalog product retrieval from one photo + confidence gate

Branch `research/delighting-051-catalog-retrieval`. Code in `../catalog051/`
(`embed.py`, `build_clean_index.py`, `retrieve.py`, `rp_data.py`,
`realpairs_bench.py`, `run_all.py`, `run_crop_ablation.py`, `transforms.py`,
`vlm_verify051.py`, `make_board.py`, `relief_name_audit.py`); committed
evidence in `../results/051/` (summary_all.json, summary_crop.json, per-run
bench_*.json, failure_decomposition.json, relief_name_audit.json,
vlm_verify.json, board_raw.jpg, board_crop50.jpg). Embedding caches and
per-query/curve dumps are gitignored — regenerate with `run_all.py` then
`run_crop_ablation.py` (≈40 min on MPS, fastbook venv).

**The product question (CTO):** when a user uploads a photo of a glass sheet,
can we RECOGNIZE which catalog product it is, so per-SKU presets (relief, now
report 050's auto-detected procedural presets, plus metadata) can be looked up
— with per-photo material estimation still handling that sheet's specific
colors/streaks? And since users will upload sheets outside the catalog: can we
CALIBRATE a "confidently in-catalog" gate, falling back to photo-only
detection (050) below threshold?

## 0. Headline

**Recognition: partially — 1-in-3 top-1 within a 226-product catalog, and only
after a crop stage; the naive full-frame pipeline gets 1-in-8. The calibrated
confidence gate: NO at any useful recall — in-catalog vs out-of-catalog score
distributions are near-inseparable (AUC 0.52–0.57). There IS a tiny
ultra-confident tier (cosine ≥ 0.91, ~3% of queries, 100% top-1 precision
measured) that can auto-confirm; everything else must be presented as
suggestions or fall back to 050.** Delighting the query does NOT help retrieval
— the classical-delighted T actually hurts (§4), and the win that does exist
(center-crop, 2× accuracy) is about composition, not illumination. A VLM
verification stage on the top-5 shortlist adds real precision (§6). Texture
FAMILY is largely solved by metadata + retrieval-of-the-look; the exact-SKU
colorway within a family is the hard, often visually ill-posed part (§5).

## 1. Setup

- **Index backbone:** DINOv2-small (`facebook/dinov2-small`, 384-d pooled CLS,
  HF transformers, MPS) — verified downloadable + runnable BEFORE building
  (report 028 lesson): loads in ~10 s, self-retrieval sanity 1.000. One entry
  per image, product score = max-pool over the product's entries, cosine
  similarity.
- **Catalog side:** the canonical clean corpus (report 021/024;
  1,281 images, Bullseye/Oceanside/Youghiogheny/Wissmach) embedded as
  `results/051/clean_index_dinov2.npz` (gitignored) + committed meta. In the
  benchmark it serves as the realistic distractor pool; it is also the index
  the shipped app would start from.
- **Benchmark:** the report-033 real cross-capture pairs. Query = a product's
  WILD captures (window 444 / shop 230); target = the same product's CLEAN
  captures (closeup/lightbox) in the index. All report-033 contamination
  screens applied (stock-photo dhash groups, lineup/on-white, finished-product
  tail slots, mirror/multi-pack products, suspect same-photo pairs — §9.3 of
  the dataset card). **674 wild queries over 176 scorable products; index =
  490 realpairs reference images (226 products with ≥1 clean capture) + the
  1,281 clean-corpus distractors = 1,771 entries / 1,507 products.**
- **Harvest restoration:** the 033 raw images (368 MB, gitignored, local-only)
  were not on this machine; maintainer authorized re-running the idempotent
  `harvest_033.py` under the original 033 posture (Delphi CDN only, ~0.40
  req/s measured, 62 min, descriptive UA with contact email). **Zero
  attrition:** 254/254 products, 1,491/1,491 images, 100% capture-label
  agreement with the frozen `manifest_033.json` — the benchmark is exactly the
  dataset 033 froze.
- **Holdout discipline:** retrieval here is zero-shot (no training), so the
  034 holdout can be scored without leak; it is reported as a breakdown
  (holdout products score slightly ABOVE eval-eligible — 33% vs 25% top-1 at
  crop50 — so no optimistic-selection concern).

## 2. Main result: wild→clean product retrieval

| run (674 queries) | top-1 | top-5 | gate AUC |
|---|---:|---:|---:|
| raw photo, + distractors (PRIMARY) | 12.6% | 26.3% | 0.523 |
| raw photo, no distractors | 13.5% | 28.8% | 0.524 |
| delighted-T (extract.py), + distractors | **9.8%** | 23.7% | 0.515 |
| 019 luma-quotient, + distractors | 12.2% | 26.4% | 0.523 |
| **center-crop 50%, + distractors** | **26.6%** | **44.4%** | 0.552 |
| center-crop 50% + quotient | 26.9% | 45.7% | 0.553 |
| center-crop 30%, + distractors | 26.7% | 44.2% | 0.565 |
| center-crop 50%, no distractors | **33.2%** | **54.7%** | 0.566 |

Reading order matters here:

1. **The naive pipeline is weak (12.6%)** — but not because the catalog
   confuses it: removing all 1,281 clean-corpus distractors buys back less
   than one point. The problem is the query side.
2. **A dumb central crop DOUBLES accuracy.** Wild captures carry windowsills,
   trees, racks and hands; DINOv2's global embedding is scene-dominated.
   Cropping to the central 50% (where Delphi's house style — and most users
   photographing "their sheet" — put the glass) recovers more than every
   illumination treatment combined. **The product lesson: a sheet-detection /
   crop stage (or UI guidance to fill the frame) is the single
   highest-leverage component**, worth more than any delighting.
3. **At realistic catalog scale the pool costs ~6.6 points** (33.2 → 26.6)
   — after cropping to pure texture, cross-brand look-alikes in the corpus
   steal 34% of top-1s (vs 8% pre-crop; `failure_decomposition.json`).
   Catalog growth will keep eroding exact-SKU top-1.
4. **No clean-reference penalty:** the any-capture leave-one-image-out
   diagnostic (target = ANY other capture of the product, 718 queries) scores
   12.8%/28.4% — the same as clean-target. Matching a wild capture to
   ANYTHING else of the same sheet is the hard part; that the reference is a
   clean studio-ish closeup costs nothing extra.

Per-brand (crop50, top-1): uro 33% (n137), clear-textured 31% (n240), kokomo
30% (n30), tiffany-today 28% (n161), **wissmach 4% (n76)** — Wissmach's
realpairs presence is almost entirely English Muffle colorways, the
family-colorway confusion case in §5. Window and shop captures score the same
(27%/26%); opal-caution products score no worse than identity-clean ones
(29% vs 25%).

## 3. The confidence gate — the honest, load-bearing negative

Out-of-catalog was simulated by leave-product-out: for every query, re-score
with the true product's entries removed from the index; the top-1 cosine that
remains is exactly what an out-of-catalog upload would produce against this
index. Compared against in-catalog top-1 cosines:

| representation | AUC (in vs out) | in-cat median | OOC median |
|---|---:|---:|---:|
| raw | 0.523 | 0.663 | 0.654 |
| crop50 | 0.552 | 0.727 | 0.709 |
| crop50 no distractors | 0.566 | 0.727 | 0.685 |

**These distributions overlap almost completely.** The reason is structural,
not a tuning miss: this catalog contains many NEAR-DUPLICATE products
(colorways of one texture line, cross-brand equivalents), so removing the true
product leaves a sibling whose score is nearly as high — out-of-catalog
queries look exactly like in-catalog queries of a sibling SKU. A cosine
threshold cannot tell "right product" from "similar product", and that is the
same reason exact-SKU top-1 is hard.

What survives calibration:

- **An ultra-confident auto-confirm tier exists:** at cosine ≥ 0.913 (the
  measured precision-0.90 threshold, crop50), 18/674 queries (2.7%) pass and
  **all 18 are top-1 correct**. Precision holds; recall is 2.7%.
- The best balanced operating point (Youden) is t = 0.817: 21.5% recall at
  61% precision — **not shippable** as an "in catalog" claim.
- Margin (top1−top2) is no better — sibling SKUs crush it by construction.

Per the brief's instruction not to ship an uncalibrated heuristic confidence
(the 019-024 library-picker lesson): **the separation is poor and we say so
plainly.** The gate interface that follows honestly from the measurements is a
three-tier design, not a binary:

```
score >= 0.91  ->  auto-confirm SKU        (~3% of uploads, measured 100% top-1)
else           ->  show top-5 as *suggestions* (44% contain the right product
                   at crop50; VLM verification, §6, can promote one to a
                   confirm or reject all)
always         ->  run photo-only detection (050 relief presets + per-photo
                   T/sigma_s estimation) — retrieval AT BEST adds metadata; it
                   never gates the photo-only path off
```

050's fallback isn't a fallback at this accuracy — it's the primary path,
with retrieval as an opportunistic metadata bonus. (Texture family, though,
often doesn't need the gate at all — §7.)

## 4. Does delighting help retrieval? No — and it costs

The research tie-in question, answered as a product-grounded
capture-invariance eval:

- **Classical-delighted T (extract.py, auto class prior, no VLM, 384 px):
  9.8% top-1 vs 12.6% raw — delighting HURTS by 2.8 points.** The extractor
  assumes the frame IS a glass sheet; on wild frames it happily "delights" the
  windowsill and foliage, and its illumination-envelope division flattens
  exactly the low-frequency color statistics the embedding was using to match.
  DINOv2 was trained on natural photos — it is already largely
  illumination-robust; preprocessing that alters image statistics away from
  the training distribution costs more than the invariance it adds.
- **019 luma-quotient: 12.2% ≈ raw (12.6%), and crop50+quotient (26.9%) ≈
  crop50 (26.6%)** — the cheap homomorphic normalization neither helps nor
  hurts; the embedding had already absorbed what it removes.
- **What DOES transfer poorly is composition, not illumination** (crop 2×
  win, §2). For retrieval, "delight the query" is the wrong knob; "isolate
  the sheet" is the right one. Delighting remains the right tool for its
  actual job (material estimation on an already-isolated sheet region — the
  T/σ_s per-photo path is untouched by this finding).

## 5. Failure modes, characterized (failure_decomposition.json + boards)

- **Exact-SKU vs the-look:** among crop50 misses, top-1 shares the query's
  brand 37% and its relief family 23%; 13% is the same product LINE, wrong
  colorway. The embedding reliably lands in the right visual neighborhood and
  cannot pick the sibling. `board_crop50.jpg` rows 9–11 show it concretely:
  an "English Muffle Sussex Green" window shot (green foliage showing THROUGH
  clear muffle glass) retrieves Noble Brass / Sage / Emerald Muffle — right
  family four times over, wrong colorway every time.
- **Clear glass IS its background** (the known hard case, confirmed): a clear
  textured sheet's apparent color is whatever is behind it, so wild captures
  of clear products carry a color signal that is pure noise w.r.t. identity.
  Texture survives; color misleads. Wissmach's 4% is this failure
  concentrated. No 2-D preprocessing fixes it — the information isn't in the
  photo; only texture-selective matching (patch-level, color-suppressed) or
  the VLM's reasoning partially compensates.
- **Name-collisions / photo reuse:** handled upstream — clean corpus is
  hash-deduplicated (021), realpairs applies the 033 dhash stock-photo screen;
  the Spectrum→Oceanside relisting duplicates are on the killed side of that
  screen. Residual risk: relisting-style near-duplicates ACROSS the two
  corpora (a Delphi-sold Wissmach vs our Wissmach corpus) can make a "wrong"
  top-1 that is actually the same physical product under another SKU;
  measured top-1-steals by the corpus at crop50 (34%) will include some of
  these, so the true product-level accuracy is, if anything, slightly
  understated.
- **Scale/zoom mismatch** between a whole-sheet window shot and a closeup
  reference crop remains unaddressed by global embeddings; multi-scale query
  crops or patch-token matching are the obvious next lever (not attempted —
  scope).

## 6. VLM top-5 verification (budget ~40 calls, sonnet)

`vlm_verify051.py`: one `claude -p` call per query — query photo + its 5
shortlist candidates as images, forced choice "which candidate is the same
product, or none", candidate order shuffled per call. Stratified sample:
top-1-correct (A), correct-in-top-2..5 (B), correct-not-in-top-5 (C).

40/40 calls succeeded (zero parse failures). Shortlists came from the PRIMARY
(raw) run — per-stratum rates below are measured there; applying them to
crop50's shortlists is an extrapolation, flagged as such.

| stratum (n) | embedding top-1 | VLM choice correct | VLM said "none" |
|---|---:|---:|---:|
| A: top-1 was correct (14) | 100% | 78.6% | 0% |
| B: correct at rank 2–5 (16) | 0% | **100%** | 0% |
| C: correct not in top-5 (10) | 0% | 0% (n/a) | **70%** |

Three measured findings:

1. **Reranking is where the value is: 16/16 perfect promotion** of the right
   candidate out of rank 2–5. Since top-5 recall is ~1.7× top-1 (44.4 vs 26.6
   at crop50), a single VLM call per upload converts most of that gap:
   estimated end-to-end top-1 ≈ 0.266·0.786 + 0.178·1.00 ≈ **38.7%** at crop50
   (12-point lift; on raw shortlists, where these rates were measured, the
   arithmetic gives 12.6% → 23.6%, near-doubling).
2. **The confirm direction is imperfect (78.6%):** the VLM occasionally
   switches away from a correct top-1 to a sibling colorway — the same
   ambiguity that limits the embedding limits the judge. Net it is still
   strongly positive (its losses on A are much smaller than its gains on B).
3. **"None of these" works at 70% specificity** on hopeless shortlists — the
   only measured signal in this study that meaningfully separates
   shortlist-doesn't-contain-the-answer from shortlist-does (the cosine gate's
   AUC is 0.55). As an out-of-catalog detector it is a second stage, not a
   solution: 30% of hopeless shortlists still get a (wrong) pick, and C-stratum
   here means "product exists but wasn't retrieved", which only proxies true
   out-of-catalog. Cost: one multimodal call (~6 images) per upload, ~10–60 s —
   fine as an async enrichment, not for a blocking UI.

## 7. Per-SKU relief cache: mostly a metadata lookup where it matters

`relief_name_audit.py` (results in `relief_name_audit.json`), separating
surface-RELIEF words (granite/ripple/waterglass/stipple/glue-chip/muffle/…)
from bulk-material words (opal/wispy/iridescent — NOT relief):

| population | texture-NAMED (preset = metadata lookup) | smooth-named (needs per-photo relief) |
|---|---:|---:|
| shipped registry (1,269 SKUs) | **19.8%** | 80.2% |
| clean corpus (1,281 imgs) | 19.5% | 80.5% |
| Delphi realpairs (254 products) | **55.9%** | 44.1% |

Top named families in the registry: stipple 55, granite 44, waterglass 35,
ripple 22, rough-rolled 21, muffle 17, hammered 10 — a ~15-preset dictionary
covers the named fifth of the registry outright. The 80% "smooth-named"
remainder is dominated by double-/thin-rolled cathedrals and opalescents whose
relief is gentle and generic — exactly where 050's auto-detected procedural
presets from the photo are the right source. **Cache design that follows:**
key presets by (manufacturer, texture-family) — populated from metadata for
named SKUs, from 050 detection for the rest; retrieval output (a SKU) resolves
to its (manufacturer, family) key, so even a WRONG-colorway-same-family
retrieval, which is the dominant near-miss mode (§5), still fetches the RIGHT
relief preset. Retrieval accuracy at the family level is far better than at
SKU level, and the preset cache only needs the family.

## 8. What this means for the product idea

1. **Ship the crop/sheet-isolation stage first** — it is worth 2× whatever
   sits behind it, and it also feeds the per-photo material estimator.
2. **Exact-SKU identification from one wild photo is a suggestions feature,
   not an auto-tag** at this accuracy (26.6% top-1 / 44.4% top-5 at realistic
   scale): show top-5, let the user confirm; auto-confirm only the ~3%
   ultra-confident tier; optionally spend one VLM call to promote/reject (§6).
3. **The CTO's out-of-catalog worry is justified but is the WRONG failure
   axis:** out-of-catalog uploads won't be caught by score gating (AUC 0.55)
   — they will look like sibling-SKU matches. The safe architecture treats
   retrieval output as metadata enrichment on top of an always-on photo-only
   path (050 + per-photo T/σ_s), never as a switch that turns that path off.
4. **The relief-preset half of the idea survives even when SKU-recognition
   misses**, because relief keys off the texture family (§7) and family-level
   agreement is the common case among misses.

## 9. Limits & reproduction

- Benchmark queries are Delphi's storefront photography, not real user phone
  photos — one house style, mostly well-centered; real uploads are plausibly
  HARDER pre-crop and no easier post-crop. Statistics-only same-product pairs
  include the 31.5% opal-caution products where same-sheet identity across
  captures is unverified (033 §9.4) — those queries score no worse here, but
  their "correct" label is product-level, not sheet-level.
- DINOv2-small only; -base or patch-token/multi-crop matching untested
  (would be the next iteration alongside a real sheet detector). CLIP path
  exists behind the same interface (`embed.py --backbone clip`) but was not
  benchmarked — the crop finding reorders priorities ahead of backbone shopping.
- Raw images (corpus + realpairs) are LOCAL-ONLY and gitignored; boards commit
  small downscaled thumbnails only, captioned as the manufacturers'/Delphi's
  photography (033 posture).
- Reproduce: `run_all.py` → `run_crop_ablation.py` → `vlm_verify051.py`
  → `make_board.py` (fastbook venv python; ~40 min + VLM calls).
