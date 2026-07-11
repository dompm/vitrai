# 029 — VLM realism critique: what makes our renders not look like photos

Date: 2026-07-10. Branch `research/delighting-029` (off `research/delighting` @ `2f55cbc`).
Code: `vlm_realism_critique.py` (blind pairwise/triplet critique harness, `claude` CLI
subprocess per the `vlm_classify.py` pattern), `vlm_realism_aggregate.py`. Artifacts:
`results/vlm_realism_029/` (raw VLM outputs in `vlm_raw/`, `aggregate.json`, provenance
manifests), cited images downscaled + committed in `reports/assets_029/`. Full-size scraped
originals and render copies gitignored. No PR — reports are the deliverable.

The maintainer's ask: before scaling to 20k samples, get a systematic *critical* inventory
of what makes the render_022 synthetic photos NOT look like real glass photos — separating
gaps we already know about (MMv3, gallery-reviewer notes) from ones we don't.

## 0. TL;DR

- **23 VLM critique calls** (sonnet, ~1–2 min each) over three sets: 10 render_022 samples
  ("ours"), 11 clean-manifest catalog swatches ("corpus"), 12 in-the-wild photos of real
  glass under real capture conditions ("wild"). Same blind prompt for diagnostic pairs and
  real-vs-real calibration controls, so the false-positive rate is measured with the same
  instrument.
- **Ours was flagged as the synthetic image in 16/16 diagnostic comparisons** (12 pairs + 4
  triplets) — but see §4's honest notes: file paths leaked set identity to the model, so the
  *verdict accuracy* number is soft. The *observations* are the deliverable, and the
  strongest ones were spot-verified by eye (§3).
- **Calibration: 3/7 real-vs-real controls false-positived (43%)** — always in the same
  direction: the flatter, cleaner, studio-style CATALOG image got called synthetic, citing
  "no grain / flat light / too clean". No wild photo was ever called synthetic. Lesson: (a)
  "too clean" cues are weak evidence against catalog-style targets, and MUST be discounted;
  (b) the catalog corpus itself sits partway between our renders and wild photos on the
  realism axis — training/critiquing against catalog images alone will not teach wild-capture
  realism.
- **Ranked gap list (§2): the two most frequent tells are (1) procedural texture spatial
  statistics (15/16 calls) and (2) the missing/wrong camera-optics layer (13/16)** — the
  first is a NEW dimension beyond 022's hf-energy fix (which put texture *amplitude* in the
  real band; the VLM reads *spatial structure*: constant wavelength, isotropy, no
  roll-direction anisotropy, no discrete seeds/bubbles). The single most actionable NEW
  finding is **layer decoupling** (10/16): color gradients, vignettes, and hotspots sit ON
  TOP of the relief instead of being modulated by it — the VLM independently recovered, from
  pixels alone, the construction fact that the generator authors `T`, `height`, and lighting
  as statistically independent fields.
- **Most damning single image: our saturated-opalescent render carries a razor-sharp
  horizontal seam** (verified by eye, `reports/assets_029/ours_saturated-opalescent.jpg`) —
  almost certainly the HDRI horizon transmitted *sharply* through supposedly milky opal
  glass. That is MMv3-G1's roughness-only haze failing to scatter away a hard background
  boundary, visible to a critic in one glance.

## 1. Setup

### Comparison sets

- **A. Ours** — 10 recipes x 1 sample from `render_022/` (`without_shadow_photo.png`,
  found read-only in the 022 worktree, repo convention), downscaled to 900px JPEG:
  cathedral-{amber,blue,red}, dark-{opaque,ruby,textured}, streaky-{mix,fine-texture},
  wispy-white, saturated-opalescent.
- **B. Corpus** — 11 high-confidence swatches drawn from THE canonical
  `results/corpus/clean_manifest.json` (021/024), stratified across classes (4
  cathedral-clear, 3 opalescent, 2 wispy, 2 dark-opaque), catalog images symlinked
  read-only per the 015 convention. Picks + provenance in
  `results/vlm_realism_029/corpus_picks.json`.
- **C. Wild** — 12 photos of real stained glass under real capture conditions (room
  reflections, mixed lighting, shelves, backlit windows, macro sheet crops), scraped
  politely (normal UA, 1.5s spacing, 12 files) from a stained-glass community blog
  (everythingstainedglass.com — community-submitted photos; Etsy/Delphi listing pages
  403 non-browser fetchers, not retried aggressively). Source URLs in
  `results/vlm_realism_029/wild_manifest.json`; full-size originals gitignored, only
  downscaled cited copies committed.

### The critique instrument

