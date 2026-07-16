# 052 — External literature review (Gemini Deep Research): verification + implications

Date: 2026-07-16. The CTO commissioned a comprehensive literature review (2022–2026) from
Gemini Deep Research using a prompt I authored around our core problem — single-image
multiplicative layer separation `I = T·B` for physical glass material estimation. The full
25-page review is committed verbatim at `docs/external/052-gemini-litreview-2026-07.pdf`.
This memo is the lab's verification pass and the extraction of what changes (and doesn't)
for our bets. Context: our own prior surveys are report 027 (fresh-tracks scout, bet-ranked,
deliberately narrow) and the 2026-07-10 academic consultant review.

## 1. Citation verification (the 027 lesson: verify before trusting)

I spot-checked every load-bearing citation with my own fetches. **All real:**

| Work | Verified | Notes |
|---|---|---|
| **WindowSeat** (CVPRW/NTIRE 2026, arXiv 2512.05000) | ✓ code+weights, Apache 2.0 | Reflection removal via **Qwen-Image-Edit DiT + LoRA**, trained on a Blender PBR synthetic pipeline. **Senior author is Anton Obukhov — the Marigold author.** ETH Zurich + Huawei. |
| **Removing Reflections from RAW Photos** (CVPR 2025, Kee et al., arXiv 2404.14414) | ✓ (no code — Adobe/commercial) | Confirms the linear-RAW emphasis: "training on RAW simulation data improves performance more than the architectural variations among prior works." |
| **Flash-Split** (CVPR 2025, arXiv 2501.00637) | ✓ | Dual-branch **latent** diffusion separation, flash/no-flash conditioning confirmed. |
| **SeeClear** (arXiv 2603.19547) | ✓ | Generative opacification + the 396k paired transparent↔opaque synthetic dataset confirmed. |
| **Flatbed scanner R+T estimation** (C&G 2025, arXiv 2502.14462, Rodriguez-Pardo/Garces) | ✓ | Single-scanner-image transmittance+opacity estimation confirmed (project page is literally named "Delighting"). |
| **Ouroboros** (ICCV 2025, arXiv 2508.14461) | ✓ (previously known) | Cycle-consistent forward+inverse single-step diffusion; already in our consultant review. |

Marigold, RGB↔X, IntrinsicAnything are known-real from prior work. I did not verify every
one of the 100 web citations; the un-spot-checked remainder (datasets in §8, uncertainty
methods in §7) should be re-verified before any is load-bearing for a decision.

## 2. Where the review CONVERGES with what we already established

- **Its "gap #1" is our probe-028 kill, independently re-derived.** The review: reflection
  removal "universally treat[s] the transmitted layer as the clear ground truth to be
  recovered, completely ignoring the internal material properties of the transmissive medium."
  That is exactly why DSRNet returned our input as transmission (028): the priors are
  *inverted* for us. The review reaches the same conclusion from the literature that we
  reached from the bench.
- **Its "specific missing link" is our re-priced Bet 1.** Log-space transform, dual-stream
  generative separation (one stream on background statistics, one on material statistics),
  trained on synthetic pairs, output = capture-invariant PBR maps — this is the plan we
  formulated post-028 (dual-stream architectures + our (logI, logT, logB) pairs, layer
  semantics retrained) plus MMv3's gt_B export. Strong external validation, zero new design.
- **Gap confirmation:** "transmitted-layer-dominant multiplicative separation from a single
  uncontrolled image to yield physical material output remains a genuine, unaddressed gap."
  Confirms our positioning ("data-rich in a data-poor field's mirror problem") — nobody has
  shipped this; our synthetic generator + real cross-capture pairs remain a real edge.
- **Synthetic-first is the field's proven recipe.** WindowSeat (DiT+LoRA on Blender PBR) and
  RAW-Photos (synthetic mixtures beat architecture changes) both validate the exact structure
  of our plan: pretrained diffusion backbone + LoRA + our generator's data. That WindowSeat
  comes from the Marigold author makes the Marigold-backbone choice look even better.
- **Multi-illumination consistency losses** (LightCity's finding that current models lack
  illumination coherency) = our north-star cross-capture consistency metric, already frozen
  in EVAL_PROTOCOL.md.

## 3. What is genuinely NEW to us (actionable)

1. **WindowSeat as the closest working artifact** (public code+weights). Not directly usable
   (it removes reflections; our transmitted background IS the signal it would preserve), but
   its LoRA-adaptation recipe, synthetic-data curriculum, and evaluation setup are the
   closest published blueprint to our fine-tune. Worth a close code read before the Modal run.
2. **The linear-color-space mandate, stated harder than we had it** (RAW-Photos): the
   multiplicative relationship is mathematically destroyed by tonemapping. Our synthetic
   training data is linear (EXR) with camera corruption as augmentation — consistent — but
   user photos are tonemapped JPEGs. Design check for the fine-tune: the network must learn
   the inverse-tonemap implicitly (our augmentation approach), and we should verify the
   augmentation covers real phone pipelines; we cannot demand RAW from users.
3. **Pretraining/eval datasets we didn't know:** SeeClear-396k (transparent↔opaque pairs),
   TransPhy3D (11k Cycles-rendered transparent video sequences w/ depth+normals),
   3DReflecNet (22TB transparent/reflective corpus), GlassPol (real colored glass under
   polarization), OpenIllumination / OLATverse (multi-illumination real objects — candidate
   external eval for our consistency metric).
4. **Test-time diffusion posterior sampling** (DPS family): enforce `T·B = I` as a
   measurement-consistency constraint at inference. A future enhancement layer on Bet 2 —
   same role 027 assigned to test-time optimization, now with a concrete modern toolbox.
5. **VITRAIL** (stained-glass acquisition, lab-controlled): historical anchor confirming
   heterogeneous stained-glass light transport; not directly usable (lab rig).

## 4. Where the review is WEAK or misses things (for the record)

- It asserts wild paired GT is "physically impossible" — over-strong. Our catalog
  cross-capture pairs (033/044: same sheet, clean+wild) are exactly the loophole; they can't
  give per-pixel gt_B but they power the consistency metric and sim-to-real eval.
- It is unaware synthetic generation for this exact problem already exists (ours) — its #2
  recommendation is to build what we've been building since report 006. (Expected: the
  prompt didn't disclose our assets.)
- Several §7 uncertainty citations and §9 texture citations are thin (ResearchGate/thesis
  links, "code unknown") — treat that section as a menu of directions, not vetted methods.
  Our own conf-channel plan (calibrated per-pixel confidence, 034 OUTPUT_CONTRACT) already
  covers the requirement it argues for.
- The "top 5" list is reasonable but WindowSeat/Flash-Split/RAW-Photos are all
  *architecture/data* references for Bet 1 — none of them touches σ_s estimation, which our
  045 gate proved is first-order. The scatter term remains our own problem to solve.

## 5. Net effect on the lab's bets

**No bet changes.** The review independently validates the post-028 Bet-1 shape, the Bet-2
backbone choice (Marigold lineage), the synthetic-first strategy, and the consistency-loss
north star — and confirms the gap we're positioned in. It adds: a code blueprint to read
(WindowSeat), a linear-space design check for the fine-tune, candidate external datasets for
pretraining/eval, and DPS as a future test-time layer. The immediate physics agenda
(σ_s supervision — 048 merged; auto-relief — 050; retrieval — 051) is untouched: the review
has nothing on scatter estimation, which stays our differentiator.
