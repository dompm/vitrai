# 053 — Deployment-capture realism: phone pipelines, finite-depth scenes, crop sim, holdouts + 1k pilot

Date: 2026-07-16. Branch `research/delighting-053-capture-realism` (off `research/delighting`
@ `8c8877a` — the same trunk the external review was performed against). Status: pipeline
landed + smoke-verified; deployment pilot + boards committed. **No training launched** (a
separate decision); **Modal/payment untouched.**

Companion: `docs/external/053-dataset-capture-review.md` (the CTO-commissioned review, verbatim).

---

## Context — the review and its verified claims

The CTO commissioned an independent-agent review of the synthetic-dataset pipeline at trunk
`8c8877a`. Its thesis, adopted by the lead after verification:

> "You have invested deeply in glass physics and material taxonomy. The weak side is now the
> camera, the scene around the glass, and the bridge to actual user captures." A model could
> score beautifully on the current synthetic set while mostly learning **"Blender glass grammar."**

The lead verified five concrete code claims against trunk before commissioning this work; they
are treated as established (not re-litigated here):

1. `foundation/dataset.py::_augment_photo` = exposure + signal-dependent noise + gamma + JPEG,
   each INDEPENDENTLY randomized. No AWB, HDR/tonemap, sharpening halos, denoise, saturation,
   per-channel clip, lens shading, CA, blur, rescale/HEIC — and no correlated device presets.
2. `generate_synthetic.py::generate_hand_mask` = HARD-CODED axis-aligned rectangles at fixed
   pixel coords (4 edge variants), σ=10 blur; and `has_shadow = True` always → every identity a
   shadow/no-shadow pair → training sees shadows ~50% with a recognizable shape grammar.
3. `render_farm.py::build_cmd` forwarded ONLY out/light-variations/validate/recipe/hdri-dir —
   silently dropping `--gt-b --gt-aov --no-tex-dump --exr-codec --specular`. A 20k run would
   omit gt_B/AOV supervision and blow the ≤100MB/sample storage budget.
4. `--count == 5` special case = "first 5 recipes", stale now there are 17.
5. White marker = constant self-emission workaround (the scene lacks front light).

This report delivers the **fixed pipeline + a deployment pilot**, per the review's "do not render
20k yet" instruction.

---

## A. Phone-pipeline presets (loader-side) — `foundation/phone_pipeline.py`

Replaced the four independent knobs with **5 named, COMPLETE, correlated device ISP pipelines**,
applied in physical order:

    scene-linear → auto-exposure error → AWB error → lens shading → chromatic aberration →
    sensor noise (signal-dependent) → optical blur (motion/defocus) → local HDR/tonemap (with
    HALOS) → denoise (edge-preserving) → sharpen (unsharp OVERSHOOT) → saturation/per-channel
    clip → rescale (resolution loss) → JPEG/HEIC quantization → decode back to scene-linear

