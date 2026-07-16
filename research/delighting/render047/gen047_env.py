"""047 shared environment: a synthetic equirectangular HDR (.hdr / Radiance RGBE).

The SAME file is loaded as the world in Cycles and as the PMREM environment in
three.js, so the image-based lighting -- ambient fill, the front-hemisphere
sources whose reflections become the Fresnel "veil"/glints, and the coloured
sky/ground -- is byte-identical across the two renderers. HDR (values > 1) is
deliberate: the small bright "window" panels are what make crisp moving glints
on the glass under a camera orbit.

Radiance RGBE, uncompressed flat scanlines (RGBELoader reads this fine).
"""
import numpy as np, argparse, os

def write_hdr(path, rgb):
    """rgb: HxWx3 float32 (scene-linear). Writes uncompressed Radiance RGBE."""
    h, w, _ = rgb.shape
    rgb = np.maximum(rgb, 0.0).astype(np.float32)
    brightest = np.maximum.reduce(rgb, axis=2)
    e = np.zeros((h, w), np.int32)
    mant = np.zeros((h, w, 3), np.float32)
    nz = brightest > 1e-32
    m, ex = np.frexp(brightest[nz])          # brightest = m * 2**ex, m in [0.5,1)
    scale = (m * 256.0 / brightest[nz])
    mant[nz] = rgb[nz] * scale[:, None]
    e[nz] = ex + 128
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = np.clip(mant, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(e, 0, 255).astype(np.uint8)
    with open(path, 'wb') as f:
        f.write(b"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n")
        f.write(f"-Y {h} +X {w}\n".encode())
        f.write(out.tobytes())        # flat, one RGBE quad per pixel

def build_env(w=1024, h=512):
    yy, xx = np.mgrid[0:h, 0:w]
    theta = (yy + 0.5) / h * np.pi          # 0 top .. pi bottom (polar)
    phi = (xx + 0.5) / w * 2*np.pi - np.pi   # -pi..pi (azimuth)
    up = np.cos(theta)                       # +1 zenith .. -1 nadir
    env = np.zeros((h, w, 3), np.float32)
    # sky/ground gradient: cool sky, warm-neutral ground, moderate energy
    sky = np.array([0.42, 0.52, 0.70]); ground = np.array([0.30, 0.26, 0.22])
    t = (up*0.5+0.5)[..., None]
    env += t*sky + (1-t)*ground
    env *= 0.55
    # soft overhead key (broad, warm) -> ambient shaping
    key = np.exp(-((theta-0.55)**2)/(2*0.5**2)) * np.exp(-((phi-0.6)**2)/(2*0.9**2))
    env += key[..., None]*np.array([1.7,1.55,1.25])*1.3
    # crisp bright "window" panels -> the moving glints on the glass front face.
    def panel(pc, tc, ph, tw, val, col):
        d = np.exp(-((phi-pc)**2)/(2*ph**2) - ((theta-tc)**2)/(2*tw**2))
        d = (d > 0.5).astype(np.float32)*d     # squarer falloff
        return d[..., None]*np.array(col)*val
    env += panel(-1.1, 0.75, 0.16, 0.14, 9.0, [1.0,0.98,0.92])
    env += panel(0.15, 0.62, 0.10, 0.20, 14.0, [1.0,0.96,0.88])
    env += panel(1.7, 0.9, 0.13, 0.11, 6.0, [0.9,0.94,1.0])
    # a dim rim source behind (keeps back hemisphere non-black for orbit)
    env += panel(3.0, 0.85, 0.25, 0.3, 1.2, [0.8,0.85,1.0])
    return env

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    env = build_env()
    write_hdr(a.out, env)
    print(f"wrote {a.out}  range {env.min():.3f}..{env.max():.1f}  mean {env.mean():.3f}")
