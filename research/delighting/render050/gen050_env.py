"""050 environment: a SOFTER, less directional IBL than 047's orbit-demo env.

047's env has three sharp bright 'window' panels -- perfect for sliding glints
in the orbit demo, but they cast strong DIAGONAL streaks across the sheet that
mask isotropic pebble relief as directional (a detection confound). A photo a
user takes of their sheet is typically diffuse-lit (light table / soft window /
overcast). This env keeps a gentle overhead soft-box (so relief still glints)
but is dominated by diffuse hemispheric fill, so isotropic textures read as
isotropic and directional textures (streaky) still read as directional.
"""
import numpy as np, argparse, os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'render047'))
from gen047_env import write_hdr


def build_env(w=1024, h=512):
    yy, xx = np.mgrid[0:h, 0:w]
    theta = (yy + 0.5) / h * np.pi
    phi = (xx + 0.5) / w * 2 * np.pi - np.pi
    up = np.cos(theta)
    env = np.zeros((h, w, 3), np.float32)
    sky = np.array([0.60, 0.66, 0.74]); ground = np.array([0.52, 0.50, 0.48])
    t = (up * 0.5 + 0.5)[..., None]
    env += t * sky + (1 - t) * ground
    env *= 0.9                                  # bright diffuse fill
    # one broad, soft overhead key (large sigma -> no sharp streak), gentle
    key = np.exp(-((theta - 0.5) ** 2) / (2 * 0.6 ** 2))
    env += key[..., None] * np.array([1.0, 0.99, 0.95]) * 1.1
    # a single soft, wide bright panel high up (soft-box) -> gentle isotropic glint
    d = np.exp(-((phi - 0.1) ** 2) / (2 * 0.5 ** 2) - ((theta - 0.5) ** 2) / (2 * 0.4 ** 2))
    env += d[..., None] * np.array([1.0, 0.98, 0.94]) * 2.2
    return env


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    env = build_env()
    write_hdr(a.out, env)
    print(f"wrote {a.out} range {env.min():.3f}..{env.max():.1f} mean {env.mean():.3f}")
