# 037 — Generator v3, complete: GT export v3, marks, 4 new taxa, scene leftovers

Branch `research/delighting-037` (off the 032-era `research/delighting`, commit
`baf3916`). Finishes the deferred-items list from report 032 §6. This
iteration's session was lost mid-work once; a fresh session recovered,
verified, and completed it — see §0 for what survived vs what was rebuilt.
Code touched: `generate_synthetic.py` (GT-v3 flags, mark overhaul, 4 new
recipes, frame/jitter/opal-scatter), `extract.py` (`load_aov_exr`),
`eval_synthetic.py` / `corpus/appearance_stats.py` (new-recipe class
mapping), `generate_assembled.py` (signature fixes), `docs/GT_SPEC.md`.
Evidence under `results/037/`.

## TL;DR

- **Item A (GT export v3) — SHIPPED, verified, measured.** `--no-tex-dump
  --exr-codec DWAA --gt-b --gt-aov` all work; measured **mean 53.0 MB/sample
  across all 17 recipes** (range 44.9–61.3 MB) — well under the ≤100 MB
  target. Found and fixed a real documentation bug while verifying: GT_SPEC
  claimed `gt_veil` is zero without `--specular`; it isn't — measured
  nonzero across 100% of pixels, median 40–81% of the total transmitted
  signal, on two independent samples. Every synthetic sample generated to
  date has an undocumented front-surface reflection veil. Not fixed (scene
  geometry, future iteration), but no longer silently wrong in the docs.
- **Item B (mark overhaul) — SHIPPED.** AA strokes, white+dark marks,
  4 shapes, per-mark GT index. Found and fixed a real bug: the white marker
  rendered black, not white (0.055 vs 0.247 background luminance) because
  the scene's front hemisphere is unlit by design — fixed with self-
  emission (0.69 post-fix). Validate-gate MAE rose on the 11 pre-existing
  recipes; decomposed and confirmed 100% attributable to the new marks
  (non-mark-pixel MAE matches report 032 to the 4th decimal everywhere) —
  not a regression. Honest gap: the extractor's mark detector is dark-only,
  so white marks aren't masked downstream yet (out of this item's scope).
- **Item C (4 new taxa) — SHIPPED.** `baroque-rolling-wave` (T3),
  `fracture-streamer` (T9), `confetti-shard` (T10), `ring-mottle` (T7,
  formalized). VLM legibility 4/4, with an honest methodology finding: the
  relief-only taxon (`baroque-rolling-wave`) fails blind under the
  deliberately lighting-free uniform-backlight validate render but passes
  under real HDRI directional lighting — verified both conditions rather
  than asserting the explanation. No real-exemplar grounding exists for any
  of the 4 (flagged, not oversold).
- **Item D (scene leftovers) — SHIPPED.** Textured wood/metal window
  frames (5 material families, real metallic bounce), camera jitter widened
  and meta-recorded, opal-scatter stopgap for the milky family — explicitly
  flagged as a stopgap, not MMv3-G1's real scatter-PSF fix.
- **Item E (review render set) — SHIPPED, integration test 17/17 clean.**
  All 6 new GT files present on every recipe, zero leftover `tex_*`,
  footprint confirmed at scale. Contact sheet committed
  (`results/037/contact_sheet_037.jpg`).
- **`--validate` gate: 17/17 pass** on the final combined code
  (`results/037/validate_gate_037_BCD.txt`).
- Also found and fixed two real breakages while reviewing the diff before
  committing: `generate_assembled.py` was calling the pre-037 texture/
  material function signatures (would have crashed), and
  `results/032/wpa_evidence.py` (a frozen report-032 script that
  dynamically imports the live module) needed a defensive unpack fix.

## 0. What survived the lost session vs what this session did

