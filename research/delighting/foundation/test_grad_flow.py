#!/usr/bin/env python3
"""Iteration 040 — permanent GRADIENT-FLOW regression test.

Report 040's gate1b found that `FoundationDelighter.decode()` wrapped the VAE decode
call in `torch.no_grad()`. The VAE's own weights were already frozen via
`requires_grad_(False)` in `__init__` (sufficient on its own to keep them from
updating), but wrapping the forward call ALSO severed the gradient path from T's OWN
loss back to the trainable LoRA parameters — T only ever moved as a side-effect of
h/B/shadow/mark/conf's gradients, which take a different path (through the AuxHead
on `z_T_hat`, never through the no-grad decode). Discovered by training T-only for
100+ steps and finding the loss bit-for-bit unchanged: proof that zero gradient
reached ANY trainable parameter.

This bug class — a frozen submodule's forward pass ALSO blocking gradient to an
UPSTREAM trainable path, not just its own weights — is invisible to a plain
forward+backward smoke test. report 038's real_backbone_step.py used
`loss = out["T"].mean() + out["h"].mean() + out["shadow"].mean()` and reported "grads
flow to all trainable tensors" — true, but only because h/shadow's real gradient
covered for T's severed one; the test never isolated T alone, so the break was invisible.

THE TEST: for EACH head individually (T, h, B, shadow, mark, conf), zero every other
loss weight, run one forward+backward on a small synthetic batch, and assert AT LEAST
ONE trainable parameter has a nonzero gradient. A head whose gradient never reaches
any trainable parameter fails LOUD here, in under a minute, instead of silently in a
1000-step overnight run.

Runs on the `tiny` backbone (no download) by default so it is cheap enough to be a
preflight — wired as `--check-grads` in both train.py and overfit_gate.py, and called
unconditionally at the top of modal_app.py's `_run_training` so a broken gradient path
is caught before any paid A100 time burns.

Usage:
  python foundation/test_grad_flow.py                    # tiny backbone, exits 1 on FAIL
  python foundation/test_grad_flow.py --backbone marigold-iid --cache-only
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DELIGHT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, DELIGHT)

import torch  # noqa: E402

from backbone import FoundationDelighter  # noqa: E402
from train import compute_losses  # noqa: E402

HEADS = ("T", "h", "B", "shadow", "mark", "conf")


def _synthetic_batch(device, size=64, seed=0):
    """Small, filesystem-independent batch — shapes/ranges only need to be plausible,
    not photoreal; this test is about gradient PLUMBING, not fidelity, so it never
    depends on a render root existing (works standalone in a fresh Modal container)."""
    g = torch.Generator().manual_seed(seed)

    def rnd(c):
        return torch.rand(1, c, size, size, generator=g).to(device)

    mark = (rnd(1) > 0.9).float()
    batch = {
        "photo": rnd(3), "T": rnd(3), "B": rnd(3),
        "h": rnd(1), "shadow": (rnd(1) > 0.5).float(), "mark": mark,
        "valid": 1.0 - mark,
    }
    batch["has_B"] = torch.tensor([1.0], device=device)
    return batch


def check_gradient_flow(backbone="tiny", device=None, lora_rank=4, verbose=True):
    """Returns {head: grad_norm}. Raises AssertionError naming any head whose gradient
    never reaches a trainable parameter."""
    device = device or ("mps" if torch.backends.mps.is_available() else
                        "cuda" if torch.cuda.is_available() else "cpu")
    model = FoundationDelighter(backbone=backbone, dtype=torch.float32, freeze_backbone=True,
                                lora_rank=lora_rank, cache_only=(backbone != "tiny")).to(device)
    tp = model.trainable_parameters()
    batch = _synthetic_batch(device)

    results = {}
    for head in HEADS:
        weights = {h: (1.0 if h == head else 0.0) for h in HEADS}
        model.zero_grad(set_to_none=True)
        out = model(batch["photo"])
        loss, _ = compute_losses(out, batch, weights)
        loss.backward()
        grad_norm = sum(float(p.grad.detach().abs().sum())
                        for p in tp if p.grad is not None)
        results[head] = grad_norm
        if verbose:
            status = "OK" if grad_norm > 0 else "*** ZERO GRADIENT ***"
            print(f"  [grad-flow] head={head:8s} grad_norm={grad_norm:.6g}  {status}")

    failed = [h for h, g in results.items() if not (g > 0)]
    if failed:
        raise AssertionError(
            f"gradient-flow check FAILED for head(s) {failed}: zero gradient reached "
            f"any trainable parameter. This is the report-040 decode()-no_grad bug "
            f"class — a frozen submodule's forward pass silently blocking gradient to "
            f"an UPSTREAM trainable path, not just its own weights. Audit every "
            f"`torch.no_grad()` / `.detach()` on the path from this head's output back "
            f"to the LoRA parameters before trusting any loss curve for it.")
    return results


def preflight_or_raise(backbone="tiny", device=None):
    """The one-line hook for train.py/overfit_gate.py's --check-grads and
    modal_app.py's cloud entrypoint. Prints a compact PASS/FAIL and re-raises on
    failure so the caller aborts before spending any real training time."""
    print(f"[grad-flow] preflight ({backbone} backbone, synthetic batch)...")
    results = check_gradient_flow(backbone=backbone, device=device)
    print(f"[grad-flow] PASS — all {len(results)} heads reach the trainable parameters")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backbone", default="tiny",
                    choices=["tiny", "marigold-iid", "marigold-depth", "sd2"])
    ap.add_argument("--device", default=None)
    args = ap.parse_args()
    try:
        preflight_or_raise(backbone=args.backbone, device=args.device)
    except AssertionError as e:
        print(f"[grad-flow] FAIL: {e}")
        sys.exit(1)
