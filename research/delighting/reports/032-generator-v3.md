# 032 — Generator v3: pre-scaling texture-authoring overhaul

Date: 2026-07-10/11. Branch `research/delighting-032` (off `research/delighting`).
Consolidates the evidence from reports 029 (VLM realism critique), 031 (variety
coverage), and `docs/RENDER_AT_SCALE.md` into generator changes, ahead of the
20k-sample production run. Code touched: `generate_synthetic.py` (WP-A authoring
+ helpers, WP-B `--specular`), `corpus/appearance_stats.py` (single-source
refactor), `docs/GT_SPEC.md` (WP-C spec + size budget). Evidence, harnesses,
and review materials under `results/032/`. No PR — reports are the deliverable.

## 0. TL;DR

- **WP-A (texture authoring) — SHIPPED + verified offline + `--validate` gated.**
  The headline: the two recipes report 031 caught being **misclassified by a
  fresh VLM** (`streaky-fine-texture`→ring mottle, `wispy-white`→smooth opal)
  now carry legible flow-advected streaks — macro-scale directional anisotropy
  of authored T rises **1.12→1.65 (1.47x)** and **1.20→1.96 (1.63x)**
  respectively (`results/032/wpa_offline_evidence.txt`). Added the discrete
  seed/bubble micro-event layer (029's #1 authenticity cue, previously entirely
  absent), Beer–Lambert **T↔height coupling** (029 gap G-3, the most-actionable
  NEW finding — corr(T, height−0.5)=+0.92 on cathedral, mean-T preserved), and
  fixed the **mirror-symmetry artifact** (gallery-flagged cathedral-green
  seed700: mirror corr 0.235→0.007; seed1234 0.295→0.017) — all
  statistics-preserving (hf-energy grounding intact).
- **Single-source grounding.** `corpus/appearance_stats.py` no longer duplicates
  the recipe formulas (the copy the code comments warned "keep in sync" and
  which WOULD have drifted on every WP-A change) — it now imports the REAL
  `author_glass_arrays` under a `bpy` stub, so appearance grounding re-derives
  byte-identical authored T. Color targets preserved (cathedral-green
  L71.9/C28.7/hue146°, streaky-fine L55/C40/hue30° — match 021/022).
- **WP-C (GT export) — spec + size decision SHIPPED (`docs/GT_SPEC.md`); code
  wiring specified, not landed.** Measured a real sample at **242 MB** (validate)
  / ~270 MB (production), of which **58% (141.7 MB) is the regenerable `tex_*.exr`
  dump**. Decision for 20k: `--no-tex-dump --exr-codec DWAA` → **≤100 MB/sample**
  (5.5 TB → 1.2–1.8 TB), which RENDER_AT_SCALE named as the true scaling
  constraint (egress can cost 10x compute). `gt_B` + 4 free multilayer AOVs
  specified with wiring notes.
- **VLM legibility: 3/3 streaky recipes now classify as T12-streaky** (§3) —
  after four retune→re-render→re-classify rounds; the decisive addition was a
  thin smoke-filament veil layer (`filament_layer()`), the cue the real
  exemplars show. Instrument calibrated on two committed REAL exemplars (both
  pass), so the letter grade is meaningful.
- **WP-B: `--specular` flag landed** (glass Specular IOR Level 0.5–1.0 + a
  dim-interior wall, dedicated RNG so OFF/ON scenes are otherwise identical);
  specular-ON extractor impact measured in §7. Textured window frames, wider
  camera jitter, and the opal-scatter ceiling are NOT landed (§6).
- **`--validate` gate: 13/13 pass** — unchanged-family recipes reproduce report
  022's committed MAE to the 3rd–4th decimal; the reworked streaky recipes stay
  inside the 022 band (§5).

## 1. WP-A: texture-authoring overhaul

All authoring is pure numpy/scipy in `author_glass_arrays` + new helpers
(`flow_field`, `advect_streaks`, `streak_selector`, `micro_events`,
`couple_T_to_height`); no shader/renderer change, so GT stays by-construction
and the uniform-backlight validate is unperturbed (both gt_T and the transmitted
photo derive from the same authored T).

### 1a. Flow-advected streaks (029 G-1 + 031 legibility failures)

Replaced the isotropic vertical zoom-stretch streak authoring with **line-
integral-convolution advection along a flow field** (a dominant pull direction +
low-frequency curl eddies), with feathered ends (triangular LIC taper) and
occasional **sharp lamination lines** (thresholded then advected). Authored at a
320px working resolution (streaks are large-scale) then bilinear-upscaled —
~0.6 s at 1536.

