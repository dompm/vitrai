# 054 — The relief-refraction residual: four cheap operators killed, mechanism localized

Date: 2026-07-16/17 (lead's own study, run directly — not delegated). Branch
`research/delighting-054-relief-lensing` off trunk 5cc53f6. Data: the restored
oracle-045 truth renders (`~/Documents/vitrai-datasets/oracle45_data`, Drive-backed).
Code: `oracle45/relief_lens_054.py` (main tier + board), `t2c_054.py`, `t3s2_054.py`,
`diag054.py`, `localcorr054.py`, `dirfield054.py`. Metrics/boards in `results/054/`.

**The question (CTO: "I really want to nail the material model"):** cathedral and
baroque/fracture/confetti keep a ~8–13 MAE structured-light residual that survived
045 (analytic warp), 046 (browser mip-blur ≡ ideal), and 047 (3-D normal-mapped
refraction = glitter). Can any cheap image-space operator on (T, h, height, B) —
the class a browser preview could ship — close it?

## 0. TL;DR

**No. Four operator families, each given ORACLE maps and oracle-fit parameters,
all fail — and the diagnostics localize why: the residual is genuine rough-surface
light transport (a per-pixel GGX lobe integrating the structured backlight around
a bump-tilted axis), which does not factor into any warp + blur + pointwise/
first-order-shading composition.** The 2-D preview keeps the residual honestly;
closing it belongs to (a) the learned model's decoder, which can fit the operator
class no closed form reaches, and/or (b) real 3-D shading (the three.js scene's
normal-mapped lobe against an environment — the 047 demo already does a
qualitative version of exactly this mechanism).

Pre-registered verdicts (§1, set before any number): cathedral < 6 = extend the
material target; ≥ 11 = kill. Measured: **12.70 — kill.**

## 1. Pre-registration

Before running: hypothesis was that 045-t2 failed for two fixable reasons —
full-band displacement (fine relief belongs to σ_s, not a warp) and sequential
fitting (σ fixed before gain). Operator t2b: displacement from
∇(G_σℓ·height) with JOINT (σℓ, α, σ_max) search. Verdicts: cathedral struct MAE
< 6 → adopt φ-channel; 6–9 → partial; ≥ 11 → kill. Also required: coherent α
across samples. streaky-mix included as a solved-family do-no-harm control.

## 2. Kills (all struct scene, all oracle-fit; baselines reproduced with 045's own code)

| sample | t1 σ-only | t2 (045 full-band) | t2b scale-split | t2c warp-after-blur | t3s shading |
|---|---:|---:|---:|---:|---:|
| cathedral-green | 12.72 | 12.63 (gain −4) | **12.72 (α=0)** | 12.70 (α=−2) | 12.72 (γ=0) |
| cathedral-amber | 13.07 | 13.06 (gain +8) | 13.07 (α=0) | 13.03 (α=−2) | 13.07 (γ=0) |
| baroque-rolling-wave | 11.02 | 11.02 (0) | 11.02 (α=0) | 10.95 (α=−4) | 11.02 (γ=0) |
| confetti-shard | 11.46 | 11.41 (−1) | 11.46 (α=0) | 11.46 (α=−2) | 11.46 (γ=0) |
| fracture-streamer | 8.26 | 8.22 (+6) | 8.26 (α=0) | 8.24 (α=−8) | 8.26 (γ=0) |
| streaky-mix (control) | 3.03 | 3.03 (−1) | 3.03 (α=0) | 3.02 (+4) | 3.03 (γ=0) |

1. **t2b scale-split potential lensing: killed at the search level** — the joint
   optimizer chooses α = 0 on every sample; no smoothing band makes displacement
   help. My own pre-registered hypothesis is falsified.
2. **t2c warp-AFTER-blur** (each point samples the diffused backdrop at its
   normal-shifted direction — the linearization that produces relief-scale
   modulation): ≤ 0.07 MAE gain. One genuinely new signal: **α is coherently
   NEGATIVE across all five relief families** — the first non-flipping fit in
   three studies — but the magnitude is noise-level.
3. **t3s illumination-aligned shading** `L·(1+γ·(∇height·d))`, d = unit
   ∇(G_bs·B), bs ∈ {8,16,32,64,128,256}, standardized: γ = 0 chosen everywhere.
4. σ_max saturates the 045 grid (256) and extending to 512 doesn't move MAE —
   the Gaussian family itself isn't the binding constraint at this error level.

## 3. Diagnostics — what the residual actually is

(`diag054_*.jpg`, `localcorr054.py`, `dirfield_cathedral.jpg`)

- **Multiplicative and strong**: log-ratio (truth / best-σ recon) std ≈ 0.19–0.22
  on the residual families. Visually: the truth keeps high relief-scale contrast
  while the checker is diffused; the recon is a flat wash. The missing appearance
  is "the relief texture, shaded", not "the checker, displaced".
- **Pointwise-decorrelated globally**: corr(log-ratio, {height, ∇height, |∇h|,
  curvature}) ≈ 0.00–0.04. No pointwise function of geometry explains it.
- **Strongly aligned locally**: per-64px-tile regression of log-ratio on
  (∂x h, ∂y h): mean best-fit corr **0.54 (cathedral) / 0.56 (baroque)**,
  p90 0.78–0.93 — vs **0.26** on the streaky control. The residual IS
  slope-driven; the *direction* of the driving rotates across the image.
- **The direction field is organized at the checker-cell scale**
  (`dirfield_cathedral.jpg`: fitted per-tile directions rendered over B) — not
  radial from the camera. Mechanism: per-pixel illumination direction from the
  structured backlight shades the bump-tilted transmission lobe. But §2.3 shows
  a single global gain on any ∇(G·B)-derived direction fails: the true term's
  local amplitude/sign depends on the lobe-vs-cell geometry in a way no
  first-order closed form we tested expresses.

## 4. Conclusion & recommendations

- **The residual is irreducible within the cheap-operator class** (warp ∘ blur ∘
  pointwise/first-order shading), even with oracle maps and oracle fitting. It is
  the image of a per-pixel rough-lobe hemisphere integral — Cycles' actual
  computation — and resists separation.
- **For the product**: keep the honest residual in the 2-D compositing preview —
  it affects clear relief-textured families where 047 showed the ORBITABLE 3-D
  scene carries the perceptual load anyway; and note that three.js's own
  normal-mapped shading against an environment IS the qualitative version of the
  mechanism identified here (047's "sparkle" = this term, coarsely). No new
  estimated map is warranted: everything the term needs (normal/height, B) is
  already present at render time; what's missing is transport, not material.
- **For the learned model**: this is now a precise argument for letting the
  DECODER learn the residual operator — a small network conditioned on
  (∇height, a blur pyramid of B) can express locally-varying amplitude/sign
  where closed forms cannot. If we ever chase these last ~10 MAE, that is the
  path (or SH/probe-lit normal shading in the renderer), NOT more analytic tiers.
- **Material target unchanged: (T, σ_s) + presentation-layer relief** (050/047
  architecture). The φ-channel proposal is withdrawn — killed by its own
  pre-registered test.

## 5. Reproduction

Restore truth data (`rclone copy gdrive:vitrai-lab-backup/oracle45_data ...`),
then: `python oracle45/relief_lens_054.py` (t2b + board), `t2c_054.py`,
`t3s2_054.py`, `localcorr054.py`, `dirfield054.py`. All analytic — no Blender.
