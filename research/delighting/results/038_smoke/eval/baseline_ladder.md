# EVAL_PROTOCOL baseline ladder — foundation model (iteration 038)

Backbone `tiny` · 5 held-out-identity test samples (seed%5==0 / 800-812) · 2 cross-lighting groups.

**Family 1 — cross-capture consistency (invariance_T macro, lower = more consistent).**
Frozen rows read from EVAL_PROTOCOL §5; model row computed here.

| route | invariance_T | source |
|---|---|---|
| raw copy | 0.0946 | frozen §5 |
| luma quotient α=1 | 0.0815 | frozen §5 |
| classical (frozen) | 0.0932 | frozen §5 |
| **foundation (tiny)** | **0.0576** | **this run** |

**Family 3/GT accuracy + Family 2 texture preservation (model row; classical frozen).**

| metric | classical (frozen) | quotient (frozen) | flatten control | foundation |
|---|---|---|---|---|
| T-MAE ↓ | 0.1080 | — | — | 0.1941 |
| h-MAE ↓ | 0.1550 | — | — | 0.2200 |
| fine retained-energy (flatten gate) | 1.2700 | 1.2400 | 0.0300 | 29.2542 |
| FCS survival ↑ | 0.5090 | 0.5890 | 0.0000 | — |

**Family 4 — confidence calibration (§1d).**

- Spearman(conf, −err): -0.2436 (higher = better)
- ECE @ τ=8/255: 0.3080 (lower = better)

**Continuation gate (consultant plan).**

- beats classical on primary: True
- beats quotient on primary: True
- sub-floor flatten flag: False
- texture-hallucination flag: True
- **GO: False**