Presets (`PRESET_NAMES`), each with per-parameter jitter and CORRELATED settings (the review's
key point — "low light tends to mean stronger denoising, sharpening and local tone mapping
together"):

| preset | character | coupled signature |
|---|---|---|
| `neutral_mid` | clean well-exposed | light processing (keeps some near-pristine inputs) |
| `bright_window_hdr` | Apple computational HDR of a bright pane | highlight compression + local-contrast HALO ring + punchy sat + HEIC; low gain/noise |
| `low_light_handheld` | dim interior lifted by AE | high gain + heavy shot noise + aggressive denoise (smears texture) + over-sharpen + warm AWB + motion blur + HEIC |
| `android_punchy` | saturation-forward tuning | strong sat + strong edge-halo sharpening + JPEG at variable quality |
| `wide_edge` | ultra-wide / cheap lens | dominant vignette + colour shading + strong CA at the edges |

- In/out **scene-linear** (report 025 conventions preserved); applied to the INPUT photo only, so
  every target stays intrinsic — this trains nuisance (N) invariance directly.
- HEIC is APPROXIMATED (cv2 has no HEVC-image encoder): chroma-plane smear + high-Q JPEG
  reproduces HEIC's soft-chroma / low-chroma-noise signature. Documented in `_quantize`.
- `dataset._augment_photo` now calls `apply_phone_pipeline`. Self-test board:
  `results/053/phone_pipeline_strip.jpg` (each preset run twice on a synthetic window+mullion
  scene) — the halos, CA fringing, vignette, warm AWB drift, and HDR compression read distinctly.

## B. Scene realism (`generate_synthetic.py`, gated behind `--deploy-scene`; `--validate` untouched)

- **Finite-depth backgrounds** (`add_deploy_lighting_and_background`): a procedurally textured
  plane at a SAMPLED depth (10 cm / 50 cm / 2 m / ∞) behind the glass, with a nearer shelf-edge/
  mullion bar at a different depth (depth discontinuity, ~50% of finite-bg samples). Closer
  backgrounds are refracted more strongly by the relief — "background distance controls how
  strongly relief refracts it" is now a sampled axis. HDRI stays the far layer. Depth recorded in
  `meta.background`.
- **Mixed front/back lighting as the NORM**: a soft area light BEHIND the camera (never in frame)
  aimed at the glass front face, present ~70% of deploy samples, plus deploy-default front-surface
  specular + a dim reflective interior wall. Reflections and front-lit marks are now ordinary, not
  an opt-in `--specular` stress test.
- **White-marker hack dropped**: with real front light the norm, the constant self-emission
  workaround falls 0.6 → 0.15 (a small fallback floor for the minority of samples with no front
  light). **Verified**: white grease-pencil marks render legibly under the new front light (see
  `results/053/boards_smoke/board_crop_workflow.jpg`, dark-opaque row — the white squiggle).
- **Shadow overhaul** (`generate_shadow_mask`): VARIED silhouettes — hand at an arbitrary angle,
  forearm, phone edge, soft blob cluster — entering from a random side at random position/scale/
  tilt with a varied penumbra, replacing the 4 fixed rectangle sets. Shadow PRESENCE is a sampled
  probability (deploy default 0.3), not a forced pair for every identity. `--shadow-pairs` forces
  dense pairs for the shadow-supervision path (the with/without diff). Silhouette preview:
  `results/053/shadow_masks_preview.png`.
- The GT emission renders defensively hide the new front-light/background objects (same discipline
  as the DarkWall); `gt_B` correctly captures the finite background.

## C. Holdout strengthening (`foundation/dataset.py` + `docs/EVAL_PROTOCOL.md` v1.2)

Beyond seed%5 identity holdout, `holdout_reason()` reserves entire FAMILIES of each axis to
TEST-only, deterministically (EVAL_PROTOCOL §3b-ext):

| axis | reserved-to-test rule |
|---|---|
| texture-generator family / taxon | `class_label ∈ {ring-mottle, confetti-shard, cathedral-red, dark-slate}` |
| HDRI / background scene | `sha1(hdri_basename) % 5 == 0` (~20% of the pack) |
| camera-pipeline preset | `wide_edge` (TRAIN loader draws only `TRAIN_PRESETS`; TEST may see all) |
| capture geometry | `perspective_rectified` (from the crop-sim, §D) |

Old batches lacking the new meta fields fall back to train-eligible, so nothing is retro-held-out.
EVAL_PROTOCOL bumped to **v1.2** (synthetic split only; the frozen REAL set §3c is UNCHANGED). The
doc states plainly this is NECESSARY-not-sufficient: the final gate is untouched real user photos
(a CTO action item, out of scope).

## D. Fixes (`render_farm.py`, `generate_synthetic.py`)

- `render_farm.build_cmd` now exposes + forwards **every** production flag it silently dropped:
  `--gt-b --gt-aov --no-tex-dump --exr-codec --specular --fixed-ev --no-marks` plus the new 053
  scene flags. Verified by a direct `build_cmd` assertion and by the pilot running THROUGH the farm
  with the full production flag set (gt_index_B.exr emitted, DWAA codec, tex dump pruned).
- Stale `--count == 5` special case removed; `--cover-recipes` cycles all 17 recipes
  deterministically (`recipe = recipes[i % 17]`), making coverage explicit.

## E. σ_s eval scoring (`foundation/eval_foundation.py`) — the 048-owed metric

Report 048 plumbed σ_s as a target but `eval_foundation` never scored it; the reviewer re-flagged
it. Added, on the held-out-identity test split:

- **σ_s-MAE** (authored-linear, like h-MAE), where the model emits σ_s and the sample carries a
  supervised gt_σ_s.
- **σ_s structured-background relight L1** (045/046 methodology): σ_s drives a per-pixel
  roughness-mip blur (`variable_blur`, σ = SIGMA_MAX·σ_s) of a warm-white/cool-dark checker; the
  checker is relit by the PREDICTED σ_s and by the GT σ_s, and scored as sRGB L1 between the two
  relights — isolating σ_s's effect on a structured backdrop (the exact gap the uniform-backlight
  validate gate cannot see, per report 045). A per-sample `gt_relight_scale` (GT σ_s vs no-scatter)
  is reported as context so the L1 is read against how much structured softening the GT actually
  induces. Unit-tested: perfect→0, no-scatter→full penalty, flat→penalized. Rows added to
  `baseline_ladder.md` and `eval.json`.