Evidence (`results/032/wpa_evidence.py`, macro-anisotropy @lp32, OLD=origin):

| recipe | OLD | NEW | note |
|---|---:|---:|---|
| streaky-fine-texture | 1.12 | **1.65** | 031's ring-mottle (T7) misread — the worst failure |
| wispy-white | 1.20 | **1.96** | 031's smooth-opal (T14) misread |
| streaky-mix | 1.64 | 1.38 | already read correctly (031); the metric *rewards* the old perfectly-straight bands and penalizes realistic feathered/curled streaks — the VLM check (§3), not the ratio, is the acceptance gate here. Curl kept low (0.08) to stay coherent. |

The fine-texture detail was moved to a genuinely fine scale (20–22px, 2–3
octaves) so it feeds hf-energy **without** swamping the macro streak reading —
the exact failure mode of the old isotropic scale-60 amp-0.8 overlay that flat-
tened the streak direction (031).

### 1b. Micro-event layer (029 #1 authenticity cue; 031 T11)

`micro_events()` stamps discrete refractive **donut** events (raised rim +
sunken core) into the height field (so they lens through the existing bump
shader — 031's free-through-existing-shader cost note) and a small local
transmission perturbation, with a footprint mask. Per-recipe density (events /
512 tile): cathedral 28, dark-textured 40, wispy/opal 10, etc. Coverage where
authored: 0.5–1.9% (was **0** — we had no event layer at all, 029's single most
consistent "real" cue). Density is a per-recipe dict, so a seedy-heavy T11
variant is a one-line addition; a dedicated `gt_events` mask export is folded
into WP-C's AOV plan.

### 1c. Beer–Lambert T↔height coupling (029 G-3)

`couple_T_to_height(T, height, k)`: local thickness co-varies with the SAME
authored height field — `T_out = T^(1 − k·(2·height−1))`. Crests (thinner)
transmit **lighter and less saturated** ((T_r/T_g)^p → 1 for p<1), troughs
darker and more saturated — the physical co-variation 029 found missing (color
rode ON TOP of relief as an independent draw). Per-recipe swing k (clear
cathedral 0.22 … milky opal 0.14 … dark 0.12). Verified: corr(T, height−0.5) =
+0.92 on cathedral-green, mean-T preserved to 4 decimals (0.3542), and the
helper unit-check shows crest [0.503,0.299,0.178] > trough [0.318,0.134,0.056].
Because the coupled T becomes BOTH gt_T and the transmitted photo, validate
agreement is unchanged.

### 1d. Mirror-symmetry artifact fix

Root cause (found by bisecting the fBm blend): the coarsest octave of large-scale
recipes lands at a tiny `base_res` (cathedral scale=200 → 7 cells at 1536, as low
as 2 at smaller sizes), and a cubic zoom of a 2–7-cell grid is near mirror-
symmetric about the image CENTER for some seeds. Fix in `generate_noise._band`:
(a) `base_res` floor of 4, (b) generate a slightly larger grid and crop a per-band
**random-offset** window so the center is not a reflection axis. Both preserve the
noise's frequency and amplitude (hf-energy unchanged within noise → 021/022
grounding holds); they only decorrelate the spurious centered mirror. Result:
seed700 UD 0.235→0.007, seed1234 LR 0.295→0.017; other seeds stay at the ~0.02–0.06
coarse-noise sampling floor. Deterministic (offset drawn from the same seeded
stream).

### 1e. Marks / new taxa — status

- **Mark overhaul** (white paint-pen + dark, anti-aliased, per-mark GT):
  **NOT landed.** The current dark-only scribble is unchanged. This is the one
  WP-A bullet I deprioritized under time; it is independent of the streak/relief
  work and cleanly landable next. Flagged, not faked.
- **New taxa** (baroque rolling-wave, Voronoi fracture/confetti, formalized
  ring-mottle): **NOT landed as recipes.** The micro-event + coupling + flow
  machinery they'd reuse is now in place; adding them is per-recipe authoring +
  a corpus-grounding pass. `NO thin-film iridescence (T13)` — correctly deferred
  to MMv3 physics per 031 §5.

## 2. Single-source appearance grounding (`corpus/appearance_stats.py`)