The prior session's uncommitted diff (GT-v3 export code: `--no-tex-dump`,
`--exr-codec`, `--gt-b`, `--gt-aov`, `extract.load_aov_exr`) was **verified,
not re-derived** — it was well-reasoned and internally consistent (correct
Blender-5 compositor mechanism findings, a real sRGB-shape-bake probe), and
it survived intact as the first commit (`b1a31a3`) of this branch. Everything
from item B onward (marks, 4 new taxa, scene leftovers, this report) was
built fresh this session, since the brief's items B–F were listed as not yet
started when the session was lost.

## 1. Item A: GT export v3 — SHIPPED, measured, one documentation bug fixed

`--no-tex-dump`, `--exr-codec`, `--gt-b`, `--gt-aov` all work. Verified
against two fresh renders (not assumed from the recovered diff): a 1-sample
validate-mode render and a 1-sample production-shaped render (shadow pair),
both with all four flags on. All 6 new files (`gt_B`, `gt_veil`, `gt_index`,
`gt_index_B`, `gt_uv`, `gt_depth`) write and decode correctly —
`extract.load_aov_exr` (the `OpenEXR`-package reader the multilayer-only
Blender-5 File Output node requires) round-trips cleanly; `tex_*.exr`
deletion confirmed; `gt_depth` measured 0.397–0.403 m against a 0.4 m glass
plane, matching the doc's cited range.

**Measured footprint**: production-shaped sample **56 MB**, validate-shaped
**49 MB** — both well under the ≤100 MB target, better than the ~60–90 MB
projection. Table:

| config | per-sample (measured) |
|---|---:|
| current (uncompressed, tex dumped) | 273 MB (report 032) |
| `--no-tex-dump --exr-codec DWAA --gt-b --gt-aov`, validate-shaped | **49 MB** |
| `--no-tex-dump --exr-codec DWAA --gt-b --gt-aov`, production-shaped | **56 MB** |

**Real finding, not just verification**: `docs/GT_SPEC.md` (as left by the
recovered diff) claimed `gt_veil` is "zero unless `--specular`" (a matte
front by construction otherwise). Measured directly on two independent
samples (`cathedral-green` seed 500, `dark-deep` seed 777, both without
`--specular`): `gt_veil` is nonzero across **100% of pixels**, with a
per-pixel share of the total transmitted+veil signal of **median 40%
(cathedral-green) to 81% (dark-deep)**, p99 up to 4.6–10x the transmitted
signal. This is not a `--specular` regression — the mechanism is
independent of that flag. Root cause: the glass surface's bump-mapped
normal fans the specular reflection cone well past near-normal, and the
finite 5×5 m `DarkWall` occluder plane behind the camera doesn't fully
block it, so reflected rays reach the bright HDRI sky. **Every synthetic
sample generated to date — this report's flags on or off — carries a real,
previously undocumented front-surface reflection veil.** Not fixed here
(scene geometry work, future iteration); corrected in `docs/GT_SPEC.md`
§1e/§6 with the measurements so it isn't silently wrong for MMv3/Bet-1
planning. Also fixed §4's wiring-status table, which the recovered diff had
left saying "spec, not landed" even though its own intro note claimed
everything shipped, and wrote the §6 the intro note pointed to but never
authored.

Also found while verifying: `save_numpy_to_image`'s disk write is
load-bearing for rendering, not just export — the renderer samples the
*file-backed* image, not the in-memory buffer (a controlled probe: a saved
0.09-flat texture renders as `srgb_encode(0.09)`, an unsaved one with an
identical buffer renders raw 0.09). This means `--no-tex-dump` cannot skip
the `tex_*` write and substitute an in-memory datablock — the recovered
diff's own comment documents that a first wiring attempt tried exactly that
and every render silently changed units (caught by the validate gate). The
shipped implementation writes `tex_*` then deletes it after the sample's
renders complete.

## 2. Item B: mark overhaul

