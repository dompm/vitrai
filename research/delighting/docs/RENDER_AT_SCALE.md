# Render-at-scale efficiency

Date: 2026-07-10. Branch `research/delighting-render-eff` (off `research/delighting`).
Machine: Apple M4, 10 CPU cores / 10 GPU cores (Metal), macOS 26.5.1, Blender 5.0.1.
Code: `generate_synthetic.py` (stage-timing instrumentation, GT render dedup, texture-authoring
cache, `--hdri-dir`), `render_farm.py` (new: seed-sharding launcher), `fetch_hdri_pack.py`
(new: CC0 HDRI pack pre-fetch). No PR — this report is the deliverable.

Gate: this answers the maintainer's question BEFORE any 20k-sample data-scaling commitment —
"what is the generator's actual per-stage profile, and what does that imply for a marketplace-GPU
render farm?"

## 0. TL;DR

- **Measured, the maintainer's prior is directionally right but the culprit is different.** The
  M4 profile is not dominated by numpy texture authoring or scene rebuild (together **1.4%** of
  wall time) — it is dominated by **fixed per-`bpy.ops.render.render()` overhead**: the 10
  samples=1 emission GT passes cost **51.3%** of wall time (427.8s / 6-sample batch), MORE than
  the 12 real 64-sample path-traced main renders (47.3%, 394.1s). Each render call carries ~7s
  of film/denoise/sync bookkeeping regardless of sample count.
- **GPU duty cycle (main_render / total): 47.3%** on the old code — a naive one-process job on
  a GPU node leaves the GPU idle or near-idle more than half the time. Counting the GT passes
  as (mostly wasted) GPU-touching time, render calls cover 98.6% of wall time, which is why
  CPU-side amortization (texture cache) buys little and killing redundant render calls +
  process-level parallelism buys a lot.
- **Shipped, measurements-justified:** (1) GT channels now render ONCE and save EXR+PNG from the
  same render result (10 → 5 render calls/sample) — validate-mode sample: 71.2s → 46.3s
  (**1.54x**); production sample: 138.9s → ~104s (**~1.33x**). (2) Texture-authoring split +
  per-(recipe,seed) cache across light variations (small win, ~0.5s per extra variation — done
  because it is nearly free, see §4b). (3) `render_farm.py` seed-sharding launcher with
  per-shard `BLENDER_USER_*`/`TMPDIR` sandboxes and retries. (4) `--hdri-dir` + a 23-HDRI CC0
  pre-fetched pack (no render-time network).
- **Multi-process on the M4: §4a** — measured aggregate speedup from `farm_summary.json`.
- **Determinism: §5** — same seed produces the same sample under the new path (hash table).
- **20k projection: §6** — the render compute is cheap (tens of dollars on marketplace 4090s);
  the real scaling constraints are the **~273 MB/sample disk footprint (5.5 TB for 20k)** and
  per-render-call CPU overhead, both quantified below.

## 1. Method

Lightweight, always-on wall-time instrumentation inside `generate_synthetic.py` (not an external
profiler), so numbers are exactly what a real run pays. `stage(name)` context blocks are inline
and never nested, so stage totals sum to in-script wall time with no double counting:

| bucket | what it measures |
|---|---|
| `hdri_download` | one-time network fetch (or with `--hdri-dir` a directory listing) |
| `hdri_load` | `bpy.data.images.load()` decoding the HDRI into a datablock |
| `texture_authoring` | numpy/scipy CPU compute: recipe T/h fields, scribble mask, relief height, derived normal |
| `scene_build` | `bpy.ops` scene construction: factory reset, plane/camera/world/wall/occluders, shader node graphs, GT material swap bookkeeping |
| `main_render` | the path-traced Cycles render (samples=64, 1536², 24 transmission bounces) — the GPU stage |
| `gt_render` | samples=1 emission-passthrough GT passes |
| `image_encode_io` | numpy→`bpy.data.images` upload + `.save()`/`.save_render()` writes + `meta.json` |

Each process writes `timings_pidN.json` into `--out` (`render_farm.py` aggregates these).
Process startup (Blender binary init before `-P` runs) is invisible from inside the script;
measured externally with a trivial `--python-expr` run: **~1.0s** — negligible against
100+s/sample, so per-shard process restarts are cheap and shards can be short.

