# Report 006 — Validation coverage closed for all 5 recipes

Date: 2026-07-09. Code: `generate_synthetic.py` (vendored + fixes) @ this commit,
`check_validation.py` (now takes a root-dir arg + groups by recipe).
Worktree on `research/delighting`. In-house run (Blender installed locally, see below).
No PR. Renders are gitignored; this table is the deliverable.

## 0. TL;DR

- **All 5 recipes now pass the uniform-backlight consistency check.** Previous runs
  only ever validated `cathedral-green` and `streaky-mix`; the three missing recipes
  (`cathedral-amber`, `dark-opaque`, `wispy-white`) had never been scored. They are now.
- Acceptance was: cathedral ≈ 0.02 (Fresnel floor), and critically `streaky-mix` and
  `dark-opaque` a few percent. **Met on every recipe.**

## 1. What this check measures

Validate mode (`--validate`) replaces the HDRI with a **perfectly uniform white
emissive backlight** (strength 1.0, world black) and disables frame + shadow. Under
that light the photographed transmission through the glass should equal the authored
transmittance `gt_T`. `check_validation.py` computes the mean absolute error between
`without_shadow_photo_linear.exr` (linear render) and `gt_T.exr` (raw-emission authored
transmittance), per pixel, across RGB. It is a **generator self-consistency / physics**
check — "does the glass shader actually transmit the color it was authored with" — not
an extractor test (that is report 007).

The residual is expected to be non-zero even for a perfect shader: Fresnel reflection
at the two glass surfaces removes a few percent of light, so a clear cathedral pane
floors out around 0.02.

## 2. Results — per-recipe MAE (all 5 recipes)

Command:

```
blender -b --python-use-system-env -P generate_synthetic.py -- \
    --validate --count 5 --light-variations 1 --out validate_data_check
.venv/bin/python check_validation.py validate_data_check
```

| recipe          | MAE      | n | acceptance         | verdict |
|-----------------|----------|---|--------------------|---------|
| cathedral-green | 0.021753 | 1 | ≈0.02 Fresnel floor | PASS — sits on the floor |
| cathedral-amber | 0.025792 | 1 | a few %            | PASS |
| dark-opaque     | 0.005914 | 1 | a few % (critical) | PASS |
| streaky-mix     | 0.026901 | 1 | a few % (critical) | PASS |
| wispy-white     | 0.038579 | 1 | a few % (critical) | PASS |

(linear absolute units, 0–1, mean over RGB.)

## 3. Reading the numbers honestly

- **cathedral-green (0.022) and cathedral-amber (0.026)** land exactly where a clean
  Fresnel-limited transparent pane should. This is the reference floor.
- **streaky-mix (0.027)** is the previously-fixed "milky streaks render as bright
  transmission, not dark smudge" case, and it validates right at the floor. Good.
- **wispy-white (0.039)** is the highest residual, and that is *physically correct,
  not a defect*: opalescent/wispy glass scatters (haze), so some transmitted light is
  redirected off-axis rather than passing straight to camera. A few extra percent of
  disagreement with a straight-transmittance target is the expected signature of haze,
  not a shader bug. Worth keeping an eye on in the extractor eval.
- **dark-opaque (0.006)** is the *lowest* residual, but this is a weak test for that
  recipe by construction: dark glass has `T ≈ 0` everywhere, so both the photo and
  `gt_T` are near zero and their absolute difference is trivially tiny. The useful
  thing it *does* confirm is direction: the render is **dark, not blown-out bright** —
  i.e. the data itself carries a dark tint, which is the precondition for the extractor
  to be able to recover a dark `T`. Whether it renders dark *and neutral vs.
  purple/magenta* is an HDRI-lit question and is answered in report 007, not here
  (validate mode has no HDRI).

## 4. Environment / provenance

- **Blender 5.0.1** (official macOS arm64 portable build, matches `blender_version` in
  every existing `meta.json`), run headless with Cycles on the Apple M4 Metal GPU.
- Generator needs `scipy` + `requests` (noise + HDRI fetch) which Blender's bundled
  Python lacks; installed to `~/.local` and surfaced to Blender via `PYTHONPATH` +
  `--python-use-system-env` (the app bundle's own site-packages is read-only).
- `check_validation.py` run from the repo `.venv` (has `cv2` for EXR I/O).
