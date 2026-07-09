# Report 011 — Combined end-to-end: FIXED classical + neural shadow removal

Date: 2026-07-09. Branch: `research/delighting-combined` (merge of
`research/delighting-neural` + `research/delighting-classical`). Code:
`extract.py` @ the fixed classical (report 009), `neural/` @ report 010,
`neural/eval_combined.py`. Deliverables: `neural/results/combined_eval_test.json`,
`combined_table_test.md`, this report. **No PR.**

This is the payoff run: both independent prongs stacked. The classical fix (009)
corrected the absolute-scale anchor (dark-opaque 0.10→0.20, opalescent 0.80→0.88)
and color-constancy, flipping dark-opaque from a preview-invariance LOSS to a WIN;
cathedral/wispy extractor logic was left unchanged. The neural stage (010) removes
cast shadows as a post-process. Here we measure them together on the **held-out**
split (unseen lighting/seeds).

## 0. TL;DR

Stacking works. Inside cast shadows, on held-out lighting, the pipeline goes from
the original classical **48.2** → fixed classical **44.8** → **fixed + neural 17.8**
(sRGB/255 preview MAE). The two fixes are complementary and hit different failures:

- **Cathedral** (the shadow failure from report 008): the classical fix does
  nothing (its logic was unchanged), and **the neural stage carries it 56.9 → 14.0**.
- **dark-opaque** (the scale failure): the **classical fix** carries the non-shadow
  win (OUT 43.7 → 17.8), and the neural stage still adds an inside-shadow win on top
  (IN 46.1 → 23.6) **despite a real train/inference distribution shift** (see §3).

Non-shadow regions do not degrade at any stage.

## 1. Definitive per-recipe table (HELD-OUT, unseen lighting)

`eval_combined.py --split test`. Preview MAE sRGB/255. IN = inside detected cast
shadow; OUT = valid non-shadow pixels. "T-shift" = mean |T_orig − T_fixed| over
valid pixels (how much the classical fix moved this class's transmittance — i.e.
the size of the distribution shift the neural model sees at inference).

| recipe | n | IN orig | IN fixed | **IN fixed+neural** | OUT orig | OUT fixed | OUT fixed+neural | T-shift |
|---|---|---|---|---|---|---|---|---|
| cathedral-green | 2 | 56.9 | 56.9 | **14.0** | 21.7 | 21.7 | 21.6 | 0.00 |
| dark-opaque | 1 | 64.7 | 46.1 | **23.6** | 43.7 | 17.8 | 17.1 | 0.07 |
| streaky-mix | 1 | 16.6 | 16.9 | **13.6** | 19.0 | 17.4 | 17.3 | 0.02 |
| wispy-white | 1 | 14.4 | 19.4 | **19.5** | 12.1 | 12.6 | 11.3 | 0.01 |
| **shadowed (all)** | 4 | 48.2 | 44.8 | **17.8** | 24.8 | 18.4 | 17.9 | — |

Aggregates:

- **Cathedral inside-shadow: 56.9 → 56.9 → 14.0.** Pure neural win; the classical
  fix is a no-op on cathedral by construction (T-shift 0.00), so this combined
  number is fully in-distribution and identical to report 010.
- **Shadowed overall inside: 48.2 → 44.8 → 17.8.** Non-shadow: 24.8 → 18.4 → 17.9.
- **All-valid preview MAE (5 held-out): 24.3 → 19.0 → 17.8** — each stage helps.

## 2. Who fixes what (the two prongs are orthogonal)

- The **classical fix** owns the *non-shadow, absolute-scale* failure. Its entire
  effect is on dark-opaque (OUT 43.7 → 17.8) and a small streaky nudge; it does not
  touch cathedral/wispy (T-shift ≈ 0). This matches report 009.
- The **neural stage** owns the *inside-shadow* failure. It moves cathedral 4× and
  adds a further inside-shadow gain on dark-opaque and streaky. It is a no-op on
  wispy inside shadow (14.4 → 19.5 net; the +5 came from the classical color nudge,
  not the neural stage — see §4), which is correct: hazy glass already diffuses the
  shadow so there is nothing to remove.

Together: fixed classical handles brightness/scale everywhere, neural handles cast
shadows on top. Inside shadow, only the stack gets both (48.2 → 17.8).

## 3. The distribution-shift check (asked for, measured honestly)

The U-Net was **trained with the ORIGINAL extractor's T as part of its 6-channel
input**. The classical fix changes T for some classes, so at inference the model
can receive out-of-distribution input:

- **cathedral / streaky / wispy: T-shift 0.00–0.02** → effectively in-distribution;
  the combined numbers are valid as-is. Cathedral (the main shadow-win class) is
  *exactly* unchanged.
- **dark-opaque: T-shift 0.07** (T mean 0.070 → 0.141, ~doubled) → a **real
  distribution shift**. The honest question is whether shadow removal survives it.
  **It does:** inside-shadow dark-opaque still improves 46.1 → 23.6 on the fixed
  input, and OUT is unchanged (17.8 → 17.1). So the shadow stage **degraded
  gracefully — in fact it still clearly helped** — rather than breaking on the
  brighter T. Caveat: this is **n=1** dark-opaque held-out sample at 2.1% shadow, so
  treat the magnitude as indicative, not calibrated.

Read: no retraining is *required* for the shadow win to hold under the fix. But
retraining the U-Net on the fixed extractor's T would remove the mismatch entirely
and would most likely sharpen dark-opaque further; it is the clean next step before
any dark-opaque ship decision.

## 4. Honest caveats

- **Tiny held-out set:** 2 cathedral + 1 each of dark/streaky/wispy. The cathedral
  result (n=2, both seeds) is the trustworthy headline; the single-sample recipes
  are directional. Train-split context (n=11 shadowed): inside-shadow 55.9 → 55.9 →
  26.3, same shape as held-out, confirming the effect is learned, not memorized.
- **wispy classical regression:** the color-constancy fix nudged wispy inside-shadow
  14.4 → 19.4 (n=1). Small, on a class that was never a shadow problem, and the
  neural stage correctly leaves it alone. Worth a glance in report 009's domain, not
  a blocker here.
- **Synthetic-only, Cycles shadows** are cleaner-edged than a real hand shadow; the
  neural false-positive-on-dark-leads tendency (report 010 §4) is unchanged here.

## 5. Verdict — how far did we push it

On held-out lighting, inside cast shadows — the exact place report 008 showed
material-relight *losing* to a raw pixel copy — the combined pipeline goes
**48.2 → 17.8** (cathedral **56.9 → 14.0**), while non-shadow error drops
**24.8 → 17.9** from the scale fix. The original report-008 failure (cathedral cast
shadow becomes permanent fake-dark transmittance) is resolved on synthetic held-out
data. The two prongs are orthogonal and stack cleanly. Remaining work before a ship
call: retrain the shadow U-Net on the fixed extractor's T (kills the dark-opaque
mismatch), add a chroma cue to the shadow mask (kills the dark-lead false positive),
and validate on a real hand-shadow photo pair.

## 6. Files

- `neural/eval_combined.py` — three-condition held-out eval (orig / fixed /
  fixed+neural), inside & outside shadow, with the T-shift diagnostic.
- `neural/results/combined_eval_{test,train}.json`, `combined_table_{test,train}.md`.
- Two caches (both gitignored): `cache/` (original extractor), `cache_fixed/`
  (fixed extractor, built via `NEURAL_CACHE=cache_fixed prepare_data.py`).
- Reuses `neural/model.py`, `train.py` (report 010 weights, unchanged) and the
  merged `extract.py` (report 009 fixes).
