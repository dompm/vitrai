# RESUME — 055 train-once pilot

Last checkpoint: **step 17999 / 18000** (written 2026-07-27 07:11:56).

- adapter:     `/Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/agent-a1d2be47074cefd82/research/delighting/results/055/train/adapter.pt`
- train state: `/Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/agent-a1d2be47074cefd82/research/delighting/results/055/train/train_state.pt` (optimizer + scheduler + step)
- loss log:    `/Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/agent-a1d2be47074cefd82/research/delighting/results/055/train/train_log.jsonl` (one JSON object per logged step)

Config: backbone=marigold-iid crop=512 bs=1 lr=0.0001
Data roots:
  - /Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/agent-a1d2be47074cefd82/research/delighting/pilot_053_out
  - /Users/dominiquepiche-meunier/Documents/vitrai-datasets/render_pilot_v1

## Resume the run

```
caffeinate -i /Users/dominiquepiche-meunier/Documents/fastbook/.venv/bin/python /Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/agent-a1d2be47074cefd82/research/delighting/foundation/train.py --data /Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/agent-a1d2be47074cefd82/research/delighting/pilot_053_out /Users/dominiquepiche-meunier/Documents/vitrai-datasets/render_pilot_v1 --backbone marigold-iid --cache-only --steps 18000 --bs 1 --crop 512 --lr 1e-4 --log-every 25 --save-every 250 --snapshot-every 2000 --out /Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/agent-a1d2be47074cefd82/research/delighting/results/055/train --resume
```

`--resume` reloads adapter + optimizer + scheduler from `train_state.pt` and continues at
the saved step; the JSONL log is appended, not truncated.

---

## Eval leg (2026-08-05)

Training is COMPLETE (17,999 steps). Remaining compute was the §4 synthetic per-preset table.

- running detached: `foundation/eval_foundation.py --ckpt results/055/train/adapter.pt
  --backbone marigold-iid --cache-only --data <pilot_053_out> <render_pilot_v1>
  --out results/055/eval --work 512`
- log: `research/delighting/results/055/eval_run.log`
- output when done: `results/055/eval/eval.json` + `baseline_ladder.md`

DONE already (safe to write the report from these):
- `results/055/curves.png`, `train_log.jsonl` — §3
- `results/055/real/` — 15 panels + `real_stats.json` — §5
- `results/055/pairs/realpairs_consistency.json` — screened 140/145 pairs, 64 products — §6
- `results/055/pairs_broad/realpairs_consistency.json` — sensitivity, 161/79

NOTE: eval_foundation was SIGKILLed on its first attempt — it kept every prediction resident
(323 samples x 6 conditions x ~12.6 MB ~= 24 GB). It now streams grouped by identity; if it
dies again it is NOT memory, look elsewhere.
