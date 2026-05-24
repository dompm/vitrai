import type { LampConfig } from '../types';

// New layout: one strip per facet column, side by side with a small gap.
// Each strip is a vertical stack of one trapezoid (or rectangle) per tier.
// Each trapezoid is a true isoceles trapezoid that matches what would be cut
// from glass — print-accurate.

export interface UnrolledLamp {
  width: number;
  height: number;
  strips: UnrolledStrip[];
}

export interface UnrolledStrip {
  facetIdx: number;
  centerX: number;
  // Closed polygon outline of the entire strip (stack of trapezoids).
  outline: [number, number][];
  // Horizontal seams between adjacent tiers within this strip.
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

const PAD = 40;
const STRIP_GAP = 12; // mm — visual separation between adjacent strips

export function computeUnrolledLamp(config: LampConfig | undefined | null): UnrolledLamp {
  if (!config || config.profilePoints.length < 2 || config.facetCount < 3) {
    return { width: 800, height: 600, strips: [] };
  }
  const { facetCount: N, profilePoints } = config;
  const sinPiN = Math.sin(Math.PI / N);

  // Per-tier: chord widths and flat vertical extent.
  const tierGeom: { topChord: number; botChord: number; flatH: number }[] = [];
  let maxChord = 0;
  for (let t = 0; t < profilePoints.length - 1; t++) {
    const Rt = profilePoints[t].r;
    const Rb = profilePoints[t + 1].r;
    const H = profilePoints[t + 1].y - profilePoints[t].y;
    const topChord = 2 * Rt * sinPiN;
    const botChord = 2 * Rb * sinPiN;
    const L = Math.hypot(Rb - Rt, H);
    // Flat vertical height of the trapezoid when its top/bot edges sit horizontally.
    const flatH = Math.sqrt(Math.max(0, L * L - ((botChord - topChord) / 2) ** 2));
    tierGeom.push({ topChord, botChord, flatH });
    maxChord = Math.max(maxChord, topChord, botChord);
  }

  const stripWidth = maxChord;
  const totalStripsW = N * stripWidth + (N - 1) * STRIP_GAP;
  const totalStripH = tierGeom.reduce((acc, t) => acc + t.flatH, 0);
  const width = totalStripsW + 2 * PAD;
  const height = totalStripH + 2 * PAD;

  const strips: UnrolledStrip[] = [];
  for (let i = 0; i < N; i++) {
    const centerX = PAD + stripWidth / 2 + i * (stripWidth + STRIP_GAP);

    // Build the stack of tier trapezoids vertically.
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

    // Outline: down the right slant through every tier, then across the bottom,
    // up the left slant in reverse.
    const outline: [number, number][] = [];
    // Top edge (left to right).
    outline.push([centerX - tiers[0].topChord / 2, tiers[0].topY]);
    outline.push([centerX + tiers[0].topChord / 2, tiers[0].topY]);
    // Right slant: walk top→bot for each tier (each tier contributes bot-right corner).
    for (const tier of tiers) {
      outline.push([centerX + tier.botChord / 2, tier.botY]);
    }
    // Bottom edge (right to left).
    outline.push([centerX - tiers[tiers.length - 1].botChord / 2, tiers[tiers.length - 1].botY]);
    // Left slant: walk bot→top for each tier in reverse.
    for (let t = tiers.length - 1; t >= 0; t--) {
      outline.push([centerX - tiers[t].topChord / 2, tiers[t].topY]);
    }

    // Tier seams between consecutive tiers within this strip.
    const tierSeams: UnrolledStrip['tierSeams'] = [];
    for (let t = 1; t < tiers.length; t++) {
      const seamChord = tiers[t].topChord; // = tiers[t-1].botChord
      const y = tiers[t].topY;
      tierSeams.push({
        x1: centerX - seamChord / 2, y1: y,
        x2: centerX + seamChord / 2, y2: y,
      });
    }

    strips.push({ facetIdx: i, centerX, outline, tierSeams, tiers });
  }

  return { width, height, strips };
}

// Reverse-project a pattern-space point onto a strip's tier trapezoid.
// u runs 0→1 left slant → right slant within the trapezoid at the point's height,
// v runs 0→1 top → bottom of the tier.
export function patternToFacetUV(
  px: number,
  py: number,
  unrolled: UnrolledLamp,
): { tierIdx: number; facetIdx: number; u: number; v: number } | null {
  for (const strip of unrolled.strips) {
    const cx = strip.centerX;
    for (const tier of strip.tiers) {
      if (py < tier.topY || py > tier.botY) continue;
      const vy = (py - tier.topY) / Math.max(1e-6, tier.botY - tier.topY);
      const widthAtV = tier.topChord * (1 - vy) + tier.botChord * vy;
      const leftAtV = cx - widthAtV / 2;
      const u = (px - leftAtV) / Math.max(1e-6, widthAtV);
      if (u < 0 || u > 1) continue;
      return { tierIdx: tier.tierIdx, facetIdx: strip.facetIdx, u, v: vy };
    }
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

  for (const strip of unrolled.strips) {
    const o = strip.outline;
    for (let i = 0; i < o.length; i++) {
      const a = o[i];
      const b = o[(i + 1) % o.length];
      tryProject(a[0], a[1], b[0], b[1]);
    }
    for (const s of strip.tierSeams) tryProject(s.x1, s.y1, s.x2, s.y2);
  }

  return bestPt;
}

// All snap-worthy corners — strip outline vertices + tier seam endpoints.
export function getLampSnapPoints(unrolled: UnrolledLamp): [number, number][] {
  const seen = new Set<string>();
  const out: [number, number][] = [];
  const push = (x: number, y: number) => {
    const key = `${x.toFixed(2)},${y.toFixed(2)}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push([x, y]);
  };
  for (const strip of unrolled.strips) {
    for (const [x, y] of strip.outline) push(x, y);
    for (const s of strip.tierSeams) {
      push(s.x1, s.y1);
      push(s.x2, s.y2);
    }
  }
  return out;
}
