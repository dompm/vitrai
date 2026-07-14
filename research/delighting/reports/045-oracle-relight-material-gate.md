# 045 — Oracle relight: is the T,h material model good enough to fine-tune on?

Date: 2026-07-14. Branch `research/delighting-045-oracle-relight` (off `research/delighting`
@ `b087c46`). This is the **gate the user asked for before we commit to the Modal fine-tune**:
"evidence that our material model is good enough … a report of what reconstructed light (e.g.
on a simple uniform light box) looks like, supposing we estimated ground-truth t, h, normals, etc."

Code (new, self-contained, does not touch the trunk generator): `research/delighting/oracle45/`
— `gen_oracle45.py` (Cycles truth-scene renderer), `recon_bench_045.py` (analytic tiered
reconstructions + metrics + board), `gen045_module.py` (verbatim byte-identical copy of trunk
`generate_synthetic.py` at study start, so the forward model is exactly the shipped one).
Artifacts (committed): `results/045/oracle_relight_board.jpg` == `board_045_all.jpg` (12 family
strips), `results/045/oracle_relight_metrics.json` == `oracle_relight_metrics_all12.json`
(per-sample + family_agg). Raw renders live in `oracle45_data/` (gitignored — ~115 MB of EXRs,
deterministically regenerable from the committed seeds+code). Renders: Blender 5.0.1, Metal GPU,
1024², 64 spp, denoised; marks/shadows/frame/specular off (dataset defaults), **bump on** (relief
is one of the effects under study). No PR — the report + board are the deliverable.

## 0. TL;DR

- **Verdict: T,h is NOT sufficient. Add one term — σ_s, haze-driven subsurface scatter — to
  the material target before the fine-tune. Relief-lensing and veil are NOT worth adding for
  the backlit relight.** σ_s is the single dominant missing physical term; adding it closes
  66–92% of the structured-light reconstruction gap and *solves* 5 of 7 glass families
  (residual MAE 1–2 / 8-bit, SSIM > 0.995). See §2.
- **The uniform lightbox is a trap — do not gate on it.** Under a flat backlight the current
  model reduces analytically to L = T (measured, not assumed: `uniform_L0_equals_T` MAE
  ≈ 1–3 × 10⁻⁴ linear on all 12 samples), so **every tier scores an identical ~1–4 MAE and
  the model's deficiency is completely invisible.** You cannot distinguish transmission from
  scatter under light that carries no spatial structure. We therefore pair the lightbox with a
  **structured (checker) backdrop**, which is what exposes the gap. §1.
- **Structured backdrop, current (T,h) model, per family (8-bit MAE ↓ / SSIM ↑):**

  | family (n) | t0 current (T,h) | +σ_s scatter | +relief lensing | +veil | σ_s gap-closure |
  |---|---|---|---|---|---|
  | cathedral (2) | 38.0 / 0.747 | **12.9 / 0.866** | 12.8 / 0.866 | 12.8 | 66% |
  | baroque/fracture/confetti (3) | 36.7 / 0.857 | **10.2 / 0.988** | 10.2 / 0.988 | 10.2 | 72% |
  | ring-mottle (1) | 19.3 / 0.906 | **1.6 / 0.999** | 1.4 / 0.999 | 1.4 | 92% |
  | streaky (2) | 15.4 / 0.924 | **2.2 / 0.996** | 2.2 / 0.996 | 2.2 | 85% |
  | wispy (1) | 14.4 / 0.937 | **1.3 / 0.9997** | 1.3 / 0.9997 | 1.3 | 91% |
  | dark (2) | 11.4 / 0.929 | **1.0 / 0.995** | 1.0 / 0.995 | 1.0 | 91% |
  | saturated-opalescent (1) | 11.0 / 0.953 | **1.8 / 0.9997** | 1.7 / 0.9997 | 1.7 | 83% |

- **σ_s scatter does essentially all the work.** For everything except cathedral and
  baroque/fracture/confetti, blurring the backdrop by σ ∝ h drives the residual to the noise
  floor. This is the term the current model is missing and the one to bake into the target.
