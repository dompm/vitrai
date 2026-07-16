"""047: convert exact .npy maps -> the 8-bit PNG textures the three.js material
loads (exactly what the shipped app would ship), and generate the shared
backdrop image (the 'scene behind the window') used, identically, by both the
Cycles truth and the three.js model.

Encodings chosen to match a real deployment / three.js colour management:
  tint.png    sRGB 8-bit RGB   = gt_T (loaded SRGBColorSpace -> three linearises
                                 back to the linear transmittance). This is the
                                 per-pixel colour the material multiplies the
                                 transmitted light by (attenuationColor in three
                                 is a single constant, so per-pixel T rides the
                                 base-colour `map`).
  haze.png    linear 8-bit L   = h  (roughness map; NoColorSpace)
  normal.png  linear 8-bit RGB = tangent-space normal (NoColorSpace)
Run: <venv>/python prep047_maps.py --assets <assets_dir>
"""
import numpy as np, argparse, os
from PIL import Image

def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x*12.92, 1.055*np.power(x, 1/2.4)-0.055)

def save_rgb8(path, arr):   # arr already in [0,1] display-encoded
    Image.fromarray((np.clip(arr,0,1)*255+0.5).astype(np.uint8), 'RGB').save(path)

def save_l8(path, arr):
    Image.fromarray((np.clip(arr,0,1)*255+0.5).astype(np.uint8), 'L').save(path)

def make_backdrop(size=1024):
    """The 'scene behind the glass': a structured outdoor-ish backdrop with
    SOFT edges. Structure (gradients, a soft horizon glow, low-frequency
    'mullions', a large soft check, a soft sun) is what lets refraction/scatter/
    parallax read under an orbit; the softness keeps a cross-renderer MAE
    reporting MATERIAL differences rather than sub-pixel checker-phase
    misalignment (a razor checker explodes MAE under any fractional offset
    between two independent rasterisers). scene-linear [0, ~2]."""
    from scipy.ndimage import gaussian_filter
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)/size
    sky = np.array([0.50,0.66,0.98]); grnd = np.array([0.86,0.78,0.58])
    horizon = 0.55
    t = np.clip((yy)/horizon,0,1)[...,None]
    img = t*grnd + (1-t)*sky
    below = yy>horizon
    img[below] = grnd*(1.0-0.35*((yy[below]-horizon)/(1-horizon)))[...,None]
    # soft horizon glow
    img += np.exp(-((yy-horizon)**2)/(2*0.04**2))[...,None]*np.array([0.5,0.48,0.4])
    # large soft check (low freq => legible refraction, no razor edges)
    ck = 0.5+0.5*np.sin(xx*2*np.pi*5)*np.sin(yy*2*np.pi*5)
    band = np.clip(1-np.abs(yy-0.5)/0.28,0,1)
    img += (band*(ck-0.5))[...,None]*np.array([0.6,0.58,0.5])
    # low-frequency 'mullions' (soft-edged verticals)
    for cx in (0.30,0.70):
        img -= (np.exp(-((xx-cx)**2)/(2*0.02**2)))[...,None]*np.array([0.5,0.5,0.5])
    # soft sun (glint source through the glass)
    sun = np.exp(-(((xx-0.60)**2+(yy-0.22)**2)/(2*0.05**2)))
    img += sun[...,None]*np.array([1.4,1.3,1.0])
    img = np.clip(img,0,4)
    img = gaussian_filter(img, sigma=(size/256, size/256, 0))  # soften every edge
    return np.clip(img,0,4)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--assets', required=True)
    a = ap.parse_args()
    fams = [d for d in os.listdir(a.assets) if os.path.isdir(os.path.join(a.assets,d))]
    for fam in fams:
        d = os.path.join(a.assets, fam)
        T = np.load(os.path.join(d,'T.npy')); h = np.load(os.path.join(d,'h.npy'))
        nrm = np.load(os.path.join(d,'normal.npy'))
        save_rgb8(os.path.join(d,'tint.png'), srgb_encode(T))   # sRGB-coded linear T
        save_l8(os.path.join(d,'haze.png'), h)                  # linear roughness
        save_rgb8(os.path.join(d,'normal.png'), nrm)            # linear tangent normal
        print(f"{fam}: tint/haze/normal.png  T{T.shape} h[{h.min():.2f},{h.max():.2f}]")
    bd = make_backdrop(1024)
    # linear .npy (Cycles emissive) + sRGB png (three basic map)
    np.save(os.path.join(a.assets,'backdrop.npy'), bd.astype(np.float32))
    save_rgb8(os.path.join(a.assets,'backdrop.png'), srgb_encode(bd/bd.max()))
    # also store the max scale so Cycles can restore linear magnitude
    with open(os.path.join(a.assets,'backdrop_scale.txt'),'w') as f: f.write(str(float(bd.max())))
    print(f"backdrop: range 0..{bd.max():.2f}")

if __name__=='__main__': main()
