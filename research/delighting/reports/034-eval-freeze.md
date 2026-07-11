# 034 — Freezing the evaluation protocol

Date: 2026-07-10. Branch `research/delighting-034`. Deliverables: `docs/EVAL_PROTOCOL.md`
(v1.0, FROZEN), `docs/OUTPUT_CONTRACT.md` (v1.0), metric corrections implemented in
`assembled_bench.py` / `eval_texture_preservation.py` (new) / `register_pair.py`, and this
report. Implements the academic consultant's weeks-1–2 plan (adopted by the lead with
amendments), which must exist BEFORE any foundation-model training begins. **No PR.**

## 0. What was frozen

1. **The primary metric was corrected** (the review's sharpest catch). The old drag test rewards
   low dispersion of a piece's colour across DIFFERENT sheet positions — a metric a *flattening*
   method games by throwing away texture. The primary consistency criterion is now the
   **registered SAME-coordinate T-agreement**: same physical sheet point under two captures must
   de-light to the same canonical material. Flattening does not help it (a flat map disagrees
   with a faithful map at the same point just as much). The drag dispersion is retained as a
   DIAGNOSTIC, bounded below by the grain floor; **dispersion significantly under the floor is now
   an explicit FLATTENING-FAILURE flag, not a win.**
2. **Texture-preservation metrics are mandatory and new** — multiscale gradient preservation
   (MGP) + feature-correspondence survival (FCS) — the explicit counter-pressure to flattening.
3. **Holdouts hold out physical/material IDENTITIES**, not captures: synthetic `(recipe,seed)`
   with `seed%5==0`; real Delphi products with `hash(product_id)%5==0` (~20%, stratified by brand
   × capture-type) + the tutorial suncatcher + future maintainer photos. Per-class-family reporting.
4. **Five metric families** and a **mandatory baseline ladder** (raw / exposure-WB / luma-quotient
   / frozen classical `@59813c2` / tiny GlassNet / new model without+with refinement).
5. **Output contract** M={T, σ_s, a_glow, d, r_f, z_m}, N={B, shadow/occluder, mark, camera/
   exposure} + per-pixel confidence, with `(T,h)` explicitly a compatibility projection, not the
   ceiling.
6. **Freeze discipline**: the real test set cannot change after first results are seen; all
   changes are versioned protocol bumps.

The frozen classical reference is `extract.py` @ **`59813c272de67d2b5d7145aaf0ff8226f1d27ba2`**.

## 1. Metric corrections implemented (surgical)

- `assembled_bench.py`: `drag_test` now returns `flatten_flag` — fires when relit dispersion <
  0.75×grain-floor on either lens (`FLATTEN_MARGIN=0.25`). Verified: the committed baselines read
  all-False (wispy relit lum_cv 0.050 = 1.84× floor; cathedral 0.140 = 16.5× floor), and a
  synthetic over-flattened case (relit driven below the floor) fires it.
- `eval_texture_preservation.py` (new): `evaluate(ref, test, mask)` = MGP (per-scale grad-mag
  correlation + retained energy, fine bands σ=1,2 are the pass/fail signal) + FCS (ORB keypoint
  survival). Runnable frozen-baseline row on the 9 real library sheets + 2 benchmark images for
  classical and quotient, with a Gaussian-blur flatten control.
- `register_pair.py`: T-agreement extracted to `registered_t_agreement(T_a, T_b, valid)` +
  `t_agreement_from_registered_photos(...)` — the primary consistency metric as a plain callable
  for future training evals on any two aligned T maps. `main()` refactored to use it; CLI output
  unchanged.

## 2. Frozen baseline reference table

Harvested from the committed result JSONs of the frozen extractor (the synthetic/assembled/
suncatcher rows — see §4 for why they are read-from-record, not re-run) plus the
**texture-preservation row, re-run fresh this iteration**.

**Consistency — synthetic same-seed T-difference (macro/13 recipes; lower=more consistent):**
raw 0.0946 · quotient 0.0815 · **classical 0.0932** · naive-hybrid 0.1482. (Read with the §1a
caveat: raw's low number is the flattening-analog trap.)

**Consistency — suncatcher position-sensitivity (dE / lum_cv):** raw 8.98/0.407 · quotient
2.44/0.073 · **classical 9.30/0.306**.

**Drag test + flatten flag (uniform target):**

| material (family) | raw lum_cv | relit lum_cv | grain floor | relit/floor | flatten_flag |
|---|---|---|---|---|---|
| wispy-white (wispy) | 0.141 | 0.050 | 0.027 | 1.84× | False (pass) |
| cathedral-green (cathedral) | 0.292 | 0.140 | 0.0085 | 16.5× | False (pass) |

**Texture preservation (RE-RUN; 9 library + 2 benchmark real images; T vs photo hi-freq; macro):**

| route | fine grad-corr | fine retained-energy | FCS survival |
|---|---|---|---|
| **classical (frozen)** | **0.609** | **1.27** | **0.509** |
| luma quotient α=1 | 0.707 | 1.24 | 0.589 |
| flatten control (8σ blur) | 0.44 | **0.03** | **0.00** |

The flatten control collapses retained-energy→0.03 and FCS→0.00: the metric decisively catches
over-flattening. Quotient preserves more fine texture than classical (consistent with report 026).

**Controlled relight — uniform target (sRGB MAE; lower better):** wispy raw 16.6 / **relit 6.8** /
oracle-input 1.6; cathedral raw 35.6 / **relit 26.4** / oracle-input 30.3.

**Synthetic GT accuracy (frozen classical, 13 recipes):** macro T-MAE 0.108, h-MAE 0.155.
**Preview-invariance (sRGB MAE):** raw 29.9 / quotient 15.6 / **classical 18.2** / hybrid 27.8.

**Families 4 (failure detection) and 5 (artist utility): no baseline yet** — family 4 needs the
confidence-calibration harness built against the output contract; family 5 is the deferred artist
study.

## 3. Reserved real-test-set definition

- **Harvest-033 Delphi:** TEST iff `int(sha1(str(product_id)).hexdigest(),16) % 5 == 0` (~20%),
  keyed on Delphi's decimal-string `product_id` (confirmed with harvest-033). Stratify/report by
  `brand` (10 sheet-category slugs) × capture-type (`{lightbox,window,shop,closeup}`). Use gates:
  `finished_product_flag` pairs excluded from sheet metrics; `opal_streaky_caution` products kept
  but scored sheet-identity-unverified (report 030 §2.3). Manifest lands at
  `realpairs/results/manifest_033.json` on `research/delighting-033` (still writing, ~254 products,
  ~1.5–2h); the RULE is frozen now and needs no file. If harvest-033 ships an explicit reserved-id
  list, adopting it is a v1.1 bump.
- **Synthetic:** identity `(recipe,seed)` TEST iff `seed%5==0` (already-reserved: the 800–812
  report-023 holdout batch).
- **Tutorial suncatcher** assets: always TEST. **Future maintainer photos:** TEST on arrival (the
  only path to real absolute-fidelity ground truth).

## 4. What I adapted from the consultant's spec to our actual instruments (honest deltas)

1. **Synthetic/assembled/suncatcher baselines are read-from-record, not re-run.** The consultant
   asked to "run all on the current frozen baselines over the existing synthetic sets + the 030
   sample pairs." The Blender render inputs (`synthetic_data`, `render_022/023`, `assembled_data`)
   are gitignored and absent, `generate_synthetic.py` is owned by iter-032 this iteration
   (read-only coordination), and the 030 raw pair images live only in `/tmp` (never committed).
   So those rows are harvested from the committed result JSONs of the frozen extractor — which
   ARE the current baselines' recorded values — rather than regenerated. The **one row I could
   run fresh, I did**: texture preservation on the committed real library+benchmark images. Re-
   running the synthetic/assembled rows against the frozen extractor is a mechanical follow-up
   once Blender data is regenerated (no code change needed; the flag/callable are wired).
2. **Texture-preservation reference signal is capture-limited on real data.** The spec wants MGP/
   FCS "against authored GT on synthetic and registered pairs on real." Lacking synthetic GT and
   committed registered pairs this iteration, the frozen fresh run uses the single-capture variant
   (T vs the input photo's high-frequency) — a NECESSARY-not-sufficient screen (it cannot separate
   real relief from baked see-through background). The GT and registered-pair variants are
   specified and wired (`evaluate` takes any two maps) for when that data is present.
3. **MGP fine-band grad *correlation* is a soft flattening discriminator.** An 8σ-blur control
   still scores ~0.44 there (a blur keeps the largest σ=2 structures). The **retained-energy** and
   **FCS** channels are the sharp detectors (0.03 / 0.00 on the control); the protocol treats those
   two as the gates and reports grad-corr as context.
4. **Failure-detection calibration made concrete.** The consultant named "confidence must predict
   large errors" as a family without a measure; I froze **Spearman(conf, −error) + ECE at
   τ=8/255** and pointed it first at the classical trunk's existing `conf`/`anchor_fallback`/
   `anchor_scale_disagree` signals.
5. **Output-contract `(T,h)` explicitly demoted.** Per the lead's amendment, `h` is stated as the
   lossy projection of MMv3's `(σ_s, a_glow)` and the whole `(T,h)` as a compatibility projection,
   with `z_m` as the ground-before-you-promote residual latent — so the contract defines
   prediction targets/units without over-claiming exact physical recoverability.
6. **Class families use six buckets** (cathedral/wispy/opalescent/dark/iridized/textured) even
   though iridized + several textured varieties have zero synthetic coverage today (report 031) —
   frozen as fixed reporting columns so real-set and future-recipe results slot in without a
   schema change.

## 5. Open items

- **Artist study (family 5): execution deferred to the maintainer** — procedure frozen (§1e),
  needs real artists + real/maintainer photos.
- **Maintainer photos pending** — the matched sheet→cut-piece→assembled capture (report 013 §6 /
  014 §6) is the only route to real absolute-fidelity GT; reserved as TEST on arrival.
- **Family-4 calibration harness** not yet built (spec frozen; needs a run emitting per-pixel
  confidence + reference).
- **Re-run the synthetic/assembled/cross-lighting rows against the frozen extractor** once Blender
  data is regenerated, to replace the read-from-record rows with a same-session re-run (harness
  changes are already in place).
- ~~**Harvest-033 manifest finalization** — pin per-brand reserved counts and top up any brand
  landing <15% (a v1.1 bump) when the harvest completes.~~ DONE, §7 below (v1.1, 2026-07-11).

## 6. Files

- `docs/EVAL_PROTOCOL.md` — the frozen protocol (v1.0 = `7f6f1ee`; v1.1 after §7).
- `docs/OUTPUT_CONTRACT.md` — the material/nuisance state contract (v1.0, unchanged by v1.1).
- `eval_texture_preservation.py` — MGP + FCS; `--library` frozen-baseline run + `evaluate()` import.
- `assembled_bench.py` — `flatten_flag` on the drag test.
- `register_pair.py` — `registered_t_agreement` / `t_agreement_from_registered_photos` callables.
- `results/texture_preservation/texture_preservation_{classical,quotient}.json` — the fresh row.

## 7. v1.1 — the real holdout pinned (2026-07-11, harvest-033 complete)

The pre-declared bump (§5's last item; v1.0 §3c/§6.2), executed on harvest-033's completion ping
and BEFORE any method was scored against the real set. Final manifest
(`realpairs/results/manifest_033.json` on `research/delighting-033`, `REAL_PAIRS_DATASET.md`
§9.3/§9.4, commit `c36f307`): 254 unique products, 1,491 images, 213 raw cross-capture pairs →
145 surviving all screens (64 products).

**Pinned reservation (independently recomputed from the manifest; matches harvest-033's numbers
exactly).** The frozen hash rule reserves 55/254 = 21.7%: armstrong 5/13 · clear-textured 19/88 ·
delphi-superior 0/2 · kokomo 2/17 · specialty-finish 0/7 · tiffany-today 10/42 · uro 7/30 ·
van-gogh 8/29 · wissmach 4/26. Reserved-set capture mix: window 142 / closeup 114 / shop 55 /
lightbox 6 / other 1; 13 of the 64 pair-bearing products land in the base holdout.

**Top-up refinement + list.** One refinement over v1.0's sketch, with justification: the <15%
floor is computed over eval-ELIGIBLE products (no `non_transmissive_mirror` /
`multi_sheet_listing` product flag) and topped up with eligible products only — v1.0's literal
"next-lowest-hash" would have reserved mirror product 220088, which the §9.3 consumption
predicate excludes from every sheet metric: dead weight that buys no eval coverage. Frozen
top-up (next-lowest-hash unreserved eligible, until ≥15% of eligible): **239270**
(delphi-superior), **203533** (kokomo), **220043** (specialty-finish). All three are free of
product-level EXCLUSION flags (the eligibility criterion). Cross-audit nuances from
harvest-033, recorded for honest reading of what they contribute: 239270 carries
`opal_streaky_caution` (scores sheet-identity-unverified under §3c; its 2 raw cross-capture
pairs are the report-030 "bell pepper" same-photo crops — identity coverage only);
203533/220043 each carry 2-3 image-level flags (line_stock_photo/lineup gallery slots) and have
no surviving registrable pairs — statistics-only contributors.
**Final frozen holdout: 58/254 = 22.8%.** No v1.0-reserved product was removed. harvest-033
cross-verified the list and synced the dataset card to this freeze point
(`REAL_PAIRS_DATASET.md` §9.4 @ `6d6d7f5` on `research/delighting-033`, referencing `94f2d01`).

**Schema additions wired into §3c use-gating:** per-image contamination flags are LISTS;
`variant_duplicate_listing` duplicates are one identity (count once; reserve ALL if the hash
ever disagrees across duplicates — 175010/234263 both land train-side, no action);
`suspect_same_photo` (residual_mad<15 AND inliers≥200, 16 pairs — the clear-glass
crop-derivation leak) excluded as registered pairs; finished-product screen validated at 96%
recall / 0 FP on Van Gogh.

**Honest bias note carried into the protocol:** surviving pairs are heavily brand-skewed
(uro+tiffany-today+clear-textured = 92%); the three top-up products come from brands with few or
no surviving registrable pairs, so they buy identity coverage for texture/statistics work, not
pair volume; lightbox references remain near-absent (1.8%).
