# 027 — Fresh bold tracks: a literature-grounded research-bets memo

Date: 2026-07-10. Branch `research/delighting-027` (off `research/delighting`).
Deliverable pair: this memo + `docs/MATERIAL_MODEL_V3.md` (the forward-model proposal).
Role: literature scout. The maintainer is explicitly skeptical that classical/hybrid
refinements are the 2026 answer and asked for **bolder, learned** directions grounded in
**current** literature. This memo does NOT recommend classical refinements — that track is
measured and owned (reports 009/016/017/020/023/025). Every bet is a learned method, every
citation was fetched/verified (arXiv IDs and venues in §6; two future-dated IDs are flagged
as such — they surface because this environment's clock reads July 2026).

Companion context assumed read: `RESEARCH_STATE.md`, `CODEX_RESEARCH_PERSONA.md` (Mira's
GlassNet/Bets A–D), reports 013/014(+b)/021/022/023/025.

---

## 0. The problem, stated the way the literature lets us attack it

Single phone photo of a thin glass sheet against an unknown, often high-contrast background
→ capture-invariant per-pixel material maps. The measured, unsolved **core** (reports
013 §5, 014 §4, 014b §8.1) is the see-through split:

> **photo ≈ T · B** — two unknowns per pixel, one observation. Classical extraction leaves
> the transmitted background baked into `T`, so dragging a transmissive cathedral piece
> still swings green↔blue (relit luminance-CV **0.140** vs grain floor **0.0085** — 16× the
> floor; T-MAE-vs-authored **0.134**). Opalescent/wispy is already **solved** (relit
> dispersion collapses to the grain floor, dE 1.01 ≈ floor 0.92, report 014 §4). **All
> remaining product value on the hard axis lives in the transmissive `T·B` split.**

Two framings unlock most of the recent literature, and they are the spine of this memo:

1. **The `T·B` split is the multiplicative mirror of reflection removal.** Reflection
   removal solves `photo = T + R` (transmission + an additive reflection layer). Take the
   log: `log(photo) = log(T) + log(B)` — our multiplicative split becomes an **additive
   two-layer separation** in log space, structurally identical to the problem a large,
   fast-moving 2025–26 diffusion-prior literature already attacks. Their "transmission-layer
   prior" is literally a *clean-glass-color* prior. **We are the mirror image of a hot field**,
   and we hold the one asset that field is starved for (below).

2. **We own paired ground truth at scale; they don't.** Reflection-removal and single-image
   SVBRDF papers fight for a few thousand real `(mixed, clean)` pairs. Our Blender generator
   emits `(photo, T, h, B, height, normal, shadow-pair)` by construction across 13
   real-grounded recipes (reports 021/022), and the assembled-pair instrument (report 014)
   produces held-out cross-lighting truth. Every bet below is designed to convert that
   asymmetry into an edge.

---

## THE BETS

### Bet 1 — Log-space layer separation with a reflection-removal diffusion prior *(top pick)*

**Core idea.** Port the 2025–26 single-image reflection-*separation* diffusion stack to our
mirror problem. Work in log space so `photo = T·B` → `logI = logT + logB`, an additive
two-layer split. Fine-tune a **joint latent diffusion** that denoises *both* layers with
cross-layer attention (exactly the CVPR 2026 "Reflection Separation via Joint Latent
Diffusion" design — a unified model generating transmission + reflection simultaneously with
a cross-layer self-attention for disentanglement and a disjoint sampling schedule) but
retargeted so layer-A = intrinsic glass `T` (+`h`) and layer-B = the transmitted background.
The generative prior is what the ill-posedness *demands*: the split is genuinely
multimodal (a dark streak is glass-or-shadow-or-background), and a diffusion posterior
represents that ambiguity instead of regressing to a mean the way a feed-forward net does.
FUMO's VLM-guided spatial gate and DPIT's transmission-prior injection are drop-in
conditioning ideas; our class prior (Track C) is the natural gate signal.

**Why it beats the from-scratch neural track on the core metric.** The whole reason
cathedral fails is that the model can't tell "structured thing behind the glass" from
"structure in the glass." A diffusion prior over *natural backgrounds* (gardens, windows,
sky — the corpus's actual backdrops) knows what a plausible `B` looks like and can therefore
*explain away* the garden bokeh into `logB` instead of leaving it in `T`. A tiny U-Net
trained only on synthetic (GlassNet) has no such background prior.

**What it needs.** Data: our generator at scale — 20–50k synthetic `(logI, logT, logB)`
triples across all 13 recipes with the `B` layer rendered explicitly (a one-node generator
change, §MMv3). GPU: fine-tuning a pretrained SD-1.5/SDXL-class layer-separation backbone is
an **A100-class rented / backend** job (the maintainer blessed a backend: "if cloud inference
is much better, I'll add a backend"). Inference is a cloud call — fine.

**Expected ceiling vs the classical track.** Classical caps cathedral relit lum-CV at 0.140
(16× floor). A background-aware generative split should push cathedral toward the wispy
regime — target **lum-CV ≤ 0.05, dE toward the grain floor** — because it can actually
*remove* transmitted structure rather than smooth an envelope. This is the first method with
a mechanism to close the north-star gap, not just narrow it.

**Falsifiable 1-week milestone.** Zero-/few-shot a *pretrained* reflection-removal model
(e.g. the DPIT or self-supervised-diffusion checkpoints) on `log(photo)` of the report-014
assembled cathedral pairs; feed the recovered "transmission layer" back through
`assembled_bench.py`'s drag test. **Kill criterion:** if the recovered `T` doesn't beat the
classical 0.140 lum-CV on cathedral drag, the log-space mirror hypothesis is dead and Bet 1
is abandoned. (Cheap, uses only existing instruments and an off-the-shelf checkpoint.)

**Risk.** (a) Log space is numerically nasty where `B→0` (dark backgrounds) — mitigated by
an ε-floor and the fact that dark-background captures are the *easy* case. (b) Reflection
priors are trained on *additive* mixtures with different statistics; the fine-tune may need
our synthetic pairs to fully re-home the prior. (c) A diffusion split can *hallucinate*
plausible-but-wrong background — but for *consistency* (the actual product metric) a
consistent wrong split still wins, and uncertainty can gate it.

**Differentiation / collaboration with Mira.** Her Bet C predicts glass + background with a
feed-forward net; this is a *generative diffusion posterior* over the same split — a
different, stronger tool for the same target. Collaboration point: her Bet C net makes an
excellent **conditioning/initialization** input to the diffusion sampler (coarse split →
diffusion refine), i.e. Materialist's init+refine pattern applied to layer separation.

---

### Bet 2 — Foundation intrinsic-prior transfer: a Marigold/RGB↔X-style dense predictor fine-tuned to emit Vitraux `T,h`

**Core idea.** Instead of training GlassNet from scratch (Mira Bet A — a tiny U-Net with
zero real-world prior), **stand on a pretrained latent-diffusion dense predictor** and
fine-tune it to output *our* material state. RGB↔X (SIGGRAPH 2024) and Marigold-Intrinsic
(2025) already repurpose Stable Diffusion into per-pixel intrinsic-channel estimators
(albedo/roughness/metallic); DiffusionRenderer (NVIDIA, CVPR 2025) does the same as a
**G-buffer** predictor from a single image/video. These backbones carry a massive prior on
natural-image statistics — the very "what does a background look like" knowledge the
`T·B` split needs — learned from billions of images we can't match synthetically. We add a
LoRA / lightweight decoder that emits `(T, h)` (+ optionally the MMv3 channels) and fine-tune
on our synthetic corpus with the preview-invariance loss (report 008) as the objective.

**Why bold, not classical.** This is not tuning a constant; it's transferring a
foundation-model prior into a niche material-capture task with ~1k real swatches — exactly
the regime where fine-tuned diffusion dense-predictors have repeatedly beaten from-scratch
CNNs (Marigold's headline result). It gives the learned track a real-image backbone in one
step.

**What it needs.** Data: synthetic `(photo, T, h)` at 20–50k for LoRA fine-tune, plus the
1,281-swatch corpus as an unlabeled real distribution for the invariance loss. GPU:
LoRA fine-tune of an SDXL-class predictor is **rented A100 or a single high-VRAM node**;
distillable to a small student for local M4 inference later. Backend inference acceptable.

**Expected ceiling.** Marigold-class transfer typically matches or beats task-specific nets
on dense prediction with far less data. Realistic target: **generalizes to held-out material
identities** (GlassNet's open weakness, RESEARCH_STATE "held-out-material split") and matches
classical on wispy while improving cathedral T-MAE below 0.134 — because the natural-image
prior disambiguates background. It won't fully *separate* `T·B` on its own (that's Bet 1's
job); it's the generalization workhorse.

**Falsifiable 1-week milestone.** Take an *off-the-shelf* RGB↔X or Marigold-Intrinsic
checkpoint, run it zero-shot on the 9-sheet library + assembled renders, and correlate its
albedo/shading split against our GT `T` and illumination `L`. **Kill criterion:** if the
foundation intrinsic split has *no* usable correlation with `T` on transmissive glass (i.e.
it treats the whole sheet as opaque albedo), the transfer premise is weak and we downgrade to
Bet 1 only.

**Risk.** These priors are trained on *opaque* scene intrinsics; thin transmissive glass is
out-of-distribution (their albedo≠our `T`). The fine-tune may fight the backbone. Mitigate by
choosing DiffusionRenderer (closest to a relightable G-buffer) and by the invariance loss
doing the real-domain adaptation.

**Differentiation / collaboration.** This is the *backbone upgrade* for Mira's GlassNet: same
output contract (`T,h,mask,confidence`), but a foundation prior instead of scratch weights.
Cleanest collaboration in the memo — propose GlassNet-v2 = this backbone.

---

### Bet 3 — Render-in-the-loop distillation with self-supervised *real-corpus* light-transport consistency

**Core idea.** Two ingredients the classical/from-scratch tracks each lack half of.
(1) **Differentiable forward model in the loop** (Materialist's init+refine north star):
predict `(T,h,B,L)`, push through our own differentiable renderer
`photo = T·[h⟨B⟩+(1−h)B]` (MMv3 upgrades this forward op), backprop the recon loss — the
network only gets credit if the state *re-renders* the photo. (2) **The bold part:
self-supervised consistency on the 1,281-swatch REAL corpus via IC-Light's light-transport
linearity.** IC-Light (ICLR 2025 oral) scaled to 10M images on one physical law: *the linear
blend of an object's appearances under two lightings equals its appearance under the blended
lighting.* We have the same handle for free — the cross-lighting instrument (report 017
`eval_cross_lighting.py`) and any two real captures of the same sheet must de-light to the
*same* `T`. Train with recon loss on synthetic (has GT) **+** an unsupervised
cross-capture/light-transport consistency loss on real swatches (no GT needed). This is the
sim-to-real bridge pure-synthetic GlassNet can't build.

**Why bold.** It turns our *invariance metric into a training signal* and imports a proven
foundation-scale self-supervision trick onto real glass. The consistency loss is exactly the
product's success metric (RESEARCH_STATE "primary metric is cross-capture consistency"), so
we optimize the thing we're graded on, on real data, without labels.

**What it needs.** Data: synthetic pairs + the corpus (ideally a few dozen *real*
cross-lighting pairs — the still-unshot capture RESEARCH_STATE flags; even manufacturer
multi-photo SKUs give weak pairs). GPU: mid-size — **local M4 feasible for a PoC**, rented
A100 to scale. Fits the "slow-but-quality, distill later" path.

**Expected ceiling.** Won't out-separate Bet 1 on a single photo, but should deliver the best
*measured cross-capture invariance* (the primary metric) because it trains on it directly —
target: match report 020's per-sheet-pooled classical invariance (dark-opaque 0.045) *and*
extend it to cathedral, where classical is capture-dependent (017: 0.18–0.20).

**Falsifiable 1-week milestone.** Add the IC-Light linearity loss to the existing GlassNet
training on synthetic multi-lighting only (we can *synthesize* blended-lighting renders
exactly), and measure whether held-out cross-lighting invariance improves over the current
GlassNet. **Kill criterion:** no invariance gain from the consistency loss on synthetic ⇒ the
loss is inert, don't take it to real data.

**Risk.** The linearity law assumes additive light transport; strong haze/scatter partially
violates it (mitigated by MMv3's explicit scatter term). Real cross-lighting pairs are scarce
until the capture ask lands — the synthetic-only milestone de-risks that.

**Differentiation / collaboration.** This is the concrete build-out of Mira's Bet B
(test-time neural optimization) turned into an *amortized* trained model with a real-data
self-supervision loss she hasn't specified. Natural joint effort with her renderer work.

---

## RANKING & RECOMMENDATION

**#1 — Bet 1 (log-space reflection-removal diffusion prior).** It is the only bet with a
*mechanism* to actually remove transmitted background rather than smooth it, it rides the
single hottest, best-verified 2025–26 external literature line, and it is the one place our
paired-GT generator is a decisive, unfair advantage over a field that has no ground truth.
The one-week off-the-shelf milestone is cheap and genuinely falsifiable. Highest expected
movement on the north-star metric.

**#2 — Bet 2 (foundation intrinsic-prior transfer).** Highest *generalization* ceiling and
the cleanest upgrade to the existing learned track — it fixes GlassNet's held-out-material
weakness by giving it a natural-image backbone. Slightly lower rank only because thin
transmissive glass is out-of-distribution for opaque-intrinsic priors, so its solo
`T·B`-separation power is unproven where Bet 1's is mechanistically motivated.

**#3 — Bet 3 (render-in-loop + real light-transport self-supervision).** The best *primary-
metric* (consistency) optimizer and the essential sim-to-real bridge, but it's an
enhancement layer more than a new capability — its consistency loss and differentiable
renderer are ingredients that *also* strengthen Bets 1 and 2. Rank #3 as a standalone;
promote it to a shared training component.

**Recommendation.** Run Bet 1's off-the-shelf milestone and Bet 2's off-the-shelf milestone
**this week, in parallel** — both are zero-training probes on existing checkpoints and
instruments, so they cost days, not GPU-weeks, and they cleanly falsify the two premises. If
Bet 1's probe clears the 0.140 cathedral bar, commit the backend GPU there and fold Bet 3's
IC-Light consistency loss into its fine-tune. Treat Bet 2 as GlassNet-v2's backbone and hand
it to Mira as the collaboration seam. Do **not** build all three cold — the probes decide.

---

## §6. Verified citations (fetched abstracts / venue pages, not recalled)

Reflection / layer separation (the mirror line):
- **Reflection Separation from a Single Image via Joint Latent Diffusion** — Huang, Wang, Liu,
  Chuang, CVPR 2026, arXiv **2606.04107** (fetched: unified two-layer diffusion, cross-layer
  self-attention, disjoint sampling; future-dated ID per env clock).
- **FUMO: Prior-Modulated Diffusion for Single Image Reflection Removal** — arXiv **2603.19036**
  (VLM guidance → spatial gate in the denoising U-Net; future-dated ID).
- **DPIT: Single Image Reflection Removal via Dual-Prior Interaction Transformer** — arXiv
  **2505.12641** (lightweight transmission-prior generation + dual-prior interaction).
- **Reflection Removal through Efficient Adaptation of Diffusion Transformers** — arXiv
  **2512.05000**.
- **Single Image Reflection Removal via Self-Supervised Diffusion Models** — arXiv **2412.20466**.

Diffusion / foundation intrinsic & relighting priors:
- **RGB↔X: Material- and lighting-aware diffusion** — Zeng et al., SIGGRAPH 2024, arXiv
  **2405.00666**.
- **Marigold** (CVPR 2024, arXiv **2312.02145**) + **Marigold-Intrinsic / IID** journal
  extension arXiv **2505.09358** (albedo + diffuse-shading + non-diffuse residual, and
  albedo/roughness/metallic variants).
- **IntrinsicAnything: Learning Diffusion Priors for Inverse Rendering under Unknown
  Illumination** — Chen et al., ECCV 2024, arXiv **2404.11593** (diffusion material prior
  regularizing an ill-posed decomposition — the exact template for Bet 1's prior).
- **DiffusionRenderer: Neural Inverse and Forward Rendering with Video Diffusion Models** —
  Liang et al., NVIDIA, CVPR 2025, arXiv **2501.18590** (single-image/video → G-buffers →
  relight; Bet 2 backbone candidate).
- **IC-Light / Scaling In-the-Wild Training … by Imposing Consistent Light Transport** —
  Zhang, Rao, Agrawala, ICLR 2025 (oral), OpenReview `u1cQYxRI1H` (light-transport linearity
  self-supervision; Bet 3's real-data loss).

Hybrid inverse rendering / single-image material:
- **Materialist: Physically Based Editing Using Single-Image Inverse Rendering** — arXiv
  **2501.03717** (intern-cited; neural init + differentiable-render refine; Bet 3 template).
- **MatFusion: A Generative Diffusion Model for SVBRDF Capture** — SIGGRAPH Asia 2023, arXiv
  **2406.06539**.
- **Diffusion-Guided Relighting for Single-Image SVBRDF Estimation** — SIGGRAPH Asia 2025,
  ACM 10.1145/3757377.3763809 (shuffle-based background-consistency + specular-prior reuse to
  stabilize **saturated regions** — directly relevant to the extractor's saturation-collapse
  failure, report 022 §5).

Transparent / translucent forward & inverse rendering (for MMv3):
- **TransparentGS** — arXiv **2504.18768** (intern-cited; refraction + local light-field
  probes).
- **TSGS: Transparent Surface reconstruction via normal + de-lighting priors** — ACM MM 2025.
- **GTSR: Subsurface-Scattering-Aware 3D Gaussians for Translucent Surfaces** — arXiv
  **2603.22036** (future-dated ID).
- **RT-Splatting: Joint Reflection–Transmission Modeling** — arXiv **2605.18263** (future-dated
  ID).
- **Belcour & Barla, "A Practical Extension to Microfacet Theory for … Iridescence"** —
  SIGGRAPH 2017 (thin-film term for MMv3's flashed/dichroic layer).
- **Physics-based inverse modelling of dichroic glass (Lycurgus Cup)** — Applied Physics A,
  2026, doi 10.1007/s00339-026-09579-y.

Lighting estimation / capture:
- **DiffusionLight / DiffusionLight-Turbo** — arXiv **2312.09168** / **2507.01305** (chrome-ball
  inpainting light probes — an off-the-shelf way to *estimate the target illuminant* the
  report-014 relight step currently refuses to read).
- **LayerDiffusion / latent transparency** — Zhang & Agrawala, arXiv **2402.17113**
  (native transparent-layer generation; relevant to representing the `B` layer).
- **Diffusion-VAS: Using Diffusion Priors for Video Amodal Segmentation** — CVPR 2025 (the
  "see-through what's occluded" prior, for the video axis).

---

## §7. The single most surprising thing in the literature

**The transmitted-background problem is the exact multiplicative mirror of single-image
reflection removal — and that field is *booming* (a CVPR-2026 joint-latent-diffusion paper,
FUMO, DPIT, diffusion-transformer and self-supervised variants all in the last ~12 months) —
yet it is chronically bottlenecked on the one thing we manufacture for free: paired
ground-truth `(mixed, clean)` layers.** A single `log()` converts our `T·B` split into their
`T+R` split, so their entire denoising-prior toolbox transfers, while our Blender generator
hands us the supervised pairs their papers spend whole sections apologizing for not having.
The project has been treating the see-through split as a lonely, bespoke ill-posed problem;
it is actually the well-funded twin of a mainstream research line, and we are sitting on that
line's scarcest resource. That reframing — *we are data-rich in a data-poor field's mirror
problem* — is the highest-leverage insight in this memo, and it is what puts Bet 1 at #1.
