# 046 — Browser-render runtime ceiling vs Cycles: does the shipping preview need path tracing?

Date: 2026-07-14. Branch `research/delighting-046-browser-renderer` (off `research/delighting`
@ `18ce521`). Follow-on to the oracle-relight material gate (report 045). **The CTO's question:**
given our current material model and GROUND-TRUTH maps (estimation error removed), how close can a
cheap, deployable, IN-BROWSER glass renderer get to the Cycles path-traced truth? If it is close,
the shipping preview does not need path tracing — a screen-space transmission shader suffices.

Code (new, self-contained): `research/delighting/render046/` — `browser_render_046.py` (numpy
mirror of the real-time shader + 12-family ceiling bench), `export_assets_046.py` (bakes each
family's maps to base64 PNGs), `build_html_046.py` (assembles the WebGL2 prototype),
`validate_browser_path.py` (browser-vs-numpy faithfulness check), `sideview_046.py` (the grazing-angle
thickness study, §5). Artifacts (committed): `results/046/render046.html` (the self-contained WebGL2
prototype), `results/046/browser_ceiling_board.jpg` (12-family strip), `results/046/sideview_thickness_board.jpg`
(the side-view thickness board), `results/046/{browser_ceiling,sideview}_metrics.json`. Inputs are oracle 045's ground-truth
renders (`oracle45_data/`, gitignored, read by absolute path). Metrics (MAE 0–255 sRGB, SSIM on
luma) are byte-identical to oracle 045's `recon_bench_045` so the two tables are directly comparable.

## 0. TL;DR

- **Verdict: a cheap in-browser screen-space transmission shader reaches the Cycles truth as well
  as the idealized analytic model does — path tracing is NOT needed for the preview.** Feeding a
  game-engine grab-pass + roughness-mip-blur + tint shader the ground-truth (T, h→σ_s) maps
  reconstructs backlit glass to the SAME ceiling oracle 045 measured with a continuous Gaussian:
  the finite-mip real-time approximation costs **≤ 0.09 MAE on every one of the 12 families
  (mean +0.007)** — i.e. nothing. Ship a screen-space transmission material (three.js
  `MeshPhysicalMaterial`), not a path tracer.
- **The real-time technique IS our material model.** σ_s haze-scatter = a spatially-varying blur of
  the backdrop behind the glass = exactly the "grab-pass + roughness-mip" trick engines already use
  for frosted glass. The mapping is 1:1; there is no gap between "what report 045 says the material
  needs" and "what a real-time shader can do."
- **Per-family browser ceiling (8-bit sRGB MAE ↓ / SSIM ↑ vs Cycles truth), scatter fitted per
  sample exactly as oracle fit σ_max:**

  | family (n) | scatter OFF (T·B) | **browser +scatter** | oracle 045 ideal Gaussian | Δ (real-time cost) |
  |---|---|---|---|---|
  | dark (2) | 27.4 | **1.07 / 0.995** | 1.0 / 0.995 | +0.07 |
  | wispy (1) | 58.7 | **1.23 / 1.000** | 1.3 / 1.000 | −0.07 |
  | ring-mottle (1) | 43.3 | **1.61 / 0.999** | 1.6 / 0.999 | +0.01 |
  | saturated-opalescent (1) | 61.1 | **1.71 / 1.000** | 1.8 / 1.000 | −0.09 |
  | streaky (2) | 53.2 | **2.20 / 0.996** | 2.2 / 0.996 | ≈0 |
  | baroque/fracture/confetti (3) | 62.4 | **10.30 / 0.988** | 10.2 / 0.988 | +0.10 |
  | cathedral (2) | 61.7 | **12.90 / 0.866** | 12.9 / 0.866 | ≈0 |

- **Same 5-of-7-families-solved split as 045.** Scatter-dominated glass (dark, wispy, ring-mottle,
  opalescent, streaky) lands at MAE 1–3 / SSIM > 0.99 — the browser render is indistinguishable
  from the path-traced truth by eye (board + prototype diff panels near-black). The two hard
  families (cathedral 12.9, baroque/fracture/confetti 10.3) keep the same refracted-checker residual
  045 flagged — a material-model gap (relief-coupled refraction), NOT a renderer gap. §3.
- **Refraction toggle is marginal → noise; veil is a no-op.** With the σ_s blur in place, adding the
  single-interface normal-tilt refraction (gain grid-searched incl. sign) improves MAE by **< 0.005
  on all 12 families** — even weaker than oracle's < 0.15, and the best gain pins to the ±grid edge
  with zero effect (fitting noise). The front veil is identically zero in a backlit rig (045 §4);
  the prototype's veil toggle *adds* error, demonstrating it belongs to a future front-lit scene. §4.
- **Thickness estimation is NOT needed for the preview, and not separable from T anyway.** The
  head-on transmittance already bakes thickness into its exponent (`gt_T = T_base^thickness(x)`), so
  the grazing-angle absorption correction is a **global** `T^(1/cos θ_r)` factor — and a per-pixel
  thickness map is *algebraically identical* to it (verified: max pixel diff 5×10⁻⁸ on the highest-
  coupling relief family). The one genuinely thickness-dependent view effect is **slab refraction
  parallax**, which only exists in a *volumetric* glass model; our flat surface-BSDF preview has none.
  So: thickness is unnecessary for the flat backlit preview and for angled *absorption*; it becomes
  necessary only if we adopt a volumetric glass model for angled/3D views (a future 047). §5.

## 1. The renderer: the real deployable technique, mirrored faithfully

The shader is the standard game-studio screen-space transmission material, implemented verbatim in
both a numpy reference (`browser_render_046.py`) and WebGL2 (`render046.html`):

1. **Grab-pass.** The "scene behind the glass" is the backdrop B (oracle's `struct_B`, the checker
   the glass sees). Sample it.
2. **σ_s scatter = a variable blur via a mip pyramid.** Build B's mip chain by repeated 2× box
   downsample — *exactly* what GPU `generateMipmap` does — then sample per-pixel with
   `textureLod(uv, LOD)`, `LOD = log₂(σ_s)`, `σ_s(x) = σ_scale·h(x)`. This is the dominant term. At
   max LOD the 1×1 mip == mean(B), so this single term reproduces the shipped app model's `h·⟨B⟩`
   mean-crossfade at the high-haze limit *without a separate term*.
3. **Tint.** Multiply by T(x) (Beer–Lambert). `L = T · scatter`.
4. **Relief refraction (toggle).** Offset the grab UV by the surface-normal tilt (single interface,
   IOR 1.5), gain grid-searched incl. sign.
5. **Front veil (toggle, OFF).** Fresnel front reflection; ~zero backlit.

**This is not an idealized continuous Gaussian** — it is the finite mip / trilinear approximation a
GPU actually runs, which is the whole point: the ceiling number below is the *real-time* ceiling,
and the gap to oracle 045's true per-σ Gaussian stack (tier t1) is the honest real-time-approximation
cost. Two correctness details that matter: (a) the mip blur must average in **linear** light, not
gamma-compressed bytes (a ~0.13 error on the high-contrast checker otherwise) — the WebGL path uses
`SRGB8_ALPHA8` textures so `generateMipmap` and sampling are hardware-linear-correct; (b) raw `gt_T`
is used as a linear multiplier per the 045/025 validate-gate identity. `validate_browser_path.py`
decodes the exact 256² PNGs the prototype embeds and reproduces the shader in numpy: the WebGL
prototype tracks the 1024² ceiling within ±0.27 MAE (mean −0.05), and the live in-page MAE readout
was confirmed against a headless-Chrome render (cathedral-green 12.43, wispy-white 1.32).

## 2. The real-time approximation is free

Fitting σ_scale per sample on the structured scene (the same grid search oracle used for σ_max) and
scoring the finite-mip render against the Cycles truth gives, per sample:

| recipe | σ_scale | scatter OFF | **browser +scatter** / SSIM | oracle t1 | Δ |
|---|---|---|---|---|---|
| dark-textured | 1024 | 32.2 | **0.99 / 0.997** | 0.9 | +0.09 |
| dark-ruby | 512 | 22.5 | **1.16 / 0.993** | 1.1 | +0.06 |
| wispy-white | 512 | 58.7 | **1.23 / 1.000** | 1.3 | −0.07 |
| streaky-fine-texture | 1024 | 50.7 | **1.47 / 0.997** | 1.4 | +0.07 |
| ring-mottle | 1024 | 43.3 | **1.61 / 0.999** | 1.6 | +0.01 |
| saturated-opalescent | 1024 | 61.1 | **1.71 / 1.000** | 1.8 | −0.09 |
| streaky-mix | 512 | 55.8 | **2.92 / 0.994** | 3.0 | −0.08 |
| fracture-streamer | 1024 | 62.3 | **8.32 / 0.994** | 8.3 | +0.02 |
| baroque-rolling-wave | 1024 | 61.5 | **11.06 / 0.986** | 11.0 | +0.06 |
| confetti-shard | 1024 | 63.3 | **11.52 / 0.984** | 11.5 | +0.02 |
| cathedral-green | 1024 | 60.3 | **12.72 / 0.832** | 12.7 | +0.02 |
| cathedral-amber | 1024 | 63.1 | **13.08 / 0.899** | 13.1 | −0.02 |

**Δ (browser mip-scatter − oracle ideal Gaussian): mean +0.007, abs-max 0.09 MAE.** The finite mip
pyramid and the continuous Gaussian are indistinguishable at these scales. Two reasons it comes out
this clean: the fitted blur saturates near the top of the pyramid for almost every family (σ_scale
512–1024, i.e. the glass wants aggressive diffusion — the same saturation oracle saw at σ_max=256 on
its grid), and trilinear-between-mip-levels is a perfectly adequate reconstruction of a large
isotropic blur. The "scatter OFF" baseline (a sharp tinted grab, `T·B`) is a *stricter* baseline than
oracle's t0 (which already folds in the `h·⟨B⟩` mean-crossfade), which is why the OFF→ON drop looks
even larger here (e.g. 61→1.7 for opalescent) — the point stands either way: the blur is the whole
game.

## 3. Same two hard families, same cause (a material gap, not a render gap)

cathedral (12.9) and baroque/fracture/confetti (10.3) retain a real residual after the fitted scatter
— identical to oracle 045 to two significant figures (045 §0: 12.9 / 0.866 and 10.2 / 0.988). The
prototype's diff panel makes the cause visible: for these high-transmission, relief-textured glasses
the truth is a genuinely *refracted* checker (place-varying, locally-anisotropic distortion of the
backdrop), and an isotropic σ∝h blur softens the checker but cannot re-place it. This is exactly the
limit 045 identified as the missing physics — relief-coupled refraction — and it is a property of the
material representation `(T, h, σ_s)`, not of the renderer: the path-traced-ideal oracle recon hits
the same wall. A browser shader cannot beat it, and neither can path tracing *of these maps*; closing
it needs a richer material target (a refraction/normal term the backlit relight does not otherwise
justify — see 045 §5), not a heavier renderer.

## 4. Refraction and veil earn nothing here (confirming 045)

The relief-refraction toggle, given the ground-truth normal and a grid-searched gain (sign included),
improves MAE by **< 0.005 on every family** — the "+refr" column of the §2 bench is byte-identical to
"+scatter" at two decimals, and the fitted gain pins to the ±8 grid edge with no effect, the
signature of fitting residual noise. This is *weaker* than oracle's already-marginal < 0.15 (oracle
warped from the exact height field the Bump node consumed; a real shader's normal-map tilt is a looser
proxy, and at a large scatter blur the offset is washed out anyway). The front veil is identically
zero in a black-room backlit rig (045 §4); the prototype includes a Fresnel veil toggle for the
*future front-lit 3D case*, and toggling it ON in this backlit rig visibly *raises* the MAE — a live
demonstration that veil is the wrong term for backlit glass, not merely a null one.

