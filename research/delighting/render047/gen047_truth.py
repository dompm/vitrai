"""047 Cycles volumetric TRUTH: a REAL 3 mm glass slab (not a thin surface BSDF).

Geometry: a 512-grid plane displaced by gt_height (real relief), then Solidify
3 mm -> a solid slab whose front face carries the relief that genuinely refracts.
Material: clear dielectric surfaces (Principled, IOR 1.5, Transmission 1,
Roughness = gt_h) + a Volume Absorption whose per-pixel Color is calibrated so
the HEAD-ON transmittance through the nominal 3 mm equals gt_T exactly
(Beer-Lambert sigma_a = (1-Color)*Density; T = exp(-sigma_a*d0)).
Lighting: the shared env.hdr as the world (front-hemisphere sources -> the
Fresnel veil / moving glints), plus an emissive textured backdrop (the scene
behind the glass) for the window case. Camera orbits the glass (window-nudge).

Two scenes:
  flat  -- the window-nudge: slab + backdrop + env, camera azimuth in --angles.
  lamp  -- a curved glass shell (cylinder, 3 mm wall) with an INTERIOR emitter,
           viewed from outside; env dim.

Run:
  <blender> -b --python gen047_truth.py -- --assets <dir> --family cathedral-green \
      --scene flat --angles 0,10,15,30 --res 640 --out <renderdir>
"""
import sys, os, argparse, json, math
sys.path.insert(0, os.path.expanduser('~/.local/lib/python3.11/site-packages'))
import numpy as np, bpy
from mathutils import Vector

D0 = 2000.0          # volume density (1/m); D0*d0 = 6 head-room for T down to ~0.0025
D_SLAB = 0.003       # nominal slab thickness (m)
GLASS = 0.5          # glass extent (m)

def img_from_np(name, arr, colorspace='Non-Color', float_buf=True):
    """Create a bpy image from HxWx{1,3} float array (values used as data)."""
    h, w = arr.shape[:2]
    if arr.ndim == 2: arr = np.repeat(arr[..., None], 3, 2)
    rgba = np.ones((h, w, 4), np.float32); rgba[..., :3] = arr
    img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=float_buf)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(np.flipud(rgba).reshape(-1))  # blender origin bottom-left
    img.pack()
    return img

def setup_render(res, spp=64):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    pr = bpy.context.preferences.addons['cycles'].preferences
    pr.compute_device_type = 'METAL'; pr.get_devices()
    for d in pr.devices: d.use = True
    sc.cycles.device = 'GPU' if pr.has_active_device() else 'CPU'
    sc.cycles.samples = spp; sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 32; sc.cycles.transmission_bounces = 32
    sc.cycles.transparent_max_bounces = 32; sc.cycles.volume_bounces = 8
    sc.view_settings.view_transform = 'Standard'
    sc.render.resolution_x = res; sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False

def world_env(hdr_path, strength=1.0):
    sc = bpy.context.scene
    w = bpy.data.worlds.new('W'); sc.world = w; w.use_nodes = True
    n = w.node_tree.nodes; l = w.node_tree.links; n.clear()
    out = n.new('ShaderNodeOutputWorld'); bg = n.new('ShaderNodeBackground')
    tex = n.new('ShaderNodeTexEnvironment')
    img = bpy.data.images.load(hdr_path); img.colorspace_settings.name = 'Linear Rec.709'
    tex.image = img
    bg.inputs['Strength'].default_value = strength
    l.new(tex.outputs['Color'], bg.inputs['Color']); l.new(bg.outputs['Background'], out.inputs['Surface'])

def glass_material(T, h, name='GlassVol'):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    nt = mat.node_tree; n = nt.nodes; l = nt.links; n.clear()
    out = n.new('ShaderNodeOutputMaterial')
    bsdf = n.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['IOR'].default_value = 1.5
    bsdf.inputs['Base Color'].default_value = (1, 1, 1, 1)
    if 'Transmission Weight' in bsdf.inputs: bsdf.inputs['Transmission Weight'].default_value = 1.0
    else: bsdf.inputs['Transmission'].default_value = 1.0
    # roughness from haze
    rimg = img_from_np('haze', h, 'Non-Color'); rt = n.new('ShaderNodeTexImage'); rt.image = rimg
    rt.interpolation = 'Cubic'; l.new(rt.outputs['Color'], bsdf.inputs['Roughness'])
    l.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    # volume absorption: Color = 1 + ln(T)/(D0*d0)
    tfloor = 0.0025
    absorb = np.clip(1.0 + np.log(np.clip(T, tfloor, 1.0)) / (D0 * D_SLAB), 0.0, 1.0)
    aimg = img_from_np('absorb', absorb, 'Non-Color'); at = n.new('ShaderNodeTexImage'); at.image = aimg
    at.interpolation = 'Cubic'
    vol = n.new('ShaderNodeVolumeAbsorption'); vol.inputs['Density'].default_value = D0
    l.new(at.outputs['Color'], vol.inputs['Color']); l.new(vol.outputs['Volume'], out.inputs['Volume'])
    return mat