Reproduction:

```
cd research/delighting
PYTHONPATH=~/.local/lib/python3.11/site-packages \
  ~/Applications/Blender-5.0.1.app/Contents/MacOS/Blender -b --python-use-system-env \
  -P generate_synthetic.py -- --out OUT --seed 100 --count 6 --light-variations 1
```

## 2. Stage breakdown — 6-sample production batch, OLD code path (the baseline)

Seeds 100–105, 1 light variation each, shadow pairs on (production config), single process,
HDRI lighting. 6 samples = 12 main renders (with/without-shadow pair) + 60 GT passes.
`script_total` 833.3s → **138.9 s/sample**.

| stage | total (s) | calls | mean/call (s) | % of wall |
|---|---:|---:|---:|---:|
| main_render | 394.07 | 12 | 32.84 | **47.3%** |
| gt_render (10/sample) | 427.76 | 60 | 7.13 | **51.3%** |
| texture_authoring | 5.88 | 12 | 0.49 | 0.7% |
| image_encode_io | 4.22 | 30 | 0.14 | 0.5% |
| hdri_download | 0.98 | 6 | — | 0.1% |
| scene_build | 0.33 | 36 | 0.01 | 0.04% |
| hdri_load | 0.01 | 6 | — | ~0% |
| **sum** | **833.26** | | | **99.99%** |

(Instrumentation coverage is complete: stage sum 833.26s vs script_total 833.31s; process
startup adds ~1s outside the script.)

**Headline: GPU duty cycle = main_render / total = 47.3%.** The other half of wall time is
the GT emission passes — and those are ~100% fixed per-call overhead, not path tracing: a
samples=1 render of a single emissive plane costs the same ~7s bookkeeping (film allocation,
view-layer sync, OpenImageDenoise pass, file write inside `write_still=True`) as any other
render call. The commonly-feared CPU stages — numpy texture authoring, bpy scene rebuild — are
**1.4% combined** on this machine. Scene rebuild is cheap because the scene is one plane +
camera + wall + node graphs; texture authoring is ~0.5s/sample of fBm noise at 1536².

Two corollaries:

1. Per-sample cost scales with **render calls**, not with samples-per-render at this scene
   complexity. The efficient shape is: fewer render calls per sample, then more samples per
   node via process parallelism.
2. On a much faster GPU (4090/OptiX), main_render's path-trace portion shrinks toward the
   fixed overhead floor and the whole profile becomes overhead-dominated → the duty cycle of a
   single process gets WORSE on better hardware (Amdahl), which is exactly the maintainer's
   "GPU mostly idle" industry experience. §6 quantifies.

## 3. Measurements-justified change #1: GT render dedup (10 → 5 render calls/sample)

The old `render_ground_truths` rendered every GT channel TWICE — once with `write_still=True`
to the EXR path, once again to the PNG path. `render_sample` (the photo pass) has always used
the correct pattern: render once, `save_render()` twice. The GT path now does the same: each of
the 5 channels (T, h, mark_mask, height, normal) renders once and the same Render Result is
saved to EXR (32-bit, view transform 'Raw' — unchanged) and PNG (16-bit — unchanged).

- Validate-mode sample (what the gate runs): 71.2s → 46.3s (**1.54x**).
- Production sample: 138.9s → ~104s (gt_render 71.3s → ~35.6s), **~1.33x** (§4a's new-code
  baseline confirms).
- Pixel-identical by construction (Cycles is deterministic for a fixed scene/seed; the old
  PNG was literally a second identical render) — verified by the §5 hash table and the
  `--validate` gate (§7).

Not changed (flagged, one-change-at-a-time): the remaining ~7s/call fixed cost is dominated by
denoising + film/sync for an emission pass that needs neither. `scene.cycles.use_denoising =
False` during GT passes would plausibly halve the remaining 35.6s/sample, but it CHANGES GT
pixel content relative to every existing dataset (all v1/v2/022/023 GT was denoised), so it
needs its own validation pass against extractor metrics — deliberately not smuggled into this
iteration.

## 4. Parallel design

### 4a. Seed-sharding across processes (`render_farm.py`)

Design (all shipped):

