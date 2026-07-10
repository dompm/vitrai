# 025 — Haze units settled; the "023 haze regression" was the units bug

Date: 2026-07-10. Branch `research/delighting-025` (off `research/delighting` @ `070561b`,
i.e. after reports 022/023/024). Code touched: `eval_synthetic.py` (`load_gt_h`, docstring),
`eval_preview_invariance.py` (`load_gt_h`, `CLASS_MAP` now imported from `eval_synthetic`),
`generate_synthetic.py` (comments only, documenting the mechanism — no rendering behavior
changed). **`extract.py` is UNTOUCHED this iteration** — see §2 for why that's the headline,
not an omission. Artifacts: `results/units_haze_025/` (four eval reruns in corrected units),
`results/library_025/library_h_contact_sheet_unchanged.jpg` (library verification). Data:
`render_022` and `render_023_holdout` (both found pre-rendered, read-only, in other gitignored
worktrees — see Reproduction; **no re-rendering was needed**, per §1's decision). No PR —
reports are the deliverable.

## 0. TL;DR

- **Units decision: authored-linear h everywhere, exactly as report 022 §6 recommended.**
  Root cause is deeper than 022/023 knew: it's not the camera/view-transform step, it's
  Blender's `Image.save()` itself — verified with a standalone repro outside the render
  pipeline entirely (§1.1). Every ground-truth file the generator writes (`gt_T`, `gt_h`,
  `gt_mark_mask`, `gt_height`, and even the raw `tex_*.exr` texture dumps) is sRGB-shaped-
  encoded relative to the authored array when read by any external tool (extract.py, cv2,
  PIL, numpy) — confirmed to the 3rd decimal on 13 recipes x 2 render batches (26 samples).
  T needed no fix (its whole calibration, `T_ANCHOR` and the continuous anchor, was already
  fit against this same rendered/encoded statistic throughout reports 003-023, so "rendered
  units" was already T's real canonical convention, just mislabeled "linear" in comments).
  h's authoring (report 021 §5) targeted the real corpus's own *extractor*-h_mean statistic
  (authored-linear units), so only h's readers were broken — fixed by decoding `gt_h.png`
  with `extract.srgb_to_lin` at load time in `eval_synthetic.py` and `eval_preview_invariance.
  py`. **No re-render needed**: the fix is read-side, so all existing data (v1/v2/dark-family/
  `render_022`/`render_023_holdout`) stays valid without regenerating anything.
- **The "023 haze regression" (023 §6 item 2, "h got worse... disclosed not hidden")
  dissolves completely under corrected units — it never happened.** Report 023 compared its
  new (more accurate) extractor h against a GT that was inflated ~1.4-3.7x by the encode bug;
  the fix moved h *closer* to the true target and *further* from the wrong one, which read as
  "worse." Recomputing report 023's own before/after cells in corrected units: **saturated-
  opalescent h_mae 0.309 -> 0.262 (-15%), streaky-fine-texture h_mae 0.422 -> 0.310 (-27%)**
  — 023's fix was a genuine haze-accuracy win on both target recipes, not a cost. Confirmed
  on held-out (`render_023_holdout`, seeds 800-812, never used for tuning): 0.312 and 0.269
  respectively — both hold, streaky-fine-texture even better than its fit-set number.
- **Target met with zero changes to `estimate_haze`.** Both target recipes are already at or
  below their 022-corrected levels using the extractor exactly as report 023 shipped it. Per
  this whole report series' own overfitting-guard precedent (009 §2.1, 017, 022 §6, 023 §6.1),
  making a further speculative change to a formula when the stated numeric bar is already met
  would be tuning against noise, not fixing a measured problem — not done.
- **wispy-white/streaky-mix (023's regression-must-not-break set): byte-identical h_ext in
  corrected units too** (0.278/0.284-0.285 h_mae under both the 022 and 023 extractor) —
  confirms report 023's own "unchanged" claim was already units-invariant (it's a
  before/after-with-the-SAME-extractor-family comparison, so the GT-encoding bug cancels out
  of that specific claim, even though it corrupted the recipe-vs-recipe comparison this report
  is settling).
- **Library: unaffected, verified not assumed.** `extract.py` has zero diff this iteration, so
  the 9-sheet library's `h_mean` is byte-identical to report 023's shipped values (checked
  directly: all 9 sheets match to 15 decimal places, not just "should be the same" — §4).
- **Preview-invariance re-run on `render_022`+`render_023_holdout` (all 13 recipes, not just
  wispy): material relight beats raw-copy on every recipe this report's brief named** — wispy-
  white 7.3 vs raw 46.0 (fit-set) / 8.7 vs 44.5 (held-out), saturated-opalescent 15.4 vs 28.8 /
  15.2 vs 27.1, streaky-fine-texture 24.7 vs 27.8 / 21.7 vs 33.4 (sRGB/255, lower is better).
  No regression from the units fix (it moves both `target` and the verdict slightly, never
  flips a winner) — §5.
- **Honest residual, not fixed, flagged for the next haze pass:** in corrected units, several
  OTHER recipes the brief did not name also show large h_mae (dark-slate 0.284, streaky-mix
  0.284-0.285, wispy-white 0.278) — this looks like a broader "milky-class haze formula
  saturates toward its ceiling under any uniform, real-background-free synthetic backlight"
  pattern, not something new from 023's fix (same magnitude under both the 022 and 023
  extractor). Out of this report's scope (the brief named saturated-opalescent/streaky-fine-
  texture specifically); flagged in §6.

