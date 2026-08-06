# EVAL_PROTOCOL baseline ladder — foundation model (iteration 038)

Backbone `marigold-iid` · 322 held-out-identity test samples (seed%5==0 / 800-812) · 189 cross-lighting groups.

**Family 1 — cross-capture consistency (invariance_T macro, lower = more consistent).**
Frozen rows read from EVAL_PROTOCOL §5; model row computed here.

| route | invariance_T | source |
|---|---|---|
| raw copy | 0.0946 | frozen §5 |
| luma quotient α=1 | 0.0815 | frozen §5 |
| classical (frozen) | 0.0932 | frozen §5 |
| **foundation (marigold-iid)** | **0.0764** | **this run** |

**Family 3/GT accuracy + Family 2 texture preservation (model row; classical frozen).**

| metric | classical (frozen) | quotient (frozen) | flatten control | foundation |
|---|---|---|---|---|
| T-MAE ↓ | 0.1080 | — | — | 0.1366 |
| h-MAE ↓ | 0.1550 | — | — | 0.1224 |
| fine retained-energy (flatten gate) | 1.2700 | 1.2400 | 0.0300 | 0.3045 |
| FCS survival ↑ | 0.5090 | 0.5890 | 0.0000 | 0.0700 |

**σ_s (haze-driven scatter) — report 053 / 048-owed metric, 264 held-out samples with supervised gt_σ_s.**

| metric | foundation | note |
|---|---|---|
| σ_s-MAE ↓ | 0.1218 | authored-linear, like h-MAE |
| σ_s structured-relight L1 (sRGB, 0-255) ↓ | 7.8332 | checker relit by pred σ_s vs GT σ_s (045/046) |
| — GT-relight scale (context) | 17.7739 | GT σ_s vs no-scatter; read L1 against this |

**Per-ISP-preset breakdown (053b — deployment inputs, not just clean renders).**
'clean' repeats the headline row; the held-out device preset is marked ✋ (never
seen in training — the preset-generalization axis).

| condition | invariance_T ↓ | T-MAE ↓ | h-MAE ↓ | σ_s-MAE ↓ | retained-energy |
|---|---|---|---|---|---|
| clean | 0.0764 | 0.1366 | 0.1224 | 0.1218 | 0.3045 |
| neutral_mid | 0.0739 | 0.1359 | 0.1283 | 0.1315 | 0.3003 |
| bright_window_hdr | 0.0781 | 0.1469 | 0.1157 | 0.1217 | 0.3052 |
| low_light_handheld | 0.0674 | 0.1421 | 0.1143 | 0.1187 | 0.2680 |
| android_punchy | 0.0602 | 0.1341 | 0.1247 | 0.1262 | 0.2931 |
| wide_edge ✋ | 0.0638 | 0.1304 | 0.1260 | 0.1294 | 0.2795 |

**Family 4 — confidence calibration (§1d).**

- Spearman(conf, −err): -0.0339 (higher = better)
- ECE @ τ=8/255: 0.3251 (lower = better)

**Continuation gate (consultant plan).**

- beats classical on primary: True
- beats quotient on primary: True
- sub-floor flatten flag: True
- texture-hallucination flag: False
- **GO: False**
