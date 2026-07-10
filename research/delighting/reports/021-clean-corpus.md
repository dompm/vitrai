# 021 — Canonical clean corpus, real-vs-synthetic appearance grounding, and recipe gaps

Branch `research/delighting-021`. Scripts in `../corpus/{clean_manifest,appearance_stats,
gap_exemplars,rerun_clean_stats}.py`, artifacts in `../results/corpus/`. Builds directly on
reports 015 (corpus census/triage/extractor breadth), 019 (scrape-audit/quarantine), and 017 (dark
recipe family). Takeover note: an earlier agent designed and ran the clean-manifest build and the
appearance-statistics extraction (Tasks A/B) before hitting a session limit; the lead re-ran the
clean-corpus extractor breadth test and gap-exemplar scripts (Tasks C/D) and verified all outputs
on disk; this report is the write-up over that already-computed, already-verified data — no numbers
below were re-derived.

## TL;DR

- **`results/corpus/clean_manifest.json` is now THE canonical clean corpus** — every future
  delighting experiment against the catalog corpus should load it instead of re-deriving its own
  filter. 2,853 registry-recoverable files (015) → **1,274 clean** after dropping 124
  quarantine-flagged files (019) and collapsing 1,455 hash-duplicate files across 66 cross-SKU
  photo-reuse groups (019 §5, generalized to a hash collapse over the whole pool). Bullseye 510,
  Oceanside 281, Youghiogheny 266, Wissmach 217; cathedral-clear 800, opalescent 272, wispy 163,
  dark-opaque 39.
- **015's extractor-breadth verdicts partially changed, and the causes are separable.** Re-running
  015's exact pipeline on the clean corpus (n=64, 0 failures, **0 `T_anchor_qa_flag`s** — 015's
  `T_anchor_k = 880` blowup class is categorically gone) shows real improvement, but §2 below
  decomposes *why* per class: cathedral-clear's gain is corpus-cleaning; opalescent's is mostly the
  anchor-gate work landed in reports 016/017/020 (confirmed by re-running 015's *original* 57-image
  pool through the *current* extractor — same blowup-free result on the same images); wispy's
  apparent gain is a **sampling artifact, not a fix** — the specific worst-case marbled file 015
  flagged (`wissmach-wiwo702.jpg`, self-recon MAE 31.7/255) is still sitting in the clean manifest,
  just wasn't drawn by this run's stratified sample.
- **Appearance grounding (n=1,138 backlit-verified real photos) vs the 8 authored synthetic
  recipes finds two systematic, cross-recipe gaps**, not five independent ones: (1) both cathedral
  recipes are ~2x oversaturated (authored C 50–56 vs real cathedral-clear median C 28.7), and (2)
  every recipe is 10–300x too spatially smooth (authored `hf_energy_frac` 0.0016–0.0040 vs real
  per-class medians 0.017–0.110) — traced to a **dead parameter**: `generate_noise(size, scale,
  seed, octaves=1)` declares `octaves` but the function body never reads it; every recipe's T-noise
  is a single-octave call, with no multi-frequency detail mechanism actually wired up anywhere.
