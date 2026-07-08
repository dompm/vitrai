# Report 001 — Classical baseline (Track A) + VLM class prior (Track C)

Date: 2026-07-08. Code: `extract.py` @ this commit. Panels: `results/`.

## 1. Problem and model

From one casual backlit photo, recover `T(x)` (RGB transmittance) and `h(x)`
(haze fraction). Working image model, in linear RGB:

```
I(x) = L(x) · T(x) · [ h(x) + (1 − h(x)) · B(x) ] + S(x)
```

`L` = backlight illumination field, `B` = background radiance relative to `L`
(what you see through clear regions), `S` = additive front-surface speculars.
A single photo cannot separate all five factors; the pipeline leans on two
priors: (a) illumination is very low frequency, (b) a **global glass class**
(`opalescent | wispy | cathedral-clear | dark-opaque`) that resolves the
dark-pixel ambiguity — in `wispy`/`cathedral-clear` a dark low-texture pixel is
background seen through clear glass (high T, low h); in `dark-opaque` it is the
glass itself (low T, high h).

## 2. Benchmark

| case | file | class | why |
|---|---|---|---|
| EASY | `benchmark/easy_amber.jpg` | cathedral-clear | app default-library swatch, even light-table backlight, single hue |
| DIFFICULT | `benchmark/difficult_wispy.jpg` | wispy | handheld against a window; hand shadow, sunset color gradient, green lawn below, grease-pencil "9000-81", sheen |

## 3. Metrics (precise definitions)

**M1 Self-reconstruction.** `Î = L·T·(h + (1−h)·B̃)` where `B̃ = clip(R/T)`
downsampled to **quarter resolution** and back (`R = I/L` after specular/mark
inpainting). Restricting `B̃` to quarter res is the teeth of the metric: any
glass detail mis-assigned to the background layer is destroyed by the
downsample and shows up as error. Error is per-pixel `|sRGB(Î) − sRGB(I)|` on
a 0–255 scale. Pixels inside the specular/mark masks are **excluded** from the
headline number (the maps disagree with the photo there *on purpose*); the
all-pixel value is reported alongside. Side-by-side + 5x error map are columns
4–5 of each panel.

**M2 Relighting plausibility.** Panels under warm `(1.0,0.72,0.42)` and cool
`(0.65,0.82,1.0)` uniform illuminants, `out = c·T·(h + (1−h)·1)`. Judged by
eye; every visible artifact is listed in §6.

**M3 Cross-lighting validation.** Reserved — needs the second-lighting shots
(not yet arrived). Batch mode + manifest exist so rerunning is one command.

Results:

| case | M1 MAE (clean px) | M1 p95 | M1 MAE (all px) | mark px | spec px |
|---|---|---|---|---|---|
| easy_amber | **2.67 / 255** | 13.85 | 2.67 | 0 % | 0 % |
| difficult_wispy | **2.93 / 255** | 8.54 | 4.14 | 11.2 % | 6.1 % |

## 4. Method (Track A), per original work item

**W1 — Edge-aware illumination (replaces the Level-0 Gaussian).**
`L = luminance envelope × chroma field`.
*Envelope*: 88th-percentile filter, window ≈ 35 % of image, on 8× downsampled
luminance, then heavy Gaussian — an upper envelope, so large-scale glass
absorption stays in `T` instead of being eaten (the Level-0 failure).
*Chroma*: weighted **quadratic polynomial** fit of `I`'s chroma, weights =
milky-pixel score. A quadratic can follow the sunset-warm-top → neutral-bottom
gradient of the backlight but cannot follow glass structure, so wispy tint
survives. Class-gated: for `cathedral-clear`/`dark-opaque` the illuminant is
assumed neutral and all color stays in `T` (a uniformly amber sheet is
indistinguishable from amber light in one photo — the class prior is what
breaks the tie).

**W2 — Grease-pencil detection + inpaint.**
Local statistics failed: black-hat depth / sharpness / saturation of the pencil
overlap almost completely with wispy glass veining (measured: black-hat p90
0.28 vs 0.21). Shape filtering on connected components also failed — the
strokes merge with veins into one blob. What worked: **chroma anomaly** — the
pencil is a foreign pigment, its chroma deviates from the local (6 % window)
glass chroma by ~0.12 L2 vs ~0.03 for veins. Detector = smoothstep(black-hat)
× smoothstep(anomaly), then Telea inpaint of `R`, inpaint of `h`, and
confidence-zero in the `T` diffusion fill.

**W3 — Specular suppression.**
Deliberately conservative: near-clipped pixels always; plus small-scale
top-hat outliers (>0.22 over 85th luminance percentile) only for
`opalescent/wispy/dark-opaque` — on hammered cathedral glass the glints are
transmitted lensing that belongs in `T`. Sanity valve: if the mask exceeds
15 % of the frame, skip inpainting entirely.

**W4 — Haze map `h`.**
Milkiness `m` = bright × locally-smooth × desaturated, where texture is
measured on median-filtered luminance (so 1–3 px sparkle doesn't read as
background texture), then class modulation:

| class | h |
|---|---|
| opalescent | `(0.55 + 0.45·m) · (1 − 0.9·bg)` |
| wispy | `(0.05 + 1.1·m) · (1 − 0.9·bg)` |
| cathedral-clear | `0.06 + 0.20·m` |
| dark-opaque | `0.25 + 0.75·max(dark·smooth, 0.4·m)` |

`bg = 1 − exp(−(sat/0.25)²)` marks saturated pixels as background content
(kills the lawn) for the near-white classes. Final `h` is guided-filtered
(edge-aware) by luminance.

