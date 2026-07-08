# Report 003 — Absolute transmittance scale

Date: 2026-07-08. Code: `extract.py` @ this commit. Panels: `results/library/`.
Worked in a throwaway worktree (`.claude/worktrees/delight-003`) on
`research/delighting`; main checkout untouched.

Read reports 001 (model, metrics) and 002 (library batch, harness) first. This
iteration fixes one defect the maintainer caught in the 002 review: **the black
sheet's `T` was physically wrong** — it rendered as bright grey-green when black
glass transmits a few percent at most, so in a lamp render that sheet would glow.

## 1. The bug and its root cause

The pipeline ended with `T = T * (0.97 / percentile(T, 99))` — every sheet's
brightest 1 % of glass was stretched to 0.97. That is right for clear glass
(its clearest pixels really do transmit ~95 %) but nonsense for **dark-opaque**
glass, which has no clear pixel: its brightest fleck is still nearly opaque, and
stretching it to 0.97 inflated the whole map. Black came out `T_mean` **(0.21,
0.24, 0.19)** — ~21 % grey-green.

Why no metric caught it: per-image exposure is unknown, so the split between the
illumination scale `L` and the transmittance scale `T` is a **gauge the photo
does not fix** — `L` silently absorbs whatever global level `T` gives up. The
self-recon metric M1 reconstructs `I ≈ L·T·(…)`, so it only ever sees the
product `L·T`; it is *structurally blind* to how that product is split into `L`
and `T`. Black's self-recon MAE was a healthy 0.80 with a completely wrong `T`,
because `L` had quietly gone dark to compensate. Dark glass is simply where the
lie is visible to the eye (a near-opaque sheet rendered as translucent grey).

## 2. The fix — a class-prior absolute anchor (with the gauge moved honestly)

I anchor the gauge with a **class prior**: the clearest glass of each class
transmits a known fraction, so I scale `T` to hit that target at a chosen
percentile (`T_ANCHOR` in `extract.py`):

| class | percentile | target | rationale |
|---|---|---|---|
| cathedral-clear | p99 | 0.95 | clearest glass ≈ 95 % (≈ the old 0.97, so unchanged) |
| wispy | p99 | 0.95 | has clear streaks that reach near-clear |
| opalescent | p99 | 0.80 | milky: even the brightest is translucent, not clear |
| dark-opaque | p99 | 0.10 | brightest fleck ≈ 10 %; the median lands near-black |

Crucially, when I scale `T` by `k` I also move `L → L/k` and `R → R·k`, so the
product `L·T` — and therefore the entire self-recon — is **exactly invariant**.
The anchor changes only `T`'s numeric level (the deliverable), not the photo fit.
This is the honest way to state the gauge argument: I am not "improving" `T`
against any ground truth (there is none); I am choosing where to place a scale
the photo genuinely cannot determine, using the class as the tie-breaker (same
role the class prior plays everywhere else in this pipeline).

**Chosen anchor: class prior. Why not the physical cues the maintainer floated —**

- *Border pixels of bare backlight.* Would give an absolute white reference, but
  the library crops (and most casual photos) contain no margin of unattenuated
  light source; the sheet fills the frame. Not reliable enough to depend on.
- *Specular ceiling.* Front-surface speculars are already suppressed (W3) and are
  conflated with transmitted lensing glints (OP-6); using them as a white anchor
  would reintroduce exactly that ambiguity.

The class prior needs no such luck and reuses a signal we already have.

**Failure modes of the class-prior anchor (honest list):**

1. **Mislabeled class flips the scale.** A dark cathedral sheet wrongly called
   `dark-opaque` gets crushed to near-black; a `dark-opaque` sheet called
   `cathedral-clear` blows up bright (the old bug). The anchor is only as good as
   the class, so it inherits every class-detection failure in OP-1/OP-4.
2. **Within-class scale variation is unmodeled.** All `dark-opaque` sheets are
   pinned to the same 10 % ceiling; a genuinely blacker or a slightly-more-open
   sheet is off by the ratio of its true clearest transmittance to 0.10.
3. **The target numbers are priors, not measurements** — round values picked to
   look right, defensible to ±0.05 at best. Absolute transmittance to a real
   physical unit still needs a reference (exposure metadata + known light, or a
   white card in frame). This is OP-7, narrowed but not closed.
4. **p99 can latch onto an outlier.** For `dark-opaque` the brightest 1 % may be
   a residual specular fleck; anchoring to it makes the whole map a touch bright.
   p99 (not p100) is the guard; it held on black here, but a heavily-glinting
   dark sheet is the case to watch.

## 3. Result — black comes out dark, the other 8 do not break

**Before/after: `results/library/black_scale_before_after.jpg`.** `T_mean` went
**(0.21, 0.24, 0.19) → (0.02, 0.03, 0.02)** — from 21 % grey to ~2 % near-black,
with the hammered texture preserved. The relit-warm panel changed from a bright
yellow-green **glow** to a dark olive: a lamp render now keeps black glass dark.
Self-recon MAE **0.80 → 0.78** (essentially unchanged, as the gauge argument
predicts). This is the headline win, verified on the image.

