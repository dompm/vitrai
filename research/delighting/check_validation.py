import os
import cv2
import numpy as np

# Enable EXR reading in OpenCV
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"

def main():
    root_dir = "validate_data"
    if not os.path.exists(root_dir):
        print(f"Error: {root_dir} not found.")
        return
        
    recipes = {}
    total_samples = 0
    
    for entry in os.listdir(root_dir):
        sample_dir = os.path.join(root_dir, entry)
        if not os.path.isdir(sample_dir):
            continue
            
        exr_path = os.path.join(sample_dir, "without_shadow_photo_linear.exr")
        gt_path = os.path.join(sample_dir, "gt_T.exr")
        
        if not os.path.exists(exr_path) or not os.path.exists(gt_path):
            continue
            
        exr = cv2.imread(exr_path, cv2.IMREAD_UNCHANGED)
        gt = cv2.imread(gt_path, cv2.IMREAD_UNCHANGED)
        
        if exr is None or gt is None:
            print(f"Failed to read images in {sample_dir}")
            continue
            
        # In case there's an alpha channel, keep only RGB
        if exr.shape[2] == 4:
            exr = exr[..., :3]
        if gt.shape[2] == 4:
            gt = gt[..., :3]
            
        gt_float = gt.astype(np.float32)
        
        # OpenCV reads in BGR format, but since we are computing absolute difference across all channels,
        # the channel order doesn't matter as long as they match. Both are rendered from Blender, 
        # so they will both be loaded as BGR.
        
        # Ensure we only compare the RGB/BGR channels (discard alpha if present)
        exr_rgb = exr[..., :3]
        gt_rgb = gt_float[..., :3]
        
        # Compute Mean Absolute Error for this sample
        diff = np.abs(exr_rgb - gt_rgb)
        mae = diff.mean()
        
        # Extract recipe name from directory (e.g. cathedral-green__seed42__light0000 -> cathedral-green)
        recipe = entry.split("__")[0]
        if recipe not in recipes:
            recipes[recipe] = []
        recipes[recipe].append(mae)
        total_samples += 1

    print("========================================")
    print(f"Validation Results: Uniform-Backlight T-Agreement")
    print(f"Total evaluated samples: {total_samples}")
    print("========================================")
    for r, maes in recipes.items():
        print(f"{r}: MAE = {np.mean(maes):.6f}")

if __name__ == '__main__':
    main()