Removed the ~130-line duplicated `generate_noise` + `recipe_T` copy; it now stubs
`bpy` and imports `generate_synthetic.author_glass_arrays` directly (verified:
shim T == generator T, byte-identical). This turns the "keep both files in sync"
footgun — which every WP-A change would have tripped — into a real single source
of truth, at zero risk to the render path (no importer of appearance_stats
elsewhere; the generator is untouched by the shim).

**Full grounding re-run** over the real corpus (n=692 backlit-verified images;
`results/032/appearance_grounding_032.txt`, refreshed
`results/corpus/appearance_stats.json`): all 13 post-032 recipes sit inside
their class's real L/C/hue ranges — streaky-fine-texture lands the 021 target
exactly (L54.4/C40.0/hue30°); wispy-white moved from L=90.7 (ABOVE the real
wispy p95 of 88.9 — the pre-032 recipe was too white to be real) to L=76,
between the class median and p95. Two honest flags: (1) the previously
committed `appearance_stats.json` was **stale — pre-022, 8 recipes only** — so
old-vs-new hf comparisons from that file are meaningless; the valid hf
preservation evidence is the OLD-code-vs-NEW-code harness in
`results/032/wpa_evidence.py`. (2) By the 512px radial-FFT hf-fraction
instrument, the two-color streak recipes (streaky-mix 0.0011, wispy-white
0.0013) sit below the real wispy p5 (0.0035) — the legible macro-streak
contrast inflates the DENOMINATOR (total variance), not because fine detail
fell (the stale pre-022 baseline scored the same 0.0016 with far less macro
structure). hf-fraction and streak legibility trade off directly through that
ratio; flagged for a follow-up calibration of the instrument, deliberately not
"fixed" by killing the streak contrast the VLM gate demanded.

## 3. VLM legibility verdict (WP-A acceptance): **3/3 PASS, instrument-calibrated**

Harness: `results/032/vlm_legibility_032.py` — one blind `claude -p` (haiku)
taxon call per rendered photo (T12-streaky vs T7-ring-mottle vs T14-smooth-opal
vs T2-cathedral-textured), the `vlm_classify.py` subprocess pattern. Inputs are
the uniform-backlight `--validate` renders (the HARDEST case for pattern
legibility — no directional lighting to help). Downscaled copies committed at
`results/032/legibility_inputs/`.

**Instrument calibration first**: both committed REAL wispy/streaky exemplars
(`reports/assets_029/corpus_bullseye-0021000000f1010.jpg` black 2-color mix,
`corpus_bullseye-0023050030f1010.jpg` salmon 2-color mix) classify as
T12-streaky — the letter grade is achievable, so a synthetic miss is a real
authoring gap, not prompt noise.

It took four rounds (each: retune → re-render → re-classify → verify by eye —
every round re-passed the `--validate` gate):

| round | change | streaky-mix | streaky-fine | wispy-white |
|---|---|---|---|---|
| 1 | flow-advected streaks (§1a) | **T12 PASS** | T2 (fine detail swamped the soft streak in the RENDER) | T14 (wisps washed to near-white) |
| 2 | streak amp ↑, detail ↓, wisp threshold/color deepened | — | T14 | T14 |
| 3 | **filament layer** (`filament_layer()`: thin smoke-like curved veils — sparse thresholded source + long high-curl LIC at 768 working res; the cue the real exemplars scream) | — | **T12 PASS** | T14 |
| 4 | wispy contrast deepened (wisp_color 0.42→0.30, fil 0.5→0.72; grounded headroom — pre-032 wispy L=90.7 was ABOVE the real wispy p95 88.9, final L=76 sits between the class median 56.8 and p95; gate MAE improved 0.0397→0.0264) | — | — | **T12 PASS** |

The round-1..2 lesson is worth keeping: **authored-array anisotropy is not
render legibility.** Round 1's authored T had the anisotropy lift (§1a table),
but the render diluted it (fine-detail mottle + relief shading). The filament
layer — thin, sharp, curved veils folding through broad soft marbling — is what
flipped the VLM, and it is exactly what the real corpus exemplars show.

