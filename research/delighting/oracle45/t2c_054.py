import os, sys, json
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2, numpy as np
sys.path.insert(0, "/Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/lead-054/research/delighting/oracle45")
import recon_bench_045 as rb

ALPHAS = [0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, -1.0, -2.0, -4.0, -8.0]
SM = rb.SIGMA_MAX_GRID + [384.0, 512.0]
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
    meanB = B.reshape(-1, 3).mean(axis=0)
    levels = rb.SIGMA_LEVELS + [384.0, 512.0]
    stack = rb.blur_stack(B, levels)
    best = None
    for sm in SM:
        Bb = rb.variable_blur(stack, levels, sm * h) if sm > 0 else B
        for al in ALPHAS:
            if al == 0.0:
                Bw = Bb
            else:
                mx, my = rb.lens_warp_maps(s, al)   # FULL-BAND gradient, warp AFTER blur
                Bw = cv2.remap(Bb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            L = T * (h[..., None] * meanB[None, None] + (1.0 - h[..., None]) * Bw)
            m = score(L, truth)
            if best is None or m < best[0]:
                best = (m, sm, al, L)
    m, sm, al, L = best
    out.append({"sample": name, "t2c_mae": round(m, 2), "sigma_max": sm, "alpha": al})
    print(out[-1])
    Ls = rb.lin_to_srgb(np.clip(L, 0, None)); Ts = rb.lin_to_srgb(np.clip(truth, 0, None))
    strip = np.concatenate([Ts, Ls, np.clip(np.abs(Ls - Ts) * 5, 0, 1)], axis=1)
    small = cv2.resize(strip, (0, 0), fx=0.3, fy=0.3, interpolation=cv2.INTER_AREA)
    cv2.imwrite(f"/tmp/t2c_{name.split('__')[0]}.jpg", (np.clip(small, 0, 1) * 255).astype(np.uint8)[..., ::-1])
json.dump(out, open("/tmp/t2c_results.json", "w"), indent=1)