- **Relief lensing is marginal here — do not prioritize it.** A ground-truth single-interface
  Snell warp of the backdrop (IOR 1.5, from the exact height field the Bump node consumed,
  gain oracle-fit) improves MAE by **< 0.15 over scatter for every family** (cathedral
  12.89 → 12.83). The oracle-fit gain even flips sign across samples (−4, −2, −1, +6, +8),
  i.e. it is fitting noise, not a coherent refraction signal, at the checker scale we probe. §3.
- **Veil is a no-op in a backlit rig — confirmed, and worth stating plainly.** The veil tier
  adds the front-surface Glossy AOV; in a black room lit only from behind there is no front
  illumination to reflect, so `veil_mean_linear ≡ 0` on **all 12 samples, opal included**
  (wispy, saturated-opalescent). t3 == t2 everywhere. Opalescent "milkiness" is transmitted
  subsurface scatter (the σ_s term), not a front-surface veil. §4.
- **Honest limitation — two families are not fully solved.** cathedral (12.8) and
  baroque/fracture/confetti (10.2) retain a real residual after every tier: high-transmission,
  relief-textured glass whose backdrop is genuinely *refracted* (not just scattered), and
  isotropic σ ∝ h scatter plus our single-interface warp don't reconstruct that structure. If
  we later want these families tight, the missing physics is anisotropic/relief-coupled
  refraction, not scatter. It does not block the fine-tune (see §5). §3, §5.

## 1. The uniform lightbox hides the gap; the structured backdrop reveals it

Each authored sheet is rendered in two black-room scenes with an identical straight-on camera:
a **uniform** emissive white backlight, and a **structured** backlight carrying a two-tone
checker (0.2 m squares, warm-white / cool-dark). The reconstructions are scored against the
Cycles truth in both.

Under the uniform backlight the shipped compositing model
`L = T·(h·⟨B⟩ + (1−h)·B)` collapses: B is spatially flat, so `⟨B⟩ = B` and `L = T·B`, i.e.
just the transmission map lit by a constant — **h drops out of the image entirely.** The bench
measures this directly: `uniform_L0_equals_T` (‖L₀ − T‖, linear) is 1–3 × 10⁻⁴ across all 12
samples, at the validate-gate noise level. Consequently every model tier scores the same under
uniform light (columns 1–3 of the board are visually identical flat fields, MAE 1.0–3.6), and
**a "reconstructed uniform lightbox" — exactly the demo originally proposed — would look
perfect for a model that is in fact missing a first-order term.** That is the trap: it is the
one lighting condition under which T,h is provably indistinguishable from any richer model.

The structured backdrop removes the degeneracy. Now B has edges, and how the sheet *redistributes*
those edges (scatter, refraction) becomes visible. Board column 4 (TRUTH structured) shows the
checker softened/rippled by the glass; column 5 (current T,h) shows a **razor-sharp** checker,
because the current model transmits the background pixel-for-pixel (haze only cross-fades toward
the mean, it never blurs). That sharp-vs-soft mismatch is the entire t0 error, MAE 11–38.

## 2. σ_s scatter is the dominant missing term

Tier 1 replaces the sharp background with a per-pixel variable blur, σ(x) = σ_max·h(x), σ_max
oracle-fit per sample on the structured scene. This is the MMv3-G1 scatter model. Result: the
structured MAE collapses (table in §0). Five of seven families reach MAE 1–2 with SSIM > 0.995
— indistinguishable from truth by eye (board column 6). The gap-closure fraction (66–92%) is
first-order for every family, and for the scatter-dominated glasses (opal, wispy, dark,
ring-mottle, streaky) it is essentially the whole story. The fitted σ_max saturates at the top
of the grid (256 px) for almost all samples, i.e. these glasses want *aggressive* haze-driven
diffusion — a term the current renderer has no analog for.

Physically this is unsurprising and it is the crux of the gate: haze in real glass is volumetric
/ subsurface light spreading, and the shipped model encodes haze only as a contrast-reducing
cross-fade to the mean background, with no spatial spread. The reconstruction says: give the
material model a scatter radius driven by h and the backlit appearance of most glass families is
recovered to the noise floor.

