import type { LampConfig } from '../types';

// Two flat-pattern layouts for a lamp, chosen by config.smooth:
//   - 'faceted' (default): one strip per facet column, side by side. Each strip
//     is the column of tier trapezoids, geometrically accurate per facet.
//   - 'smooth': each tier unrolls to its true continuous shape (rectangle for a
//     cylinder, annular sector for a cone), stacked centered. Treats the lamp
//     as a curved surface; facetCount is for visualization only.

export type UnrolledLamp =
  | { mode: 'faceted'; width: number; height: number; strips: UnrolledStrip[] }
  | { mode: 'smooth'; width: number; height: number; tiers: SmoothTier[] };

export interface UnrolledStrip {
  facetIdx: number;
  centerX: number;
  outline: [number, number][];
  tierSeams: { x1: number; y1: number; x2: number; y2: number }[];
  tiers: StripTier[];
}

export interface StripTier {
  tierIdx: number;
  topY: number;
  botY: number;
  topChord: number;
  botChord: number;
}

export interface SmoothTier {
  tierIdx: number;
  outline: [number, number][];
  meta: SmoothTierMeta;
}

export type SmoothTierMeta =
  | {
      type: 'cylinder';
      leftX: number;
      topY: number;
      width: number;
      height: number;
    }
  | {
      type: 'sector';
      apexX: number;
      apexY: number;
      bisectorSign: 1 | -1;
      L_top: number;
      L_bot: number;
      theta: number;
    };

// Maps a pattern-coord point onto the lamp surface.
//   - 'faceted' mode: returns the (tierIdx, facetIdx) of the strip + tier the
//     point lies in, plus (u, v) inside that flat trapezoid for bilinear.
//   - 'smooth' mode: returns (tierIdx, theta01, v) where theta01 is 0→1 around
//     the full lamp circumference. theta_3D = theta01 * 2π.
export type SurfaceMapping =
  | { mode: 'faceted'; tierIdx: number; facetIdx: number; u: number; v: number }
  | { mode: 'smooth'; tierIdx: number; theta01: number; v: number };

const PAD = 40;
const STRIP_GAP = 12;
const SECTOR_STEPS = 64;

export function computeUnrolledLamp(config: LampConfig | undefined | null): UnrolledLamp {
  if (!config || config.profilePoints.length < 2) {
    return { mode: 'faceted', width: 800, height: 600, strips: [] };
  }
  if (config.smooth) return computeSmoothLayout(config);
  return computeFacetedLayout(config);
}

// ─── Faceted layout (one strip per facet column) ────────────────────────
function computeFacetedLayout(config: LampConfig): Extract<UnrolledLamp, { mode: 'faceted' }> {
  const { facetCount: N, profilePoints } = config;
  if (N < 3) return { mode: 'faceted', width: 800, height: 600, strips: [] };
  const sinPiN = Math.sin(Math.PI / N);

  const tierGeom: { topChord: number; botChord: number; flatH: number }[] = [];
  let maxChord = 0;
  for (let t = 0; t < profilePoints.length - 1; t++) {
    const Rt = profilePoints[t].r;
    const Rb = profilePoints[t + 1].r;
    const H = profilePoints[t + 1].y - profilePoints[t].y;
    const topChord = 2 * Rt * sinPiN;
    const botChord = 2 * Rb * sinPiN;
    const L = Math.hypot(Rb - Rt, H);
    const flatH = Math.sqrt(Math.max(0, L * L - ((botChord - topChord) / 2) ** 2));
    tierGeom.push({ topChord, botChord, flatH });
    maxChord = Math.max(maxChord, topChord, botChord);
  }

  const stripWidth = maxChord;
  const totalStripsW = N * stripWidth + (N - 1) * STRIP_GAP;
  const totalStripH = tierGeom.reduce((acc, g) => acc + g.flatH, 0);
  const width = totalStripsW + 2 * PAD;
  const height = totalStripH + 2 * PAD;

  const strips: UnrolledStrip[] = [];
  for (let i = 0; i < N; i++) {
    const centerX = PAD + stripWidth / 2 + i * (stripWidth + STRIP_GAP);
    const tiers: StripTier[] = [];
    let cumY = PAD;
    for (let t = 0; t < tierGeom.length; t++) {
      const g = tierGeom[t];
      tiers.push({
        tierIdx: t,
        topY: cumY,
        botY: cumY + g.flatH,
        topChord: g.topChord,
        botChord: g.botChord,
      });
      cumY += g.flatH;
    }

    const outline: [number, number][] = [];
    outline.push([centerX - tiers[0].topChord / 2, tiers[0].topY]);
    outline.push([centerX + tiers[0].topChord / 2, tiers[0].topY]);
    for (const tier of tiers) {
      outline.push([centerX + tier.botChord / 2, tier.botY]);
    }
    outline.push([centerX - tiers[tiers.length - 1].botChord / 2, tiers[tiers.length - 1].botY]);
    for (let t = tiers.length - 1; t >= 0; t--) {
      outline.push([centerX - tiers[t].topChord / 2, tiers[t].topY]);
    }

    const tierSeams: UnrolledStrip['tierSeams'] = [];
    for (let t = 1; t < tiers.length; t++) {
      const seamChord = tiers[t].topChord;
      const y = tiers[t].topY;
      tierSeams.push({
        x1: centerX - seamChord / 2, y1: y,
        x2: centerX + seamChord / 2, y2: y,
      });
    }

    strips.push({ facetIdx: i, centerX, outline, tierSeams, tiers });
  }

  return { mode: 'faceted', width, height, strips };
}