## 5. Side view: do we actually need a thickness map?

The CTO's follow-on: the grazing angle is where a baked-T preview *should* break and a thickness map
*should* become necessary. We tested it — and the answer, for our current material model, is decided
analytically without a new render. **Why no new Cycles render:** the generator models the glass as a
**zero-thickness Principled "thin glass" surface BSDF** (`gen045_module.py:1675-1708`: Transmission=1,
IOR 1.5, Base Color = gt_T², Roughness = h; a flat `primitive_plane_add`, no Volume node, no
solidify). Surface transmission is **angle-independent**, so there is no volumetric grazing truth in
this material model to render against in the first place — rendering the *existing* scene at a tilted
camera would only add Fresnel + foreshortening, not the thickness effect under study. A genuine test
requires *changing the material model* to a volumetric slab, which is a scoped material-model
extension we are deferring (see below), not something this study renders. The physics is unambiguous
from the maps, so we demonstrate it directly (`sideview_046.py`, `sideview_thickness_board.jpg`).

The head-on transmittance already **bakes thickness into its exponent**: `couple_T_to_height`
(`gen045_module.py:376-387`) authors `gt_T(x) = T_base(x)^thickness(x)`, `thickness(x) =
1 − coupling·(2·height(x)−1)` (coupling largest for cathedral, ~0 for opal). Three variants at a
55° view (θ_r = 33.1° refracted, 1/cos θ_r = 1.19):