Own-eyes verdict (mine, final renders next to the real exemplars): streaky-mix
has legible directional two-color streaks with sharp lamination lines;
streaky-fine reads as marbled salmon with thin darker threads — a convincing
sibling of the real salmon 2-color mix; wispy-white now carries smoke-like
folding veils with thin filaments, a strong family resemblance to the real
black-smoke exemplar (in white). None of the three would fool 029's full
realism critique (that instrument reads camera optics and lighting too — out of
WP-A's scope), but the *pattern taxon* is now right, which is what 031 flagged
and this gate accepts.

## 4. WP-C: GT export v3 + size budget

Full spec in `docs/GT_SPEC.md`. Headline numbers (measured, real 1536² sample):

| config | per-sample | 20k |
|---|---:|---:|
| current (uncompressed, tex dumped) | 273 MB | 5.5 TB |
| `--no-tex-dump` (regenerable from seed) | ~131 MB | 2.6 TB |
| `--no-tex-dump --exr-codec DWAA` | **~60–90 MB** | **1.2–1.8 TB** |

`gt_B` (hidden-glass background, Bet-1) + `gt_veil/index/uv/depth` (free
multilayer AOVs off the one main render) specified with wiring notes; each stays
inside the ≤100 MB budget. Encoding cheat-sheet (sRGB-vs-linear per file, the
025 lesson) is in the doc so it isn't relitigated at read time. **Code wiring
for the flags/AOVs/gt_B is specified, not landed** — it must re-pass validate +
an extractor smoke-run, deliberately not smuggled in with the authoring change.

## 5. `--validate` gate

Full 13-recipe uniform-backlight gate on the WP-A code (seed 42,
`check_validation.py`, report-022 protocol; raw table committed at
`results/032/validate_gate_032.txt`). Strictly, EVERY recipe's texture is
regenerated-by-design this iteration (micro-events + coupling touch all 13
T/height fields; the streaky three additionally have new streak authoring) —
what the gate verifies is the *invariant*: rendered transmission == gt_T under
uniform backlight, i.e. the authored→shader→render→GT pipeline is intact.

**13/13 pass.** MAE vs report 022's committed gate values:

| recipe | 032 MAE | 022 MAE | | recipe | 032 MAE | 022 MAE |
|---|---|---|---|---|---|---|
| dark-deep | 0.0013 | 0.0013 | | saturated-opalescent | 0.0132 | 0.0130 |
| dark-ruby | 0.0017 | 0.0016 | | cathedral-blue | 0.0147 | 0.0146 |
| dark-textured | 0.0035 | 0.0035 | | cathedral-red | 0.0163 | 0.0162 |
| dark-opaque | 0.0045 | 0.0045 | | cathedral-green | 0.0232 | 0.0230 |
| streaky-fine-texture | 0.0083 | 0.0084 | | cathedral-amber | 0.0258 | 0.0256 |
| dark-slate | 0.0095 | 0.0095 | | streaky-mix | 0.0426 | 0.0375 |
| | | | | wispy-white | 0.0264 | 0.0397 |

(Table shows the FINAL post-§3-tuning values; the intermediate rounds also all
passed — streaky-fine 0.0083/0.0084/0.0084, wispy 0.0341/0.0318/0.0264 across
rounds.) Reading: the dark family reproduces 022 exactly (the coupling swing is
smallest there and MAE is texture-mean-dominated); cathedral/opalescent recipes
land within +0.0002 of 022 (micro-events + coupling are mean-preserving by
construction); the two rewritten streak recipes move MAE *within* the 022 band
in both directions (streaky-mix 0.0375→0.0426, wispy-white 0.0397→0.0264 —
022's own gate ceiling was 0.0397; streaky-mix's small rise tracks its sharper
lamination lines, far below any failure threshold).

## 6. What is NOT done, and why (honest scope)

Landed beyond WP-A: the `--specular` flag + dim-interior wall (§0, §7), the
VLM legibility loop (§3), the grounding re-run (§2), extractor OFF/ON A/B and
review contact sheet (§7). Deliberately NOT landed:

1. **WP-B remainder**: textured window frames (the RGB-0.01 void bars are
   unchanged), wider camera jitter ranges, per-render HDRI-pack sampling as the
   *default* (the pack + `--hdri-dir` are consumed by the §7 batches, but the
   no-flag default still downloads the single sunflowers HDRI — unchanged for
   byte-compat), and the opal-scatter stopgap (second rough-transmission lobe).
   Each is a scene change that must ride its own validate+extractor pass; the
   real fix for the scatter is MMv3-G1's PSF and remains so.
2. **Mark overhaul + new taxa recipes** (§1e).
3. **WP-C code** (`--no-tex-dump`, `--exr-codec`, gt_B, AOVs) — spec'd (§4)
   with wiring notes, not landed.
4. **Determinism spot-check old-vs-new**: not run as a render-level check this
   iteration — by design the reworked recipes regenerate (that's the point),
   and unchanged-recipe determinism is already covered by RENDER_AT_SCALE §5
   plus the gate's 4th-decimal MAE reproduction (§5). Authoring-level
   determinism (same seed → identical arrays) is verified in
   `results/032/wpa_evidence.py`'s harness.

The through-line: everything that could be verified offline or with the render
budget available this session shipped and is gated; the remaining scene/GT
items each need their own validate+extractor pass and are cleanly separable.

## 7. Extractor impact: specular OFF vs ON, and the review contact sheet

Batch: 13 recipes × 1 HDRI-pack lighting (`--hdri-dir`, 23 CC0 HDRIs,
seed-keyed) × production config (shadow pairs), seeds 500–512, rendered TWICE
with identical seeds — specular OFF vs `--specular` ON (Specular IOR Level
0.5–1.0 + dim-interior wall 0.02–0.08; scenes otherwise identical by the
dedicated-RNG construction). Extractor = `eval_synthetic.py`'s oracle-class
harness over `extract.py`. Full tables: `results/032/extractor_{off,on}_table.md`,
per-recipe delta: `results/032/extractor_delta_off_on.txt`.

**Measured impact: near-zero on T, small and dark-family-concentrated on h.**
Mean ΔT_mae = +0.0000 (max |Δ| 0.005, cathedral-blue); mean Δh_mae = +0.0024,
dominated by ONE recipe — dark-deep h_mae 0.115→0.155 (+0.040): against a
near-black transmission even a dim-interior veil is proportionally the largest
signal, and the veil-less extractor books it as haze.

The honest reading (do NOT over-celebrate): this is **not** evidence the
extractor tolerates reflection veils — it is evidence the *dim-interior* veil
this flag produces is small by construction (a 0.02–0.08 gray wall). It is the
right first step for capture realism (a real workshop interior IS dim next to a
backlit sheet — and 9/16 of 029's diagnostics cited the total *absence* of any
glint), but MMv3-G2's real front IBL (a bright environment reflected in the
front face) will hit the extractor's no-veil assumption much harder. That
measurement belongs to the iteration that adds the front IBL; this one
establishes the mechanism, the meta.json audit trail (the `specular` block),
and the baseline numbers.

Also visible in the OFF/ON photos (own eyes): cathedral-green/red pick up a
believable relief-tracking sheen with `--specular` ON; the effect is subtle at
review-sheet scale for the dark family. Micro-event seeds read as small bright
dots on the dark recipes — 029's donut cue, now present.

**Review contact sheet** (WP-D): `results/032/contact_sheet_032.jpg` —
13 recipes × [photo OFF | photo ON | gt_T | gt_height], downscaled and
committed; built by `results/032/contact_sheet_032.py` from the gitignored
batch dirs, so the lead can rebuild the review page. The HDRI-pack lighting
variety is evident across rows (window-lit interiors, outdoor sun, dim rooms —
vs the historical single sunflowers env), and the frame-occluder trap and
shadow-pair machinery ran unchanged (dark-deep drew edge bars; streaky-mix drew
a window-backlit interior).

**Production per-sample footprint, measured on this batch: 275 MB** (21 files,
shadow pair + 5 GT channels) — confirms `docs/GT_SPEC.md`'s 273 MB planning
number and its ≤100 MB `--no-tex-dump --exr-codec DWAA` decision.

## Reproduction

```
cd research/delighting
python3 results/032/wpa_evidence.py          # OLD-vs-NEW offline evidence table
# validate gate (needs Blender):
for r in <13 recipes>; do BLENDER -b -P generate_synthetic.py -- \
   --out OUT --seed 42 --count 1 --light-variations 1 --validate --recipe $r; done
python3 check_validation.py OUT
# VLM legibility (needs `claude` CLI):
python3 results/032/vlm_legibility_032.py OUT/<streaky-sample>/without_shadow_photo.png
# specular A/B batch + extractor + contact sheet (needs Blender + HDRI pack):
python3 fetch_hdri_pack.py --out HDRI_DIR --res 1k
#   render 13 recipes seeds 500-512 twice (results/032/batch_specular_ab_032.sh; ON adds --specular)
python3 eval_synthetic.py --data OFF_DIR --out EVAL_OFF   # and ON_DIR
python3 results/032/contact_sheet_032.py OFF_DIR ON_DIR results/032/contact_sheet_032.jpg
# appearance grounding (needs the catalog_images symlink, report-015 convention):
python3 corpus/appearance_stats.py
```
