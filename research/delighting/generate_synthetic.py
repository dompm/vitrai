import bpy
import numpy as np
import argparse
import os
import json
import math
import random
import sys

# Ensure we're running in background mode if we want, though this script works either way.
# Usage: python generate_synthetic.py --out DIR --seed N --count M

def generate_noise(size, scale, seed, octaves=1):
    """Generate basic 2D noise using numpy."""
    np.random.seed(seed)
    
    from scipy.ndimage import zoom
    
    base_res = max(1, int(size / scale))
    low_freq = np.random.rand(base_res, base_res)
    
    zoom_factor = size / base_res
    noise_img = zoom(low_freq, zoom_factor, order=3) 
    
    noise_img = noise_img[:size, :size]
    
    # Normalize to 0-1
    noise_img = (noise_img - noise_img.min()) / (noise_img.max() - noise_img.min() + 1e-8)
    return noise_img

def generate_scribble_mask(size, seed):
    np.random.seed(seed)
    mask = np.zeros((size, size), dtype=np.float32)
    num_lines = np.random.randint(1, 4)
    
    for _ in range(num_lines):
        # Random walk for scribble
        x, y = np.random.randint(0, size, 2)
        steps = np.random.randint(50, 200)
        
        # Smooth random walk using low frequency noise to drive direction
        angle = np.random.uniform(0, 2 * np.pi)
        for s in range(steps):
            if 0 <= x < size and 0 <= y < size:
                # Draw a thick dot
                r = np.random.randint(2, 6)
                ymin = max(0, int(y-r))
                ymax = min(size, int(y+r))
                xmin = max(0, int(x-r))
                xmax = min(size, int(x+r))
                mask[ymin:ymax, xmin:xmax] = 1.0
            
            # Change angle slightly
            angle += np.random.normal(0, 0.3)
            x += np.cos(angle) * np.random.uniform(2, 8)
            y += np.sin(angle) * np.random.uniform(2, 8)
            
    # Soften edges slightly
    from scipy.ndimage import gaussian_filter
    mask = gaussian_filter(mask, sigma=1.0)
    return np.clip(mask, 0, 1)

def save_numpy_to_image(array, filepath, is_color=True):
    H, W = array.shape[:2]
    
    if not is_color:
        rgba = np.ones((H, W, 4), dtype=np.float32)
        rgba[..., 0] = array
        rgba[..., 1] = array
        rgba[..., 2] = array
    else:
        rgba = np.ones((H, W, 4), dtype=np.float32)
        rgba[..., :3] = array
        
    pixels = rgba.flatten()
    
    name = f"{os.path.basename(filepath)}_{random.randint(0, 99999999)}"
    
    # Always create a new image to prevent Blender caching across variations
    img = bpy.data.images.new(name, width=W, height=H, alpha=False, float_buffer=True)
        
    img.pixels.foreach_set(pixels)
    
    # To avoid Blender's sRGB view transform on PNGs, ALWAYS save as EXR
    if filepath.endswith('.png'):
        filepath = filepath[:-4] + '.exr'
    img.filepath_raw = filepath
    img.file_format = 'OPEN_EXR'
        
    img.save()
    
    # We must set colorspace AFTER saving, otherwise Blender zeroes out the pixels!
    img.colorspace_settings.name = 'Linear Rec.709' if is_color else 'Non-Color'
    return img