| family | (a) baked-T vs (b) T^(1/cos) MAE | (b) global-cos **vs (c) per-pixel thickness** | (d) differential slab-parallax vs (b) MAE |
|---|---|---|---|
| cathedral-green | 5.7 | **max 5.2×10⁻⁸ (identical)** | 4.4 |
| baroque-rolling-wave | 5.4 | **5.0×10⁻⁸** | 3.6 |
| streaky-mix | 7.2 | **5.2×10⁻⁸** | 4.4 |
| cathedral-green, **flattened** control | 5.7 | **3.9×10⁻⁸** | **0.0** |

Reading the columns:

- **(a) vs (b): the angle correction is real** (MAE 5–7): if the glass had volume, a grazing ray's
  longer path darkens the transmission, and a **global** factor `T^(1/cos θ_r)` handles it — because
  `gt_T` already carries the per-pixel thickness, `gt_T^(1/cos) = T_base^(thickness/cos)`.
- **(b) ≡ (c): a thickness MAP buys nothing over that global factor** for absorption. Computed by an
  independent code path (factor `gt_T` into `(T_base, thickness)`, then per-pixel Beer-Lambert), it
  matches the global correction to **float epsilon (≤5×10⁻⁸)** on every family, cathedral included.
  This is an identity, `(X^t)^{1/c} = X^{t/c}`, not a coincidence: thickness and intrinsic tint are
  not separable from a single head-on transmittance in the first place.
