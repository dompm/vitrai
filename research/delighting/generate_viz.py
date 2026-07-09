import os
import json
import base64
import argparse

def get_base64_img(filepath):
    if not os.path.exists(filepath):
        return None
    with open(filepath, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return f"data:image/png;base64,{encoded_string}"

def generate_html(data_dir):
    samples = []
    
    # Iterate through all subdirectories in the data directory
    for item in sorted(os.listdir(data_dir)):
        item_path = os.path.join(data_dir, item)
        if os.path.isdir(item_path):
            meta_path = os.path.join(item_path, 'meta.json')
            if os.path.exists(meta_path):
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                
                # Depending on whether there are shadow pairs, we might have multiple renders
                if meta.get("has_shadow"):
                    photo_path = os.path.join(item_path, 'with_shadow_photo.png')
                else:
                    photo_path = os.path.join(item_path, 'photo.png')
                    
                T_path = os.path.join(item_path, 'gt_T.png')
                h_path = os.path.join(item_path, 'gt_h.png')
                mark_path = os.path.join(item_path, 'gt_mark_mask.png')
                
                samples.append({
                    "id": item,
                    "meta": meta,
                    "photo": get_base64_img(photo_path),
                    "T": get_base64_img(T_path),
                    "h": get_base64_img(h_path),
                    "mark": get_base64_img(mark_path)
                })

    # HTML Template
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Synthetic Glass Data Visualizer</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #111; color: #eee; margin: 0; padding: 20px; }
            h1 { text-align: center; color: #fff; }
            .grid { display: flex; flex-direction: column; gap: 40px; max-width: 1400px; margin: 0 auto; }
            .sample { background: #222; border-radius: 8px; padding: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); }
            .sample-header { display: flex; justify-content: space-between; margin-bottom: 15px; border-bottom: 1px solid #444; padding-bottom: 10px; }
            .sample-title { font-size: 1.2em; font-weight: bold; }
            .images { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 20px; }
            .img-container { display: flex; flex-direction: column; align-items: center; text-align: center; }
            .img-container span { margin-bottom: 8px; font-weight: 500; color: #aaa; font-size: 0.9em; }
            img { max-width: 100%; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.8); background: #000; aspect-ratio: 1/1; object-fit: contain; }
            .meta-info { font-size: 0.85em; color: #888; margin-top: 15px; background: #1a1a1a; padding: 10px; border-radius: 4px; white-space: pre-wrap; font-family: monospace; }
        </style>
    </head>
    <body>
        <h1>Synthetic Glass Data Visualizer</h1>
        <div class="grid">
    """
    
    for sample in samples:
        mark_html = ""
        if sample['mark']:
            mark_html = f"""
                    <div class="img-container">
                        <span>Ground Truth: Marks (mask)</span>
                        <img src="{sample['mark']}" alt="mark mask">
                    </div>
            """
            
        html_content += f"""
            <div class="sample">
                <div class="sample-header">
                    <div class="sample-title">{sample['id']}</div>
                    <div>Recipe: {sample['meta'].get('class_label', 'N/A')}</div>
                </div>
                <div class="images">
                    <div class="img-container">
                        <span>Photo (sRGB)</span>
                        <img src="{sample['photo']}" alt="Photo">
                    </div>
                    <div class="img-container">
                        <span>Ground Truth: Transmittance (T)</span>
                        <img src="{sample['T']}" alt="T map">
                    </div>
                    <div class="img-container">
                        <span>Ground Truth: Haze (h)</span>
                        <img src="{sample['h']}" alt="h map">
                    </div>
                    {mark_html}
                </div>
                <div class="meta-info">{json.dumps(sample['meta'], indent=2)}</div>
            </div>
        """
        
    html_content += """
        </div>
    </body>
    </html>
    """
    
    out_path = os.path.join(data_dir, "viz.html")
    with open(out_path, "w") as f:
        f.write(html_content)
    
    print(f"Visualization generated at: {out_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', type=str, required=True, help="Path to the synthetic data output directory")
    args = parser.parse_args()
    
    generate_html(args.dir)