One prompt template (2-image and 3-image variants, `vlm_realism_critique.py`): it (a)
names the KNOWN nuisance differences and orders the model to set them aside (background
content, sheet size/labels/hands, angle/crop/resolution, glass color), and (b) asks for
concrete falsifiable observations in six categories — front-surface specularity, texture
statistics, color-depth/translucency gradients, edge/rim effects, lighting plausibility,
noise/camera optics — each tied to a specific image and specific visual evidence, then a
verdict with an explicit "both real / uncertain" escape hatch. **The same prompt runs on
diagnostic pairs (ours-vs-real) and on real-vs-real controls**, unlabeled, so control
false-positives are measured with the identical instrument.

23 calls: 7 ours-vs-corpus, 5 ours-vs-wild, 4 triplets (ours-vs-corpus-vs-wild), 2
corpus-vs-wild (cross-source real-real), 5 same-source real-real controls.

## 2. The ranked gap list

Frequency = how many of the 16 diagnostic calls raised the theme against our render.
"Control FPs" = whether the same cue class was also (wrongly) cited against a real image
in the 7 controls — cues that fire on real catalog photos are weaker evidence.

| # | Gap | Freq | Known/NEW | Control FPs | Read |
|---|-----|-----:|-----------|-------------|------|
| G-1 | **Texture spatial statistics read procedural**: near-constant wavelength/amplitude ("tiled lattice", "single-frequency noise field"), isotropic blobs with no roll-direction anisotropy, ONE visible scale (single blurred octave), zero discrete micro-events (seeds/bubbles/pits) | 15/16 | **Partially known → mostly NEW.** 022 fixed hf *energy* (amplitude now in the real p5–p95 band); the VLM reads *structure*: periodicity, isotropy, missing event layer. New dimension, not a re-finding. | 1 (cal01 called real bubbles "stamped") | The single most consistent tell. Notably, **bubble/seed optics were the VLM's favorite authenticity cue for real images** (bright-core/dark-rim "donut" shading, irregular clustering — cited in 8 calls); we have no event layer at all. |
| G-2 | **Camera-optics layer absent or wrong**: no sensor grain, no chromatic aberration at high-contrast edges, no focus/DoF falloff, uniform frame-wide softness; where noise IS visible (streaky-mix, t04) it is *signal-independent* — uniform speckle that doesn't shrink in blown highlights (Cycles Monte-Carlo residual, not photon shot noise) | 13/16 | **NEW** as a named, systematic gap (never in MMv3/gallery notes) | **3 (all three control FPs cite it)** | Strong tell vs wild photos, weak vs catalog swatches (real catalog images are denoised/retouched and fire the same cue). t04's signal-independence observation is the sharpest version: real shot noise scales with signal; ours doesn't. |
| G-3 | **Layer decoupling — color/lighting ride on top of relief instead of being modulated by it**: "a normal-map ripple over a flat color ramp" (c03), "blobs keep constant contrast as the whole field darkens, as if a separate vignette were multiplied over a texture" (c07), "the color transition ignores the underlying ripple relief" (w01), "backlight through a streaky sheet should warp/break the hotspot; here the gradient is mathematically clean under the noise" (t04) | 10/16 | **NEW** — and it is literally TRUE by construction: the generator authors `T` and `height` as independent noise draws, and the render's brightness falloff is an independent third factor. The VLM recovered our architecture from pixels. | 1 (x01, against a flat catalog swatch) | The most *actionable* new finding: real glass couples color density to local thickness (Beer–Lambert) and couples the transmitted hotspot to the relief. |
| G-4 | **No front-surface reflection/specularity anywhere**: zero glints, no environment veil, no highlight tracking the relief | 9/16 | **KNOWN** — MMv3 G2, `Specular IOR Level = 0.0` by construction; maintainer-named | 1 (x02, "structureless highlight" on a catalog swatch) | The VLM confirms it as a top-frequency tell and repeatedly used real-image specular behavior (per-bump glint lines on ribbed dark glass, reflected house imagery) as its authenticity anchor. |
| G-5 | **Lighting monotony + one bug-level artifact**: radially symmetric near-Gaussian hotspot (3 calls), symmetric 4-corner vignette (w02), perfectly flat field (w03/t01), single top-to-bottom gradient (w05) — plus the **hard horizontal seam in saturated-opalescent** (c05, verified by eye) | 9/16 | Monotony **KNOWN** (single HDRI, fixed camera — gallery-reviewer notes). The seam is **NEW**, and mechanistically it is MMv3-G1: a sharp HDRI horizon transmitted through high-`h` opal glass that roughness-only haze fails to blur away — physically impossible for real milky opal. | 0 for the seam-class artifact | The seam is the most damning single-image evidence in the study (§3). |
| G-6 | **Mark rendering artifacts**: grease-pencil strokes are razor-sharp/stair-stepped-aliased *inside* an otherwise uniformly soft render ("blocky stepped pixel edges … a rendered/vector line composited onto the texture", w03; same in c02/w01/w02/t02/t03) | 7/16 | **NEW** (mark *placement* realism was 002/012 work; mark *rendering* consistency was never scored) | 0 | Maintainer note folded in mid-flight: real sheet markings can also be **WHITE paint-pen on dark glass** — the generator only draws dark strokes, and the extractor's mark detector inherits the same dark-only assumption (chroma-anomaly inpainting). Already queued as a generator+detector fix. |

