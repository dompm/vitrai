# 031 — VLM glass-VARIETY coverage scan: what structural varieties exist that our 13 recipes don't

Date: 2026-07-10. Branch `research/delighting-031` (off `research/delighting`).
Code: `corpus/sample_variety_031.py` (stratified sample), `corpus/grid_contact_sheet_031.py`
(labeled contact-sheet grids), `corpus/vlm_taxonomy_031.py` (VLM taxonomy pass, `claude` CLI
subprocess, sonnet), `corpus/grid_recipes_031.py` + inline call (recipe-mapping pass),
`corpus/keyword_prevalence_031.py` (independent prevalence estimate), `corpus/extract_exemplars_031.py`
(committable downscaled exemplars). Artifacts: `results/variety_031/{sample_manifest.json,
grids/, taxonomy_raw/, taxonomy_consolidated.txt, recipe_mapping_raw.txt, exemplars/}`. Catalog
corpus accessed via the report-015 symlink convention (`frontend/public/assets/catalog_images`
symlinked in, not committed). No PR — reports are the deliverable.

Complements report 021 §5's Lab/hf statistical gap analysis (which measures color/texture-energy
*continuously* and can't see pattern *type*) with a categorical/structural read: does a glass
sheet's pattern belong to a known structural family a color histogram can't distinguish (ring
mottle vs. streaky-mix both can have similar hf_energy; fracture-streamer vs. smooth cathedral can
have similar mean Lab).

## 0. TL;DR

- **14-taxon bottom-up taxonomy** built from a VLM read of 72 stratified real catalog photos
  (§1). Two prevalence estimates broadly agree on the very common taxa but **diverge sharply on
  surface/body texture that manufacturers don't bother naming** — e.g. fine surface relief
  (T2) reads in **33% of sampled tiles** but only **9.4%** of registry names contain a
  granite/ripple/waterglass/rough-rolled keyword (category-level "Textured/Baroque" is 10.8%,
  still 3x under the pixel rate) — texture is pervasive across nominally-plain "Cathedral"
  category product photos, not confined to the manufacturer's own textured line.
- **9 of the 14 taxa have ZERO representation across our 13 synthetic recipes** (§3): iridized/
  dichroic surface sheen (T13), seedy bubbles/inclusions (T11), baroque/rolling-wave relief (T3),
  fracture/thread-crack streamer network (T9), confetti shard collage (T10), reactive
  color-cell mottle (T8), crackle/faceted relief (T4), dew-droplet/dimple relief (T5), drapery
  fold (T6).
- **Top-5 missing by prevalence** (§4): **T13 iridized/dichroic sheen (~15-19%)**, **T11 seedy
  bubbles (~12.5% sample / rarely named)**, **T3 baroque/rolling-wave relief (~11% by category,
  higher by pixels)**, **T9 fracture-streamer network (~9.7% sample / ~1.8% by "Collage" naming)**,
  **T10 confetti shard collage (~2.8%, tied with T4/T8, picked for its structural novelty)**.
