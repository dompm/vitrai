# Output contract — material / nuisance state for the foundation-model era (v1.0)

Iteration 034. Branch `research/delighting-034`. Status: **FROZEN alongside `EVAL_PROTOCOL.md`
v1.0.** This is the consultant §3.1/§4 state contract, aligned with `MATERIAL_MODEL_V3.md`. It
defines WHAT a de-lighting model predicts and in what units — the prediction targets the frozen
metrics (`EVAL_PROTOCOL.md`) score against. Data-generation ground-truth encodings live in
`synthetic-glass-data-spec.md` (the generator brief; the "GT_SPEC" cross-reference below points
there until a dedicated GT_SPEC.md is split out).

## 0. The two-part state

A capture is modelled as a **material state M** (intrinsic to the physical glass, the thing the
app must recover and re-light consistently) plus a **nuisance state N** (everything the capture
baked in that must be removed or ignored), and a **per-pixel confidence** over M.

> **capture = f(M, N)**, where f is the `MATERIAL_MODEL_V3.md` forward compositing model.
> De-lighting = infer M and the confidence; discard/quarantine N.

Crucial framing (consultant §4, lead-amended): **the older `(T, h)` representation is a
COMPATIBILITY PROJECTION of this state, not its ceiling.** `T` carries forward unchanged (its
003–023 calibration is preserved); the single haze scalar `h` is the lossy projection of the
`(σ_s, a_glow)` pair (`MATERIAL_MODEL_V3.md` G1). A model may predict the full M and PROJECT to
`(T,h)` for today's app renderer, or predict `(T,h)` directly as a strict subset. Neither is
required to claim exact physical recoverability of every field — see §3.

## 1. Material state M (prediction targets)

Per-pixel unless noted. Encodings/units are the FROZEN prediction targets; the parenthetical maps
to `MATERIAL_MODEL_V3.md`.

| field | meaning | encoding / units | status |
|---|---|---|---|
| `T` | RGB transmitted colour | linear RGB ∈[0,1]; absolute scale anchored (report 003/009/016) | **kept, calibrated** (MMv3, unchanged) |
| `σ_s` | forward-scatter PSF width (background blur) | scalar ≥0, in px at a canonical sheet resolution (define at 700-max-dim working res); ∞-limit = fully diffuse | NEW (MMv3 G1) — replaces roughness-only h |
| `a_glow` | diffuse self-glow / opal opacity (milky term) | scalar ∈[0,1]; 0 clear, 1 fully self-lit opal | NEW (MMv3 G1) — split out of h |
| `d` | surface relief (height) | scalar height field, authored-linear units; ∇d drives both shading-normal and refractive lensing | v2 (MMv3 G3), kept |
| `r_f` | front-surface Fresnel reflectance (veil driver) | scalar ∈[0,1], low-frequency | NEW (MMv3 G2) |
| `z_m` | residual latent material code | learned vector (dim TBD by the model); captures flash/thin-film/unmodeled appearance not in the explicit fields | NEW — the escape hatch (see §3) |

Compatibility projection to today's renderer:
`T_app = T`;  `h_app = a_glow ⊕ g(σ_s)` — the binary app mix `L = T·[h·⟨B⟩+(1−h)·B]` is the
`σ_s→∞ / a_glow` limit of the MMv3 transmission term, so `h` is recovered as a monotone function
of `(σ_s, a_glow)` (exact form frozen with the app renderer, not here). `d` already feeds the v2
bump path; `r_f`, `z_m` are ignored by the current app and consumed only by the MMv3 renderer /
future relight.

## 2. Nuisance state N (removed / quarantined, not shipped as material)

| field | meaning | encoding |
|---|---|---|
| `B` | through-glass background layer | linear RGB; the explicit `gt_B` export MMv3 needs for Bet-1 `logT/logB` supervision |
| shadow / occluder masks | cast hand-shadows, frame/mullion/border occluders | per-pixel bool/soft masks (OP-1; report 010/012 territory) |
| `mark` mask | grease-pencil / paint-pen marks (incl. WHITE pen on dark glass, report 029) | soft mask; inpainted out of M |
| camera / exposure params | global exposure, white balance, vignette, shot grain/CA/DoF (report 029 camera-optics layer) | global scalars/low-D per capture |

N is what makes two captures of the same sheet differ; the PRIMARY metric (`EVAL_PROTOCOL.md`
§1a) is precisely the requirement that M be invariant to N.

## 3. What the contract does and does NOT claim

- It defines **prediction targets and their units**, not a promise of exact physical
  recoverability for every field. From a single photo, `T` and `B` are fundamentally entangled
  (`photo = T·B`, the north-star hard case); `σ_s`/`a_glow`/`r_f`/`d` are identifiable to varying
  degrees depending on capture and class. The contract says WHAT to predict and how it is
  scored, and lets the calibration family (`EVAL_PROTOCOL.md` §1d) report how confidently each
  field was actually recovered.
- **`z_m` is the honesty valve.** Appearance the explicit fields cannot represent (flashed
  glass, thin-film iridescence — MMv3 G4; anything unmodeled) goes into the residual latent
  rather than being force-fit into `T` (the "iridescence-painted-into-T" mistake, MMv3 caveats).
  A field is only promoted from `z_m` to an explicit target once it is grounded against the real
  corpus (the 021/022 discipline).
- **Every field must be grounded before it is trusted** (MMv3 honest caveats). Emitting a channel
  in this contract is not a claim it is calibrated — `T` is (003–023); `σ_s`/`a_glow`/`r_f`/`d`
  require the MMv3 rollout to ground them against corpus haze/relief/reflection statistics before
  their predictions are scored as fidelity rather than plausibility.

## 4. Per-pixel confidence (required output)

A model MUST emit a per-pixel confidence over M, and it MUST be CALIBRATED to predict its own
error (`EVAL_PROTOCOL.md` §1d: Spearman(conf, −error) + ECE at τ=8/255). The app consumes it as
the provenance signal (reports 012/015): high confidence → offer the material relight; low
confidence → fall back to raw copy / flag "invented vs measured". The frozen classical trunk's
existing `conf`, `anchor_fallback`, and `anchor_scale_disagree` (report 016) are the first
signals to calibrate under this contract; a learned model's confidence is scored the same way.

## 5. Relationship to the frozen protocol

- `T` (and its projection `h`) is scored by families 1 (consistency), 3 (relight), and GT-MAE.
- `d`, `σ_s`, `a_glow` are scored by family 2 (texture preservation) — they ARE the streak/
  bubble/relief structure that must survive de-lighting.
- `B` and the nuisance masks are scored implicitly: the PRIMARY metric passes only if they were
  removed (same coordinates, different N → same M).
- confidence is scored by family 4.
- `z_m` is not directly scored (latent); it is validated only through the reconstruction/relight
  it enables and must never leak into a scored explicit field.

Frozen with `EVAL_PROTOCOL.md` v1.0; changes are versioned bumps under the same discipline (§6
there).