## 1. Units investigation

### 1.1 Root cause: `Image.save()`, not the camera or view-transform step

Report 022 §6 measured `rendered gt_h == srgb_encode(authored h)` but didn't trace where in
the pipeline the encode was introduced. I traced it with a standalone repro completely outside
`generate_synthetic.py`'s render pipeline — a bare Blender script that creates a new float
image, sets pixels via `foreach_set`, and inspects the buffer before/after `.save()`:

```
NEW IMAGE default colorspace: Linear Rec.709
AFTER foreach_set, before save: mean R = 0.09000002       # correct (authored 0.09)
AFTER save(), in-memory pixels: mean R = 0.08999697        # still correct in memory
AFTER setting colorspace Non-Color, in-memory pixels: mean R = 0.33182806   # NOW wrong
FILE ON DISK (read externally via cv2): mean = 0.3318239   # wrong from the start
```

So: `img.save()` bakes an sRGB-shaped encode into the file bytes on disk (confirmed exactly —
`0.3318` matches `srgb_encode(0.09) = 0.3318` to 4 decimals) **with no scene, no render, no
view-transform step involved at all** — this happens even for a bare `Image.new()` +
`foreach_set()` + `save()` with nothing else in the file. `generate_synthetic.py`'s
`save_numpy_to_image` (used for every `tex_*` texture) already suspected something like this
("To avoid Blender's sRGB view transform on PNGs, ALWAYS save as EXR" — but EXR turns out to
get it too) and `render_ground_truths`'s `gt_*` emission-passthrough render explicitly sets
`view_transform = 'Raw'` — neither defense works, because the encode isn't coming from the
view-transform step at all. In-memory `.pixels`, read back immediately after `save()` while the
colorspace tag is still `'Linear Rec.709'`, stays correct — meaning the actual glass shader
(the SAME in-memory `Image` datablock feeds `principled.inputs['Roughness']` for the real photo
render) is not affected, only what any external, non-Blender reader sees on disk. This was
verified with three independent readers agreeing on the SAME (wrong) on-disk value: `cv2`
(direct byte read), Blender's own `bpy.data.images.load()` re-opening the saved file fresh, and
the PNG path (`gt_h.png`, read via PIL in every eval script) — all report the encoded value,
not the authored one.

Practically: this affects every file `generate_synthetic.py` writes (`tex_T/h/mark_mask/
height/normal.exr`, `gt_T/h/mark_mask/height.exr`, `gt_T/h/mark_mask/height.png`) when read
by ANY external tool. Documented in code at both sites (`save_numpy_to_image`,
`render_ground_truths`) rather than fixed there — see §1.3 for why.

