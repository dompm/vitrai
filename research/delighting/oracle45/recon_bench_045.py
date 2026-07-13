"""Iteration 045 -- ORACLE RELIGHT analytic reconstructions + metrics + board.

Given the truth renders from gen_oracle45.py, reconstruct each scene from the
GROUND-TRUTH maps (oracle setting -- no extraction) at progressively richer
model tiers and score each tier against the Cycles truth:

  tier0 "current"   L = T * (h*<B> + (1-h)*B)          -- the shipped app model
  tier1 "+scatter"  B -> blur(B, sigma_s(x)) with sigma_s = sigma_max * h
                     (MMv3 G1; sigma_max grid-searched per sample -- oracle fit)
  tier2 "+lensing"  B -> warp(B) by single-interface Snell refraction from
                     gt_normal (IOR 1.5, physical displacement estimate x a
                     grid-searched gain -- MMv3 G3), then scatter blur
  tier3 "+veil"     L += gt veil AOV (MMv3 G2)

All compositing in scene-linear; metrics (MAE, SSIM) in sRGB (0-255 for MAE),
matching the report-008/014 convention. Under the uniform scene tier0
analytically reduces to L = T (the report-008 sec0 collapse) -- measured, not
assumed.

Run:  .venv/bin/python recon_bench_045.py --data <data_dir> \
          --out ../results/045 [--board-only]
"""

import argparse
import json
import os
import sys

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from extract import srgb_to_lin, lin_to_srgb, load_aov_exr  # noqa: E402

IOR = 1.5
FAMILY = {
    "cathedral-green": "cathedral", "cathedral-amber": "cathedral",
    "cathedral-blue": "cathedral", "cathedral-red": "cathedral",
    "streaky-mix": "streaky", "streaky-fine-texture": "streaky",
    "wispy-white": "wispy",
    "saturated-opalescent": "saturated-opalescent",
    "ring-mottle": "ring-mottle",
    "dark-opaque": "dark", "dark-deep": "dark", "dark-ruby": "dark",
    "dark-slate": "dark", "dark-textured": "dark",
    "baroque-rolling-wave": "baroque/fracture/confetti",
    "fracture-streamer": "baroque/fracture/confetti",
    "confetti-shard": "baroque/fracture/confetti",
}

SIGMA_LEVELS = [0.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]
SIGMA_MAX_GRID = [0.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]
LENS_GAIN_GRID = [-4.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0]


def read_exr_rgb(path):
    a = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if a is None:
        # cv2 5.0 fails on some single-channel (BW) EXR layouts; fall back to
        # the OpenEXR binding (plain single-part files read fine there too).
        import OpenEXR
        f = OpenEXR.File(path)
        ch = f.parts[0].channels
        keys = sorted(ch.keys())
        if len(keys) == 1:
            px = ch[keys[0]].pixels
            a = px[..., :3][..., ::-1] if px.ndim == 3 else px  # match cv2 BGR path
        else:
            order = [k for k in ("B", "G", "R") if k in keys] or keys
            a = np.stack([ch[k].pixels for k in order], axis=-1)
    if a.ndim == 3:
        a = a[..., :3][..., ::-1]  # BGR->RGB
    return np.ascontiguousarray(a, dtype=np.float32)


def load_sample(d):
    s = {}
    s["meta"] = json.load(open(os.path.join(d, "meta.json")))
    gt_T = read_exr_rgb(os.path.join(d, "gt_T.exr"))
    gt_h = read_exr_rgb(os.path.join(d, "gt_h.exr"))
    gt_height = read_exr_rgb(os.path.join(d, "gt_height.exr"))
    if gt_h.ndim == 3:
        gt_h = gt_h[..., 0]
    if gt_height.ndim == 3:
        gt_height = gt_height[..., 0]
    # UNITS (report 025 / GT_SPEC sec 5-6, check_validation.py convention):
    # the shader samples the sRGB-shaped FILE, so the render's effective
    # material fields are the RAW gt_* bytes -- photo_linear == raw(gt_T) * B
    # is the frozen validate-gate identity. The oracle recon therefore uses
    # the raw values (perfect estimation of the *effective* material); the
    # authored-linear decode (srgb_to_lin) is a monotone reparameterization a
    # predictor could carry either way.
    s["T"] = np.clip(gt_T, 0, 1)
    s["h"] = np.clip(gt_h, 0, 1)
    s["height"] = np.clip(gt_height, 0, 1)  # == enc(authored height): exactly
    # what the Bump node consumed, so its gradient IS the shading perturbation
    for prefix in ("uniform", "struct"):
        s[f"{prefix}_truth"] = read_exr_rgb(os.path.join(d, f"{prefix}_photo_linear.exr"))
        s[f"{prefix}_B"] = read_exr_rgb(os.path.join(d, f"{prefix}_B.exr"))
        v = load_aov_exr(os.path.join(d, f"{prefix}_veil.exr"))
        if v.ndim == 3 and v.shape[-1] > 3:
            v = v[..., :3]
        s[f"{prefix}_veil"] = v.astype(np.float32)
    return s