**T assembly.** `T = R` where the glass color is directly observed
(confidence = max(h, bright·desat)); elsewhere (dark/saturated background seen
through clear glass) `T` is diffusion-filled from confident neighbours.
`T` is normalized so p99 = 0.97 — absolute transmittance is unknowable from
one photo of unknown exposure; `T` is *relative*.

## 5. Track C — VLM class prior

`vlm_classify.py` shells out to `claude -p … --allowedTools Read --model haiku`
with a 4-way multiple-choice question (never numeric regression). Results:
amber → `cathedral-clear` ✓, wispy sheet → `wispy` ✓ (2/2, ~15 s per call,
cached). This is enough signal to wire `--vlm` into batch mode as the default
class source for incoming eval photos.

## 6. Honest failure analysis (what a human sees in the panels)

**easy_amber** (`results/easy_amber_panel.jpg`) — good. Light-table hotspot
(top-left) removed from `T`; hammered texture fully preserved; relit-cool
correctly turns amber toward green-yellow (little blue transmitted). Residual
issues: some low-frequency unevenness remains in `T` (envelope under-fits the
corner falloff), and `h` is a near-constant 0.06 — the class default, not a
measurement. **Against the CTO's criterion ("reproduce the easy case
faithfully"), this case passes to my eye** — but verify on the panel.

**difficult_wispy** (`results/difficult_wispy_panel.jpg`) — usable but a human
will notice, in roughly this order:

1. **Faint pencil ghost**: pale outlines of the "9000-81" loops survive in `T`
   and both relit panels (bottom-right). Much weaker than Level-0, not gone.
2. **Hand-shadow smudge** (top-center) survives in `T` as a fake gray wisp —
   indistinguishable from real glass structure by any local cue we have (OP-1).
3. **Sparkle flattening**: the icy texture (top-left / mid-left) is partially
   smoothed away by specular inpainting + mark-mask false positives (11 % of
   pixels, mostly harmless because the fill is local, but it costs micro-detail).
4. **Softened contrast**: overall the wispy structure in `T` is lower-contrast
   than the original — some structure leaked into the illumination envelope and
   the fills average things out.
5. **Bottom edge**: a thin olive smear where the lawn boundary met the glass
   edge; the lawn itself is gone from `T` (it was the Level-0 headline failure).
6. **`h` fine scale is unvalidated**: plausible at large scale (milky top high,
   clear blue streaks low), but dense gray wisps get `h` dips because "dark +
   smooth" reads as background-through-clear-glass — for smoke-gray wisps that
   is physically wrong (they diffuse). No ground truth until M3 photos arrive.

## 7. Parameters that matter (sensitivity, by experience tuning)

- Envelope percentile (88) & window (0.35·dim): lower percentile eats glass
  tint; smaller window lets illumination follow wisps.
- Mark detector thresholds: black-hat smoothstep (0.08–0.16), chroma-anomaly
  smoothstep (0.075–0.13). At (0.06/0.05–0.10) the mask hit 15 % and wiped real
  streaks; at (0.14 binary) the pencil was missed. This is the most brittle
  part of the pipeline.
- `bg` saturation scale (0.25) and confidence desat scale (0.35): the knob
  between "lawn leaks into T" (too loose) and "blue glass streaks get washed
  out" (too tight). Current values are a compromise; both artifacts are
  faintly present.
- Milkiness texture scale (0.07 relative std) + median-5 prefilter: without
  the median, sparkle punches h≈0 holes in milky regions.

## 8. Open problems (keyed)

- **OP-1 shadow-vs-wisp**: a soft hand/frame shadow on the sheet is locally
  identical to gray glass structure. Single-photo fixes are weak; a cast-shadow
  detector (geometry from the sheet border? penumbra profile?) or user scribble
  may be needed.
- **OP-2 mark-detector generality**: the chroma-anomaly cue assumes the pigment
  color differs from the glass. A *white* grease pencil on white opal, or black
  marker on dark glass, will not be detected. Also 11 % false-positive area on
  wispy (soft impact but real).
- **OP-3 h has no ground truth**: needs M3 (second lighting) or a physical
  measurement (sheet on a printed pattern) to validate the heuristic.
- **OP-4 tint/illuminant ambiguity**: for `cathedral`/`dark` classes the
  illuminant is assumed neutral — a warm photo makes a warm T. A white-balance
  anchor (the sheet's paper label? the hand?) could help.
- **OP-5 sky-through-clear vs milky**: bright + smooth + desaturated describes
  both a milky region and sky seen through clear glass. Currently resolved in
  favour of milky (h high). Wrong for large clear panes against sky.
- **OP-6 sparkle**: transmitted lensing glints vs front-surface speculars are
  conflated; suppression costs texture (see failure 3).
- **OP-7 T is relative**: p99-normalized; absolute transmittance would need a
  reference (exposure metadata + known light, or the label paper as white ref).
- **OP-8 metric choice**: quarter-res background in M1 is a modeling decision;
  a sharper background layer would lower error but weaken the metric's teeth.

## 9. What to try next

1. **M3 cross-lighting validation** the moment second-shot photos land
   (batch mode is ready; add pairs to `benchmark/manifest.json`).
2. Gradient-domain illumination estimation (Poisson solve keeping only
   gradients that milky-weighted evidence assigns to the backlight) instead of
   the percentile envelope — should recover contrast lost in failure 4.
3. Replace the diffusion fill with a matting-Laplacian / guided upsample of `T`
   confidence — crisper boundaries between clear streaks and opal.
4. Track B (heavy compute is allowed per the reframe): off-the-shelf intrinsic
   decomposition / de-lighting networks as an illumination-and-shadow prior —
   specifically targeting OP-1, which classical cues cannot resolve.
5. Extend Track C: the VLM could also answer *multiple-choice* questions like
   "is there handwriting on the sheet: none / bottom-left / bottom-right / …"
   to gate and localize the mark detector (still no numeric regression).