## 3. Relief lensing is marginal; two families expose its (and scatter's) limit

Tier 2 adds a physically-grounded lensing warp: the backdrop is displaced by single-interface
Snell refraction (IOR 1.5) computed from the *exact* camera-space height field the Cycles Bump
node consumed, projected to backdrop pixels through the shared camera, times an oracle-fit gain.
Despite being given ground-truth geometry, it improves structured MAE by **< 0.15 over scatter
alone for every family**, and the fit gain's sign is inconsistent across samples — the hallmark
of fitting residual noise rather than a real, coherent displacement at this checker scale. So as
a term to add to the material target, **relief lensing does not earn its place for the backlit
relight.**

The interesting exception is *where the residual remains*: cathedral (12.8) and
baroque/fracture/confetti (10.2) are the two high-transmission, relief-textured families, and
neither scatter nor our lensing closes them (board columns 6–7 still show a faint checker for
cathedral/baroque). The truth there is a genuinely *refracted* checker — the surface relief bends
the sharp backdrop into place-varying, locally-anisotropic distortion — and both an isotropic
σ ∝ h blur (which softens but cannot displace) and a single-interface small-angle warp (which
displaces but cannot capture the multi-scale relief) are the wrong shape for it. This is the one
place the material model is measurably incomplete; the missing physics is relief-coupled
refraction, not more scatter.

## 4. Veil is zero in this rig (all families, opal included)

Tier 3 adds the front-surface reflection veil (Glossy Direct+Indirect AOV). In a black room lit
only from behind, the front hemisphere is unlit, so there is nothing for a front-surface lobe to
reflect: `veil_mean_linear` is exactly 0 (or ~1e-9) on all 12 samples, wispy and
saturated-opalescent included, and t3 is identical to t2 throughout. We rendered and scored it
anyway, for honesty and to answer the specific question of whether opalescent milkiness needs a
veil term — it does not. Opal appearance is carried by transmitted subsurface scatter (§2), which
is why saturated-opalescent goes 11.0 → 1.8 on the *scatter* tier. Veil would only matter under
front/ambient illumination, which is not the backlit relight scenario this gate is about.

## 5. Verdict for the fine-tune

**Yes, proceed with the fine-tune — and extend the material target from (T, h) to (T, h, σ_s).**
The evidence the user asked for: given ground-truth material maps, the *forward model* — not an
estimator, the ceiling of what the material representation itself can express — reconstructs
backlit glass to MAE 1–2 / SSIM > 0.995 for 5 of 7 families **once σ_s scatter is included**,
and hides all of its own deficiency under a uniform lightbox. So:

- **σ_s (haze-driven scatter radius) is a required addition.** It is first-order for every
  family and decisive for opal/wispy/dark/ring-mottle/streaky. Without it, structured-light
  reconstruction is off by 11–38 MAE; with it, most families are solved. This is the headline
  material-model implication.
- **Relief-lensing and veil are not needed** for the backlit target — lensing is < 0.15 MAE
  and veil is identically zero. Do not spend fine-tune capacity predicting normals-for-lensing
  or a veil channel on the strength of this study.
- **Known residual (does not block):** cathedral and baroque/fracture/confetti keep ~10–13 MAE
  from relief refraction that (T, h, σ_s) cannot express. These remain the hardest families and
  are the natural next target if we later want them tight; the fix is refraction physics, not
  the training run. Flagging as a limitation rather than a blocker.

Reproduction: `research/delighting/oracle45/`; render with
`<blender> -b -P gen_oracle45.py -- --out oracle45_data --samples <recipe:seed,...> --res 1024`
then `.venv/bin/python recon_bench_045.py --data oracle45_data --out ../results/045`. Twelve
samples: cathedral-green:6001, cathedral-amber:6002, streaky-mix:6001, streaky-fine-texture:6002,
wispy-white:6001, saturated-opalescent:6001, ring-mottle:6001, dark-ruby:6001, dark-textured:6002,
baroque-rolling-wave:6001, confetti-shard:6002, fracture-streamer:6003.
