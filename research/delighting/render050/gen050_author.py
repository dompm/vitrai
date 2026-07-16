"""050 asset authoring (run in Blender). Like gen047_assets but writes one
directory PER (recipe, seed) -> keeps a multi-seed holdout set (gen047_assets
keyed dirs by recipe name only, so seeds overwrote each other).

Each dir '<recipe>__<seed>' gets T/h/height/normal.npy (verbatim trunk forward
model, gen045_module) + a per-dir entry in families.json carrying the recipe,
seed, bump_distance and the relief CATEGORY (the synthetic ground truth for
detection scoring).

Run: <blender> -b --python gen050_author.py -- --out <dir> --specs \
     cathedral-green:6001:hammered,dark-opaque:7001:granite,... --size 768
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
    p.add_argument('--specs', required=True, help='recipe:seed:category,...')
    p.add_argument('--size', type=int, default=768)
    return p.parse_args(argv)


def main():
    a = parse_args()
    G.GT_OPTS['no_marks'] = True
    os.makedirs(a.out, exist_ok=True)
    mpath = os.path.join(a.out, 'families.json')
    manifest = json.load(open(mpath)) if os.path.exists(mpath) else {}
    for spec in a.specs.split(','):
        recipe, seed, cat = spec.split(':')
        seed = int(seed)
        key = f'{recipe}__{seed}'
        T, h, md, mw, mi, height, normal, bd = G.author_glass_arrays(recipe, size=a.size, seed=seed)
        d = os.path.join(a.out, key); os.makedirs(d, exist_ok=True)
        np.save(os.path.join(d, 'T.npy'), T.astype(np.float32))
        np.save(os.path.join(d, 'h.npy'), h.astype(np.float32))
        np.save(os.path.join(d, 'height.npy'), height.astype(np.float32))
        np.save(os.path.join(d, 'normal.npy'), normal.astype(np.float32))
        manifest[key] = {
            'recipe': recipe, 'seed': seed, 'category': cat, 'size': a.size,
            'bump_distance_m': float(bd),
            'T_mean': [round(float(x), 4) for x in T.mean(axis=(0, 1))],
            'h_mean': round(float(h.mean()), 4),
            'opal_scatter': recipe in G.OPAL_SCATTER_RECIPES,
        }
        print(f"AUTH {key} [{cat}]: bd {bd:.5f} h_mean {h.mean():.2f}")
    with open(mpath, 'w') as f:
        json.dump(manifest, f, indent=2)
    print('WROTE', mpath, len(manifest), 'entries')


if __name__ == '__main__':
    main()