## F. The deployment pilot + boards

- Rendered through **`render_farm.py` with production flags ON**: `--deploy-scene --cover-recipes
  --gt-b --gt-aov --no-tex-dump --exr-codec DWAA --shadow-prob 0.3`, single shard (the machine is
  one-Blender-at-a-time). Renders are gitignored (`pilot_053_out/`); only downscaled JPEG boards
  are committed under `results/053/boards/`.
- Crop-sim (`crop_sim.py`) is a decoupled POST-pass (cv2, run in the venv — Blender's bundled
  python lacks cv2): one user-crop homography (0–5% pad/trim, tilt, scale, optional four-corner
  perspective) applied IDENTICALLY to the photo and every GT channel (LINEAR for continuous,
  NEAREST for labels), so maps stay registered. Emits the cropped sheet + registered detail
  patches and stamps `capture_geometry` + the 3×3 transform into meta.json (multilayer AOVs are
  skipped and can be re-warped later with the stored matrix — documented).
- Boards (`build_boards_053.py`): `board_overview` (full sheets, tagged recipe/bg-depth/shadow/
  front-light), `board_crop_workflow` (full render → cropped sheet → detail patches, geometry-
  labeled), `board_shadows` (clean vs varied-silhouette shadow).

### Pilot composition (as rendered)

**68 samples** (34 identities × 2 light variations, seeds 500–533) through `render_farm.py`
with `--deploy-scene --cover-recipes --gt-b --gt-aov --no-tex-dump --exr-codec DWAA
--shadow-prob 0.3`, then `crop_sim.py` + `build_boards_053.py`:

- **17/17 recipes** covered (`--cover-recipes`); **23 distinct HDRIs**.
- **Shadows 25%** (17/68; target 0.3 — sampling noise), all varied-silhouette.
- **Front light 71%** (48/68; target 0.7); specular + dim interior on 100% (deploy default);
  frame occluders 25%.
- **Background depth mix**: 0.1 m ×16 · 0.5 m ×16 · 2 m ×16 · ∞/HDRI-only ×20.
- **Capture geometry**: tilt_scale_crop 42 · perspective_rectified 26 (each sample also
  emits 3 registered detail patches).
- **Storage**: ≤80 MB/sample max (production flags) — inside the ≤100 MB budget.
- **Holdout partition** (dataset.py rules, precedence seed→recipe→hdri→geometry):
  train 12 · seed%5 14 · recipe-family 10 · hdri 14 · geometry 18 → **56/68 test (82%)**.
  The small pilot deliberately over-covers held-out families so the lead/CTO can eyeball
  every axis; **at scale, rebalance** with `crop_sim.py --perspective-prob 0.1–0.15` (the
  geometry axis is the largest test contributor) and by rendering more seeds (the recipe/
  hdri reservations are fixed fractions).

Boards (committed): `results/053/boards/board_overview.jpg` (full sheets tagged
recipe/bg-depth/shadow/front-light), `board_crop_workflow.jpg` (full render → cropped sheet →
detail patches, one row per recipe), `board_shadows.jpg` (clean vs shadow pairs, varied
silhouettes). Interim smoke boards: `results/053/boards_smoke/`.

Operational note (honest): the render was interrupted once mid-run by a session stall that
killed the background Blender (seeds 500–513 survived on disk; seed 514 was detected partial
by manifest check, deleted, and seeds 514–533 re-rendered with identical flags — the per-seed
deterministic RNG makes this resume exact). `_farm/farm_summary.json`: shards_ok=1, failed=0.

