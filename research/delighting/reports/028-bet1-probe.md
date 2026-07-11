# Report 028 — Bet-1 falsification probe: off-the-shelf reflection removal in log space

Date: 2026-07-10. Branch `research/delighting-028` (off `research/delighting`).
Code: `bet1_probe.py` (the DSRNet log-space wrapper), `run_bet1_probe.py` (scoring +
panels), reusing `assembled_bench.drag_test` verbatim. Deliverables:
`results/bet1_probe/{drag_table.json, panel_*.jpg}`, this report. Model weights + the
XReflection clone are external (env vars, §1); renders are gitignored (regenerate via
`generate_assembled.py`). **No PR.**

This is the report-027 **Bet 1** one-week milestone, run as a kill-or-continue experiment.
The hypothesis (027 §Bet 1 / §7): our see-through split `photo = T·B` is the multiplicative
mirror of single-image reflection removal `I = T_layer + R_layer`; take `log` and it becomes
an additive two-layer split, so a **pretrained reflection-removal model, fed normalized
`log(photo)`, might separate glass tint from transmitted background with ZERO training**
because its deep prior already knows natural backgrounds. The memo's own **kill criterion**:
if the recovered `T` can't beat classical's **0.140** cathedral drag lum-CV, *or* the
separated background layer is degenerate (empty / copy-of-input), Bet 1 is dead.

## 0. TL;DR — KILL: the prior is INVERTED, not absent

**KILL, cleanly, with both failure modes present at once — and one diagnosis explaining
both:**

> **The reflection-removal prior is trained to KEEP the natural scene (as its transmission
> layer) and remove a sparse ghost. Our transmitted background *is* the natural scene. The
> prior's notion of "the layer to remove" is exactly opposite to ours — so off-the-shelf
> transfer cannot work regardless of checkpoint quality, and a *stronger* remover would
> preserve our background *better*, i.e. fail *harder*.**

Concretely, fed `log(photo)`, DSRNet (ICCV-2023 SOTA reflection separation):

