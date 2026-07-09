# 015 — Real-glass catalog corpus: characterization for research use

Branch `research/delighting-corpus`. Scripts in `../corpus/`, artifacts in `../results/corpus/`.

## TL;DR

The catalog corpus (~3,200 manufacturer swatch photos, ~1,381 registry rows across Bullseye,
Oceanside, Youghiogheny, Wissmach, SGE) is a **class-prior and pseudo-label source**, not a
transmittance ground-truth set, and not uniformly usable even for that without preprocessing:

- **82.8%** of the corpus (2,649/3,200 images) gets a confident `{cathedral-clear, wispy,
  opalescent, dark-opaque}` label straight from metadata (category + a few name-keyword
  overrides). SGE (236 images, 7.4% of the corpus) has **zero** registry coverage.
- Lighting geometry is **not uniformly backlit**. Bullseye/Wissmach read as consistently
  backlit/light-table photography; Oceanside/Youghiogheny mostly backlit but with a
  front-lit-leaning subset (textured/iridescent finish shots, and Youghiogheny's dark-opaque
  texture shots specifically); SGE is a genuinely **mixed bag** — backlit swatches, front-lit
  product photos with drop shadows, and non-swatch imagery (finished ornaments, tools, installed
  windows) all under one manufacturer prefix with no metadata to separate them.
- Running the *unmodified* classical extractor on a 57-image backlit-verified, stratified subset
  is plausible on smooth/milky glass (best-case MAE down to 0.04/255) but has real, identifiable
  failure modes: iridescent/rainbow finishes get baked into `T` as if they were transmitted color,
  highly saturated no-texture solid swatches can degenerate the absolute-scale anchor (one image
  hit `T_anchor_k = 880`, collapsing `T` to all-black, MAE 83/255), and streaky/marbled glass with
  sharp local contrast sometimes loses all texture in `T`.
- The VLM class prior (`vlm_classify.py`, `claude`/haiku CLI) scores **30.6% (11/36)** against
  metadata ground truth — barely above chance for the 3-way choice this sample actually exercised
  — the first real-scale test past the 2-photo validation quoted in the script's own docstring
  ("both correct"). It over-predicts `wispy` and struggles most on `opalescent`/`cathedral-clear`,
  plausibly because its prompt assumes "held against a light source" and a meaningful slice of the
  corpus (§2) isn't backlit that way.
- **Bottom line for research use** (§5): the corpus is good for a classifier training set and for
  grounding the synthetic recipes' color/texture *statistics*, weak-to-unusable as ground truth for
  anything numeric (`T`, `h`, consistency), and only usable as a pseudo-label source with the
  lighting triage + extractor QA gates from this report applied first.

## 1. Registry census

`../corpus/census.py`. Full numbers in `../results/corpus/census.json`; per-file class assignment
in `../results/corpus/per_image_class.json`.

### 1.1 What's actually on disk vs. registered

| manufacturer | files on disk | exact registry match | fuzzy size-variant recovery* | no metadata |
|---|---:|---:|---:|---:|
| Bullseye | 1,650 | 610 (37%) | 995 | 45 (2.7%) |
| Oceanside | 560 | 286 (51%) | 247 | 27 (4.8%) |
| Youghiogheny | 532 | 267 (50%) | 230 | 35 (6.6%) |
| Wissmach | 222 | 218 (98%) | 0 | 4 (1.8%) |
| SGE | 236 | 0 (0%) | 0 | **236 (100%)** |
| **total** | **3,200** | **1,381 (43.2%)** | **1,472 (46.0%)** | **347 (10.8%)** |

\* The registry was deliberately deduplicated to one canonical size variant per SKU (see the
`refactor: deduplicate swatch variants` commit on `scripts/build_swatch_library.py`), so the other
~1,472 on-disk files are `.../fhalf`, `.../ffull`, `.../6x12`-suffixed crops of an *already
registered* design at a different real-world sheet size. `census.py` recovers their metadata by
stripping the known size-variant suffixes and matching the remaining base SKU. This matters: naive
"exact filename in registry" coverage (43%) badly understates how much of the corpus has
recoverable metadata (89%) — the real gap is SGE, not the size variants.