# ---------------------------------------------------------------- model tiers
def blur_stack(B, sigmas):
    out = []
    for sg in sigmas:
        if sg <= 0:
            out.append(B)
        else:
            k = int(sg * 3) * 2 + 1
            out.append(cv2.GaussianBlur(B, (k, k), sg))
    return np.stack(out, axis=0)  # (S,H,W,3)


def variable_blur(stack, sigmas, sigma_map):
    """Per-pixel lerp between the two nearest blur levels."""
    sig = np.clip(sigma_map, sigmas[0], sigmas[-1])
    idx = np.searchsorted(sigmas, sig, side="right") - 1
    idx = np.clip(idx, 0, len(sigmas) - 2)
    lo = np.array(sigmas)[idx]
    hi = np.array(sigmas)[idx + 1]
    w = np.where(hi > lo, (sig - lo) / np.maximum(hi - lo, 1e-9), 0.0)[..., None]
    H, W = sig.shape
    rows, cols = np.mgrid[0:H, 0:W]
    a = stack[idx, rows, cols]
    b = stack[idx + 1, rows, cols]
    return a * (1 - w) + b * w


def lens_warp_maps(s, gain):
    """Single-interface Snell displacement of the backdrop, small-angle form.

    The Cycles sheet is ONE interface (single plane, no exit face), so a
    camera ray entering the glass keeps its refracted direction all the way
    to the backdrop. Small angles: transmitted deviation ~= slope*(1 - 1/IOR).
    Slope is taken from the CAMERA-SPACE gt_height gradient -- gt_height's
    raw bytes are exactly the field the Bump node consumed (see load_sample),
    so grad(gt_height)/px * (px per meter at the glass) * bump_distance is
    the world slope the renderer actually shaded with. Displacement on the
    backdrop (dist_gb behind the glass) projects back to B-image pixels
    through the same camera. An undeviated ray hits the backdrop at its own
    pixel, so the warp is a pure per-pixel offset.
    `gain` multiplies the physical displacement (grid-searched, sign
    included; covers Bump-node normalization differences honestly).
    """
    meta = s["meta"]
    H, W = s["h"].shape
    bump = meta["bump_distance_m"]
    dist_gb = meta["backdrop_y_m"]                       # glass y=0 -> backdrop
    cam_dist_b = meta["backdrop_y_m"] - meta["cam_y_m"]  # camera -> backdrop
    cam_dist_g = -meta["cam_y_m"]                        # camera -> glass
    lens = meta["camera"]["lens_mm"]
    sensor = meta["camera"]["sensor_width_mm"]
    half_w = (sensor / 2.0) / lens                       # tan(hfov/2)

    # camera-space height gradient, per render pixel (rows = image down)
    gy, gx = np.gradient(s["height"])
    vis_w_glass = 2.0 * cam_dist_g * half_w              # visible meters at glass
    slope_x = gx * (W / vis_w_glass) * bump              # dh/dx_world
    slope_z = -gy * (H / vis_w_glass) * bump             # image row down = -z
    dev = (1.0 - 1.0 / IOR)
    disp_x_world = -dist_gb * dev * slope_x * gain       # toward-normal bend
    disp_z_world = -dist_gb * dev * slope_z * gain
    # world meters -> B-image pixels at the backdrop plane
    px_per_m = W / (2.0 * cam_dist_b * half_w)
    dx_px = disp_x_world * px_per_m
    dy_px = -disp_z_world * px_per_m                     # image row = -z
    cols, rows = np.meshgrid(np.arange(W, dtype=np.float32),
                             np.arange(H, dtype=np.float32))
    map_x = cols + dx_px.astype(np.float32)
    map_y = rows + dy_px.astype(np.float32)
    return map_x, map_y


