import polygonClipping from 'polygon-clipping';
import type { CurvePoint } from '../types';

export type Point = [number, number];

const DEFAULT_CURVE_FLATNESS = 0.5;
const MAX_CURVE_SUBDIVISIONS = 10;

export interface CubicBezier {
  start: Point;
  ctrl1: Point;
  ctrl2: Point;
  end: Point;
}

/** Cubic entries always carry both an explicit kind and a second control point. */
export function isCubicCurvePoint(curve: CurvePoint): curve is CurvePoint & {
  kind: 'cubic';
  ctrl2: Point;
} {
  return curve.kind === 'cubic' && Array.isArray(curve.ctrl2);
}

export function makeCubicCurvePoint(
  edgeIdx: number,
  ctrl1: Point,
  ctrl2: Point,
): CurvePoint {
  return { edgeIdx, kind: 'cubic', ctrl: ctrl1, ctrl2 };
}

export function evaluateQuadraticBezier(
  start: Point,
  ctrl: Point,
  end: Point,
  t: number,
): Point {
  const mt = 1 - t;
  return [
    mt * mt * start[0] + 2 * mt * t * ctrl[0] + t * t * end[0],
    mt * mt * start[1] + 2 * mt * t * ctrl[1] + t * t * end[1],
  ];
}

export function evaluateCubicBezier(
  start: Point,
  ctrl1: Point,
  ctrl2: Point,
  end: Point,
  t: number,
): Point {
  const mt = 1 - t;
  const mt2 = mt * mt;
  const t2 = t * t;
  return [
    mt2 * mt * start[0] + 3 * mt2 * t * ctrl1[0] + 3 * mt * t2 * ctrl2[0] + t2 * t * end[0],
    mt2 * mt * start[1] + 3 * mt2 * t * ctrl1[1] + 3 * mt * t2 * ctrl2[1] + t2 * t * end[1],
  ];
}

/** Convert a quadratic edge to the exactly equivalent cubic controls. */
export function quadraticToCubicControls(start: Point, ctrl: Point, end: Point): [Point, Point] {
  return [
    [start[0] + (2 / 3) * (ctrl[0] - start[0]), start[1] + (2 / 3) * (ctrl[1] - start[1])],
    [end[0] + (2 / 3) * (ctrl[0] - end[0]), end[1] + (2 / 3) * (ctrl[1] - end[1])],
  ];
}

/** Return cubic controls for either a legacy quadratic or a cubic curve entry. */
export function curveToCubicControls(
  start: Point,
  end: Point,
  curve: CurvePoint,
): [Point, Point] {
  return isCubicCurvePoint(curve)
    ? [curve.ctrl, curve.ctrl2]
    : quadraticToCubicControls(start, curve.ctrl, end);
}

/** Evaluate either a legacy quadratic or a cubic edge at parameter t. */
export function evaluateCurve(
  start: Point,
  end: Point,
  curve: CurvePoint,
  t: number,
): Point {
  const clampedT = Math.max(0, Math.min(1, t));
  return isCubicCurvePoint(curve)
    ? evaluateCubicBezier(start, curve.ctrl, curve.ctrl2, end, clampedT)
    : evaluateQuadraticBezier(start, curve.ctrl, end, clampedT);
}

function lerpPoint(a: Point, b: Point, t: number): Point {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/** Split a cubic at t with de Casteljau's algorithm (useful for inserting nodes). */
export function splitCubicBezier(curve: CubicBezier, t: number): [CubicBezier, CubicBezier] {
  const clampedT = Math.max(0, Math.min(1, t));
  const a = lerpPoint(curve.start, curve.ctrl1, clampedT);
  const b = lerpPoint(curve.ctrl1, curve.ctrl2, clampedT);
  const c = lerpPoint(curve.ctrl2, curve.end, clampedT);
  const d = lerpPoint(a, b, clampedT);
  const e = lerpPoint(b, c, clampedT);
  const split = lerpPoint(d, e, clampedT);
  return [
    { start: curve.start, ctrl1: a, ctrl2: d, end: split },
    { start: split, ctrl1: e, ctrl2: c, end: curve.end },
  ];
}

/** Reflect a handle around its anchor, the conventional smooth-node operation. */
export function reflectHandle(anchor: Point, handle: Point): Point {
  return [2 * anchor[0] - handle[0], 2 * anchor[1] - handle[1]];
}

/** Keep a handle collinear with a partner while preserving its own length. */
export function alignHandle(anchor: Point, movedHandle: Point, handleLength: number): Point {
  const dx = anchor[0] - movedHandle[0];
  const dy = anchor[1] - movedHandle[1];
  const length = Math.hypot(dx, dy);
  if (length === 0 || handleLength === 0) return [anchor[0], anchor[1]];
  const scale = handleLength / length;
  return [anchor[0] + dx * scale, anchor[1] + dy * scale];
}

function pointLineDistance(point: Point, start: Point, end: Point): number {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const length = Math.hypot(dx, dy);
  if (length === 0) return Math.hypot(point[0] - start[0], point[1] - start[1]);
  return Math.abs(dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0]) / length;
}

