"""Report 054 -- scale-split potential lensing: can (T, sigma_s, phi) close the
cathedral/baroque relief-refraction residual that survived 045/046/047?

Hypothesis (lead, pre-registered): 045's t2 lensing failed for two fixable
reasons, not because warp-lensing is wrong physics:
  (1) FULL-BAND displacement -- grad(height) carries the fine relief, whose
      true image effect is statistical (= sigma_s blur); feeding it into a
      deterministic warp produces per-pixel jitter (the 2-D twin of 047's
      orange-peel), and the grid-fit gain then trades off scales -> the
      sign-flipping gains 045 measured.
  (2) SEQUENTIAL fitting -- t1's sigma_max was frozen before the warp gain was
      searched, so scatter had already absorbed the smoothing that coarse
      lensing should explain; the warp was left fitting residual noise.

Operator under test (tier "t2b"):
  height_smooth = G_{sigma_l} * height          (coarse band only)
  u(x)          = alpha * P[grad(height_smooth)] (045's exact camera/world
                                                 projection, gain alpha)
  B'            = remap(B, x + u)                (radiance-conserving: the
                                                 backdrop is emissive, so no
                                                 |det J| factor is due)
  B''           = variable_blur(B', sigma_max * h)  (sigma_s as shipped)
  L             = T * (h*<B> + (1-h)*B'')
JOINT grid over (sigma_l, alpha, sigma_max); struct scene only (uniform is the
045-proven trap). Baseline columns reproduce 045's t1 (sigma only) and t2
(full-band warp, sequential fit) for a like-for-like read.

Pre-registered verdicts (set before any number was seen):
  cathedral struct MAE < 6   -> extend the material target with phi
  6..9                       -> real but partial; report honestly
  >= 11                      -> KILL scale-split lensing; relief needs transport
Also required for a win: best (sigma_l, alpha) coherent across samples
(stable sign + order of magnitude), unlike t2's -4..+8 flips.
"""
import json
import os
import sys

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import recon_bench_045 as rb  # reuse loaders, tiers, metrics -- byte-identical baselines

SIGMA_L_GRID = [2.0, 4.0, 8.0, 16.0, 32.0]      # coarse-band smoothing (px @1024)
ALPHA_GRID = [0.0, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]
SIGMA_MAX_GRID = rb.SIGMA_MAX_GRID               # same 9 levels as 045
SAMPLES = ["cathedral-green__seed6001", "cathedral-amber__seed6002",
           "baroque-rolling-wave__seed6001", "confetti-shard__seed6002",
           "fracture-streamer__seed6003",
           "streaky-mix__seed6001"]              # streaky = solved-family control:
                                                 # t2b must NOT regress it


def lens_warp_maps_band(s, gain, sigma_l):
    """045's lens_warp_maps with the height field low-passed first."""
    height_full = s["height"]
    hs = cv2.GaussianBlur(height_full, (0, 0), sigma_l) if sigma_l > 0 else height_full
    s2 = dict(s)
    s2["height"] = hs
    return rb.lens_warp_maps(s2, gain)


def reconstruct_t2b(s, B, T, h, meanB, warped_cache, sigma_max):
    Bw = warped_cache
    if sigma_max > 0:
        stack = rb.blur_stack(Bw, rb.SIGMA_LEVELS)
        Bb = rb.variable_blur(stack, rb.SIGMA_LEVELS, sigma_max * h)
    else:
        Bb = Bw
    return T * (h[..., None] * meanB[None, None] + (1.0 - h[..., None]) * Bb)


def score(L, truth):
    Ls = rb.lin_to_srgb(np.clip(L, 0, None))
    Ts = rb.lin_to_srgb(np.clip(truth, 0, None))
    mae = float(np.abs(Ls - Ts).mean() * 255.0)
    ssim = rb.ssim_gray(Ls.mean(axis=-1).astype(np.float32),
                        Ts.mean(axis=-1).astype(np.float32))
    return mae, float(ssim)