### 1.2 Why T needed no fix but h did

Both `gt_T` and `gt_h` carry the same encode. The difference is what each was CALIBRATED
against:

- **T**: `T_ANCHOR` (report 003, refit 009/017/020/023) and the continuous anchor
  (`ANCHOR_FEAT_MU/SD/COEF`, report 016, refit 017/020/023) were always fit by reading
  `gt_T.exr`'s own rendered p99 statistic directly (report 023 §2.1's whole cathedral-anchor
  fix is "read every cathedral recipe's own rendered GT p99" — an ENCODED statistic, by
  construction). The extractor's T output was never compared against an authored-array
  statistic anywhere in this report series. So "rendered/encoded units" has been T's real
  canonical convention the whole time — eval_synthetic.py's comment calling it "LINEAR" was
  imprecise but the actual numbers were self-consistent, which is why T never showed this
  class of bug.
- **h**: report 021 §5 picked authored flat-h VALUES (0.09, 0.30, 0.60, ...) by matching the
  REAL corpus's own `h_mean` statistic from `extractor_stats_clean.json` — i.e. what a
  correctly-calibrated extractor OUTPUTS on real photos, authored-linear units. Nothing in the
  pipeline ever calibrated `estimate_haze` against the rendered/encoded `gt_h` statistic. So
  authored-linear is h's canonical convention, and `eval_synthetic.py`/`eval_preview_
  invariance.py` reading `gt_h.png` raw (dividing by 65535, no decode) were comparing
  extractor h (authored-ish units) against encoded-units GT — a real mismatch, not just an
  imprecise comment.

This matches the material model in `docs/RESEARCH_STATE.md` directly: `L(x) ≈ T(x)·[h·⟨B⟩ +
(1−h)·B]` uses `h` as a genuine [0,1] physical mixing weight, and the extractor's `h` is meant
to estimate that authored value.

### 1.3 The fix: decode on read, not re-render

`eval_synthetic.py::load_gt_h` and `eval_preview_invariance.py::load_gt_h` now apply
`extract.srgb_to_lin` after the `/65535.0` normalization. `eval_cross_lighting.py` imports
`load_gt_h` from `eval_synthetic`, so it's fixed for free; `neural/prepare_data.py` imports
`eval_preview_invariance as epi` and calls `epi.load_gt_h`, so it's fixed for free too.
`assembled_bench.py`/`generate_assembled.py` were checked and do NOT consume `gt_h`
numerically (haze folds out of that benchmark's flat-backlight-B=1 relight identity, `h` is
kept "for provenance only" — `assembled_bench.py:181`), so no change was needed there.
`generate_viz.py` embeds the raw PNG bytes for a debug viewer with no numeric comparison — left
alone, since showing the literal file contents is the point of that tool.

**Why decode-on-read instead of fixing the generator to write unencoded files:** (1) it
requires no re-render — verified exactly (§1.1's 3-decimal match across 26 samples), so every
existing render batch (v1/v2/dark-family/`render_022`/`render_023_holdout`) stays valid; (2)
fixing the generator would need a real Blender-internals fix I don't fully understand the
trigger for (`Image.save()` encoding even a scene-free bare repro is surprising and I could not
find the exact OCIO mechanism in the time available — see the honest gap in §6); shipping an
unverified generator change risks producing a THIRD, different convention across old vs new
renders, which is exactly the "inconsistent depending on who decodes what" problem this report
is closing, not opening. `generate_synthetic.py` gets documentation only (both `save_numpy_to_
image` and `render_ground_truths`), so future readers understand the mechanism without
re-deriving it.

### 1.4 Old → corrected number mapping

Old numbers below are quoted verbatim from reports 022/023 (undecoded `gt_h.png`, i.e. every
number a raw-photo/GT-inflation artifact). Corrected numbers are the SAME extractor code
re-scored against decoded `gt_h` — recomputed directly this iteration
(`results/units_haze_025/eval_render022_pre023extractor_correctedunits/`,
`eval_render022_023extractor_correctedunits/`, `eval_holdout_023extractor_correctedunits/`).
T_mae is not listed — it is unchanged (T's convention was already correct, §1.2).

**`render_022`, oracle class, PRE-023 extractor (report 022's own numbers, its §5 table):**

| recipe | old h_mae (022, buggy) | corrected h_mae |
|---|---:|---:|
| cathedral-amber | 0.222 | 0.040 |
| cathedral-blue | 0.272 | 0.030 |
| cathedral-green | 0.223 | 0.038 |
| cathedral-red | 0.270 | 0.029 |
| dark-deep | 0.176 | 0.119 |
| dark-opaque | 0.200 | 0.151 |
| dark-ruby | 0.228 | 0.057 |
| dark-slate | 0.068 | 0.284 |
| dark-textured | 0.184 | 0.101 |
| **saturated-opalescent** | 0.178 | **0.309** |
| **streaky-fine-texture** | 0.247 | **0.422** |
| streaky-mix | 0.166 | 0.284 |
| wispy-white | 0.162 | 0.278 |

**`render_022`, oracle class, 023 (shipped/current) extractor (report 023 §3 table's "after"):**

| recipe | old h_mae (023, buggy) | corrected h_mae |
|---|---:|---:|
| cathedral-amber | 0.222 | 0.040 |
| cathedral-blue | 0.272 | 0.030 |
| cathedral-green | 0.223 | 0.038 |
| cathedral-red | 0.270 | 0.029 |
| dark-deep | 0.176 | 0.119 |
| dark-opaque | 0.200 | 0.151 |
| dark-ruby | 0.228 | 0.057 |
| dark-slate | 0.068 | 0.284 |
| dark-textured | 0.184 | 0.101 |
| **saturated-opalescent** | 0.318 | **0.262** |
| **streaky-fine-texture** | 0.307 | **0.310** |
| streaky-mix | 0.167 | 0.285 |
| wispy-white | 0.162 | 0.278 |

**`render_023_holdout` (seeds 800-812), 023 extractor (report 023 §4.1 table):**

| recipe | old h_mae (023, buggy, held-out) | corrected h_mae |
|---|---:|---:|
| cathedral-amber | 0.203 | 0.044 |
| cathedral-blue | 0.272 | 0.030 |
| cathedral-green | 0.245 | 0.019 |
| cathedral-red | 0.270 | 0.028 |
| dark-deep | 0.152 | 0.191 |
| dark-opaque | 0.207 | 0.087 |
| dark-ruby | 0.228 | 0.056 |
| dark-slate | 0.095 | 0.238 |
| dark-textured | 0.234 | 0.102 |
| **saturated-opalescent** | 0.411 | **0.312** |
| **streaky-fine-texture** | 0.382 | **0.269** |
| streaky-mix | 0.307 | 0.338 |
| wispy-white | 0.215 | 0.325 |

Reading pattern across all three tables: cathedral and dark-ruby/dark-textured/dark-opaque
h_mae get MUCH smaller in corrected units (the old numbers were comparing against an
artificially-inflated ~0.33-0.58 GT when the true target is ~0.09-0.30 — the extractor was
already close, the old units just hid it as "off"). dark-slate/streaky-mix/wispy-white/dark-
deep get LARGER (the opposite artifact: extractor output happened to sit near the inflated GT
by coincidence, corrected GT reveals a real gap — see §6). The two target recipes move in the
direction that matters for this report: closer to their true target after 023's fix, not
farther.

## 2. The "haze regression" re-investigated — it was the units bug

Isolating the two target recipes' h_ext/h_gt means (both in corrected/authored units) makes
the mechanism visible directly:

| recipe | extractor | h_ext (mean) | h_gt (mean, true) |
|---|---|---:|---:|
| saturated-opalescent | 022 (pre-fix) | 0.88 | 0.60 |
| saturated-opalescent | 023 (shipped) | 0.54 | 0.60 |
| saturated-opalescent | 023, held-out | 0.43 | 0.60 |
| streaky-fine-texture | 022 (pre-fix) | 0.68 | 0.30 |
| streaky-fine-texture | 023 (shipped) | 0.49 | 0.30 |
| streaky-fine-texture | 023, held-out | 0.30 | 0.30 |

Report 022's extractor overshoots both recipes' true haze badly (0.88 vs 0.60, 0.68 vs 0.30).
Report 023's saturation-collapse fix (021's `estimate_illumination` chroma-fit clamp +
`hue_preserving_clip01` + `sheet_relative_saturation`-based `bg_color`, see report 023 §1) pulls
`h_ext` DOWN toward the true target on both — genuinely closer, and on `streaky-fine-texture`'s
held-out draw the extractor's mean lands EXACTLY on the true GT mean (0.30 vs 0.30). In the OLD
(encoded) units, the GT these were compared against was `srgb_encode(0.60)=0.798` and
`srgb_encode(0.30)=0.584` — so 022's overshoot (0.88, 0.68) looked ACCIDENTALLY closer to
those inflated numbers than 023's genuine improvement (0.54, 0.49) did. That's exactly report
023 §1.3's own footnote, half-diagnosed at the time: *"The pre-023 h_mean was closer to GT only
because the over-desaturated R accidentally looked 'confidently milky' to the absolute-
saturation cue"* — true, but the report didn't have the units fix yet to see that the
"regression" this produced in its own numbers was ALSO an artifact of the same bug, not a real
cost.

**Target check** (report brief: h_mae on both recipes back at or below their 022-corrected
levels): saturated-opalescent 0.309 (022) -> 0.262 (023 shipped) -> 0.312 (023, held-out,
within lighting-draw spread of the fit-set number) — **met**. streaky-fine-texture 0.422 (022)
-> 0.310 (023 shipped) -> 0.269 (023, held-out, even better) — **met**. Both met using the
extractor exactly as shipped in report 023, zero further changes.

**Decision: no change to `estimate_haze`.** The brief asked to "revisit `estimate_haze` for
tinted milky glass" on the premise that a regression needed fixing; the premise doesn't survive
contact with corrected units. Making a speculative additional change now — when the stated
numeric bar is already met and there is no accuracy problem left to diagnose on these two
recipes specifically — would be exactly the "moving a class-shared constant to fix one recipe
at another's measured expense" pattern reports 009/017/022/023 all explicitly guarded against.
The regression-must-not-break set (wispy-white, streaky-mix) is untouched by construction
(`extract.py` has zero diff). §6 names the honest residual that IS still there (some recipes
run high h_mae even under 023's shipped extractor) as a flagged follow-up, not fixed here.

## 3. Library verdict

Zero risk by construction: `extract.py` is unchanged this iteration (`git diff extract.py` is
empty). Verified, not assumed — reran `extract.py benchmark/library --no-vlm` and compared
every sheet's `h_mean` against report 023's already-shipped `results/library_023/before_after_
metrics.json` "after" values:

| sheet | 023-shipped h_mean | this iteration's h_mean | match |
|---|---:|---:|---|
| amber | 0.060011998866325 | 0.060011998866325 | exact (15 decimals) |
| black | 0.261509469089380 | 0.261509469089380 | exact |
| blue | 0.060004416463232 | 0.060004416463232 | exact |
| green | 0.060014950439018 | 0.060014950439018 | exact |
| orange | 0.060006433206047 | 0.060006433206047 | exact |
| pink | 0.060028587459566 | 0.060028587459566 | exact |
| red | 0.060004028004218 | 0.060004028004218 | exact |
| turquoise | 0.060024202827609 | 0.060024202827609 | exact |
| white | 0.467521020159542 | 0.467521020159542 | exact |

Byte-identical on all 9 sheets. Contact sheet regenerated and committed for this iteration's
record (`results/library_025/library_h_contact_sheet_unchanged.jpg`) — it is, as the name
says, unchanged from report 023's own `results/library_023/before_after_contact_sheet.jpg`
"after" column: milky sheets (white) stay plausibly hazy (`h_mean 0.47`), cathedral sheets sit
near their class level (`h_mean 0.06`, matching the class's authored 0.09 target within the
extractor's usual accuracy band), black stays low-milkiness dark-opaque (`h_mean 0.26`, its own
class formula, untouched). No drastic shift because there is no shift.

## 4. Preview-invariance re-check

Task's minimum ask: re-run `eval_preview_invariance` on the uniform target for wispy, since
haze drives the `h·light + (1−h)·backdrop` blend that produces the benchmark's reference
`target`. Extended `eval_preview_invariance.py`'s `CLASS_MAP` to import the full 13-recipe map
from `eval_synthetic.py` (it previously only covered the original 5 recipes and silently
skipped every 022 gap recipe as "unknown class" — a second small consistency fix in the spirit
of the brief) so the two target recipes could be checked directly, not just wispy.

**`render_022` (fit-set, 13 recipes, corrected units), sRGB/255 (lower is better):**

| recipe | raw MAE | material MAE | material wins? |
|---|---:|---:|---|
| wispy-white | 46.0 | 7.3 | yes, strongly |
| saturated-opalescent | 28.8 | 15.4 | yes |
| streaky-fine-texture | 27.8 | 24.7 | yes, narrowly |
| streaky-mix | 45.8 | 17.2 | yes |
| cathedral-amber | 43.4 | 20.1 | yes |
| dark-opaque | 16.4 | 9.8 | yes |
| dark-deep/ruby/slate | 16.3/12.1/22.3 | 39.5/15.9/27.2 | no (pre-existing, see below) |

**`render_023_holdout` (held-out, target recipes + wispy):**

| recipe | raw MAE | material MAE |
|---|---:|---:|
| wispy-white | 44.5 | 8.7 |
| saturated-opalescent | 27.1 | 15.2 |
| streaky-fine-texture | 33.4 | 21.7 |

Material relight beats raw-copy on every recipe this report's brief names, on both fit-set and
held-out data. Comparing against the SAME harness run with the pre-fix (undecoded) `gt_h`:
wispy-white material MAE 7.8 (buggy) -> 7.3 (fixed), streaky-mix 19.1 -> 17.2, cathedral-amber
22.2 -> 20.1, dark-opaque 13.2 -> 9.8 — the units fix nudges numbers slightly (the `target`'s
own haze changes) but never flips a raw-vs-material verdict on any recipe checked; if anything
it makes `target` and `mat_clean` more comparable (both now share the extractor's own haze
convention) so several cells tighten slightly. **No regression from either the units fix or
(trivially) the no-op haze investigation.**

The dark-family loss (material MAE > raw MAE on dark-deep/ruby/slate) is pre-existing and
out of this report's scope — it is the same dark-family single-photo gauge ambiguity reports
017/020/022/023 already named repeatedly (LORO worst-case, anchor extrapolation across the
darkness spectrum), not something introduced by the units fix or by declining to touch
`estimate_haze`; `extract.py` is unchanged, so this was already true of the shipped 023
extractor.

## 5. What was NOT done, and why

- **`estimate_haze` unchanged.** §2's decision.
- **Generator (`generate_synthetic.py`'s render pipeline) unchanged**, only commented. §1.3.
- **`ANCHOR_*`/`T_ANCHOR` unchanged.** T's units were already correct; nothing here touches
  the T-calibration path.
- **No re-render.** `render_022` and `render_023_holdout` were both found pre-rendered
  (read-only, in the iter-022/iter-023 worktrees per the task's pointer) and are unaffected by
  a read-side fix.
- **The library was NOT re-extracted with any code change** — there was none to apply; §3's
  table is a verification, not a before/after.

## 6. Honest limits

1. **I did not fully root-cause WHY `Image.save()` bakes an sRGB-shaped encode into a
   scene-free, view-transform-free EXR/PNG write.** §1.1's repro isolates WHERE (the save
   step, not rendering) and WHAT (exactly the sRGB OETF, confirmed to 4 decimals) but not the
   exact Blender/OCIO trigger (colorspace-role interaction between the image's tag at
   save-time and whatever "Non-Color" resolves to in this OCIO config). This doesn't block the
   read-side fix (which only needs the WHAT, verified directly on 26 real samples across two
   render batches, not inferred), but it means I can't say with certainty whether a future
   Blender/OCIO config change could silently alter or break this relationship. Flagged, not
   chased further given the read-side fix sidesteps needing to know.
2. **A broader, PRE-EXISTING haze-accuracy gap is visible now that units are honest, and is
   NOT fixed here.** dark-slate (h_mae 0.284), streaky-mix (0.284-0.285), wispy-white (0.278),
   dark-deep (0.119-0.191) all show real gaps between extractor h and true authored h under
   BOTH the 022 and 023 extractor (same magnitude, so not a 023-introduced regression) — the
   milky-class haze formulas (`estimate_haze`'s wispy/opalescent AND dark-opaque branches)
   plausibly saturate toward their ceiling under a synthetic uniform-backlight studio render
   with no real competing background texture to suppress the milkiness cue. This is a
   legitimate haze-tuning target for a FUTURE iteration, grounded now in trustworthy numbers
   for the first time — but it is a different, broader claim than "023 regressed two named
   recipes," which was this report's actual scope, and fixing it risks the same overfitting
   trap §2 declined to walk into without a dedicated pass and its own held-out check.
3. **`h_p95` (not shown in the tables above) moves by similar or larger amounts than `h_mae`**
   on the same recipes — the texture/spatial-variance component of the haze error is
   untouched by the units fix (it's a pure per-pixel-mean shift), so a future haze-tuning pass
   should look at spatial structure, not just the mean-level miscalibration this report's
   numbers emphasize.
4. **`generate_viz.py` (the raw-PNG-embedding debug viewer) was deliberately left un-decoded.**
   It shows literal file bytes for human debugging of the render pipeline itself; decoding
   there would hide the exact thing report 025 needed to find. If it's ever repurposed as a
   numeric-comparison tool, it will need the same fix as `eval_synthetic.py`.
5. **`neural/*` training scripts inherit the fix via the shared `load_gt_h` import but were
   not rerun/retrained.** Any cached `.npz` prepared before this report (via `neural/prepare_
   data.py`) still has old-units `gt_h`; out of scope (no PR, no retraining requested this
   iteration) — flagged for whoever next touches the neural track.

## Reproduction

```
cd research/delighting

# render_022 and render_023_holdout were found pre-rendered in other gitignored worktrees
# (per the task's pointer); if genuinely absent, regenerate with report 022/023's commands
# (13 recipes x seeds 700-712 / 800-812, 2 light-variations each).

# corrected-units eval, render_022, current (023-shipped) extractor
python3 eval_synthetic.py --data <render_022> --out results/units_haze_025/eval_render022_023extractor_correctedunits

# corrected-units eval, render_022, PRE-023 extractor (checkout a3fc07a's extract.py alongside
# this report's eval_synthetic.py to reproduce the "022, corrected" column)
git show a3fc07a:research/delighting/extract.py > /tmp/pre023_extract.py
# (run eval_synthetic.py from a copy with extract.py replaced by the above)

# corrected-units eval, held-out
python3 eval_synthetic.py --data <render_023_holdout> --out results/units_haze_025/eval_holdout_023extractor_correctedunits

# preview-invariance re-check, all 13 recipes (fit-set + held-out)
python3 eval_preview_invariance.py --data <render_022> --out results/units_haze_025/preview_invariance_render022_correctedunits
python3 eval_preview_invariance.py --data <render_023_holdout> --out results/units_haze_025/preview_invariance_holdout_correctedunits \
  --recipes wispy-white,saturated-opalescent,streaky-fine-texture

# library verification (no code change, so this reproduces report 023's own numbers exactly)
python3 extract.py benchmark/library --no-vlm --out /tmp/lib_verify
python3 contact_sheet.py benchmark/library /tmp/lib_verify results/library_025/library_h_contact_sheet_unchanged.jpg 190
```