Secondary observations that support known gaps: the wild set's waterglass pair
(`wild_sheets_waterglass_pair.jpg`) shows a *house imaged through the ripple, warped* —
the VLM cited this refracted-background behavior as authenticity evidence in 3 calls
(x01/t01/w01). That is MMv3-G3 (refractive background lensing), already ranked; the wild
photos make its absence in our renders vivid. Edge/rim effects (MMv3 doesn't name them):
real cut edges show a thickness-darkened rim with color fringe (c05/t03/x01 cited them
FOR real images); our renders are full-bleed crops with no sheet edge visible, so this is
a framing-coverage question rather than a shader gap — worth one edge-visible variant per
recipe at scaling time.

## 3. Verified-by-eye spot checks (not trusting the VLM's word)

- **The c05 seam is real**: `ours_saturated-opalescent.jpg` has a razor-sharp horizontal
  brightness/color discontinuity ~70% down the frame, running edge to edge. Given the
  scene (sheet against the sunflowers HDRI), this is the sky/field horizon transmitted
  through glass authored as milky opal. Diagnosis: `h` drives Principled *Roughness*, and
  rough transmission at 700px render scale does not produce anywhere near the scatter a
  real opal sheet has — the exact G1 σ_s/a_glow split MMv3 proposes. One-glance fail.
- **Mark aliasing is real**: the same image's mark (and dark-textured's) shows hard
  stair-stepped edges while everything around it is soft — the grease-pencil overlay does
  not participate in the render's optics.
- **Texture periodicity is real but subtler than the VLM claims**: cathedral-amber's
  ripple (ours_cathedral-amber.jpg) does read as same-scale cellular undulation everywhere;
  "tiles with unnatural periodicity" is an overstatement (it is jittered value noise, not
  a repeating tile), but "no scale mixing, no directional grain, no events" is accurate.
- **Calibration FPs are understandable by eye**: the Bullseye medium-amber swatch
  (corpus_bullseye-0011370050f1010.jpg) that cal01 called synthetic genuinely is a
  noise-free flat yellow field with soft-ringed bubbles — a heavily-produced catalog
  photo. The instrument isn't hallucinating; the catalog style really does share several
  "synthetic" cues.

## 4. Calibration result + honest notes

**Controls: 7 real-vs-real calls → 3 correct "both appear real" (cal02, cal04, cal05),
1 "uncertain" (cal03, leaned toward a macro crop being synthetic but explicitly declined
to call it), 3 false positives (cal01, x01, x02) = 43% FP rate.** Structure of the FPs:

- All three FPs called the **catalog-style** image synthetic (twice vs a wild photo, once
  vs a richer catalog photo), citing no-grain/flat-light/too-clean cues.
- No wild photo was ever called synthetic; no FP invoked the seam-class or
  mark-aliasing-class artifacts.
- Per-cue: the "too clean" optics cue fired in 3/3 FPs (heavily discounted in §2's
  ranking); a texture-uniformity claim fired in 1 FP; a decoupling-style claim in 1.

Reading: **the instrument cannot reliably distinguish a real STUDIO catalog photo from a
synthetic render — but it never mistook an in-the-wild photo for one.** Two consequences.
(1) Gap themes were ranked above by cross-referencing against control behavior, not raw
frequency alone. (2) For the learned track: the catalog corpus is itself
"synthetic-adjacent" in capture statistics — models validated only against catalog
swatches will not have seen wild-capture physics (reflections, grain, mixed light).

Honest notes:

1. **Path leak.** The prompt hands the model file paths, which include `ours/` and recipe
   names; one verdict (t02) literally echoes "dark-ruby". So 16/16 diagnostic accuracy is
   NOT a clean blind-detection statistic. Mitigating evidence that it wasn't mere
   path-following: 3 controls called `corpus/`-pathed images synthetic, and cal01's FP
   picked the image *first* in path order. Future runs should copy inputs to neutral
   hashed filenames. The report's deliverable — the observation inventory — is unaffected:
   observations are concrete, category-tagged, and the strongest were verified by eye (§3).
