import polygonClipping from 'polygon-clipping';
import type { CurvePoint } from '../types';

const CURVE_SEGMENTS = 8; // samples per curved edge — enough for smooth visuals

/** Convert clean polygon + parametric curve metadata into a dense display polygon. */
export function flattenCurves(
  polygon: [number, number][],
  curvePoints?: CurvePoint[],
): [number, number][] {
  if (!curvePoints || curvePoints.length === 0) return polygon;
  const n = polygon.length;
  const curveMap = new Map(curvePoints.map(cp => [cp.edgeIdx, cp.ctrl]));
  const result: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const A = polygon[i];
    const B = polygon[(i + 1) % n];
    result.push(A);
    const ctrl = curveMap.get(i);
    if (ctrl) {
      for (let s = 1; s < CURVE_SEGMENTS; s++) {
        const t = s / CURVE_SEGMENTS;
        const mt = 1 - t;
        result.push([
          mt * mt * A[0] + 2 * t * mt * ctrl[0] + t * t * B[0],
          mt * mt * A[1] + 2 * t * mt * ctrl[1] + t * t * B[1],
        ]);
      }
    }
  }
  return result;
}

/** Given a ctrl point and edge endpoints, return the visual handle position (bezier midpoint). */
export function ctrlToHandle(A: [number, number], B: [number, number], ctrl: [number, number]): [number, number] {
  return [A[0] / 4 + ctrl[0] / 2 + B[0] / 4, A[1] / 4 + ctrl[1] / 2 + B[1] / 4];
}

/** Given a dragged handle position, return the implied quadratic Bezier control point. */
export function handleToCtrl(A: [number, number], B: [number, number], H: [number, number]): [number, number] {
  return [2 * H[0] - (A[0] + B[0]) / 2, 2 * H[1] - (A[1] + B[1]) / 2];
}

export function computeCentroid(polygon: [number, number][]): { x: number; y: number } {
  const x = polygon.reduce((s, p) => s + p[0], 0) / polygon.length;
  const y = polygon.reduce((s, p) => s + p[1], 0) / polygon.length;
  return { x, y };
}

export function smoothPolygon(pts: [number, number][]): [number, number][] {
  if (pts.length < 3) return pts;
  const n = pts.length;
  const out: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const [cx, cy] = pts[i];
    const [nx, ny] = pts[(i + 1) % n];
    out.push([cx * 0.75 + nx * 0.25, cy * 0.75 + ny * 0.25]);
    out.push([cx * 0.25 + nx * 0.75, cy * 0.25 + ny * 0.75]);
  }
  return out;
}

export function snapPolygonToNeighbors(
  polygon: [number, number][],
  neighbors: [number, number][][],
  radius: number,
): [number, number][] {
  if (neighbors.length === 0 || polygon.length < 3) return polygon;
  const r2 = radius * radius;

  return polygon.map(([px, py]) => {
    let bestD2 = r2;
    let bestX = px, bestY = py;
    for (const nb of neighbors) {
      for (let i = 0; i < nb.length; i++) {
        const [ax, ay] = nb[i];
        const [bx, by] = nb[(i + 1) % nb.length];
        const dx = bx - ax, dy = by - ay;
        const len2 = dx * dx + dy * dy;
        let t = 0;
        if (len2 > 0) {
          t = ((px - ax) * dx + (py - ay) * dy) / len2;
          if (t < 0) t = 0; else if (t > 1) t = 1;
        }
        const cx = ax + t * dx, cy = ay + t * dy;
        const ex = px - cx, ey = py - cy;
        const d2 = ex * ex + ey * ey;
        if (d2 < bestD2) { bestD2 = d2; bestX = cx; bestY = cy; }
      }
    }
    return [bestX, bestY] as [number, number];
  });
}

export function subtractPolygons(subject: [number, number][], clipPolygons: [number, number][][]): [number, number][] {
  if (clipPolygons.length === 0) return subject;
  
  try {
    const subjPoly = [subject];
    const clipPolys = clipPolygons.map(p => [p]);
    
    const diff = polygonClipping.difference(subjPoly, ...clipPolys);
    
    if (diff.length === 0) return [];
    
    let largestRing: [number, number][] = [];
    let maxArea = -1;
    
    for (const multi of diff) {
      const ring = multi[0];
      let area = 0;
      for (let i = 0; i < ring.length - 1; i++) {
        area += ring[i][0] * ring[i+1][1] - ring[i+1][0] * ring[i][1];
      }
      area = Math.abs(area) / 2;
      
      if (area > maxArea) {
        maxArea = area;
        largestRing = ring as [number, number][];
      }
    }

    // polygon-clipping returns closed rings (first vertex repeated at the
    // end); piece polygons are stored open everywhere else, and the stray
    // duplicate vertex corrupts flattenCurves/centroid/snapping downstream.
    if (largestRing.length > 1) {
      const first = largestRing[0];
      const last = largestRing[largestRing.length - 1];
      if (first[0] === last[0] && first[1] === last[1]) {
        largestRing = largestRing.slice(0, -1);
      }
    }

    return largestRing;
  } catch (e) {
    console.warn("Clipping failed", e);
    return subject;
  }
}

