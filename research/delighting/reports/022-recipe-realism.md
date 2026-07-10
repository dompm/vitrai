# 022 — Recipe realism: texture octaves, cathedral desaturation, five gap recipes

Date: 2026-07-10. Branch `research/delighting-022` (off `research/delighting` @ `5b1d006`).
Code: `generate_synthetic.py` (octave implementation + per-family octave params + cathedral
re-pick + five new recipes), `corpus/appearance_stats.py` (recipe re-derivation kept in exact
sync + new recipes), `eval_synthetic.py` (`CLASS_MAP` additions + per-sample self-recon MAE).
Artifacts: `results/corpus/appearance_stats_022.json`, `results/recipe_realism_022/`. Renders
(gitignored, repo convention): `validate_data_022/` (13 uniform-backlight validation samples),
`render_022/` (13 recipes x 1 seed x 2 HDRI lightings). No PR — reports are the deliverable.

Closes the two systematic gaps report 021 §3 measured (texture smoothness, cathedral
oversaturation) and its five §5 coverage-gap recipe proposals. The extractor
(`extract.py`) is deliberately untouched this iteration — including the `ANCHOR_*`
constants, which were fit on the OLD recipe statistics (reports 017/020); §5 reports what
the new recipes do to extraction quality and flags the refit as follow-up, one change at a
time.

## 0. TL;DR

- **The dead `octaves` parameter is now real.** `generate_noise(size, scale, seed, octaves=1)`
  had declared `octaves` since the generator's first version and never read it (021's traced
  mechanism for every recipe being 10–300x too smooth). It now blends `octaves`
  independently-seeded value-noise fields, each `lacunarity`x finer and `persistence`x weaker
  (standard fBm), renormalized once. `octaves=1` (the default) is byte-identical to the old
  behavior, so `generate_relief_height`'s existing hand-blended calls are untouched.
- **Every recipe family got tuned octave params** against the real per-class
  `hf_energy_frac` medians, and **all 13 recipes now land inside the real per-class p5–p95
  hf band** (before: all 8 recipes sat 1.6–3.6x BELOW their class's p5, 12–70x below its
  median). Cathedral,
  wispy, and opalescent families land within ~5% of their class *median*; the dark family
  deliberately lands below its median (0.068 vs 0.110) — see the honest note in §2.
- **Cathedral desaturated to the real median**: both recipes re-picked at the same L*/hue
  with C* 50.5/55.8 → 28.7 (= real cathedral-clear median exactly), haze raised per 021 §5.
- **Five gap recipes added** from 021 §5's Lab→linear targets, grounded only on its clean
  exemplars (Luminescent/dichroic ones excluded per its caveats): `cathedral-blue`,
  `cathedral-red`, `saturated-opalescent` (the FIRST opalescent-class recipe — 21% of the
  clean corpus had zero synthetic coverage), `streaky-fine-texture`, `dark-textured`.
- **Validate gate: 13/13 recipes pass** at MAE 0.0013–0.0397 (the historical few-percent
  band; report 006 floors were 0.006–0.039).
- **Extractor still works on all five new recipes** (oracle class, no `anchor_fallback`, no
  QA flags) — but §5's numbers show the expected cost of realism: more authored texture =
  more per-pixel structure the extractor's smooth-envelope assembly does not reproduce, and
  the class anchors (fit on the OLD, brighter/smoother recipes) overscale the new
  mid-brightness cathedral colors. Honest finding, not hidden: **the authored→rendered
  sRGB-shaped transform (017) applies to the HAZE channel too** (measured exactly:
  rendered `gt_h` = `srgb_encode(authored h)`), which means 021 §5's haze targets — authored
  units chosen against an extractor-unit statistic — overshoot in rendered units; h
  authoring needs a units decision before the next haze tuning pass (§6).

## 1. The octave fix (task A)

