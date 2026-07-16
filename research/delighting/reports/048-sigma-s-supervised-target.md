# 048 — σ_s as a supervised material channel: (T, h) → (T, h, σ_s)

Date: 2026-07-16. Branch `research/delighting-048-sigma-target` (off `research/delighting`
@ `525e3fd`). Implements the oracle-045 gate verdict (§5): **extend the material target from
(T, h) to (T, h, σ_s)** — σ_s being the haze-driven subsurface-scatter radius that report 045
proved is the dominant missing physical term (closes 66–92 % of the structured-light
reconstruction gap, solves 5 of 7 glass families). This report wires σ_s through the two halves
of the pipeline (dataset emission + fine-tune supervision) and validates the report-043
decomposition contract on all 12 oracle-045 recipe families.

Code (committed): `foundation/{dataset,backbone,train}.py` (the training-side extension —
the substantive change), `results/048/verify_sigma_target.py` (decomposition validator + board),
`results/048/gen048_blender.py` (Blender/scipy generation shim), `results/048/render_all12.sh`.
Artifacts (committed): `results/048/sigma_target_board.jpg` (12-family σ_s/a_glow/h/T board),
`results/048/sigma_target_metrics.json` (authoring contract), `results/048/sigma_target_ondisk_metrics.json`
(rendered round-trip), `results/048/smoke/train_log.json` (loop smoke). Raw renders live in
`results/048/gen_data/` (gitignored — regenerable from the seeds+code). **No Modal / payment
touched.** No long training run — a tiny-backbone MPS smoke only.

## 0. TL;DR

- **The dataset half was already done — by report 043, not this report.** The trunk generator
  (`generate_synthetic.py`) already authors `decompose_haze(h, recipe) → (σ_s, a_glow)`, re-derives
  `h = a_glow + (1−a_glow)·σ_s` (`project_h`), and emits `gt_sigma_s` + `gt_a_glow` PNG/EXR on the
  byte-identical encode path as `gt_h`, unconditionally (no flag). I **verified** this end-to-end
  rather than re-implementing it — the honest statement is that scope item 1 was a no-op on landing,
  and I say so plainly. §1.
- **The training half was the real gap and is this report's substantive change.** The fine-tune
  pipeline (`foundation/`, the paused gate2/pilot LoRA work) supervised only (T, h, B, shadow, mark,
  conf) — σ_s was authored on disk but never loaded or supervised. I extended all three files so the
  target is now (T, h, σ_s, …): the loader reads `gt_sigma_s` (gated by `has_sigma_s` for
  backward-compat with pre-043 batches), the model emits a σ_s head (AuxHead 7→8 channels, sigmoid to
  [0,1] like h), and the loss adds a valid-masked L1 σ_s term weighted co-equal with h (2.0). §2.
- **Decomposition contract holds on all 12 families (authoring, exact).** `project_h(σ_s, a_glow)`
  reproduces the emitted h with residual **0.0** on every family; `a_glow` is nonzero on **exactly
  the two opal families** (wispy-white max 0.333, saturated-opalescent 0.210) and **identically zero
  on all 10 non-opal**; ranges sane (σ_s ∈ [0, 0.92 clip], a_glow ≤ 0.35, h ∈ [0, 0.95]). §3, board.
