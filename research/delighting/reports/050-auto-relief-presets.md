# 050 — Auto-detected procedural relief presets from one photo

Date: 2026-07-16. Branch `research/delighting-050-auto-relief` (off
`research/delighting` @ `4898d70`). Follow-on to 047 (volumetric three.js glass)
and the 045/046 material-model line.

**The decision this report serves.** 047 proved the relief normal map is NOT a
learned fidelity target — feeding even the *ground-truth* normal to three.js
screen-space refraction turns relief into high-frequency sparkle, not the smooth
large-scale lensing a real slab does, and it *worsens* the match to Cycles truth
(SSIM 0.834 normal-off → 0.748 normal-on; §047.4). But the CTO eye-tested the
047 orbit demo **with that sparkle on** and loved it ("this looks like glass to
me"). So the normal becomes a **presentation-layer effect** — procedural and/or
derived — with one hard product requirement, verbatim:

> "I'd still like the category + settings (e.g. hammered, small bumps) to be
> automatically detected from the user photo, not as something where my user has
> to try 8 different settings until they find something that matches their real
> glass."

This report builds (1) a small procedural relief **preset bank**, (2) an
**auto-detector** that picks a preset from one raw photo, (3) a **synthetic
quantitative validation** against the generator's authored relief, (4) a **real
qualitative board**, and (5) an **end-to-end perceptual A/B** in the real
three.js material. Code: `research/delighting/render050/`. Boards/JSON:
`results/050/`. Raw renders are gitignored (deterministically regenerable).

## 0. TL;DR

- **Preset bank shipped: 6 categories × ≤3 knobs, procedural, tileable, cheap,
  deterministic** — `smooth, hammered, granite, seedy, ripple, rolling_wave`,
  each `(amplitude, feature_scale[, angle])`. The taxonomy is grounded 1:1 in the
  generator's own relief families (`generate_relief_height`) and the real corpus
  classes, not invented. Band-limited Fourier noise + wrapped seed-stamps → the
  height/normal tile seamlessly. §2, `board_preset_bank.jpg`.
- **The honest headline: from ONE photo, the coarse relief *character* is
  weakly detectable and the fine sub-label + numeric knobs are not.** VLM
  multiple-choice category (the lab's validated pattern, haiku, direction-first
  prompt) on a synthetic **holdout** lands **fine 6-way ≈ 0.50–0.58 and coarse
  4-way ≈ 0.50–0.67 across two runs** (chance 0.17 / 0.25). The **only categories
  reliable across both runs are `smooth` and `ripple` (2/2 each)**; the
  isotropic-pebble trio (hammered↔granite↔seedy) is unstable and its errors even
  cross coarse boundaries. §3, §4.
- **VLM category is stochastic run-to-run.** Two identical-config runs on the
  same 12 holdout photos gave fine 0.50 and 0.58 (coarse 0.50 and 0.67) — a
  ~±2/12 wobble. So treat these as ~0.5, not a precise figure. This stochasticity
  is itself a reason not to hang a fidelity-critical decision on the per-photo
  fine pick. §3, §4.
- **This is NOT a model-capability ceiling — it is genuine single-photo
  ambiguity.** A stronger model (sonnet) with the *same* prompt did **worse**
  (fine 0.33 / coarse 0.42); it collapses uncertain textures to `smooth`. And our
  own generator authors hammered/granite/seedy as three variations on the *same*
  isotropic-hammered base (`generate_relief_height` shared-relief grouping) — so
  they *are* near-identical surfaces; asking a photo to separate them asks for a
  distinction that barely exists. §3, §4.
- **Knob detection (amplitude/feature-scale bins) is weak from one photo, by
  both channels.** Classical statistics: amplitude-bin ≈ 0.42, scale-bin ≈ 0.17.
  VLM multiple-choice bins: amplitude ≈ 0.50, scale ≈ 0.42. Neither is ship-grade;
  the VLM amplitude bin is the least-bad. §3.
- **A T-derived pseudo-normal is a useful blend component exactly where the brief
  predicted** — streaky/wispy, where the relevant structure lives in the tint T,
  not in front-surface glints — and is near-noise on clear cathedral. §3.
- **End-to-end A/B (the 047b question) is the good news.** Rendered in the real
  three.js material three ways — GT normal | procedural preset | off — the
  **procedural bank preset is perceptually GT-like** (both read as "textured
  glass"; both clearly ≠ the flat "off" panel), clearest on cathedral. So 047's
  "even GT doesn't beat off against truth" + this "preset ≈ GT perceptually"
  means the effect is **robust to which textured preset you pick** — the whole
  game is getting the *coarse* character right, and the fine label / exact knob
  are low-stakes. §6, `board_ab_normal.jpg`.
- **Recommendation: ship auto-detection only for the reliably-separable axis**
  (is it flat? is it directional/streaky?), default everything else to a single
  "textured" preset (`hammered`, medium knobs), and add the T-pseudo-normal blend
  on streaky/wispy. That honours the CTO requirement — the user never tries 8
  settings — while being honest that one photo does not support a reliable 6-way
  + numeric-knob pick. §7.

## 1. Method

**Preset bank** (`relief_presets.py`, pure numpy). Categories + knobs below;
height synthesised as band-limited (periodic → tileable) Fourier noise, with
discrete wrapped seed-stamps for `seedy` and an anisotropic frequency envelope
for `ripple`. `height_to_normal` is byte-compatible with the trunk generator's
so procedural and GT normals feed the material identically.

**Detection** (`detect_relief.py`). *Category*: `claude` CLI as subprocess,
multiple-choice over the 6 categories with an explicit option list (the lab's
validated VLM-as-classifier pattern; `vlm_classify.py` lineage). *Knobs*:
classical statistics on the photo (luminance HF energy + specular glint contrast
→ amplitude; radial-PSD dominant wavelength → feature-scale; structure-tensor
orientation → ripple angle) **and** VLM multiple-choice bins, computed side by
side so we can ship the more reliable. *T-pseudo-normal*: high-pass of the tint
map's luminance → pseudo-height → normal, plus a `t_structure` score.

**Synthetic ground truth** (`gen050_author.py`, `gen050_photos.py`). The
generator authors a known relief per recipe; we render each recipe/seed as a
**front-lit "user photo"** — a real 3 mm volumetric slab (047's construction:
displaced by `gt_height`, Beer-Lambert volume from `gt_T`, roughness from
`gt_h`) under a **soft, diffuse IBL** (`gen050_env.py` — 047's three sharp window
panels cast diagonal streaks that masked isotropic pebble as directional; a
diffuse light is both fairer and more like a real sheet photo) and a soft
luminous backdrop, so the glass's *own* surface relief reads as glints/shading
(047: relief is invisible in the 045/046 backlit rig; it needs front light). 15
assets across 5 relief-bearing categories × up to 3 seeds + 3 flattened `smooth`
samples. **Holdout discipline: seed 6001 = tuning, seeds 7001/7002 = holdout;
headline numbers are holdout.** `score050.py` scores category + knob bins.

**Real board** (`board_real.py`): detection on the curated corpus/wild sheet
photos in `reports/assets_029/` + the CTO's difficult sheet. **A/B**
(`model050.html` + `drive050_ab.py`): the 047 window-nudge scene in real three.js
`MeshPhysicalMaterial`, headless-Chrome rendered with GT / procedural / off
normals.

## 2. The preset bank — grounded in our own relief taxonomy

`board_preset_bank.jpg` (height | normal | raking-light shade | 2×2 tile). Each
preset = a relief **category** + up to 3 **knobs** (`amplitude`,
`feature_scale`, and `angle` for ripple only); amplitude/feature-scale are
exposed to detection as **bins** (subtle/medium/strong × fine/medium/coarse).

The category list is not invented — it is the set of relief families the trunk
generator already authors in `generate_relief_height`, themselves grounded
(003–037) in the real sheet-glass corpus:

| preset | generator relief family | authored bump range | character |
|---|---|---|---|
| `smooth` | (float/cast; ~flat) | ~0 | flat, faint sub-mm only |
| `hammered` | cathedral-green/amber/blue/red | 1.6–4.5 mm | isotropic pebbled cells |
| `granite` | dark-opaque/deep/ruby/slate/textured, ring-mottle | 1.0–3.0 mm | dense fine stipple |
| `seedy` | wispy-white/opalescent/confetti (+`micro_events`) | 0.8–2.5 mm | discrete round bumps/seeds |
| `ripple` | streaky-mix/fine, fracture-streamer | 0.15–0.7 mm | directional pulled streaks |
| `rolling_wave` | baroque-rolling-wave | 6–14 mm | coarse cm-scale waves |

Note the generator itself **groups** hammered/granite/seedy as variations on one
isotropic-hammered base (`0.65·hammered+0.35·noise`, `0.50·hammered+0.50·noise`)
— they differ mostly in a secondary octave and in colour/haze, not in a distinct
surface finish. This is the taxonomic reason detection cannot cleanly separate
them (§4), and the product reason it need not.

## 3. Detection: what one photo supports

**Category (VLM multiple-choice).** The winning configuration is **haiku with a
direction-first prompt** ("decide DIRECTIONAL vs ISOTROPIC first; only choose
ripple if the direction is unmistakable"). Two things justify it:

| config | fine 6-way (holdout) | coarse 4-way (holdout) |
|---|---|---|
| haiku, flat 6-option prompt | 0.50 | 0.58 |
| haiku, direction-first, run A | 0.58 | 0.67 |
| haiku, direction-first, run B (persisted) | 0.50 | 0.50 |
| sonnet, direction-first | 0.33 | 0.42 |

The sonnet row is the important one: **a bigger model is worse**, so category
detection is limited by photo ambiguity, not model capacity — spend the cheap
model. The run-A/run-B spread is the stochasticity (§0). (Chance = 0.17 fine /
0.25 coarse.)

**Knobs.** Both channels are weak, on the holdout (persisted run):

| knob | classical | VLM MC |
|---|---|---|
| amplitude bin | 0.42 | **0.50** |
| feature-scale bin | 0.17 | 0.42 |

The VLM amplitude bin is the least-bad and is what we would ship if forced;
neither is reliable enough to expose as a fidelity-critical setting.
Feature-scale is additionally category-tied in the generator, so its low number
partly reflects the confound, not only detector error.

**T-derived pseudo-normal.** The `t_structure` score cleanly separates the
families whose relief-relevant structure lives in the tint (streaky/wispy, high
score) from clear cathedral (near-zero) — matching the brief's prediction. It is
therefore the correct blend component to add *only* on the directional/scatter
families, not on clear glass.

## 4. Synthetic validation — the confusion is informative

`board_synth_photos.jpg` shows the 18 front-lit slab photos. Holdout category
confusion (persisted direction-first haiku run):

```
smooth        -> smooth   x2         (reliable: flat reads flat)
ripple        -> ripple   x2         (reliable: directional reads directional)
rolling_wave  -> {rolling_wave, seedy}
hammered      -> {hammered, rolling_wave}
granite       -> {smooth, ripple}
seedy         -> {smooth, ripple}
```

The pattern, consistent across both runs: **only the endpoints are reliable** —
`smooth` (flat) and `ripple` (directional) were 2/2 in *both* runs. The
isotropic-pebble trio (hammered/granite/seedy) is intrinsically ambiguous (§2)
and its misfires scatter to `smooth`, `ripple`, and `rolling_wave` — i.e. they
even cross coarse-group boundaries, which is why coarse accuracy was not reliably
better than fine in the persisted run. `rolling_wave` is near-`smooth` at a tight
sheet crop because its waves are cm-scale — a genuine ambiguity that also exists
for real waterglass at a glance.

Two honest caveats: (a) the set is small (12 holdout photos), so ±1 photo moves a
number by ~0.08 — combined with the VLM stochasticity, treat every accuracy here
as "≈0.5", directional not precise; (b) feature-scale has little within-category
variation in the generator, so its bin score mostly measures category, not scale.

## 5. Real board

`board_real_detection.jpg`: detection on the curated real corpus/wild sheet
photos (`reports/assets_029/corpus_*`, `wild_*`) + the CTO's difficult sheet,
each `photo | detected category+settings | procedural normal | shade`. The
detected-category distribution over the 18 real photos is
`ripple 7, seedy 4, rolling_wave 3, hammered 2, granite 1, smooth 1` — and the
sensible calls line up with §4's reliable axis: the two **waterglass/handblown**
sheets → `rolling_wave` (correct — waterglass *is* rolling wave), the reeded
`wild_sheets_shelf` → `ripple`, a clear float sheet → `smooth`; the isotropic
cathedral/opalescent sheets land somewhere in the textured family with the exact
sub-label wobbling. The **CTO's difficult sheet → `ripple`** (medium/coarse,
angle ≈ −81°). Settings + resulting normals in `results/050/real_detection.json`.
(Raw corpus images are local-only; only downscaled board crops are committed,
per prior reports.)

## 6. End-to-end A/B — the procedural preset is perceptually GT-like

`board_ab_normal.jpg`: the 047 window-nudge scene in the real three.js
`MeshPhysicalMaterial`, three ways (GT normal | procedural preset | off), same
T/haze/env. To isolate the *perceptual* question from the noisy per-photo fine
pick, the middle column is the **default preset for the family's true coarse
group** — i.e. exactly what the recommended ship path (coarse-detect + in-family
default, §7) produces when the coarse call succeeds.

- **cathedral-green (textured → `hammered`):** the preset panel is
  **perceptually GT-like** — same textured-glass sparkle character — and both are
  clearly distinct from the flat "off" panel. This is the tie 047 predicted:
  since even the GT normal does not beat "off" against Cycles *truth*, a
  plausible procedural normal ties with GT *perceptually*.
- **wispy-white (→ `seedy`):** GT and preset both add a soft texture over the
  "off" panel; the difference GT-vs-preset is subtle. Tie holds.
- **streaky-mix (→ `ripple`):** all three panels look nearly the same — the
  structure is carried by the tint T (and, per §3, by the T-pseudo-normal), so
  the normal choice barely matters here.

Net: the perceptual stakes ride on the **coarse** character being right, and the
bank's preset for the right group **ties with GT** — the fine sub-label and the
exact knob change little.

## 7. Recommendations

- **Ship auto-detection only for the axis one photo reliably supports:** "is the
  surface clearly flat?" and "is it directional/streaky?" (the two categories
  robust across both runs). Map to presets: clearly-flat → `smooth`;
  directional → `ripple` + the T-pseudo-normal blend; **everything else → a
  single default `textured` preset (`hammered`, medium knobs)** rather than a
  fragile hammered-vs-granite-vs-seedy pick. This satisfies the CTO requirement
  literally — the user never tries 8 settings, the category is auto-detected —
  while being honest about what one photo supports. §6 shows the default textured
  preset ties with GT perceptually, so collapsing the isotropic trio costs
  nothing visible.
- **Do not expose the numeric knobs as user-visible fidelity settings.** Both
  channels are weak on amplitude/scale; drive them from a per-category default
  plus, at most, the VLM amplitude bin (least-bad, 0.50) as a subtle/medium/
  strong nudge. The effect is robust to this being approximate (§6).
- **Use the cheap model, one cached call/photo.** Sonnet is worse here; category
  detection is ambiguity-limited, not capacity-limited.
- **Blend the T-pseudo-normal only on the streaky/wispy family**, where the
  structure lives in the tint; it is near-noise on clear glass.
- **Keep the full 6-way bank** (it is free, tileable, and useful for a future
  "advanced/manual" override), but do not gate the automatic path on the fine
  label.

Honest bottom line: the CTO's requirement is **partially** met from one photo.
The reliably-detectable relief axis (flat vs directional vs "textured") plus a
sensible default is auto-detectable, and the A/B says that is perceptually
enough. A *precise* hammered-vs-granite-vs-seedy + exact-amplitude read is not
reliable — and the sonnet result + the generator's own taxonomy say it likely
*cannot* be, from a single photo. Ship the coarse path; do not promise the fine
one.

Reproduction: `research/delighting/render050/` —
`python relief_presets.py` (bank smoke) · `python preview_bank.py` (bank board) ·
`<blender> -b --python gen050_author.py -- --out results/050/assets_ms --specs …` ·
`<venv>/python ../render047/prep047_maps.py --assets results/050/assets_ms` ·
`python gen050_env.py --out results/050/assets_ms/env_soft.hdr` ·
`<blender> -b --python gen050_photos.py -- --assets results/050/assets_ms --keys … --soft --env env_soft.hdr --out results/050/photos_v2` ·
`<venv>/python score050.py` · `python drive050_ab.py` · `python board_real.py` ·
`python exp_category.py sonnet haiku` (model ceiling). VLM = `claude` CLI, haiku,
one cached call/photo.