- **(d) the one genuinely thickness-dependent view effect is slab refraction PARALLAX** — the
  background seen through the glass shifts by ∝ thickness·tan θ_r, so relief ridges displace it more
  than valleys (MAE 3.6–4.4 on relief families; **exactly 0 on the flattened control** — a flat sheet
  has none). But this is a **volumetric** effect: our flat surface-BSDF preview produces no parallax
  at all, so it is shown as *what a thickness map would buy in a 3D/volumetric preview*, not something
  the current model exhibits. Note it also only survives at **low haze** — the σ_s scatter (§2) that
  solves the hazy families washes parallax out entirely, which is why it matters, if ever, only for
  low-haze high-relief glass (cathedral/baroque).

**Verdict on thickness:** not needed for the flat backlit head-on preview, and not needed for angled
*absorption* either (a global cos factor is exact; a per-pixel thickness map is algebraically the same
thing). Thickness becomes a real, separately-useful quantity only if we adopt a **volumetric glass
model** (a solid slab: solidify + displacement from `gt_height` + Volume Absorption / slab refraction)
for **angled, camera-orbit 3D views**, where slab parallax and self-occlusion appear. That is a
material-model *extension* (in the spirit of 045's σ_s addition) whose proper truth would be a fresh
volumetric Cycles render; it is scoped as a future **report 047** and deferred by *priority* — pending
whether 3D angled relighting is a near-term goal — not by tooling (Blender is available). It does not
change the flat-view ceiling above. The WebGL
prototype exposes this interactively: a view-angle slider with `T^(1/cos)` and slab-parallax toggles,
where at grazing the diff panel shows the (parallax) thickness contribution since no grazing truth
exists.

## 6. Production recommendation

**Ship a screen-space transmission shader; do not build or wait on a path tracer for the preview.**
Concretely:

- The mapping from our material maps to a real-time material is 1:1 and standard: **T → transmission
  color / attenuation (Beer–Lambert); h → roughness (drives the transmission-blur mip LOD); normal →
  normalMap (marginal here, keep for the front-lit 3D case); IOR 1.5.** three.js
  `MeshPhysicalMaterial` (`transmission` + `roughness` + `attenuationColor/Distance` + `thickness` +
  `normalMap`) implements precisely the technique benchmarked here and is the likely production path;
  the raw-WebGL2 `render046.html` shows the same shader with no framework dependency (and avoids
  inlining a heavy three.js build), so either route is viable.
- **Expected shipped quality (given good maps):** MAE 1–3 / SSIM > 0.99 — visually exact — on the 5
  scatter-dominated families; a visible-but-plausible residual on cathedral/baroque/fracture/confetti
  until the material model gains a refraction term. This is the *ceiling with perfect maps*; the
  product's real quality is then gated by map-estimation error (the extract/fine-tune track), not by
  the renderer.
- **Do not spend engineering on** a screen-space refraction pass, a veil/Fresnel term, or a
  **thickness channel** for the backlit preview — all three are measurably worthless here (§4, §5).
  A `thickness`/roughness-thickness input to `MeshPhysicalMaterial` can stay at a constant; the
  per-pixel absorption is already in T. Revisit veil + refraction + a real thickness map only if the
  preview moves to a front-lit or camera-orbit **volumetric 3D** scene (→ 047).

Deliverable for review: `results/046/render046.html` (self-contained WebGL2 prototype — family
selector, scatter/refraction/veil toggles, σ_s slider, a **view-angle slider with T^(1/cos) +
slab-parallax toggles**, live MAE, truth/render/diff panels). Handed to the team lead to review +
publish as the artifact.

Reproduction: `research/delighting/render046/`; `.venv/bin/python browser_render_046.py --data
<oracle45_data> --out ../results/046` (flat ceiling + board), `python sideview_046.py --data
<oracle45_data> --out ../results/046` (side-view thickness board), then `DATA046=<oracle45_data>
python export_assets_046.py && python build_html_046.py` (prototype), `python validate_browser_path.py`
(faithfulness). Twelve families as in report 045. **Side-view caveat:** the grazing panels are a
physics/model demonstration on the existing maps, not an empirical Cycles-truth ceiling — the current
generator's zero-thickness surface BSDF has no volumetric grazing truth to render against, so a
genuine test requires a new volumetric material model. That render is deferred to a potential 047 by
*priority* (pending whether 3D angled relighting is a near-term goal), not by tooling — Blender is
available at `~/Applications/Blender-5.0.1.app`.
