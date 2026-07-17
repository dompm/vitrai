import os, sys, json
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2, numpy as np
sys.path.insert(0, "/Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/lead-054/research/delighting/oracle45")
import recon_bench_045 as rb

for name in ["cathedral-green__seed6001", "baroque-rolling-wave__seed6001"]:
    d = os.path.join(os.path.expanduser("~/Documents/vitrai-datasets/oracle45_data"), name)
    s = rb.load_sample(d)
    truth = s["struct_truth"]
    # best t1 recon (sigma 256 from the sweep)
    rec = rb.reconstruct(s, "struct", 256.0, 0.0, False)
    eps = 1e-4
    ratio = (truth.mean(axis=-1) + eps) / (rec.mean(axis=-1) + eps)   # multiplicative residual
    logr = np.log(np.clip(ratio, 0.05, 20.0))
    # candidate explanatory fields, all derivable from gt maps:
    gy, gx = np.gradient(s["height"])
    slope = np.sqrt(gx**2 + gy**2)                    # |grad h| full band
    lap = cv2.Laplacian(cv2.GaussianBlur(s["height"], (0,0), 4), cv2.CV_32F)  # curvature
    def cc(a, b):
        a = (a - a.mean()) / (a.std() + 1e-9); b = (b - b.mean()) / (b.std() + 1e-9)
        return float((a * b).mean())
    print(f"{name}: log-ratio std={logr.std():.4f}")
    print(f"  corr(logR, |grad h| fullband) = {cc(logr, slope):+.3f}")
    print(f"  corr(logR, grad_x)            = {cc(logr, gx):+.3f}")
    print(f"  corr(logR, grad_y)            = {cc(logr, gy):+.3f}")
    print(f"  corr(logR, curvature)         = {cc(logr, lap):+.3f}")
    print(f"  corr(logR, height)            = {cc(logr, s['height']):+.3f}")
    # save visual: truth | recon | logR normalized | slope
    v = lambda a: np.clip((a - a.min()) / (a.max() - a.min() + 1e-9), 0, 1)
    strip = np.concatenate([rb.lin_to_srgb(np.clip(truth,0,None)),
                            rb.lin_to_srgb(np.clip(rec,0,None)),
                            np.repeat(v(logr)[...,None],3,-1),
                            np.repeat(v(slope)[...,None],3,-1)], axis=1)
    small = cv2.resize(strip, (0,0), fx=0.3, fy=0.3, interpolation=cv2.INTER_AREA)
    cv2.imwrite(f"/tmp/diag054_{name.split('__')[0]}.jpg", (np.clip(small,0,1)*255).astype(np.uint8)[...,::-1])
print("panels in /tmp")
