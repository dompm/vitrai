# Glass de-lighting — FROZEN evaluation protocol (v1.1)

Iteration 034. Branch `research/delighting-034`. Status: **FROZEN**.

> **v1.1 (2026-07-11)** — the pre-declared bump on harvest-033 completion (v1.0 §3c/§6.2;
> executed BEFORE any method was scored against the real set). All changes are in §3c: per-brand
> reserved counts pinned against the final `manifest_033.json` (254 products; the base hash rule
> reserves 55 = 21.7%); the <15% floor is computed over **eval-ELIGIBLE** products (those without
> a product-level exclusion flag — reserving a product the consumption predicate excludes anyway
> adds zero eval coverage) and topped up with eligible products only; the frozen top-up list is
> **3 product ids** (final holdout 58/254 = 22.8%); the harvest's final contamination schema is
> wired in (per-image flag LISTS, `variant_duplicate_listing`, the sixth `suspect_same_photo`
> pair screen, and the `REAL_PAIRS_DATASET.md` §9.3 consumption predicate by reference). No
> product reserved by v1.0's hash rule was removed. v1.0 is commit `7f6f1ee` for comparison.

This document is the
evaluation contract that must exist BEFORE any foundation-model training begins (the academic
consultant's weeks-1–2 deliverable, adopted by the lead with the amendments recorded inline).
Companion: `OUTPUT_CONTRACT.md` (the prediction targets), `MATERIAL_MODEL_V3.md` (the forward
model), `REAL_PAIRS_DATASET.md` (the real-pair source), `reports/034-eval-freeze.md` (what was
frozen + the baseline table this doc references).

Freeze semantics: sections 1–6 define the metrics, holdouts, baselines, and discipline. The
**real test set may not be modified after the first results are seen on it** (§6). Any change
is a versioned protocol bump (v1.1, v2.0, …) with a written justification in
`reports/`. The frozen classical extractor reference is **`extract.py` @ commit
`59813c272de67d2b5d7145aaf0ff8226f1d27ba2`** (the report-026 trunk; `--illum classical`
default is byte-identical to every report 003–026).

---

## 1. Metrics — the five families

Every future experiment reports all five families it can (a synthetic-only run skips the
real-pair family, etc.), per class family (§3d). The scalar **primary criterion** is family 1.

### 1a. THE METRIC CORRECTION — registered cross-capture consistency is primary; the drag test is a bounded diagnostic

**The catch (the review's sharpest).** Our headline "drag test" (`assembled_bench.py`, report
014) rewards LOW dispersion of a piece's mean colour as it is re-sourced from different sheet
POSITIONS. That is gameable: a method that simply **flattens** the sheet to a spatially-uniform
map trivially scores near-zero drag dispersion while having destroyed the streaks/bubbles/relief
that make glass legible. Dispersion-across-positions rewards exactly the failure mode reports
013/014/029/031 warn about. (The same gap shows up numerically in the frozen baselines: on the
synthetic cross-lighting instrument raw-copy's unscaled T-dispersion, 0.0946, is already *lower*
than the classical extractor's, 0.0932 — dispersion alone does not tell you which map is right.)

**The correction — the primary consistency criterion is redefined:**

> **SAME sheet coordinates under DIFFERENT captures → the SAME canonical material.**
> Measured as `register_pair.registered_t_agreement(T_a, T_b, valid)`: the sRGB MAE (+p95)
> between two intrinsic T maps sampled at the SAME registered coordinates. This is a
> *registered comparison* — same physical point, two lightings — not a comparison across
> different positions, so flattening does not help it (a flattened map disagrees with a
> faithful map at the same point just as much). It is `register_pair.py`'s original
> T-agreement number, now generalized and exposed as a plain callable (report 034) usable by:
> - real registered pairs (`t_agreement_from_registered_photos`, the harvest-033 Delphi pairs);
> - synthetic same-seed multi-lighting renders (`eval_cross_lighting.py`'s setting);
> - a model's two per-capture predictions of the same sheet.

**The drag test's role is redefined (not discarded).** Dispersion across drag positions stays,
but as a DIAGNOSTIC bounded BELOW by the **grain floor** = the irreducible dispersion of the
authored `gt_T` texture itself (or, on real data, the same-region texture variance). Reading:

- relit dispersion **≈ grain floor** → texture-only dragging, the product win (wispy in report 014);
- relit dispersion **well above** the floor → residual baked lighting / see-through leak (cathedral);
- relit dispersion **significantly UNDER** the floor → **FLATTENING VIOLATION — an explicit
  FAILURE flag, not a win.** A method cannot honestly be more consistent than the texture allows.
  Implemented as `assembled_bench.flatten_flag`: fires when relit dispersion <
  `(1 − 0.25)·grain_floor` on either lens (lum_cv is the trustworthy gain-invariant lens; lab_dE
  reported for context). The current classical baseline reads **all-False** (relit is above the
  floor on both materials); an over-flattened method fires it (verified, report 034).

### 1b. Texture-preservation metrics (NEW, mandatory)

The explicit counter-pressure to flattening. Implemented in `eval_texture_preservation.py`;
callable `evaluate(ref_lin, test_lin, mask)`. Two measures:

1. **Multiscale gradient preservation (MGP).** Band-pass luminance at scales σ∈{1,2,4,8}
   (difference-of-Gaussian, octave-wide); per scale report the Pearson correlation of the
   gradient-magnitude fields and the retained gradient energy `‖∇test‖/‖∇ref‖`. **Fine bands
   (σ=1,2) carry the texture that must survive; coarse bands (σ=4,8) carry the illumination
   envelope we are ALLOWED to change** — so only the fine-band correlation + retained energy are
   pass/fail. (Honest limitation: fine-band grad *correlation* is a soft discriminator — an
   8σ-blur flatten control still scores ~0.44 because a blur keeps the largest σ=2 structures;
   the **retained-energy** channel (0.03 for the blur) and **FCS** (0.0) are the sharp
   flattening detectors. Report all three; treat retained-energy and FCS as the gates.)
2. **Feature-correspondence survival (FCS).** ORB keypoints on the reference; fraction that
   still land within 6 px of a keypoint in the test map. The streak/bubble/relief-cue survival
   number (report 012's "derived from the real sheet, or invented?").

Reference signal, per data type:
- **synthetic:** reference = authored `gt_T`, test = extracted/predicted T (intrinsic-vs-intrinsic);
- **real registered pair:** reference = de-lit T of capture A, test = de-lit T of capture B at the
  same registered coordinates (texture must both survive AND agree);
- **real single capture:** reference = input photo high-frequency, test = de-lit T (texture must
  survive de-lighting — NECESSARY not sufficient: cannot tell real relief from baked see-through
  background, so a failure is decisive but a pass is not a fidelity claim).

### 1c. Controlled relight quality

Assembled-pair fidelity against a KNOWN target (`assembled_bench.py`). Two conditions:
- **uniform target (product-aligned headline, report 014b):** relight = T × known constant, no
  illuminant estimation — isolates EXTRACTION quality. Report composite-vs-RENDER-U sRGB MAE.
- **rotated-IBL target (stress test, report 014):** the honest-illuminant `<L_A>·2^ΔEV` case;
  the unmodeled HDRI-rotation colour dominates absolute error and is shared by raw and relit, so
  read it with the oracle-gain attribution ceiling, not as a raw-vs-relit discriminator.

### 1d. Failure detection (calibration)

The predicted per-pixel **confidence must predict large errors** (`OUTPUT_CONTRACT.md`). Frozen
calibration measure: bin pixels by predicted confidence and report **(i)** Spearman correlation
between confidence and the *negative* per-pixel error against reference (higher confidence ⇒
lower error), and **(ii)** the **expected calibration error (ECE)**: `Σ_b (|bin_b|/N)·|acc_b −
conf_b|` where `acc_b` is the fraction of bin-b pixels with error below a fixed threshold
(τ = 8/255 sRGB) and `conf_b` is mean predicted confidence in the bin. A method whose confidence
does not separate its own good and bad pixels is not shippable regardless of mean error, because
the app uses confidence to decide where to offer the material relight vs fall back to raw copy
(the report 015 provenance/"offer prior assistance" hook). Classical trunk emits `conf`,
`anchor_fallback`, `anchor_scale_disagree` (report 016) — those are the current confidence
signals to calibrate first.

### 1e. Artist utility (PROTOCOL PLACEHOLDER — execution deferred to the maintainer)

Blind A/B with practicing stained-glass artists; the acceptance criterion no metric captures
(reports 011/012). Procedure sketched, NOT executed this iteration:
- assemble N triples {raw-copy preview, method preview, reference} for held-out real sheets
  across the class families (§3d);
- artists rank "which reads as the same physical glass dragged into the design" and "which would
  you trust to choose glass", blind to condition and randomized order;
- report win-rate vs raw-copy with a sign test; a method must not LOSE to raw-copy on artist
  preference even where it wins on MAE (the report-014 honest-negative lesson: absolute fidelity
  and felt consistency diverge).
Execution is a maintainer task (needs real artists + real/maintainer photos, §3c); this protocol
freezes the PROCEDURE so results are comparable whenever it runs.

---

## 2. Metric families ↔ instruments (what is wired today)

| family | instrument | callable / entry | data needed |
|---|---|---|---|
| 1 registered consistency (PRIMARY) | `register_pair.py`, `eval_cross_lighting.py` | `registered_t_agreement`, `t_agreement_from_registered_photos` | registered pairs / same-seed renders |
| 1 drag diagnostic + flatten flag | `assembled_bench.py` | `drag_test` → `flatten_flag` | assembled Blender renders |
| 2 texture preservation | `eval_texture_preservation.py` | `evaluate` (MGP + FCS) | any map pair / photo+T |
| 3 controlled relight | `assembled_bench.py` | `run_uniform`, `run_material` | assembled renders (uniform + IBL) |
| 4 failure detection | (to build on the contract) | Spearman + ECE spec §1d | any run with per-pixel conf + reference |
| 5 artist utility | placeholder §1e | — (deferred) | held-out real sheets + artists |

---

## 3. Holdout rules

### 3a. Principle — hold out PHYSICAL/MATERIAL IDENTITIES, not captures

The recurring past mistake (`RESEARCH_STATE.md`, GlassNet report 009): a "held-out-lighting"
split leaves sibling lightings of the SAME material in training, so it only proves lighting
invariance, not new-sheet generalization. **The frozen rule: no crop, lighting, size variant,
sibling render, or SKU-variant photo of a test identity may appear in training.** The unit of
holdout is the physical/material identity, not the image.

### 3b. Synthetic identity-holdout list (recipe + seed families)

Recipes are the 13 current families (`generate_synthetic.py`, reports 017/022): cathedral-green,
cathedral-amber, cathedral-blue, cathedral-red, dark-opaque, dark-deep, dark-ruby, dark-slate,
dark-textured, streaky-mix, streaky-fine-texture, wispy-white, saturated-opalescent — plus any
NEW recipe added later. A synthetic **identity = (recipe, seed)**; all of its lighting/shadow/
occluder/assembled renders move together.

Frozen split rule (deterministic, seed-based, survives new-recipe additions):

> A synthetic identity `(recipe, seed)` is **TEST iff `seed % 5 == 0`**, TRAIN otherwise
> (≈20% held out). Seeds are the generator's own integer seeds. Because the split is a pure
> function of the seed, a newly generated batch is auto-partitioned with no shared list to
> maintain, and no identity can leak by being re-rendered under a new lighting into the wrong
> side. Reserved reference seeds already in the repo that are TEST under this rule (do not train
> on): the report-023 holdout batch (seeds 800–812) and any `seed % 5 == 0` render in
> render_022/render_023_holdout. **A model may never be tuned against a `seed%5==0` identity.**

### 3c. Real frozen test set

Three sources, reserved BEFORE first results:

1. **Harvest-033 Delphi products — ~20% stratified reservation.** Deterministic rule keyed on
   Delphi's `product_id` (the join key, `REAL_PAIRS_DATASET.md` §4; stored as a decimal string
   e.g. `"173738"` — confirmed with harvest-033):

   > **reserve product P as TEST iff `int(sha1(str(product_id)).hexdigest(), 16) % 5 == 0`.**

   Stratification/reporting: partition results by `brand` (the sheet-category slugs) ×
   capture-type (`{lightbox, window, shop, closeup}`, the report-030 merged taxonomy) so the
   ~20% reservation is read per stratum, not just in aggregate.

   **v1.1 — PINNED against the final `manifest_033.json`** (254 unique products, 1,491 images,
   213 raw cross-capture pairs → 145 surviving all contamination screens, across 64 products;
   `research/delighting-033`, `REAL_PAIRS_DATASET.md` §9). The base hash rule reserves
   **55/254 = 21.7%**; per brand (reserved/total): armstrong 5/13 · clear-textured 19/88 ·
   delphi-superior 0/2 · kokomo 2/17 · specialty-finish 0/7 · tiffany-today 10/42 · uro 7/30 ·
   van-gogh 8/29 · wissmach 4/26. Reserved-set capture mix: window 142, closeup 114, shop 55,
   lightbox 6, other 1; 13 of the 64 pair-bearing products land in the base holdout.

   **v1.1 top-up (the <15% floor).** The floor is computed over **eval-ELIGIBLE** products —
   those without a product-level exclusion flag (`non_transmissive_mirror`,
   `multi_sheet_listing`), since an excluded product can never appear in the eval and reserving
   it adds no coverage. Brands under the eligible floor: delphi-superior 0/2, kokomo 2/17,
   specialty-finish 0/4-eligible. Frozen top-up = the next-lowest-hash unreserved ELIGIBLE
   products until ≥15%:

   > **`239270`** (delphi-superior, Bell Pepper Opal) · **`203533`** (kokomo, Dark Purple
   > Light Seedy) · **`220043`** (specialty-finish, MLW Indian Hand-Stained).

   (Cross-audited with harvest-033: all three are free of product-level EXCLUSION flags;
   239270 carries `opal_streaky_caution` so it scores sheet-identity-unverified below, and
   203533/220043 have image-level flags and no surviving registrable pairs — the top-ups
   contribute identity/statistics coverage, not pair volume. Recorded in
   `reports/034-eval-freeze.md` §7.)

   **Final frozen holdout: the 55 hash-rule products + these 3 = 58/254 = 22.8%.**

   Use-gating of reserved products (affects HOW they are scored, not WHO is reserved), per the
   harvest-033 final schema — the full load-bearing predicate is `REAL_PAIRS_DATASET.md` §9.3:
   - `finished_product_flag` pairs (gallery-tail suncatcher/mosaic) → **excluded** from all
     sheet metrics (Van Gogh screen validated: 96% recall, 0 FP);
   - per-image contamination flags are LISTS (e.g. `["line_stock_photo","product_on_white"]`,
     `contamination_033.json` products[pid].images) — any flagged image is excluded;
   - `suspect_same_photo` (`residual_mad < 15 AND inliers >= 200` on a cross_capture pair; the
     clear-glass crop-derivation leak, 16 pairs) → excluded as a registered pair;
   - `variant_duplicate_listing` (e.g. 175010/234263, one product listed twice) → the duplicates
     are ONE identity: count once, and if the hash rule ever disagrees across duplicates,
     reserve ALL of them (conservative; for 175010/234263 both land train-side, no action);
   - `opal_streaky_caution` (product-level, 31.5%) → kept but scored **sheet-identity-
     unverified** (report 030 §2.3), reported in a separate column, never used as a
     registered-consistency positive.

   Known reserved-set biases to weigh when reading results (`REAL_PAIRS_DATASET.md` §9.4):
   surviving pairs are brand-skewed (uro + tiffany-today + clear-textured = 92%), lightbox
   references are near-absent (1.8% of images), and the three top-up products come from brands
   that contribute few or no surviving registrable pairs — they buy identity coverage for
   texture/statistics work, not pair volume.

2. **Tutorial suncatcher assets** — the real backlit suncatcher photo + the two
   hammered-cathedral sheet photos + GT piece polygons (`suncatcher_bench.py`, report 013).
   Always TEST (consistency-only: mismatched glass, no absolute-fidelity ground truth).

3. **Future maintainer photos** — any matched capture the maintainer shoots (the report-013 §6 /
   014 §6 ask: shoot a sheet, cut a piece from a known region, assemble + backlight, shoot the
   result) is TEST by default. This is the only path to real absolute-fidelity ground truth;
   reserve it on arrival, never train on it.

### 3d. Report per class family

Every result table is broken out by class family so a method that wins on the easy bulk and
fails the hard case is not hidden by an average:

**cathedral (transmissive/see-through) · wispy · opalescent · dark · iridized · textured.**

(iridized and several textured varieties have zero synthetic recipe coverage today — report 031;
they exist here so real-set results and future-recipe results slot into fixed columns. Map the 13
recipes onto families via `eval_synthetic.CLASS_MAP`; real captures via the harvest-033/030
capture+title cues.)

---

## 4. Mandatory baselines (every future experiment)

No result is interpretable without the ladder beneath it. Every experiment reports, in order:

1. **raw copy** — the captured pixels, exposure-matched only (today's app);
2. **global exposure / white-balance normalization** — one global gain + WB, no spatial model;
3. **luma quotient (α=1)** — report 019's deterministic log-luminance quotient (`--illum
   quotient`); the strong non-learned normalizer every learned cleanup must beat (report 026);
4. **frozen classical extractor** — `extract.py` @ `59813c272de6…` (the reference row below);
5. **tiny GlassNet** — the report-009 class-conditioned U-Net;
6. **the new model** — reported BOTH without and with any refinement stage, so the refinement's
   contribution is separable.

A model that does not beat baselines 3 and 4 on the PRIMARY criterion (§1a) for a class family
has not earned a GO for that family, regardless of its GT-MAE.

---

## 5. FROZEN BASELINE REFERENCE ROW

Recorded on the frozen instruments over the existing synthetic sets, the report-013 suncatcher,
and the real library. Numbers are harvested from the committed result JSONs of the frozen
extractor (they ARE the current baselines' recorded values — the Blender render inputs are
gitignored and the generator is owned by iter-032, so the synthetic/assembled rows are read from
record, not re-run this iteration; see report 034 §caveats), except the **texture-preservation
row, which was re-run fresh this iteration** on the committed real images.

**Family 1 — cross-capture consistency (synthetic same-seed, T-map difference; lower = more consistent).**
Macro-avg over 13 recipes (`results/quotient_synthesis_026`, instrument 4). NB dispersion-style
metric — read with §1a's caveat (raw's low number is the flattening-analog trap, not a win):

| route | invariance_T (macro) |
|---|---|
| raw copy | 0.0946 |
| luma quotient α=1 | 0.0815 |
| **classical (frozen)** | **0.0932** |
| naive hybrid | 0.1482 |

**Family 1 — real suncatcher position-sensitivity** (`instrument 1`; dispersion of a piece across
9 sheet positions; lower = more consistent):

| route | mean dE | lum_cv |
|---|---|---|
| raw copy | 8.98 | 0.407 |
| luma quotient α=1 | 2.44 | 0.073 |
| **classical (frozen)** | **9.30** | **0.306** |

**Family 1 — drag test + flatten flag** (`results/assembled/metrics.json`, uniform target;
lum_cv gain-invariant so identical to the IBL drag):

| material (family) | raw lum_cv | relit lum_cv | grain floor | relit/floor | flatten_flag |
|---|---|---|---|---|---|
| wispy-white (wispy) | 0.141 | 0.050 | 0.027 | 1.84× | False (pass) |
| cathedral-green (cathedral) | 0.292 | 0.140 | 0.0085 | 16.5× | False (pass) |

Relit ≈ floor for wispy (texture-only dragging); cathedral stays 16× above the floor (the
see-through `T·B` residual, the north-star hard case). Neither sub-floor: no flattening.

**Family 2 — texture preservation (RE-RUN fresh, report 034).** 9 real library sheets + 2
benchmark images; T-map vs input-photo high-frequency (mode=photo); macro-avg:

| route | fine grad-corr | fine retained-energy | FCS survival |
|---|---|---|---|
| **classical (frozen)** | **0.609** | **1.27** | **0.509** |
| luma quotient α=1 | 0.707 | 1.24 | 0.589 |
| flatten control (8σ blur) | 0.44 | **0.03** | **0.00** |

The flatten control collapses retained-energy to 0.03 and FCS to 0.00 → the metric detects
over-flattening decisively (quotient preserving MORE fine texture than classical is consistent
with report 026: it removes only the smooth envelope).

**Family 3 — controlled relight, uniform target** (`results/assembled/metrics.json`; sRGB MAE,
lower better; oracle-input = extraction-only floor):

| material (family) | raw | relit | oracle-input | T-MAE vs authored |
|---|---|---|---|---|
| wispy-white (wispy) | 16.6 | **6.8** | 1.6 | 0.036 |
| cathedral-green (cathedral) | 35.6 | **26.4** | 30.3 | 0.134 |

**Family 3/GT — synthetic accuracy** (frozen classical, 13 recipes, instrument 2): macro T-MAE
**0.108**, h-MAE **0.155**. **Preview-invariance** (instrument 3, sRGB MAE): raw 29.9 / quotient
15.6 / **classical 18.2** / naive-hybrid 27.8.

**Families 4–5:** no frozen baseline yet — family 4 needs the confidence-calibration harness
(§1d, to build against `OUTPUT_CONTRACT.md`); family 5 is the deferred artist study (§1e).

---

## 6. Freeze discipline

1. The **real test set (§3c) may not be modified after the first results are seen on it.** No
   adding/removing products, re-drawing the hash split, or re-labelling reserved captures once a
   method has been scored against them.
2. Any protocol change is a **versioned bump** (this is v1.1; v1.0 = commit `7f6f1ee`): new
   version header + change log, a `reports/NNN` entry stating what changed and why, and the old
   version kept in git history for comparison. Retuning a metric, adding a class family, or any
   change to the reserved set requires a bump. (The brand-stratum top-up pre-declared in v1.0
   was executed as v1.1 on harvest-033 completion, before any method was scored on the real set —
   the holdout is now fully pinned; further changes to it need first-results-grade justification.)
3. The **frozen classical extractor** (`59813c272de6…`) is the immovable reference row; if the
   trunk extractor advances, the frozen commit stays pinned here as the comparison anchor and the
   new extractor is reported as a candidate against it, not silently swapped in.
4. Baselines §4 are mandatory, not optional — a result table missing them is not a GO-eligible
   result.
