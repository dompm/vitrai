"""Assembled-pair benchmark generator (report 014).

Simulates the real-world ground-truth pair ENTIRELY in Blender, so the sheet and
the assembled piece are the SAME glass by construction (same authored T,h,mark
textures -> exact texture correspondence, no registration).

For each authored glass material it renders, under a controllable HDRI:
  RENDER A : the FLAT sheet "capture" under IBL_1  -> the extractor's input photo.
  RENDER B : a simple ASSEMBLED piece -- four square pieces cut from KNOWN UV
             regions of that sheet, laid in a 2x2 grid with dark lead strips
             between them -- under IBL_2 (same HDRI rotated + EV shifted). This
             is the RELIGHT TRUTH. One render per IBL_2 variant.
  RENDER C : the same assembled piece under IBL_1 (separates assembly-model
             error from relight error).
Plus aligned ground-truth authored maps (gt_T/gt_h/gt_mark) in RENDER-A image
space, reused from generate_synthetic.

Purity (per the brief): NO hand-shadow casters, NO border occluders, and the
procedural hammered bump is DISABLED (use_bump=False) so the rendered appearance
equals the authored T,h -- relief/shadows are separate, already-studied axes.
The pieces are 4 coplanar squares + thin near-black coplanar lead strips.

Every piece's UV rect, its source pixel bbox in RENDER A, its dest pixel bbox in
the assembled image, and all lighting params are recorded in meta.json so the
bench can sample the extracted maps at the exact known regions.

Run (Blender 5.0.1):
  PYTHONPATH=~/.local/lib/python3.11/site-packages \
    ~/Applications/Blender-5.0.1.app/Contents/MacOS/Blender -b \
    --python-use-system-env -P generate_assembled.py -- --out assembled_data
"""
import bpy
import numpy as np
import argparse
import os
import json
import math
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate_synthetic import (  # noqa: E402
    create_glass_textures, create_glass_material, download_polyhaven_hdri,
    render_sample, render_ground_truths,
)

# ----------------------------------------------------------------- constants
RES = 1024              # render resolution (square). Correspondence is recorded
                        # in pixels at this res, so it is res-independent.
SAMPLES = 96
CAM_DIST = 0.4          # camera sits at (0, -CAM_DIST, 0), looking +Y
SHEET_SIZE = 0.5        # flat sheet plane full width -> UV: u = 2*X + 0.5
LEAD_Y = 0.004          # lead strips a hair behind the glass (avoid z-fight)
LEAD_DARK = 0.006       # near-black lead albedo

# 2x2 piece layout (world metres, in the glass plane).
PIECE_HALF = 0.050      # half-size of each square piece
GAP_HALF = 0.007        # half-width of the lead line between pieces
BORDER = 0.012          # lead border thickness around the 2x2
CENTER = PIECE_HALF + GAP_HALF          # piece-centre offset from origin
GRID_HALF = CENTER + PIECE_HALF + BORDER  # outer half-extent of the leaded panel

# Materials: one transmissive cathedral (hard case) + one opalescent product case.
MATERIALS = [
    ("cathedral-green", "cathedral-clear"),
    ("wispy-white", "wispy"),
]

# Lighting. IBL_1 is the capture light; IBL_2 variants are the same HDRI rotated
# about Z (~90-135 deg) and EV-shifted (+/-1). X-tilt is held fixed so it is
# genuinely "the same HDRI, rotated" and not a different sky slice.
XTILT = 0.10
IBL_1 = {"z_rot": 0.60, "ev": 0.0}
IBL_2_VARIANTS = [
    {"name": "rot135_evm1", "z_rot": 0.60 + math.radians(135), "ev": -1.0},
    {"name": "rot90_evp1",  "z_rot": 0.60 + math.radians(90),  "ev": +1.0},
]


# ------------------------------------------------------------------ scene ops
def common_render_setup(scene):
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
    scene.cycles.samples = SAMPLES
    scene.view_settings.view_transform = 'Standard'
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100


