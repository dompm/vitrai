import os, sys, json
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2, numpy as np
sys.path.insert(0, "/Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/lead-054/research/delighting/oracle45")
import recon_bench_045 as rb

GAMMAS = [0.0, 0.05, 0.1, 0.2, 0.4, 0.8, -0.05, -0.1, -0.2, -0.4, -0.8]
BIGS = [8.0, 16.0, 32.0]
SAMPLES = ["cathedral-green__seed6001", "cathedral-amber__seed6002",
           "baroque-rolling-wave__seed6001", "confetti-shard__seed6002",
           "fracture-streamer__seed6003", "streaky-mix__seed6001"]

def score(L, truth):
    Ls = rb.lin_to_srgb(np.clip(L, 0, None)); Ts = rb.lin_to_srgb(np.clip(truth, 0, None))
    return float(np.abs(Ls - Ts).mean() * 255.0)

out = []
for name in SAMPLES:
    d = os.path.join(os.path.expanduser("~/Documents/vitrai-datasets/oracle45_data"), name)
    s = rb.load_sample(d)
    T, h, truth, B = s["T"], s["h"], s["struct_truth"], s["struct_B"]
    gy, gx = np.gradient(s["height"])
    baseL = rb.reconstruct(s, "struct", 256.0, 0.0, False)
    base_mae = score(baseL, truth)
    best = None
    for bs in BIGS:
        Blum = cv2.GaussianBlur(B.mean(-1), (0, 0), bs)
        by, bx = np.gradient(Blum)
        mag = np.sqrt(bx**2 + by**2) + 1e-12
        dx, dy = bx / mag, by / mag                     # unit light-direction field
        inter = gx * dx + gy * dy                        # slope along light dir
        inter = inter / (inter.std() + 1e-12)            # unit-std shading basis
        for gm in GAMMAS:
            mod = np.clip(1.0 + gm * inter, 0.0, 4.0)[..., None]
            m = score(baseL * mod, truth)
            if best is None or m < best[0]:
                best = (m, bs, gm)
    m, bs, gm = best
    out.append({"sample": name, "t1": round(base_mae, 2), "t3s2": round(m, 2),
                "big": bs, "gamma": gm})
    print(out[-1])
json.dump(out, open("/tmp/t3s2_results.json", "w"), indent=1)
