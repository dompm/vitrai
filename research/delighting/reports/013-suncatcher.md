# Report 013 — The Suncatcher Benchmark: real end-to-end de-light vs raw-copy

Date: 2026-07-09. Branch: `research/delighting-suncatcher` (off
`research/delighting-combined`). Code: `suncatcher_bench.py`, extractor
`extract.py` @ the fixed classical (report 009). Deliverables:
`results/suncatcher/{panel_assembly.jpg, closeup_worst_GT_PIECE_2.jpg,
metrics.json}`, this report. **No PR.**

This is the first benchmark that touches **real** assets end-to-end instead of
synthetic renders. The app's onboarding tutorial ships a real pair: a photo of a
physical stained-glass suncatcher (`orange-pattern.jpg` — an orange with three
green leaves, backlit in a window) plus photos of the raw hammered glass tiles
(`green.png`, `orange.png`), plus the tutorial's ground-truth piece polygons
(`GT_PIECE_1..4` in `frontend/src/components/Tutorial/types.ts`), which are drawn
**on** the pattern photo and so are pixel-aligned to the real object.

## 0. Provenance — read this first (it bounds every claim below)

Confirmed by the maintainer, and it changes what this benchmark can prove:

1. **The pattern photo was NOT cut from the same physical glass as the sheet
   photos.** Different glass. Visible in the panel: the reference leaves are a
   bright *lime/yellow*-green; the green sheet is a deep *emerald/bottle*-green.
2. **The reference photo carries its own baked window light** (bright sky top-left,
   railing/building behind), independent of the sheet photos' garden backlight.

Therefore **absolute per-piece color vs the reference is not an accuracy claim.**
It is reported only as "style distance" and must not be read as fidelity. What the
assets *can* support without a true reference is the metric the whole project is
really about:

> **cross-piece consistency / lighting-invariance** — pieces cut from one sheet
> should preview as the same glass regardless of which patch of the sheet they were
> sampled from. Raw-copy bakes in each patch's local backlight; de-lighting should
> remove it.

That question needs no ground-truth color, so it is the **primary** result here.
The reference photo's role is a **qualitative realism anchor** for the side-by-side
panel ("this is what a real backlit suncatcher looks like"). The global illuminant
fit is **presentation** (make the two composites comparable to the reference's
overall warmth), not measurement — the *same* per-channel model is fit for both
conditions, so it grants neither an advantage.

## 1. Method (and its honest deviations)

**Compositing** reimplements `ResultPanel.PieceOverlay` (`rotation=0`): a pattern
pixel `P` samples sheet coordinate `glass = t + scale·(P − centroid)`, clipped to
the piece polygon. Two conditions, identical geometry:

- **RAW-COPY** (current app): sample the raw linear sheet photo.
- **RELIT**: run the fixed classical extractor on each sheet → intrinsic
  transmittance `T`; the relit material is `T·(h + (1−h)·1)` (plain bright backdrop
  `B=1`; both sheets classify **cathedral-clear**, `h_mean ≈ 0.06`, so ≈ `T`).

**Deviations from the literal app, documented, applied to both conditions equally:**

- `DEFAULT_PROJECT.pieces` is **empty** — the tutorial builds transforms
  interactively, so **no transform is stored** in the repo. The brief assumed
  stored `{glassSheetId, x, y, rotation, scale}`; that turned out not to exist. We
  parse only the GT polygons and **synthesize** transforms.
- We sample the **glass interior only** (auto-detected tile bbox, eroded off the
  wood frame / label sticker / sill reflection). The app's literal default centers
  a piece on the *whole* sheet photo, i.e. it would sample frame + garden
  background — a strictly worse raw-copy, and not the interesting comparison. (Note
  this means the honest raw-copy pain in the real app is *larger* than measured
  here; we sanitized it to isolate the within-glass question.)
- Scale is chosen so each piece occupies <½ the interior, leaving room to translate
  it for the position-sensitivity test.