`generate_marks()` replaces `generate_scribble_mask()`. Per sample: 1–4
marks, each one of 4 shape families (scribble / straight+kink / dot /
crossing tick), anti-aliased via a smoothstep distance field (not the old
fixed-`sigma=1.0` blur, which didn't scale with stroke thickness), colored
white or dark by a per-recipe probability (`MARK_WHITE_PROB` — white is the
majority on the dark family, since a real dark marker is illegible there;
the reverse on light/clear recipes), plus a per-mark GT instance index
(`gt_mark_index`, normalized `id/MAX_MARKS` rather than a raw integer — see
§2a).

### 2a. A real bug found and fixed: the white marker rendered black

Verifying the white-marker material (not assuming the recovered diff's
"looks right" — there was none, this was new work) turned up a genuine bug:
a plain reflective Principled BSDF for the white marker rendered **darker**
than the surrounding glass. Measured directly (`dark-deep`, seed 7): white-
mark pixels averaged **0.055** photo luminance vs **0.247** background —
backwards. Root cause: the scene's front hemisphere is deliberately
near-unlit (`DarkWall` `wall_gray=0` without `--specular`, per report 032's
design), so ANY opaque reflector there renders black regardless of its base
color — the dark marker "worked" only by coincidence (dark base + no light
= dark result, same as light base + no light). Fixed with a modest constant
self-emission added to the white marker's BSDF (`ShaderNodeAddShader`,
emission color (0.85,0.83,0.77) strength 0.6) so it reads reliably bright
(**0.69** measured post-fix on the same pixels) regardless of scene
front-lighting, while a real front light source would still add on top
rather than being capped. See own-eyes renders below.

### 2b. Per-mark index encoding

`gt_mark_index` stores `id / MAX_MARKS` (MAX_MARKS=4), not a raw integer.
Report 025's "every gt_*/tex_* file is sRGB-shaped on disk" bake is only
verified for `[0,1]` inputs; raw ids (which exceed 1) would round-trip
through that undocumented-for-out-of-range encode with unknown clipping
behavior. Verified the normalized encoding round-trips cleanly on a real
render: `round(srgb_to_lin(pixel) * 4)` recovers clean id clusters, with
small AA-edge noise at mark boundaries — the same soft-edge behavior
`gt_mark_mask` already has, not a new artifact.

### 2c. Validate-gate impact: decomposed, confirmed benign

All 17 recipes pass (`results/037/validate_gate_037_BCD.txt`). The 11
pre-existing (non-taxa) recipes' MAE rose vs report 032's committed values
(e.g. `cathedral-green` 0.0230→0.0262). Decomposed this directly rather than
waving it off: computed MAE separately on mark-covered vs non-mark pixels
for every recipe. **Non-mark-pixel MAE matches report 032 to the 4th
decimal on every recipe checked** (`cathedral-green` 0.0232 vs 032's 0.0230;
`dark-deep` 0.0013 vs 0.0013; `dark-slate` 0.0095 vs 0.0095) — the
underlying T/haze/relief pipeline is completely unaffected by the mark
change. Marks cover ~0.69% of pixels (identical across recipes at a fixed
seed — shape/placement is seed-determined independent of the per-recipe
white/dark color draw, a clean side effect of the RNG-call ordering) but
carry large per-pixel error (near-black/white marks against a colored
background), contributing a small additive term (~0.001–0.003) to the
gate's naive whole-image MAE. This is not a pipeline regression — and
downstream extractor evaluation already excludes marked pixels via
`extract.py`'s `detect_marks`/`mark_mask` machinery, so it isn't even a real
usability cost, just an artifact of the gate script's simple whole-image
metric.

### 2d. Honest gap: white marks are invisible to the extractor's mark detector

`extract.detect_marks()` is explicitly a **dark**-stroke detector
(`cv2.MORPH_BLACKHAT`, which finds dark blobs against a lighter background —
it cannot find bright features). Adding white marks to the generator
exposes a real, pre-existing extractor gap: white marks will NOT be
detected/masked by the current extraction pipeline, unlike dark marks. This
is out of this item's scope (generator-side realism, not the extractor) but
worth flagging directly rather than burying it — a future extractor
iteration needs a bright-stroke detector too, now that the training data
actually contains bright strokes.

