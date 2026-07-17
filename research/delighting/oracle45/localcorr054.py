import os, sys
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2, numpy as np
sys.path.insert(0, "/Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/lead-054/research/delighting/oracle45")
import recon_bench_045 as rb

for name in ["cathedral-green__seed6001", "baroque-rolling-wave__seed6001", "streaky-mix__seed6001"]:
    d = os.path.join(os.path.expanduser("~/Documents/vitrai-datasets/oracle45_data"), name)
    s = rb.load_sample(d)
    truth, rec = s["struct_truth"], rb.reconstruct(s, "struct", 256.0, 0.0, False)
    eps = 1e-4
    logr = np.log(np.clip((truth.mean(-1)+eps)/(rec.mean(-1)+eps), 0.05, 20.0))
    gy, gx = np.gradient(s["height"])
    H, W = logr.shape; ts = 64
    ccs, ccs_best = [], []
    for y in range(0, H-ts, ts):
        for x in range(0, W-ts, ts):
            r = logr[y:y+ts, x:x+ts].ravel()
            if r.std() < 1e-4: continue
            r = (r - r.mean()) / r.std()
            best = 0.0
            for g in (gx[y:y+ts, x:x+ts].ravel(), gy[y:y+ts, x:x+ts].ravel()):
                if g.std() < 1e-9: continue
                g = (g - g.mean()) / g.std()
                c = float((r*g).mean())
                best = max(best, abs(c))
                ccs.append(c)
            ccs_best.append(best)
    # best linear combo per tile ~ max over the two axes (lower bound on true dir fit)
    print(f"{name}: tiles={len(ccs_best)}  mean|per-tile best-axis corr|={np.mean(ccs_best):.3f}  p90={np.quantile(ccs_best,0.9):.3f}")
