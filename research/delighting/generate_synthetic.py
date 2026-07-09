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
    
    name = os.path.basename(filepath)
    if name in bpy.data.images:
        img = bpy.data.images[name]
    else:
        img = bpy.data.images.new(name, width=W, height=H, alpha=False, float_buffer=True)
        
    img.pixels.foreach_set(pixels)
    
    img.filepath_raw = filepath
    if filepath.endswith('.exr'):
        img.file_format = 'OPEN_EXR'
    else:
        img.file_format = 'PNG'
        
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
    return hdri_path

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
        # Validate mode: uniform white background
        wout = wnodes.new('ShaderNodeOutputWorld')
        wbg = wnodes.new('ShaderNodeBackground')
        wbg.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
        wbg.inputs['Strength'].default_value = 1.0
        wlinks.new(wbg.outputs['Background'], wout.inputs['Surface'])
        ev = 0.0
        z_rot = 0.0
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
    
    if has_frame:
        # Window Frame (mullions/crossbars)
        bpy.ops.mesh.primitive_grid_add(x_subdivisions=2, y_subdivisions=2, size=0.6, location=(0, 0.01, 0), rotation=(math.radians(90), 0, 0))
        frame_obj = bpy.context.active_object
        frame_obj.name = "WindowFrame"
        wire = frame_obj.modifiers.new(name="Wireframe", type='WIREFRAME')
        wire.thickness = 0.01
        
        mat_frame = bpy.data.materials.new(name="FrameMat")
        mat_frame.use_nodes = True
        mat_frame.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.01, 0.01, 0.01, 1)
        frame_obj.data.materials.append(mat_frame)
    
    # Camera - zoomed in so the glass perfectly fills the frame
    bpy.ops.object.camera_add(location=(0, -0.4, 0), rotation=(math.radians(90), 0, 0))
    cam = bpy.context.active_object
    scene.camera = cam
    
    # Randomize camera slightly
    cam.location.x += random.uniform(-0.02, 0.02)
    cam.location.z += random.uniform(-0.02, 0.02)
    cam.rotation_euler.x += random.uniform(-0.05, 0.05)
    cam.rotation_euler.z += random.uniform(-0.05, 0.05)
    
    # Dark wall behind camera to block HDRI reflections on the front face (simulates dim interior)
    bpy.ops.mesh.primitive_plane_add(size=5.0, location=(0, -2.0, 0), rotation=(math.radians(90), 0, 0))
    wall = bpy.context.active_object
    wall.name = "DarkWall"
    mat_wall = bpy.data.materials.new(name="WallMat")
    mat_wall.use_nodes = True
    mat_wall.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1)
    wall.data.materials.append(mat_wall)
    
    return glass_obj, cam, ev, z_rot

def create_glass_material(glass_obj, img_T, img_h, img_mark, recipe):
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
        
    # The transmittance color drives the Base Color
    links.new(tex_T.outputs['Color'], principled.inputs['Base Color'])
    
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
    
    # Hammered surface bump (affects glossy and translucent)
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
    
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_depth = '16'
    
    # Ground truth maps should be linear data without sRGB view transforms
    scene.view_settings.view_transform = 'Raw'
    
    # Render T
    tex_node.image = img_T
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.filepath = os.path.join(sample_dir, "gt_T.png")
    bpy.ops.render.render(write_still=True)
    
    # Render h
    tex_node.image = img_h
    scene.render.image_settings.color_mode = 'BW'
    scene.render.filepath = os.path.join(sample_dir, "gt_h.png")
    bpy.ops.render.render(write_still=True)
    
    # Render mark
    tex_node.image = img_mark
    scene.render.image_settings.color_mode = 'BW'
    scene.render.filepath = os.path.join(sample_dir, "gt_mark_mask.png")
    bpy.ops.render.render(write_still=True)
    
    # Restore
    glass_obj.data.materials[0] = orig_mat
    scene.view_settings.view_transform = 'Standard'
    if bg_node:
        bg_node.inputs['Strength'].default_value = orig_strength
    if wall:
        wall.hide_render = False

def render_sample(out_dir, prefix):
    scene = bpy.context.scene
    
    # Render sRGB
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '8'
    scene.render.filepath = os.path.join(out_dir, f"{prefix}photo.png")
    bpy.ops.render.render(write_still=True)
    
    # Render EXR
    scene.render.image_settings.file_format = 'OPEN_EXR'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '32'
    scene.render.filepath = os.path.join(out_dir, f"{prefix}photo_linear.exr")
    bpy.ops.render.render(write_still=True)

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
        
        if args.count == 5:
            recipe = recipes[i]
        else:
            recipe = random.choice(recipes)
            
        for v in range(args.light_variations):
            has_shadow = True # Always generate pairs (with and without shadow)
            has_frame = random.random() < 0.33
            lighting_id = f"light{random.randint(0, 9999):04d}"
            
            # Name directory with seed so identical glass pieces are grouped together, but have different lighting IDs
            sample_dir = os.path.join(args.out, f"{recipe}__seed{seed}__{lighting_id}")
            os.makedirs(sample_dir, exist_ok=True)
        
            print(f"Generating {sample_dir}...")
            
            # 1. Setup scene FIRST (clears factory settings)
            if args.validate:
                glass_obj, cam, ev, z_rot = setup_scene(None, has_frame=has_frame)
            else:
                glass_obj, cam, ev, z_rot = setup_scene(hdri_path, has_frame=has_frame)
        
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
                render_sample(sample_dir, "")
                
            # Render aligned ground truths
            render_ground_truths(glass_obj, sample_dir, img_T, img_h, img_mark)
                
            with open(os.path.join(sample_dir, 'meta.json'), 'w') as f:
                json.dump(metadata, f, indent=2)

if __name__ == '__main__':
    main()