def build_world_hdri(scene, hdri_path):
    """Create the HDRI world node graph once; lighting is set via set_lighting."""
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    n = world.node_tree.nodes
    lk = world.node_tree.links
    n.clear()
    wout = n.new('ShaderNodeOutputWorld')
    wbg = n.new('ShaderNodeBackground')
    wtex = n.new('ShaderNodeTexEnvironment')
    wtex.image = bpy.data.images.load(hdri_path)
    wmap = n.new('ShaderNodeMapping')
    wcoord = n.new('ShaderNodeTexCoord')
    lk.new(wcoord.outputs['Generated'], wmap.inputs['Vector'])
    lk.new(wmap.outputs['Vector'], wtex.inputs['Vector'])
    lk.new(wtex.outputs['Color'], wbg.inputs['Color'])
    lk.new(wbg.outputs['Background'], wout.inputs['Surface'])
    return wmap, wbg


def set_lighting(wmap, wbg, z_rot, ev):
    wmap.inputs['Rotation'].default_value[0] = XTILT
    wmap.inputs['Rotation'].default_value[2] = z_rot
    wbg.inputs['Strength'].default_value = 2.0 ** ev


def add_camera(scene):
    bpy.ops.object.camera_add(location=(0, -CAM_DIST, 0), rotation=(math.radians(90), 0, 0))
    cam = bpy.context.active_object
    scene.camera = cam
    return cam


def add_dark_wall():
    """Kill front-face HDRI reflections (dim interior), matching generate_synthetic."""
    bpy.ops.mesh.primitive_plane_add(size=5.0, location=(0, -2.0, 0), rotation=(math.radians(90), 0, 0))
    wall = bpy.context.active_object
    wall.name = "DarkWall"
    m = bpy.data.materials.new(name="WallMat")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0, 0, 0, 1)
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.0
    wall.data.materials.append(m)
    return wall


def projection(cam):
    """Pinhole map for the (jitter-free) camera at glass depth y=0.
    Returns visible half-extents and the visible UV window (u = 2*X + 0.5).

    NB: for sensor_fit='AUTO' the FIT axis is the horizontal (sensor_width) when
    res_x >= res_y, and the vertical FOV of the actual render scales by the pixel
    aspect -- so cam.data.angle_y (which is derived from sensor_height=24mm, not
    the render aspect) is NOT the true rendered vertical FOV for a square image.
    Verified empirically (report 014): a square render shows a SQUARE world
    region, i.e. vis_half_z == vis_half_x, not the 0.096 that angle_y implies.
    We therefore derive vhz from vhx and the pixel aspect."""
    vhx = CAM_DIST * math.tan(cam.data.angle_x / 2.0)
    vhz = vhx * (RES / RES)  # square render -> square world region; general: *res_y/res_x
    return {
        "vis_half_x": vhx, "vis_half_z": vhz,
        "u_lo": 0.5 - 2 * vhx, "u_hi": 0.5 + 2 * vhx,
        "v_lo": 0.5 - 2 * vhz, "v_hi": 0.5 + 2 * vhz,
        "W": RES, "H": RES,
    }


def world_x_to_col(x, pj):
    return (x + pj["vis_half_x"]) / (2 * pj["vis_half_x"]) * pj["W"]


def world_z_to_row(z, pj):
    # image row 0 = top = max Z
    return (pj["vis_half_z"] - z) / (2 * pj["vis_half_z"]) * pj["H"]


def uv_to_col(u, pj):
    return (u - pj["u_lo"]) / (pj["u_hi"] - pj["u_lo"]) * pj["W"]


def uv_to_row(v, pj):
    return (pj["v_hi"] - v) / (pj["v_hi"] - pj["v_lo"]) * pj["H"]


def set_uv_rect(obj, u0, v0, u1, v1, half):
    """Map the square piece's local x,y in [-half,half] to sheet UV rect, so the
    piece samples exactly that region of the shared sheet texture. Local x->u,
    local y->v matches the flat sheet's default plane UV (both are size-plane_add
    planes rotated (90,0,0), so local x=world X and local y=world Z)."""
    me = obj.data
    uvlayer = me.uv_layers.active.data
    for loop in me.loops:
        co = me.vertices[loop.vertex_index].co
        fx = (co.x + half) / (2 * half)
        fy = (co.y + half) / (2 * half)
        uvlayer[loop.index].uv = (u0 + fx * (u1 - u0), v0 + fy * (v1 - v0))


