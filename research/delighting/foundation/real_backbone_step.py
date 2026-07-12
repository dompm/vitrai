#!/usr/bin/env python3
"""Iteration 038 deliverable-1 proof: a full FoundationDelighter train STEP (forward +
backward, LoRA + AuxHead) through the REAL Marigold backbone runs on the M4 (MPS),
cache-only (no re-download). Run from research/delighting/:
    python foundation/real_backbone_step.py
Writes results/038_backbone/real_backbone_step.json."""
import os, sys, time, json, torch
sys.path.insert(0, "foundation")
from backbone import FoundationDelighter
dev = "mps" if torch.backends.mps.is_available() else "cpu"
t0=time.time()
# marigold-depth: smaller in/out (8/4); cache_only => no re-download
m = FoundationDelighter(backbone="marigold-depth", freeze_backbone=True, lora_rank=8,
                        cache_only=True, dtype=torch.float32).to(dev)
load=time.time()-t0
ntr=sum(p.numel() for p in m.trainable_parameters())
x=torch.rand(1,3,256,256,device=dev)
t1=time.time()
out=m(x)              # single-step forward through the REAL 866M UNet + LoRA + VAE decode
fwd=time.time()-t1
t2=time.time()
loss=out["T"].mean()+out["h"].mean()+out["shadow"].mean()
loss.backward()       # prove LoRA+head grads flow through the real backbone
bwd=time.time()-t2
g=sum(p.grad is not None for p in m.trainable_parameters())
rec={"backbone":"marigold-depth","device":dev,"lora_ok":m.lora_ok,
     "trainable_params":int(ntr),"unet_in":m.unet_in,"unet_out":m.unet_out,
     "load_s":round(load,1),"forward_s":round(fwd,1),"backward_s":round(bwd,1),
     "grad_tensors":f"{g}/{len(m.trainable_parameters())}",
     "T_shape":list(out["T"].shape)}
os.makedirs("results/038_backbone",exist_ok=True)
json.dump(rec,open("results/038_backbone/real_backbone_step.json","w"),indent=2)
print("REAL-BACKBONE STEP OK:",json.dumps(rec))
