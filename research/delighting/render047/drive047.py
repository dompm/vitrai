"""047 driver: render the three.js model across the ablation matrix (headless
Chrome), compare each to the Cycles truth, emit metrics + boards.

Modes (flat): full, no_normal (drop normalMap -> tests whether normal-mapped
screen-space refraction recovers relief), no_haze (roughness->0), no_tint
(white base), const_atten (per-pixel T replaced by one constant attenuationColor
-> shows why per-pixel is needed), surface_only (no normal + roughness 0).

Run: <venv>/python drive047.py --family cathedral-green --scene flat \
        --truthdir results/047/renders --out results/047 --port 8047 --size 512
Assumes serve047.py is already serving on --port with OUT=--modelpng dir.
"""
import subprocess, os, sys, time, json, argparse, urllib.request
from compare047 import metrics, diff_img, hcat, load
from PIL import Image
import numpy as np

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HERE = os.path.dirname(os.path.abspath(__file__))
MODES_FLAT = ['full', 'no_normal', 'no_haze', 'no_tint', 'const_atten', 'surface_only']
MODES_LAMP = ['full', 'no_normal', 'no_tint']

def render_model(port, modeldir, family, scene, az, mode, meta, meanT, nscale, size, tag):
    name = f'{family}_{scene}_{mode}_az{int(az)}{tag}'
    outpng = os.path.join(modeldir, name + '.png')
    if os.path.exists(outpng): os.remove(outpng)
    q = (f'family={family}&scene={scene}&mode={mode}&az={az}&fov={meta["fov_deg"]}'
         f'&dist={meta["dist"]}&elev={meta["elev_deg"]}&res={size}&dslab={meta["d_slab_m"]}'
         f'&nscale={nscale}&meanT={meanT[0]},{meanT[1]},{meanT[2]}&name={name}')
    if scene == 'lamp':
        L = meta['lamp']; q = (f'family={family}&scene=lamp&mode={mode}&az={az}&fov={L["fov"]}'
             f'&dist={L["dist"]}&elev={meta["elev_deg"]}&res={size}&dslab={meta["d_slab_m"]}'
             f'&nscale={nscale}&meanT={meanT[0]},{meanT[1]},{meanT[2]}&name={name}')
    url = f'http://localhost:{port}/render047/render047_model.html?{q}'
    subprocess.run([CHROME, '--headless=new', f'--window-size={size},{size}',
                    '--force-device-scale-factor=1', '--virtual-time-budget=30000',
                    '--screenshot=/tmp/_s047.png', url],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
    for _ in range(40):
        if os.path.exists(outpng) and os.path.getsize(outpng) > 0: return outpng
        time.sleep(0.25)
    raise RuntimeError('model render failed: ' + name)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--family', required=True); ap.add_argument('--scene', default='flat')
    ap.add_argument('--truthdir', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--modelpng', default='/tmp/r047'); ap.add_argument('--port', default='8047')
    ap.add_argument('--size', type=int, default=512); ap.add_argument('--nscale', type=float, default=1.0)
    a = ap.parse_args()
    tdir = os.path.join(a.truthdir, a.family, a.scene)
    meta = json.load(open(os.path.join(tdir, 'scene_meta.json')))
    fam = json.load(open(os.path.join(a.out, 'assets', 'families.json')))
    meanT = fam[a.family]['T_mean']
    modes = MODES_FLAT if a.scene == 'flat' else MODES_LAMP
    results = {}
    boarddir = os.path.join(a.out, 'boards'); os.makedirs(boarddir, exist_ok=True)
    for az in meta['angles']:
        truth = os.path.join(tdir, f'truth_az{int(az)}.png')
        row = {}
        model_imgs = {}
        for mode in modes:
            mp = render_model(a.port, a.modelpng, a.family, a.scene, az, mode, meta, meanT, a.nscale, a.size, '')
            mt, t, m = metrics(truth, mp, a.size)
            row[mode] = mt; model_imgs[mode] = m
            print(f'{a.family} {a.scene} az{int(az)} {mode}: MAE {mt["mae"]} SSIM {mt["ssim"]}', flush=True)
        results[f'az{int(az)}'] = row
        # board: truth | full | no_normal | diff(full) | diff(no_normal)
        t = load(truth, a.size)
        strip = [t, model_imgs['full'], model_imgs.get('no_normal', model_imgs['full']),
                 diff_img(t, model_imgs['full']), diff_img(t, model_imgs.get('no_normal', model_imgs['full']))]
        Image.fromarray(hcat(strip)).save(os.path.join(boarddir, f'{a.family}_{a.scene}_az{int(az)}.png'))
    outj = os.path.join(a.out, f'metrics_{a.family}_{a.scene}.json')
    json.dump(results, open(outj, 'w'), indent=2)
    print('WROTE', outj)

if __name__ == '__main__':
    main()
