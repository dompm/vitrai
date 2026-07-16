"""Assemble the 047 comparison boards as downscaled labelled JPEGs."""
import os, json, numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', 'results', '047'))
REN = os.path.join(ROOT, 'renders'); MODEL = '/tmp/r047'; OUT = ROOT
P = 260  # panel px
try: FONT = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 15); FB = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 13)
except Exception: FONT = FB = ImageFont.load_default()

def truth(fam, scene, az): return os.path.join(REN, fam, scene, f'truth_az{az}.png')
def model(fam, scene, mode, az): return os.path.join(MODEL, f'{fam}_{scene}_{mode}_az{az}.png')

def panel(path, label, sub=None):
    im = Image.open(path).convert('RGB').resize((P, P), Image.LANCZOS)
    bar = 24 + (16 if sub else 0)
    c = Image.new('RGB', (P, P + bar), (20, 22, 26)); c.paste(im, (0, 0))
    d = ImageDraw.Draw(c); d.text((6, P + 3), label, font=FONT, fill=(235, 238, 242))
    if sub: d.text((6, P + 21), sub, font=FB, fill=(150, 200, 255))
    return c

def diffpanel(a, b, label):
    ta = np.asarray(Image.open(a).convert('RGB').resize((P, P), Image.LANCZOS), np.float32)
    tb = np.asarray(Image.open(b).convert('RGB').resize((P, P), Image.LANCZOS), np.float32)
    d = np.clip(np.abs(ta - tb).mean(2) * 4, 0, 255)
    img = np.stack([np.clip(d*1.4,0,255), np.clip((d-60)*1.6,0,255), np.clip(d*0.6,0,255)], -1).astype(np.uint8)
    c = Image.new('RGB', (P, P + 24), (20, 22, 26)); c.paste(Image.fromarray(img), (0, 0))
    ImageDraw.Draw(c).text((6, P + 3), label, font=FONT, fill=(235, 238, 242))
    return c

def grid(rows, path, title=None):
    w = max(sum(p.width for p in r) + 6*(len(r)-1) for r in rows)
    hh = sum(max(p.height for p in r) for r in rows) + 6*(len(rows)-1)
    top = 30 if title else 0
    canvas = Image.new('RGB', (w, hh+top), (12, 13, 15))
    if title: ImageDraw.Draw(canvas).text((8, 8), title, font=FONT, fill=(240,242,246))
    y = top
    for r in rows:
        x = 0; rh = max(p.height for p in r)
        for p in r: canvas.paste(p, (x, y)); x += p.width + 6
        y += rh + 6
    canvas.save(path, quality=88); print('wrote', path, canvas.size)

def M(fam,scene,mode,az): return json.load(open(os.path.join(ROOT, f'metrics_{fam}_{scene}.json')))[f'az{az}'][mode]

# 1. window-nudge fidelity: cathedral rows over angles
rows = []
for az in (0, 15, 30):
    t = truth('cathedral-green','flat',az)
    f = model('cathedral-green','flat','full',az); n = model('cathedral-green','flat','no_normal',az)
    mf, mn = M('cathedral-green','flat','full',az), M('cathedral-green','flat','no_normal',az)
    rows.append([panel(t, f'TRUTH (Cycles) az{az}'),
                 panel(f, 'three.js FULL', f"MAE {mf['mae']} SSIM {mf['ssim']}"),
                 panel(n, 'three.js no-Normal', f"MAE {mn['mae']} SSIM {mn['ssim']}"),
                 diffpanel(t, f, 'diff x4 (FULL)')])
grid(rows, os.path.join(OUT,'board_window_fidelity.jpg'),
     'Window-nudge fidelity - cathedral-green (worst family): three.js MeshPhysicalMaterial vs Cycles volumetric slab')

# 2. map-set ablation across families (az0)
rows = []
for fam in ('cathedral-green','streaky-mix','wispy-white'):
    t = truth(fam,'flat',0)
    cols = [panel(t, f'TRUTH {fam}')]
    for mode,lab in (('no_tint','- Tint'),('no_haze','- Haze'),('const_atten','const tint'),('full','FULL {T,haze,N}')):
        try:
            mm = M(fam,'flat',mode,0); cols.append(panel(model(fam,'flat',mode,0), lab, f"MAE {mm['mae']}"))
        except Exception: pass
    rows.append(cols)
grid(rows, os.path.join(OUT,'board_mapset.jpg'),
     'Map-set ablation (az0): drop one map. Tint is decisive everywhere; Haze matters for scatter (streaky/wispy), not clear cathedral.')

# 3. normal-map grain vs smooth relief (cathedral az0)
t = truth('cathedral-green','flat',0)
grid([[panel(t,'TRUTH: smooth relief'),
       panel(model('cathedral-green','flat','full',0),'+ Normal map','high-freq sparkle'),
       panel(model('cathedral-green','flat','no_normal',0),'no Normal','smooth, closer'),
       diffpanel(t, model('cathedral-green','flat','full',0),'diff FULL'),
       diffpanel(t, model('cathedral-green','flat','no_normal',0),'diff no-Normal')]],
     os.path.join(OUT,'board_normal_grain.jpg'),
     'Normal map adds high-frequency grain, not Cycles smooth relief lensing -> hurts the match (SSIM drops)')

# 4. lamp limitation
lt = truth('cathedral-green','lamp',0)
cols = [panel(lt,'TRUTH lamp (Cycles)','interior-lit green glow')]
for g,lab in ((0,'three.js transmission'),):
    p = os.path.join(MODEL, f'cg_lamp_glow{g}.png')
    if os.path.exists(p): cols.append(panel(p, lab, 'dark shell - glow not carried'))
p = os.path.join(MODEL,'cg_lamp_glow0.8.png')
if os.path.exists(p): cols.append(panel(p,'+ emissive glow hack','uniform, still wrong'))
cols.append(diffpanel(lt, os.path.join(MODEL,'cg_lamp_glow0.png'),'diff'))
grid([cols], os.path.join(OUT,'board_lamp.jpg'),
     'Lamp: screen-space transmission cannot carry the interior glow through the curved wall (naive emissive over-brightens)')

# 5. glassiness under orbit (model, glints slide)
cols = [panel(model('cathedral-green','flat','full',az), f'orbit az{az}') for az in (0,10,15,30)]
grid([cols], os.path.join(OUT,'board_orbit_glints.jpg'),
     'Window-nudge in three.js: IBL glints + backdrop parallax slide with the orbit (the reborn front veil) - the delight cue')
print('done')