function appendFlattenedCubic(curve: CubicBezier, result: Point[], flatness: number, depth = 0): void {
  const flatEnough = Math.max(
    pointLineDistance(curve.ctrl1, curve.start, curve.end),
    pointLineDistance(curve.ctrl2, curve.start, curve.end),
  ) <= flatness;
  if (flatEnough || depth >= MAX_CURVE_SUBDIVISIONS) {
    result.push(curve.end);
    return;
  }
  const [left, right] = splitCubicBezier(curve, 0.5);
  appendFlattenedCubic(left, result, flatness, depth + 1);
  appendFlattenedCubic(right, result, flatness, depth + 1);
}

/** Convert clean polygon + parametric curve metadata into a dense display polygon. */
export function flattenCurves(
  polygon: Point[],
  curvePoints?: CurvePoint[],
  flatness = DEFAULT_CURVE_FLATNESS,
): Point[] {
  if (!curvePoints || curvePoints.length === 0 || polygon.length === 0) return polygon;
  const n = polygon.length;
  const curveMap = new Map(curvePoints.map(cp => [cp.edgeIdx, cp]));
  const result: Point[] = [];
  const safeFlatness = Number.isFinite(flatness) && flatness > 0 ? flatness : DEFAULT_CURVE_FLATNESS;
  for (let i = 0; i < n; i++) {
    const A = polygon[i];
    const B = polygon[(i + 1) % n];
    result.push(A);
    const curve = curveMap.get(i);
    if (!curve) continue;

    const [ctrl1, ctrl2] = curveToCubicControls(A, B, curve);
    const flattened: Point[] = [];
    appendFlattenedCubic({ start: A, ctrl1, ctrl2, end: B }, flattened, safeFlatness);
    // The next polygon iteration adds B, so omit it here to avoid duplicates.
    result.push(...flattened.slice(0, -1));
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
  if (polygon.length === 0) return { x: 0, y: 0 };
  const x = polygon.reduce((s, p) => s + p[0], 0) / polygon.length;
  const y = polygon.reduce((s, p) => s + p[1], 0) / polygon.length;
  return { x, y };
}

// Each pass doubles the vertex count; cap it so repeated Smooth clicks can't
// inflate a piece into tens of thousands of vertices and blow up clipping,
// snapping, and packing downstream.
const SMOOTH_MAX_VERTICES = 512;

export function smoothPolygon(pts: [number, number][]): [number, number][] {
  if (pts.length < 3) return pts;
  if (pts.length * 2 > SMOOTH_MAX_VERTICES) return pts;
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

    // polygon-clipping returns rings closed (first vertex repeated at the
    // end) and re-anchored at an arbitrary vertex; piece polygons are stored
    // open everywhere else. Strip the closing duplicate so downstream code
    // (flattenCurves/centroid/snapping) never sees a zero-length edge.
    const openRing = (ring: [number, number][]): [number, number][] => {
      if (ring.length > 1) {
        const first = ring[0];
        const last = ring[ring.length - 1];
        if (first[0] === last[0] && first[1] === last[1]) return ring.slice(0, -1);
      }
      return ring;
    };

    let largestRing: [number, number][] = [];
    let maxArea = -1;

    for (const multi of diff) {
      const ring = openRing(multi[0] as [number, number][]);
      const area = computePolygonArea(ring);

      if (area > maxArea) {
        maxArea = area;
        largestRing = ring;
      }
    }

    // Nothing was actually subtracted: hand back the subject untouched so
    // callers keep its exact vertex order/anchoring (and any curve metadata
    // indexed against it). The difference is a subset of the subject, so
    // equal area means an identical region.
    const subjectArea = computePolygonArea(subject);
    if (
      diff.length === 1 && diff[0].length === 1 &&
      Math.abs(maxArea - subjectArea) <= subjectArea * 1e-9
    ) {
      return subject;
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
