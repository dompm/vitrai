"""Iteration 045 -- ORACLE RELIGHT truth renderer.

Renders, per (recipe, seed) sample, the SAME authored glass sheet in two
controlled scenes:

  (a) UNIFORM LIGHTBOX  -- emissive white plane (strength 1.0) behind the
      sheet, black room, straight-on camera. prefix `uniform_`.
  (b) STRUCTURED BACKDROP -- the same plane with a backlit two-tone checker
      (warm-white / cool-dark, 0.2 m squares). prefix `struct_`.

These are the relight TRUTHS the analytic reconstructions (recon_bench_045.py)
are scored against. Per scene we save:
  <prefix>photo.png            sRGB 8-bit (Standard view transform)
  <prefix>photo_linear.exr     scene-linear 32-bit (the metric target)
  <prefix>B.exr                the scene with the glass HIDDEN = the exact
                               per-pixel background B (scene-linear)
  <prefix>veil.exr             Glossy Direct+Indirect AOV = front-surface
                               reflection veil (multilayer EXR; read with
                               extract.load_aov_exr) -- expected ~0 in the
                               black room, exported for honesty
plus once per sample (camera identical in both scenes):
  gt_T/gt_h/gt_height/gt_normal .exr  -- camera-aligned GT maps via the
      emission-passthrough trick (sRGB-shaped on disk, report-025 decode)
  meta.json  -- geometry + material params the recon needs (camera lens/
      sensor, glass/backdrop distances, checker params, bump_distance).

Purity choices (all deliberate, mirroring the dataset defaults except where
noted): marks OFF (the current app model has no mark term; they would
contaminate a model-expressiveness metric), shadows OFF, frame occluders OFF,
specular OFF (dataset default), bump ON (relief IS one of the effects under
study -- Cycles bump bends transmitted rays, so the truth carries real
shading+lensing structure).

Uses a VERBATIM copy of the trunk generate_synthetic.py (gen045_module.py,
byte-identical to origin/research/delighting at study start) -- iteration 043
has a concurrent editor on the original, which is never touched.

Run (inside Blender):
  <blender> -b --python-use-system-env -P gen_oracle45.py -- \
      --out <data_dir> --samples cathedral-green:6001,wispy-white:6085 [--res 1024]
"""

import argparse
import json
import math
import os
import sys
import time

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen045_module as G

# ---------------------------------------------------------------- constants
GLASS_SIZE = 0.5          # m, matches dataset
CAM_Y = -0.4              # m
BACKDROP_Y = 2.0          # m (same plane position as --validate mode)
BACKDROP_SIZE = 50.0      # m
CHECKER_SQUARE_M = 0.2    # checker square edge in meters
CHECKER_C1 = (1.0, 0.95, 0.88)   # warm white
CHECKER_C2 = (0.10, 0.12, 0.16)  # cool dark (non-zero: keeps signal in dark T)
TEX_SIZE = 1536           # authored texture res, dataset canonical


def wait_msg(msg):
    print(f"[oracle45] {msg}", flush=True)


