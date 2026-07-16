"""050 synthetic 'user photo' renderer: a front-lit displaced glass slab under
the shared IBL environment, filling the frame like a photo of a sheet. This is
the RELIEF-SHOWING render (report 047: relief reads as front-surface glints /
shading under front light, invisible in the 045/046 backlit rig) -- the right
synthetic photo for validating relief auto-detection.

Reuses gen047_truth's volumetric-slab construction (real 3 mm slab displaced by
gt_height, Beer-Lambert volume absorption from gt_T, roughness from gt_h) but:
  - one camera angle (a slight tilt so relief glints rake),
  - the slab fills the frame (no orbit),
  - optional --flatten zeroes the displacement -> a 'smooth' category sample.

Run: <blender> -b --python gen050_photos.py -- --assets <dir> \
     --keys cathedral-green__6001,... --res 448 --spp 48 --out <dir>
"""
import sys, os, argparse, json, math
sys.path.insert(0, os.path.expanduser('~/.local/lib/python3.11/site-packages'))
import numpy as np, bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'render047'))
import gen047_truth as GT  # reuse slab/material/env builders


def make_soft_backdrop():
    """A soft, near-uniform luminous field behind the sheet (like a light table
    / softbox / bright wall) -- NO mullions/checker/sun. This isolates the
    glass's OWN surface relief as the dominant structure in the photo (a real
    sheet photo, not the 047 window-refraction scene), which is what detection
    reads. Faint large-scale gradient only, so relief still produces glints and
    gentle lensing distortion."""
    n = 512
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) / n
    base = 1.15 - 0.25 * yy                      # gentle top->bottom falloff
    glow = np.exp(-(((xx - 0.4) ** 2 + (yy - 0.35) ** 2) / (2 * 0.32 ** 2)))
    val = base + 0.35 * glow                     # one very soft bright region
    warm = np.stack([val * 1.0, val * 0.99, val * 0.96], -1)
    bpy.ops.mesh.primitive_plane_add(size=1.9, location=(0, 0, -0.5))
    ob = bpy.context.active_object; ob.name = 'SoftBackdrop'
    mat = bpy.data.materials.new('SBD'); mat.use_nodes = True
    nd = mat.node_tree.nodes; lk = mat.node_tree.links; nd.clear()
    out = nd.new('ShaderNodeOutputMaterial'); em = nd.new('ShaderNodeEmission')
    tex = nd.new('ShaderNodeTexImage')
    img = GT.img_from_np('softbd', warm.astype(np.float32), 'Non-Color')
    tex.image = img
    em.inputs['Strength'].default_value = 1.0
    lk.new(tex.outputs['Color'], em.inputs['Color'])
    lk.new(em.outputs['Emission'], out.inputs['Surface'])
    ob.data.materials.append(mat)
    return ob


def parse():
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument('--assets', required=True)
    p.add_argument('--keys', required=True, help='asset dir keys, comma-sep')
    p.add_argument('--res', type=int, default=448)
    p.add_argument('--spp', type=int, default=48)
    p.add_argument('--az', type=float, default=12.0)
    p.add_argument('--elev', type=float, default=10.0)
    p.add_argument('--fov', type=float, default=30.0)
    p.add_argument('--dist', type=float, default=0.82)
    p.add_argument('--flatten', action='store_true',
                   help="zero displacement -> a 'smooth' sample")
    p.add_argument('--soft', action='store_true',
                   help="soft uniform luminous backdrop (isolate relief)")
    p.add_argument('--env', default='env.hdr', help="env hdr filename in assets")
    p.add_argument('--suffix', default='')
    p.add_argument('--out', required=True)
    return p.parse_args(argv)


def render_one(assets, key, a, outdir):
    d = os.path.join(assets, key)
    T = np.load(os.path.join(d, 'T.npy'))
    h = np.load(os.path.join(d, 'h.npy'))
    height = np.load(os.path.join(d, 'height.npy'))
    manifest = json.load(open(os.path.join(assets, 'families.json')))
    disp_amp = 0.0 if a.flatten else manifest[key]['bump_distance_m']

    GT.clear()
    GT.setup_render(a.res, a.spp)
    GT.world_env(os.path.join(assets, a.env))
    mat = GT.glass_material(T, h)
    ob = GT.make_slab(height, disp_amp, mat)
    bd = make_soft_backdrop() if a.soft else GT.make_backdrop(assets, a.res)
    GT.group_rotate([ob, bd], a.az, a.elev)
    GT.fixed_cam(a.dist, a.fov)
    name = f'photo_{key}{a.suffix}.png'
    GT.render_to(os.path.join(outdir, name))
    print('RENDERED', name, 'disp', disp_amp)


def main():
    a = parse()
    outdir = os.path.join(a.out)
    os.makedirs(outdir, exist_ok=True)
    for key in a.keys.split(','):
        render_one(a.assets, key, a, outdir)
    print('DONE', a.keys)


if __name__ == '__main__':
    main()
