"""Inline render047_proto.html + vendored three.js + assets into ONE
self-contained HTML (no external/CDN fetches): three.js bundled as data: URI
ES-modules (MIT, license header preserved), env.hdr + map textures as data:
URIs injected via window.__AMAP__.  Maps downscaled to keep the artifact light.
"""
import os, base64, io, json
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.abspath(os.path.join(HERE, '..', 'results', '047', 'assets'))
OUT = os.path.abspath(os.path.join(HERE, '..', 'results', '047', 'proto047_volumetric_glass.html'))
FAMILIES = ['cathedral-green', 'wispy-white', 'streaky-mix']
MAP_SIZE = 512   # downscale textures for the embedded artifact

def b64(data): return base64.b64encode(data).decode()
def js_datauri(src): return 'data:text/javascript;base64,' + b64(src.encode())
def png_datauri(path, size=None):
    im = Image.open(path)
    if size: im = im.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, 'PNG'); return 'data:image/png;base64,' + b64(buf.getvalue())
def hdr_datauri(path):
    return 'data:application/octet-stream;base64,' + b64(open(path, 'rb').read())

def main():
    core = open(os.path.join(HERE, 'vendor', 'three.core.min.js')).read()
    module = open(os.path.join(HERE, 'vendor', 'three.module.min.js')).read().replace(
        './three.core.min.js', 'three-core')
    hdr = open(os.path.join(HERE, 'vendor', 'HDRLoader.js')).read()
    importmap = {'imports': {
        'three-core': js_datauri(core),
        'three': js_datauri(module),
        'hdrloader': js_datauri(hdr),
    }}
    amap = {'env.hdr': hdr_datauri(os.path.join(ASSETS, 'env.hdr')),
            'backdrop.png': png_datauri(os.path.join(ASSETS, 'backdrop.png'), MAP_SIZE)}
    for f in FAMILIES:
        for m in ('tint', 'haze', 'normal'):
            amap[f'{f}/{m}.png'] = png_datauri(os.path.join(ASSETS, f, f'{m}.png'), MAP_SIZE)
    scale = float(open(os.path.join(ASSETS, 'backdrop_scale.txt')).read())

    html = open(os.path.join(HERE, 'render047_proto.html')).read()
    # swap importmap
    import re
    html = re.sub(r'<script type="importmap">.*?</script>',
                  '<script type="importmap">' + json.dumps(importmap) + '</script>',
                  html, flags=re.S)
    html = html.replace("import { HDRLoader } from '/render047/vendor/HDRLoader.js';",
                        "import { HDRLoader } from 'hdrloader';")
    inject = ('<script>window.__AMAP__=' + json.dumps(amap) +
              ';window.__SCALE__=' + str(scale) + ';</script>\n')
    html = html.replace('</head>', inject + '</head>')
    open(OUT, 'w').write(html)
    print(f'wrote {OUT}  ({len(html)/1e6:.1f} MB)')

if __name__ == '__main__':
    main()