| sheet | class | MAE 002 | MAE 003 | p95 003 | h_mean | `T_mean` | verdict |
|---|---|---|---|---|---|---|---|
| green | cathedral-clear | 0.67 | 0.64 | 3.5 | 0.06 | (.03,.48,.09) | pass, best in set |
| **black** | **dark-opaque** | 0.80 | **0.78** | 4.4 | 0.26 | **(.02,.03,.02)** | **fixed — now near-black** |
| turquoise | cathedral-clear | 1.73 | 1.71 | 10.1 | 0.06 | (.05,.41,.39) | pass |
| pink | cathedral-clear | 2.17 | 2.11 | 13.7 | 0.06 | (.60,.17,.26) | pass |
| orange | cathedral-clear | 2.14 | 2.11 | 11.7 | 0.06 | (.87,.33,.01) | pass |
| amber | cathedral-clear | 2.16 | 2.12 | 11.9 | 0.06 | (.75,.42,.02) | pass |
| red | cathedral-clear | 3.07 | 2.95 | 15.7 | 0.06 | (.79,.03,.06) | pass, deep-red hotspot residue |
| blue | cathedral-clear | 3.56 | 3.45 | 23.4 | 0.06 | (.06,.26,.75) | weakest — backlight hotspot (as 002) |
| **white** | **opalescent** | 0.90* | 3.98* | 17.0 | 0.46 | (.52,.54,.55) | reclassified — see §4 (*MAE not comparable across classes) |

The 8 cathedral-clear sheets are near-identical to 002 (their `k ≈ 1`); the
small MAE dips are the R/T-consistency side effect below. No sheet regressed.

**Side effect worth flagging honestly.** Rescaling `R` in lockstep with `T` also
corrected a latent inconsistency in the *background* term of the self-recon: 002
scaled `T` but left `R` un-scaled, so `B = clip(R/T)` was biased by the same
factor. Fixing it dropped the benchmark **wispy** self-recon MAE **2.40 → 0.79**
and nudged every sheet down slightly. The wispy `T` map itself is unchanged (same
contrast, same SKU removal — verified on `results/difficult_wispy_panel.jpg`); it
is the reconstruction that got more consistent, not the map that got better. I am
calling this out rather than claiming a 3× quality jump.

## 4. The white sheet — VLM was right, the manifest was stale

The maintainer's eye ("white looks opalescent, `h_mean` 0.09 is wrong") checks
out. Asked directly, the VLM classifies `white.jpg` as **opalescent**. But the
002 library `manifest.json` **hard-coded** `white → cathedral-clear`, and the
manifest wins over the VLM in batch mode — so the batch ran the wrong class. That
is the bug: **a stale hand-written class default overriding the correct VLM
answer**, not a pipeline error.

Reclassified `white → opalescent` in the manifest. `h_mean` went **0.09 → 0.46**
and `T` is now milky mid-grey (0.52, 0.54, 0.55) with real haze structure in the
`h` map — it reads as diffuse opal, not clear glass (see the contact sheet's
bottom row). Its self-recon MAE (3.98) is not comparable to the 002 value (0.90)
because the class — hence the whole `h`/`T`/anchor path — changed.

Process note for the maintainer: the VLM had the right answer in 002; we just
didn't use it. Options going forward are to trust `--vlm` for class in the
library batch, or to treat manifest classes as reviewed ground truth and keep
them current. (Caveat: the VLM's *mark* localization is less reliable — it
reported a nonexistent mark on the clean `black` swatch — so `mark_region` still
wants a human or `none` for the library.)

## 5. Contact sheet + harness

`results/library/contact_sheet.jpg` regenerated with the new maps and the white
reclassification. `register_pair.py` updated to use the anchored `L`/`R` returned
by `extract_maps` (so A's `T` and B's illumination are crossed on the same
absolute scale); re-verified on the synthetic pair (ORB 400 inliers, T-agreement
MAE 6.2/255). Still awaiting the real `~/Downloads` validation pairs.

## 6. Open problems — status

- **OP-7 (T is relative)**: narrowed. `T` now carries an absolute *class-anchored*
  scale, good enough that dark glass reads dark and relights without glowing.
  A true physical unit still needs an in-frame reference; the class anchor is a
  prior, not a measurement (§2 failure modes).
- **New dependency**: absolute scale now rides on the class label, so class
  detection (OP-4) and its manifest defaults (§4) matter more than before — a
  class error is now also a brightness error.
- **OP-1 shadow/wisp, OP-6 sparkle, blue/red hotspot residue**: unchanged from
  002; still the top of the next list, still gated on the validation pairs.

## 7. Ship read

Against "reproduce the easy case faithfully": the 002 verdict stands and the one
physically-wrong sheet (black) is fixed and verified on the image — it is now
near-black and relights dark. White is corrected to opalescent. All 9 library
sheets now render plausibly under a lamp, which is the concrete downstream use.
The remaining gaps (blue/red hotspot, wispy hand-shadow) are quality, not
correctness, and neither blocks the easy-case criterion.