- **Identity survives the render+encode round-trip.** Re-derived on the generator's rendered
  `gt_*` PNGs, `h = a_glow + (1−a_glow)·σ_s` holds to residual **0.0 on the 10 non-opal families**
  (there σ_s ≡ h ≡ the same authored array → bit-identical renders) and **mean 1.0e-4 on the two
  opal families (wispy-white 1.48e-4, saturated-opalescent 5.67e-5; max 5.1e-2)** (three distinct arrays through three independent sRGB-shaped encodes — the
  first place the round-trip is a real test, matching report 043's ~1.4e-4 regime). §3.
- **Training smoke is green.** The tiny-backbone MPS loop runs end-to-end over all 12 families with
  the new channel: the σ_s loss term is live (nonzero, backpropagating through the 8-channel head),
  total loss trends down early, adapter saves. It is a wiring smoke, not convergence. §4.
- **Honest scope limits:** (a) the authoring identity is 0 *by construction* (h is *defined* as
  `project_h`), so it is a consistency check, not independent evidence — the round-trip and the opal
  residual are the load-bearing numbers; (b) `decompose_haze` is still report 043's first-pass
  per-recipe split, NOT the corpus regrounding of (σ_s, a_glow) that MATERIAL_MODEL_V3 owes; (c)
  `eval_foundation.py` scores T/h/conf but not yet σ_s — plumbing the target was the deliverable,
  scoring it is the flagged follow-up. §5.

## 1. Dataset half — already landed (report 043), verified not rebuilt

Scope item 1 asked to "extend the synthetic generator so every sample also emits ground-truth σ_s
and a_glow." Reading the trunk generator, this was already true as of report 043 (MMv3-G1):

- `decompose_haze(h, recipe)` (`generate_synthetic.py:96`) — non-opal: `σ_s = h`, `a_glow = 0`
  (byte-equivalent to the CTO-approved (T,h) look); opal: `σ_s = clip(1.15·h, 0, 0.92)`,
  `a_glow = clip(0.35·h, 0, 0.35)`.
- `project_h(σ_s, a_glow)` (`:124`) re-derives `h = clip(a_glow + (1−a_glow)·σ_s, 0, 1)` — the
  OUTPUT_CONTRACT §0 compatibility projection, so existing (T, h) consumers keep working.
- `author_glass_arrays` returns σ_s/a_glow (`:1442`); `create_glass_textures` encodes
  `tex_sigma_s.png`/`tex_a_glow.png` (`:1465`); `render_ground_truths` appends `gt_sigma_s`/
  `gt_a_glow` to the GT channel list and writes each as `.exr` (32-bit) + `.png` (16-bit) on the
  same emission-passthrough path as `gt_h` (`:2209`), **unconditionally** — no CLI flag gates it.

So there was no generator code to write. I verified the behaviour two ways (§3): headless authoring
of all 12 families (bpy stubbed — the authoring path is pure numpy/scipy, `:1028` "no bpy state
touched"), and a real Blender render of all 12 families whose on-disk `gt_sigma_s.png` I read back.
**Reporting this as pre-existing rather than claiming it as new work.**

## 2. Training half — the substantive change (`foundation/`)

The Bet-2 fine-tune (`foundation/`, report 038; paused pending the material-gate decision this
report closes) is a LoRA-adapted latent-diffusion dense predictor: a frozen VAE decodes T, and a
small trainable `AuxHead` emits the remaining tier-1 channels. It supervised
`AUX_CHANNELS = (h, B, shadow, mark, conf)` — **σ_s was on disk but invisible to training.** Three
edits make (T, h, σ_s) the target:

**`backbone.py`** — `AUX_CHANNELS = (h, σ_s, B, shadow, mark, conf)`, `AUX_DIMS[σ_s]=1`, so
`AUX_TOTAL 7→8` (the AuxHead's final 1×1 conv gains one output channel). In `forward`, σ_s is
sigmoid-activated to [0,1] exactly like h (it is an authored-linear [0,1] scalar). *Consequence,
flagged:* the head's output width changed, so a previously-saved 7-channel adapter no longer
supplies `aux.out` weights — `load_adapter(strict=False)` reinitialises them. This is correct for a
paused/never-shipped adapter (training resumes fresh on the new target); it is not a silent break.

**`dataset.py`** — `_load_gt_sigma_s()` reads `gt_sigma_s.png`/`.exr` and `srgb_to_lin`-decodes it,
byte-for-byte the same path as `_load_gt_h` (the generator encodes both identically). Threaded
through `_components` / `load_full` / `sample_crop` with a **`has_sigma_s` flag**: pre-043 renders
(render_022/037) that lack the file load fine with σ_s zero-filled and `has_sigma_s=False`, so no old
batch crashes and none contributes a spurious zero-σ_s gradient.

**`train.py`** — `collate` stacks σ_s and `has_sigma_s`; `compute_losses` adds
`l_sigma_s = masked_L1(out[σ_s], batch[σ_s])` over `valid · has_sigma_s` (the mask mirrors `has_B`,
so the term is inert on σ_s-less data); weight `w[σ_s]=2.0`, co-equal with h per the gate's
first-order finding. Loss dict + log line surface `ss=`. `modal_app.py` imports `train_loop`
unchanged — the Modal entrypoint inherits the new channel with **zero Modal edits** (untouched).

## 3. Validation — the decomposition contract, 12 families

`results/048/verify_sigma_target.py` checks two levels.

**(A) Authoring (exact, all 12).** For each family it authors (T, h, σ_s, a_glow), recomputes
`h_proj = project_h(σ_s, a_glow)`, and asserts the contract:

| check | result |
|---|---|
| `|h_proj − h|` max over families | **0.0** |
| a_glow nonzero ⟺ opal | wispy-white (0.333), saturated-opalescent (0.210); **0.000 on all 10 non-opal** |
| σ_s range | [0, 0.92] (opal clip binds), spatially varying on streaky/wispy, flat on cathedral/dark/ring/baroque/confetti/fracture |
| h range | [0, 0.95] |
| all_ok | **12/12** |

The board `results/048/sigma_target_board.jpg` shows, per family, `T | σ_s | a_glow | h | h_proj`:
the h and h_proj columns are visually identical (residual 0), a_glow is black for every non-opal
family and lifts only for the two opal sheets, and σ_s ≈ h for non-opal (a_glow=0 ⇒ h_proj = σ_s)
while for opal h sits slightly above σ_s by exactly the a_glow term.

*This level is exact by construction* — the generator *defines* the emitted h as `project_h`, so a
0.0 residual confirms the code is internally consistent but is not independent physical evidence.
The independent test is level B.

**(B) Rendered round-trip.** I rendered all 12 families through the real generator (Blender 5.0.1,
`--validate` uniform backlight ⇒ no HDRI needed) and re-derived `h = a_glow + (1−a_glow)·σ_s` from
the encoded `gt_*.png`:

- **10 non-opal families: residual 0.0.** There `a_glow ≡ 0` and `σ_s = h.copy()`, so gt_σ_s and
  gt_h are renders of the *same* array through the *same* encode — bit-identical, and the identity is
  trivially exact.
- **2 opal families: residual mean 1.0e-4** (wispy-white 1.48e-4, saturated-opalescent 5.67e-5; per-family max 4.6–5.1e-2) (`sigma_target_ondisk_metrics.json`). This is the
  only regime where the identity is a genuine test — gt_h, gt_σ_s, gt_a_glow are three *different*
  authored arrays each independently emission-rendered and sRGB-shaped-16-bit-encoded, so the residual
  measures whether the projection survives three separate round-trips. It lands in report 043's
  measured ~1.4e-4 regime, i.e. the decomposition is render-pipeline-stable.

(One documented round-trip artefact, not an identity failure: high σ_s values inflate slightly under
the sRGB-shaped encode — streaky-mix authored σ_s max 0.92 reads back 0.98 — the report-025 encode
shaping; it cancels in the non-opal identity because σ_s and h share it.)

## 4. Training smoke (loop only, no long run)

`foundation/train.py --smoke` (backbone=tiny, no download, MPS, on the rendered gen_data,
`results/048/smoke/train_log.json`): the loop runs end-to-end over all 12 rendered families
(all train-split; seeds 6001–6003 %5≠0) with the extended target — 110.5 k trainable params
(LoRA + the now-8-channel AuxHead), the new σ_s loss term is nonzero and backpropagates, total loss
trends down early (4.15 → 3.86 over the first 10 steps), and the adapter serialises. This is a
**plumbing smoke, not convergence**: at 20 steps on a random-init tiny backbone (bs 2, cosine LR) the
per-channel curves are noise — σ_s here even drifts up 0.25 → 0.40 — so the claim is only that the
(T, h, σ_s) target trains without shape/wiring errors and the σ_s gradient flows. It does NOT claim
σ_s is *learned well*; that is the resumed Modal run this gate unblocks, explicitly out of scope here.
The 12-family set includes the two opal sheets where σ_s and h genuinely differ (a_glow lift), so the
head has a target distinct from h to fit — not a degenerate σ_s ≡ h copy.

## 5. What did NOT get done / honest limitations

- **Authoring identity is 0 by construction**, not independent validation (§3A). The load-bearing
  numbers are the opal round-trip residual (§3B) and the smoke (§4).
- **(σ_s, a_glow) is still the report-043 first-pass decomposition**, grounded on the existing
  per-recipe h calibration — NOT the corpus regrounding against real scatter statistics that
  MATERIAL_MODEL_V3 requires before the channels are *trusted* (043 §1 flagged this; it remains owed).
  This report wires the channel through supervision; it does not re-ground its physics.
- **`eval_foundation.py` does not score σ_s yet** — it evaluates T/h/conf (family-1..4 metrics). The
  target-channel plumbing was the deliverable; adding a σ_s MAE/relight metric to the eval harness is
  the natural follow-up so the resumed run can be scored on the new channel.
- **a_glow is intentionally NOT a fine-tune target.** Per gate §5 the target is (T, h, σ_s); a_glow
  stays generator-side, recoverable from (h, σ_s) via the projection where needed. If a future opal
  study wants it predicted, it is a one-line AUX_CHANNELS addition mirroring σ_s.
- **Render cost.** Blender's bundled Python lacks scipy and the app bundle is read-only + ignores
  PYTHONPATH; the `gen048_blender.py` shim injects an isolated scipy onto `sys.path`. Full-quality
  validate renders are ~1–2 min/sample; the 12-family set is sequential (one-Blender machine rule).

## 6. Reproduction

```
# authoring contract + board (venv with numpy/scipy/cv2, bpy stubbed):
<venv>/python results/048/verify_sigma_target.py

# rendered round-trip (Blender + isolated scipy):
BLPY=".../Blender.app/Contents/Resources/5.0/python/bin/python3.11"
"$BLPY" -m pip install --target=/tmp/bl_scipy_pkg --no-deps --only-binary=:all: scipy==1.13.1
bash results/048/render_all12.sh                                   # -> results/048/gen_data/
<venv>/python results/048/verify_sigma_target.py --ondisk results/048/gen_data

# training loop smoke (torch venv, tiny backbone, no cloud/download):
~/Documents/fastbook/.venv/bin/python foundation/train.py --smoke \
    --data results/048/gen_data --out results/048/smoke --steps 12
```