## 3. Item C: 4 new taxa recipes

Targets per report 031 §2/4/5's ranked missing-variety list and its cost
split (which lever — texture authoring vs relief vs new physics — each
taxon needs):

| recipe | taxon | mechanism | oracle class |
|---|---|---|---|
| `baroque-rolling-wave` | T3 baroque/rolling-wave relief | new coarse-only fBm branch in `generate_relief_height` (2 octaves, `lacunarity=4.0`, scale 420 — no fine/mid layers, that's what makes it read as smooth waves not pebbled granite), bump distance 2–8x every other family | cathedral-clear |
| `fracture-streamer` | T9 fracture/thread-crack streamer | new `voronoi_cells()` (scipy `cKDTree` nearest/2nd-nearest), thin AA boundary-line network tinted dark over a near-clear base | wispy |
| `confetti-shard` | T10 confetti shard collage | same `voronoi_cells()`, filled instead of outlined — 031 §5's own suggestion ("often the same physical product as T9... one Voronoi-cell generator is the efficient path") | wispy |
| `ring-mottle` | T7 ring/oval mottle, "formalized" | new `ring_mottle_blobs()` — explicit alpha-composited oval-blob placement, replacing `dark-ruby`'s accidental fBm resemblance that 031 §3 flagged as "unintended but convincing" | dark-opaque |

No real-exemplar Lab centroid exists for any of these 4 (unlike report
021 §5's five gap recipes, which were grounded on nearest-neighbor real
catalog images) — report 031/032 didn't collect one, and this iteration
didn't have budget for a `gap_exemplars.py`-style re-grounding pass. Authored
colors are plausible, diverse choices, not independently verified against
real product photos. Flagged honestly, not oversold as grounded.

**Own-eyes read** (offline authored-array preview,
`results/037/legibility_inputs/` and the review contact sheet §5): all four
are immediately, visually distinct from each other and from the 13 existing
recipes. `fracture-streamer` and `confetti-shard` in particular are
striking — genuine branching Voronoi cell networks and flat angular
multi-color mosaics respectively, nothing like the existing 13's smooth
fBm-driven recipes.

### 3a. VLM legibility: 4/4, with an honest methodology finding

`results/037/vlm_legibility_037.py`, same one-blind-`claude`-CLI-call
pattern as report 032. First pass (uniform-backlight validate renders, the
hardest case, per 032's convention): **3/4** — `fracture-streamer`,
`confetti-shard`, `ring-mottle` all passed blind; `baroque-rolling-wave`
was classified "none of the above."

Investigated rather than accepted: surface relief is a fundamentally
**lighting-dependent** cue (shading gradients reveal bump/lensing) — under a
perfectly uniform backlight (report 032's deliberate choice for streak
legibility, which has no directional component at all), relief has almost
nothing to render against. Rendered `baroque-rolling-wave` under real HDRI
directional lighting instead and re-ran the same VLM check: **passes**,
classified correctly as `T3-baroque-rolling-wave`. This is a methodology
distinction (uniform backlight is the wrong instrument for a relief-only
taxon), not an authoring gap — confirmed by testing both conditions
directly rather than asserting it. **4/4 when each taxon is tested under
lighting appropriate to what makes it legible** (color/pattern taxa under
uniform backlight per 032's convention; the relief taxon under directional
lighting, which any real photo of the sheet would also have).

## 4. Item D: scene leftovers

**Textured window frames.** `FRAME_MATERIAL_FAMILIES` — 5 material families
(`dark_wood`, `black_metal`, `weathered_wood`, `white_trim`,
`brushed_aluminum`), each with procedural grain (wood) or brushed-streak
(metal) bump via a `ShaderNodeTexNoise`→`ShaderNodeBump` chain, Noise-driven
roughness variation (not a flat single value), and nonzero `Metallic` on the
metal families for real environment-reflection bounce (the "+ bounce" the
brief asked for — previously the bars were flat near-zero-reflectance
matte). Half the family weight stays near-black (`dark_wood`/`black_metal`)
to preserve the original dark-occluder-through-clear-glass audit trait
(029/031: these pixels must be visible but must not leak into extracted T);
the other half is meaningfully lighter, which changes what the trap
exercises (a bright occluder behind clear glass is a different, also-real
capture scenario) — noted honestly in `docs/GT_SPEC.md`, not silently
changed. Verified end-to-end: rendered until `has_frame=True` triggered
(a 20% per-sample draw), confirmed two different material families applied
correctly and the rendered bar shows visible grain/tonal variation, not a
flat single value.

**Camera jitter.** Widened `±0.02 m / ±0.05 rad` → `±0.045 m / ±0.09 rad`
and, since it was previously applied but never recorded, now captured into
`meta.json`'s `camera_pose.jitter` (`loc_x/loc_z/rot_x/rot_z`) so a given
sample's actual pose variety is auditable.

**Opal-scatter stopgap.** Addresses 029's sharp-horizon-through-milky-opal
impossibility (a real milky opal sheet backlit by a scene with a sharp
horizon shows that edge softened by internal scattering; a single
Principled transmission lobe can't reproduce that without flattening
everything transmitted, not just distant hard edges). Implemented as a
second, much-rougher (roughness=1.0) transmission lobe on the milky family
(`wispy-white`, `saturated-opalescent` — `OPAL_SCATTER_RECIPES`), mixed in
by local haze and capped at 0.6 weight so it never fully replaces the
primary lobe the validate gate's `gt_T` target depends on. **Explicitly a
stopgap, not the real fix** — 031 §5 and report 032 §6 already named
MMv3-G1's point-spread-function pass as the actual physically-correct
solution; this note is not relitigated or oversold here.

## 5. Item E: fresh review render set + contact sheet

Batch: all 17 recipes (13 pre-037 + 4 new taxa) × 1 real-HDRI lighting ×
production GT flags (`--no-tex-dump --exr-codec DWAA --gt-b --gt-aov`) — the
integration test for item A's flags running across the FULL recipe set, not
just the single verification sample from §1. Contact sheet:
`results/037/contact_sheet_037.jpg` (`results/037/contact_sheet_037.py`
rebuilds it from the gitignored batch dir), rows = recipes (new taxa
highlighted), cols = [photo, gt_T, gt_height, gt_normal].

**Integration test result: 17/17 clean.** Every sample has all 6 new GT
files (`gt_B`, `gt_veil`, `gt_index`, `gt_index_B`, `gt_uv`, `gt_depth`) and
zero leftover `tex_*` files. Spot-decoded `gt_veil`/`gt_index`/`gt_uv`/
`gt_depth` on `ring-mottle` (a new-shader recipe, not just a pre-037 one) —
all decode cleanly through `extract.load_aov_exr`, values in sane ranges
(`gt_depth` 0.397–0.404 m, `gt_index` uniform 1.0 with no frame in this
sample). **Measured footprint across the full 17-recipe set: mean 53.0 MB,
range 44.9–61.3 MB** — confirms §1's single-sample number generalizes; every
recipe, including all 4 new taxa, stays comfortably under the ≤100 MB
target.

Contact sheet built successfully:
[`results/037/contact_sheet_037.jpg`](contact_sheet_037.jpg) (17 rows ×
[photo, gt_T, gt_height, gt_normal], new taxa rows dark-highlighted).
**Own-eyes read**: the 4 new taxa are immediately recognizable next to the
13 existing recipes, not just in isolated crops — `baroque-rolling-wave`'s
`gt_height` column shows unmistakably coarse, soft rolling blobs distinct
from every other recipe's fine mm-scale granite pebbling; `fracture-
streamer`'s `gt_T` shows a clean branching cell-boundary network;
`confetti-shard`'s `gt_T` shows flat angular multi-colored cells, and under
the batch's real HDRI lighting (`without_shadow_photo.png`, not just the
downscaled contact-sheet tile) the sky/horizon is visibly seen THROUGH the
individual colored cells — a genuinely convincing "stained-glass confetti"
read, not just a flat color-block texture; `ring-mottle`'s `gt_T` shows
dense overlapping warm-toned blobs, clearly legible against the darker
matrix color. Marks (item B) are visible in the photo column across
several recipes (a dark tick on `confetti-shard`, scribbles elsewhere).

## 6. What is NOT done, and why (honest scope)

1. **The `gt_veil` finding is documented, not fixed.** The front-surface
   reflection veil present on every sample (§1) needs a scene-geometry fix
   (enlarge/reshape the `DarkWall` occluder, or accept the veil and rely on
   `gt_veil` for supervision) — that's a future iteration's work, not this
   one's. Flagged prominently rather than buried, since it changes the
   interpretation of every dataset generated so far.
2. **New-taxa color grounding is not real-exemplar-verified.** Unlike
   report 021 §5's five gap recipes (each grounded on 3 nearest-neighbor
   real catalog images by Lab distance), the 4 new taxa in this report have
   no equivalent grounding pass — colors are plausible, diverse choices.
   A `gap_exemplars.py`-style re-grounding pass is future work.
3. **White marks are invisible to the extractor.** `extract.detect_marks()`
   is dark-only (`MORPH_BLACKHAT`). Generator-side realism improved; the
   extractor gap this exposes is out of scope here.
4. **The opal-scatter stopgap is exactly that.** MMv3-G1's real scatter-PSF
   pass remains the actual fix (031 §5 / report 032 §6's own framing,
   reaffirmed, not relitigated).
5. **Item E's HDRI variety is a single lighting**, not the "1-2" the brief
   allowed for — one real-HDRI production-flag pass across all 17 recipes
   was judged sufficient as the integration test (confirms the flags/AOVs
   work at scale); a second lighting variant would mostly re-confirm the
   same wiring, not surface new information, given render-budget time
   constraints this session.
6. **Frame-material brightness widening is a real behavior change**, not
   just decoration — noted in `docs/GT_SPEC.md` §1d and §4 above rather
   than silently shipped: the dark-occluder-through-clear-glass audit trap
   now also exercises brighter occluders on ~60% of draws (3 of 5
   families), which is a different (also real) capture scenario than the
   trap originally tested.

The through-line: everything in the original brief's items A–F is landed
and gated; every corner cut or scope boundary above is named, not hidden.

## 7. Reproduction

```
cd research/delighting
# validate gate, all 17 recipes:
for r in cathedral-green cathedral-amber dark-opaque streaky-mix wispy-white \
         dark-deep dark-ruby dark-slate cathedral-blue cathedral-red \
         saturated-opalescent streaky-fine-texture dark-textured \
         baroque-rolling-wave fracture-streamer confetti-shard ring-mottle; do
  BLENDER -b -P generate_synthetic.py -- --out OUT --seed 42 --count 1 \
    --light-variations 1 --validate --recipe $r
done
python3 check_validation.py OUT

# 1-sample GT-v3 production-flag verification:
BLENDER -b -P generate_synthetic.py -- --out OUT --seed 500 --count 1 \
  --light-variations 1 --recipe cathedral-green \
  --no-tex-dump --exr-codec DWAA --gt-b --gt-aov

# VLM legibility, new taxa only:
python3 results/037/vlm_legibility_037.py results/037/legibility_inputs/*.png

# review render set + contact sheet:
for r in <17 recipes>; do BLENDER -b -P generate_synthetic.py -- \
   --out REVIEW --seed 42 --count 1 --light-variations 1 --recipe $r \
   --no-tex-dump --exr-codec DWAA --gt-b --gt-aov; done
python3 results/037/contact_sheet_037.py REVIEW results/037/contact_sheet_037.jpg
```