**Piece→sheet:** `GT_PIECE_1` = orange slice → orange sheet; `GT_PIECE_2/3/4` =
leaves → green sheet (matches the tutorial's `isOrange = matchedGt === GT_PIECE_1`).

**Metrics** (piece pixels only, polygon eroded 6–9px to drop solder edges / bleed):

- **M1 cross-piece consistency** — dispersion of the 3 green leaves' piece-mean
  colors (each leaf placed at a distinct interior column).
- **M2 lighting-position sensitivity** — each piece sampled at a 3×3 grid of sheet
  positions; dispersion of its own piece-mean across the 9 positions. This is the
  cleanest test and needs no cross-piece placement assumptions.
- Dispersion reported three ways because no single lens is honest here:
  **Lab dE76** (perceptual), **lum_cv** (std/mean of linear luminance — scale- and
  saturation-free), **hue_std** (circular std of Lab hue angle).
- **M3 style-distance** — piece-mean dE76 vs the reference, after the presentation
  illuminant. Labeled not-accuracy per §0.

## 2. Results

### 2.1 Sheet-interior flatness (pixel-level; lower = flatter)

How much spatial variation de-lighting removes from the glass, before any piece
averaging:

| sheet | CV raw → relit | low-freq CV raw → relit |
|---|---|---|
| green | 0.946 → **0.735** (−22%) | 0.621 → **0.449** (−28%) |
| orange | 0.606 → **0.404** (−33%) | 0.392 → **0.239** (−39%) |

De-lighting **does** flatten the tiles — it removes a real smooth illumination
envelope `L` (the extractor's estimated `L` is a clean top-bright falloff; see the
raw/`T`/`L` decomposition described in §3). This is the classical method's genuine
strength and it shows up clearly.

### 2.2 M1 — cross-piece consistency (3 green leaves)

| lens | raw | relit |
|---|---|---|
| Lab dE (mean→centroid) | **2.53** | 2.76 |
| lum_cv | 0.121 | **0.113** |
| hue_std (deg) | 0.5 | 0.6 |

### 2.3 M2 — lighting-position sensitivity (per piece, 9 sheet positions)

| piece [sheet] | Lab dE raw→relit | lum_cv raw→relit | hue raw→relit |
|---|---|---|---|
| orange-slice [orange] | 7.71 → 6.82 | 0.257 → **0.183** | 2.8 → 3.8 |
| leaf-R [green] | 9.68 → 10.88 | 0.486 → **0.350** | 1.2 → 1.0 |
| leaf-L [green] | 9.25 → 11.10 | 0.436 → **0.360** | 1.0 → 0.8 |
| leaf-far-L [green] | 9.27 → 11.69 | 0.448 → **0.378** | 1.0 → 1.1 |
| **aggregate** | **8.98 → 10.12** | **0.407 → 0.318 (−22%)** | 1.5 → 1.7 |

### 2.4 M3 — style-distance vs reference (NOT accuracy)

| piece | raw dE | relit dE |
|---|---|---|
| orange-slice | 11.0 | **7.8** |
| leaf-R | 41.4 | 40.6 |
| leaf-L | 38.0 | 38.0 |
| leaf-far-L | 36.6 | 36.5 |

The orange moves closer to the reference under relight; the leaves stay ~37–41 dE
away in both conditions — that is the **different-glass** fact (deep emerald sheet
vs lime reference), not an extractor failure, and no method operating on this sheet
could close it.

## 3. The verdict — split along the two difficulty axes, and it is honest

**Did de-lighting move the preview measurably toward reality? Partly, on exactly the
axis the classical method owns, and not on the axis it doesn't.**

- **Brightness / smooth-envelope axis: YES.** Every luminance measure improves under
  relight — pixel CV −22 to −33%, and the product-level lighting-position
  luminance-CV −22% aggregate (−12 to −29% per piece). If an artist samples the same
  leaf from a bright vs dark patch of the sheet, the relit preview's *brightness*
  disagrees measurably less. This is the "shadow + brightness-gradient
  normalization" difficulty (1) that `RESEARCH_STATE.md` calls tractable — and here,
  on real glass, it delivers.

- **Perceptual color / see-through axis: NO (slightly worse).** Lab dE does **not**
  improve; cross-piece 2.53 → 2.76, position aggregate 8.98 → 10.12. Two causes,
  both real: (a) **dE inflates with saturation** — de-lit `T` is a deeper, more
  saturated glass color, so the same *relative* variation maps to a larger
  perceptual distance (this is why lum_cv, which is saturation-free, tells the
  opposite and fairer story); and (b) the residual that survives extraction is the
  **transmitted garden bokeh + hammer relief** of *transmissive cathedral glass* —
  the `photo = T·B` see-through-background separation that `RESEARCH_STATE.md` names
  as ill-posed / difficulty (2) / "the north-star hard case." The `T` map for the
  green sheet is visually almost identical to the raw tile (the extractor removes a
  gentle `L` envelope but the mid-scale bokeh discs and relief remain in `T`), so
  the residual position-to-position color swing is essentially unremoved.

So the benchmark's honest claim: **de-lighting improves the internal
brightness-coherence and lighting-invariance of the preview for real hammered
cathedral glass, but not its color-coherence, because the dominant residual is
see-through background that classical extraction cannot separate from a single
photo.** That is not a disappointment — it is the *same* boundary every synthetic
report drew (007/008/009), now confirmed to hold on real glass rather than only in
Cycles.

## 4. Own-eyes read of the panel (`panel_assembly.jpg`)

- Both composites read as **one coherent object**, not a collage — but note that is
  partly because we sampled clean interior glass; the win is real but modest, not
  dramatic.
- The **relit** leaves are a deeper, more saturated emerald and the orange a richer
  amber; the **raw** version is lighter, more golden-yellow, with more visible
  specular hammer glints (little photographic highlights). The relit side reads a
  touch more like *solid backlit glass* and less like *a photo of glass* — the
  qualitative de-lighting benefit, consistent with the modest numbers.
- Against the **reference**: neither composite reproduces the reference's soft
  internal glow (bright center from the sky behind) because the fitted illuminant is
  near-flat — the reference's own baked light is a per-object thing the flat preview
  intentionally does not copy. And the reference's *lime* leaves make the
  different-glass fact impossible to miss.
- `closeup_worst_GT_PIECE_2.jpg` (the leaf at 9 sheet positions) is the clearest
  single image: both rows swing from bright to dark green across positions; the
  relit row is marginally deeper and marginally more even in brightness, but the
  position-dependence plainly persists in both. This is the see-through residual,
  made visible.

## 5. Biggest remaining realism gap

Ranked:

1. **See-through background separation for transmissive glass** (the color axis
   above). This, not solder or the illuminant model, is what caps the consistency
   win on cathedral glass. It is the documented ill-posed case and is the strongest
   argument for the **learned track** — a single photo cannot split `T·B`.
2. **The illuminant/relight model is flat.** The real suncatcher glows because a
   spatially-varying backlight shines *through* it; our preview multiplies by a
   near-constant gain. A believable preview eventually needs a real relight stage
   (2D gradient light + the 3D lamp PBR that was spiked and shelved), not just a
   global gain.
3. **Solder** is a minor gap here — the reference's leaded seams have real metallic
   sheen; we draw flat dark polylines. Masked out of all metrics, and visually a
   small contributor, but it is a piece of the "it's a photo vs it's a render" tell.

## 6. What would make absolute fidelity testable (a capture ask)

This benchmark cannot measure fidelity to a *specific* real piece because the
assets are mismatched glass. It becomes a true ground-truth eval the moment the
maintainer captures a **matched** set: photograph one real sheet, cut a real piece
from a **known region** of it, assemble/backlight it, and photograph the result.
Then raw-copy and relit can be scored as absolute color/appearance error against a
real cut piece of the *same* glass — the one thing missing today. Until then,
consistency (M1/M2) is the trustworthy number and absolute color (M3) is style only.

## 7. Files

- `suncatcher_bench.py` — parser (regex over the TS polygon literals), sheet
  interior detection, compositing reimpl, the three metrics, illuminant fit, panel
  + closeup rendering. Self-documenting header covers every deviation.
- `results/suncatcher/panel_assembly.jpg` — reference | raw-copy | relit, full
  assembly.
- `results/suncatcher/closeup_worst_GT_PIECE_2.jpg` — worst piece (leaf-R) at 9
  sheet positions, raw vs relit.
- `results/suncatcher/metrics.json` — all three metrics, three lenses each, plus
  interior-flatness diagnostics and the fitted illuminants.