- Emits a **transmission layer that is a near-perfect copy of the input** (lum-correlation
  with input **+0.98** at native 1024; drag lum-CV **0.274** vs raw 0.292 — it removes
  essentially nothing, and **loses to classical's 0.140 by ~2×**). The transmitted sky/field
  landscape is fully retained.
- Emits a **reflection layer that is degenerate — a near-black empty residual** (median 0.007
  linear ≈ 4% of the input's 0.164; correlation with input **+0.08**). Its low lum-CV
  (0.037–0.11) is the artifact of an almost-constant near-zero map, **not** background
  separation, and it is unusable as de-lit glass (it's black).
- **The sRGB (no-log) control fails identically**, so this is **not** a log-space
  distribution shift — it is the wrong-prior-domain failure above.

Neither output resembles the authored flat-green GT (headline panel, §4). Bet 1 as a
zero-training probe is falsified; §5 spells out what the diagnosis implies for the
fine-tuning stage (short version: Bet 1 moves from "cheap adaptation" to "moderate
training run with swapped layer semantics").

## 1. Model + environment (what ran, and why this checkpoint)

**Model: DSRNet** — *"Single Image Reflection Separation via Component Synergy"*, Hu & Guo,
ICCV 2023 — via the **XReflection** model zoo checkpoint `dsr-25.8915.ckpt` (PSNR 25.89 dB
on the SIR² benchmark; 124.6 M params). Chosen over the 027-cited candidates because:

1. **Directly downloadable public weights** — `https://checkpoints.mingjia.li/dsr-25.8915.ckpt`
   (1.66 GB), no Google-Drive quota gate. The 027 memo's top literature picks (CVPR-2026
   joint-latent-diffusion, FUMO, the diffusion-transformer variant) are future-dated / have no
   released weights; DPIT and the self-supervised-diffusion checkpoints are Google-Drive-hosted
   and heavier. DSRNet is the strongest reflection-remover with friction-free public weights.
2. **It explicitly emits BOTH a transmission layer and a reflection layer** (the "component
   synergy" design: `t, r, recon = net(inp, vgg(inp))`, with a reconstruction head tying
   `t+r`), which is exactly what the *"is the background layer degenerate?"* kill-check needs —
   a single-output remover couldn't be probed this way.
3. **Feed-forward CNN** → ~9 s/image at 512² / ~30 s at 1024² on this M4 (MPS), so the full
   synthetic + real sweep runs in minutes, not GPU-hours.

It is a faithful stand-in for the memo's line: DPIT/FUMO/the CVPR-2026 model are refinements of
this same *transmission-layer-prior + reflection-layer* paradigm. A prior that behaves
structurally the way DSRNet does here would behave the same way — the failure below is about
the **paradigm**, not DSRNet's accuracy rank.

**Environment.** torch 2.9.1 + MPS on the M4 (the `~/Documents/fastbook/.venv`, reused per the
"reuse a compatible torch venv" note; XReflection deps — lightning, timm, opencv,
scikit-image — pip-installed into it). The arch + `Vgg19` hypercolumn are imported from a local
clone of `github.com/hainuo-wang/XReflection`; the `net_g.*` weights load with **0 missing / 0
unexpected** keys. Reproduce with:
`XREFLECTION_DIR=<clone> DSRNET_CKPT=<dsr.ckpt> python run_bet1_probe.py`.

## 2. Input adaptation (`log(photo) → [0,1]`, documented)

The additive mirror is in **linear** light: `photo_lin = T·B ⇒ log(photo_lin) = log(T)+log(B)`.
Per image (RENDER-A linear EXR, values here in `[0.005, 0.5]`, no blow-out):

1. `logI = log(clip(I_lin, ε, ∞))`, `ε = 1e-3` (the memo's dark-`B` risk; irrelevant here since
   the darkest pixel is 0.005 — dark backgrounds are the *easy* case anyway).
2. Robust per-image min-max to the model's expected `[0,1]`: `lo,hi = pct(logI, [0.5, 99.5])`,
   `x = clip((logI−lo)/(hi−lo), 0, 1)`. Feed `x` to DSRNet.
3. Invert a returned layer `y` back to linear de-lit glass: `exp(y·(hi−lo)+lo)`.

Both model outputs are inverted this way and each is tested as the candidate de-lit `T` (which
layer catches the flat tint vs the natural-looking background is precisely what the probe must
discover). **Control** (`separate_srgb`): the same model run on the **sRGB display image, no
log** — to tell a log-space distribution-shift failure apart from a wrong-prior-domain failure.

## 3. Drag-test table (the report-014 instrument, verbatim)

One cathedral piece re-sourced from 9 UV positions; dispersion of the piece-mean. lum-CV is
gain-invariant (directly comparable to the standing numbers); Lab dE reported under a flat unit
illuminant. `corr` = luminance correlation of the candidate map with the input photo;
`med` = candidate map median (linear). **Run at 512²; 1024² native confirms (last two rows).**

**cathedral-green** — grain floor lum-CV **0.0085**, bar to beat = classical **0.1376**:

| candidate (de-lit `T`)        | lum-CV ↓ | Lab dE | corr w/input | map median | reading |
|-------------------------------|:--------:|:------:|:------------:|:----------:|---------|
| raw photo (no de-light)       | 0.2921   | 12.36  | +1.000       | 0.164      | baseline |
| **classical `T` (the bar)**   | **0.1376** | 18.57 | +0.860      | 0.470      | standing 0.140 |
| **Bet 1: log → transmission** | **0.2755** | 11.98 | **+0.909**  | 0.119      | **≈ copy of input; FAILS (2× the bar)** |
| Bet 1: log → reflection       | 0.1105   | 0.90   | +0.224       | **0.0076** | **degenerate near-black; unusable** |
| control: sRGB → transmission  | 0.2679   | 13.79  | +0.932       | 0.149      | copy of input (log didn't help) |
| control: sRGB → reflection    | 0.7657   | 1.45   | +0.473       | 0.0006     | empty/noise |
| — 1024² log → transmission    | 0.2742   | 11.49  | **+0.984**   | 0.126      | copy of input, sharper |
| — 1024² log → reflection      | 0.0371   | 0.44   | **+0.075**   | 0.0074     | empty, uncorrelated w/ scene |

**wispy-white** (control material, already solved by classical) — grain floor **0.0273**,
classical **0.0497**:

| candidate | lum-CV | corr w/input | map median | reading |
|-----------|:------:|:------------:|:----------:|---------|
| raw photo | 0.1415 | +1.000 | 0.242 | baseline |
| classical `T` | 0.0497 | +0.828 | 0.829 | the known win |
| log → transmission | 0.1290 | +0.893 | 0.204 | copy of input |
| log → reflection | 0.0302 | +0.497 | 0.092 | empty-layer artifact, not separation |

Even where the reflection-layer lum-CV dips below the bar (0.11 cathedral / 0.03 wispy), it is
the numeric signature of a **near-empty constant map**, disqualified by the memo's *"degenerate
background layer"* clause — confirmed by median ≈ 0 and input-correlation ≈ 0. There is **no
candidate that both beats the bar and is a non-degenerate glass map.**

## 4. Panels (own-eyes read)

`results/bet1_probe/panel_cathedral-green.jpg` — **the single most informative panel.**
Left→right: *input photo* (sky/cloud top, green field bottom — the transmitted landscape baked
into the glass) | *log transmission layer* (**visibly the same landscape** — background kept) |
*log reflection layer* (**near-black**, faint horizon ghost — empty) | *authored GT* (a **flat
mint green** — what de-lit glass should be) | *classical de-lit T* (envelope removed, but the
see-through sky/field residual remains — the known half-win). DSRNet's two layers look like
*(input, black)*; **neither** approaches the flat GT.

`results/bet1_probe/panel_real_green_sheet.jpg`, `..._orange_sheet.jpg` (tutorial hammered-
cathedral sheets, report 013's real assets) and `..._reactive_ice.jpg` (a clean-corpus Bullseye
Cathedral swatch) — the same on real photos: transmission-layer correlation with input
**0.99–1.00**, reflection layer **pure black** (median ≈ 0.001). The garden bokeh, the
backlight hotspot, and the swatch's own tint all stay in the transmission layer; the reflection
layer carries nothing. `panel_wispy-white.jpg` completes the synthetic set.

## 5. Diagnosis — the inverted prior, and what it costs Bet 1

**Root cause: the prior is INVERTED relative to our problem (not a fixable log-space
shift).** A single-image reflection remover is trained on `I = T_clean + R_ghost`, where the
**transmission `T_clean` is the recognizable natural scene it must PRESERVE** and `R_ghost` is
a sparse, often blurred, *secondary reflected image* it must subtract. Map that onto us: our
transmitted background `B` (garden, sky, field) **is** the natural-looking scene, so the prior
faithfully **keeps it in the transmission layer** — the exact thing we needed removed — while
the flat, low-frequency, *multiplicative* glass tint `log(T_glass)` looks nothing like a sparse
reflected ghost, so the model drives the reflection layer to ≈ 0. The two degeneracies
(transmission = copy-of-input, reflection = empty) are the **same fact** seen from both heads.
The sRGB control failing identically proves the `log` reframing is not the blocker — even given
the additive space, the prior's layer-selection semantics point the wrong way.

**So the 027 §7 framing is half right and half wrong.** The *algebra* mirrors (a `log` does
turn `T·B` into a two-layer additive split), but the *prior* does not mirror: reflection-
removal's generative knowledge lives on the layer we want to **keep** (natural scene →
transmission), not on the layer we want to **remove**. Off-the-shelf transfer therefore cannot
work for any checkpoint in this family; a stronger remover (DPIT / the CVPR-2026 diffusion
model) would preserve the background *better*, i.e. fail *harder* on our objective.

**Implication for Bet 1's fine-tuning stage (what survives, what changes).** The
*architecture* is not what failed here — a dual-stream layer-separation backbone (DSRNet's
component synergy, or the CVPR-2026 joint-latent cross-attention design) is still structurally
the right tool for a two-layer split, and its pretrained low-level features (edges, bokeh,
scene statistics) plausibly still transfer. What is dead is the assumption that the pretrained
**layer-selection semantics** transfer: the mapping *which stream gets the natural scene,
which gets the residual* must be **retrained from our supervised pairs**, with the loss roles
swapped — the *removed* stream supervised to be the transmitted background `gt_B`, the *kept*
stream supervised to be the flat glass `logT`. That needs MATERIAL_MODEL_V3's explicit `gt_B`
export (G1/G2: render the background as its own ground-truth layer) and ~20–50k
`(logI, logT, logB)` triples across the 13 recipes, then an A100-class run that is a genuine
re-training of the output heads/attention roles, not a LoRA nudge. **Bet 1 therefore moves
from "cheap adaptation of a hot external line" to "moderate supervised training run whose main
external asset is the backbone, not the prior"** — which puts it on the same cost/evidence
footing as Mira's Bet C (feed-forward `T,B` prediction) and Bet 2 (foundation backbone
fine-tuned to emit our channels), rather than ahead of them. The honest sequencing: the `gt_B`
generator change is the prerequisite for *all three*, so it — not another checkpoint download —
is the next concrete step if the see-through split stays funded.

## 6. Verdict

**KILL.** The log-space reflection-removal-mirror hypothesis is falsified as a zero-training
method: the transmission layer is a copy of the input (drag lum-CV 0.274–0.276, corr 0.91–0.98,
vs the 0.140 bar) and the reflection layer is a degenerate near-black residual — both kill
criteria, on synthetic cathedral **and** on real hammered-cathedral sheets, with the no-log
control failing identically (wrong-prior-domain, not numerical adaptation). A clean, cheap,
decisive negative: it removes the "zero-training transfer" version of the single most-hyped
external-literature bet from the table, and re-prices the trained version (§5) onto the same
footing as the other supervised `T·B` bets, all of which now wait on the same `gt_B` generator
change (MMv3 G1/G2).

## 7. Files / provenance

- `bet1_probe.py` — DSRNet loader (0-missing-key state-dict load from the lightning ckpt) +
  `separate_log` / `separate_srgb`; env `XREFLECTION_DIR`, `DSRNET_CKPT`.
- `run_bet1_probe.py` — synthetic drag scoring (reuses `assembled_bench.drag_test`) + degeneracy
  diagnostics + panels; real-image qualitative panels.
- `results/bet1_probe/drag_table.json` — every number above; `panel_*.jpg` — committed,
  downscaled (256-px rows, 23–107 KB each).
- External / not committed: XReflection clone, `dsr-25.8915.ckpt` (1.66 GB), `assembled_data/`
  (gitignored EXRs — regenerate with `generate_assembled.py`; cathedral-green + wispy-white
  seed42 used here, copied read-only from the report-014b uniform-branch renders).
- Env: torch 2.9.1 / MPS / M4; DSRNet 124.6 M params; probe run at 512² (1024² confirmatory).
