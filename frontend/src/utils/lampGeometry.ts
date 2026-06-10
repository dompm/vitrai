import type { LampConfig } from '../types';
import { getSnapFractions } from './snapping';

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
  // Small tolerance so vertices that landed a hair past a strip's edge (e.g. a
  // box-tool release slightly outside the strip outline) still map onto that
  // strip's tier instead of getting dropped from 3D rendering entirely.
  const TOL_Y = 1;        // mm
  const TOL_U = 0.02;     // fraction of strip width
  if (unrolled.mode === 'faceted') {
    for (const strip of unrolled.strips) {
      const cx = strip.centerX;
      for (const tier of strip.tiers) {
        if (py < tier.topY - TOL_Y || py > tier.botY + TOL_Y) continue;
        const tierH = Math.max(1e-6, tier.botY - tier.topY);
        const vy = Math.max(0, Math.min(1, (py - tier.topY) / tierH));
        const widthAtV = tier.topChord * (1 - vy) + tier.botChord * vy;
        const leftAtV = cx - widthAtV / 2;
        const u = (px - leftAtV) / Math.max(1e-6, widthAtV);
        if (u < -TOL_U || u > 1 + TOL_U) continue;
        const uClamped = Math.max(0, Math.min(1, u));
        return { mode: 'faceted', tierIdx: tier.tierIdx, facetIdx: strip.facetIdx, u: uClamped, v: vy };
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
      // Degenerate (zero-size) tiers would yield 0/0 = NaN here.
      const theta01 = m.width > 1e-6 ? (px - m.leftX) / m.width : 0.5;
      const v = m.height > 1e-6 ? (py - m.topY) / m.height : 0.5;
      return { mode: 'smooth', tierIdx: tier.tierIdx, theta01, v };
    }
    // sector
    const dx = px - m.apexX;
    const dy = py - m.apexY;
    const d = Math.hypot(dx, dy);
    if (d < 1e-6) continue;
    // For a contracting tier (Rt > Rb) L_top > L_bot, so the valid band is
    // [min, max] of the two — and v's denominator is legitimately negative
    // (numerator is too); clamping it positive collapsed every point to v=0.
    const dLo = Math.min(m.L_top, m.L_bot);
    const dHi = Math.max(m.L_top, m.L_bot);
    if (d < dLo - 0.5 || d > dHi + 0.5) continue;
    const angleRel = Math.atan2(m.bisectorSign * dx, m.bisectorSign * dy);
    if (angleRel < -m.theta / 2 || angleRel > m.theta / 2) continue;
    const theta01 = (angleRel + m.theta / 2) / m.theta;
    const dDenom = m.L_bot - m.L_top;
    const v = Math.abs(dDenom) < 1e-6 ? 0.5 : (d - m.L_top) / dDenom;
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

export interface LampSnapPoint {
  pt: [number, number];
  label?: string;
}

// All snap-worthy points — strip/tier outline vertices and (faceted) tier seam endpoints, plus fractional edge points.
export function getLampSnapPoints(unrolled: UnrolledLamp, effectiveScale: number, t: (k: string) => string): LampSnapPoint[] {
  const seen = new Set<string>();
  const out: LampSnapPoint[] = [];

  const FRACTIONS = getSnapFractions(t);

  const pushCorner = (x: number, y: number) => {
    const key = `${x.toFixed(2)},${y.toFixed(2)}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ pt: [x, y] });
  };

  const pushEdgeFractions = (ax: number, ay: number, bx: number, by: number) => {
    const lineLen = Math.hypot(bx - ax, by - ay);
    const pixelLen = lineLen * effectiveScale;
    
    const activeFractions = [0, 1]; // corners are always active
    const minGapPx = 32;

    for (const frac of FRACTIONS) {
      const tooClose = activeFractions.some(val => Math.abs(frac.value - val) * pixelLen < minGapPx);
      if (!tooClose) {
        activeFractions.push(frac.value);
        const x = ax + (bx - ax) * frac.value;
        const y = ay + (by - ay) * frac.value;
        const key = `${x.toFixed(2)},${y.toFixed(2)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({ pt: [x, y], label: frac.label });
      }
    }
  };

  if (unrolled.mode === 'faceted') {
    for (const strip of unrolled.strips) {
      const o = strip.outline;
      for (let i = 0; i < o.length; i++) {
        const a = o[i];
        const b = o[(i + 1) % o.length];
        pushCorner(a[0], a[1]);
        pushEdgeFractions(a[0], a[1], b[0], b[1]);
      }
      for (const s of strip.tierSeams) {
        pushCorner(s.x1, s.y1);
        pushCorner(s.x2, s.y2);
        pushEdgeFractions(s.x1, s.y1, s.x2, s.y2);
      }
    }
  } else {
    for (const tier of unrolled.tiers) {
      const o = tier.outline;
      for (let i = 0; i < o.length; i++) {
        const a = o[i];
        const b = o[(i + 1) % o.length];
        pushCorner(a[0], a[1]);
        pushEdgeFractions(a[0], a[1], b[0], b[1]);
      }
    }
  }

  return out;
}

// Robust conversion helpers for reflowing pieces on geometry change.
export function patternToSurfaceRobust(
  px: number,
  py: number,
  unrolled: UnrolledLamp,
  N: number,
): { tierIdx: number; facetIdx: number; u: number; v: number; theta01: number } {
  let tierIdx = 0;
  let v = 0.5;

  if (unrolled.mode === 'faceted') {
    let bestTierIdx = 0;
    let bestDistY = Infinity;
    let bestV = 0.5;

    const refStrip = unrolled.strips[0];
    if (refStrip) {
      for (let t = 0; t < refStrip.tiers.length; t++) {
        const tier = refStrip.tiers[t];
        const midY = (tier.topY + tier.botY) / 2;
        const dist = Math.abs(py - midY);
        if (dist < bestDistY) {
          bestDistY = dist;
          bestTierIdx = t;
          const tierH = Math.max(1e-6, tier.botY - tier.topY);
          bestV = Math.max(0, Math.min(1, (py - tier.topY) / tierH));
        }
      }
    }
    tierIdx = bestTierIdx;
    v = bestV;

    let bestFacetIdx = 0;
    let bestDistX = Infinity;
    let bestU = 0.5;

    for (const strip of unrolled.strips) {
      const tier = strip.tiers[tierIdx];
      if (!tier) continue;
      const widthAtV = tier.topChord * (1 - v) + tier.botChord * v;
      const leftAtV = strip.centerX - widthAtV / 2;
      const u = (px - leftAtV) / Math.max(1e-6, widthAtV);
      const uClamped = Math.max(0, Math.min(1, u));
      const dist = Math.abs(px - (strip.centerX + (uClamped - 0.5) * widthAtV));
      if (dist < bestDistX) {
        bestDistX = dist;
        bestFacetIdx = strip.facetIdx;
        bestU = uClamped;
      }
    }

    return {
      tierIdx,
      facetIdx: bestFacetIdx,
      u: bestU,
      v,
      theta01: (bestFacetIdx + bestU) / N,
    };
  } else {
    let bestTierIdx = 0;
    let bestDistY = Infinity;
    let bestV = 0.5;
    let bestTheta01 = 0.5;

    for (let t = 0; t < unrolled.tiers.length; t++) {
      const tier = unrolled.tiers[t];
      const m = tier.meta;
      if (m.type === 'cylinder') {
        const midY = m.topY + m.height / 2;
        const dist = Math.abs(py - midY);
        if (dist < bestDistY) {
          bestDistY = dist;
          bestTierIdx = t;
          // NaN from a zero-size tier would pass straight through min/max.
          bestV = Math.max(0, Math.min(1, (py - m.topY) / Math.max(1e-6, m.height)));
          bestTheta01 = Math.max(0, Math.min(1, (px - m.leftX) / Math.max(1e-6, m.width)));
        }
      } else {
        const dx = px - m.apexX;
        const dy = py - m.apexY;
        const d = Math.hypot(dx, dy);
        const midD = (m.L_top + m.L_bot) / 2;
        const dist = Math.abs(d - midD);
        if (dist < bestDistY) {
          bestDistY = dist;
          bestTierIdx = t;
          // Denominator is negative for contracting tiers; keep its sign
          // (see patternToSurface) or reflow collapses points onto v=0.
          const dDenom = m.L_bot - m.L_top;
          bestV = Math.abs(dDenom) < 1e-6 ? 0.5 : Math.max(0, Math.min(1, (d - m.L_top) / dDenom));
          const angleRel = Math.atan2(m.bisectorSign * dx, m.bisectorSign * dy);
          bestTheta01 = Math.max(0, Math.min(1, (angleRel + m.theta / 2) / m.theta));
        }
      }
    }

    const facetIdxFloat = bestTheta01 * N;
    const facetIdx = Math.min(Math.max(Math.floor(facetIdxFloat), 0), N - 1);
    const u = facetIdxFloat - facetIdx;

    return {
      tierIdx: bestTierIdx,
      facetIdx,
      u,
      v: bestV,
      theta01: bestTheta01,
    };
  }
}

export function surfaceToPatternRobust(
  tierIdx: number,
  facetIdx: number,
  u: number,
  v: number,
  theta01: number,
  unrolled: UnrolledLamp,
  N: number,
): [number, number] {
  if (unrolled.mode === 'faceted') {
    const newFacetIdx = Math.min(Math.max(facetIdx, 0), N - 1);
    const strip = unrolled.strips[newFacetIdx];
    if (!strip) return [0, 0];

    const tIdx = Math.min(Math.max(tierIdx, 0), strip.tiers.length - 1);
    const tier = strip.tiers[tIdx];
    if (!tier) return [0, 0];

    const widthAtV = tier.topChord * (1 - v) + tier.botChord * v;
    const x = strip.centerX + (u - 0.5) * widthAtV;
    const y = tier.topY + v * (tier.botY - tier.topY);
    return [x, y];
  } else {
    const tIdx = Math.min(Math.max(tierIdx, 0), unrolled.tiers.length - 1);
    const tier = unrolled.tiers[tIdx];
    if (!tier) return [0, 0];

    const m = tier.meta;
    if (m.type === 'cylinder') {
      const x = m.leftX + theta01 * m.width;
      const y = m.topY + v * m.height;
      return [x, y];
    } else {
      const d = m.L_top + v * (m.L_bot - m.L_top);
      const angleRel = -m.theta / 2 + theta01 * m.theta;
      const dx = m.bisectorSign * Math.sin(angleRel);
      const dy = m.bisectorSign * Math.cos(angleRel);
      const x = m.apexX + d * dx;
      const y = m.apexY + d * dy;
      return [x, y];
    }
  }
}

export function reflowLampPoints(
  points: [number, number][],
  oldUnrolled: UnrolledLamp,
  newUnrolled: UnrolledLamp,
  oldN: number,
  newN: number,
): [number, number][] {
  return points.map(([px, py]) => {
    const norm = patternToSurfaceRobust(px, py, oldUnrolled, oldN);
    return surfaceToPatternRobust(norm.tierIdx, norm.facetIdx, norm.u, norm.v, norm.theta01, newUnrolled, newN);
  });
}

export function replicatePointToFacet(
  px: number,
  py: number,
  fromFacet: number,
  toFacet: number,
  unrolled: UnrolledLamp,
  N: number,
): [number, number] {
  const norm = patternToSurfaceRobust(px, py, unrolled, N);
  const newFacetIdx = toFacet;
  const newTheta01 = (norm.theta01 + (toFacet - fromFacet) / N + 1.0) % 1.0;
  return surfaceToPatternRobust(norm.tierIdx, newFacetIdx, norm.u, norm.v, newTheta01, unrolled, N);
}