def create_glass_textures(recipe, out_dir, size=1536, seed=42):
    np.random.seed(seed)
    
    if recipe == 'cathedral-green':
        base_color = np.array([0.15, 0.55, 0.20])
        noise = generate_noise(size, scale=200, seed=seed)
        noise_scaled = (noise * 0.2) - 0.1 
        T = np.clip(base_color * (1.0 + noise_scaled[..., None]), 0, 1)
        h = np.full((size, size), 0.02, dtype=np.float32)
        
    elif recipe == 'cathedral-amber':
        base_color = np.array([0.75, 0.45, 0.08])
        noise = generate_noise(size, scale=200, seed=seed)
        noise_scaled = (noise * 0.2) - 0.1
        T = np.clip(base_color * (1.0 + noise_scaled[..., None]), 0, 1)
        h = np.full((size, size), 0.02, dtype=np.float32)
        
    elif recipe == 'dark-opaque':
        base_color = np.array([0.03, 0.035, 0.03])
        noise = generate_noise(size, scale=50, seed=seed)
        noise_scaled = (noise * 0.01) - 0.005
        T = np.clip(base_color + noise_scaled[..., None], 0, 1)
        h = np.full((size, size), 0.3, dtype=np.float32)
        
    elif recipe == 'streaky-mix':
        noise = generate_noise(size, scale=250, seed=seed)
        from scipy.ndimage import zoom
        noise_stretched = zoom(noise[:size//10, :], (10, 1), order=3)[:size, :size]
        mask = np.clip((noise_stretched - 0.3) * 2.0, 0, 1) 
        
        color1 = np.array([0.9, 0.9, 0.95])
        color2 = np.array([0.3, 0.5, 0.8])
        
        T = color1 * mask[..., None] + color2 * (1 - mask[..., None])
        h = 0.9 * mask + 0.05 * (1 - mask)
        
    elif recipe == 'wispy-white':
        noise = generate_noise(size, scale=150, seed=seed)
        mask = generate_noise(size, scale=50, seed=seed+1)
        wisp = np.clip((noise * mask) * 2.0, 0, 1)
        
        base_color = np.array([0.85, 0.87, 0.92])
        wisp_color = np.array([0.55, 0.55, 0.55])
        
        T = base_color * (1 - wisp[..., None]) + wisp_color * wisp[..., None]
        h = 0.5 + 0.45 * wisp
    else:
        raise ValueError(f"Unknown recipe: {recipe}")
        
    T_path = os.path.join(out_dir, "tex_T.png")
    h_path = os.path.join(out_dir, "tex_h.png")
    mark_path = os.path.join(out_dir, "tex_mark_mask.png")
    
    img_T = save_numpy_to_image(T, T_path, is_color=True)
    img_h = save_numpy_to_image(h, h_path, is_color=False)
    
    mark = generate_scribble_mask(size, seed+5)
    img_mark = save_numpy_to_image(mark, mark_path, is_color=False)
    
    return img_T, img_h, img_mark

def download_polyhaven_hdri(out_dir):
    """Downloads a small outdoor HDRI from polyhaven if not present."""
    import requests
    hdri_path = os.path.join(out_dir, "sunflowers_1k.hdr")
    if not os.path.exists(hdri_path):
        print("Downloading HDRI...")
        url = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/sunflowers_1k.hdr"
        r = requests.get(url)
        with open(hdri_path, 'wb') as f:
            f.write(r.content)
    return os.path.abspath(hdri_path)

# Realistic partial window-frame occluders (report review: the old full mullion
# cross was over-aggressive vs real captures -- a real handheld photo of a sheet
# near a window mostly shows a frame EDGE poking in from one border, not a
# symmetric cross covering the whole pane). Coordinates below are in the glass
# plane's local frame: after setup_scene's (90deg, 0, 0) rotation, local X maps
# 1:1 to world X and local Y maps 1:1 to world Z (world Y is depth/normal), so
# these bounds can be reasoned about as plain 2D image-plane coordinates.
#
# NOTE: the visible half-extent at the occluder's depth is NOT the glass
# plane's own half-size (0.25) -- the camera's default 50mm/36mm lens is
# actually narrower than that (the glass is deliberately oversized so it
# bleeds off all four edges, per the "no borders" comment below), and the
# horizontal/vertical FOV are not equal even for a square render. We must
# derive the true visible box from the camera's own FOV, or bars end up
# almost entirely outside frame (only a sliver of their corner visible).
FRAME_BORDERS = ['top', 'bottom', 'left', 'right']
OCCLUDER_Y = 0.01  # depth offset behind the glass (matches the old WindowFrame position)


def add_frame_occluders(cam):
    """Create 1-2 near-black bars hugging edge(s) of the frame, like a real
    photo of a sheet held near a window edge. Returns the occluder params
    (recorded into meta.json) so the dark-occluder-through-clear-glass trap
    stays auditable: these pixels must be visible in the photo but must NOT
    leak into the extracted T.

    `cam` must already be positioned/rotated (called after camera setup) so
    we can compute the true visible frustum box at the occluder's depth.
    """
    dist = abs(OCCLUDER_Y - cam.location.y)
    vis_half_x = dist * math.tan(cam.data.angle_x / 2.0)
    vis_half_z = dist * math.tan(cam.data.angle_y / 2.0)
    margin_x, margin_z = vis_half_x * 1.5, vis_half_z * 1.5  # bars run well past frame -> no floating inner edge

    # Mostly a single edge; occasionally two adjacent edges (a frame corner).
    n_borders = 1 if random.random() < 0.7 else 2
    borders = random.sample(FRAME_BORDERS, n_borders)

    params = []
    for i, border in enumerate(borders):
        reach_frac = random.uniform(0.08, 0.35)   # fraction of the visible half-extent
        jitter_frac = random.uniform(-0.04, 0.04)  # irregular inner edge, not perfectly flush
        darkness = random.uniform(0.005, 0.02)     # near-black, slightly varied

        if border in ('top', 'bottom'):
            thickness = max(0.005, (reach_frac + jitter_frac) * vis_half_z)
        else:
            thickness = max(0.005, (reach_frac + jitter_frac) * vis_half_x)

        lo_x, hi_x = -(vis_half_x + margin_x), (vis_half_x + margin_x)
        lo_z, hi_z = -(vis_half_z + margin_z), (vis_half_z + margin_z)
        if border == 'top':
            x0, x1 = lo_x, hi_x
            z0, z1 = vis_half_z - thickness, vis_half_z + margin_z
        elif border == 'bottom':
            x0, x1 = lo_x, hi_x
            z0, z1 = -(vis_half_z + margin_z), -(vis_half_z - thickness)
        elif border == 'left':
            x0, x1 = -(vis_half_x + margin_x), -(vis_half_x - thickness)
            z0, z1 = lo_z, hi_z
        else:  # right
            x0, x1 = vis_half_x - thickness, vis_half_x + margin_x
            z0, z1 = lo_z, hi_z

        cx, cz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
        bpy.ops.mesh.primitive_plane_add(size=1, location=(cx, OCCLUDER_Y, cz), rotation=(math.radians(90), 0, 0))
        bar = bpy.context.active_object
        bar.name = f"FrameOccluder_{border}"
        bar.scale = (x1 - x0, z1 - z0, 1.0)

        mat_frame = bpy.data.materials.new(name=f"FrameOccluderMat_{i}")
        mat_frame.use_nodes = True
        mat_frame.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (darkness, darkness, darkness, 1)
        bar.data.materials.append(mat_frame)

        params.append({"border": border, "thickness": round(thickness, 4),
                        "reach_frac": round(reach_frac, 4), "darkness": round(darkness, 4)})

    return params


def setup_scene(hdri_path, has_frame=False):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    # Try GPU, fallback to CPU
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL' # For Mac
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    scene.cycles.device = 'GPU' if prefs.has_active_device() else 'CPU'
    scene.cycles.max_bounces = 24
    scene.cycles.transparent_max_bounces = 24
    scene.cycles.transmission_bounces = 24
    scene.cycles.use_denoising = True
    scene.cycles.samples = 64 # Use low samples with OpenImageDenoise to speed up rendering
    
    # Standard view transform
    scene.view_settings.view_transform = 'Standard'
    
    scene.render.resolution_x = 1536
    scene.render.resolution_y = 1536
    scene.render.resolution_percentage = 100
    
    # Environment HDRI
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    wnodes = world.node_tree.nodes
    wlinks = world.node_tree.links
    wnodes.clear()
    
    if hdri_path is None:
        # Validate mode: clean transmission target. World is perfectly black.
        wout = wnodes.new('ShaderNodeOutputWorld')
        wbg = wnodes.new('ShaderNodeBackground')
        wbg.inputs['Color'].default_value = (0.0, 0.0, 0.0, 1.0)
        wbg.inputs['Strength'].default_value = 1.0
        wlinks.new(wbg.outputs['Background'], wout.inputs['Surface'])
        ev = 0.0
        z_rot = 0.0
        
        # Dedicated white emissive backlight behind the glass (+Y direction)
        bpy.ops.mesh.primitive_plane_add(size=50.0, location=(0, 2.0, 0), rotation=(math.radians(90), 0, 0))
        backlight = bpy.context.active_object
        backlight.name = "WhiteBacklight"
        mat_bl = bpy.data.materials.new(name="BacklightMat")
        mat_bl.use_nodes = True
        nodes_bl = mat_bl.node_tree.nodes
        links_bl = mat_bl.node_tree.links
        for n in nodes_bl: nodes_bl.remove(n)
        emission = nodes_bl.new('ShaderNodeEmission')
        emission.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
        emission.inputs['Strength'].default_value = 1.0
        out_bl = nodes_bl.new('ShaderNodeOutputMaterial')
        links_bl.new(emission.outputs['Emission'], out_bl.inputs['Surface'])
        backlight.data.materials.append(mat_bl)
    else:
        wout = wnodes.new('ShaderNodeOutputWorld')
        wbg = wnodes.new('ShaderNodeBackground')
        wtex = wnodes.new('ShaderNodeTexEnvironment')
        
        wtex.image = bpy.data.images.load(hdri_path)
        
        wmapping = wnodes.new('ShaderNodeMapping')
        wcoord = wnodes.new('ShaderNodeTexCoord')
        
        wlinks.new(wcoord.outputs['Generated'], wmapping.inputs['Vector'])
        wlinks.new(wmapping.outputs['Vector'], wtex.inputs['Vector'])
        wlinks.new(wtex.outputs['Color'], wbg.inputs['Color'])
        wlinks.new(wbg.outputs['Background'], wout.inputs['Surface'])
        
        # Randomize rotation and EV, tilt slightly so sky is visible
        wmapping.inputs['Rotation'].default_value[0] = random.uniform(math.radians(-5), math.radians(15))
        z_rot = random.uniform(0, math.pi * 2)
        wmapping.inputs['Rotation'].default_value[2] = z_rot
        ev = random.uniform(-1.5, 0.5) # Reduced max EV to prevent overexposure
        wbg.inputs['Strength'].default_value = 2.0 ** ev
    
    # Glass plane - size 0.5 ensures it completely fills the camera view (no borders)
    bpy.ops.mesh.primitive_plane_add(size=0.5, align='WORLD', location=(0, 0, 0), rotation=(math.radians(90), 0, 0))
    glass_obj = bpy.context.active_object
    glass_obj.name = "GlassSheet"

    # Camera - zoomed in so the glass perfectly fills the frame
    bpy.ops.object.camera_add(location=(0, -0.4, 0), rotation=(math.radians(90), 0, 0))
    cam = bpy.context.active_object
    scene.camera = cam

    # Randomize camera slightly
    cam.location.x += random.uniform(-0.02, 0.02)
    cam.location.z += random.uniform(-0.02, 0.02)
    cam.rotation_euler.x += random.uniform(-0.05, 0.05)
    cam.rotation_euler.z += random.uniform(-0.05, 0.05)

    frame_params = []
    if has_frame:
        # Partial window-frame edge(s) entering from the image border(s) --
        # see add_frame_occluders() above. Replaces the old full mullion cross.
        # Needs the camera (for its true FOV/frustum), so must run after it exists.
        frame_params = add_frame_occluders(cam)

    # Dark wall behind camera to block HDRI reflections on the front face (simulates dim interior)
    bpy.ops.mesh.primitive_plane_add(size=5.0, location=(0, -2.0, 0), rotation=(math.radians(90), 0, 0))
    wall = bpy.context.active_object
    wall.name = "DarkWall"
    mat_wall = bpy.data.materials.new(name="WallMat")
    mat_wall.use_nodes = True
    bsdf = mat_wall.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.00, 0.00, 0.00, 1)
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.0
    wall.data.materials.append(mat_wall)
    
    return glass_obj, cam, ev, z_rot, frame_params

def create_glass_material(glass_obj, img_T, img_h, img_mark, recipe, use_bump=True):
    mat = bpy.data.materials.new(name="GlassMat")
    
    # We must use nodes to set up the material
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    out_node = nodes.new('ShaderNodeOutputMaterial')
    
    tex_T = nodes.new('ShaderNodeTexImage')
    tex_T.image = img_T
    
    tex_h = nodes.new('ShaderNodeTexImage')
    tex_h.image = img_h
    
    tex_mark = nodes.new('ShaderNodeTexImage')
    tex_mark.image = img_mark
    
    # Physically-based glass using Principled BSDF
    principled = nodes.new('ShaderNodeBsdfPrincipled')
    principled.inputs['IOR'].default_value = 1.5
    
    if 'Transmission Weight' in principled.inputs:
        principled.inputs['Transmission Weight'].default_value = 1.0
    elif 'Transmission' in principled.inputs:
        principled.inputs['Transmission'].default_value = 1.0
        
    # Square the input texture so that Principled BSDF's internal sqrt (for thin glass) cancels out!
    # This ensures the transmitted physical light perfectly matches the gt_T map.
    math_node = nodes.new('ShaderNodeVectorMath')
    math_node.operation = 'MULTIPLY'
    links.new(tex_T.outputs['Color'], math_node.inputs[0])
    links.new(tex_T.outputs['Color'], math_node.inputs[1])
    
    # The transmittance color drives the Base Color
    links.new(math_node.outputs['Vector'], principled.inputs['Base Color'])
    
    # Haze drives the roughness of the transmission
    links.new(tex_h.outputs['Color'], principled.inputs['Roughness'])
    
    # Add grease pencil marks on top
    mark_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    mark_bsdf.inputs['Base Color'].default_value = (0.01, 0.01, 0.01, 1)
    mark_bsdf.inputs['Roughness'].default_value = 0.8
    
    mix_mark = nodes.new('ShaderNodeMixShader')
    links.new(tex_mark.outputs['Color'], mix_mark.inputs['Fac'])
    links.new(principled.outputs['BSDF'], mix_mark.inputs[1])
    links.new(mark_bsdf.outputs['BSDF'], mix_mark.inputs[2])
    
    links.new(mix_mark.outputs['Shader'], out_node.inputs['Surface'])
    
    # Hammered surface bump (affects glossy and translucent). Disabled
    # (use_bump=False) for the assembled-pair benchmark (report 014): its
    # procedural noise is evaluated in per-object space, so the relief would NOT
    # correspond between the flat-sheet capture and the 2x2 pieces cut from it --
    # and relief glints are lighting-dependent (a separate realism axis, like
    # shadows). Turning it off keeps the rendered appearance == the authored T,h
    # by construction, which is exactly what that benchmark's purity requires.
    if use_bump:
        noise_node = nodes.new('ShaderNodeTexNoise')
        noise_node.inputs['Scale'].default_value = 50.0
        bump_node = nodes.new('ShaderNodeBump')

        # Streaky glass is generally smoother/less bumpy
        if recipe == 'streaky-mix':
            bump_node.inputs['Distance'].default_value = random.uniform(0.0001, 0.0005)
        else:
            bump_node.inputs['Distance'].default_value = random.uniform(0.001, 0.004)

        links.new(noise_node.outputs['Fac'], bump_node.inputs['Height'])
        links.new(bump_node.outputs['Normal'], principled.inputs['Normal'])
    
    glass_obj.data.materials.append(mat)
    
    # Crucial: For Transparent BSDF to work in Cycles with a single plane, 
    # we don't need Solidify. Solidify makes it double-sided, squaring the transmittance.
    # So we remove Solidify completely.
    return mat

def generate_hand_mask(size=512):
    mask = np.zeros((size, size), dtype=np.float32)
    edge = random.choice(['top', 'bottom', 'left', 'right'])
    
    if edge == 'bottom':
        mask[470:512, 150:180] = 1.0 # Index
        mask[450:512, 200:230] = 1.0 # Middle
        mask[460:512, 250:280] = 1.0 # Ring
        mask[480:512, 300:330] = 1.0 # Pinky
    elif edge == 'top':
        mask[0:42, 150:180] = 1.0
        mask[0:62, 200:230] = 1.0
        mask[0:52, 250:280] = 1.0
        mask[0:32, 300:330] = 1.0
    elif edge == 'left':
        mask[150:180, 0:42] = 1.0
        mask[200:230, 0:62] = 1.0
        mask[250:280, 0:52] = 1.0
        mask[300:330, 0:32] = 1.0
    elif edge == 'right':
        mask[150:180, 470:512] = 1.0
        mask[200:230, 450:512] = 1.0
        mask[250:280, 460:512] = 1.0
        mask[300:330, 480:512] = 1.0
        
    # Blur heavily for soft shadow effect (reduced slightly to preserve thin finger shape)
    from scipy.ndimage import gaussian_filter
    mask = gaussian_filter(mask, sigma=10.0)
    return np.clip(mask, 0, 1)

def add_shadow_caster(out_dir):
    # Generate hand mask
    hand = generate_hand_mask()
    hand_path = os.path.join(out_dir, 'hand_mask.png')
    img_hand = save_numpy_to_image(hand, hand_path, is_color=False)
    
    # Create a plane for the shadow caster
    # Size 0.3 covers the entire 0.28m camera FOV
    # Place it at the camera's X/Z location so it perfectly aligns with the visible frame
    cam = bpy.context.scene.camera
    bpy.ops.mesh.primitive_plane_add(size=0.3, location=(cam.location.x, 0.05, cam.location.z), rotation=(math.radians(90), 0, 0))
    caster = bpy.context.active_object
    caster.name = "ShadowCaster"
    
    mat = bpy.data.materials.new(name="CasterMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    
    out_node = nodes.new('ShaderNodeOutputMaterial')
    
    tex_hand = nodes.new('ShaderNodeTexImage')
    tex_hand.image = img_hand
    
    # Diffuse BSDF (black) for the hand shadow
    diffuse = nodes.new('ShaderNodeBsdfDiffuse')
    diffuse.inputs['Color'].default_value = (0, 0, 0, 1)
    
    transp = nodes.new('ShaderNodeBsdfTransparent')
    
    mix = nodes.new('ShaderNodeMixShader')
    links.new(tex_hand.outputs['Color'], mix.inputs['Fac'])
    links.new(transp.outputs['BSDF'], mix.inputs[1])
    links.new(diffuse.outputs['BSDF'], mix.inputs[2])
    
    links.new(mix.outputs['Shader'], out_node.inputs['Surface'])
    
    # Cycles handles transparency automatically via node setup.
    
    caster.data.materials.append(mat)
    
    # Rotate slightly for interesting pose
    caster.rotation_euler.z += random.uniform(-0.5, 0.5)
    caster.rotation_euler.x += random.uniform(-0.1, 0.1)
    
    return caster

def render_ground_truths(glass_obj, sample_dir, img_T, img_h, img_mark):
    scene = bpy.context.scene
    
    # Hide the world background for ground truths (make it black)
    world = bpy.context.scene.world
    bg_node = world.node_tree.nodes.get('Background')
    if bg_node:
        orig_strength = bg_node.inputs['Strength'].default_value
        bg_node.inputs['Strength'].default_value = 0.0
        
    # Hide the dark wall if it exists
    wall = bpy.data.objects.get("DarkWall")
    if wall:
        wall.hide_render = True
        
    # Create emission material
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
    
    # Temporarily replace glass material
    orig_mat = glass_obj.data.materials[0]
    glass_obj.data.materials[0] = mat_gt
    
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_depth = '32'
    scene.view_settings.view_transform = 'Raw'
    
    # Emission shaders don't need many samples
    orig_samples = scene.cycles.samples
    scene.cycles.samples = 1
    
    # Render T (EXR)
    tex_node.image = img_T
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.filepath = os.path.join(sample_dir, "gt_T.exr")
    bpy.ops.render.render(write_still=True)
    
    # Render h (EXR)
    tex_node.image = img_h
    scene.render.image_settings.color_mode = 'BW'
    scene.render.filepath = os.path.join(sample_dir, "gt_h.exr")
    bpy.ops.render.render(write_still=True)
    
    # Render mark (EXR)
    tex_node.image = img_mark
    scene.render.image_settings.color_mode = 'BW'
    scene.render.filepath = os.path.join(sample_dir, "gt_mark_mask.exr")
    bpy.ops.render.render(write_still=True)
    
    # Render T (PNG for viz)
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_depth = '16'
    tex_node.image = img_T
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.filepath = os.path.join(sample_dir, "gt_T.png")
    bpy.ops.render.render(write_still=True)
    
    # Render h (PNG for viz)
    tex_node.image = img_h
    scene.render.image_settings.color_mode = 'BW'
    scene.render.filepath = os.path.join(sample_dir, "gt_h.png")
    bpy.ops.render.render(write_still=True)
    
    # Render mark (PNG for viz)
    tex_node.image = img_mark
    scene.render.image_settings.color_mode = 'BW'
    scene.render.filepath = os.path.join(sample_dir, "gt_mark_mask.png")
    bpy.ops.render.render(write_still=True)
    
    # Restore
    glass_obj.data.materials[0] = orig_mat
    scene.view_settings.view_transform = 'Standard'
    scene.cycles.samples = orig_samples
    if bg_node:
        bg_node.inputs['Strength'].default_value = orig_strength
    if wall:
        wall.hide_render = False

def render_sample(out_dir, prefix):
    scene = bpy.context.scene
    
    # Render once
    bpy.ops.render.render(write_still=False)
    img = bpy.data.images['Render Result']
    
    # Save sRGB PNG
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '8'
    img.save_render(os.path.abspath(os.path.join(out_dir, f"{prefix}photo.png")))
    
    # Save Linear EXR
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '32'
    img.save_render(os.path.abspath(os.path.join(out_dir, f"{prefix}photo_linear.exr")))

def parse_args():
    # Because blender consumes some arguments when run via `blender -b -P`, 
    # we filter them out if `--` is present. Otherwise, standard python execution.
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = sys.argv[1:]
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=str, required=True)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--count', type=int, default=1)
    parser.add_argument('--light-variations', type=int, default=3, help="Number of lighting variations per glass piece")
    parser.add_argument('--validate', action='store_true', help="Run in uniform backlight validation mode")
    parser.add_argument('--recipe', type=str, default=None,
                        help="Render only this recipe (targeted top-up, e.g. extra dark-opaque shadow-pair samples)")
    return parser.parse_args(argv)

def main():
    args = parse_args()
    
    recipes = ['cathedral-green', 'cathedral-amber', 'dark-opaque', 'streaky-mix', 'wispy-white']
    
    os.makedirs(args.out, exist_ok=True)
    hdri_path = download_polyhaven_hdri(args.out)
    
    # If count is exactly 5, generate one of each recipe. Otherwise, pick randomly.
    for i in range(args.count):
        seed = args.seed + i
        random.seed(seed)
        
        if args.recipe is not None:
            if args.recipe not in recipes:
                raise ValueError(f"Unknown recipe: {args.recipe}")
            recipe = args.recipe
        elif args.count == 5:
            recipe = recipes[i]
        else:
            recipe = random.choice(recipes)
            
        for v in range(args.light_variations):
            has_shadow = True # Always generate pairs (with and without shadow)
            has_frame = random.random() < 0.20  # partial frame-edge occluder trap (report 012)
            if args.validate:
                has_frame = False # No window mullions blocking transmission during math evaluation
                has_shadow = False # Skip shadow pass entirely during validation
            lighting_id = f"light{random.randint(0, 9999):04d}"

            # Name directory with seed so identical glass pieces are grouped together, but have different lighting IDs
            sample_dir = os.path.join(args.out, f"{recipe}__seed{seed}__{lighting_id}")
            os.makedirs(sample_dir, exist_ok=True)

            print(f"Generating {sample_dir}...")

            # 1. Setup scene FIRST (clears factory settings)
            if args.validate:
                glass_obj, cam, ev, z_rot, frame_params = setup_scene(None, has_frame=has_frame)
            else:
                glass_obj, cam, ev, z_rot, frame_params = setup_scene(hdri_path, has_frame=has_frame)
        
            # 2. Create textures
            img_T, img_h, img_mark = create_glass_textures(recipe, sample_dir, size=1536, seed=seed)
            
            # 3. Create material
            mat = create_glass_material(glass_obj, img_T, img_h, img_mark, recipe)
        
            metadata = {
                "glass_name": f"{recipe}_{seed}",
                "class_label": recipe,
                "hdri_name": "UniformWhite" if args.validate else os.path.basename(hdri_path),
                "hdri_rotation": z_rot,
                "hdri_ev": ev,
                "has_frame": has_frame,
                "frame_occluders": frame_params,
                "camera_pose": {
                    "location": list(cam.location),
                    "rotation": list(cam.rotation_euler)
                },
                "blender_version": bpy.app.version_string,
                "seed": seed,
                "has_shadow": has_shadow
            }
        
            if has_shadow:
                caster = add_shadow_caster(sample_dir)
                
                # Render with shadow
                metadata["shadow_mode"] = "with_shadow"
                render_sample(sample_dir, "with_shadow_")
                
                # Hide caster and render without
                caster.hide_render = True
                metadata["shadow_mode"] = "without_shadow"
                render_sample(sample_dir, "without_shadow_")
                
            else:
                metadata["shadow_mode"] = "none"
                render_sample(sample_dir, "without_shadow_")
                
            # Render aligned ground truths
            render_ground_truths(glass_obj, sample_dir, img_T, img_h, img_mark)
                
            with open(os.path.join(sample_dir, 'meta.json'), 'w') as f:
                json.dump(metadata, f, indent=2)

if __name__ == '__main__':
    main()