def make_slab(height, disp_amp, mat):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=512, y_subdivisions=512, size=GLASS)
    ob = bpy.context.active_object; ob.name = 'Glass'
    # UV already present from grid; add displace + solidify
    himg = img_from_np('height', height, 'Non-Color')
    tex = bpy.data.textures.new('h', 'IMAGE'); tex.image = himg; tex.extension = 'EXTEND'
    dm = ob.modifiers.new('disp', 'DISPLACE'); dm.texture = tex; dm.texture_coords = 'UV'
    dm.strength = disp_amp; dm.mid_level = 0.5
    sm = ob.modifiers.new('sol', 'SOLIDIFY'); sm.thickness = D_SLAB; sm.offset = 0.0
    ob.data.materials.append(mat)
    for p in ob.data.polygons: p.use_smooth = True
    return ob

def make_backdrop(assets, res_scale):
    # default plane lies in XY with normal +Z -> already faces the +Z camera
    bpy.ops.mesh.primitive_plane_add(size=1.6, location=(0, 0, -0.55))
    ob = bpy.context.active_object; ob.name = 'Backdrop'
    mat = bpy.data.materials.new('BD'); mat.use_nodes = True
    n = mat.node_tree.nodes; l = mat.node_tree.links; n.clear()
    out = n.new('ShaderNodeOutputMaterial'); em = n.new('ShaderNodeEmission')
    tex = n.new('ShaderNodeTexImage')
    # build from backdrop.npy via the SAME flipud upload path as the glass maps
    # -> upright, and byte-for-byte the linear values three gets from backdrop.png
    bd_lin = np.load(os.path.join(assets, 'backdrop.npy'))
    bd = img_from_np('bd_emit', bd_lin, 'Non-Color'); tex.image = bd
    em.inputs['Strength'].default_value = 1.0
    l.new(tex.outputs['Color'], em.inputs['Color']); l.new(em.outputs['Emission'], out.inputs['Surface'])
    ob.data.materials.append(mat)
    return ob

def fixed_cam(R, fov_deg):
    """Camera on +Z, dead-on, ZERO roll -> trivially identical to three.js.
    Orbit is done by rotating the scene group instead (no track-quat/lookAt
    roll ambiguity between engines)."""
    bpy.ops.object.camera_add(location=(0, 0, R), rotation=(0, 0, 0))
    cam = bpy.context.active_object; bpy.context.scene.camera = cam
    cam.data.sensor_fit = 'VERTICAL'; cam.data.lens_unit = 'FOV'
    cam.data.angle = math.radians(fov_deg)
    return cam

def group_rotate(objs, az_deg, el_deg):
    """Parent objs to an Empty at origin and tilt it (elevation about X, azimuth
    about Y, XYZ order) -- the SAME euler three.js applies to its glass group."""
    bpy.ops.object.empty_add(location=(0, 0, 0)); e = bpy.context.active_object
    for o in objs:
        o.parent = e
    e.rotation_mode = 'XYZ'
    e.rotation_euler = (math.radians(el_deg), math.radians(az_deg), 0.0)
    return e

def render_to(path):
    sc = bpy.context.scene
    sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGB'
    sc.render.image_settings.color_depth = '8'
    sc.render.filepath = os.path.abspath(path)
    bpy.ops.render.render(write_still=True)