def setup_scene_oracle(pattern, res):
    """Black-room lightbox scene. pattern in {'uniform','checker'}."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    scene.cycles.device = 'GPU' if prefs.has_active_device() else 'CPU'
    scene.cycles.max_bounces = 24
    scene.cycles.transparent_max_bounces = 24
    scene.cycles.transmission_bounces = 24
    scene.cycles.use_denoising = True
    scene.cycles.samples = 64
    scene.view_settings.view_transform = 'Standard'
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.resolution_percentage = 100

    # Black world (the "black room")
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    wn = world.node_tree.nodes
    wl = world.node_tree.links
    wn.clear()
    wout = wn.new('ShaderNodeOutputWorld')
    wbg = wn.new('ShaderNodeBackground')
    wbg.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
    wbg.inputs['Strength'].default_value = 1.0
    wl.new(wbg.outputs['Background'], wout.inputs['Surface'])

    # Emissive backlight plane behind the sheet
    bpy.ops.mesh.primitive_plane_add(size=BACKDROP_SIZE, location=(0, BACKDROP_Y, 0),
                                     rotation=(math.radians(90), 0, 0))
    backlight = bpy.context.active_object
    backlight.name = "Backlight"
    mat = bpy.data.materials.new(name="BacklightMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    emission = nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 1.0
    out = nodes.new('ShaderNodeOutputMaterial')
    links.new(emission.outputs['Emission'], out.inputs['Surface'])
    if pattern == 'uniform':
        emission.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
    else:
        checker = nodes.new('ShaderNodeTexChecker')
        checker.inputs['Color1'].default_value = (*CHECKER_C1, 1.0)
        checker.inputs['Color2'].default_value = (*CHECKER_C2, 1.0)
        # Generated coords span [0,1] over the plane's bounding box
        # (BACKDROP_SIZE m), so scale = size / square edge.
        checker.inputs['Scale'].default_value = BACKDROP_SIZE / CHECKER_SQUARE_M
        coord = nodes.new('ShaderNodeTexCoord')
        links.new(coord.outputs['Generated'], checker.inputs['Vector'])
        links.new(checker.outputs['Color'], emission.inputs['Color'])
    backlight.data.materials.append(mat)

    # Glass sheet
    bpy.ops.mesh.primitive_plane_add(size=GLASS_SIZE, align='WORLD', location=(0, 0, 0),
                                     rotation=(math.radians(90), 0, 0))
    glass_obj = bpy.context.active_object
    glass_obj.name = "GlassSheet"
    glass_obj.pass_index = 1

    # Straight-on camera, NO jitter (deterministic pixel<->UV)
    bpy.ops.object.camera_add(location=(0, CAM_Y, 0), rotation=(math.radians(90), 0, 0))
    cam = bpy.context.active_object
    scene.camera = cam

    # Dark wall behind camera (dataset default; keeps front hemisphere unlit)
    bpy.ops.mesh.primitive_plane_add(size=5.0, location=(0, -2.0, 0),
                                     rotation=(math.radians(90), 0, 0))
    wall = bpy.context.active_object
    wall.name = "DarkWall"
    mat_wall = bpy.data.materials.new(name="WallMat")
    mat_wall.use_nodes = True
    bsdf = mat_wall.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1)
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    wall.data.materials.append(mat_wall)

    return glass_obj, cam


def setup_veil_aov(sample_dir, name):
    """Slim veil-only AOV writer (pattern from gen045_module.setup_aov_outputs)."""
    scene = bpy.context.scene
    vl = bpy.context.view_layer
    vl.use_pass_glossy_direct = True
    vl.use_pass_glossy_indirect = True
    ng = bpy.data.node_groups.new("Oracle45_veil", 'CompositorNodeTree')
    scene.compositing_node_group = ng
    scene.use_nodes = True
    nodes, links = ng.nodes, ng.links
    rl = nodes.new('CompositorNodeRLayers')
    rl_outs = {o.name: o for o in rl.outputs}
    fo = nodes.new('CompositorNodeOutputFile')
    fo.format.file_format = 'OPEN_EXR_MULTILAYER'
    fo.format.color_depth = '32'
    fo.format.exr_codec = 'DWAA'
    fo.file_output_items.new(socket_type='RGBA', name=name)
    add = nodes.new('ShaderNodeMixRGB')
    add.blend_type = 'ADD'
    add.inputs[0].default_value = 1.0
    links.new(rl_outs['Glossy Direct'], add.inputs[1])
    links.new(rl_outs['Glossy Indirect'], add.inputs[2])
    links.new(add.outputs['Color'], fo.inputs[name])
    fo.directory = os.path.abspath(sample_dir)
    fo.file_name = name


def teardown_veil_aov():
    scene = bpy.context.scene
    scene.compositing_node_group = None
    scene.use_nodes = False


def save_render_result(path_noext, png=True):
    scene = bpy.context.scene
    rr = bpy.data.images['Render Result']
    if png:
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.image_settings.color_depth = '8'
        rr.save_render(os.path.abspath(path_noext + ".png"))
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '32'
    scene.render.image_settings.exr_codec = 'DWAA'
    rr.save_render(os.path.abspath(path_noext + "_linear.exr" if png else path_noext + ".exr"))


def render_scene(sample_dir, prefix, glass_obj):
    """Main photo (with veil AOV) + hidden-glass B render."""
    scene = bpy.context.scene
    setup_veil_aov(sample_dir, f"{prefix}veil")
    t0 = time.perf_counter()
    bpy.ops.render.render(write_still=False)
    wait_msg(f"{prefix}photo rendered in {time.perf_counter()-t0:.1f}s")
    teardown_veil_aov()
    save_render_result(os.path.join(sample_dir, f"{prefix}photo"), png=True)

    # Hidden-glass background render = exact B
    orig_samples = scene.cycles.samples
    glass_obj.hide_render = True
    scene.cycles.samples = max(8, orig_samples // 4)
    bpy.ops.render.render(write_still=False)
    glass_obj.hide_render = False
    scene.cycles.samples = orig_samples
    save_render_result(os.path.join(sample_dir, f"{prefix}B"), png=False)


def render_gt_maps(sample_dir, glass_obj, arrays_imgs):
    """Camera-aligned GT via the emission-passthrough trick (samples=1, Raw).
    Only the 4 channels the oracle recon needs. Same encode conventions as
    gen045_module.render_ground_truths (sRGB-shaped on disk, report 025)."""
    scene = bpy.context.scene
    world = scene.world
    bg_node = world.node_tree.nodes.get('Background')
    orig_strength = bg_node.inputs['Strength'].default_value
    bg_node.inputs['Strength'].default_value = 0.0
    # Hide backlight + wall for the emission trick
    hidden = []
    for name in ("Backlight", "DarkWall"):
        ob = bpy.data.objects.get(name)
        if ob:
            ob.hide_render = True
            hidden.append(ob)

    mat_gt = bpy.data.materials.new(name="GT_Mat")
    mat_gt.use_nodes = True
    nodes = mat_gt.node_tree.nodes
    links = mat_gt.node_tree.links
    nodes.clear()
    out_node = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')
    tex_node = nodes.new('ShaderNodeTexImage')
    links.new(tex_node.outputs['Color'], emission.inputs['Color'])
    links.new(emission.outputs['Emission'], out_node.inputs['Surface'])

    orig_mat = glass_obj.data.materials[0]
    glass_obj.data.materials[0] = mat_gt
    scene.view_settings.view_transform = 'Raw'
    orig_samples = scene.cycles.samples
    scene.cycles.samples = 1

    for gt_name, gt_img, color_mode in arrays_imgs:
        tex_node.image = gt_img
        bpy.ops.render.render(write_still=False)
        rr = bpy.data.images['Render Result']
        scene.render.image_settings.file_format = 'OPEN_EXR'
        scene.render.image_settings.color_depth = '32'
        scene.render.image_settings.color_mode = color_mode
        scene.render.image_settings.exr_codec = 'DWAA'
        rr.save_render(os.path.abspath(os.path.join(sample_dir, f"{gt_name}.exr")))

    glass_obj.data.materials[0] = orig_mat
    scene.view_settings.view_transform = 'Standard'
    scene.cycles.samples = orig_samples
    bg_node.inputs['Strength'].default_value = orig_strength
    for ob in hidden:
        ob.hide_render = False


def run_sample(recipe, seed, out_root, res, tex_cache):
    sample_dir = os.path.join(out_root, f"{recipe}__seed{seed}")
    os.makedirs(sample_dir, exist_ok=True)
    wait_msg(f"=== {recipe} seed {seed} -> {sample_dir}")

    # Author once (numpy, cached); marks suppressed via GT_OPTS.
    key = (recipe, seed, TEX_SIZE)
    if key not in tex_cache:
        tex_cache[key] = G.author_glass_arrays(recipe, size=TEX_SIZE, seed=seed)
    T, h, mark_dark, mark_white, mark_index, height, normal, bump_distance = tex_cache[key]

    cam_meta = None
    for pattern, prefix in (("uniform", "uniform_"), ("checker", "struct_")):
        glass_obj, cam = setup_scene_oracle(pattern, res)
        # bpy encode must rerun after each factory reset (module docs)
        (img_T, img_h, img_mark, img_mark_white, img_mark_index, img_height,
         img_normal, _bd) = G.encode_glass_textures(
            sample_dir, T, h, mark_dark, mark_white, mark_index, height, normal,
            bump_distance)
        G.create_glass_material(glass_obj, img_T, img_h, img_mark, img_mark_white,
                                img_height, recipe, bump_distance,
                                use_bump=True, specular_ior_level=None)
        render_scene(sample_dir, prefix, glass_obj)
        if pattern == "uniform":
            # GT maps once (camera identical across scenes)
            render_gt_maps(sample_dir, glass_obj, [
                ("gt_T", img_T, 'RGB'),
                ("gt_h", img_h, 'BW'),
                ("gt_height", img_height, 'BW'),
                ("gt_normal", img_normal, 'RGB'),
            ])
            cam_meta = {
                "lens_mm": cam.data.lens,
                "sensor_width_mm": cam.data.sensor_width,
                "sensor_fit": cam.data.sensor_fit,
                "location": list(cam.location),
            }

    # prune tex dumps (GT_SPEC sec 3; they were load-bearing during render)
    for _tex in ("tex_T", "tex_h", "tex_mark_mask", "tex_mark_white",
                 "tex_mark_index", "tex_height", "tex_normal"):
        p = os.path.join(sample_dir, _tex + ".exr")
        if os.path.exists(p):
            os.remove(p)

    meta = {
        "recipe": recipe,
        "seed": seed,
        "resolution": res,
        "tex_size": TEX_SIZE,
        "glass_size_m": GLASS_SIZE,
        "cam_y_m": CAM_Y,
        "backdrop_y_m": BACKDROP_Y,
        "backdrop_size_m": BACKDROP_SIZE,
        "checker": {"square_m": CHECKER_SQUARE_M, "c1": CHECKER_C1, "c2": CHECKER_C2},
        "camera": cam_meta,
        "bump_distance_m": bump_distance,
        "ior": 1.5,
        "marks": "suppressed",
        "opal_scatter_lobe": recipe in G.OPAL_SCATTER_RECIPES,
        "blender_version": bpy.app.version_string,
        "module_provenance": "gen045_module.py == origin/research/delighting generate_synthetic.py (byte-identical at study start)",
    }
    with open(os.path.join(sample_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)


def parse_args():
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True)
    p.add_argument('--samples', required=True,
                   help="comma list of recipe:seed, e.g. cathedral-green:6001,wispy-white:6085")
    p.add_argument('--res', type=int, default=1024)
    return p.parse_args(argv)


def main():
    args = parse_args()
    G.GT_OPTS["no_marks"] = True     # purity: no marks in the oracle study
    G.GT_OPTS["exr_codec"] = 'DWAA'
    os.makedirs(args.out, exist_ok=True)
    tex_cache = {}
    for spec in args.samples.split(","):
        recipe, seed = spec.rsplit(":", 1)
        run_sample(recipe.strip(), int(seed), args.out, args.res, tex_cache)
    wait_msg("all samples done")


if __name__ == '__main__':
    main()
