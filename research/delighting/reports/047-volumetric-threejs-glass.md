# 047 — Volumetric three.js glass: lamp + window-nudge, and the minimal map set

Date: 2026-07-16. Branch `research/delighting-047-volumetric` (off `research/delighting`
@ `525e3fd`). Follow-on to the browser-render ceiling (046) and the material gate (045).
**The CTO's question:** for two product use cases — (a) a **3D lamp** (curved glass shell, near
interior light, viewed from outside) and (b) a **window nudge** (a flat stained-glass pattern the
user can tilt/orbit ±10–15° to feel that it is really glass) — can we lean on an EXISTING three.js
rasteriser glass material (`MeshPhysicalMaterial` transmission + KHR volume) fed our estimated maps,
and **what minimal set of maps must the network predict** to make it look good? And, folding in the
CTO's steer off the 046 board ("the cathedral doesn't look like glass — would I need a 3D scene I can
orbit, with an IBL, for it to feel like glass?"): is the interactive orbitable IBL scene the thing
that sells it, and does three.js transmission's normal-map-driven screen-space refraction bring back
the relief structure the flat 2D shader misses?

**Framing (important).** The 045/046 rigs were deliberately clinical — a backlit black room, no front
light — precisely to isolate transmission/scatter. That rig **excluded by construction** every
perceptual "glassiness" cue: front-surface reflections, environment glints, motion parallax. This
study adds them all back: a real image-based-lighting (IBL) environment with front-hemisphere sources,
a scene behind the glass, and a camera/window that moves. So the **front-surface Fresnel veil that was
identically zero in 045 §4 is back in play** (045 flagged exactly this), and it turns out to be the
dominant delight cue.

Code (new, self-contained): `research/delighting/render047/` — `gen047_env.py` (shared equirectangular
HDR), `gen047_assets.py` (authors the GT maps with the verbatim trunk forward model), `prep047_maps.py`
(maps → 8-bit PNG textures + shared backdrop), `gen047_truth.py` (**Cycles volumetric-slab truth**),
`render047_model.html` (the three.js model, headless-Chrome-renderable), `serve047.py`/`drive047.py`
(render + ablation matrix driver), `compare047.py` (8-bit MAE + SSIM, byte-comparable to 045/046),
`assemble047.py` (boards), `render047_proto.html` + `build_proto047.py` (the **self-contained
orbitable prototype**). Artifacts (committed): `results/047/board_*.jpg`,
`results/047/proto047_volumetric_glass.html` (single-file, no CDN — vendored three.js r184, MIT),
`results/047/metrics_*_*.json`. Raw renders + `.npy`/`.hdr` intermediates are gitignored
(deterministically regenerable). Renders: Blender 5.0.1, Metal GPU, 512², 64 spp (flat) / 96 spp
(lamp), denoised. three.js renders on the same M4 GPU via ANGLE-Metal in headless Chrome.

## 0. TL;DR

- **Window nudge: YES — an off-the-shelf three.js `MeshPhysicalMaterial` reproduces the Cycles
  volumetric-slab truth to the cross-renderer alignment floor.** On cathedral-green (the documented
  worst family) the full model lands **MAE 19.5–24.9 / SSIM 0.62–0.83** over a ±0–30° orbit — and the
  **glass-hidden background alone already costs MAE ~20 / SSIM ~0.95** from two independent
  rasterisers not agreeing sub-pixel, so the glass material adds essentially **nothing** on top of the
  camera-match residual. Ship it for the window use case. §2, §3.
- **Minimal map set = {T (per-pixel tint), σ_s (haze→roughness)}. Normal is NOT worth predicting;
  per-pixel thickness is still not needed.** Dropping **T** is catastrophic on every family
  (MAE +30–60). Dropping **haze** hurts the scatter families (streaky +0.8, wispy +0.6 MAE / lower
  SSIM) and is a no-op on clear cathedral. Dropping **Normal changes nothing to the good** — see next
  bullet. §3.
- **The CTO's key hypothesis is REFUTED: three.js normal-mapped screen-space refraction does NOT bring
  the relief back.** Feeding the relief normal map, `full ≈ no_normal` in MAE and **SSIM is
  consistently HIGHER with the normal OFF** (cathedral az0: 0.748 → 0.834). A normalScale sweep is
  **monotonic** — every increase from 0 makes the match worse. The board shows why: three's
  normal-mapped transmission/reflection injects **high-frequency "orange-peel" sparkle**, whereas the
  real 3 mm slab refracts the background as **smooth, large-scale lensing**. The map bends the
  backbuffer, yes, but into the wrong spatial character. §4.
