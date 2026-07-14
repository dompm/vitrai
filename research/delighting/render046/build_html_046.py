"""046 -- assemble the self-contained WebGL2 prototype (render046.html) from the
exported per-family assets. No external deps: the assets JSON (base64 PNG
data-URIs) is inlined into a <script> tag, all CSS/JS inline. Complete standalone
document -- open directly in a browser, or publish as an Artifact.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "results", "046", "webgl_assets.json")
OUT = os.path.join(HERE, "..", "results", "046", "render046.html")

VERT = """#version 300 es
in vec2 aPos;
out vec2 vUv;
void main(){ vUv = aPos*0.5+0.5; gl_Position = vec4(aPos,0.0,1.0); }
"""

FRAG = """#version 300 es
precision highp float;
in vec2 vUv;
out vec4 frag;
uniform sampler2D uB, uT, uH, uN, uTruth;
uniform float uSigmaScale, uTexRes, uRefrGain;
uniform bool uScatter, uRefract, uVeil;
uniform int uView;            // 0 render, 1 truth, 2 diff(x3)
uniform vec2 uNormalMedian;

vec3 s2l(vec3 c){ return mix(c/12.92, pow((c+0.055)/1.055, vec3(2.4)), step(vec3(0.04045),c)); }
vec3 l2s(vec3 c){ c=clamp(c,0.0,1.0); return mix(c*12.92, 1.055*pow(c,vec3(1.0/2.4))-0.055, step(vec3(0.0031308),c)); }

