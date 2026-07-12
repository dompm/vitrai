"""Report 039: measure the REBUILT streak recipes on the same metrics used for
the real exemplars (streak_exemplars_039.py) and check gt_h structure. Prints a
before/after-comparable table and the srgb-encoded gt_h stats (the maintainer's
'near-uniform white' concern)."""
import sys, types, os, json
sys.modules["bpy"] = types.ModuleType("bpy")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import numpy as np
import generate_synthetic as gs
from streak_exemplars_039 import (srgb_to_lab, high_freq_energy_fraction,
    structure_tensor_coherence, edge_bimodality, two_mode_color)

LUM = np.array([0.2126, 0.7152, 0.0722])
RESULTS = os.path.join(os.path.dirname(__file__), "..", "results", "039")


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def measure_recipe(recipe, seed):
    T, h, *_ = gs.author_glass_arrays(recipe, size=384, seed=seed)
    rgb = lin_to_srgb(T)            # authored T -> displayed sRGB (what a photo shows)
    lab = srgb_to_lab(rgb)
    L = lab[..., 0]
    C = np.hypot(lab[..., 1], lab[..., 2])
    luma = rgb @ LUM
    coh, _ = structure_tensor_coherence(luma)
    he = lin_to_srgb(h)            # gt_h as written to disk (sRGB-encoded)
    out = {
        "L_p50": float(np.median(L)),
        "L_range": float(np.percentile(L, 95) - np.percentile(L, 5)),
        "C_p50": float(np.median(C)), "C_p95": float(np.percentile(C, 95)),
        "hf": high_freq_energy_fraction(luma), "coh": coh,
        "gt_h_std": float(he.std()), "gt_h_p50": float(np.median(he)),
        "gt_h_frac_white": float((he > 0.85).mean()),
    }
    out.update({k: two_mode_color(lab)[k] for k in ["delta_ab"]})
    out.update({k: edge_bimodality(luma)[k] for k in ["bimodality_p99_p50"]})
    return out


def main():
    seeds = [42, 101, 202, 303, 404]
    real = json.load(open(os.path.join(RESULTS, "exemplar_summary.json")))["overall"]
    print(f"{'recipe':<22}{'L50':>6}{'Lrng':>6}{'C50':>6}{'C95':>6}{'hf':>7}{'coh':>6}"
          f"{'dab':>6}{'bimod':>7}{'ghStd':>7}{'gh50':>6}{'ghWht':>7}")
    print(f"{'REAL(overall)':<22}{real['L_p50']:>6.0f}{real['L_range']:>6.0f}"
          f"{real['C_p50']:>6.0f}{real['C_p95']:>6.0f}{real['hf_energy_frac']:>7.3f}"
          f"{real['coherence']:>6.2f}{real['delta_ab']:>6.0f}{real['bimodality_p99_p50']:>7.1f}"
          f"{'-':>7}{'-':>6}{'-':>7}")
    print("-" * 100)
    allrows = {}
    for recipe in ["streaky-mix", "streaky-fine-texture", "wispy-white"]:
        rows = [measure_recipe(recipe, s) for s in seeds]
        agg = {k: float(np.mean([r[k] for r in rows])) for k in rows[0]}
        allrows[recipe] = agg
        print(f"{recipe:<22}{agg['L_p50']:>6.0f}{agg['L_range']:>6.0f}"
              f"{agg['C_p50']:>6.0f}{agg['C_p95']:>6.0f}{agg['hf']:>7.3f}"
              f"{agg['coh']:>6.2f}{agg['delta_ab']:>6.0f}{agg['bimodality_p99_p50']:>7.1f}"
              f"{agg['gt_h_std']:>7.3f}{agg['gt_h_p50']:>6.2f}{agg['gt_h_frac_white']:>7.2f}")
    json.dump(allrows, open(os.path.join(RESULTS, "rebuild_stats.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