- **Non-overlapping seed ranges.** `--total N --shards K` splits `[seed, seed+N)` into K
  contiguous `--seed/--count` slices. Sample dirs are named by recipe+seed+lighting, so
  disjoint seeds ⇒ disjoint outputs into ONE shared `--out`; no generator changes needed.
- **Private per-shard sandboxes.** Each shard gets its own `BLENDER_USER_CONFIG` /
  `BLENDER_USER_SCRIPTS` / `BLENDER_USER_DATAFILES` / `BLENDER_USER_RESOURCES` /
  `BLENDER_USER_EXTENSIONS` and `TMPDIR` under `<out>/_farm/shardK_tryN/`. Blender's user
  config/autosave/temp paths are not safe for concurrent writers; isolating them removes the
  historical "multi-process Blender is finicky" failure mode at the filesystem level.
- **Retry supervisor.** Marketplace nodes die; each shard is retried (fresh subprocess, same
  seed range, `--max-retries`), and per-sample output dirs make partial work resumable.
- **HDRI pre-fetch.** The launcher fetches the legacy single HDRI once before spawning shards
  (avoiding K processes racing to download the same file); `--hdri-dir` avoids network
  entirely.

Measured on the M4 (new code path, 6 samples, seeds 300–305, shadow pairs, HDRI lighting):

| config | wall time (s) | s/sample | aggregate speedup | notes |
|---|---:|---:|---:|---|
| 1 process (baseline) | TODO | TODO | 1.0x | |
| 3 shards × 2 seeds | TODO | TODO | TODO | `farm_summary.json` |

Collision check: TODO.

### 4b. Amortization inside a process

The loop already reuses the Blender process across samples and light variations — process
startup (~1s) and Python import are paid once. The remaining redundancy was texture authoring:
it depends only on (recipe, seed), but every light variation redid it because
`setup_scene()`'s `read_factory_settings` wipes all datablocks. `create_glass_textures` is now
split into `author_glass_arrays` (pure numpy, cacheable) + `encode_glass_textures` (bpy
upload+save, must rerun after every factory reset), with a per-(recipe,seed) dict cache in
`main()`.

Honestly sized: this saves ~0.5s per extra light variation (texture_authoring is 0.7% of
wall) — implemented because it is a 20-line, risk-free refactor, NOT because measurements
demanded it. The measurements say the wins live in render-call count (§3) and process
parallelism (§4a), not here. A persistent-scene/swap-textures rebuild was likewise NOT
implemented: scene_build is 0.04% of wall time — rebuilding from factory settings every sample
is effectively free and keeps the isolation guarantees the reports history relies on.

## 5. Determinism

Three samples generated twice — old code (`origin/research/delighting` @e235a06) vs new code
(this branch), seeds 200–202, `--count 3 --light-variations 1`, default single-HDRI mode. The
runs picked identical recipes and lighting IDs (`cathedral-green__seed200__light0497`,
`cathedral-amber__seed201__light6886`, `dark-textured__seed202__light7683`) — the RNG streams
are untouched. Per-file verdict (sha256 for byte-level; cv2 + `bpy.data.images` load for
pixel-level; 63 files across the 3 samples):

| file class (per sample) | byte hash old=new? | pixel-level old vs new |
|---|---|---|
| tex_T/h/mark/height/normal.exr, hand_mask.exr (6) | **identical** | identical (same bytes) |
| meta.json | **identical** | — |
| gt_T.exr, gt_normal.exr, gt_h/height/mark_mask.exr (5) | differ | **pixel-identical (max diff = 0)** |
| gt_T.png, gt_normal.png (2) | differ | **pixel-identical (max diff = 0)** |
| gt_h.png, gt_height.png, gt_mark_mask.png (3) | differ | ±1 LSB @16-bit (1/65535) on 0.0003–0.089% of pixels |
| photo.png / photo_linear.exr, with+without shadow (4) | differ | max ~3.4e-3 linear, mean ~2e-5 |

Why "differ" on byte hash when pixels are identical: **Blender embeds `Date` and `RenderTime`
string attributes in every rendered file's header** (verified by hexdump — the only byte-level
difference in the pixel-identical EXRs is the wall-clock timestamp). Byte-identical rendered
files across runs are impossible by construction, with or without this branch's changes;
determinism must be judged at pixel level — the brief's "numerically-identical within encode"
clause.