---

## Validate gate (byte-level discipline)

All deploy-scene features are gated by `if args.validate:` (shadow/frame off) and by
`hdri_path is None` (no finite-bg/front-light in validate) and by `GT_OPTS["deploy_scene"]`
(white-marker emission stays 0.6). So `--validate` output is unchanged from trunk for a given
(recipe, seed). **Full 17/17 sweep rendered post-change** (`--seed 1 --count 17
--cover-recipes --validate`) — uniform-backlight T-agreement MAE, all in the historical pass
band:

| recipe | MAE | recipe | MAE | recipe | MAE |
|---|---|---|---|---|---|
| dark-deep | 0.0021 | saturated-opalescent | 0.0031 | dark-textured | 0.0036 |
| dark-ruby | 0.0044 | dark-opaque | 0.0051 | streaky-fine-texture | 0.0069 |
| wispy-white | 0.0072 | dark-slate | 0.0096 | streaky-mix | 0.0130 |
| cathedral-red | 0.0166 | ring-mottle | 0.0172 | cathedral-blue | 0.0172 |
| cathedral-green | 0.0232 | baroque-rolling-wave | 0.0238 | confetti-shard | 0.0241 |
| cathedral-amber | 0.0278 | fracture-streamer | 0.0304 | | |

Reproducibility note: the sweep was rendered twice for six recipes (a session stall killed the
first run mid-way); the overlapping recipes agree to ~1e-5 MAE (e.g. cathedral-green 0.023166 →
0.023160) — GPU-denoise-level noise only, confirming the validate path is untouched.

---

## Honest limitations & deviations

- **HEIC is approximated** (chroma smear + high-Q JPEG), not a true HEVC encode — cv2 has no
  encoder. The signature (soft chroma, low chroma noise) is reproduced; block structure is JPEG's.
- **Crop-sim is a post-pass, not a wider camera render.** Rather than re-frame the camera (which
  would break the "glass fills the frame / no borders" design and GT alignment), the same
  homography is applied to all rendered channels — registration is exact by construction and the
  transform is stored. Multilayer AOVs (gt_veil/gt_index) are skipped by the cv2 pass.
- **Deploy single-shadow vs pair.** Default deploy renders the clean `without_shadow_` always
  (loader requires it for GT alignment) and adds the `with_shadow_` twin only for the sampled
  ~30% — i.e. ~30% of identities carry a supervised shadow, not the legacy 100%. `--shadow-pairs`
  restores dense pairs.
- **σ_s relight uses a fixed SIGMA_MAX** (not the 045 per-sample oracle grid-search), because the
  goal is a fair pred-vs-GT map comparison on an identical checker, not a model-tier fit.
- The pilot is a REPRESENTATIVE deployment set to prove the pipeline + produce eyeball boards; the
  exact command to scale to the full ~1k (or 20k) is below.

## Deferred (explicitly out of this scope, per the brief and the lead)

- **Real pairs during training** (review §"Use real pairs during training"): a training-side
  decision parked with the paused trainer work — noted, not implemented.
- **Collect 50–100 real user phone photos** as the untuned deployment audit / final sim-to-real
  gate (review §Strengthen the holdout, §What I would do next): a CTO action item.
- **Missing material taxa** (iridized/dichroic, crackle, dew/dimple, reactive-cell, drapery;
  confetti still visibly procedural): the reviewer explicitly ranks these BELOW capture-domain
  realism — not addressed here.
- **No training run launched**; **Modal/payment untouched.**

## How to scale (commands)

```
# full deployment pilot (~1k), single shard (one-Blender machine):
python3 render_farm.py --out pilot_053_out --seed 0 --total 500 --shards 1 \
    --light-variations 2 --hdri-dir hdri_pack --deploy-scene --cover-recipes \
    --gt-b --gt-aov --no-tex-dump --exr-codec DWAA --shadow-prob 0.3
python3 crop_sim.py --root pilot_053_out              # user-crop + patches, registered
python3 build_boards_053.py --root pilot_053_out --out results/053/boards
```
Storage stays ≤100MB/sample only with `--no-tex-dump --exr-codec DWAA` (the farm now forwards
both). Do NOT raise `--shards` on this machine (one-Blender-at-a-time).
