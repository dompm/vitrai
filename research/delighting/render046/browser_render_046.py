"""046 -- BROWSER-RENDER RUNTIME CEILING (numpy-faithful real-time shader).

Question (report 046, follow-on to the oracle-relight gate 045): given our
current material model (T, h -> sigma_s scatter, + optional relief refraction
and front veil) and GROUND-TRUTH maps, how close can a *cheap, deployable,
in-browser* glass renderer get to the Cycles path-traced truth? If it is close,
the shipping preview does not need path tracing -- a screen-space transmission
shader suffices.

This module is the NUMPY MIRROR of the exact real-time algorithm the WebGL
prototype (render046.html) runs, so the ceiling number is measured on the true
game-engine approximation, not an idealized continuous Gaussian:

  1. GRAB-PASS   : the "scene behind the glass" is the backdrop B (struct_B).
  2. MIP PYRAMID : build B's mip chain by repeated 2x box downsample (exactly
                   what GPU auto-mip generation does), 1024 -> 512 -> ... -> 1.
  3. SCATTER     : per-pixel sigma_s(x) = sigma_scale * h(x); sample the pyramid
                   with textureLod(uv, LOD) where LOD = log2(sigma_s) -- the
                   "roughness-mip blur" frosted-glass trick. Trilinear (bilinear
                   within a level + linear across the two nearest levels), the
                   literal GPU textureLod. At max LOD the 1x1 mip == mean(B), so
                   this single term reproduces the current app model's h*<B>
                   mean-crossfade at the high-haze limit without a separate term.
  4. TINT        : multiply by T(x)  (Beer-Lambert absorption).  L = T * scatter.
  5. REFRACTION  : (toggle) offset the grab UV by the surface-normal tilt
                   (single interface, IOR 1.5), gain grid-searched incl. sign --
                   oracle 045 found this marginal; we confirm.
  6. VEIL        : (toggle, OFF by default) add the front-surface reflection AOV;
                   identically zero in a backlit rig (oracle 045 sec 4).

The real-time-approximation COST is precisely the gap between this finite
mip/trilinear scatter and oracle 045's true per-sigma Gaussian stack (tier t1).

Metrics (MAE 0-255 sRGB, SSIM on luma) are byte-identical to oracle 045's
recon_bench_045.score / ssim_gray so the two tables are directly comparable.

Run:  .venv/bin/python browser_render_046.py --data <oracle45_data> --out <dir>
"""

import argparse
import json
import os

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np

IOR = 1.5

FAMILY = {
    "cathedral-green": "cathedral", "cathedral-amber": "cathedral",
    "streaky-mix": "streaky", "streaky-fine-texture": "streaky",
    "wispy-white": "wispy", "saturated-opalescent": "saturated-opalescent",
    "ring-mottle": "ring-mottle", "dark-ruby": "dark", "dark-textured": "dark",
    "baroque-rolling-wave": "baroque/fracture/confetti",
    "fracture-streamer": "baroque/fracture/confetti",
    "confetti-shard": "baroque/fracture/confetti",
}

# sigma_scale grid: blur radius (working-res px) at h=1. Grid-searched per
# sample exactly as oracle 045 grid-searched sigma_max, so we measure THIS
# renderer's own ceiling rather than transplanting oracle's Gaussian sigma.
SIGMA_SCALE_GRID = [0.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0, 512.0, 1024.0]
REFR_GAIN_GRID = [-8.0, -4.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 4.0, 8.0]


# ---------------------------------------------------------------- EXR IO
def read_exr(path):
    """Scene-linear RGB (or HxW scalar) float32. cv2 first; OpenEXR fallback
    for the BW single-channel DWAA files cv2 5.0 cannot parse (report 043)."""
    a = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if a is not None:
        if a.ndim == 3:
            a = a[..., :3][..., ::-1]  # BGR->RGB
        return np.ascontiguousarray(a, np.float32)
    import OpenEXR
    f = OpenEXR.File(path)
    ch = f.parts[0].channels
    keys = sorted(ch.keys())
    if len(keys) == 1:
        px = ch[keys[0]].pixels
        return (px[..., :3] if px.ndim == 3 else px).astype(np.float32)
    order = [k for k in ("R", "G", "B") if k in keys] or keys
    return np.stack([ch[k].pixels for k in order], -1).astype(np.float32)