void main(){
  vec2 uv = vUv;
  vec2 grabUv = uv;
  if(uRefract){
    vec3 n = texture(uN, uv).rgb*2.0 - 1.0;            // decode normal
    float nz = max(abs(n.z), 1e-3);
    vec2 tilt = n.xy/nz - uNormalMedian;               // isolate relief tilt
    vec2 offPx = tilt*(1.0-1.0/1.5)*uRefrGain;         // single-interface Snell, 1024-px
    grabUv += offPx/1024.0;                            // -> uv offset
  }
  float h = texture(uH, uv).r;
  // uB/uT are SRGB8_ALPHA8 textures: the sampler auto-decodes to LINEAR and,
  // crucially, generateMipmap averages in LINEAR space -- so the mip-scatter
  // blurs light physically (matching Cycles + the numpy ceiling), not in the
  // gamma-compressed byte space a plain RGBA8 grab would.
  vec3 B;
  if(uScatter){
    float sigma = uSigmaScale*h*(uTexRes/1024.0);      // px at texture res
    float lod = clamp(log2(max(sigma,1.0)), 0.0, log2(uTexRes));
    B = textureLod(uB, grabUv, lod).rgb;               // roughness-mip scatter
  } else {
    B = texture(uB, grabUv).rgb;
  }
  vec3 T = texture(uT, uv).rgb;
  vec3 L = T*B;                                         // Beer-Lambert tint
  if(uVeil){                                            // front-lit only; 0 in backlit truth
    float fres = pow(1.0 - abs(texture(uN,uv).b*2.0-1.0), 5.0);
    L += vec3(0.06)*fres;
  }
  vec3 outc = l2s(L);
  if(uView==1){ outc = texture(uTruth, uv).rgb; }
  else if(uView==2){ vec3 t=texture(uTruth,uv).rgb; outc = clamp(abs(outc-t)*3.0,0.0,1.0); }
  frag = vec4(outc, 1.0);
}
"""

CSS = """
:root{ --bg:#f6f7f9; --panel:#fff; --ink:#14171c; --sub:#5b6473; --line:#e3e7ec;
  --accent:#3b6ef0; --good:#1a9e6a; --warn:#c26a12; --bad:#c23a3a; --chip:#eef1f6; }
:root[data-theme=dark], @media (prefers-color-scheme:dark){ }
@media (prefers-color-scheme:dark){ :root{ --bg:#0f1216; --panel:#171b21; --ink:#e8ebef;
  --sub:#9aa4b2; --line:#262c34; --accent:#5b8cff; --chip:#1e242c; } }
:root[data-theme=dark]{ --bg:#0f1216; --panel:#171b21; --ink:#e8ebef; --sub:#9aa4b2;
  --line:#262c34; --accent:#5b8cff; --chip:#1e242c; }
:root[data-theme=light]{ --bg:#f6f7f9; --panel:#fff; --ink:#14171c; --sub:#5b6473;
  --line:#e3e7ec; --accent:#3b6ef0; --chip:#eef1f6; }
*{ box-sizing:border-box; }
body{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.5 -apple-system,
  BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
.wrap{ max-width:1120px; margin:0 auto; padding:24px 20px 60px; }
h1{ font-size:20px; margin:0 0 4px; letter-spacing:-0.01em; }
.lede{ color:var(--sub); margin:0 0 20px; max-width:75ch; }
.lede b{ color:var(--ink); }
.controls{ display:flex; flex-wrap:wrap; gap:16px 24px; align-items:flex-end;
  background:var(--panel); border:1px solid var(--line); border-radius:12px;
  padding:16px 18px; margin-bottom:20px; }
.ctl{ display:flex; flex-direction:column; gap:6px; }
.ctl label{ font-size:11px; text-transform:uppercase; letter-spacing:0.06em; color:var(--sub); }
select{ font:inherit; padding:7px 10px; border-radius:8px; border:1px solid var(--line);
  background:var(--chip); color:var(--ink); min-width:210px; }
.toggles{ display:flex; gap:8px; flex-wrap:wrap; }
.tg{ display:inline-flex; align-items:center; gap:7px; padding:7px 11px; border-radius:8px;
  border:1px solid var(--line); background:var(--chip); cursor:pointer; user-select:none; }
.tg input{ accent-color:var(--accent); margin:0; }
.slider{ display:flex; align-items:center; gap:10px; min-width:260px; }
input[type=range]{ width:180px; accent-color:var(--accent); }
.sval{ font-variant-numeric:tabular-nums; color:var(--sub); min-width:74px; }
.panels{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
.panel{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
  overflow:hidden; }
.panel .cap{ display:flex; justify-content:space-between; align-items:baseline;
  padding:10px 12px 8px; }
.panel .cap .t{ font-weight:600; font-size:13px; }
.panel .cap .m{ font-variant-numeric:tabular-nums; font-size:12px; color:var(--sub); }
.panel canvas, .panel img{ display:block; width:100%; height:auto; aspect-ratio:1;
  image-rendering:auto; background:#888; }
.metrics{ display:flex; gap:10px; flex-wrap:wrap; margin:18px 0 6px; }
.stat{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
  padding:10px 14px; min-width:120px; }
.stat .k{ font-size:11px; text-transform:uppercase; letter-spacing:0.06em; color:var(--sub); }
.stat .v{ font-size:20px; font-weight:650; font-variant-numeric:tabular-nums; margin-top:2px; }
.stat .v small{ font-size:12px; color:var(--sub); font-weight:500; }
.note{ color:var(--sub); font-size:12.5px; margin-top:14px; max-width:80ch; }
.badge{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px;
  font-weight:600; }
.b-good{ background:rgba(26,158,106,.15); color:var(--good); }
.b-hard{ background:rgba(194,106,18,.16); color:var(--warn); }
@media (max-width:720px){ .panels{ grid-template-columns:1fr; } }
"""

HTML_TMPL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Glass browser-render ceiling (046)</title>
<style>__CSS__</style>
</head>
<body>
<div class="wrap">
  <h1>In-browser glass render vs Cycles path-traced truth &middot; report 046</h1>
  <p class="lede">A cheap, deployable <b>screen-space transmission shader</b> (grab the
  backdrop &rarr; GPU mip-pyramid roughness-blur driven by haze &sigma;<sub>s</sub>&prop;h
  &rarr; tint by transmittance T), fed the <b>ground-truth material maps</b>, rendered live
  in WebGL2. Compare it to the Cycles path-traced truth. This is the same technique as
  three.js <code>MeshPhysicalMaterial</code> (transmission / roughness / attenuation) &mdash;
  no path tracing. Numbers are 8-bit sRGB MAE, computed live in-page at 256&sup2;.</p>

  <div class="controls">
    <div class="ctl">
      <label for="fam">Glass family</label>
      <select id="fam"></select>
    </div>
    <div class="ctl">
      <label>Shader terms</label>
      <div class="toggles">
        <label class="tg"><input type="checkbox" id="tScatter" checked> &sigma;<sub>s</sub> scatter</label>
        <label class="tg"><input type="checkbox" id="tRefract"> relief refraction</label>
        <label class="tg"><input type="checkbox" id="tVeil"> front veil</label>
      </div>
    </div>
    <div class="ctl">
      <label for="sig">&sigma;<sub>s</sub> scale <span id="sigfit"></span></label>
      <div class="slider">
        <input type="range" id="sig" min="0" max="1024" step="1">
        <span class="sval" id="sigv"></span>
      </div>
    </div>
  </div>

  <div class="metrics">
    <div class="stat"><div class="k">Browser MAE (live)</div><div class="v" id="mBrowser">&ndash;</div></div>
    <div class="stat"><div class="k">Numpy ceiling (1024&sup2;)</div><div class="v" id="mCeiling">&ndash;</div></div>
    <div class="stat"><div class="k">Oracle 045 ideal Gaussian</div><div class="v" id="mOracle">&ndash;</div></div>
    <div class="stat"><div class="k">Verdict</div><div class="v" id="mVerdict">&ndash;</div></div>
  </div>

  <div class="panels">
    <div class="panel"><div class="cap"><span class="t">Cycles truth</span><span class="m">path-traced</span></div><img id="imgTruth" alt="Cycles truth"></div>
    <div class="panel"><div class="cap"><span class="t">Browser shader</span><span class="m" id="capB">MAE &ndash;</span></div><canvas id="glc" width="256" height="256"></canvas></div>
    <div class="panel"><div class="cap"><span class="t">Diff &times;3</span><span class="m">|render &minus; truth|</span></div><canvas id="dc" width="256" height="256"></canvas></div>
  </div>

  <p class="note" id="famnote"></p>
  <p class="note">Rigorous ceiling is measured in numpy at 1024&sup2; against the same maps and is
  byte-identical in metric to oracle 045; this interactive prototype runs at 256&sup2; for embed
  size, so its live MAE tracks the ceiling closely but not exactly. Refraction and veil are
  toggles: oracle 045 found relief-refraction marginal (&lt;0.15 MAE) and the front veil
  identically zero in a backlit rig &mdash; toggling veil ON here <em>adds</em> error, which is
  the point (it belongs to a future front-lit scene, not this one).</p>
</div>

<script id="assets" type="application/json">__ASSETS__</script>
<script>__JS__</script>
</body>
</html>
"""

JS_TMPL = r"""
const A = JSON.parse(document.getElementById('assets').textContent);
const TEX = A.tex;
const VERT = `__VERT__`;
const FRAG = `__FRAG__`;

const cv = document.getElementById('glc');
const gl = cv.getContext('webgl2', {preserveDrawingBuffer:true, antialias:false});
if(!gl){ document.body.innerHTML = '<div class="wrap"><h1>WebGL2 unavailable</h1>'+
  '<p class="lede">This prototype needs a WebGL2-capable browser.</p></div>'; }

function sh(type, src){ const s=gl.createShader(type); gl.shaderSource(s,src); gl.compileShader(s);
  if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw gl.getShaderInfoLog(s); return s; }
const prog = gl.createProgram();
gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT));
gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
gl.bindAttribLocation(prog, 0, 'aPos');
gl.linkProgram(prog);
if(!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw gl.getProgramInfoLog(prog);
gl.useProgram(prog);
gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);  // image top-row -> texture t=1, so
                                               // the canvas render matches truth <img>

const vbo = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
gl.enableVertexAttribArray(0);
gl.vertexAttribPointer(0,2,gl.FLOAT,false,0,0);

const U = {};
['uB','uT','uH','uN','uTruth','uSigmaScale','uTexRes','uRefrGain','uScatter',
 'uRefract','uVeil','uView','uNormalMedian'].forEach(n=>U[n]=gl.getUniformLocation(prog,n));

function mktex(unit, mip){ const t=gl.createTexture(); gl.activeTexture(gl.TEXTURE0+unit);
  gl.bindTexture(gl.TEXTURE_2D,t);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER, mip?gl.LINEAR_MIPMAP_LINEAR:gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR); return t; }

const texUnits = {B:0,T:1,h:2,normal:3,truth:4};
const texObj = {B:mktex(0,true),T:mktex(1,false),h:mktex(2,false),normal:mktex(3,false),truth:mktex(4,false)};
// B and T are sRGB-encoded: SRGB8_ALPHA8 so sampling auto-decodes to linear
// and mip generation averages in linear (physically-correct light blur).
const SRGBFMT = {B:true, T:true, h:false, normal:false, truth:false};
gl.uniform1i(U.uB,0); gl.uniform1i(U.uT,1); gl.uniform1i(U.uH,2); gl.uniform1i(U.uN,3); gl.uniform1i(U.uTruth,4);

let truthPixels=null;          // 256x256 sRGB bytes for live MAE
const state = { fam:0, scatter:true, refract:false, veil:false, sigma:0, normalMedian:[0,0] };

function loadImg(src){ return new Promise(res=>{ const im=new Image(); im.onload=()=>res(im); im.src=src; }); }

async function loadFamily(i){
  const f = A.families[i];
  const imgs = {};
  for(const k of ['B','T','h','normal','truth']){ imgs[k] = await loadImg(f[k]); }
  for(const k of ['B','T','h','normal','truth']){
    gl.activeTexture(gl.TEXTURE0+texUnits[k]);
    gl.bindTexture(gl.TEXTURE_2D, texObj[k]);
    const ifmt = SRGBFMT[k] ? gl.SRGB8_ALPHA8 : gl.RGBA;
    gl.texImage2D(gl.TEXTURE_2D,0,ifmt,gl.RGBA,gl.UNSIGNED_BYTE,imgs[k]);
    if(k==='B') gl.generateMipmap(gl.TEXTURE_2D);   // linear-correct mip pyramid
  }
  // truth pixels for MAE + normal median for refraction, via a scratch canvas
  const sc=document.createElement('canvas'); sc.width=TEX; sc.height=TEX;
  const sx=sc.getContext('2d');
  sx.drawImage(imgs.truth,0,0,TEX,TEX); truthPixels = sx.getImageData(0,0,TEX,TEX).data;
  sx.clearRect(0,0,TEX,TEX); sx.drawImage(imgs.normal,0,0,TEX,TEX);
  const nd = sx.getImageData(0,0,TEX,TEX).data;
  const tx=[],ty=[];
  for(let p=0;p<nd.length;p+=4){ const nx=nd[p]/255*2-1, ny=nd[p+1]/255*2-1, nz=Math.max(Math.abs(nd[p+2]/255*2-1),1e-3);
    tx.push(nx/nz); ty.push(ny/nz); }
  tx.sort((a,b)=>a-b); ty.sort((a,b)=>a-b);
  state.normalMedian=[tx[tx.length>>1], ty[ty.length>>1]];
  document.getElementById('imgTruth').src = f.truth;
  document.getElementById('mCeiling').innerHTML = f.mae_scatter.toFixed(2)+' <small>MAE</small>';
  document.getElementById('mOracle').innerHTML = (window.ORACLE[f.recipe]||f.mae_scatter).toFixed(1)+' <small>MAE</small>';
  document.getElementById('sigfit').textContent = '(fit '+f.sigma_scale+')';
  const isHard = f.mae_scatter>5;
  document.getElementById('mVerdict').innerHTML = isHard
    ? '<span class="badge b-hard">refraction residual</span>'
    : '<span class="badge b-good">solved</span>';
  document.getElementById('famnote').innerHTML = isHard
    ? '<b>'+f.recipe+'</b> is one of the two hard families: high-transmission, relief-textured glass whose backdrop is genuinely <em>refracted</em>. Isotropic haze-scatter softens but cannot re-place the checker, so a real residual (MAE ~'+f.mae_scatter.toFixed(0)+') remains &mdash; the same limit oracle 045 reported. This is a material-model gap (relief-coupled refraction), not a renderer gap.'
    : '<b>'+f.recipe+'</b> is scatter-dominated: a haze-driven blur of the backdrop reconstructs it to the noise floor (MAE '+f.mae_scatter.toFixed(1)+', SSIM '+f.ssim_scatter.toFixed(3)+'). The cheap browser shader is indistinguishable from the path-traced truth.';
  // default slider to the fitted scale
  state.sigma = f.sigma_scale;
  document.getElementById('sig').value = f.sigma_scale;
  state.refractGain = f.refr_gain;
}

// oracle 045 ideal-Gaussian t1 MAE per recipe (reference)
window.ORACLE = {"cathedral-green":12.7,"cathedral-amber":13.1,"streaky-mix":3.0,
 "streaky-fine-texture":1.4,"wispy-white":1.3,"saturated-opalescent":1.8,"ring-mottle":1.6,
 "dark-ruby":1.1,"dark-textured":0.9,"baroque-rolling-wave":11.0,"confetti-shard":11.5,
 "fracture-streamer":8.3};

function draw(){
  gl.viewport(0,0,TEX,TEX);
  gl.uniform1f(U.uSigmaScale, state.sigma);
  gl.uniform1f(U.uTexRes, TEX);
  gl.uniform1f(U.uRefrGain, state.refractGain||0);
  gl.uniform1i(U.uScatter, state.scatter?1:0);
  gl.uniform1i(U.uRefract, state.refract?1:0);
  gl.uniform1i(U.uVeil, state.veil?1:0);
  gl.uniform2f(U.uNormalMedian, state.normalMedian[0], state.normalMedian[1]);
  gl.uniform1i(U.uView, 0);
  gl.drawArrays(gl.TRIANGLES,0,3);
  // read back for MAE + diff
  const px=new Uint8Array(TEX*TEX*4);
  gl.readPixels(0,0,TEX,TEX,gl.RGBA,gl.UNSIGNED_BYTE,px);
  let sum=0,n=0;
  const dctx=document.getElementById('dc').getContext('2d');
  const dimg=dctx.createImageData(TEX,TEX);
  for(let p=0;p<px.length;p+=4){
    // readPixels is bottom-up; truthPixels is top-down. Flip row.
    const idx=p>>2, r=idx/TEX|0, c=idx%TEX, tr=(TEX-1-r)*TEX+c, tp=tr*4;
    for(let k=0;k<3;k++){ const d=Math.abs(px[p+k]-truthPixels[tp+k]); sum+=d; n++;
      dimg.data[tp+k]=Math.min(255,d*3); }
    dimg.data[tp+3]=255;
  }
  dctx.putImageData(dimg,0,0);
  const mae=sum/n;
  document.getElementById('mBrowser').innerHTML = mae.toFixed(2)+' <small>MAE</small>';
  document.getElementById('capB').textContent = 'MAE '+mae.toFixed(2);
  document.getElementById('sigv').textContent = state.sigma.toFixed(0)+' px';
}

// wire UI
const sel=document.getElementById('fam');
A.families.forEach((f,i)=>{ const o=document.createElement('option'); o.value=i;
  o.textContent=f.recipe+'  ('+f.family+')'; sel.appendChild(o); });
sel.onchange=async e=>{ state.fam=+e.target.value; await loadFamily(state.fam); draw(); };
document.getElementById('tScatter').onchange=e=>{ state.scatter=e.target.checked; draw(); };
document.getElementById('tRefract').onchange=e=>{ state.refract=e.target.checked; draw(); };
document.getElementById('tVeil').onchange=e=>{ state.veil=e.target.checked; draw(); };
document.getElementById('sig').oninput=e=>{ state.sigma=+e.target.value; draw(); };

const hashFam = Math.max(0, Math.min(A.families.length-1, parseInt((location.hash||'').replace('#','')) || 0));
sel.value = hashFam; state.fam = hashFam;
(async()=>{ await loadFamily(hashFam); draw(); })();
"""


def main():
    assets = open(ASSETS).read()
    js = (JS_TMPL.replace("__VERT__", VERT.replace("`", "\\`"))
                 .replace("__FRAG__", FRAG.replace("`", "\\`")))
    html = (HTML_TMPL.replace("__CSS__", CSS)
                     .replace("__ASSETS__", assets)
                     .replace("__JS__", js))
    with open(OUT, "w") as fp:
        fp.write(html)
    kb = os.path.getsize(OUT) / 1024
    print(f"wrote {OUT}  ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