// ─── Smooth layout (one continuous shape per tier) ──────────────────────
function computeSmoothLayout(config: LampConfig): Extract<UnrolledLamp, { mode: 'smooth' }> {
  const { profilePoints } = config;

  // First pass: lay out each tier at centerX=0 with the tier's centerline-top at cumTop.
  type Computed = {
    outline: [number, number][];
    meta: SmoothTierMeta;
  };
  const computed: Computed[] = [];
  let cumTop = 0;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

  for (let t = 0; t < profilePoints.length - 1; t++) {
    const Rt = profilePoints[t].r;
    const Rb = profilePoints[t + 1].r;
    const H = profilePoints[t + 1].y - profilePoints[t].y;

    if (Math.abs(Rt - Rb) < 1e-6) {
      // Cylinder: rectangle of width 2πR, height H.
      const width = 2 * Math.PI * Rt;
      const topY = cumTop;
      const botY = cumTop + H;
      const leftX = -width / 2;
      const outline: [number, number][] = [
        [leftX, topY],
        [leftX + width, topY],
        [leftX + width, botY],
        [leftX, botY],
      ];
      computed.push({
        outline,
        meta: { type: 'cylinder', leftX, topY, width, height: H },
      });
      for (const [x, y] of outline) {
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      }
      cumTop = botY;
    } else {
      // Cone frustum: annular sector. Apex on the small-radius side.
      const L = Math.hypot(Rb - Rt, H);
      const sinAlpha = Math.abs(Rb - Rt) / L;
      const L_top = Rt / sinAlpha;
      const L_bot = Rb / sinAlpha;
      const theta = 2 * Math.PI * sinAlpha;
      const bisectorSign: 1 | -1 = Rt < Rb ? +1 : -1;
      // Anchor the top-arc centerline at (0, cumTop).
      const apexY = cumTop - bisectorSign * L_top;

      // Approximate the sector outline with SECTOR_STEPS points along each arc.
      const topArc: [number, number][] = [];
      const botArc: [number, number][] = [];
      for (let k = 0; k <= SECTOR_STEPS; k++) {
        const a = -theta / 2 + (k / SECTOR_STEPS) * theta;
        const dx = bisectorSign * Math.sin(a);
        const dy = bisectorSign * Math.cos(a);
        topArc.push([L_top * dx, apexY + L_top * dy]);
        botArc.push([L_bot * dx, apexY + L_bot * dy]);
      }
      const outline: [number, number][] = [
        ...topArc,
        ...botArc.slice().reverse(),
      ];
      computed.push({
        outline,
        meta: { type: 'sector', apexX: 0, apexY, bisectorSign, L_top, L_bot, theta },
      });
      for (const [x, y] of outline) {
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      }
      // Next tier's centerline-top sits at cumTop + L (slant length along the bisector).
      cumTop += L;
    }
  }

  // Shift to (PAD, PAD).
  const dx = PAD - minX;
  const dy = PAD - minY;
  const width = (maxX - minX) + 2 * PAD;
  const height = (maxY - minY) + 2 * PAD;

  const tiers: SmoothTier[] = computed.map((c, idx) => {
    const outline = c.outline.map(([x, y]): [number, number] => [x + dx, y + dy]);
    let meta: SmoothTierMeta;
    if (c.meta.type === 'cylinder') {
      meta = { ...c.meta, leftX: c.meta.leftX + dx, topY: c.meta.topY + dy };
    } else {
      meta = { ...c.meta, apexX: c.meta.apexX + dx, apexY: c.meta.apexY + dy };
    }
    return { tierIdx: idx, outline, meta };
  });

  return { mode: 'smooth', width, height, tiers };
}