def srgb_to_lin(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(a):
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055)


LUMW = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


# ---------------------------------------------------------------- metrics
# byte-identical to oracle45 recon_bench_045.ssim_gray / score
def ssim_gray(x, y):
    C1, C2 = 0.01 ** 2, 0.03 ** 2
    f = lambda a: cv2.GaussianBlur(a, (11, 11), 1.5)
    mx, my = f(x), f(y)
    vx = f(x * x) - mx * mx
    vy = f(y * y) - my * my
    cxy = f(x * y) - mx * my
    num = (2 * mx * my + C1) * (2 * cxy + C2)
    den = (mx * mx + my * my + C1) * (vx + vy + C2)
    return float((num / den).mean())


def score(L_lin, truth_lin):
    a = lin_to_srgb(np.clip(L_lin, 0, 1))
    b = lin_to_srgb(np.clip(truth_lin, 0, 1))
    mae = float(np.abs(a - b).mean() * 255.0)
    ssim = ssim_gray((a * LUMW).sum(-1), (b * LUMW).sum(-1))
    return mae, ssim


# ---------------------------------------------- GPU-faithful mip scatter
def build_mip_pyramid(B):
    """Repeated 2x box downsample == GPU auto-mip. Returns list of levels, and
    a stack of each level bilinearly re-upsampled to full res (so a per-pixel
    trilinear textureLod is a simple gather+lerp). INTER_AREA at exactly half
    size is a 2x2 box average; INTER_LINEAR upsample is GPU bilinear."""
    H, W = B.shape[:2]
    levels = [B]
    cur = B
    while min(cur.shape[:2]) > 1:
        h2 = max(1, cur.shape[0] // 2)
        w2 = max(1, cur.shape[1] // 2)
        cur = cv2.resize(cur, (w2, h2), interpolation=cv2.INTER_AREA)
        levels.append(cur)
    up = np.stack([cv2.resize(lv, (W, H), interpolation=cv2.INTER_LINEAR)
                   for lv in levels], axis=0)  # (L,H,W,3)
    return levels, up


def texture_lod(up_stack, lod):
    """Per-pixel trilinear sample of the pre-upsampled pyramid: linear blend
    between the two nearest mip levels (bilinear reconstruction is already
    baked into `up_stack`). `lod` is HxW float in [0, nlev-1]."""
    nlev = up_stack.shape[0]
    lod = np.clip(lod, 0.0, nlev - 1.0)
    l0 = np.floor(lod).astype(np.int32)
    l0 = np.clip(l0, 0, nlev - 2)
    f = (lod - l0)[..., None]
    H, W = lod.shape
    rows, cols = np.mgrid[0:H, 0:W]
    a = up_stack[l0, rows, cols]
    b = up_stack[l0 + 1, rows, cols]
    return a * (1.0 - f) + b * f


def sigma_to_lod(sigma_px, nlev):
    """A mip level L averages ~2^L px, i.e. a box blur of width ~2^L; so an
    effective blur width of sigma_px px is LOD = log2(sigma_px)."""
    return np.clip(np.log2(np.maximum(sigma_px, 1.0)), 0.0, nlev - 1.0)


def refraction_offset(normal, gain):
    """Screen-space grab-UV offset (in px) from the surface-normal tilt, the
    single-interface small-angle refraction a real transmission shader applies.
    Decode the normal map (n = 2*rgb-1), isolate the *relief* tilt by removing
    the flat-sheet median, and offset by the tangential slope * (1-1/IOR) * gain.
    Direction/sign & absolute scale are absorbed by the grid-searched gain,
    exactly as oracle 045's lens_gain covered Bump-node normalization."""
    n = normal * 2.0 - 1.0
    nz = np.maximum(np.abs(n[..., 2]), 1e-3)
    tilt = n[..., :2] / nz[..., None]
    tilt = tilt - np.median(tilt.reshape(-1, 2), axis=0)[None, None, :]
    dev = (1.0 - 1.0 / IOR)
    dx = tilt[..., 0] * dev * gain
    dy = tilt[..., 1] * dev * gain
    return dx.astype(np.float32), dy.astype(np.float32)


def render(maps, sigma_scale, refr_gain=0.0, use_veil=False):
    """The real-time shader, numpy mirror. maps: dict with T,h,normal,B,veil."""
    T, h, B = maps["T"], maps["h"], maps["B"]
    levels, up = maps["_pyr"]  # cached per sample
    nlev = up.shape[0]
    H, W = h.shape

    if refr_gain != 0.0:
        dx, dy = refraction_offset(maps["normal"], refr_gain)
        cols, rows = np.meshgrid(np.arange(W, dtype=np.float32),
                                 np.arange(H, dtype=np.float32))
        map_x = cols + dx
        map_y = rows + dy
        up = np.stack([cv2.remap(up[i], map_x, map_y, cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
                       for i in range(nlev)], axis=0)

    if sigma_scale > 0:
        lod = sigma_to_lod(sigma_scale * h, nlev)
        scattered = texture_lod(up, lod)
    else:
        scattered = up[0]

    L = T * scattered
    if use_veil:
        L = L + maps["veil"]
    return L


# ---------------------------------------------------------------- per sample
def load_maps(d):
    T = np.clip(read_exr(os.path.join(d, "gt_T.exr")), 0, 1)
    h = read_exr(os.path.join(d, "gt_h.exr"))
    if h.ndim == 3:
        h = h[..., 0]
    h = np.clip(h, 0, 1)
    normal = read_exr(os.path.join(d, "gt_normal.exr"))
    B = read_exr(os.path.join(d, "struct_B.exr"))
    truth = read_exr(os.path.join(d, "struct_photo_linear.exr"))
    veil_path = os.path.join(d, "struct_veil.exr")
    veil = read_exr(veil_path) if os.path.exists(veil_path) else np.zeros_like(T)
    if veil.ndim == 3 and veil.shape[-1] > 3:
        veil = veil[..., :3]
    if veil.ndim == 2:
        veil = np.repeat(veil[..., None], 3, -1)
    m = {"T": T, "h": h, "normal": normal, "B": B, "veil": veil.astype(np.float32),
         "truth": truth}
    m["_pyr"] = build_mip_pyramid(B)
    return m


def run_sample(d):
    name = os.path.basename(d)
    recipe = name.split("__")[0]
    m = load_maps(d)
    truth = m["truth"]
    res = {"sample": name, "recipe": recipe, "family": FAMILY[recipe], "tiers": {}}

    # baseline: scatter OFF (sharp grab, tinted) L = T*B
    L_off = render(m, 0.0)
    mae, ss = score(L_off, truth)
    res["tiers"]["t0_sharp"] = {"mae": mae, "ssim": ss}

    # scatter ON: fit sigma_scale (grid, oracle-style)
    best_sig, best_mae = 0.0, mae
    for sg in SIGMA_SCALE_GRID[1:]:
        mm = score(render(m, sg), truth)[0]
        if mm < best_mae:
            best_sig, best_mae = sg, mm
    L_sc = render(m, best_sig)
    mae, ss = score(L_sc, truth)
    res["tiers"]["t1_scatter"] = {"mae": mae, "ssim": ss}
    res["sigma_scale"] = best_sig

    # + refraction: fit gain given best sigma
    best_gain, best_mae2 = 0.0, best_mae
    for g in REFR_GAIN_GRID:
        if g == 0.0:
            continue
        mm = score(render(m, best_sig, g), truth)[0]
        if mm < best_mae2:
            best_gain, best_mae2 = g, mm
    L_rf = render(m, best_sig, best_gain)
    mae, ss = score(L_rf, truth)
    res["tiers"]["t2_refraction"] = {"mae": mae, "ssim": ss}
    res["refr_gain"] = best_gain

    # + veil
    L_vl = render(m, best_sig, best_gain, use_veil=True)
    mae, ss = score(L_vl, truth)
    res["tiers"]["t3_veil"] = {"mae": mae, "ssim": ss}
    res["veil_mean_linear"] = float(m["veil"].mean())

    panels = {"truth": truth, "backdrop": m["B"], "t0_sharp": L_off,
              "t1_scatter": L_sc, "t2_refraction": L_rf}
    return res, panels, m


# ---------------------------------------------------------------- board
def to_u8(lin, size):
    img = (lin_to_srgb(np.clip(lin, 0, 1)) * 255).astype(np.uint8)
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    return img[..., ::-1].copy()


def label(img, text):
    cv2.rectangle(img, (0, 0), (img.shape[1], 18), (0, 0, 0), -1)
    cv2.putText(img, text, (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                (255, 255, 255), 1, cv2.LINE_AA)
    return img


def diff_panel(a_lin, b_lin, size):
    a = lin_to_srgb(np.clip(a_lin, 0, 1))
    b = lin_to_srgb(np.clip(b_lin, 0, 1))
    d = np.abs(a - b).mean(-1)
    d = np.clip(d * 3.0, 0, 1)  # 3x gain for visibility
    dm = cv2.applyColorMap((d * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    dm = cv2.resize(dm, (size, size), interpolation=cv2.INTER_AREA)
    return dm  # already BGR


def build_board(rows, out_path, cell=240):
    board_rows = []
    for res, panels in rows:
        cells = [
            label(to_u8(panels["backdrop"], cell), f"{res['sample'][:24]} backdrop B"),
            label(to_u8(panels["truth"], cell), "CYCLES truth"),
            label(to_u8(panels["t0_sharp"], cell), f"scatter OFF  MAE {res['tiers']['t0_sharp']['mae']:.1f}"),
            label(to_u8(panels["t1_scatter"], cell), f"+scatter  MAE {res['tiers']['t1_scatter']['mae']:.1f}"),
            label(to_u8(panels["t2_refraction"], cell), f"+refr  MAE {res['tiers']['t2_refraction']['mae']:.1f}"),
            label(diff_panel(panels["t1_scatter"], panels["truth"], cell), "diff x3 (scatter)"),
        ]
        board_rows.append(np.concatenate(cells, axis=1))
    board = np.concatenate(board_rows, axis=0)
    cv2.imwrite(out_path, board, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"board -> {out_path}  {board.shape}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default=None, help="comma substrings to filter samples")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    dirs = sorted(d for d in (os.path.join(args.data, x) for x in os.listdir(args.data))
                  if os.path.isdir(d) and os.path.exists(os.path.join(d, "meta.json")))
    if args.only:
        subs = args.only.split(",")
        dirs = [d for d in dirs if any(s in os.path.basename(d) for s in subs)]

    all_res, rows = [], []
    for d in dirs:
        print(f"rendering {os.path.basename(d)} ...", flush=True)
        res, panels, _ = run_sample(d)
        all_res.append(res)
        rows.append((res, panels))
        t = res["tiers"]
        print(f"  sharp {t['t0_sharp']['mae']:6.2f}/{t['t0_sharp']['ssim']:.3f} | "
              f"scatter(sig={res['sigma_scale']:6.1f}) {t['t1_scatter']['mae']:6.2f}/{t['t1_scatter']['ssim']:.3f} | "
              f"+refr(g={res['refr_gain']:5.1f}) {t['t2_refraction']['mae']:6.2f}/{t['t2_refraction']['ssim']:.3f} | "
              f"+veil {t['t3_veil']['mae']:6.2f}")

    fam = {}
    for r in all_res:
        fam.setdefault(r["family"], []).append(r)
    agg = {}
    for f, rs in fam.items():
        agg[f] = {"n": len(rs)}
        for tkey in rs[0]["tiers"]:
            agg[f][tkey] = {
                "mae": float(np.mean([x["tiers"][tkey]["mae"] for x in rs])),
                "ssim": float(np.mean([x["tiers"][tkey]["ssim"] for x in rs])),
            }

    with open(os.path.join(args.out, "browser_ceiling_metrics.json"), "w") as fp:
        json.dump({"samples": all_res, "family_agg": agg}, fp, indent=2)
    build_board(rows, os.path.join(args.out, "browser_ceiling_board.jpg"))
    print("done")


if __name__ == "__main__":
    main()
