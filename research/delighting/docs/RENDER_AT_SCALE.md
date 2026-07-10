# Render-at-scale efficiency

Date: 2026-07-10. Branch `research/delighting-render-eff` (off `research/delighting`).
Machine: Apple M4, 10 CPU cores / 10 GPU cores (Metal), macOS 26.5.1, Blender 5.0.1.
Code: `generate_synthetic.py` (stage-timing instrumentation, `--hdri-dir`, texture-authoring
cache), `render_farm.py` (new: seed-sharding launcher). No PR — this report is the deliverable.

Gate: this report answers the maintainer's question BEFORE any 20k-sample data-scaling
commitment — "what is our generator's actual per-stage profile, and what does that imply for
a marketplace-GPU render farm?" The headline number is the GPU duty cycle: **PLACEHOLDER%**
of wall time is spent inside a Cycles render call; the rest is single-threaded CPU work with
the GPU idle.

_(This report is filled in incrementally as measurements land — see TODO markers.)_

## 0. TL;DR

- TODO after 6-sample batch + multi-process test complete.

## 1. Method

`generate_synthetic.py` already ran through hundreds of samples across reports 001-027; this
report adds lightweight, always-on wall-time instrumentation rather than external profiling,
so the numbers below are exactly what a real generation run pays, not a synthetic profiler
overhead. `stage(name)` context-manager blocks are scattered inline through every function
(never nested inside one another, so the sum of stage totals equals the in-script wall time
with no double counting) around six buckets:

| bucket | what it measures |
|---|---|
| `hdri_download` | one-time network fetch (or, with `--hdri-dir`, a directory listing) |
| `hdri_load` | `bpy.data.images.load()` decoding the HDRI file into a Blender image datablock |
| `texture_authoring` | numpy/scipy CPU compute: recipe T/h color fields, scribble mask, relief height + derived normal (`generate_noise`'s fBm octave blending, `generate_relief_height`, `height_to_normal`) |
| `scene_build` | `bpy.ops` scene construction: `setup_scene` (plane/camera/world/wall/frame occluders), `create_glass_material` (shader node graph), `add_shadow_caster`'s bpy portion, `render_ground_truths`' material swap/restore bookkeeping |
| `main_render` | the actual path-traced Cycles render (`scene.cycles.samples = 64`, 1536x1536, transmission/glass bounce settings) — the GPU-bound stage |
| `gt_render` | the 10 `samples=1` emission-passthrough ground-truth passes (T/h/mark/height/normal x {EXR,PNG}) |
| `image_encode_io` | numpy-array-to-`bpy.data.images` upload + `.save()`/`.save_render()` disk writes + `meta.json` |

Every process also writes `timings_pidNNNN.json` into `--out` (cumulative stage totals +
`script_total_s`, the full in-script wall time from the first line this script's own Python
code executes). The gap between `script_total_s` and the shell-measured wall time of the whole
`blender -b -P generate_synthetic.py` invocation is the **process-startup bucket**: Blender's
own binary init, Cycles device enumeration, and (because `import bpy` is unavoidably the
script's first line) anything the Blender executable does before handing control to `-P`. This
is NOT visible from inside the script by construction — reported as `shell_wall - script_total`.

Reproduction:
```
cd research/delighting
PYTHONPATH=~/.local/lib/python3.11/site-packages \
  ~/Applications/Blender-5.0.1.app/Contents/MacOS/Blender -b --python-use-system-env \
  -P generate_synthetic.py -- --out OUT_DIR --seed 100 --count 6 --light-variations 1
```

## 2. Stage-breakdown table (6-sample batch)

TODO.

## 3. Headline finding: GT-render fixed per-call overhead

TODO — smoke test already shows ~5-5.5s per `bpy.ops.render.render(write_still=True)` call
regardless of `samples=1` content; 10 calls/sample makes `gt_render` a bigger cost than
`main_render` (64 real path-traced samples). Quantify against the 6-sample batch and state the
implication (NOT changed in this iteration — flagged as the top follow-up, see §7).

## 4. Parallel design

### 4a. Seed-sharding launcher (`render_farm.py`)

TODO — describe + multi-process throughput measurement.

### 4b. Amortization inside a process (texture-authoring cache)

TODO — `author_glass_arrays`/`encode_glass_textures` split + `_texture_cache` keyed by
(recipe, seed); quantify against `--light-variations 3`.

## 5. Determinism

TODO — hash comparison, 3 samples, old path vs new (cache-enabled) path.

## 6. Projected 20k-sample cost on marketplace 4090s

TODO.

## 7. HDRI strategy at scale

TODO — `--hdri-dir` flag + curated pack list.

## 8. Honest notes / follow-ups NOT done this iteration

TODO.