def lead_material():
    m = bpy.data.materials.new(name="LeadMat")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (LEAD_DARK, LEAD_DARK, LEAD_DARK, 1)
    b.inputs["Roughness"].default_value = 0.7
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.1
    return m


def add_lead_rect(cx, cz, w, h, mat):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(cx, LEAD_Y, cz), rotation=(math.radians(90), 0, 0))
    r = bpy.context.active_object
    r.scale = (w, h, 1.0)
    r.data.materials.append(mat)


def add_lead_strips():
    """Lead = the complement of the 4 glass squares inside the panel bbox: a plus
    between the pieces + a border frame. Coplanar-behind so the squares keep a
    clear HDRI backlight (a full backing plane would block their transmission)."""
    mat = lead_material()
    inner = CENTER - PIECE_HALF   # inner edge of a piece (start of the centre gap)
    outer = CENTER + PIECE_HALF   # outer edge of a piece
    span = 2 * GRID_HALF
    # centre cross
    add_lead_rect(0, 0, 2 * GAP_HALF, span, mat)   # vertical
    add_lead_rect(0, 0, span, 2 * GAP_HALF, mat)   # horizontal
    # border frame (top/bottom/left/right)
    bw = GRID_HALF - outer
    bc = (outer + GRID_HALF) / 2.0
    add_lead_rect(0,  bc, span, bw, mat)
    add_lead_rect(0, -bc, span, bw, mat)
    add_lead_rect(-bc, 0, bw, span, mat)
    add_lead_rect(bc, 0, bw, span, mat)
    _ = inner  # (documented; layout constants are self-consistent)


def piece_layout(pj):
    """The 4 canonical pieces. Source UV = identity mapping (a piece sitting at
    grid slot (cx,cz) is cut from the sheet region it sits over), giving the
    purest correspondence: the assembled panel is the sheet with lead cut in.
    Records source(RENDER-A) and dest(assembled) pixel bboxes for the bench."""
    s = PIECE_HALF
    slots = {  # name -> (cx, cz) grid centre
        "TL": (-CENTER,  CENTER), "TR": (CENTER,  CENTER),
        "BL": (-CENTER, -CENTER), "BR": (CENTER, -CENTER),
    }
    pieces = []
    for name, (cx, cz) in slots.items():
        # canonical source UV rect = the sheet region under this slot
        u0, u1 = 2 * (cx - s) + 0.5, 2 * (cx + s) + 0.5
        v0, v1 = 2 * (cz - s) + 0.5, 2 * (cz + s) + 0.5
        src = [round(uv_to_col(u0, pj), 2), round(uv_to_row(v1, pj), 2),
               round(uv_to_col(u1, pj), 2), round(uv_to_row(v0, pj), 2)]  # x0,y0,x1,y1
        dst = [round(world_x_to_col(cx - s, pj), 2), round(world_z_to_row(cz + s, pj), 2),
               round(world_x_to_col(cx + s, pj), 2), round(world_z_to_row(cz - s, pj), 2)]
        pieces.append({
            "name": name, "world_center": [cx, cz], "half_size": s,
            "uv_rect": [round(u0, 5), round(v0, 5), round(u1, 5), round(v1, 5)],
            "src_bbox_px": src, "dest_bbox_px": dst,
        })
    return pieces


def build_flat_scene(scene, hdri_path, recipe, sample_dir, seed):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    common_render_setup(scene)
    wmap, wbg = build_world_hdri(scene, hdri_path)
    bpy.ops.mesh.primitive_plane_add(size=SHEET_SIZE, location=(0, 0, 0), rotation=(math.radians(90), 0, 0))
    glass = bpy.context.active_object
    glass.name = "GlassSheet"
    cam = add_camera(scene)
    add_dark_wall()
    img_T, img_h, img_mark, img_height, img_normal, bump_distance = create_glass_textures(recipe, sample_dir, size=1536, seed=seed)
    create_glass_material(glass, img_T, img_h, img_mark, img_height, recipe, bump_distance, use_bump=False)
    return scene, glass, cam, wmap, wbg, (img_T, img_h, img_mark)