- **There is no authored opalescent-class recipe at all.** All 8 existing recipes map to
  `cathedral-clear`, `dark-opaque`, or `wispy` families (`appearance_stats.py`'s own `CLASS_MAP`);
  opalescent is 21% of the clean corpus (272/1,274) and has zero synthetic representation.
- **Five gap exemplar sets** (`gap_exemplars.json` + contact sheet, hand-reviewed): cathedral-blue,
  cathedral-red, saturated-opalescent, streaky-fine-texture, dark-textured. §5 turns these into
  concrete authored L*/C*/hue/haze targets. **Caveat, found while reviewing the contact sheet**:
  2 of 3 cathedral-blue exemplars and 1 of 3 saturated-opalescent exemplars are Wissmach
  "Luminescent" or Youghiogheny "True Dichro" product lines — surface-interference/coating effects,
  not bulk transmissive glass color (the same failure mode 015 §3 and 019 flagged for iridescent
  finishes) — flagged per-exemplar below, don't grind a recipe's base color directly off those.

## 1. The canonical clean corpus

`../corpus/clean_manifest.py`. Pipeline, applied in order to 015's 2,853 registry-recoverable
files (`per_image_class.json` — exact registry match or fuzzy same-SKU size-variant recovery; SGE's
236 files never enter this pool, 015 §1):

1. drop `sge-*` by filename (belt-and-suspenders; already a no-op — 0 hits, SGE was never in the
   registry-recoverable pool to begin with)
2. drop all 019 quarantine hits, **all reason codes** including the weak/advisory
   `product_on_white` (conservative default: anything the flagger raised a hand about is out) —
   **124** files dropped
3. collapse byte-identical files by SHA-256 content hash, one canonical file per hash group
   (canonical choice prefers an `exact` registry match, tie-broken by shortest-then-lexicographic
   filename) — **1,455** duplicate files dropped, 66 of the resulting groups span more than one
   registry SKU (019 §5's "72 duplicate-image groups" finding, generalized from a hand-picked
   dedup key to a full content hash over the whole pool)

**Result: 2,853 → 1,274.** Sensitivity check baked into the script: if `product_on_white` were kept
(i.e. only the high-confidence reason codes excluded), the manifest would be 2,778 instead of
1,274 — most of step 2's exclusions are `product_on_white` hits, so this is the single most
consequential judgment call in the pipeline; the script keeps the conservative default but records
the alternative for anyone who wants to revisit it.

| manufacturer | clean n | | extractor class | clean n | | confidence | n |
|---|---:|---|---|---:|---|---|---:|
| Bullseye | 510 | | cathedral-clear | 800 | | high | 1,079 |
| Oceanside | 281 | | opalescent | 272 | | medium | 64 |
| Youghiogheny | 266 | | wispy | 163 | | low | 131 |
| Wissmach | 217 | | dark-opaque | 39 | | | |

`confidence: low` (131 files, the Textured/Baroque keyword-guess tier, 015 §1.3) is retained in the
manifest but excluded from the appearance-statistics pool in §3 — same "supports as a noisy-label
tier, don't trust for numeric grounding" verdict 015 already reached, now applied consistently
downstream instead of ad hoc per script.

## 2. 015 verdict changes: extractor breadth test on the clean corpus

`../corpus/rerun_clean_stats.py` reruns 015's exact two-stage pipeline (triage.py's lighting
heuristics → `extract.py` unmodified, same `T_anchor_k > 5` QA gate) on a fresh stratified sample
drawn from the clean manifest instead of the raw corpus. 89 images triaged, 64 pass the
backlit-verified + (not Youghiogheny-dark-opaque) filter and get run through the extractor —
**0/64 failed, 0/64 `T_anchor_qa_flag`s.**

To separate "the corpus got cleaner" from "the extractor got better since 015" (reports 016/017/020
all touched anchor calibration), a second run (`extractor_stats_original_sample_current_extractor.json`)
replays 015's *original, uncleaned* 57-image pool through the *current* `extract.py`. Same images,
different code version — isolates the extractor's own contribution:

| class | 015 original (old extractor) | same pool, current extractor | clean corpus (new pool) | read |
|---|---|---|---|---|
| cathedral-clear | n=16, MAE 1.71 (max 5.86) | n=16, MAE 1.71 (max 5.86) — **identical** | n=18, MAE **0.79** (max **2.69**) | improvement is 100% corpus-cleaning; extractor changes didn't touch this class |
| dark-opaque | n=8, MAE 2.27 (max 5.22) | n=8, MAE 2.27 (max 5.22) — **identical** | n=7, MAE 2.31 (max 5.22) | unchanged either way — dark-opaque was never contaminated or extractor-fragile |
| opalescent | n=19, MAE 6.18 (max **83.13**) | n=19, MAE 1.83 (max **10.97**) | n=22, MAE **1.30** (max **5.40**) | the 016/017/020 anchor-gate work already fixed 015's `T_anchor_k=880` blowup on the *same* images (83.13→10.97 max, no corpus change); corpus cleaning adds a further, smaller improvement on top (10.97→5.40) |
| wispy | n=14, MAE 6.26 (max 31.74) | n=14, MAE 6.26 (max 31.74) — **identical** | n=17, MAE **4.07** (max **15.81**) | **NOT a fix — a sampling artifact.** See below. |

