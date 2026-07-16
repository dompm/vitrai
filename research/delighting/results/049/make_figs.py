"""Schematic figures for report 049 (glass physics primer).
Two small PNGs, no data — pure diagrams. Run with the repo venv python.
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle

INK = "#1a1a1a"
GLASS = "#bcd6e6"
REFL = "#c9482e"   # reflected
REFR = "#2e6fc9"   # refracted / transmitted
SCAT = "#7a3fb0"   # scattered
ABS = "#8a8a8a"


def arrow(ax, p0, p1, color, lw=2.2, ls="-", alpha=1.0):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=14,
                                 color=color, lw=lw, linestyle=ls, alpha=alpha,
                                 shrinkA=0, shrinkB=0))


# ---------------------------------------------------------------- Figure 1
# A ray meets a glass slab: reflect + refract, then absorb / scatter / transmit.
fig, ax = plt.subplots(figsize=(7.4, 4.6), dpi=150)

# slab
slab = Rectangle((3.0, 0.2), 2.2, 5.6, facecolor=GLASS, edgecolor=INK, lw=1.4, alpha=0.55)
ax.add_patch(slab)
ax.text(4.1, 5.95, "glass slab", ha="center", fontsize=9, color=INK, style="italic")

# surface normal (dashed) at hit point
hit = (3.0, 3.4)
ax.plot([hit[0]-1.0, hit[0]+1.0], [hit[1], hit[1]], color=INK, lw=0.8, ls=":", alpha=0.5)
ax.text(2.05, 3.5, "surface normal", fontsize=7.5, color=INK, alpha=0.6)

# incident ray (from upper-left, steep-ish)
inc0 = (0.5, 5.5)
arrow(ax, inc0, hit, INK, lw=2.6)
ax.text(1.1, 5.2, "incident light", fontsize=9, color=INK)

# reflected ray (mirror about normal, back up-right off surface)
arrow(ax, hit, (0.9, 1.4), REFL, lw=2.2)
ax.text(0.35, 1.05, "reflected\n(Fresnel: more at\ngrazing angles)", fontsize=8, color=REFL, va="top")

# refracted ray inside glass (bent toward normal), traveling to exit face
exitp = (5.2, 2.35)
arrow(ax, hit, exitp, REFR, lw=2.2)
ax.text(3.35, 4.15, "refracted\n(Snell: bends,\nshifts backdrop)", fontsize=8, color=REFR)

# absorption: fade markers along the in-glass path
for t, a in [(0.30, 0.8), (0.55, 0.55), (0.8, 0.32)]:
    px = hit[0] + t * (exitp[0]-hit[0]); py = hit[1] + t * (exitp[1]-hit[1])
    ax.plot(px, py, "o", color=ABS, ms=6, alpha=a)
ax.text(3.18, 1.35, "absorption along the path\n(Beer-Lambert: exponential\nin thickness = the color)",
        fontsize=7.5, color="#5a5a5a", va="center", ha="left")

# transmitted ray exits (continues, dimmer)
arrow(ax, exitp, (6.9, 1.75), REFR, lw=1.8, alpha=0.65)
ax.text(6.0, 1.15, "transmitted\n(dimmer, tinted)", fontsize=8, color=REFR, alpha=0.85)

# scattering: a couple of side rays off the in-glass path (opal glass)
mid = (hit[0] + 0.5*(exitp[0]-hit[0]), hit[1] + 0.5*(exitp[1]-hit[1]))
arrow(ax, mid, (5.4, 4.6), SCAT, lw=1.3, alpha=0.8)
arrow(ax, mid, (5.3, 0.9), SCAT, lw=1.3, alpha=0.8)
ax.text(5.5, 4.75, "scattering (opal:\nglows + blurs)", fontsize=7.5, color=SCAT)

ax.set_xlim(0, 7.4); ax.set_ylim(0, 6.3)
ax.set_aspect("equal"); ax.axis("off")
ax.set_title("What light does at and inside a glass sheet", fontsize=11, color=INK)
fig.tight_layout()
fig.savefig("fig1_slab_split.png", dpi=150, bbox_inches="tight")
plt.close(fig)


# ---------------------------------------------------------------- Figure 2
# Fresnel reflectance vs incidence angle for glass (n=1.5), + Schlick approx.
fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
n1, n2 = 1.0, 1.5
th = np.radians(np.linspace(0, 89.5, 400))
ct1 = np.cos(th)
st2 = (n1/n2) * np.sin(th)
ct2 = np.sqrt(1 - st2**2)
rs = ((n1*ct1 - n2*ct2) / (n1*ct1 + n2*ct2))**2
rp = ((n1*ct2 - n2*ct1) / (n1*ct2 + n2*ct1))**2
R = 0.5 * (rs + rp)               # unpolarized exact Fresnel
R0 = ((n1-n2)/(n1+n2))**2         # normal-incidence reflectance ~= 0.04
schlick = R0 + (1-R0) * (1-ct1)**5

deg = np.degrees(th)
ax.plot(deg, R, color=REFL, lw=2.4, label="exact Fresnel (unpolarized)")
ax.plot(deg, schlick, color=REFR, lw=1.8, ls="--", label="Schlick approximation")
ax.axhline(R0, color=INK, lw=0.8, ls=":", alpha=0.6)
ax.text(2, R0+0.03, f"R0 ~= {R0:.2f}  (4% straight-on)", fontsize=8.5, color=INK)
ax.annotate("near grazing,\nglass becomes a mirror",
            xy=(85, 0.85), xytext=(48, 0.72), fontsize=8.5, color=REFL,
            arrowprops=dict(arrowstyle="->", color=REFL, lw=1.2))

ax.set_xlabel("angle of incidence  (0 deg = looking straight through)", fontsize=9.5)
ax.set_ylabel("fraction of light reflected", fontsize=9.5)
ax.set_xlim(0, 90); ax.set_ylim(0, 1.02)
ax.set_title("Fresnel: reflection rises sharply at grazing angles (glass, n=1.5)",
             fontsize=10.5, color=INK)
ax.legend(fontsize=8.5, loc="upper left")
ax.grid(alpha=0.25)
fig.tight_layout()
fig.savefig("fig2_fresnel_curve.png", dpi=150, bbox_inches="tight")
plt.close(fig)

print("wrote fig1_slab_split.png, fig2_fresnel_curve.png")
