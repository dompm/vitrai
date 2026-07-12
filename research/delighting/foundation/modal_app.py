#!/usr/bin/env python3
"""Iteration 038 / deliverable 3 (cloud) — Modal app for the real Bet-2 fine-tune.

The SAME train_loop from train.py, wrapped as a Modal @app.function(gpu="A100-80GB")
with a Volume for the synthetic corpus + checkpoints and an HF-Hub push of the trained
adapter. Designed per COMPUTE_OPTIONS.md §5 (Modal day-one runbook): --detach-ready,
Volume-backed, Secret-scoped HF token, resumable.

IMPORTANT (report-brief requirement): this file must IMPORT-CHECK on the M4 WITHOUT a
Modal account. `modal` is imported lazily behind a guard; if it is absent we install a
no-op decorator stub so `python -c "import modal_app"` and a `--selfcheck` succeed and
the deploy path is simply unavailable. Nothing here runs cloud compute at import time.

Real run (maintainer has done the COMPUTE_OPTIONS §5 account/token/secret steps):
  modal volume create vitraux-delight
  modal volume put vitraux-delight <local render_037>/ /render_037
  modal run --detach foundation/modal_app.py::train        # fire-and-forget
  modal app logs <app-id>                                  # monitor from any session
See docs/FOUNDATION_RUNBOOK.md for the full sequence + cost.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------- modal guard
try:
    import modal
    HAVE_MODAL = True
except Exception:  # no modal installed / no account — import must still succeed
    HAVE_MODAL = False

    class _Stub:
        """Just enough of the modal surface for this module to import + define the
        app without a Modal account. The decorators become identity functions."""
        def __init__(self, *a, **k):
            pass

        def function(self, *a, **k):
            def deco(fn):
                return fn
            return deco

        def local_entrypoint(self):
            def deco(fn):
                return fn
            return deco

        @staticmethod
        def from_name(*a, **k):
            return None

        def pip_install(self, *a, **k):
            return self

        def apt_install(self, *a, **k):
            return self

    class modal:  # type: ignore  # noqa: N801  (shadow the missing package)
        App = _Stub
        Image = _Stub()
        Volume = _Stub
        Secret = _Stub

        @staticmethod
        def enter():  # unused stub hook
            return None


# --------------------------------------------------------------- app definition
# The container image mirrors the M4 deps (torch/diffusers/peft/OpenEXR) + the CUDA
# torch wheel; on the M4 (stub path) this is inert metadata, never built.
if HAVE_MODAL:
    image = (
        modal.Image.debian_slim(python_version="3.10")
        .apt_install("libgl1", "libglib2.0-0")
        .pip_install(
            "torch", "diffusers>=0.39", "transformers>=4.40", "peft>=0.19",
            "safetensors", "huggingface_hub>=0.23", "OpenEXR", "opencv-python-headless",
            "numpy", "scipy", "Pillow",
        )
        .add_local_dir(os.path.dirname(HERE), "/root/delighting")  # ship the repo code
    )
    app = modal.App("vitraux-foundation-038", image=image)
    DATA_VOL = modal.Volume.from_name("vitraux-delight", create_if_missing=True)
    CKPT_VOL = modal.Volume.from_name("vitraux-delight-ckpt", create_if_missing=True)
else:
    image = None
    app = modal.App("vitraux-foundation-038")
    DATA_VOL = None
    CKPT_VOL = None


def _run_training(data_glob, out_dir, backbone, steps, bs, crop, lr, lora_rank,
                  hf_repo=None):
    """The body — identical on cloud and (for a dry selfcheck) locally. Imports the
    repo's train_loop so there is ONE training implementation, not a fork."""
    import glob
    sys.path.insert(0, "/root/delighting/foundation")
    sys.path.insert(0, os.path.join(HERE))
    from train import train_loop  # the shared loop

    roots = sorted(glob.glob(data_glob))
    print(f"[modal] data roots: {roots}")
    model, log = train_loop(roots, out_dir, backbone=backbone, steps=steps, bs=bs,
                            crop=crop, lr=lr, lora_rank=lora_rank, fp32=False,
                            save_every=max(1, steps // 10))
    ckpt = os.path.join(out_dir, "adapter.pt")
    if hf_repo:
        _push_to_hub(ckpt, hf_repo)
    return {"ckpt": ckpt, "final_loss": log[-1]["total"] if log else None}


def _push_to_hub(ckpt, repo_id):
    """Push the compact adapter (LoRA+AuxHead) as the artifact of record so a later
    agent with no memory of the run can pull it (COMPUTE_OPTIONS §5 step 5)."""
    try:
        from huggingface_hub import HfApi
        api = HfApi(token=os.environ.get("HF_TOKEN"))
        api.create_repo(repo_id, private=True, exist_ok=True)
        api.upload_file(path_or_fileobj=ckpt, path_in_repo="adapter.pt", repo_id=repo_id)
        print(f"[modal] pushed adapter -> hf.co/{repo_id}")
    except Exception as e:
        print(f"[modal] HF push failed ({e}); adapter remains on the checkpoint Volume")


if HAVE_MODAL:
    @app.function(gpu="A100-80GB", timeout=86400, volumes={"/data": DATA_VOL, "/ckpt": CKPT_VOL},
                  secrets=[modal.Secret.from_name("huggingface")])
    def train(backbone="marigold-iid", steps=30000, bs=16, crop=512, lr=1e-4,
              lora_rank=16, data_glob="/data/render_*", hf_repo="vitraux/delight-foundation-038"):
        r = _run_training(data_glob, "/ckpt/run038", backbone, steps, bs, crop, lr,
                          lora_rank, hf_repo=hf_repo)
        CKPT_VOL.commit()
        return r

    @app.local_entrypoint()
    def main(steps: int = 30000, backbone: str = "marigold-iid"):
        print(train.remote(backbone=backbone, steps=steps))


def selfcheck():
    """Import-time + structural check runnable on the M4 with no Modal account."""
    print(f"modal_app import OK | HAVE_MODAL={HAVE_MODAL} | app={getattr(app, 'name', '?') if HAVE_MODAL else 'stub'}")
    print("train_loop is shared with train.py (no forked training code):",
          os.path.exists(os.path.join(HERE, "train.py")))
    print("guarded deploy path:", "AVAILABLE" if HAVE_MODAL else "unavailable (no modal) — import still succeeds")
    return True


if __name__ == "__main__":
    if "--selfcheck" in sys.argv or not HAVE_MODAL:
        selfcheck()
    else:
        print("Use `modal run --detach foundation/modal_app.py::train` to launch on cloud.")
        print("Run with --selfcheck for the no-account import check.")
