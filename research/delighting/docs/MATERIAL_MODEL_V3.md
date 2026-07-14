# Material Model v3 — a richer forward model for the generator + renderer

Companion to `../reports/027-fresh-tracks.md`. Status: **G1 shipped, G2's veil-isolation
scene fix shipped (report 043)**; G3/G4 remain proposals. Per-gap status:

| gap | status |
|---|---|
| G1 (σ_s / a_glow split) | **shipped, report 043 item 1** — `decompose_haze`/`project_h` in `generate_synthetic.py`; σ_s drives the one transmission lobe's Roughness (real graded local blur, replaces the 037 opal-stopgap second lobe), a_glow is an independent Translucent-BSDF mix; both authored + exported as `tex_/gt_sigma_s`, `tex_/gt_a_glow`; `h` is now the OUTPUT_CONTRACT compatibility projection `a_glow+(1−a_glow)·σ_s`. First-pass decomposition grounded on the existing per-recipe h calibration — the full corpus-statistics regrounding of (σ_s, a_glow) is still owed (021/022 discipline). |
| G2 (front reflection veil) | **partially shipped** — the specular lobe + `--specular` dim-interior path landed in 032; report 043 item 2 fixed the veil-isolation scene (DarkWall 5 m → 60 m) so `gt_veil` measures genuine front-surface reflection instead of the bump-fanned HDRI leak GT_SPEC §6 documented. The authored low-frequency `r_f(x)` field + front IBL are still open. |
| G3 (refractive lensing) | proposal, not implemented |
| G4 (flash / thin-film) | proposal, not implemented |

Prioritized by what our own reports show actually caps the metrics, and by what the learned
bets in report 027 need the generator to emit as ground truth.

## Where v1/v2 stands (what the generator renders today)

From `generate_synthetic.py:create_glass_material` (read 2026-07-10):

- **`T` (transmittance)** — authored image → squared → Principled `Base Color`, `Transmission
  Weight = 1`, `IOR = 1.5` hardcoded. Physically the transmitted color. Well-calibrated
  (reports 003–023).
- **`h` (haze)** — authored image → Principled **`Roughness`** (one scalar per pixel). This is
  the *entire* scattering model. The app-side light model approximates it as a **binary mix**
  `L = T·[h·⟨B⟩ + (1−h)·B]` — glow the mean background, or show it sharp.
- **marks** — grease-pencil overlay via a mix-shader.
- **`height`/`normal` (v2)** — authored height → `ShaderNodeBump` → perturbs the *shading
  normal* only (`use_bump` toggle; off for the assembled-pair purity runs).
- **Front-surface reflection: explicitly OFF** — `Specular IOR Level = 0.0`
  (`generate_synthetic.py:665`). There is no reflected-environment veil in any render.
- No flashed/colored-base layer, no thin-film/iridescence, no true refractive displacement of
  the background.

## The measured gaps (why v3, ranked by evidence)

| # | Gap | Evidence it matters | v1/v2 state |
|---|-----|--------------------|-------------|
| G1 | Haze is a single roughness scalar with a **binary** app mix, not a spatially-varying **forward-scatter PSF** | Reports 025 (open haze-accuracy gap on dark-slate/streaky/wispy/dark-deep), 021/022 (haze is the 2nd material channel and the least-calibrated); the split easy↔hard (wispy solved, cathedral not) IS a scatter-width difference | roughness only |
| G2 | **No front-surface reflection veil** | Maintainer-named unmodeled; it is the *additive* term Bet 1's log-space split needs to exist in the data | Specular IOR Level = 0 |
| G3 | **Relief does not refract/lens the background** — bump perturbs shading normal but leaves `B` un-warped | Reports 013 §5 / 014 §4: the cathedral drag residual is transmitted **bokeh + hammer relief**, i.e. *lensed background* — the exact thing v2 bump can't produce | bump normal only |
| G4 | **No flashed / iridized / dichroic layer** | Reports 015/019/021 keep flagging Luminescent/dichroic corpus items the model can't represent (~coverage of real product lines) | absent |

## v3 forward model

The unifying change: replace the single scalar `h` with a small **thin-sheet transmission
stack**, and add the two missing light paths (front reflection, refractive lensing). The
per-pixel material state grows from `{T, h, height}` to:

```
T(x)        RGB transmitted color               (unchanged; keep the whole 003–023 calibration)
σ_s(x)      forward-scatter PSF width  (haze→kernel; replaces the roughness-only h)   [NEW: G1]
a_glow(x)   diffuse self-glow / opal opacity     (the milky term, split out of h)      [NEW: G1]
r_f(x)      front-surface Fresnel reflectance     (drives the reflected-env veil)       [NEW: G2]
height(x)   surface relief (keep)                                                       [v2]
—→ used two ways: (a) shading normal (v2 bump);  (b) refractive background displacement [NEW: G3]
flash(x)    optional 2nd colored transmittance layer (flashed glass)   [NEW: G4, class-gated]
film(x)     optional thin-film thickness for iridized/dichroic         [NEW: G4, class-gated]
```

### Forward compositing (renderer + differentiable app model)