def run_sample(data_dir, name, out_rows, panels):
    d = os.path.join(data_dir, name)
    s = rb.load_sample(d)
    T, h = s["T"], s["h"]
    truth = s["struct_truth"]
    B = s["struct_B"]
    meanB = B.reshape(-1, 3).mean(axis=0)

    # --- baselines, reproduced with 045's exact code path ---
    best_t1 = min(((sm,) + score(rb.reconstruct(s, "struct", sm, 0.0, False), truth)
                   for sm in SIGMA_MAX_GRID), key=lambda r: r[1])
    t1_sigma, t1_mae, t1_ssim = best_t1
    best_t2 = min(((g,) + score(rb.reconstruct(s, "struct", t1_sigma, g, False), truth)
                   for g in rb.LENS_GAIN_GRID), key=lambda r: r[1])
    t2_gain, t2_mae, t2_ssim = best_t2

    # --- t2b: joint (sigma_l, alpha, sigma_max) ---
    best = None
    for sl in SIGMA_L_GRID:
        for al in ALPHA_GRID:
            if al == 0.0:
                Bw = B
            else:
                mx, my = lens_warp_maps_band(s, al, sl)
                Bw = cv2.remap(B, mx, my, cv2.INTER_LINEAR,
                               borderMode=cv2.BORDER_REPLICATE)
            stack = rb.blur_stack(Bw, rb.SIGMA_LEVELS) if True else None
            for sm in SIGMA_MAX_GRID:
                if sm > 0:
                    Bb = rb.variable_blur(stack, rb.SIGMA_LEVELS, sm * h)
                else:
                    Bb = Bw
                L = T * (h[..., None] * meanB[None, None] + (1.0 - h[..., None]) * Bb)
                mae, ssim = score(L, truth)
                if best is None or mae < best["mae"]:
                    best = {"sigma_l": sl, "alpha": al, "sigma_max": sm,
                            "mae": mae, "ssim": ssim, "L": L}
            if al == 0.0:
                break  # alpha=0 identical for every sigma_l; skip repeats
    row = {"sample": name,
           "t1": {"sigma_max": t1_sigma, "mae": round(t1_mae, 2), "ssim": round(t1_ssim, 4)},
           "t2_fullband": {"gain": t2_gain, "mae": round(t2_mae, 2), "ssim": round(t2_ssim, 4)},
           "t2b": {k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in best.items() if k != "L"}}
    out_rows.append(row)
    print(json.dumps(row))
    # panel: truth | t1 | t2b | |err t1|x5 | |err t2b|x5
    Ls_t1 = rb.lin_to_srgb(np.clip(rb.reconstruct(s, "struct", t1_sigma, 0.0, False), 0, None))
    Ls_2b = rb.lin_to_srgb(np.clip(best["L"], 0, None))
    Ts = rb.lin_to_srgb(np.clip(truth, 0, None))
    e1 = np.clip(np.abs(Ls_t1 - Ts) * 5, 0, 1)
    e2 = np.clip(np.abs(Ls_2b - Ts) * 5, 0, 1)
    strip = np.concatenate([Ts, Ls_t1, Ls_2b, e1, e2], axis=1)
    small = cv2.resize(strip, (0, 0), fx=0.35, fy=0.35, interpolation=cv2.INTER_AREA)
    panels.append((name, (np.clip(small, 0, 1) * 255).astype(np.uint8)))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.expanduser(
        "~/Documents/vitrai-datasets/oracle45_data"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "results", "054"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rows, panels = [], []
    for name in SAMPLES:
        run_sample(args.data, name, rows, panels)
    json.dump(rows, open(os.path.join(args.out, "relief_lens_054_metrics.json"), "w"),
              indent=1)
    W = max(p.shape[1] for _, p in panels)
    board = []
    for name, p in panels:
        bar = np.zeros((22, W, 3), np.uint8)
        cv2.putText(bar, f"{name}   truth | t1 sigma-only | t2b phi-lens | err_t1 x5 | err_t2b x5",
                    (6, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
        pad = np.zeros((p.shape[0], W - p.shape[1], 3), np.uint8)
        board += [bar, np.concatenate([p, pad], axis=1)]
    cv2.imwrite(os.path.join(args.out, "board_054.jpg"),
                np.concatenate(board, axis=0)[..., ::-1],
                [cv2.IMWRITE_JPEG_QUALITY, 88])
    print("board ->", os.path.join(args.out, "board_054.jpg"))


if __name__ == "__main__":
    main()
