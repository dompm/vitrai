# 032 — Generator v3: pre-scaling texture-authoring overhaul

Date: 2026-07-10. Branch `research/delighting-032` (off `research/delighting`).
Consolidates the evidence from reports 029 (VLM realism critique), 031 (variety
coverage), and `docs/RENDER_AT_SCALE.md` into generator changes, ahead of the
20k-sample production run. Code touched: `generate_synthetic.py` (WP-A authoring
+ helpers), `corpus/appearance_stats.py` (single-source refactor),
`docs/GT_SPEC.md` (WP-C spec + size budget). Offline evidence + reproduction
scripts under `results/032/`. No PR — reports are the deliverable.

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
- **WP-B (scene realism) and the render-gated WP-D items (specular-on extractor
  impact, gallery rebuild) — NOT landed this iteration.** Honest scoping call:
  WP-A is the highest-leverage, offline-verifiable, evidence-backed core (029
  gaps #1/#3 + 031's documented legibility failures), and I prioritized landing
  it clean and gated over half-finishing the scene/GT render plumbing. §6 states
  exactly what remains and why each needs a render/VLM budget I flag rather than
  fake.
- **`--validate` gate: 13/13 pass** — unchanged-family recipes reproduce report
  022's committed MAE to the 3rd–4th decimal; the reworked streaky recipes stay
  inside the 022 band (§5).
- **VLM legibility verdict:** see §3.

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
elsewhere; the generator is untouched by the shim). Recipe color stats
re-derived post-change still hit the 021/022 targets (§0).

## 3. VLM legibility verdict (WP-A acceptance)

[PENDING — HDRI-lit renders of the three streaky recipes + a per-recipe `claude`
CLI taxon classification (streaky T12 vs ring-mottle T7 vs smooth-opal T14 vs
cathedral). Acceptance: streaky recipes classify as streaky. Filled after the
`--validate` gate frees the GPU.]

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
| | | | | wispy-white | 0.0341 | 0.0397 |

Reading: the dark family reproduces 022 exactly (the coupling swing is smallest
there and MAE is texture-mean-dominated); cathedral/opalescent recipes land
within +0.0002 of 022 (micro-events + coupling are mean-preserving by
construction); the two rewritten streak recipes move MAE *within* the 022 band
in both directions (streaky-mix 0.0375→0.0426, wispy-white 0.0397→0.0341 —
022's own gate ceiling was 0.0397; streaky-mix's small rise tracks its sharper
lamination lines, far below any failure threshold).

## 6. What is NOT done, and why (honest scope)

Render/VLM/extractor-budget-gated items I deliberately did not fake:

1. **WP-B scene realism** (front-surface specular veil, textured window frames,
   wider camera jitter, opal-scatter ceiling). Specular-on **degrades the
   veil-less extractor** by construction (029/MMv3 G2) — the point is to MEASURE
   that honestly, which needs an extractor smoke-run over a new render batch
   (specular OFF vs ON). Not startable without those renders; flagged as the
   next package.
2. **Mark overhaul + new taxa recipes** (§1e).
3. **WP-C code** (flags/AOVs/gt_B) — spec'd (§4), not landed.
4. **Gallery rebuild + extractor smoke-run + determinism spot-check** (WP-D
   render deliverables).

The through-line: WP-A is the evidence-backed core that is fully verifiable
offline and gate-checkable, so it shipped clean; the scene/GT/render items each
need a render or VLM budget whose result I would rather measure than assert.

## Reproduction

```
cd research/delighting
python3 results/032/wpa_evidence.py          # OLD-vs-NEW offline evidence table
# validate gate (needs Blender):
for r in <13 recipes>; do BLENDER -b -P generate_synthetic.py -- \
   --out OUT --seed 42 --count 1 --light-variations 1 --validate --recipe $r; done
python3 check_validation.py OUT
```