/**
 * Cyclic polygon equality: the same ring may come back from clipping
 * re-anchored at a different start vertex, closed (duplicate end vertex),
 * or with reversed winding — all of which still describe an unchanged
 * polygon. A naive index-by-index compare treated those as "changed" and
 * made every curve edit near a neighbor discard its Bezier metadata.
 */
export function arePolygonsEqual(p1: [number, number][], p2: [number, number][], epsilon = 0.1): boolean {
  const stripClosed = (p: [number, number][]) =>
    p.length > 1 && p[0][0] === p[p.length - 1][0] && p[0][1] === p[p.length - 1][1]
      ? p.slice(0, -1)
      : p;
  const a = stripClosed(p1);
  const b = stripClosed(p2);
  if (a.length !== b.length) return false;
  const n = a.length;
  if (n === 0) return true;

  const matches = (i: number, j: number) =>
    Math.abs(a[i][0] - b[j][0]) <= epsilon && Math.abs(a[i][1] - b[j][1]) <= epsilon;

  // Only offsets where b matches a's first vertex can align — typically 0-1
  // candidates, so this stays near-linear for the common "not equal" case.
  for (let off = 0; off < n; off++) {
    if (!matches(0, off)) continue;
    for (const dir of [1, -1]) {
      let ok = true;
      for (let i = 1; i < n; i++) {
        const j = (((off + dir * i) % n) + n) % n;
        if (!matches(i, j)) { ok = false; break; }
      }
      if (ok) return true;
    }
  }
  return false;
}

export function computePolygonArea(polygon: [number, number][]): number {
  if (polygon.length < 3) return 0;
  let area = 0;
  const n = polygon.length;
  const isClosed = polygon[0][0] === polygon[n - 1][0] && polygon[0][1] === polygon[n - 1][1];
  const limit = isClosed ? n - 1 : n;
  
  for (let i = 0; i < limit; i++) {
    const [x1, y1] = polygon[i];
    const [x2, y2] = polygon[(i + 1) % limit];
    area += x1 * y2 - x2 * y1;
  }
  return Math.abs(area) / 2;
}

export function computeBleedRatio(
  generated: [number, number][],
  groundTruth: [number, number][],
): number {
  if (generated.length < 3 || groundTruth.length < 3) return 0;
  try {
    const gtArea = computePolygonArea(groundTruth);
    if (gtArea === 0) return 0;

    const closeRing = (ring: [number, number][]): [number, number][] => {
      if (ring.length === 0) return [];
      const first = ring[0];
      const last = ring[ring.length - 1];
      if (first[0] === last[0] && first[1] === last[1]) return ring;
      return [...ring, [first[0], first[1]]];
    };

    const genClosed = closeRing(generated);
    const gtClosed = closeRing(groundTruth);

    const diff = polygonClipping.difference([genClosed], [gtClosed]);
    
    let bleedArea = 0;
    for (const poly of diff) {
      if (poly.length > 0) {
        bleedArea += computePolygonArea(poly[0] as [number, number][]);
        for (let j = 1; j < poly.length; j++) {
          bleedArea -= computePolygonArea(poly[j] as [number, number][]);
        }
      }
    }
    return bleedArea / gtArea;
  } catch (e) {
    console.warn("Bleed calculation failed", e);
    return 0;
  }
}

export function findMatchedGroundTruth(
  generated: [number, number][],
  gts: [number, number][][]
): [number, number][] | null {
  if (generated.length < 3) return null;
  let bestGt: [number, number][] | null = null;
  let maxOverlap = 0;

  const closeRing = (ring: [number, number][]): [number, number][] => {
    if (ring.length === 0) return [];
    const first = ring[0];
    const last = ring[ring.length - 1];
    if (first[0] === last[0] && first[1] === last[1]) return ring;
    return [...ring, [first[0], first[1]]];
  };

  const genClosed = closeRing(generated);

  for (const gt of gts) {
    const gtClosed = closeRing(gt);
    try {
      const intersection = polygonClipping.intersection([genClosed], [gtClosed]);
      let area = 0;
      for (const poly of intersection) {
        if (poly.length > 0) {
          area += computePolygonArea(poly[0] as [number, number][]);
          for (let j = 1; j < poly.length; j++) {
            area -= computePolygonArea(poly[j] as [number, number][]);
          }
        }
      }
      if (area > maxOverlap) {
        maxOverlap = area;
        bestGt = gt;
      }
    } catch (e) {
      // Ignore clipping errors
    }
  }

  if (bestGt) {
    const gtArea = computePolygonArea(bestGt);
    if (maxOverlap > 0.15 * gtArea) {
      return bestGt;
    }
  }
  return null;
}