// ─── Reverse projection: 2D pattern → surface mapping ───────────────────
export function patternToSurface(
  px: number,
  py: number,
  unrolled: UnrolledLamp,
): SurfaceMapping | null {
  if (unrolled.mode === 'faceted') {
    for (const strip of unrolled.strips) {
      const cx = strip.centerX;
      for (const tier of strip.tiers) {
        if (py < tier.topY || py > tier.botY) continue;
        const vy = (py - tier.topY) / Math.max(1e-6, tier.botY - tier.topY);
        const widthAtV = tier.topChord * (1 - vy) + tier.botChord * vy;
        const leftAtV = cx - widthAtV / 2;
        const u = (px - leftAtV) / Math.max(1e-6, widthAtV);
        if (u < 0 || u > 1) continue;
        return { mode: 'faceted', tierIdx: tier.tierIdx, facetIdx: strip.facetIdx, u, v: vy };
      }
    }
    return null;
  }

  // smooth
  for (const tier of unrolled.tiers) {
    const m = tier.meta;
    if (m.type === 'cylinder') {
      if (px < m.leftX || px > m.leftX + m.width) continue;
      if (py < m.topY || py > m.topY + m.height) continue;
      const theta01 = (px - m.leftX) / m.width;
      const v = (py - m.topY) / m.height;
      return { mode: 'smooth', tierIdx: tier.tierIdx, theta01, v };
    }
    // sector
    const dx = px - m.apexX;
    const dy = py - m.apexY;
    const d = Math.hypot(dx, dy);
    if (d < 1e-6) continue;
    if (d < m.L_top - 0.5 || d > m.L_bot + 0.5) continue;
    const angleRel = Math.atan2(m.bisectorSign * dx, m.bisectorSign * dy);
    if (angleRel < -m.theta / 2 || angleRel > m.theta / 2) continue;
    const theta01 = (angleRel + m.theta / 2) / m.theta;
    const v = (d - m.L_top) / Math.max(1e-6, m.L_bot - m.L_top);
    const vClamped = Math.max(0, Math.min(1, v));
    return { mode: 'smooth', tierIdx: tier.tierIdx, theta01, v: vClamped };
  }
  return null;
}

// Project the cursor onto the closest seam line, if within thresholdPx (screen px).
export function findLampEdgeSnap(
  cursor: [number, number],
  unrolled: UnrolledLamp,
  effectiveScale: number,
  thresholdPx: number,
): [number, number] | null {
  let bestPt: [number, number] | null = null;
  let bestDist = thresholdPx;

  const tryProject = (ax: number, ay: number, bx: number, by: number) => {
    const dx = bx - ax;
    const dy = by - ay;
    const len2 = dx * dx + dy * dy;
    if (len2 < 1e-6) return;
    const t = Math.max(0, Math.min(1, ((cursor[0] - ax) * dx + (cursor[1] - ay) * dy) / len2));
    const px = ax + t * dx;
    const py = ay + t * dy;
    const dist = Math.hypot(px - cursor[0], py - cursor[1]) * effectiveScale;
    if (dist < bestDist) {
      bestDist = dist;
      bestPt = [px, py];
    }
  };

  if (unrolled.mode === 'faceted') {
    for (const strip of unrolled.strips) {
      const o = strip.outline;
      for (let i = 0; i < o.length; i++) {
        const a = o[i];
        const b = o[(i + 1) % o.length];
        tryProject(a[0], a[1], b[0], b[1]);
      }
      for (const s of strip.tierSeams) tryProject(s.x1, s.y1, s.x2, s.y2);
    }
  } else {
    for (const tier of unrolled.tiers) {
      const o = tier.outline;
      for (let i = 0; i < o.length; i++) {
        const a = o[i];
        const b = o[(i + 1) % o.length];
        tryProject(a[0], a[1], b[0], b[1]);
      }
    }
  }

  return bestPt;
}

// All snap-worthy corners — strip/tier outline vertices and (faceted) tier seam endpoints.
export function getLampSnapPoints(unrolled: UnrolledLamp): [number, number][] {
  const seen = new Set<string>();
  const out: [number, number][] = [];
  const push = (x: number, y: number) => {
    const key = `${x.toFixed(2)},${y.toFixed(2)}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push([x, y]);
  };
  if (unrolled.mode === 'faceted') {
    for (const strip of unrolled.strips) {
      for (const [x, y] of strip.outline) push(x, y);
      for (const s of strip.tierSeams) {
        push(s.x1, s.y1);
        push(s.x2, s.y2);
      }
    }
  } else {
    for (const tier of unrolled.tiers) {
      for (const [x, y] of tier.outline) push(x, y);
    }
  }
  return out;
}
