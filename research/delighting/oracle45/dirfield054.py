import os, sys
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2, numpy as np
sys.path.insert(0, "/Users/dominiquepiche-meunier/Documents/vitraux/.claude/worktrees/lead-054/research/delighting/oracle45")
import recon_bench_045 as rb

name = "cathedral-green__seed6001"
d = os.path.join(os.path.expanduser("~/Documents/vitrai-datasets/oracle45_data"), name)
s = rb.load_sample(d)
truth, rec, B = s["struct_truth"], rb.reconstruct(s, "struct", 256.0, 0.0, False), s["struct_B"]
eps = 1e-4
logr = np.log(np.clip((truth.mean(-1)+eps)/(rec.mean(-1)+eps), 0.05, 20.0))
gy, gx = np.gradient(s["height"])
H, W = logr.shape; ts = 64
canvas = (np.clip(rb.lin_to_srgb(np.clip(B,0,None)),0,1)*160).astype(np.uint8).copy()
for y in range(0, H-ts, ts):
    for x in range(0, W-ts, ts):
        r = logr[y:y+ts, x:x+ts].ravel(); r = r - r.mean()
        a = gx[y:y+ts, x:x+ts].ravel(); a = a - a.mean()
        b = gy[y:y+ts, x:x+ts].ravel(); b = b - b.mean()
        G = np.stack([a, b], 1)
        beta, *_ = np.linalg.lstsq(G, r, rcond=None)
        pred = G @ beta
        cc = float(np.corrcoef(pred, r)[0, 1]) if pred.std() > 1e-9 else 0.0
        n = np.hypot(*beta) + 1e-12
        ux, uy = beta[0]/n, beta[1]/n
        c = (int(255*min(cc,1)), 60, int(255*(1-min(cc,1))))
        cx, cy = x+ts//2, y+ts//2
        cv2.arrowedLine(canvas, (cx, cy), (int(cx+ux*24), int(cy+uy*24)), c, 2, tipLength=0.35)
small = cv2.resize(canvas, (0,0), fx=0.6, fy=0.6)
cv2.imwrite("/tmp/dirfield_cathedral.jpg", small[...,::-1])
print("saved /tmp/dirfield_cathedral.jpg  (arrows=fitted shading direction, red=strong corr, blue=weak; underlay=backdrop B)")
