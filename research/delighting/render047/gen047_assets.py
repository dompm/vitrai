"""047 asset authoring (run in Blender for scipy-backed authoring).

Authors each family's ground-truth maps with the VERBATIM trunk forward model
(gen045_module) and dumps them as exact float32 .npy:
    T (HxWx3 linear transmittance), h (HxW haze), height (HxW [0,1] relief),
    normal (HxWx3 tangent-space [0,1]).
These are the single source of truth consumed by BOTH the Cycles volumetric
truth (gen047_truth.py, reads .npy for full-precision volume absorption) and
the three.js model (prep047_maps.py converts them to the 8-bit PNG textures the
shipped material would actually use).

Run:
  <blender> -b --python gen047_assets.py -- --out <assets_dir> \
      --families cathedral-green:6001,wispy-white:6001,streaky-mix:6001 --size 1024
"""
import sys, os, argparse, json
sys.path.insert(0, os.path.expanduser('~/.local/lib/python3.11/site-packages'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'oracle45'))
import numpy as np
import gen045_module as G


def parse_args():
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    p.add_argument('--families', required=True, help='recipe:seed,recipe:seed')
    p.add_argument('--size', type=int, default=1024)
    return p.parse_args(argv)


def main():
    a = parse_args()
    G.GT_OPTS['no_marks'] = True
    os.makedirs(a.out, exist_ok=True)
    manifest = {}
    for spec in a.families.split(','):
        recipe, seed = spec.rsplit(':', 1); seed = int(seed)
        T, h, md, mw, mi, height, normal, bd = G.author_glass_arrays(recipe, size=a.size, seed=seed)
        d = os.path.join(a.out, recipe); os.makedirs(d, exist_ok=True)
        np.save(os.path.join(d, 'T.npy'), T.astype(np.float32))
        np.save(os.path.join(d, 'h.npy'), h.astype(np.float32))
        np.save(os.path.join(d, 'height.npy'), height.astype(np.float32))
        np.save(os.path.join(d, 'normal.npy'), normal.astype(np.float32))
        manifest[recipe] = {
            'seed': seed, 'size': a.size, 'bump_distance_m': float(bd),
            'T_mean': [round(float(x), 4) for x in T.mean(axis=(0, 1))],
            'T_min': round(float(T.min()), 4), 'T_max': round(float(T.max()), 4),
            'h_mean': round(float(h.mean()), 4), 'h_min': round(float(h.min()), 4), 'h_max': round(float(h.max()), 4),
            'coupling': G.COUPLING.get(recipe, 0.0) if hasattr(G, 'COUPLING') else None,
            'opal_scatter': recipe in G.OPAL_SCATTER_RECIPES,
        }
        print(f"AUTH {recipe} seed{seed}: T {T.min():.3f}-{T.max():.3f} h {h.min():.2f}-{h.max():.2f} bd {bd:.5f}")
    with open(os.path.join(a.out, 'families.json'), 'w') as f:
        json.dump(manifest, f, indent=2)
    print('MANIFEST', json.dumps(manifest))


if __name__ == '__main__':
    main()