SGE has **no registry row for any of its 236 images** — manufacturer, name, category, dimensions
are all unknown for this slice, and (see §2) its content isn't even uniformly "glass swatch photo."

### 1.2 Category distribution (exact registry rows)

Catalog taxonomy is `{Cathedral, Opalescent, Wispy/Streaky, Textured/Baroque, English Muffle
(Wissmach only), Ring Mottle (Youghiogheny only)}`, fairly consistent across the 4 registered
manufacturers:

| | Cathedral | Opalescent | Wispy/Streaky | Textured/Baroque | other |
|---|---:|---:|---:|---:|---:|
| Bullseye (610) | 342 | 162 | 91 | 15 | — |
| Oceanside (286) | 108 | 57 | 52 | 69 | — |
| Youghiogheny (267) | 146 | 84 | 4 | 25 | 8 Ring Mottle |
| Wissmach (218) | 103 | 53 | 16 | 29 | 17 English Muffle |

### 1.3 Category+keyword -> extractor class mapping

The catalog taxonomy is a **product-line/art-tradition** taxonomy, not a **light-transport**
taxonomy — it doesn't line up 1:1 with the extractor's `{cathedral-clear, wispy, opalescent,
dark-opaque}`, which is about how light passes through the glass. Two corrections were necessary:

1. **"Black Opalescent"** is a whole product line (Bullseye/Oceanside/Youghiogheny all carry it),
   catalogued under `Opalescent`, but at typical viewing/backlighting it transmits very little
   light and reads as near-black, not milky-glowing — optically it's `dark-opaque`. Same for the
   literal word "Opaque" in a name. Caught by regex override
   (`black\s+opal(escent)?|opaque`) *before* the category rule, medium confidence.