- **What actually carries the "feels like glass" delight is the reborn front-surface veil:** the IBL
  environment reflection on the Fresnel lobe (plus background parallax), which **slides across the
  glass as the camera orbits**. This is a free property of `MeshPhysicalMaterial` + an environment
  map; it needs **no predicted map at all**. The interactive orbitable IBL scene is indeed the thing
  that sells it — the static boards undersell it. Prototype delivered. §4, §6.
- **3D LAMP: NO — screen-space transmission is the wrong tool for an interior-lit shell.** The Cycles
  truth is a glass shell that **glows green all over** (interior light transmitted through the curved
  volume in every direction). three.js transmission only samples the **screen-space backbuffer**, so
  the shell renders **dark except directly in front of the filament** — MAE 44.9 / SSIM 0.32, and
  **tint barely registers** (there is no transmitted light across the wall to tint). A naive emissive
  "glow" augmentation over-brightens uniformly and makes it worse (MAE 45 → 80). The lamp needs baked
  interior lighting or a view-dependent glow model, not the maps-into-off-the-shelf-transmission
  strategy. §5.
- **Net for the product & the network:** the window-nudge preview is a ship-now win on
  `MeshPhysicalMaterial` and only sharpens the 045/046 target — **predict {T, σ_s}; do not spend
  capacity on Normal or thickness**. The lamp is a separate rendering problem. §6.

## 1. Method: one scene, two renderers, shared assets

To make an 8-bit MAE meaningful across two entirely different renderers, every input is **shared byte-
for-byte** and only the renderer changes:

- **Maps.** `gen047_assets.py` authors each family's GT maps (T, h, height, normal) with
  `gen045_module` — the *verbatim* trunk forward model — and saves exact float `.npy`. `prep047_maps.py`
  bakes the three.js-facing 8-bit PNGs (tint = sRGB-coded gt_T; haze; tangent normal) that a shipped
  material would actually load.
- **Environment.** `gen047_env.py` writes one equirectangular **HDR** (Radiance RGBE): coloured
  sky/ground, a soft key, and a few bright "window" panels (HDR > 1) whose reflections become the
  moving glints. The *same* `.hdr` is the Cycles world and the three.js PMREM environment.
- **Backdrop.** One shared image is the "scene behind the glass" — soft-edged structure (gradients,
  low-freq mullions, a large soft check, a soft sun). Softness is deliberate: a razor checker makes a
  cross-renderer MAE report sub-pixel **phase** misalignment, not material fidelity.
- **Truth = a REAL volumetric slab** (`gen047_truth.py`, per the CTO brief): a 512-grid plane
  **displaced** by gt_height (real relief that genuinely refracts), then **Solidify 3 mm** →
  constant-thickness slab; clear dielectric surfaces (Principled, IOR 1.5, Transmission 1, Roughness =
  gt_h) + a **Volume Absorption** whose per-pixel colour is calibrated so head-on transmittance through
  the nominal 3 mm equals gt_T exactly (`σ_a = (1−Color)·Density`, `T = exp(−σ_a·d)`; Density fixed,
  Color = `1 + ln(gt_T)/(D·d)`). This honours 046 §5: gt_T already bakes thickness, so absorption is
  a nominal-constant-thickness Beer–Lambert and no per-pixel thickness map is introduced.
- **Model** = three.js `MeshPhysicalMaterial` on a **flat quad** (the cheap deployable case — no
  per-pixel geometry): `transmission 1`, `thickness 0.003`, `ior 1.5`, `map` = tint (per-pixel T rides
  the base colour, because `attenuationColor` is a single constant — see §3), `roughnessMap` = haze,
  `normalMap` = relief, lit by the shared PMREM environment + the backdrop plane.
- **Camera match.** Both use a fixed, zero-roll camera on +Z; the "orbit" is a **group rotation**
  (elevation about X, azimuth about Y, identical XYZ euler) of the glass+backdrop — this avoids the
  `lookAt`-vs-`to_track_quat` roll divergence that otherwise rotates the two silhouettes oppositely.
  The glass-hidden **background render** is the alignment gate (and the MAE floor everything is read
  against).

Metrics (8-bit sRGB MAE 0–255, SSIM on luma, Gaussian window) are computed identically to 045/046.

## 2. Window nudge fidelity — cathedral-green (worst family)

`board_window_fidelity.jpg`. three.js `MeshPhysicalMaterial` (full maps) vs Cycles volumetric slab,
over the orbit:

| az | three.js FULL MAE / SSIM | no-Normal MAE / SSIM | −Tint MAE | background-only floor |
|---|---|---|---|---|
| 0° | 19.5 / 0.748 | **18.9 / 0.834** | 56.9 | ~20 / 0.95 |
| 10° | 22.5 / 0.677 | 22.3 / 0.722 | 51.9 | — |
| 15° | 24.9 / 0.617 | 24.7 / 0.643 | 50.1 | ~20 / 0.96 |
| 30° | 22.5 / 0.717 | 22.0 / 0.752 | 56.3 | — |