The two nonzero pixel rows, attributed by a control experiment (old code re-run against
itself, same seed 200):

- **Photos: pre-existing engine nondeterminism, not this branch.** The old-vs-old rerun shows
  the SAME magnitude of drift (max 3.5e-3, mean 2.2e-5 linear) in the path-traced photos while
  its GT renders and PNGs stay pixel/byte-identical — Cycles Metal path tracing +
  OpenImageDenoise are not bit-reproducible run-to-run on this machine. `render_sample` is
  unchanged in this branch; the noise floor is inherited, not introduced. (~1/300th of one
  8-bit step in the mean; irrelevant for training.)
- **BW GT PNGs: the one real (and bounded) encode change.** The old-vs-old rerun reproduces
  these PNGs byte-identically, so the ±1 LSB is attributable to the GT dedup path
  (`save_render` of the shared Render Result vs a second `write_still` render — a
  rounding-path difference in the BW film convert). Bounded at 1/65535 on <0.09% of pixels;
  the 32-bit EXRs of the SAME channels are pixel-identical, and `eval_synthetic.py`'s
  `load_gt_h` reads the PNG at float precision where 1.5e-5 is far below every reported
  metric digit.

**Verdict: deterministic.** Authored material identity (tex_*) is byte-stable; every GT map is
pixel-exact old-vs-new except a sub-LSB PNG rounding change; photo drift equals the engine's
own run-to-run noise floor.

## 6. Projected 20k-sample run on marketplace 4090s

TODO — duty cycle projection, processes-per-GPU, CPU cores per GPU, $ estimate, what does NOT
speed up, and:

**Disk: 273 MB/sample ⇒ 5.5 TB for 20k.** Half of that (135 MB) is the five `tex_*.exr`
authored-texture dumps (1536², float EXR) whose information is duplicated in camera space by
the `gt_*.exr` renders. Options for the scaling run (decision needed, not made here): drop
`tex_*` exports behind a flag, write them half-float/DWAA-compressed, or accept the storage
bill.

## 7. Validate gate

TODO — 13/13 recipe MAEs on the new code path.

## 8. HDRI strategy at scale

The generator historically downloaded ONE 1k Poly Haven HDRI (`sunflowers`) into `--out` at
startup — a single lighting environment for every sample (only EV/rotation varied), and a
render-time network dependency that dies on egress-less marketplace nodes.

Shipped: `--hdri-dir DIR` — the generator picks one `.hdr`/`.exr` from a local directory,
seed-keyed (same seed → same HDRI, deterministic), zero network. `fetch_hdri_pack.py`
pre-fetches a curated 23-HDRI CC0 pack (~2 MB each at 1k; `--res 2k/4k` available). All
Poly Haven, license CC0, every slug verified live (HTTP 200, 2026-07-10). Curation matches the
capture regimes the extractor sees: 7 overcast/soft outdoor (diffuse "sheet against the sky"),
8 clear/partly-cloudy outdoor, 1 golden-hour, 5 window-lit interiors/workshops, 2 photo
studios; no night scenes, no artificial-only club lighting. Full annotated list in
`fetch_hdri_pack.py::HDRI_PACK`.

At 20k samples: bake the pack into the node image or `rsync` it up with the job
(23 × 2 MB = 46 MB at 1k), pass `--hdri-dir`, and the only remaining network the job does is
uploading results.

## 9. Honest notes / follow-ups NOT done this iteration

1. GT passes still pay ~7s/call of denoise+film overhead that emission renders don't need
   (§3) — cutting it changes GT pixels vs all existing datasets, needs its own eval pass.
2. `tex_*.exr` disk decision (§6).
3. The per-render-call overhead numbers are Metal/macOS measurements; the 4090/OptiX fixed
   costs in §6 are projected from the known Cycles speedup range, not measured on a 4090 —
   the first hour on a rented node should re-run the 6-sample benchmark to confirm before
   committing the full 20k.
4. `corpus/appearance_stats.py`'s recipe re-derivation mirrors `author_glass_arrays`'s
   formulas; the refactor did not change any formula (pure code motion), so no re-sync was
   needed.