2. **"Textured/Baroque"** is a grab-bag category (rough-rolled / hammered / waterglass /
   granite-texture finish applied to otherwise-transparent OR opal glass) that needs a name-keyword
   sub-split: `opal` in the name -> `opalescent`; an explicit N-color "mix" -> `wispy` (streaky);
   else default `cathedral-clear` (the majority of the unlabeled remainder are Youghiogheny's "96
   COE ... Rough Rolled/Waterglass/Hammered" line — textured but transparent). This bucket is
   explicitly **low confidence** — it's a keyword guess over a grab-bag, not a direct category
   match.

Rule table (first match wins), applied to all 2,853 metadata-resolved files (exact + fuzzy):

| rule | class | confidence | n |
|---|---|---|---:|
| `category:Cathedral` | cathedral-clear | high | 1,470 |
| `category:Opalescent` | opalescent | high | 658 |
| `category:Wispy/Streaky` | wispy | high | 385 |
| `textured:default` (Textured/Baroque, no keyword) | cathedral-clear | low | 171 |
| `name:black-opal/opaque-override` | dark-opaque | medium | 103 |
| `textured:opal-keyword` | opalescent | low | 18 |
| `category:English-Muffle->cathedral` | cathedral-clear | medium | 17 |
| `category:Ring-Mottle->opalescent` | opalescent | medium | 16 |
| `textured:color-mix-keyword` | wispy | low | 15 |

Resulting class distribution over the whole corpus: **cathedral-clear 1,658, opalescent 692, wispy
400, dark-opaque 103** (dark-opaque is scarce — it's a rare *product line*, not just a rare
extractor class, which matters for §5's pseudo-label-source verdict).

**Coverage headline:** high+medium confidence (i.e. excluding both the Textured/Baroque keyword
guess and the fully-unregistered residual) = **2,649/3,200 = 82.8%** of the corpus gets a class
straight from metadata with no image inspection at all. Adding the low-confidence tier gets to
89.2%; SGE's 236 images (7.4%) get **no metadata class whatsoever** and would need either VLM
classification or manual labeling.

## 2. Lighting-geometry triage (critical)

`../corpus/triage.py`. The extractor's `T,h` semantics are defined for **backlit** photos only
(`extract.py`'s own model: `L` = *backlight* illumination, `B` = background *seen through* the
glass). A front-lit product shot has no "light passing through onto a background" — there's
nothing for the model to estimate, and the extractor would produce numbers that don't mean what
the rest of the research program (reports 003–013, the T-scale anchor, the preview-invariance
benchmark) assumes they mean. This was flagged as the first thing to check because getting it
wrong silently poisons everything downstream.

100 images stratified across manufacturer x extractor-class (5 per cell, SGE sampled uniformly
since it has no class) were scored with cheap luminance/vignette/specular heuristics and rendered
into a labeled contact sheet: `../results/corpus/triage_contact_sheet.jpg`. **I looked at every
tile.** Per-manufacturer verdict (heuristic means in `../results/corpus/triage_sample.json`):

| manufacturer | mean_lum | p99 | specular_frac | corner/center | sat | auto "backlit" tally |
|---|---:|---:|---:|---:|---:|---:|
| Bullseye | 0.497 | 0.742 | 0.0047 | 1.103 | 0.486 | 14/20 |
| Oceanside | 0.504 | 0.711 | 0.0003 | 1.284 | 0.379 | 17/20 |
| Youghiogheny | 0.441 | 0.780 | 0.0048 | 1.025 | 0.493 | 16/20 |
| Wissmach | 0.410 | 0.636 | 0.0028 | 1.105 | 0.575 | 14/20 |
| SGE | 0.547 | 0.870 | 0.0063 | 1.154 | 0.354 | 12/20 |

**Human verdicts (the numbers above are a weak correlate at best; this is the part that counts):**

- **Bullseye — confidently backlit.** Full-bleed, edge-to-edge, glowing saturated color with
  minimal front-surface sheen except where an iridescent finish is being deliberately shown. This
  is the manufacturer's standard "as it looks held to light" catalog style. One outlier: a flat
  opaque-white tile shot with visible physical edges/corners on a table — clearly front-lit product
  photography, a small minority pattern.
- **Wissmach — confidently backlit, including dark-opaque.** Even the darkest tiles show graduated
  transmission (thin/thick variation glowing through), which is only visible under backlighting;
  a purely front-lit opaque black tile would show flat black with at most surface sheen. Highest-
  confidence uniformly-backlit manufacturer of the five.
- **Oceanside — mostly backlit, with a real front-lit-leaning minority.** Solid-color swatches read
  backlit-glow. But textured/iridescent-finish shots show raking-light surface relief and
  angle-dependent rainbow color banding that can only come from reflected light hitting a coating —
  a photography choice made specifically to *show the finish*, which needs front/side lighting to
  be visible at all. This overlaps materially with the `Textured/Baroque` category (69/286 = 24%
  of Oceanside's registered rows).
- **Youghiogheny — mostly backlit, but dark-opaque specifically looks front-lit.** Cathedral/
  opalescent/wispy swatches read backlit-glow like the others. The dark-opaque tiles, though, show
  clear woven/hammered/granite surface **texture visible through near-total blackness** — texture on
  an opaque black surface is only visible under reflected (front) light; true backlighting through
  fully opaque glass would show flat black with no relief at all. **This is why the extractor
  breadth test (§3) excludes Youghiogheny dark-opaque from the "backlit-verified" subset.**
- **SGE — unreliable, mixed content, cannot be batch-triaged.** Genuinely heterogeneous: some
  backlit-glowing swatches, some overtly front-lit product photos with visible drop shadows on a
  white background, and — critically — **non-swatch imagery**: a finished glass-ball ornament
  wreath, a Christmas-ornament tree, a lampworking rod/tool, and photos of *installed* stained-glass
  windows/mirrors with garden or interior backgrounds visible through them. SGE has zero registry
  metadata to filter any of this out. It needs manual curation before any use, full stop.

**Automatic triage rule: does not work well enough to trust unattended.** The four cheap pixel
heuristics (`p99`, `specular_frac`, `corner_center_ratio`, `sat_mean`) correlate only weakly with
the human read — e.g. they don't detect "surface texture visible through blackness" (Youghiogheny's
dark-opaque tell) or "installed-window vs. swatch" (SGE's actual biggest problem) at all; those
needed eyes on the image. `specular_frac` was the most promising single signal in principle
(front-surface sheen -> reflected light) but didn't separate iridescent-tagged filenames from
plain ones in this sample (mean 0.0046 vs 0.0038, n=5 iridescent — too small and too weak to act
on). **Practical recommendation:** don't build a per-image auto-classifier for this; use a
per-manufacturer prior (Bullseye/Wissmach default-trust; Oceanside/Youghiogheny trust for
cathedral/opalescent/wispy but hold out Textured/Baroque and (for Youghiogheny) dark-opaque for
manual spot-check; SGE always manual) — that's what §3's subset selection actually did.

## 3. Extractor breadth test (no ground truth — plausibility only)

`../corpus/run_extractor_subset.py`. Ran the **unmodified** `extract.py` (class from §1's metadata
mapping, `--no-vlm` equivalent — the class prior is not being tested here, §4 does that) on 57
images: the 100-image triage sample (§2) filtered to `auto_verdict == backlit`, SGE excluded
entirely, Youghiogheny dark-opaque excluded (the front-lit tell from §2). Roughly balanced across
the remaining manufacturer x class cells (2–5 each). Full per-image metrics:
`../results/corpus/extractor_stats.json`. Contact sheet (best 3 / typical 3 / worst 3, ranked by
the extractor's own self-reconstruction MAE): `../results/corpus/extractor_best_typical_worst.jpg`.

Per-class self-recon summary:

| class | n | recon MAE mean (max) | h mean [range] | T luminance mean [range] | T_raw_p99 outliers (2σ, in-class) |
|---|---:|---:|---:|---:|---:|
| cathedral-clear | 16 | 1.71 (5.86) | 0.08 [0.06–0.15] | 0.63 [0.20–0.88] | 1 |
| dark-opaque | 8 | 2.27 (5.22) | 0.32 [0.25–0.55] | 0.11 [0.04–0.18] | 0 |
| opalescent | 19 | 6.18 (**83.13**) | 0.43 [0.06–1.00] | 0.73 [0.00–0.87] | 1 |
| wispy | 14 | 6.26 (31.74) | 0.20 [0.01–0.80] | 0.79 [0.37–0.87] | 1 |

(recon MAE in sRGB/255, so "typical" here is ~1–2/255 — very good self-reconstruction; the max
columns are the interesting part.)

**Systematic failure modes found (all visible in the best/typical/worst sheet):**

1. **Iridescent finishes get painted straight into `T`.** An Oceanside dark-opaque swatch with an
   angle-dependent rainbow coating comes out of the extractor with the rainbow bands preserved
   almost unchanged in `T` — the model has no concept of a front-surface coating whose color
   depends on viewing/lighting angle, so it treats the reflected color separation as if it were the
   glass's transmitted color. This is the direct downstream consequence of the front-lit-leaning
   photography identified in §2 for textured/iridescent shots.
2. **Degenerate absolute-scale anchor on solid, texture-free, saturated swatches.** One Wissmach
   opalescent (a smooth solid red) blew the extractor's class-anchor gain to `T_anchor_k = 880`
   (every other image in the 57-sample sat at 0.95–2.0) and collapsed `T` to all-black, `h` to a
   flat mid-gray, and self-recon MAE to **83/255** — by far the single worst result. The anchor
   (report 003/009: "brightest 1% of this class transmits about `target`") assumes the image has
   *some* near-full-transmission pixel for the percentile fit to lock onto; a uniformly dense,
   textureless swatch with no highlight has nothing for that percentile to grab, so the gain
   compensates by exploding. **This is a real, cheaply-detectable QA gate**: `T_anchor_k > ~5`
   caught this one case with zero false positives among the other 56 (max non-degenerate value was
   0.96) — worth adding as an automatic reject/flag in any batch run over this corpus, independent
   of the existing `T_raw_p99` diagnostic (which is a different signal and did *not* catch this
   failure — it flagged 3 different, less severe cases with elevated-but-not-catastrophic MAE).
3. **Streaky/marbled glass with sharp local color transitions can lose structure entirely.** The
   single worst wispy case (a green/blue marbled Wissmach swatch, MAE 31.7) came out of the
   extractor as a smooth two-tone gradient block with none of the marbling preserved — the
   illumination/chroma-field fit (designed to separate smooth backlight gradients from glass
   structure) overreached and absorbed the glass's own color structure into what it thought was
   the illumination field.
4. **Best cases are the easy, smooth, semi-transparent/milky swatches** (solid sage-green, cream,
   pale pink opalescent) with self-recon MAE down to 0.04/255 — exactly the regime the pipeline
   (edge-aware illumination envelope + milkiness-fit chroma field) was designed around. The
   difficulty gradient across this sample runs roughly: smooth milky glass (easy) < solid
   transparent color (ok) < marbled/streaky with sharp contrast, iridescent finish, and texture-free
   saturated solids (all hard, for three different reasons).

No image failed to run (0/57), but "ran without crashing" and "produced a plausible T,h" are
clearly different things here — see #2 above for a case that ran cleanly and was still wrong by a
wide margin.

## 4. VLM classifier accuracy at scale

`../corpus/run_vlm_subset.py`, `../results/corpus/vlm_confusion.json`. Images sampled from the
**high-confidence** metadata tier only (direct category match, not the Textured/Baroque guess),
stratified across manufacturer x class, classified with the real `claude`/haiku CLI subprocess
(`vlm_classify.classify_glass`, ~15 s/call, real elapsed ~505 s for the batch). This is the first
test of the classifier past the 2-photo validation quoted in its own docstring ("amber swatch -> C,
wispy sheet -> B, both correct").

**Sampling caveat, itself a finding:** the request was for 40 images stratified across
manufacturer x class among the "high"-confidence tier; only **36** came back, because
`dark-opaque` is *never* high-confidence in this census's tiering — it's only ever reached via the
"Black Opalescent"/"Opaque" name-keyword override (§1.3), which is deliberately tagged `medium`.
So this run, as scoped, **cannot test the VLM on dark-opaque at all** — a real gap, not just small
print; a follow-up would need to sample from the medium tier (or a hand-verified subset) to get
dark-opaque coverage.

**Result: 11/36 correct = 30.6% overall accuracy — barely above chance (33% for a 3-way choice,
which is what this sample actually exercised since it has zero dark-opaque examples) and far below
the "validated" 100% (2/2) the script's docstring reports.** This is the headline finding of this
task: the class-prior VLM step, at the scale tested here, is not a reliable signal on this real
photo corpus, in sharp contrast to the confidence its docstring implies from a 2-image check.

Confusion matrix (rows = metadata ground truth, columns = VLM prediction; dark-opaque row/column
all-zero for the reason above):

| gt \\ pred | opalescent | wispy | cathedral-clear | dark-opaque |
|---|---:|---:|---:|---:|
| opalescent (n=12) | 3 | 4 | 5 | 0 |
| wispy (n=12) | 2 | 5 | 5 | 0 |
| cathedral-clear (n=12) | 3 | 6 | 3 | 0 |
| dark-opaque (n=0) | 0 | 0 | 0 | 0 |

Per-class accuracy: opalescent 25.0% (3/12), wispy 41.7% (5/12), cathedral-clear 25.0% (3/12).

Two patterns stand out:
- **The VLM over-predicts `wispy`** (15/36 predictions, 42%, vs. an even 12/36/33% if unbiased) and
  under-predicts `opalescent` (8/36, 22%) — it seems to default toward "translucent with some
  streaks" as a catch-all guess when uncertain, rather than committing to either extreme
  (fully-diffusing opal or clearly-see-through cathedral).
- **This is very plausibly connected to §2's lighting finding.** The classifier prompt explicitly
  frames the image as "a photo of a stained-glass sheet held against a light source" — but §2 found
  the corpus is not uniformly backlit, and even within the "backlit-verified" manufacturers there
  are front-lit-leaning subsets. A front-lit photo of, say, a cathedral-clear swatch doesn't show
  "background clearly visible through it" the way the prompt's option (C) describes, because
  nothing is transilluminating it — so the model is being asked to pick between descriptions that
  don't cleanly apply to the photo it's shown, which is a much better explanation for nearly-random
  performance than "the model is just bad at this."

## 5. Research-use verdict

| use case | verdict | what it needs |
|---|---|---|
| **(a) DINO/linear classifier training set** | **Supports it, with the SGE/Textured-Baroque caveats.** 2,649 images (82.8%) have a class label with no image inspection at all, spread across all 4 extractor classes present in the corpus's product lines (dark-opaque is real but rare: 103 images, 3.9% of labeled corpus — expect class imbalance to matter). Needs: drop or hand-label SGE (no metadata, and §4 shows the VLM can't be trusted to fill that gap either — 30.6% accuracy, worse than not labeling at all); either drop the Textured/Baroque low-confidence tier or treat it as noisy/weak-labeled; a held-out split by manufacturer (not just by image) if the goal is generalization, since each manufacturer has a distinct visual "look" (see §2) that a classifier could shortcut on. |
| **(b) synthetic-recipe grounding statistics** | **Partially supports it.** The corpus gives a much richer real color/texture distribution than the 5 hand-authored synthetic recipes (cathedral-green, cathedral-amber, dark-opaque, streaky-mix, wispy-white) — e.g. §1 shows cathedral-clear alone spans 1,658 images across 4 manufacturers with wide hue/saturation variety the 2 cathedral recipes can't represent, and dark-opaque is a real, distinct, if rare, product line rather than a single dark-glass guess. Use it to check recipe *coverage* (do the recipes span the real hue/saturation/haze range, or clip to a narrow slice?) — this needs a follow-up pass extracting per-class color/haze histograms from the §3-style extractor output (or simpler: raw-pixel color statistics, since that doesn't need the extractor to be right) and comparing to the recipes' authored ranges. Not yet done here — flagged as the natural next task. It does **not** support grounding *T,h absolute values* against the corpus, because there's no ground truth (see (c)). |
| **(c) consistency / domain-adaptation training data** | **Does not support it, structurally.** The consistency metric (RESEARCH_STATE.md: "same seed across lightings") needs multiple photos of the *same physical glass* under different lighting. The catalog corpus is one photo per SKU (plus incidental same-SKU size-variant crops, which are typically the same photograph re-cropped, not an independent lighting condition) — there is no cross-lighting pair for any sheet in this corpus. This is the same "real photos still un-shot" gap flagged in `RESEARCH_STATE.md`'s open problems; this corpus doesn't close it. |
| **(d) pseudo-label source** | **Usable, narrowly, after the QA gates in this report — and only using the metadata class, not the VLM class, as the prior.** For the ~57-image-scale regime demonstrated in §3 (metadata class -> extractor `T,h` as a "probably OK" pseudo-label), apply: (i) the manufacturer/category triage from §2 (drop SGE, drop Youghiogheny dark-opaque, treat Textured/Baroque as needing a spot-check); (ii) the §3 QA gate `T_anchor_k > 5` as an automatic reject; (iii) still expect the iridescent-finish and sharp-marbled-texture failure modes to occasionally slip through with a *plausible-looking but wrong* `T` (no automatic gate found for these — visual spot-check recommended for any class-mismatched-looking result). §4's result means the VLM prior should **not** be trusted as a fallback for the 347 images (10.8%, mostly SGE) with no metadata class — at 30.6% accuracy it would inject more label noise than it resolves, so those images need a human label or exclusion, not a VLM guess. Pseudo-labels from this pipeline are appropriate as weak supervision/pretraining signal, not as an eval set — there is no ground truth anywhere in this corpus to score against. |

**What this corpus cannot do, stated plainly:** it cannot serve as ground truth for `T`/`h` values
(no measurement exists, only photos), it cannot supply cross-lighting or shadow/no-shadow pairs
(one photo per swatch), and roughly 1-in-10 images (SGE) can't even be assumed to depict a raw
glass swatch, let alone a backlit one.

## Reproduction

```
cd research/delighting/corpus
python3 census.py                    # writes ../results/corpus/{census,per_image_class}.json
python3 triage.py                    # writes ../results/corpus/{triage_sample.json,triage_contact_sheet.jpg}
python3 run_extractor_subset.py      # writes ../results/corpus/{extractor_stats.json,extractor_best_typical_worst.jpg}
python3 run_vlm_subset.py --n 40     # writes ../results/corpus/vlm_confusion.json (needs the `claude` CLI, ~15s/image)
```

Corpus itself (`frontend/public/assets/catalog_images/`,
`frontend/public/assets/glass_swatch_registry.json`) is gitignored on `main` and was accessed via a
local symlink into this worktree from an existing checkout — not committed, not modified.
