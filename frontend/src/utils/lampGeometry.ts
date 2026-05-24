import type { LampConfig } from '../types';

export interface UnrolledLamp {
  width: number;
  height: number;
  // One geometrically-correct flat polygon per tier. Tiers are positioned
  // along a shared vertical center axis; corners of adjacent tiers don't
  // generally line up (different sector curvatures), so we render each tier
  // as its own outline rather than one merged polygon.
  tiers: UnrolledTier[];
}

export interface UnrolledTier {
  // Closed polygon outline of the tier in pattern coords.
  outline: [number, number][];
  // Slanted seams between adjacent facets within the tier.
  facetSeams: { x1: number; y1: number; x2: number; y2: number }[];
}

const PAD = 40;

interface TierLayout {
  topPolyline: [number, number][];   // N+1 points across the top edge
  bottomPolyline: [number, number][]; // N+1 points across the bottom edge
  bottomCenterY: number;              // y of the tier's bottom centerline (for stacking)
}

// Lay out a single conical/cylindrical tier in flat pattern coords.
// Top centerline is anchored at (centerX, topY); the tier extends downward.
function unrollTier(
  Rt: number,
  Rb: number,
  H: number,
  N: number,
  centerX: number,
  topY: number,
): TierLayout {
  const sinPiN = Math.sin(Math.PI / N);
  const topChord = 2 * Rt * sinPiN;
  const botChord = 2 * Rb * sinPiN;

  // Cylinder: each facet is a rectangle. Lay them out side-by-side.
  if (Math.abs(Rt - Rb) < 1e-6) {
    const totalW = N * topChord;
    const topPolyline: [number, number][] = [];
    const bottomPolyline: [number, number][] = [];
    for (let k = 0; k <= N; k++) {
      const x = centerX - totalW / 2 + k * topChord;
      topPolyline.push([x, topY]);
      bottomPolyline.push([x, topY + H]);
    }
    return { topPolyline, bottomPolyline, bottomCenterY: topY + H };
  }

  // Cone frustum: each facet fans out from the apex by phiPerFacet radians.
  const L = Math.hypot(Rb - Rt, H);
  const sinAlpha = Math.abs(Rb - Rt) / L;
  const L_top = Rt / sinAlpha;
  const L_bot = Rb / sinAlpha;
  const phi = (2 * Math.PI / N) * sinAlpha;
  const theta = N * phi;

  // bisectorSign +1 = apex above the layout (bisector points down). This is the case when
  // the small-radius end of the cone is at the top. For Rt > Rb (narrows downward), the
  // apex sits below the layout and the bisector points up.
  const bisectorSign = Rt < Rb ? +1 : -1;
  const apexY = topY - bisectorSign * L_top;

  const startAngle = -theta / 2;
  const topPolyline: [number, number][] = [];
  const bottomPolyline: [number, number][] = [];
  for (let k = 0; k <= N; k++) {
    const a = startAngle + k * phi;
    // Radial direction from apex: rotate the bisector vector (0, bisectorSign) by angle a.
    const dx = -bisectorSign * Math.sin(a);
    const dy = bisectorSign * Math.cos(a);
    topPolyline.push([centerX + L_top * dx, apexY + L_top * dy]);
    bottomPolyline.push([centerX + L_bot * dx, apexY + L_bot * dy]);
  }
  // Note: the center of the bottom polyline sits at (centerX, topY + L)
  // regardless of whether bisectorSign is +1 or -1.
  return { topPolyline, bottomPolyline, bottomCenterY: topY + L };
}

export function computeUnrolledLamp(config: LampConfig | undefined | null): UnrolledLamp {
  if (!config || config.profilePoints.length < 2 || config.facetCount < 3) {
    return { width: 800, height: 600, tiers: [] };
  }
  const { facetCount: N, profilePoints } = config;

  // First, lay out each tier with centerX=0 (will be shifted to fit). Track bbox.
  type Computed = TierLayout & { facetSeams: UnrolledTier['facetSeams'] };
  const computed: Computed[] = [];

  let topY = 0;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (let t = 0; t < profilePoints.length - 1; t++) {
    const Rt = profilePoints[t].r;
    const Rb = profilePoints[t + 1].r;
    const H = profilePoints[t + 1].y - profilePoints[t].y;
    const layout = unrollTier(Rt, Rb, H, N, 0, topY);

    // Facet seams = the lines connecting topPolyline[k] to bottomPolyline[k] for k = 1..N-1.
    const facetSeams: UnrolledTier['facetSeams'] = [];
    for (let k = 1; k < N; k++) {
      facetSeams.push({
        x1: layout.topPolyline[k][0], y1: layout.topPolyline[k][1],
        x2: layout.bottomPolyline[k][0], y2: layout.bottomPolyline[k][1],
      });
    }
    computed.push({ ...layout, facetSeams });

    for (const [x, y] of layout.topPolyline) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    for (const [x, y] of layout.bottomPolyline) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    topY = layout.bottomCenterY;
  }

  // Shift everything so the bbox is at (PAD, PAD).
  const dx = PAD - minX;
  const dy = PAD - minY;
  const width = (maxX - minX) + 2 * PAD;
  const height = (maxY - minY) + 2 * PAD;

  const tiers: UnrolledTier[] = computed.map(c => {
    const topShifted: [number, number][] = c.topPolyline.map(([x, y]) => [x + dx, y + dy]);
    const botShifted: [number, number][] = c.bottomPolyline.map(([x, y]) => [x + dx, y + dy]);
    // Outline: top forward, right slant (top-last → bot-last), bottom reverse, left slant (bot-first → top-first).
    const outline: [number, number][] = [
      ...topShifted,
      ...botShifted.slice().reverse(),
    ];
    const facetSeams = c.facetSeams.map(s => ({
      x1: s.x1 + dx, y1: s.y1 + dy,
      x2: s.x2 + dx, y2: s.y2 + dy,
    }));
    return { outline, facetSeams };
  });

  return { width, height, tiers };
}

// Project the cursor onto the closest seam line on the unrolled lamp surface,
// if within thresholdPx in screen pixels. Returns the projection point in
// pattern coords, or null if no seam is close enough.
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

  for (const tier of unrolled.tiers) {
    const o = tier.outline;
    for (let i = 0; i < o.length; i++) {
      const a = o[i];
      const b = o[(i + 1) % o.length];
      tryProject(a[0], a[1], b[0], b[1]);
    }
    for (const s of tier.facetSeams) tryProject(s.x1, s.y1, s.x2, s.y2);
  }

  return bestPt;
}

// All snap-worthy corners of an unrolled lamp surface — polygon outline vertices
// and the endpoints of facet seams.
export function getLampSnapPoints(unrolled: UnrolledLamp): [number, number][] {
  const seen = new Set<string>();
  const out: [number, number][] = [];
  const push = (x: number, y: number) => {
    const key = `${x.toFixed(2)},${y.toFixed(2)}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push([x, y]);
  };
  for (const tier of unrolled.tiers) {
    for (const [x, y] of tier.outline) push(x, y);
    for (const s of tier.facetSeams) {
      push(s.x1, s.y1);
      push(s.x2, s.y2);
    }
  }
  return out;
}