**Wispy caveat, checked directly rather than assumed:** 015's worst wispy case
(`wissmach-wiwo702.jpg`, self-recon MAE 31.74/255, the marbled green/blue Wissmach swatch that "came
out as a smooth two-tone gradient with none of the marbling preserved") **is still in the clean
manifest** — it was neither quarantined nor hash-deduplicated away — and it simply wasn't drawn by
`rerun_clean_stats.py`'s fresh stratified sample (verified against `triage_sample_clean.json`: the
file does not appear in the 89-image draw at all). The aggregate wispy MAE improvement in the table
above is real for *this specific sample* but should not be read as "015 §3 finding #3 (streaky/
marbled texture loses structure) is resolved" — it isn't; a different draw would very plausibly
reproduce it. The other two verdict changes (cathedral-clear via cleaning, opalescent's blowup via
the extractor) are not subject to this caveat: cathedral-clear's improvement holds across the whole
class-size increase (16→18, MAE more than halved), and the opalescent blowup fix was confirmed
image-for-image on the unchanged 015 pool.

## 3. Real-vs-synthetic appearance grounding

`../corpus/appearance_stats.py`. Real: center-crop sRGB → CIE Lab (D65) → LCh on every clean-manifest
image with `confidence != low` and not Youghiogheny dark-opaque (015's front-lit tell), n=1,138.
Synthetic: the exact same math applied to each of the 8 recipes' authored linear `T` arrays from
`generate_synthetic.py`'s `create_glass_textures()`, re-derived (not rendered) for a clean
apples-to-apples comparison. `hf_energy_frac` is the outer-half-radius fraction of a radial-FFT
power spectrum on luma (DC excluded) — a spatial-texture-fineness statistic, unrelated to the
extractor's haze channel `h` despite the similar name; both are reported below, disambiguated.

**Real, per class (L*/C* as per-image medians, hue as chroma-weighted circular mean, all in p50
terms unless noted):**

| class | n | L | C | hue | hf_energy_frac (p50) |
|---|---:|---:|---:|---:|---:|
| cathedral-clear | 250 | 65.0 | 28.7 | 80° | 0.046 |
| opalescent | 250 | 63.1 | 31.8 | 88° | 0.020 |
| wispy | 158 | 56.8 | 28.5 | 64° | 0.017 |
| dark-opaque | 34 | 9.6 | 4.0 | 281° | 0.110 |

**Synthetic recipes (authored, re-derived from code):**

| recipe | family | L | C | hue | hf_energy_frac |
|---|---|---:|---:|---:|---:|
| cathedral-green | cathedral-clear | 72.2 | **50.5** | 146° | 0.0040 |
| cathedral-amber | cathedral-clear | 75.3 | **55.8** | 84° | 0.0040 |
| dark-opaque | dark-opaque | 21.2 | 3.4 | 144° | 0.0016 |
| dark-deep | dark-opaque | 3.5 | 0.3 | 290° | 0.0016 |
| dark-ruby | dark-opaque | 4.3 | 11.0 | 17° | 0.0016 |
| dark-slate | dark-opaque | 30.4 | 2.9 | 257° | 0.0016 |
| streaky-mix | wispy | 84.4 | 15.0 | 267° | 0.0016 |
| wispy-white | wispy | 89.1 | **2.1** | 275° | 0.0018 |

Reading the two tables together: cathedral's authored C (50–56) sits at roughly 1.8–2x real
cathedral-clear's median (28.7) — a real, class-wide oversaturation, not noise (real cathedral's
p5–p95 chroma range is 1.0–81.1, so 50–56 isn't even outside the real *range*, but it's well above
the *center of mass*, which matters for anything sampling recipes as representative draws).
`wispy-white` (L 89, C 2, hue 275°) is a near-neutral pale cool-white — real wispy's median is
darker (L 56.8), noticeably more saturated (C 28.5), and warm (hue 64° vs 275°, opposite side of the
wheel) — the recipe's name literally says "white" and the real class isn't. Every recipe's
`hf_energy_frac` sits at 0.0016–0.0040 regardless of class, while real values range from wispy's
0.017 (~10x higher) to dark-opaque's 0.110 (~70x higher, and individual dark-textured exemplars in
§5 go past 0.5, ~300x). The mechanism for the texture gap, found by reading the code rather than
inferring it from the numbers: `generate_noise(size, scale, seed, octaves=1)`
(`generate_synthetic.py:13`) declares an `octaves` parameter but the function body ignores it —
`np.random.rand(base_res, base_res)` at a single resolution, cubic-upsampled — and no caller ever
passes `octaves != 1`. There is no multi-frequency detail mechanism in the color/haze pipeline at
all (the relief/height channel, `generate_relief_height`, *does* blend three noise scales manually
— `0.52*fine + 0.34*mid + 0.14*broad` — so the pattern exists in the codebase, just not applied to
`T`/`h`).