def build_assembled_scene(scene, hdri_path, recipe, sample_dir, seed, pieces):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    common_render_setup(scene)
    wmap, wbg = build_world_hdri(scene, hdri_path)
    cam = add_camera(scene)
    add_dark_wall()
    add_lead_strips()
    img_T, img_h, img_mark, img_height, img_normal, bump_distance = create_glass_textures(recipe, sample_dir, size=1536, seed=seed)
    for p in pieces:
        cx, cz = p["world_center"]
        s = p["half_size"]
        bpy.ops.mesh.primitive_plane_add(size=2 * s, location=(cx, 0, cz), rotation=(math.radians(90), 0, 0))
        obj = bpy.context.active_object
        obj.name = f"Piece_{p['name']}"
        u0, v0, u1, v1 = p["uv_rect"]
        set_uv_rect(obj, u0, v0, u1, v1, s)
        create_glass_material(obj, img_T, img_h, img_mark, img_height, recipe, bump_distance, use_bump=False)
    return scene, cam, wmap, wbg


def process_material(recipe, gclass, hdri_path, out_root, seed):
    sample_dir = os.path.join(out_root, f"{recipe}__seed{seed}")
    os.makedirs(sample_dir, exist_ok=True)
    print(f"\n=== {recipe} (class {gclass}) -> {sample_dir} ===")

    # --- FLAT scene: RENDER A under IBL_1 + aligned ground-truth maps
    scene, glass, cam, wmap, wbg, imgs = build_flat_scene(scene=None, hdri_path=hdri_path,
                                                          recipe=recipe, sample_dir=sample_dir, seed=seed)
    pj = projection(cam)
    pieces = piece_layout(pj)
    set_lighting(wmap, wbg, IBL_1["z_rot"], IBL_1["ev"])
    print("  render A (flat sheet, IBL_1)...")
    render_sample(sample_dir, "renderA_")
    print("  render ground-truth maps...")
    render_ground_truths(glass, sample_dir, *imgs)

    # --- ASSEMBLED scene: RENDER B (each IBL_2 variant) + RENDER C (IBL_1)
    scene, cam, wmap, wbg = build_assembled_scene(scene, hdri_path, recipe, sample_dir, seed, pieces)
    for var in IBL_2_VARIANTS:
        set_lighting(wmap, wbg, var["z_rot"], var["ev"])
        print(f"  render B (assembled, IBL_2 {var['name']})...")
        render_sample(sample_dir, f"renderB_{var['name']}_")
    set_lighting(wmap, wbg, IBL_1["z_rot"], IBL_1["ev"])
    print("  render C (assembled, IBL_1)...")
    render_sample(sample_dir, "renderC_")

    meta = {
        "recipe": recipe, "glass_class": gclass, "seed": seed,
        "resolution": RES, "cam_dist": CAM_DIST, "sheet_size": SHEET_SIZE,
        "projection": pj,
        "layout": {"piece_half": PIECE_HALF, "gap_half": GAP_HALF,
                   "border": BORDER, "grid_half": GRID_HALF},
        "lighting": {
            "xtilt": XTILT,
            "IBL_1": IBL_1,
            "IBL_2_variants": IBL_2_VARIANTS,
        },
        "renders": {
            "A": "renderA_photo_linear.exr (flat sheet, IBL_1) -- extractor input",
            "B": {v["name"]: f"renderB_{v['name']}_photo_linear.exr (assembled, IBL_2)" for v in IBL_2_VARIANTS},
            "C": "renderC_photo_linear.exr (assembled, IBL_1) -- assembly-model check",
        },
        "pieces": pieces,
        "blender_version": bpy.app.version_string,
    }
    with open(os.path.join(sample_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  wrote {os.path.join(sample_dir, 'meta.json')}")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--recipe", default=None, help="render only this recipe")
    return ap.parse_args(argv)


def main():
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)
    hdri_path = download_polyhaven_hdri(args.out)
    mats = [(r, c) for (r, c) in MATERIALS if args.recipe is None or r == args.recipe]
    for recipe, gclass in mats:
        process_material(recipe, gclass, hdri_path, args.out, args.seed)


if __name__ == "__main__":
    main()
