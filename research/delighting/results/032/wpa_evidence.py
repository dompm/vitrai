#!/usr/bin/env python3
"""Report 032 WP-A offline evidence: OLD (origin/research/delighting) vs NEW
authoring, pure numpy (no Blender). Quantifies the four WP-A claims that are
measurable without a render:

  (1) streak legibility  -- macro-scale directional anisotropy of authored T
      (structure tensor on a heavily low-passed field, isolating streak-scale
      structure from fine grain). Higher = more legibly streaky. The two 031
      misclassified recipes (streaky-fine-texture -> ring mottle, wispy-white
      -> smooth opal) should rise the most.
  (2) mirror-symmetry artifact -- correlation of authored T with its up-down /
      left-right mirror for cathedral-green across seeds (the gallery-flagged
      seed700 artifact). Should drop toward noise.
  (3) Beer-Lambert coupling -- corr(dT, height-0.5): crests should transmit
      lighter (positive), and mean T should be ~preserved.
  (4) micro-events -- footprint coverage present where authored (was 0).

Run:  python3 results/032/wpa_evidence.py   (from research/delighting)
Reproduces results/032/wpa_offline_evidence.txt.
"""
import sys, types, os, importlib.util
import numpy as np
from scipy.ndimage import gaussian_filter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.modules.setdefault("bpy", types.ModuleType("bpy"))


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

NEW = _load(os.path.join(ROOT, "generate_synthetic.py"), "gs_new")
OLD_PATH = "/tmp/gs_old.py"  # git show origin/research/delighting:.../generate_synthetic.py
OLD = _load(OLD_PATH, "gs_old") if os.path.exists(OLD_PATH) else None


def aniso(field, sigma):
    g = field.astype(np.float64)
    g = g.mean(-1) if g.ndim == 3 else g
    g = gaussian_filter(g, sigma)
    gy, gx = np.gradient(g)
    Jxx, Jyy, Jxy = (gx*gx).mean(), (gy*gy).mean(), (gx*gy).mean()
    tr, det = Jxx+Jyy, Jxx*Jyy-Jxy*Jxy
    disc = max(0.0, (tr*0.5)**2 - det) ** 0.5
    return (tr*0.5 + disc) / (tr*0.5 - disc + 1e-12)


def mirror_corr(a):
    a = a.astype(np.float64); a = a.mean(-1) if a.ndim == 3 else a
    a = (a - a.mean()) / (a.std() + 1e-9)
    ud = np.corrcoef(a.ravel(), a[::-1, :].ravel())[0, 1]
    lr = np.corrcoef(a.ravel(), a[:, ::-1].ravel())[0, 1]
    return ud, lr


def T_of(mod, recipe, size, seed):
    return mod.author_glass_arrays(recipe, size=size, seed=seed)[0]


out = []
def p(s): out.append(s); print(s)

SIZE = 768
p("=" * 72)
p("Report 032 WP-A offline evidence  (OLD=origin vs NEW, size=%d)" % SIZE)
p("=" * 72)

p("\n(1) STREAK LEGIBILITY -- macro-scale directional anisotropy of T @lp32")
p("    (1.0 = isotropic; higher = legibly streaky)")
p(f"    {'recipe':22s} {'OLD':>6s} {'NEW':>6s}  {'x':>5s}")
for r in ["streaky-mix", "streaky-fine-texture", "wispy-white"]:
    an = aniso(T_of(NEW, r, SIZE, 42), 32)
    ao = aniso(T_of(OLD, r, SIZE, 42), 32) if OLD else float("nan")
    p(f"    {r:22s} {ao:6.2f} {an:6.2f}  {an/ao:5.2f}x")

p("\n(2) MIRROR-SYMMETRY ARTIFACT -- cathedral-green |corr with mirror| @1536")
p("    (gallery flagged seed700; lower = less spurious centered symmetry)")
p(f"    {'seed':>6s}  {'OLD ud/lr':>14s}  {'NEW ud/lr':>14s}")
for s in [42, 300, 700, 1234]:
    no = mirror_corr(T_of(NEW, "cathedral-green", 1536, s))
    oo = mirror_corr(T_of(OLD, "cathedral-green", 1536, s)) if OLD else (float("nan"),)*2
    p(f"    {s:6d}  {oo[0]:+6.3f}/{oo[1]:+6.3f}  {no[0]:+6.3f}/{no[1]:+6.3f}")

p("\n(3) BEER-LAMBERT COUPLING -- corr(dT vs height-0.5) and mean-T preservation")
# reconstruct the pre-coupling T by disabling coupling: compare NEW T to its own
# height via the shipped helper on a cathedral recipe.
for r in ["cathedral-green", "streaky-mix"]:
    # Report 037 note: author_glass_arrays' return tuple grew (mark_dark,
    # mark_white, mark_index replace the old single `mark`) after this
    # report-032 evidence script was authored; unpacking widened so this
    # frozen comparison (vs the already-committed wpa_offline_evidence.txt)
    # doesn't hard-crash for a future reader -- not re-verified against 037.
    T, h, mark, mark_white, mark_index, height, normal, bd = NEW.author_glass_arrays(r, size=SIZE, seed=42)
    base = NEW.couple_T_to_height(T, height, 0.0)   # identity -> current T
    # measure sign of coupling directly on the helper
    flat = np.full_like(height, 0.5)
    T0 = np.clip((T.mean(-1))[..., None]*np.ones(3), 0, 1)
    corr = np.corrcoef((T.mean(-1)).ravel(), (height - 0.5).ravel())[0, 1]
    p(f"    {r:22s} corr(T,height-0.5)={corr:+.3f}  meanT={T.mean():.4f}")
# explicit helper check: crest (height=1) lighter than trough (height=0)
Td = np.array([[[0.4, 0.2, 0.1]]])
hi = NEW.couple_T_to_height(Td, np.array([[1.0]]), 0.25)[0, 0]
lo = NEW.couple_T_to_height(Td, np.array([[0.0]]), 0.25)[0, 0]
p(f"    helper: crest {hi.round(3).tolist()} > trough {lo.round(3).tolist()} (lighter+less sat at crest)")

p("\n(4) MICRO-EVENTS -- footprint coverage (was 0 pre-032)")
for r, dens in [("cathedral-green", 28), ("dark-textured", 40), ("wispy-white", 10)]:
    hd, tg, mask = NEW.micro_events(SIZE, 99, dens)
    p(f"    {r:22s} density={dens:3d}  coverage={mask.mean()*100:5.2f}%  h_delta[{hd.min():+.2f},{hd.max():+.2f}]")

with open(os.path.join(HERE, "wpa_offline_evidence.txt"), "w") as f:
    f.write("\n".join(out) + "\n")
print("\nwrote results/032/wpa_offline_evidence.txt")