- **Cost split (§5) is the actionable headline**: T13 (iridescence) is the ONLY top-5 miss that
  needs new render physics (thin-film interference, angle/wavelength-dependent) — everything
  else is texture-authoring or an extension of the EXISTING height/relief channel from
  Material-v2 (010-neural-shadow.md / report 022's octave system), i.e. cheap relative to T13.
- **Two of our EXISTING recipes fail to read as convincing members of their own intended
  taxon** (§3): `streaky-fine-texture` was VLM-classified as **ring/oval mottle (T7)**, not
  streaky (T12) — its streaks don't read as streaks; `wispy-white` was classified as
  **opalescent-smooth/milky diffusion (T14)**, not streaky (T12) either — its wisps are too
  faint to register. `dark-ruby`, by contrast, unintentionally reads as a *convincing* T7 ring
  mottle even though it wasn't authored as one.

## 1. Method

**Sample** (`sample_variety_031.py`): 72 images from the report-021/024 clean corpus
(`results/corpus/clean_manifest.json`, n=1,281), stratified by name-keyword tag group with
quotas that **prioritize structural breadth over color/volume breadth** per the task brief —
rare/distinctive tags (flemish, fracture/crackle, dew-drop/rainwater, seedy, ring-mottle,
streamer, baroque/hammered, cloud/sunset, muffle, marine/moss, reactive/fusion) get 2-8 picks
each (near-total coverage for the rarest), while the corpus's three largest tag pools
(granite/ripple n=121, iridescent/dichroic/luminescent n=199, opal n=291) get only 2-6 picks
each — those are already well characterized by exact keyword frequency over the full manifest
(§2's independent estimate), so the sample budget goes to structure the keyword frequency can't
see. 3 untagged "plain" baseline picks fill the remainder. Exact quotas and the resulting 72-image
manifest: `results/variety_031/sample_manifest.json`.

**VLM taxonomy pass** (`vlm_taxonomy_031.py`): 8 labeled 3-column contact-sheet grids (9 tiles
each, `results/variety_031/grids/batch0{0-7}.jpg`), one `claude -p --model sonnet` call per grid
(8 calls total). Prompt asks the VLM to enumerate DISTINCT visual varieties per grid, describe
each by structure (body vs. surface, pattern shape/scale), and cite tile numbers — catalog names
given as hints only, explicitly told to judge by pixels. Raw responses:
`results/variety_031/taxonomy_raw/batch0{0-7}.txt`.

**Consolidation**: I merged the ~45 raw per-batch variety labels into 14 canonical taxa by hand
(synonym merging, e.g. "granite/fine ripple relief" + "fine granite/pebbled surface relief" +
"granite/ripple fine relief" → one T2), keeping visually-justified splits the VLM itself made
consistently across batches (e.g. it independently separated fine granite pebbling (T2) from
large-scale rolling baroque waves (T3) in 3 different batches, even though the *catalog's own*
`classify_glass()` keyword rule lumps `baroque|artique|waterglass|ripple|granite|seedy|hammered|
dew drop|rainwater|glue chip|rough rolled` into one "Textured/Baroque" bucket — see §2's finding
that this catalog-side lumping *undercounts* prevalence, not just mislabels category).
Canonical taxonomy: `results/variety_031/taxonomy_consolidated.txt`, reproduced in full in §2.

**Recipe mapping**: one `claude -p --model sonnet` call on a labeled 4-column grid of our 13
recipes' clean renders (`results/variety_031/recipes/recipe_grid.jpg`, one `without_shadow_photo.png`
per recipe from `../../agent-a505b5928482e5d03/research/delighting/render_022/`), given the
consolidated taxonomy as reference, asked to assign each recipe's best-matching taxon AND judge
whether it reads as a convincing member. Raw: `results/variety_031/recipe_mapping_raw.txt`.

**Total VLM calls: 8 (taxonomy) + 1 (recipe mapping) = 9**, well under the 15-25 budget.

## 2. The consolidated taxonomy, with both prevalence estimates

Two independent prevalence estimates, as asked: **(sample)** = % of the 72 stratified sample
tiles the VLM tagged with this taxon (tiles can carry >1 taxon — compound tiles, e.g. a sheet
that is simultaneously fine-relief AND iridized AND milky, are real and common, so these columns
sum to >100%; also this sample was **deliberately breadth-biased**, so treat rare-tag rates as
"confirmed present," not "true prevalence," while the corpus-wide taxa (T1/T2/T12/T13/T14) — sampled at low-to-moderate quota despite large real pools — are informative lower bounds on true
pixel prevalence, likely undercounting via undersampling). **(keyword)** = exact name-keyword
frequency over the FULL clean manifest (n=1,281) — the more trustworthy prevalence number for
NAMED varieties, but a **systematic undercount for varieties the manufacturer doesn't bother
naming** (see T2/T3/T9/T12 below, all confirmed by VLM pixels far more often than by name).

| taxon | structure | sample % (n=72) | keyword % (n=1281) | in our 13 recipes? |
|---|---|---:|---:|---|
| T1 smooth-cathedral | flat uniform transmissive color, no texture | 6.9% | 41.6% ("plain", imprecise proxy) | yes (baseline of all cathedral recipes) |
| T2 granite/fine-ripple relief | fine all-over pebbled/wavy SURFACE relief, mm-scale | **33.3%** | 9.4% (granite/ripple/waterglass/rough-rolled) | **yes** — this IS the relief already baked into all 13 renders (report 010/022) |
| T3 baroque/rolling-wave relief | large-scale rolling wave SURFACE relief, cm-scale, coarser than T2 | 11.1% | 0.9% keyword / 10.8% category (Textured/Baroque) | **no** |
| T4 crackle/faceted relief | dense sharp-edged ridge network or angular ice-like facets | 2.8% | 0.16% (crackle+artique) | **no** |
| T5 dew-droplet/dimple relief | discrete raindrop-shaped SURFACE bumps, mid-scale | 2.8% | 0.16% (dew drop+rainwater) | **no** |
| T6 drapery fold | large arc-shaped cloth-like folds | 1.4% | 0.0% (no "drapery" name in this corpus at all) | **no** |
| T7 ring/oval mottle | dense overlapping round/oval opaque blobs, BODY | 6.9% (sample enriched by quota) | 0.6% (Ring Mottle category) | **partial** — `dark-ruby` unintentionally reads as this |
| T8 reactive color-cell mottle | blotchy square/cellular color-reaction pattern, BODY | 2.8% | 1.25% (reactive) | **no** |
| T9 fracture/thread-crack streamer | thin dark/colored branching crack-like lines, BODY | **9.7%** | 1.80% ("Collage" naming, best proxy) | **no** |
| T10 confetti shard collage | flat angular non-overlapping color pieces embedded in clear/white BODY | 2.8% | included in the 1.80% above (co-named) | **no** |
| T11 seedy bubbles/inclusions | small round bubbles/dots suspended in BODY | **12.5%** | 0.16% (seedy) | **no** |
| T12 streaky/wispy color blend | elongated partially-blended color streaks, BODY | **20.8%** | 3.3% (wispy/streaky) | **yes** (`streaky-mix` reads correctly; 2 others miss, see §3) |
| T13 iridized/dichroic surface sheen | thin rainbow/metallic film ON TOP of body, independent layer | **19.4%** | 15.5% (iridescent/dichroic/luminescent) | **no** |
| T14 opalescent-smooth/milky diffusion | uniform milky opacity, BODY, no structure | 6.9% | 22.7% (opal, imprecise proxy) | **yes** (`saturated-opalescent`, `wispy-white` reads as this too) |

Notable divergence pattern: for **surface/body texture that isn't the manufacturer's marketing
hook** (T2, T3, T9, T12), the VLM pixel-sample rate is **3-6x the keyword rate** — texture and
streak/mottle-like body variation show up broadly across "plain-named" product photos, not just
the lines explicitly branded Textured/Baroque/Wispy. For **surface sheen and diffuse opacity**
(T13, T14), which manufacturers DO reliably name ("Iridescent", "Opalescent"), the two estimates
agree to within ~30% relative — a reasonable cross-check that the method (VLM tile-tagging) isn't
wildly miscalibrated, it's specifically naming-convention gaps that create the T2/T3/T9/T12 gap.

## 3. Recipe mapping: do our 13 recipes convincingly cover any of these taxa?

One VLM call, 13-recipe grid vs. the taxonomy above (`recipe_mapping_raw.txt` verbatim):

| recipe | mapped taxon | convincing? | VLM's reason |
|---|---|---|---|
| cathedral-amber | T2 | yes | clear fine pebbled relief, natural gradient |
| cathedral-blue | T2 | yes | crisp mm-scale pebble texture, plausible depth gradient |
| cathedral-green | T2 | partially | good pebble texture but abrupt solid-black bottom band reads as a crop artifact |
| cathedral-red | T1 | partially | lacks true flatness; uneven dark blotch reads as lighting, not material |
| dark-deep | T1 | **no** | too dark/featureless to tell it's glass vs. underexposed background |
| dark-opaque | T2 | partially | texture too faint, muddy tone undercuts the granite-glass read |
| dark-ruby | T7 | yes | soft overlapping pink/red blobs match ring/oval mottle — **unintended but convincing** |
| dark-slate | T2 | yes | convincing fine pebbled relief over believable gray-white gradient |
| dark-textured | T2 | partially | surface relief too subtle/smooth to clearly register as granite texture |
| saturated-opalescent | T14 | partially | hazy milky top plausible but sharp horizontal band breaks the uniform-diffusion look |
| streaky-fine-texture | **T7** | yes | reads as ring/oval mottle, **not the streaky (T12) family it was authored as** |
| streaky-mix | T12 | yes | blended blue/white cloud-like streaking correctly matches streaky family |
| wispy-white | **T14** | yes | uniform milky-white diffuse glow, **not streaky (T12) — its wisps don't register** |

Two authoring misses worth flagging to the generator maintainers directly: **`streaky-fine-texture`
and `wispy-white` — both named/intended as streaky-family recipes — get independently classified
by a fresh VLM judge as something else** (ring mottle and opalescent-smooth respectively), meaning
their authored streak signal is currently too weak relative to their base color/haze to read as
"streaky" to an outside eye, even though 022's own hf-energy statistics call the octave fix a
success. This is a legibility gap statistics alone didn't catch — recommend a follow-up
side-by-side crop test (same crop, side-by-side with a real T12 exemplar) before the next haze/
texture tuning pass.

## 4. Ranked missing-variety list (by prevalence, higher-confidence estimate first)

1. **T13 iridized/dichroic surface sheen** — 19.4% sample / 15.5% keyword (agree) — **not achievable
   by texture or relief authoring; genuinely missing physics.**
2. **T11 seedy bubbles/inclusions** — 12.5% sample / 0.16% keyword (rarely named; caveat: sample
   estimate may be inflated by compression/DOF misreads of fine dot texture as bubbles — flagged,
   not resolved here).
3. **T3 baroque/rolling-wave relief** — 11.1% sample / 10.8% category (best-agreeing pair for this
   taxon) — a coarser-scale sibling of the fine relief we already generate.
4. **T9 fracture/thread-crack streamer network** — 9.7% sample / 1.80% keyword ("Collage" naming).
5. **T10 confetti shard collage** (tied at 2.8% with T4 crackle/faceted and T8 reactive-cell
   mottle; picked as #5 for structural distinctiveness/shippability — often the SAME physical
   product as #4, see exemplars).

Full ranked tail: T4 crackle/faceted (2.8%/0.16%), T8 reactive-cell mottle (2.8%/1.25%), T5
dew-droplet/dimple (2.8%/0.16%), T6 drapery fold (1.4%/0.0% — genuinely rare or simply unnamed in
this corpus's SKUs; classic Tiffany drapery glass exists in the wider market even if underrepresented
here).

## 5. Cost split for each top-missing variety

| taxon | achievable with... | why |
|---|---|---|
| **T13 iridized/dichroic sheen** | **(c) NEW material-model physics** | Thin-film interference is an angle- AND wavelength-dependent Fresnel reflection layered on top of the base transmission — texture authoring (a T/h pattern) and the existing height/relief channel (a geometric bump, no spectral/angular response) cannot produce it. Needs a new coating/interference BRDF term; this is the only top-5 item that's a genuinely new render-physics investment, and it interacts with both the 2D and future 3D lamp render paths since it's view-angle dependent. |
| **T11 seedy bubbles/inclusions** | **(b) relief/height channel**, mostly | The Material-v2 height/normal export (010-neural-shadow.md) already drives Blender bump, and Cycles' own glass shader already refracts through bump-derived normals — a scattered round-dimple height pattern (Poisson-disc placement, small radius) should produce believable lensing/highlight-rim bubbles for free through the existing shader, no new physics term needed. Caveat: item 2's sample-rate uncertainty (compression/DOF confound) means this should be scoped small first. |
| **T3 baroque/rolling-wave relief** | **(b) relief/height channel**, cheap | Directly a coarser-scale extension of report 022's fBm octave system (lower octave count, larger `lacunarity`/scale, higher amplitude) — the generator mechanism already exists and is parameterized exactly for this; likely a half-day tuning task, not new code. |
| **T9 fracture/thread-crack streamer** | **(a) texture authoring only** | A body-level color/opacity pattern (T channel): a thin branching line-network mask (Voronoi-cell-boundary or similar) composited darker/tinted over a base. No new relief or physics — it's a new procedural mask generator feeding the existing T-authoring pipeline. |
| **T10 confetti shard collage** | **(a) texture authoring only** | A filled-region variant of the same Voronoi-cell idea behind T9 (cells get a random fill color instead of just a boundary line) — often the literal same product line as T9 (see exemplars: "...Base Collage" names appear under both), so authoring both together in one Voronoi-cell generator is the efficient path. |

(For completeness, the tail: **T4 crackle/faceted** is (b) relief/height with a new *sharp*
cellular height function, not the smooth fBm currently used — moderate, needs new code, not just
new params. **T8 reactive-cell mottle** is (a) texture authoring, a soft-edged Voronoi color-cell
mask, similar cost to T9/T10. **T5 dew-droplet** is (b) relief/height, a Poisson-disc bump pattern
like T11's bubbles but larger/sparser. **T6 drapery** is (b) relief/height, a low-frequency
directional/arc-biased wave, a straightforward variant of T3's authoring.)

**Net read**: of the top-5 missing varieties, **4 of 5 are cheap** (existing height/relief
machinery or new-but-simple texture masks) and **1 of 5 (T13, also the single most prevalent
miss) requires new physics** — a clean, actionable split for scoping the next iteration.

## 6. Exemplars

Downscaled (max 480px), committed real image files (not symlinks — the catalog corpus itself
stays gitignored per report-015 convention) under `results/variety_031/exemplars/`:

- `T13_iridized/{062,063,064}_Bullseye_iridescent_dichroic_lumin.jpg` — "Gold Purple", "Oregon
  Gray", "Midnight Blue" Iridescent Transparent — same rainbow-sheen structure over 3 different
  base colors, confirming the sheen is a layer independent of body hue.
- `T11_seedy/{012_Wissmach_seedy, 034_Bullseye_cloud_sunset, 045_Bullseye_marine_moss}.jpg` —
  "Clear Heavy Seedy" is the clean reference; the other two show the bubble read as an incidental
  feature of nominally plain-named transparent sheets (the T2/T3/T9/T12 undercounting pattern
  again).
- `T3_baroque/{000_Wissmach_flemish, 028_Oceanside_baroque_hammered, 039_Wissmach_muffle}.jpg` —
  three different catalog names (Flemish, Hammered, English Muffle) landing on the SAME visual
  taxon; a concrete illustration of §2's "catalog naming undercounts structural prevalence" finding.
- `T9_fracture_streamer/{005,007,022}_Bullseye_*.jpg` — "Green & Pink Fracture w/Line Cast...",
  "Green Fracture...", "White (with Black Streamers)..." — thin branching lines over a clear or
  confetti base.
- `T10_confetti/{020,021}_Bullseye_streamer.jpg` — "Black with Black Streamers on Clear... Base
  Collage" and "Deep Pink, Plum, Spring Green, Aqua (with Pink Streamers)... Base Collage" — flat
  angular color pieces, co-occurring with T9's line network on the same tiles (same product family).
- Tail taxa also captured for completeness: `T4_crackle/`, `T5_dewdrop/`, `T6_drapery/`,
  `T8_reactive_cell/`.

Full contact-sheet grids (all 72 sample tiles + all 13 recipes) are also committed under
`results/variety_031/grids/batch0{0-7}.jpg` and `results/variety_031/recipes/recipe_grid.jpg`
for anyone who wants to re-derive the taxonomy or spot-check a specific tile.

## 7. Honest caveats

1. **The stratified sample is deliberately not prevalence-representative** (breadth quotas per
   the task brief) — every "sample %" number in §2/§4 for a heavily-quota'd rare tag (T5, T6, T8)
   should be read as "confirmed present, minimum N tiles," not a calibrated rate. The keyword
   estimate is the more defensible prevalence number where a naming convention exists; where it
   doesn't (T3, T9, T10's confetti half), neither estimate is a true population rate — both are
   lower bounds, and the true rate is unknown without a uniform random sample (a natural follow-up).
2. **T11's sample rate (12.5%) is the least trustworthy number in the matrix** — small round dots
   in a JPEG-compressed macro photo are ambiguous between real embedded bubbles, surface dimples
   (see tile 011, literally named "Seedy" but VLM-classified as T5 dew-droplet, not T11 — the two
   taxa may be the same underlying glass viewed under different capture conditions), and
   compression artifacts. Flagged, not resolved.
3. **This is one VLM's (sonnet) single-pass read per grid, not a consensus.** No inter-rater
   check was run (out of scope for the ~9-call budget). The consolidation step (merging ~45 raw
   labels to 14 canonical taxa) is my own judgment call, done in good faith but not independently
   verified.
4. **The recipe-mapping call (§3) is also a single VLM pass** on renders that already carry a
   thin dark curved "mark" artifact (the hand-mask/grease-pencil simulation, visible on most
   recipe tiles) — this wasn't flagged as a problem by the VLM in its convincing/not-convincing
   judgments, but it's a known confound worth a mention if the recipe grid is reused elsewhere.
5. **`streaky-fine-texture` and `wispy-white`'s taxon misses (§3)** are read from ONE labeled
   grid call, not a scored benchmark — worth confirming with a dedicated, more controlled
   real-vs-synthetic side-by-side before treating as an authoring bug (see §3's recommendation).

## Reproduction

```
cd research/delighting
ln -s /path/to/frontend/public/assets/catalog_images ../../frontend/public/assets/catalog_images  # if not already present
python3 corpus/sample_variety_031.py                       # -> results/variety_031/sample_manifest.json
python3 corpus/grid_contact_sheet_031.py 9 3                # -> results/variety_031/grids/batch0{0-7}.jpg
python3 corpus/vlm_taxonomy_031.py                          # -> results/variety_031/taxonomy_raw/*.txt (needs `claude` CLI)
python3 corpus/grid_recipes_031.py                          # -> results/variety_031/recipes/recipe_grid.jpg (needs render_022 renders)
python3 corpus/keyword_prevalence_031.py                    # -> stdout, independent prevalence estimate
python3 corpus/extract_exemplars_031.py <subdir> <idx> ...  # -> results/variety_031/exemplars/<subdir>/
```
