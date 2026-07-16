"""047 metrics + boards: three.js model vs Cycles volumetric truth.
8-bit sRGB MAE (0..255) + SSIM (luma), matching the 045/046 convention so the
numbers are directly comparable. Also emits amplified diff maps and side-by-side
board strips.  Pure numpy (no skimage)."""
import numpy as np, argparse, os, json
from PIL import Image
from scipy.ndimage import gaussian_filter

def load(p, size=None):
    im = Image.open(p).convert('RGB')
    if size and im.size != (size, size): im = im.resize((size, size), Image.LANCZOS)
    return np.asarray(im, np.float32)

def mae(a, b): return float(np.abs(a - b).mean())

def luma(x): return x @ np.array([0.299, 0.587, 0.114], np.float32)

def ssim(a, b):
    a, b = luma(a), luma(b)
    C1, C2 = (0.01*255)**2, (0.03*255)**2
    g = lambda x: gaussian_filter(x, 1.5, truncate=3.0)
    mu_a, mu_b = g(a), g(b)
    va, vb = g(a*a)-mu_a**2, g(b*b)-mu_b**2
    vab = g(a*b)-mu_a*mu_b
    s = ((2*mu_a*mu_b+C1)*(2*vab+C2))/((mu_a**2+mu_b**2+C1)*(va+vb+C2))
    return float(np.clip(s, -1, 1).mean())

def metrics(truth, model, size):
    t, m = load(truth, size), load(model, size)
    return {'mae': round(mae(t, m), 2), 'ssim': round(ssim(t, m), 4)}, t, m

def diff_img(t, m, amp=4.0):
    d = np.clip(np.abs(t - m).mean(2)*amp, 0, 255).astype(np.uint8)
    # magma-ish
    import numpy as _np
    r = _np.clip(d*1.4, 0, 255); g = _np.clip((d-60)*1.6, 0, 255); b = _np.clip(d*0.6, 0, 255)
    return _np.stack([r, g, b], -1).astype(_np.uint8)

def hcat(imgs, pad=6, bg=32):
    h = max(i.shape[0] for i in imgs)
    out = []
    for i in imgs:
        c = np.full((h, i.shape[1], 3), bg, np.uint8); c[:i.shape[0]] = i.astype(np.uint8)
        out.append(c); out.append(np.full((h, pad, 3), bg, np.uint8))
    return np.concatenate(out[:-1], 1)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--truth', required=True); ap.add_argument('--model', required=True)
    ap.add_argument('--size', type=int, default=512); ap.add_argument('--board')
    ap.add_argument('--diff'); a = ap.parse_args()
    mt, t, m = metrics(a.truth, a.model, a.size)
    print(json.dumps(mt))
    if a.diff: Image.fromarray(diff_img(t, m)).save(a.diff)
    if a.board: Image.fromarray(hcat([t, m, diff_img(t, m)])).save(a.board)