```
B_scat(x)  = ( B ⊛ K_σs(x) )                 # background convolved with a per-pixel scatter kernel  (G1)
B_lens(x)  = warp( B_scat, ∇thickness(x) )   # thin-lens displacement of the scattered background     (G3)
T_eff(x)   = T(x) · flash(x)                  # flashed second layer (identity if absent)               (G4)
photo(x)   = r_f(x)·E_front(x)                # front-surface reflection veil (reflected environment)    (G2)
           + F_film(x)·iridescence(x)         # thin-film interference tint (identity if absent)         (G4)
           + (1 - r_f(x)) · T_eff(x) · [ a_glow(x)·⟨B⟩ + (1-a_glow(x))·B_lens(x) ]   # transmission
```

Notes:

- **G1 (headline).** The old `h` conflated two physically distinct things — *how much the
  background is blurred* (`σ_s`, a forward-scatter PSF) and *how much the glass glows on its
  own* (`a_glow`, opal opacity). Cathedral = small `σ_s`, small `a_glow` (sharp see-through);
  opal = large `σ_s`, large `a_glow` (glows, hides `B`). This directly explains the
  wispy-solved / cathedral-hard split (report 014 §4): opal already blurs `B` away, so `T·B`
  is easy; cathedral keeps `B` sharp, so it's hard. In the generator, drive `σ_s` from a
  real scatter kernel (blur `B` before it reaches the sensor) instead of Principled
  roughness; the app-side differentiable model uses a separable Gaussian of width `σ_s(x)`.
  The binary `h`-mix becomes the `σ_s→∞`/`a_glow` limit, so v1 remains a special case.
- **G2.** Turn `Specular IOR Level` back on and author a low-frequency `r_f` field; render the
  reflected front environment (a second, *front-side* IBL) so captures carry a real
  reflection veil. This is not cosmetic: **Bet 1's reflection-removal prior is trained to
  remove exactly this additive term** — without it in the data, the sim-to-real gap on real
  glare/veil is unmodeled. `r_f` is also the term the app can *suppress* at relight time.
- **G3.** Feed the height gradient into a real background **displacement** (thin-lens
  parallax), not just a shading-normal bump. This is what makes hammered/rolled cathedral
  glass *lens* the garden into bokeh discs — the report-013/014 residual. It also makes the
  assembled-pair drag test physically honest: relief-lensed background varies with capture
  geometry, which is precisely the invariance the learned track must earn.
- **G4.** Two optional, **class-gated** layers so the generator can finally cover the
  Luminescent/dichroic corpus items reports 015/019/021 keep quarantining: `flash` = a thin
  second transmittance multiply (flashed cathedral), `film` = a Belcour-style thin-film
  interference tint (iridized/dichroic). Low priority — off by default; only enable for
  recipes grounded on those product lines, and keep them out of the base color statistics.

## What v3 unlocks for the learned bets (report 027)

- **Bet 1** needs `B` rendered as an explicit ground-truth layer (for `logT`/`logB` pairs) and
  needs the additive `r_f·E_front` veil present so the prior learns to strip it. G2 + an
  explicit `gt_B` export are the minimal generator change for Bet 1's milestone-2 fine-tune.
- **Bet 2/3** consume `σ_s`, `a_glow`, `r_f` as extra output channels — a richer, more
  identifiable material state than `{T,h}` for a foundation predictor to regress, and a more
  honest differentiable renderer for the render-in-loop loss.
- The **assembled-pair instrument** (report 014) becomes a G3 test: with real lensing, the
  cathedral drag residual is *physically* attributable, so a learned method that closes it is
  provably separating background, not smoothing.

## Prioritized rollout (one change at a time — the repo's rule)

1. **G1 (σ_s / a_glow split) + explicit `gt_B` export.** Highest leverage: fixes the least-
   calibrated channel, and hands Bet 1 its supervised layers. Re-ground `σ_s`/`a_glow` against
   the corpus haze stats the same way 021/022 grounded color/texture.
2. **G2 (front-surface reflection veil).** Small node change (`Specular IOR Level` + front
   IBL); required for Bet 1's real-domain fidelity.
3. **G3 (refractive background lensing).** Bigger renderer change; makes the cathedral hard
   case physically honest and testable.
4. **G4 (flash / thin-film).** Optional, class-gated, last — coverage for dichroic/Luminescent
   product lines, kept out of base statistics.

## Honest caveats

- Every added channel is another authoring degree of freedom to ground against the real
  corpus — do **not** ship a channel until it's grounded (the 021/022 discipline), or it
  becomes invented realism (the "iridescence-painted-into-T" mistake, in reverse).
- Cycles glass is still cleaner than rolled glass (RESEARCH_STATE caveat); v3 narrows the gap
  but real matched captures remain the fidelity benchmark.
- G3 (true refraction) raises render cost and breaks the exact pixel↔UV correspondence the
  assembled-pair purity runs rely on — keep a `use_lensing=False` purity path exactly as
  `use_bump=False` exists today (report 014 §1.1).

## Material Model v3 headline

**Split the one haze scalar into a physical pair — a forward-scatter PSF `σ_s` and a
self-glow opacity `a_glow` — and add the two missing light paths the reports name as
unmodeled (a front-surface reflection veil `r_f` and true refractive background lensing from
the relief), rendering the transmitted background `B` as an explicit ground-truth layer. That
single reparameterization both explains the measured wispy-easy / cathedral-hard split as a
scatter-width difference and manufactures exactly the paired `(T, B, veil)` ground truth the
report-027 reflection-removal-mirror bet needs.**