2. **The critic model (sonnet) is not a physics oracle.** Some observations overstate
   (e.g. "tiled" periodicity, §3); several no-CA/no-grain claims are true of real catalog
   photos too. Everything promoted to §2 either recurred across many independent pairs,
   matched a known construction fact of the generator, or was verified by eye.
3. **One sample per recipe.** Each recipe was critiqued in 1–3 comparisons of ONE seed x
   ONE lighting; the frequency column measures cross-recipe recurrence, not per-recipe
   variance. Fine for a gap inventory, not for per-recipe scoring.
4. **Wild set is blog-sourced, not listing-sourced.** Etsy/Delphi block non-browser
   fetchers (403); the community-blog photos cover the same capture regime the maintainer
   wanted (hands/tape appear in some, room reflections, mixed lighting, phone optics).
   Politeness kept volume at 12 files, one pass, normal UA, 1.5s spacing.
5. **Call budget: exactly 23 calls ≈ 35 min wall time** (the harness-validation run WAS
   cal01, cached and reused) — inside the ~20–30 economy target.

## 5. Prioritized generator to-do (pre-scaling)

In descending leverage-per-effort, mapped to MMv3 where the item was already planned:

1. **Turn on the front-surface reflection veil** (MMv3 G2; `Specular IOR Level` + a front
   IBL). Known, small, and the VLM confirms it as a top-frequency tell — 9/16 diagnostics
   cite the *total absence* of any glint, and real-image specular behavior was the model's
   main authenticity anchor. Unchanged priority; now with quantified evidence.
2. **Couple color to thickness (kill the layer decoupling)** — NEW, small: derive the T
   modulation from the SAME authored height field via a Beer–Lambert-style exponent
   (T = base^(thickness/t₀)) instead of an independent noise draw, so crests read lighter
   *and* less saturated together, and the transmitted hotspot picks up relief modulation.
   This addresses the second-most-recurrent NEW theme (10/16) with a texture-authoring
   change only — no shader/renderer work, GT stays by-construction.
3. **Texture spatial statistics** — NEW, medium: (a) add a discrete event layer (seeds/
   bubbles with bright-core/dark-rim shading — the VLM's #1 authenticity cue for real
   sheets, entirely absent from all 13 recipes); (b) add an anisotropic roll-direction
   streak component (real rolled glass is directional; all our noise is isotropic);
   (c) domain-warp/jitter the value-noise lattice to break constant-wavelength reading.
   Ground each against the corpus per-class stats the 021/022 way before shipping.
4. **Fix the opal scatter (MMv3 G1, σ_s/a_glow split) — now with a smoking gun**: the
   saturated-opalescent seam proves roughness-only haze cannot hide a sharp background
   boundary behind milky glass. Interim cheap check while G1 lands: verify high-`h`
   recipes against HDRIs with hard horizon edges, or raise roughness/IOR blur until the
   horizon is gone.
5. **Camera pipeline augmentation (photo only, never GT)** — NEW, small: signal-dependent
   shot grain, mild chromatic aberration at high-contrast edges, slight exposure roll-off,
   optional defocus falloff; and control the Cycles residual (denoise or higher samples)
   so the only noise present is the *intended*, signal-dependent kind (t04 caught the
   difference). Main payoff is sim-to-real for the learned track; keep it a toggleable
   post-process so purity runs stay byte-comparable.
6. **Marks** — NEW, small: render strokes into the texture at authoring resolution
   (anti-aliased, participating in the same optics as the glass), and add the
   maintainer-queued **white paint-pen variant on dark glass** to both the generator and
   the mark-detector assumptions (the chroma-anomaly detector currently assumes dark
   marks).
7. **Lighting variety** (KNOWN — gallery notes): more HDRIs/rotations/exposures than the
   single sunflowers env; consider one edge-visible framing variant per recipe (the
   edge/rim cue in §2-secondary).

Items 1, 2, 5, 6 are individually small and independently landable (one change at a time,
each re-validated by the 006-floor gate + a re-run of this critique instrument on the
changed recipes — the harness is reusable as a regression test with ~6 calls).

## Reproduction

```
cd research/delighting
# comparison sets: render_022 copies + corpus picks + wild scrape (manifests committed)
#   results/vlm_realism_029/{corpus_picks,wild_manifest}.json document exact inputs
# the VLM pass (23 calls, ~1-2 min each, requires `claude` CLI):
python3 vlm_realism_critique.py            # all calls, cached per-call in vlm_raw/
python3 vlm_realism_aggregate.py           # verdict table + full observation dump
```