## 4. Two cross-cutting authoring fixes

Both gaps in §3 are recipe-family-wide, not per-recipe, so the fix belongs at that level rather than
inside each of the five new recipes in §5:

1. **Desaturate the cathedral family toward C≈30.** `cathedral-green`/`cathedral-amber`'s authored
   `base_color` should be re-picked (same hue, lower magnitude) to land the rendered Lab chroma near
   real cathedral-clear's median (28.7) instead of the current 50/56. This is a pure re-tuning of
   two existing base-color constants, not a new mechanism — cheap, and it also directly informs
   what "not oversaturated" should look like for the two new cathedral recipes in §5.
2. **Wire up a granularity octave.** Implement the already-declared `octaves` parameter in
   `generate_noise` (or, more simply, apply `generate_relief_height`'s existing multi-scale-blend
   pattern directly to each recipe's `T`-noise term: e.g. `0.7 * generate_noise(scale=S) + 0.3 *
   generate_noise(scale=S/6)`), tuned per-class against the real hf medians in §3 (~0.02 for
   cathedral/opalescent/wispy families, ~0.11–0.3+ for dark). This is one shared code change with
   effects across all 8 existing recipes plus every new one — the highest-leverage single fix from
   this report.

## 5. Five gap recipes: authored targets from real exemplar centroids

`../corpus/gap_exemplars.py` picks each gap's target Lab point (chosen by inspecting §3's coverage
holes — cathedral's authored hues are both green/amber, nothing on the blue/red side; no recipe
combines high haze with real chroma; texture flatness is worst on wispy/streaky and dark-opaque)
and finds the 3 nearest real clean-manifest images by weighted L/C/hue distance (+class/haze
gates). Authored `base_color` below is the exact Lab→XYZ→linear-sRGB inverse of each target,
clipped to `[0,1]` (matching `generate_synthetic.py`'s own `base_color` convention); haze `h` is a
flat value chosen against the real per-class `h_mean` from §2's `extractor_stats_clean.json`, not
guessed.

| recipe | family | target Lab (L, C, hue) | authored linear `base_color` | flat haze `h` | grounding |
|---|---|---|---|---|---|
| cathedral-blue | cathedral-clear | 45, 45, 255° | `[0.0, 0.174, 0.450]` (R clips at gamut edge) | **0.09** (real cathedral avg; existing cathedral recipes use 0.02 — also under-hazed) | see caveat below |
| cathedral-red | cathedral-clear | 45, 55, 10° | `[0.503, 0.043, 0.110]` | **0.09** | oceanside-of152s.jpg (L39 C60 h20, clean) |
| saturated-opalescent | opalescent (**first opalescent recipe**) | 60, 45, 340° | `[0.602, 0.172, 0.416]` | **0.55–0.65** (real range up to 0.98; satisfies the gap's own h≥0.5 criterion) | bullseye-0003010030f1010.jpg (L53 C49 h3, clean) |
| streaky-fine-texture | wispy | 55, 40, 30° | `[0.549, 0.145, 0.125]` | **0.25–0.35** (real wispy avg 0.215, below existing wispy-family recipes' 0.5–0.95) | 3 clean exemplars, see below |
| dark-textured | dark-opaque | 15, 5, 200° | `[0.012, 0.021, 0.021]` | **0.28–0.30** (matches existing dark-opaque/dark-deep, no haze gap here — this recipe is purely about §4's texture fix) | 3 clean exemplars, see below |

**Exemplar-by-exemplar notes** (I looked at every tile on `gap_exemplars_contact_sheet.jpg`
myself):

- **cathedral-blue**: `wissmach-wi341dr.jpg` (L55 C49 h268, registry name "Medium Blue Double
  Rolled") is the trustworthy exemplar — a clean solid blue gradient, no finish keyword. The other
  two nearest neighbors, `wissmach-wf20lum105.jpg` and `wissmach-wf16lum105.jpg`, are both
  registered as "**Luminescent**" ("96 COE Midnight/Sapphire Blue Luminescent") — on the contact
  sheet both show mottled multi-hue patches (blue/purple/pink within one tile) consistent with a
  pearlescent/interference surface finish, not a uniform transmissive blue (the same "iridescent
  finish painted into T" failure mode 015 §3 and 019 both flagged). Ground the recipe primarily on
  `wi341dr`; treat the Luminescent pair as directional-hue-only, if at all.
- **cathedral-red**: `oceanside-of152s.jpg` (L39 C60 h20, clean solid red) is the best exemplar, no
  caveats. `bullseye-0011220031f1010.jpg` is a clean secondary. `bullseye-0013320050f1010.jpg`
  ("Fuchsia Transparent") has an unusually high `hf_energy_frac` (0.365) for a nominally clear/
  transparent swatch — worth a quick look before using it as a texture reference, it may be a
  specular-highlight cluster rather than real glass structure.
- **saturated-opalescent**: `bullseye-0003010030f1010.jpg` (L53 C49 h3, clean rose) is the best
  exemplar. `youghiogheny-yd5007x9.jpg` is registered as "Yellow Opal **True Dichro**" — dichroic
  coating, a thin-film interference effect, explicitly not representative of bulk milky-opal
  transmission; its `hf_energy_frac` (0.005) is also implausibly low given the dotted/mottled
  pattern visible on the contact sheet, suggesting the center-crop statistic landed on a flat
  sub-region of a genuinely structured tile — don't trust this one's numbers *or* its color.
  `wissmach-wf40lum105.jpg` is again a "Luminescent" line (same caveat as cathedral-blue). Ground
  the recipe on the Bullseye exemplar; treat the other two as excluded, not just caveated.
- **streaky-fine-texture**: all three exemplars (`bullseye-0023110030f1010.jpg` L40 C42 h12 hf0.046,
  `oceanside-of31902s.jpg` L61 C43 h71 hf0.064, `oceanside-ofr9512x12.jpg` L33 C39 h23 hf0.039) are
  plain-named products with no iridescent/dichroic/luminescent keyword, and visually read as
  genuine marbled art glass on the contact sheet — no caveats, use freely.
- **dark-textured**: all three (`oceanside-of1009s.jpg` L2 C1 hf0.369, `bullseye-0001000043f1010.jpg`
  L21 C2 hf0.502 — a clearly ribbed/reeded surface, the best single reference for "structure visible
  through near-black glass" — `wissmach-wblack.jpg` L9 C4 hf0.250) are clean, no caveats.

## 6. Honest caveats (corpus-wide, applies to all numbers above)

1. **Appearance stats measure the photos, not the glass.** §3's real-corpus numbers inherit
   whatever the manufacturer's product photography did — light-table brightness/color balance,
   vignetting, and (per §5) occasional surface-finish effects baked into the color signal. They are
   a real, useful target distribution for authoring, not a radiometric ground truth (015's own
   verdict, restated here because §3 leans on it more directly than any prior report has).
2. Iridescent/dichroic/luminescent finishes are a recurring, identifiable contamination class for
   *color statistics* specifically — 019's quarantine flagger targets *image-selection* junk
   (test-fire tiles, non-glass merchandise) and doesn't and can't catch this, since these are
   legitimate, correctly-photographed glass products; the flag has to be per-exemplar, by eye,
   against the registry name, exactly as done in §5.
3. `extractor_best_typical_worst_clean.jpg` was not generated by this iteration's rerun — the
   `out_sheet` parameter for the clean run's `run_extractor()` is accepted but unused in the
   current script, unlike 015's original `run_extractor_subset.py`. Not fixed here (out of scope);
   flagging so nobody goes looking for a file that doesn't exist.

## Reproduction

```
cd research/delighting/corpus
python3 clean_manifest.py        # writes ../results/corpus/clean_manifest.json
python3 rerun_clean_stats.py     # writes ../results/corpus/{triage_sample_clean,extractor_stats_clean}.json
python3 appearance_stats.py      # writes ../results/corpus/appearance_stats.json
python3 gap_exemplars.py         # writes ../results/corpus/gap_exemplars.json + contact sheet
```

Corpus (`frontend/public/assets/{catalog_images,glass_swatch_registry.json}`) is gitignored on
`main`, accessed read-only from an existing checkout via a local symlink into this worktree — not
committed, not modified (same convention as reports 015/019).