`generate_synthetic.py:generate_noise` now implements the declared `octaves` parameter
(plus `persistence`, `lacunarity`), following the multi-scale-blend pattern that already
existed in `generate_relief_height` (021 §4's recommendation), generalized instead of
copy-pasted. Per-band seeds are offset (`seed + i*7919`) so octaves are independent draws,
not correlated copies. Backward compatibility is exact: `octaves=1` runs the same single
`np.random.rand` + cubic zoom + normalize as before, so all height/relief callers and any
recipe not asking for detail are bit-identical.

Per-family parameters (tuned offline against the pure-numpy recipe re-derivation in
`corpus/appearance_stats.py`, which mirrors the generator's formulas exactly and was updated
in the same commit):

| family | octaves | persistence | lacunarity | authored hf lands | real class hf p50 |
|---|---|---|---|---|---|
| cathedral (green/amber/blue/red) | 4 | 0.60 | 6.0 | 0.0483 | 0.0464 |
| opalescent (saturated-opalescent) | 4 | 0.50 | 5.6 | 0.0207 | 0.0203 |
| wispy (wispy-white noise+mask) | 3 | 0.50 | 6.0 | 0.0167 | 0.0166 |
| dark (opaque/deep/ruby/slate/textured) | 4 | 0.60 | 6.0 | 0.067–0.069 | 0.1100 |

Two recipes needed mechanism care, not just parameters:

- **streaky-mix** keeps its macro streak mask single-octave (the streaks ARE the low
  frequency) and gains an **additive** fine-detail layer after the two-color mix. A
  multiplicative overlay (the cathedral mechanism) measurably cannot work here: the mask is
  a hard-thresholded step (`clip((x-0.3)*2)`), so most pixels sit saturated at 0/1 and
  absorb the modulation — measured <2x hf gain even at amplitude 1.0, vs the needed ~10x.
  Additive detail at amp 0.8 lands hf 0.0173.
- **dark family**: one shared param set (4, 0.6, 6.0) puts all five dark recipes at
  hf ≈ 0.068. See §2's honest note on why this deliberately does NOT chase the 0.110 median.

## 2. Appearance grounding, before → after (task D.3)

`corpus/appearance_stats.py --out results/corpus/appearance_stats_022.json`, same
n=1,138 backlit-verified real pool as 021 (identical real-side numbers, re-verified this
run). BEFORE numbers are 021's committed `appearance_stats.json`.

Real per-class bands (unchanged from 021):

| class | n | C p50 [p5–p95] | hf p50 [p5–p95] |
|---|---:|---|---|
| cathedral-clear | 250 | 28.7 [1.0–81.1] | 0.0464 [0.0063–0.3524] |
| opalescent | 250 | 31.8 [1.9–83.0] | 0.0203 [0.0052–0.2591] |
| wispy | 158 | 28.5 [4.6–71.0] | 0.0166 [0.0035–0.0734] |
| dark-opaque | 34 | 4.0 [0.4–33.9] | 0.1100 [0.0058–0.3703] |

Synthetic recipes, before → after (authored T arrays, same math as 021; `--` = recipe did
not exist):

| recipe | class | C before | C after | hf before | hf after | in-band after? |
|---|---|---:|---:|---:|---:|---|
| cathedral-green | cathedral-clear | **50.5** | **28.7** | 0.0040 | 0.0483 | C+hf both ~at p50 |
| cathedral-amber | cathedral-clear | **55.8** | **28.7** | 0.0040 | 0.0483 | C+hf both ~at p50 |
| dark-opaque | dark-opaque | 3.4 | 3.4 | 0.0016 | 0.0676 | yes |
| dark-deep | dark-opaque | 0.3 | 0.3 | 0.0016 | 0.0676 | hf yes; C 0.3 < p5 0.4 (pre-existing, see note 3) |
| dark-ruby | dark-opaque | 11.0 | 11.0 | 0.0016 | 0.0674 | yes |
| dark-slate | dark-opaque | 2.9 | 2.9 | 0.0016 | 0.0676 | yes |
| streaky-mix | wispy | 15.0 | 14.1 | 0.0016 | 0.0173 | yes (hf ~at p50) |
| wispy-white | wispy | 2.1 | 1.9 | 0.0018 | 0.0167 | hf yes (~p50); C 1.9 < p5 4.6 (pre-existing, see note 3) |
| cathedral-blue | cathedral-clear | -- | 41.1 | -- | 0.0483 | yes (021 target C 45) |
| cathedral-red | cathedral-clear | -- | 55.0 | -- | 0.0483 | yes (021 target C 55) |
| saturated-opalescent | opalescent | -- | 45.1 | -- | 0.0207 | yes (hf ~at p50) |
| streaky-fine-texture | wispy | -- | 40.4 | -- | 0.0546 | yes (hf targets its own exemplars' ~0.05, above the class p50 by design — that IS the gap it fills; still below the class p95 0.0734) |
| dark-textured | dark-opaque | -- | 5.1 | -- | 0.0685 | yes |

Notes, honest ones:

1. **The headline gate passes**: every recipe's hf and C sit inside its real class's p5–p95
   band (two pre-existing C exceptions below). Before this iteration, ALL EIGHT recipes' hf
   values (0.0016–0.0040) sat below their own class's p5 — cathedral's 0.0040 vs p5 0.0063
   (1.6x) at best, dark's 0.0016 vs p5 0.0058 (3.6x; 69x vs the class median) at worst.
2. **The dark family deliberately lands at 0.068, not the 0.110 class median.** 021 §3
   traced real dark glass's huge hf to texture-relief-and-lighting interaction (ribbed/
   hammered surfaces shading under the light table), and its §5 dark-textured exemplars run
   0.25–0.50. A flat authored color-noise field claiming hf 0.110+ would be painting relief
   energy into `T` — exactly the "iridescent finish painted into T" class of mistake 015/019/
   021 warn about, in reverse. 0.068 is inside the real band [0.0058–0.3703], a 42x step up
   from before, and leaves the rest of the real texture energy where it physically belongs:
   in the height/normal channel (which for the dark family already blends fine relief) and
   the renderer's shading of it. If a future iteration wants authored-T hf parity for dark
   glass it should first check how much of the real corpus statistic the RENDERED photos
   already recover from bump shading (the grounding here measures authored arrays, not
   renders — 021 §3's own stated caveat, still true).
3. **wispy-white's C (1.9) and dark-deep's C (0.3) remain below their class p5.** Both are
   pre-existing authored-color choices (021 §3 explicitly called out wispy-white's
   near-neutral color vs the real class's C 28.5 / warm hue). Recoloring them was NOT in
   this iteration's brief (the brief's color fixes were cathedral-only) and would churn the
   dark-family anchor calibration data (017) mid-iteration; flagged as candidate follow-up
   with the same Lab re-pick recipe used for cathedral here. dark-deep's miss is marginal
   (0.3 vs 0.4 on a 34-image class) and arguably correct — it authors near-black neutral
   glass, and near-black photos' measured chroma is mostly sensor/JPEG noise.
4. **Hue coverage improved but was not a gate.** The new recipes add blue (265°), red (10°),
   rose (340°) cathedral/opal points where all prior coverage was green/amber/cool-white;
   021's hue bands are extremely wide (chroma-weighted circular means over marketing-diverse
   catalogs), so in/out-of-band statements would be near-vacuous — coverage of the named
   gaps is the claim, and the L/C/hue landing points above match 021 §5's targets to within
   the noise term of each recipe (±2 L, ±1–4 C).

## 3. Validate gate (task D.1)

Uniform-backlight `--validate` render per recipe (1 seed x 1 lighting), scored by
`check_validation.py` (photo-vs-gt_T linear MAE; `results/recipe_realism_022/validate_gate.txt`):

| recipe | MAE | | recipe | MAE |
|---|---|---|---|---|
| dark-deep | 0.0013 | | saturated-opalescent | 0.0130 |
| dark-ruby | 0.0016 | | cathedral-blue | 0.0146 |
| dark-textured | 0.0035 | | cathedral-red | 0.0162 |
| dark-opaque | 0.0045 | | cathedral-green | 0.0230 |
| streaky-fine-texture | 0.0084 | | cathedral-amber | 0.0256 |
| dark-slate | 0.0095 | | streaky-mix | 0.0375 |
| | | | wispy-white | 0.0397 |

All 13 in the few-percent band (report 006's existing-recipe floors were 0.006–0.039;
wispy-white's 0.0397 is marginally above that historical max — its noise+mask calls both
gained octaves so mild movement is expected; still comfortably "few percent"). The
uniform-backlight identity `photo ≈ gt_T` surviving the octave fix confirms the new
fine-scale texture is faithfully carried through the full authored→shader→render→GT
pipeline, not aliased away at the 1536px texture or 700px render resolutions.

The authored→rendered calibration transform (017) was re-verified on every changed/new
recipe: rendered `gt_T` mean = `srgb_encode(authored base_color)` channel-for-channel to
within noise (e.g. cathedral-blue authored [0, .174, .450] → rendered [0, .445, .709] vs
predicted [0, .454, .701]; dark-textured [.012, .021, .021] → [.112, .156, .156] vs
[.112, .156, .156] exact).

## 4. Renders (task D.2)

`render_022/`: all 13 recipes x 1 seed (700–712) x 2 HDRI lightings (sunflowers_1k, the v2
lighting-variation convention), with shadow pairs — 25 samples (cathedral-green has one
lighting, §6 note 3). Gitignored; reproduction commands below.

## 5. Extractor on the new (and changed) recipes (task D.4)

`eval_synthetic.py --data render_022` (oracle class per `CLASS_MAP`; `extract.py`
UNTOUCHED this iteration — class anchors and `ANCHOR_*` constants still the 017/020 fit on
the old recipes' statistics, per the one-change-at-a-time rule).

25/25 samples extracted, 0 skipped, **0 anchor fallbacks, every `T_anchor_k` inside the
sanity band and class-constant** (0.95 / 0.88 / 0.20 for cathedral-wispy / opalescent /
dark oracle classes) — no new recipe degenerates the T assembly. Full per-sample rows in
`results/recipe_realism_022/eval_synth/summary.json` + contact sheets per recipe.

Per-recipe (oracle class; `017 T_mae` = report 017's cross-lighting GT-error on the same
recipe under oracle class, for the changed recipes' before/after):

| recipe | n | T_mae | 017 T_mae | h_mae | recon MAE (sRGB/255) | read |
|---|---:|---:|---:|---:|---:|---|
| **dark-textured** | 2 | **0.023** | -- | 0.184 | 0.01 | best of ALL 13 — dark anchor (0.20) ~= its rendered p99 (0.178), texture recovered |
| dark-ruby | 2 | 0.065 | 0.061 | 0.228 | 1.41 | unchanged |
| dark-opaque | 2 | 0.071 | 0.060 | 0.200 | 0.02 | ~unchanged |
| wispy-white | 2 | 0.072 | 0.122 | 0.162 | 1.65 | improved (small n both sides) |
| dark-deep | 2 | 0.097 | 0.111 | 0.176 | 0.05 | ~unchanged |
| dark-slate | 2 | 0.128 | 0.153 | 0.068 | 0.05 | ~unchanged |
| cathedral-amber | 2 | 0.152 | 0.146 | 0.222 | 0.05 | ~unchanged despite 12x more texture |
| streaky-mix | 2 | 0.167 | 0.136 | 0.166 | 0.82 | slightly worse |
| **saturated-opalescent** | 2 | 0.206 | -- | 0.178 | 0.01 | **saturation collapse, see below** |
| **cathedral-blue** | 2 | 0.227 | -- | 0.272 | 0.41 | anchor overscale + hue error, see below |
| cathedral-green | 1 | 0.244 | 0.145 | 0.223 | 0.07 | n=1; its family twin amber sits at baseline |
| **cathedral-red** | 2 | 0.246 | -- | 0.270 | 0.39 | anchor overscale + desaturation, see below |
| **streaky-fine-texture** | 2 | 0.279 | -- | 0.247 | 0.12 | **saturation collapse (worst cell)**, see below |

Three specific, mechanistic findings on the new recipes (predicted failure modes showing
up where predicted — reported, not hidden):

1. **Saturation collapse on strongly-tinted bright glass.** `saturated-opalescent`
   extracts `T_mean` [0.74, 0.74, 0.73] (neutral gray) against GT [0.80, 0.45, 0.68]
   (strong rose) — the authored chroma is almost entirely erased. Same signature on
   `streaky-fine-texture`: extracted [0.83, 0.78, 0.75] vs GT [0.76, 0.41, 0.38]
   (brick red → near-neutral), the worst T_mae of the batch (0.279). Mechanism: the
   sheet-relative desaturation + saturation-as-background-bleed cues in `assemble_T`
   (report 009's color-constancy compromise, which 009 §2.1 already documented as a
   one-sided trade tuned on wispy-white — a near-NEUTRAL recipe, the only wispy/opal
   evidence that existed then). The brief predicted saturated-opalescent might stress the
   color-constancy step; it does, and streaky-fine-texture (same wispy-class assembly
   path, C 40 vs wispy-white's C 2) stresses it harder. This is the first synthetic GT
   evidence that the 009 desaturation trade is mis-calibrated for saturated
   opal/wispy-class glass — exactly the evidence-coverage hole 021 §3 flagged when it
   noted every wispy-family recipe was near-neutral.
2. **Class-anchor overscale on mid-brightness cathedral colors.** `cathedral-blue`/`red`
   extract 1.3–2x too bright in their dominant channels (blue G: 0.74 vs 0.45; red R:
   0.94 vs 0.74). `T_ANCHOR["cathedral-clear"] = (99, 0.95)` assumes the sheet's
   brightest percentile transmits ~0.95, true for the old bright recipes (rendered p99
   0.75–0.84 + hotspot) but not for 021's darker gap targets (L*45: rendered p99 0.715
   blue / 0.752 red). The anchor constants were fit before these recipes existed; per the
   brief (and reports 016/017's one-change-at-a-time lesson) they are NOT refit here —
   flagged as the natural follow-up, with the note that the continuous anchor
   (`--anchor continuous`) should already partially absorb this since it reads brightness
   from the photo (untested this iteration: the eval runs the oracle-class/class-anchor
   path).
3. **`raw_p99` correctly flags the tinted recipes.** cathedral-red 2.06–2.34,
   cathedral-blue 1.88–1.91, dark-ruby 1.98–2.11 vs ~1.0–1.1 for every neutral recipe —
   report 004's "outlier raw_p99 = residual hotspot or misclass" diagnostic fires on
   exactly the strongly-tinted sheets (the illumination envelope normalizes the DOMINANT
   channel's clear level, leaving the suppressed channels' ratio spread visible). Useful,
   already-shipped QA signal for the saturated-glass regime; no code change needed.

The changed-recipe rows carry the headline for task A's risk: **adding 12–42x more
authored texture did not break extraction on any existing recipe** (amber/dark-family/
wispy rows all at their 017 baselines; streaky-mix +0.03). The extractor's smooth-envelope
assembly simply passes fine T-texture through the ratio image R, as designed.

## 6. Honest notes

1. **The 017 authored→rendered transform applies to the HAZE channel too, and 021's haze
   targets did not account for it.** Measured exactly on this iteration's validate
   renders: rendered `gt_h` = `srgb_encode(authored h)` to the third decimal on every
   flat-haze recipe (authored 0.09 → rendered 0.332; 0.30 → 0.584; 0.60 → 0.798). The
   extractor's h is trained/scored against rendered `gt_h`, and the real corpus's
   per-class `h_mean` (021 §5's grounding for the haze targets) is extractor output —
   both in RENDERED units. 021 §5 specified its haze targets as AUTHORED flat values
   against that rendered-unit statistic, so implementing them as authored (as its table
   and this brief instruct) lands cathedral's rendered haze at 0.332 where real cathedral
   extracts ~0.09 — visible in §5 as cathedral h_mae ~0.22–0.27 (extracted ~0.06–0.11 vs
   gt 0.33). Under the rendered-unit reading the OLD authored 0.02 (rendered 0.152) was
   arguably closer, and the "under-hazed" framing inverts. Not silently deviated from the
   brief here — the specified targets are implemented as written — but the units decision
   (author h in `srgb_decode(target)` like 017 does for T, or accept authored-unit
   targets) must be made explicitly before the next haze pass. One-line fix either way
   once decided.
2. **The grounding measures authored arrays, not renders** (021 §3's caveat, inherited).
   The real corpus statistic includes backlight falloff + relief shading; the authored T
   does not. For hf specifically this cuts both ways: the renders add bump-shading
   texture energy on top of the authored hf (helping dark's remaining gap, §2 note 2)
   and the sRGB-shaped encode compresses contrast of bright recipes slightly. A
   rendered-photo-side grounding pass (same stats on `without_shadow_photo.png`) is the
   obvious next-iteration check; not run here to keep this report's before/after strictly
   comparable to 021's authored-side numbers.
3. **cathedral-green has n=1 render** (its second lighting was the sample killed
   mid-render when the batch was restarted for a process-timeout issue; not re-rendered —
   the seed/lighting recipe is in the reproduction commands). Its n=1 T_mae (0.244) reads
   worse than its family twin cathedral-amber (n=2, 0.152, at the 017 baseline);
   single-lighting draws of cathedral glass historically span ~0.13–0.26 (017), so no
   conclusion should be hung on that cell.
4. **`ANCHOR_*` (continuous anchor) constants are now stale by construction**: they were
   fit on the OLD 8-recipe statistics (35 samples, reports 017/020), and both the
   texture and the color distributions those fits saw have changed, plus five new recipes
   exist. Deliberately NOT refit this iteration (brief + one-change-at-a-time). Until the
   refit lands, continuous-anchor runs on synthetic-new-recipe data are running on an
   out-of-date calibration; the class-anchor oracle path used in §5 is unaffected.
5. **The real-photo library is untouched by construction** — `extract.py` did not change
   this iteration (the only extraction-adjacent change is a new metric column in
   `eval_synthetic.py`), so no library regression run was needed or performed.
6. **Renders are gitignored** (repo convention since 005); the corpus is symlinked
   read-only from the main checkout (015/019/021 convention), not committed, not
   modified.

## Reproduction

```
cd research/delighting
# validate gate, all 13 recipes (~2 min each)
for r in cathedral-green cathedral-amber dark-opaque dark-deep dark-ruby dark-slate \
         streaky-mix wispy-white cathedral-blue cathedral-red saturated-opalescent \
         streaky-fine-texture dark-textured; do
  PYTHONPATH=~/.local/lib/python3.11/site-packages \
    ~/Applications/Blender-5.0.1.app/Contents/MacOS/Blender -b --python-use-system-env \
    -P generate_synthetic.py -- --out validate_data_022 --validate --recipe $r \
    --seed 42 --count 1 --light-variations 1
done
python3 check_validation.py validate_data_022

# full renders (1 seed x 2 lightings each, ~8 min per recipe)
#   seeds 700..712 in the recipe order above
PYTHONPATH=... <blender> -b --python-use-system-env -P generate_synthetic.py -- \
    --out render_022 --recipe cathedral-blue --seed 708 --count 1 --light-variations 2

# appearance grounding (real corpus symlinked read-only, 015/019/021 convention)
cd corpus && python3 appearance_stats.py --out ../results/corpus/appearance_stats_022.json

# extractor eval (oracle class)
python3 eval_synthetic.py --data render_022 --out results/recipe_realism_022/eval_synth
```