def reconstruct(s, prefix, sigma_max, lens_gain, use_veil):
    T, h = s["T"], s["h"]
    B = s[f"{prefix}_B"]
    meanB = B.reshape(-1, 3).mean(axis=0)
    if lens_gain != 0.0:
        mx, my = lens_warp_maps(s, lens_gain)
        B = cv2.remap(B, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    if sigma_max > 0:
        stack = blur_stack(B, SIGMA_LEVELS)
        B = variable_blur(stack, SIGMA_LEVELS, sigma_max * h)
    L = T * (h[..., None] * meanB[None, None] + (1.0 - h[..., None]) * B)
    if use_veil:
        L = L + s[f"{prefix}_veil"]
    return L


# ---------------------------------------------------------------- metrics
def ssim_gray(x, y):
    """Standard windowed SSIM (Wang et al.) on [0,1] gray, gaussian 11/1.5."""
    C1, C2 = 0.01 ** 2, 0.03 ** 2
    f = lambda a: cv2.GaussianBlur(a, (11, 11), 1.5)
    mx, my = f(x), f(y)
    vx = f(x * x) - mx * mx
    vy = f(y * y) - my * my
    cxy = f(x * y) - mx * my
    num = (2 * mx * my + C1) * (2 * cxy + C2)
    den = (mx * mx + my * my + C1) * (vx + vy + C2)
    return float((num / den).mean())


LUMW = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def score(L_lin, truth_lin):
    a = lin_to_srgb(np.clip(L_lin, 0, 1))
    b = lin_to_srgb(np.clip(truth_lin, 0, 1))
    mae = float(np.abs(a - b).mean() * 255.0)
    ssim = ssim_gray((a * LUMW).sum(-1), (b * LUMW).sum(-1))
    return mae, ssim


# ---------------------------------------------------------------- per sample
def run_sample(d):
    s = load_sample(d)
    name = os.path.basename(d)
    res = {"sample": name, "recipe": s["meta"]["recipe"],
           "family": FAMILY[s["meta"]["recipe"]], "tiers": {}}

    truths = {p: s[f"{p}_truth"] for p in ("uniform", "struct")}

    def sc(prefix, L):
        return score(L, truths[prefix])

    # tier0: current product model
    L0 = {p: reconstruct(s, p, 0.0, 0.0, False) for p in truths}
    res["tiers"]["t0_current"] = {p: dict(zip(("mae", "ssim"), sc(p, L0[p]))) for p in truths}

    # tier1: + scatter blur; sigma_max fitted on the struct scene (oracle fit)
    best_sig, best_mae = 0.0, sc("struct", L0["struct"])[0]
    for sg in SIGMA_MAX_GRID[1:]:
        mae = sc("struct", reconstruct(s, "struct", sg, 0.0, False))[0]
        if mae < best_mae:
            best_sig, best_mae = sg, mae
    L1 = {p: reconstruct(s, p, best_sig, 0.0, False) for p in truths}
    res["tiers"]["t1_scatter"] = {p: dict(zip(("mae", "ssim"), sc(p, L1[p]))) for p in truths}
    res["sigma_max_px"] = best_sig

    # tier2: + relief lensing; gain fitted on struct given best_sig
    best_gain, best_mae2 = 0.0, best_mae
    for g in LENS_GAIN_GRID:
        if g == 0.0:
            continue
        mae = sc("struct", reconstruct(s, "struct", best_sig, g, False))[0]
        if mae < best_mae2:
            best_gain, best_mae2 = g, mae
    # refit sigma once with the gain in place
    if best_gain != 0.0:
        for sg in SIGMA_MAX_GRID:
            mae = sc("struct", reconstruct(s, "struct", sg, best_gain, False))[0]
            if mae < best_mae2:
                best_sig, best_mae2 = sg, mae
    L2 = {p: reconstruct(s, p, best_sig, best_gain, False) for p in truths}
    res["tiers"]["t2_lensing"] = {p: dict(zip(("mae", "ssim"), sc(p, L2[p]))) for p in truths}
    res["lens_gain"] = best_gain
    res["sigma_max_px_refit"] = best_sig

    # tier3: + veil AOV
    L3 = {p: reconstruct(s, p, best_sig, best_gain, True) for p in truths}
    res["tiers"]["t3_veil"] = {p: dict(zip(("mae", "ssim"), sc(p, L3[p]))) for p in truths}
    res["veil_mean_linear"] = {p: float(s[f"{p}_veil"].mean()) for p in truths}

    # collapse checks (report-008 sec0): under uniform B the current model
    # reduces to L = T; and the validate-gate identity truth ~= T * B.
    res["uniform_L0_equals_T_mae_linear"] = float(np.abs(L0["uniform"] - s["T"]).mean())
    res["uniform_truth_vs_T_mae_linear"] = float(np.abs(truths["uniform"] - s["T"]).mean())

    panels = {"truth_uniform": truths["uniform"], "t0_uniform": L0["uniform"],
              "t3_uniform": L3["uniform"], "truth_struct": truths["struct"],
              "t0_struct": L0["struct"], "t1_struct": L1["struct"],
              "t3_struct": L3["struct"]}
    return res, panels


# ---------------------------------------------------------------- board
def to_u8(lin, size):
    img = (lin_to_srgb(np.clip(lin, 0, 1)) * 255).astype(np.uint8)
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    return img[..., ::-1].copy()  # RGB->BGR for cv2 imwrite


def label(img, text):
    cv2.rectangle(img, (0, 0), (img.shape[1], 18), (0, 0, 0), -1)
    cv2.putText(img, text, (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                (255, 255, 255), 1, cv2.LINE_AA)
    return img


def build_board(rows, out_path, cell=250):
    cols = [("truth_uniform", "TRUTH uniform"), ("t0_uniform", "current (T,h)"),
            ("t3_uniform", "ext. MMv3"), ("truth_struct", "TRUTH structured"),
            ("t0_struct", "current (T,h)"), ("t1_struct", "+scatter"),
            ("t3_struct", "+lens+veil")]
    board_rows = []
    for res, panels in rows:
        cells = []
        for key, cname in cols:
            img = to_u8(panels[key], cell)
            tier = {"t0": "t0_current", "t1": "t1_scatter", "t3": "t3_veil"}.get(key[:2])
            scene = "uniform" if "uniform" in key else "struct"
            if tier:
                mae = res["tiers"][tier][scene]["mae"]
                txt = f"{cname}  MAE {mae:.1f}"
            else:
                txt = f"{res['sample'][:26]}  {cname}" if key == "truth_uniform" else cname
            cells.append(label(img, txt))
        board_rows.append(np.concatenate(cells, axis=1))
    board = np.concatenate(board_rows, axis=0)
    cv2.imwrite(out_path, board, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"board -> {out_path}  {board.shape}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    dirs = sorted(d for d in (os.path.join(args.data, x) for x in os.listdir(args.data))
                  if os.path.isdir(d) and os.path.exists(os.path.join(d, "meta.json")))
    all_res, rows = [], []
    for d in dirs:
        print(f"scoring {os.path.basename(d)} ...", flush=True)
        res, panels = run_sample(d)
        all_res.append(res)
        rows.append((res, panels))
        for t, v in res["tiers"].items():
            print(f"  {t:12s} uniform MAE {v['uniform']['mae']:6.2f} SSIM {v['uniform']['ssim']:.3f}"
                  f" | struct MAE {v['struct']['mae']:6.2f} SSIM {v['struct']['ssim']:.3f}")

    # family aggregate
    fam = {}
    for r in all_res:
        fam.setdefault(r["family"], []).append(r)
    agg = {}
    for f, rs in fam.items():
        agg[f] = {t: {p: {"mae": float(np.mean([x["tiers"][t][p]["mae"] for x in rs])),
                          "ssim": float(np.mean([x["tiers"][t][p]["ssim"] for x in rs]))}
                      for p in ("uniform", "struct")}
                  for t in rs[0]["tiers"]}

    with open(os.path.join(args.out, "oracle_relight_metrics.json"), "w") as fp:
        json.dump({"samples": all_res, "family_agg": agg}, fp, indent=2)
    build_board(rows, os.path.join(args.out, "oracle_relight_board.jpg"))
    print("done")


if __name__ == "__main__":
    main()