def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def build_lamp(assets, T, h, height, disp_amp):
    """Curved shell: a cylinder, 3mm wall, interior emitter, viewed from outside."""
    mat = glass_material(T, h, 'LampGlass')
    # axis along Y (vertical), matching three.js CylinderGeometry, so the
    # camera on +Z sees the curved SIDE wall with the interior emitter glowing through
    bpy.ops.mesh.primitive_cylinder_add(vertices=256, radius=0.06, depth=0.14,
                                        location=(0, 0, 0), rotation=(math.radians(90), 0, 0),
                                        end_fill_type='NOTHING')
    ob = bpy.context.active_object; ob.name = 'Shell'
    bpy.ops.object.transform_apply(rotation=True)
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.subdivide(number_cuts=6); bpy.ops.object.mode_set(mode='OBJECT')
    # cylindrical UVs for the tint/relief
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.cylinder_project(); bpy.ops.object.mode_set(mode='OBJECT')
    himg = img_from_np('lheight', height, 'Non-Color')
    tex = bpy.data.textures.new('lh', 'IMAGE'); tex.image = himg
    dm = ob.modifiers.new('disp', 'DISPLACE'); dm.texture = tex; dm.texture_coords = 'UV'
    dm.strength = disp_amp*0.5; dm.mid_level = 0.5
    sm = ob.modifiers.new('sol', 'SOLIDIFY'); sm.thickness = D_SLAB; sm.offset = 0.0
    ob.data.materials.append(mat)
    for p in ob.data.polygons: p.use_smooth = True
    # interior emitter (small bright cylinder along axis)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.02, depth=0.12, location=(0,0,0),
                                        rotation=(math.radians(90), 0, 0))
    em = bpy.context.active_object; em.name = 'Filament'
    bpy.ops.object.transform_apply(rotation=True)
    m = bpy.data.materials.new('Emit'); m.use_nodes = True
    nn = m.node_tree.nodes; ll = m.node_tree.links; nn.clear()
    o = nn.new('ShaderNodeOutputMaterial'); e = nn.new('ShaderNodeEmission')
    e.inputs['Strength'].default_value = 25.0; e.inputs['Color'].default_value = (1.0, 0.93, 0.82, 1)
    ll.new(e.outputs['Emission'], o.inputs['Surface']); em.data.materials.append(m)
    return ob, em

def parse():
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument('--assets', required=True); p.add_argument('--family', required=True)
    p.add_argument('--scene', default='flat', choices=['flat', 'lamp'])
    p.add_argument('--angles', default='0,10,15,30')
    p.add_argument('--res', type=int, default=640); p.add_argument('--spp', type=int, default=64)
    p.add_argument('--fov', type=float, default=34.0); p.add_argument('--dist', type=float, default=1.0)
    p.add_argument('--elev', type=float, default=6.0)
    p.add_argument('--out', required=True)
    return p.parse_args(argv)

def main():
    a = parse()
    d = os.path.join(a.assets, a.family)
    T = np.load(os.path.join(d, 'T.npy')); h = np.load(os.path.join(d, 'h.npy'))
    height = np.load(os.path.join(d, 'height.npy'))
    manifest = json.load(open(os.path.join(a.assets, 'families.json')))
    disp_amp = manifest[a.family]['bump_distance_m']
    outdir = os.path.join(a.out, a.family, a.scene); os.makedirs(outdir, exist_ok=True)
    angles = [float(x) for x in a.angles.split(',')]

    if a.scene == 'flat':
        for az in angles:
            clear(); setup_render(a.res, a.spp); world_env(os.path.join(a.assets, 'env.hdr'))
            mat = glass_material(T, h); ob = make_slab(height, disp_amp, mat)
            bd = make_backdrop(a.assets, a.res)
            group_rotate([ob, bd], az, a.elev)
            fixed_cam(a.dist, a.fov)
            render_to(os.path.join(outdir, f'truth_az{int(az)}.png'))
            # background-only (glass hidden) alignment/parallax reference
            ob.hide_render = True
            render_to(os.path.join(outdir, f'bg_az{int(az)}.png'))
            print(f"RENDERED flat {a.family} az{az}")
    else:
        for az in angles:
            clear(); setup_render(a.res, a.spp); world_env(os.path.join(a.assets, 'env.hdr'), strength=0.35)
            shell, fil = build_lamp(a.assets, T, h, height, disp_amp)
            group_rotate([shell, fil], az, a.elev)
            fixed_cam(0.42, 26.0)
            render_to(os.path.join(outdir, f'truth_az{int(az)}.png'))
            print(f"RENDERED lamp {a.family} az{az}")
    # write scene meta for the three.js harness to match camera exactly
    meta = {'scene': a.scene, 'family': a.family, 'res': a.res, 'fov_deg': a.fov,
            'dist': a.dist, 'elev_deg': a.elev, 'angles': angles, 'glass_m': GLASS,
            'd_slab_m': D_SLAB, 'D0': D0, 'disp_amp_m': disp_amp,
            'lamp': {'radius': 0.06, 'depth': 0.14, 'dist': 0.42, 'fov': 26.0}}
    with open(os.path.join(outdir, 'scene_meta.json'), 'w') as f: json.dump(meta, f, indent=2)
    print('DONE', a.scene, a.family)

if __name__ == '__main__':
    main()