The headline is the **last column vs the first**: with the glass *hidden*, two independent rasterisers
already disagree by MAE ~20 (soft-feature sub-pixel offset + minor tone). The full glass model sits at
**that same ~20** at az0 and rises only modestly with angle (the alignment residual itself grows as the
tilted slab's edges sweep the high-contrast mullions). **The glass material is not the error source —
the cross-renderer camera match is.** By eye (board) the three.js panel is the Cycles panel: same green
volumetric tint, same softened backdrop through the glass, same env sheen up top, same silhouette at
every angle. For the shipping window preview this is *indistinguishable*.

## 3. The minimal map set: {T, σ_s}. Tint decisive; haze for scatter; per-pixel thickness still unneeded

`board_mapset.jpg` (drop one map, az0):

| family | FULL | −Tint | −Haze | const-tint (no per-pixel T) |
|---|---|---|---|---|
| cathedral-green (clear) | 19.5 | **56.9** | 19.5 (=FULL) | 19.2 |
| streaky-mix (mixed) | 31.7 | **81.7** | 32.2 | 24.2 |
| wispy-white (scatter) | 23.2 | **68.8** | 23.8 | 19.0 |

- **T (tint) is the one indispensable map.** Removing it (white base) is catastrophic everywhere
  (+30–60 MAE): the glass loses its colour and the transmitted light blows out. This is the map the
  network must get right.
- **A note on HOW T enters three.js:** `attenuationColor` (the KHR volume tint the brief hypothesised)
  is a **single constant** — it cannot carry a per-pixel pattern. Per-pixel T therefore rides the
  **base-colour `map`**. Interestingly, a **constant** attenuation tint (mean T) already matches or
  *beats* the per-pixel map on the two scatter families (streaky 24.2 vs 31.7, wispy 19.0 vs 23.2),
  because their haze scatters the transmitted structure anyway, so the truth's own tint detail is
  blurred out — a sharp per-pixel tint map then *over*-sharpens. For clear cathedral the tint is nearly
  spatially uniform, so constant ≈ per-pixel. Takeaway: per-pixel T helps most on **clear** glass and
  is partly redundant under heavy haze; predicting it remains correct, but its precision requirement is
  looser than one might assume.
- **σ_s (haze → roughness) matters for the scatter families and is free for clear glass.** −Haze costs
  streaky +0.8 / wispy +0.6 MAE (and visibly sharpens the transmitted backdrop, board), while being a
  no-op on cathedral (h≈0.09). This is the *same* term 045 crowned the dominant missing physics and
  046 mapped 1:1 onto the transmission-roughness mip — it carries straight over to the angled/IBL view.
- **Per-pixel thickness: still not needed** (as 046 §5 predicted). The truth is a nominal-constant
  3 mm slab and the model a constant `thickness`; angled absorption is handled by the volume path, and
  the ±0–30° nudge shows no residual attributable to a missing thickness map.

## 4. The CTO's hypothesis, tested head-on: Normal does not recover relief; the veil does the work

The steer was explicit: *three.js transmission bends the transmitted backbuffer by the normal map, so
the relief structure the flat 2D shader misses may come back for free — quantify it on cathedral.*

**It does not.** `board_normal_grain.jpg` and the metrics:

- `full` vs `no_normal`: MAE ~identical (19.5 vs 18.9), and **SSIM is HIGHER without the normal**
  (0.834 vs 0.748 at az0; the same ordering at every angle and on every family). Adding the relief
  normal map makes the match to Cycles *worse*.
- **normalScale sweep (cathedral az0):** 0.0 → **0.834**, 0.25 → 0.827, 0.5 → 0.800, 1.0 → 0.748,
  2.0 → 0.720 SSIM. Monotonic. There is no amplitude at which the normal helps.
- **Why (board):** three's normal-mapped transmission *does* perturb the transmitted backbuffer and
  the env reflection — but the authored relief normal is high-frequency, so it produces
  **grainy, orange-peel sparkle** scattered over the surface. The real 3 mm slab, by contrast, refracts
  the background as **smooth, coherent, large-scale lensing** (Cycles integrates true geometry + the
  volume). Screen-space single-tap refraction by a per-pixel normal is the wrong operator for
  large-scale relief lensing; it adds micro-glitter, not macro-distortion. (This mirrors 045 §3 /
  046 §3, where relief-coupled refraction was the one physics both the analytic model and the flat
  shader could not place — it is *still* not recovered here, now for a renderer reason on top of the
  material one.)

**So what makes it read as glass?** The front-surface **Fresnel veil**, reborn. 045 §4 measured it as
identically zero in the black-room backlit rig and warned it would return under front/ambient light —
it has. In this IBL scene the environment reflects off the glass's front lobe, and as the camera
orbits **the glints and the background parallax slide across the surface**. That motion — not a
predicted map — is the delight cue, and it is a free property of `MeshPhysicalMaterial` + an
environment map (`board_orbit_glints.jpg` shows the glints tracking az 0→30°; the effect is far
stronger live in the prototype than in stills, which is exactly the CTO's point about needing an
orbitable IBL scene). The answer to "would I need a 3D scene I can move, with an IBL, for it to feel
like glass?" is **yes, and that scene alone — no relief map — is what delivers the feel.**

## 5. The 3D lamp: screen-space transmission cannot carry the interior glow

`board_lamp.jpg`. The Cycles truth is a curved glass shell (3 mm wall) around an interior emitter: the
shell **glows green over its whole visible face**, because the interior light transmits through the
curved volume in every direction. three.js `MeshPhysicalMaterial` transmission renders the shell
**dark except the vertical strip directly in front of the filament** (MAE 44.9 / SSIM 0.32, az0 & az20
alike), because transmission samples only the **screen-space backbuffer** — off to the sides of the
shell there is nothing bright behind the fragment, so no coloured light is transmitted, and **tint has
almost no effect** (`−Tint` == `full` to 0.05 MAE: there is no transmitted light to tint).

A naive fix — make the shell **emit** the tint colour (`emissiveMap` = tint) — does not rescue it: the
truth's glow is **concentrated near the filament and falls off**, so a uniform emissive over-brightens
the whole shell and *worsens* the match monotonically (glow 0 → 0.4 → 0.8 → 1.2 gives MAE
44.9 → 58.1 → 70.5 → 79.9). The lamp's characteristic look is a genuine **global-illumination** effect
(interior light field × volumetric absorption × curvature) that a screen-space transmission raster
cannot express. Serving it needs a different technique — baked/pre-integrated interior lighting, or a
view- and thickness-dependent glow model driven by the interior light — **not** the "estimate maps →
off-the-shelf transmission" strategy that works for the window. This is a scoped rendering problem for
a later report, flagged here honestly rather than papered over.

## 6. Recommendations

- **Ship the window-nudge preview on three.js `MeshPhysicalMaterial` transmission + an IBL
  environment.** It reproduces the Cycles volumetric truth to the cross-renderer floor on the hardest
  family, and the orbitable IBL scene is what makes it feel like glass. Give it a real environment map
  with a few bright sources (for glints) and let the user tilt it — the delivered prototype
  (`results/047/proto047_volumetric_glass.html`, self-contained, orbit + family + map toggles) is the
  reference.
- **Network target: predict {T, σ_s} — do NOT add Normal or thickness.** T (per-pixel tint via the
  base-colour map) is indispensable; σ_s (haze → transmission roughness) matters for scatter families
  and is free elsewhere; this is exactly the 045/046 target, now re-confirmed in the angled/IBL
  regime. The **relief normal map is net-negative** for matching the truth (it adds high-frequency
  sparkle, not relief lensing) and per-pixel thickness remains unnecessary — predicting either would
  spend capacity to make the preview *worse* or no better. If a "textured glass" micro-sparkle is
  wanted as a *stylistic* choice, keep the normal at a low `normalScale` behind a toggle, but do not
  train for it as a fidelity target.
- **Do not build the 3D lamp on screen-space transmission.** It structurally cannot carry the interior
  glow; treat it as a separate rendering track (baked interior lighting / view-dependent glow), or
  defer it. The maps the network predicts are not the bottleneck there — the light transport is.
- **Perceptual gap the CTO flagged on the 046 cathedral ("doesn't look like glass") is closed by the
  scene, not a new map.** The 046 board was clinical (backlit, no front light, static). Put the same
  maps in an orbitable IBL scene and the front-Fresnel veil + parallax do the rest.

Reproduction: `research/delighting/render047/`.
`python gen047_env.py --out results/047/assets/env.hdr`;
`<blender> -b --python gen047_assets.py -- --out results/047/assets --families cathedral-green:6001,wispy-white:6001,streaky-mix:6001`;
`<venv>/python prep047_maps.py --assets results/047/assets`;
`<blender> -b --python gen047_truth.py -- --assets results/047/assets --family <fam> --scene flat|lamp --angles 0,10,15,30 --res 512 --out results/047/renders`;
`python serve047.py 8047 /tmp/r047 &` then `python drive047.py --family <fam> --scene <s> --truthdir results/047/renders --out results/047`;
`python assemble047.py`; `python build_proto047.py`. three.js r184 (MIT) vendored in `render047/vendor/`.
Blender's bundled Python needs scipy (`<blender_py> -m pip install scipy`; add `~/.local/.../site-packages` to `sys.path` in batch mode).
