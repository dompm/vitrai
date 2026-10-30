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
  if (neighbors.length === 0 || polygon.length < 3 || radius <= 0) return polygon;
  const r2 = radius * radius;
  const vertexSnapR2 = (radius * 1.25) * (radius * 1.25);
  const endpointPullR2 = (radius * 0.45) * (radius * 0.45);

  const snappedMeta = polygon.map(([px, py]) => {
    // 1. Prefer snapping directly to a neighbor vertex when close so T-junctions
    // and shared corners lock to the exact same point instead of leaving wedge gaps.
    let bestVertexD2 = vertexSnapR2;
    let bestVx = px, bestVy = py;
    let matchedNbIdx = -1;
    let matchedEdgeIdx = -1;

    for (let nIdx = 0; nIdx < neighbors.length; nIdx++) {
      const nb = neighbors[nIdx];
      for (let i = 0; i < nb.length; i++) {
        const [vx, vy] = nb[i];
        const d2 = (px - vx) * (px - vx) + (py - vy) * (py - vy);
        if (d2 < bestVertexD2) {
          bestVertexD2 = d2;
          bestVx = vx;
          bestVy = vy;
          matchedNbIdx = nIdx;
          matchedEdgeIdx = i;
        }
      }
    }
    if (matchedNbIdx >= 0 && bestVertexD2 <= r2) {
      return { pt: [bestVx, bestVy] as [number, number], nbIdx: matchedNbIdx, edgeIdx: matchedEdgeIdx };
    }

    // 2. Otherwise project onto the closest neighbor segment within radius.
    let bestD2 = r2;
    let bestX = px, bestY = py;
    let bestNb = -1;
    let bestEdge = -1;
    for (let nIdx = 0; nIdx < neighbors.length; nIdx++) {
      const nb = neighbors[nIdx];
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
        let cx = ax + t * dx, cy = ay + t * dy;
        const ex = px - cx, ey = py - cy;
        const d2 = ex * ex + ey * ey;
        if (d2 < bestD2) {
          // Pull projections that land very close to a segment endpoint onto the endpoint
          if ((cx - ax) * (cx - ax) + (cy - ay) * (cy - ay) <= endpointPullR2) {
            cx = ax; cy = ay;
          } else if ((cx - bx) * (cx - bx) + (cy - by) * (cy - by) <= endpointPullR2) {
            cx = bx; cy = by;
          }
          bestD2 = d2;
          bestX = cx;
          bestY = cy;
          bestNb = nIdx;
          bestEdge = i;
        }
      }
    }
    if (bestNb < 0 && matchedNbIdx >= 0) {
      return { pt: [bestVx, bestVy] as [number, number], nbIdx: matchedNbIdx, edgeIdx: matchedEdgeIdx };
    }
    return { pt: [bestX, bestY] as [number, number], nbIdx: bestNb, edgeIdx: bestEdge };
  });

  // 3. Bridge single-vertex gaps and lock seam-end corners along a shared seam:
  // - If both i-1 and i+1 snapped to the same neighbor, bridge vertex i onto that neighbor (up to 1.6 * radius).
  // - If an adjacent vertex snapped to a neighbor and vertex i is within 1.8 * radius of a corner vertex of that
  //   same neighbor, snap vertex i to that neighbor corner so seam ends meet cleanly at 3-way solder joints.
  const n = snappedMeta.length;
  const bridgeR2 = (radius * 1.6) * (radius * 1.6);
  const cornerEndR2 = (radius * 1.8) * (radius * 1.8);
  for (let i = 0; i < n; i++) {
    if (snappedMeta[i].nbIdx >= 0) continue;
    const prev = snappedMeta[(i - 1 + n) % n];
    const next = snappedMeta[(i + 1) % n];
    const [px, py] = snappedMeta[i].pt;
    if (prev.nbIdx >= 0 && prev.nbIdx === next.nbIdx) {
      const nb = neighbors[prev.nbIdx];
      let bestD2 = bridgeR2;
      let bestX = px, bestY = py;
      let snapped = false;
      for (let j = 0; j < nb.length; j++) {
        const [ax, ay] = nb[j];
        const [bx, by] = nb[(j + 1) % nb.length];
        const dx = bx - ax, dy = by - ay;
        const len2 = dx * dx + dy * dy;
        const t = len2 > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
        const cx = ax + t * dx, cy = ay + t * dy;
        const d2 = (px - cx) * (px - cx) + (py - cy) * (py - cy);
        if (d2 < bestD2) {
          bestD2 = d2;
          bestX = cx;
          bestY = cy;
          snapped = true;
        }
      }
      if (snapped) {
        snappedMeta[i] = { pt: [bestX, bestY], nbIdx: prev.nbIdx, edgeIdx: prev.edgeIdx };
        continue;
      }
    }
    for (const adj of [prev, next]) {
      if (adj.nbIdx < 0) continue;
      const nb = neighbors[adj.nbIdx];
      let bestCornerD2 = cornerEndR2;
      let bestCornerPt: [number, number] | null = null;
      let bestCornerIdx = -1;
      for (let j = 0; j < nb.length; j++) {
        const [vx, vy] = nb[j];
        const d2 = (px - vx) * (px - vx) + (py - vy) * (py - vy);
        const adjD2 = (adj.pt[0] - vx) * (adj.pt[0] - vx) + (adj.pt[1] - vy) * (adj.pt[1] - vy);
        if (d2 < bestCornerD2 && d2 < adjD2) {
          bestCornerD2 = d2;
          bestCornerPt = [vx, vy];
          bestCornerIdx = j;
        }
      }
      if (bestCornerPt) {
        snappedMeta[i] = { pt: bestCornerPt, nbIdx: adj.nbIdx, edgeIdx: bestCornerIdx };
        break;
      }
    }
  }

  // 4. Conform contiguous snapped runs to the neighbor's intermediate contour so
  // both sides of a shared curved or multi-segment seam follow the exact same path.
  const closestNbVertexIdx = (pt: [number, number], nb: [number, number][]): number => {
    let bestIdx = 0;
    let bestD2 = Infinity;
    for (let i = 0; i < nb.length; i++) {
      const d2 = (pt[0] - nb[i][0]) ** 2 + (pt[1] - nb[i][1]) ** 2;
      if (d2 < bestD2) {
        bestD2 = d2;
        bestIdx = i;
      }
    }
    return bestIdx;
  };

  if (snappedMeta.some(m => m.nbIdx < 0)) {
    const firstUnsnapped = snappedMeta.findIndex(m => m.nbIdx < 0);
    const rotated = [
      ...snappedMeta.slice(firstUnsnapped),
      ...snappedMeta.slice(0, firstUnsnapped),
    ];
    const alignedPts: [number, number][] = [];
    let idx = 0;
    while (idx < rotated.length) {
      const nbIdx = rotated[idx].nbIdx;
      if (nbIdx < 0) {
        alignedPts.push(rotated[idx].pt);
        idx++;
        continue;
      }
      let endRun = idx;
      while (endRun + 1 < rotated.length && rotated[endRun + 1].nbIdx === nbIdx) {
        endRun++;
      }
      const runLen = endRun - idx + 1;
      const nb = neighbors[nbIdx];
      if (runLen >= 2 && nb.length >= 3) {
        const startPt = rotated[idx].pt;
        const endPt = rotated[endRun].pt;
        const startV = closestNbVertexIdx(startPt, nb);
        const endV = closestNbVertexIdx(endPt, nb);
        if (startV !== endV) {
          const buildNbChain = (step: 1 | -1) => {
            const chain: [number, number][] = [startPt];
            let cur = (startV + step + nb.length) % nb.length;
            while (cur !== endV && chain.length <= nb.length) {
              chain.push(nb[cur]);
              cur = (cur + step + nb.length) % nb.length;
            }
            chain.push(endPt);
            return chain;
          };
          const pathLen = (pts: [number, number][]) => {
            let l = 0;
            for (let k = 0; k < pts.length - 1; k++) {
              l += Math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]);
            }
            return l;
          };
          const fwd = buildNbChain(1);
          const bwd = buildNbChain(-1);
          const candidate = pathLen(fwd) <= pathLen(bwd) ? fwd : bwd;
          const runPoly = rotated.slice(idx, endRun + 1).map(m => m.pt);
          const runLength = pathLen(runPoly);
          const candLength = pathLen(candidate);
          const allClose = candLength <= Math.max(runLength * 1.35, radius * 2) &&
            candidate.every(cp => pointToNeighborsDistance(cp, [runPoly]) <= radius * 1.6);
          if (allClose) {
            alignedPts.push(...candidate);
            idx = endRun + 1;
            continue;
          }
        }
      }
      for (let k = idx; k <= endRun; k++) {
        alignedPts.push(rotated[k].pt);
      }
      idx = endRun + 1;
    }
    return dedupeConsecutivePoints(alignedPts, 0.5);
  }

  return dedupeConsecutivePoints(snappedMeta.map(m => m.pt), 0.5);
}

function dedupeConsecutivePoints(points: Point[], minDist = 0.5): Point[] {
  if (points.length <= 3) return points;
  const minDist2 = minDist * minDist;
  const out: Point[] = [];
  for (let i = 0; i < points.length; i++) {
    const prev = out.length > 0 ? out[out.length - 1] : points[points.length - 1];
    const cur = points[i];
    if ((cur[0] - prev[0]) * (cur[0] - prev[0]) + (cur[1] - prev[1]) * (cur[1] - prev[1]) >= minDist2) {
      out.push(cur);
    }
  }
  return out.length >= 3 ? out : points;
}

function pointToNeighborsDistance(pt: Point, neighbors: Point[][]): number {
  let minD2 = Infinity;
  const [px, py] = pt;
  for (const nb of neighbors) {
    for (let i = 0; i < nb.length; i++) {
      const [ax, ay] = nb[i];
      const [bx, by] = nb[(i + 1) % nb.length];
      const dx = bx - ax, dy = by - ay;
      const len2 = dx * dx + dy * dy;
      const t = len2 > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2)) : 0;
      const cx = ax + t * dx, cy = ay + t * dy;
      const d2 = (px - cx) * (px - cx) + (py - cy) * (py - cy);
      if (d2 < minD2) minD2 = d2;
    }
  }
  return Math.sqrt(minD2);
}

function turningAngleRad(prev: Point, cur: Point, next: Point): number {
  const ux = cur[0] - prev[0], uy = cur[1] - prev[1];
  const vx = next[0] - cur[0], vy = next[1] - cur[1];
  const uLen = Math.hypot(ux, uy);
  const vLen = Math.hypot(vx, vy);
  if (uLen < 1e-6 || vLen < 1e-6) return 0;
  const dot = Math.max(-1, Math.min(1, (ux * vx + uy * vy) / (uLen * vLen)));
  return Math.acos(dot);
}

function signedTurningAngleRad(prev: Point, cur: Point, next: Point): number {
  const ux = cur[0] - prev[0], uy = cur[1] - prev[1];
  const vx = next[0] - cur[0], vy = next[1] - cur[1];
  const uLen = Math.hypot(ux, uy);
  const vLen = Math.hypot(vx, vy);
  if (uLen < 1e-6 || vLen < 1e-6) return 0;
  const cross = ux * vy - uy * vx;
  const dot = ux * vx + uy * vy;
  return Math.atan2(cross, dot);
}

function normalizeVec(dx: number, dy: number): Point {
  const len = Math.hypot(dx, dy);
  return len > 1e-9 ? [dx / len, dy / len] : [1, 0];
}

function polygonPerimeter(pts: Point[]): number {
  let sum = 0;
  for (let i = 0; i < pts.length; i++) {
    const next = pts[(i + 1) % pts.length];
    sum += Math.hypot(next[0] - pts[i][0], next[1] - pts[i][1]);
  }
  return sum;
}

function intersectLines(a1: Point, a2: Point, b1: Point, b2: Point): Point | null {
  const dax = a2[0] - a1[0], day = a2[1] - a1[1];
  const dbx = b2[0] - b1[0], dby = b2[1] - b1[1];
  const denom = dax * dby - day * dbx;
  if (Math.abs(denom) < 1e-9) return null;
  const t = ((b1[0] - a1[0]) * dby - (b1[1] - a1[1]) * dbx) / denom;
  return [a1[0] + t * dax, a1[1] + t * day];
}

/**
 * Clean up SAM2 marching-squares / RDP artifacts before curve fitting:
 * 1. Prune near-collinear jitter vertices on free edges so straight sides become clean segments.
 * 2. Consolidate short 2–4 vertex corner chamfers/bevels (where SAM2 rounds a 90° corner
 *    into multiple ~25°–38° steps) back into a single crisp corner apex.
 */
function consolidateBeveledCornersAndJitter(
  initialPts: Point[],
  neighbors: Point[][],
  seamTol: number,
  cornerAngleRad: number,
): Point[] {
  let pts = [...initialPts];
  if (pts.length <= 3) return pts;

  const isLocked = (pt: Point) =>
    neighbors.length > 0 && pointToNeighborsDistance(pt, neighbors) <= seamTol;

  // Pass 1: Remove only strictly collinear micro-jitter (dev <= 0.8px) without
  // daisy-chaining across gentle curves, preserving contour samples for Bezier fitting.
  if (pts.length > 4) {
    const nextPts: Point[] = [];
    const m = pts.length;
    for (let i = 0; i < m; i++) {
      const cur = pts[i];
      if (isLocked(cur)) {
        nextPts.push(cur);
        continue;
      }
      const prev = pts[(i - 1 + m) % m];
      const next = pts[(i + 1) % m];
      const turn = turningAngleRad(prev, cur, next);
      const dev = pointLineDistance(cur, prev, next);
      if (turn < (3 * Math.PI) / 180 && dev <= 0.8) {
        continue;
      }
      nextPts.push(cur);
    }
    if (nextPts.length >= 4) {
      pts = nextPts;
    }
  }

  if (pts.length <= 4) return pts;

  // Pass 2: Collapse localized 2–4 vertex corner chamfers flanked by longer edges.
  // Rotate pts so that the longest edge is the wrap-around segment (m - 1) -> 0,
  // guaranteeing no corner bevel cluster straddles index 0.
  let longestIdx = 0;
  let longestLen = -1;
  for (let i = 0; i < pts.length; i++) {
    const next = pts[(i + 1) % pts.length];
    const len = Math.hypot(next[0] - pts[i][0], next[1] - pts[i][1]);
    if (len > longestLen) {
      longestLen = len;
      longestIdx = i;
    }
  }
  const rot = (longestIdx + 1) % pts.length;
  if (rot !== 0) {
    pts = [...pts.slice(rot), ...pts.slice(0, rot)];
  }

  const perim = polygonPerimeter(pts);
  const maxBevelSegLen = Math.max(12, Math.min(28, perim * 0.045));
  const maxBevelClusterLen = Math.max(24, Math.min(48, perim * 0.08));
  const minBevelVertexTurn = (12 * Math.PI) / 180;

  const m = pts.length;
  const signedTurns = pts.map((cur, i) =>
    signedTurningAngleRad(pts[(i - 1 + m) % m], cur, pts[(i + 1) % m]),
  );
  const segLens = pts.map((cur, i) => {
    const next = pts[(i + 1) % m];
    return Math.hypot(next[0] - cur[0], next[1] - cur[1]);
  });

  const consumed = new Array<boolean>(m).fill(false);
  const consolidated: Point[] = [];

  for (let i = 0; i < m; i++) {
    if (consumed[i]) continue;

    const sign0 = Math.sign(signedTurns[i]);
    if (Math.abs(signedTurns[i]) < minBevelVertexTurn || sign0 === 0) {
      consolidated.push(pts[i]);
      continue;
    }

    // Try growing a contiguous bevel cluster starting at i (up to 4 vertices)
    const cluster: number[] = [i];
    let curIdx = i;
    while (
      cluster.length < 4 &&
      cluster.length < m - 2 &&
      curIdx < m - 1 &&
      segLens[curIdx] <= maxBevelSegLen
    ) {
      const nextIdx = curIdx + 1;
      if (consumed[nextIdx]) break;
      if (
        Math.sign(signedTurns[nextIdx]) !== sign0 ||
        Math.abs(signedTurns[nextIdx]) < minBevelVertexTurn
      ) {
        break;
      }
      cluster.push(nextIdx);
      curIdx = nextIdx;
    }

    if (cluster.length < 2) {
      consolidated.push(pts[i]);
      continue;
    }

    const firstIdx = cluster[0];
    const lastIdx = cluster[cluster.length - 1];
    const beforeIdx = (firstIdx - 1 + m) % m;
    const afterIdx = (lastIdx + 1) % m;

    const pBefore = consolidated.length > 0 ? consolidated[consolidated.length - 1] : pts[beforeIdx];
    const pFirst = pts[firstIdx];
    const pLast = pts[lastIdx];
    const pAfter = pts[afterIdx];

    const inSegLen = Math.hypot(pFirst[0] - pBefore[0], pFirst[1] - pBefore[1]);
    const outSegLen = segLens[lastIdx];
    let bevelSumLen = 0;
    for (let c = 0; c < cluster.length - 1; c++) {
      bevelSumLen += segLens[cluster[c]];
    }
    const avgBevelLen = bevelSumLen / (cluster.length - 1);

    // Measure total directional turn between the incoming edge before the cluster
    // and the outgoing edge after the cluster
    const inVec: Point = [pFirst[0] - pBefore[0], pFirst[1] - pBefore[1]];
    const outVec: Point = [pAfter[0] - pLast[0], pAfter[1] - pLast[1]];
    const inLen = Math.hypot(inVec[0], inVec[1]);
    const outLen = Math.hypot(outVec[0], outVec[1]);
    const netTurn =
      inLen > 1e-6 && outLen > 1e-6
        ? Math.acos(Math.max(-1, Math.min(1, (inVec[0] * outVec[0] + inVec[1] * outVec[1]) / (inLen * outLen))))
        : 0;

    const flankedByLongerSides =
      bevelSumLen <= maxBevelClusterLen &&
      Math.max(inSegLen, outSegLen) >= avgBevelLen * 1.6 &&
      Math.min(inSegLen, outSegLen) >= avgBevelLen * 1.15;

    if (netTurn >= cornerAngleRad && flankedByLongerSides) {
      const lockedInCluster = cluster.filter(idx => isLocked(pts[idx]));
      if (lockedInCluster.length > 1) {
        // Keep locked seam vertices untouched
        consolidated.push(pts[i]);
        continue;
      }

      let apex: Point | null = null;
      if (lockedInCluster.length === 1) {
        apex = pts[lockedInCluster[0]];
      } else {
        // Intersect the incoming edge ray (pBefore -> pFirst) with outgoing edge ray (pAfter -> pLast)
        const hit = intersectLines(pBefore, pFirst, pLast, pAfter);
        if (hit) {
          const forwardIn = (hit[0] - pBefore[0]) * inVec[0] + (hit[1] - pBefore[1]) * inVec[1] > 0;
          const backwardOut = (pAfter[0] - hit[0]) * outVec[0] + (pAfter[1] - hit[1]) * outVec[1] > 0;
          const midCluster: Point = [(pFirst[0] + pLast[0]) / 2, (pFirst[1] + pLast[1]) / 2];
          const hitDist = Math.hypot(hit[0] - midCluster[0], hit[1] - midCluster[1]);
          if (forwardIn && backwardOut && hitDist <= Math.max(maxBevelSegLen * 1.6, bevelSumLen * 1.5)) {
            apex = hit;
          }
        }
        if (!apex) {
          // Fallback: pick the cluster vertex farthest from the chord pBefore -> pAfter
          let bestIdx = cluster[0];
          let bestDist = -1;
          for (const idx of cluster) {
            const d = pointLineDistance(pts[idx], pBefore, pAfter);
            if (d > bestDist) {
              bestDist = d;
              bestIdx = idx;
            }
          }
          apex = pts[bestIdx];
        }
      }

      for (const idx of cluster) consumed[idx] = true;
      consolidated.push(apex);
    } else {
      consolidated.push(pts[i]);
    }
  }

  return consolidated.length >= 3 ? consolidated : pts;
}

function sampleChainAtU(chain: Point[], u: number[], targetU: number): Point {
  if (chain.length === 0) return [0, 0];
  if (targetU <= 0 || chain.length === 1) return chain[0];
  if (targetU >= 1) return chain[chain.length - 1];
  for (let i = 0; i < u.length - 1; i++) {
    if (targetU >= u[i] && targetU <= u[i + 1]) {
      const span = u[i + 1] - u[i];
      const t = span > 1e-9 ? (targetU - u[i]) / span : 0.5;
      return [
        chain[i][0] + (chain[i + 1][0] - chain[i][0]) * t,
        chain[i][1] + (chain[i + 1][1] - chain[i][1]) * t,
      ];
    }
  }
  return chain[Math.floor(chain.length / 2)];
}

/**
 * Fit a cubic Bézier to an ordered chain of points [p_0, ..., p_m] (m >= 2)
 * using chord-length parameterization and regularized 2×2 linear least squares
 * anchored around the midpoint-interpolating quadratic control points. This
 * avoids noisy 1-segment corner-bevel tangents that can flip handles onto the
 * wrong side of the chord.
 */
function fitCubicBezierToChain(chain: Point[]): [Point, Point] {
  const p0 = chain[0];
  const p3 = chain[chain.length - 1];
  const chord = Math.hypot(p3[0] - p0[0], p3[1] - p0[1]);
  if (chord < 1e-6 || chain.length < 2) {
    return [
      [p0[0] + (p3[0] - p0[0]) / 3, p0[1] + (p3[1] - p0[1]) / 3],
      [p0[0] + (2 * (p3[0] - p0[0])) / 3, p0[1] + (2 * (p3[1] - p0[1])) / 3],
    ];
  }

  const u: number[] = [0];
  for (let i = 1; i < chain.length; i++) {
    u.push(u[i - 1] + Math.hypot(chain[i][0] - chain[i - 1][0], chain[i][1] - chain[i - 1][1]));
  }
  const totalLen = u[u.length - 1];
  if (totalLen < 1e-6) {
    return [
      [p0[0] + (p3[0] - p0[0]) / 3, p0[1] + (p3[1] - p0[1]) / 3],
      [p0[0] + (2 * (p3[0] - p0[0])) / 3, p0[1] + (2 * (p3[1] - p0[1])) / 3],
    ];
  }
  for (let i = 1; i < u.length; i++) u[i] /= totalLen;

  // Baseline cubic controls from the quadratic that interpolates the chain at u = 0.5
  const midPt = sampleChainAtU(chain, u, 0.5);
  const qCtrl: Point = [
    2 * midPt[0] - 0.5 * (p0[0] + p3[0]),
    2 * midPt[1] - 0.5 * (p0[1] + p3[1]),
  ];
  const [q1, q2] = quadraticToCubicControls(p0, qCtrl, p3);

  if (chain.length <= 3) {
    return [q1, q2];
  }

  // Regularized 2×2 least-squares solve for (ctrl1, ctrl2) over all interior points
  const lambda = 0.15;
  let s11 = lambda;
  let s12 = 0;
  let s22 = lambda;
  let r1x = lambda * q1[0];
  let r1y = lambda * q1[1];
  let r2x = lambda * q2[0];
  let r2y = lambda * q2[1];

  for (let i = 1; i < chain.length - 1; i++) {
    const ti = u[i];
    const mt = 1 - ti;
    const b0 = mt * mt * mt;
    const b1 = 3 * mt * mt * ti;
    const b2 = 3 * mt * ti * ti;
    const b3 = ti * ti * ti;

    s11 += b1 * b1;
    s12 += b1 * b2;
    s22 += b2 * b2;

    const rhsX = chain[i][0] - b0 * p0[0] - b3 * p3[0];
    const rhsY = chain[i][1] - b0 * p0[1] - b3 * p3[1];
    r1x += b1 * rhsX;
    r1y += b1 * rhsY;
    r2x += b2 * rhsX;
    r2y += b2 * rhsY;
  }

  const det = s11 * s22 - s12 * s12;
  if (Math.abs(det) < 1e-9) {
    return [q1, q2];
  }

  const c1: Point = [(s22 * r1x - s12 * r2x) / det, (s22 * r1y - s12 * r2y) / det];
  const c2: Point = [(s11 * r2x - s12 * r1x) / det, (s11 * r2y - s12 * r1y) / det];
  return [c1, c2];
}

function computeChainCubicFitError(chain: Point[]): { maxErr: number; worstIdx: number } {
  if (chain.length <= 2) return { maxErr: 0, worstIdx: 0 };
  const p0 = chain[0];
  const p3 = chain[chain.length - 1];
  const [c1, c2] = fitCubicBezierToChain(chain);

  const u: number[] = [0];
  for (let i = 1; i < chain.length; i++) {
    u.push(u[i - 1] + Math.hypot(chain[i][0] - chain[i - 1][0], chain[i][1] - chain[i - 1][1]));
  }
  const totalLen = u[u.length - 1];
  if (totalLen < 1e-6) return { maxErr: 0, worstIdx: 1 };
  for (let i = 1; i < u.length; i++) u[i] /= totalLen;

  let maxErr = 0;
  let worstIdx = Math.floor(chain.length / 2);
  for (let i = 1; i < chain.length - 1; i++) {
    const fitPt = evaluateCubicBezier(p0, c1, c2, p3, u[i]);
    const err = Math.hypot(chain[i][0] - fitPt[0], chain[i][1] - fitPt[1]);
    if (err > maxErr) {
      maxErr = err;
      worstIdx = i;
    }
  }
  return { maxErr, worstIdx };
}

/**
 * Convert a faceted polygon (e.g. from SAM2 segmentation or manual drawing) into
 * structural anchor vertices + fitted cubic Bézier curves (`curvePoints`), while
 * keeping any edge that lies along a neighbor polygon locked flush to the seam.
 */
export function fitSmoothPieceCurves(
  rawPolygon: Point[],
  neighbors: Point[][] = [],
  options: { cornerAngleDeg?: number; maxTurnPerSpanDeg?: number; seamTolerancePx?: number; preserveBevels?: boolean } = {},
): {
  polygon: Point[];
  curvePoints: CurvePoint[];
  anchorTypes: ('corner' | 'smooth')[];
} {
  const deduped = dedupeConsecutivePoints(rawPolygon, 0.75);
  if (deduped.length < 3) {
    return { polygon: rawPolygon, curvePoints: [], anchorTypes: rawPolygon.map(() => 'corner') };
  }

  const cornerAngleRad = ((options.cornerAngleDeg ?? 42) * Math.PI) / 180;
  const maxTurnPerSpanRad = ((options.maxTurnPerSpanDeg ?? 85) * Math.PI) / 180;
  const seamTol = options.seamTolerancePx ?? 2.5;

  const pts = options.preserveBevels
    ? deduped
    : consolidateBeveledCornersAndJitter(deduped, neighbors, seamTol, cornerAngleRad);
  const n = pts.length;
  if (n < 3) {
    return { polygon: deduped, curvePoints: [], anchorTypes: deduped.map(() => 'corner') };
  }

  // 1. Identify vertices & edges that lie on a neighbor boundary
  const vertexLocked = pts.map(pt => neighbors.length > 0 && pointToNeighborsDistance(pt, neighbors) <= seamTol);
  const edgeLocked = pts.map((pt, i) => {
    const next = pts[(i + 1) % n];
    if (!vertexLocked[i] || !vertexLocked[(i + 1) % n]) return false;
    const mid: Point = [(pt[0] + next[0]) / 2, (pt[1] + next[1]) / 2];
    return pointToNeighborsDistance(mid, neighbors) <= seamTol * 1.25;
  });

  // 2. Compute turning angles and mark structural corner anchors
  const turnAngles = pts.map((cur, i) =>
    turningAngleRad(pts[(i - 1 + n) % n], cur, pts[(i + 1) % n]),
  );

  const anchorKind = new Array<'none' | 'corner' | 'smooth'>(n).fill('none');
  for (let i = 0; i < n; i++) {
    const prevEdgeLocked = edgeLocked[(i - 1 + n) % n];
    const nextEdgeLocked = edgeLocked[i];

    // Transition between a shared seam and a free edge is a corner anchor if it turns away (>= 10°)
    if (prevEdgeLocked !== nextEdgeLocked && turnAngles[i] >= (10 * Math.PI) / 180) {
      anchorKind[i] = 'corner';
      continue;
    }
    // Sharp turns (e.g., leaf tips, Y/T-junctions, panel corners) are structural corners
    if (turnAngles[i] >= cornerAngleRad) {
      anchorKind[i] = 'corner';
    }
  }

  // Ensure at least 2 anchors exist (e.g. on a smooth oval with no sharp corners)
  const existingAnchors = anchorKind.reduce((acc, k, idx) => (k !== 'none' ? [...acc, idx] : acc), [] as number[]);
  if (existingAnchors.length === 0) {
    let minIdx = 0;
    for (let i = 1; i < n; i++) {
      if (pts[i][0] < pts[minIdx][0]) minIdx = i;
    }
    let farIdx = minIdx;
    let maxD2 = -1;
    for (let i = 0; i < n; i++) {
      const d2 = (pts[i][0] - pts[minIdx][0]) ** 2 + (pts[i][1] - pts[minIdx][1]) ** 2;
      if (d2 > maxD2) { maxD2 = d2; farIdx = i; }
    }
    anchorKind[minIdx] = 'smooth';
    if (farIdx !== minIdx) anchorKind[farIdx] = 'smooth';
  } else if (existingAnchors.length === 1) {
    const first = existingAnchors[0];
    let farIdx = first;
    let maxD2 = -1;
    for (let i = 0; i < n; i++) {
      const d2 = (pts[i][0] - pts[first][0]) ** 2 + (pts[i][1] - pts[first][1]) ** 2;
      if (d2 > maxD2) { maxD2 = d2; farIdx = i; }
    }
    if (farIdx !== first) anchorKind[farIdx] = 'smooth';
  }

  // 3. Subdivide any free chain between anchors whose cumulative turn exceeds maxTurnPerSpanRad
  //    or whose least-squares cubic Bézier residual error exceeds the contour tolerance.
  const collectAnchorIndices = () =>
    anchorKind.reduce((acc, k, idx) => (k !== 'none' ? [...acc, idx] : acc), [] as number[]);

  let anchorIndices = collectAnchorIndices();
  for (let pass = 0; pass < 4; pass++) {
    let added = false;
    for (let a = 0; a < anchorIndices.length; a++) {
      const startIdx = anchorIndices[a];
      const endIdx = anchorIndices[(a + 1) % anchorIndices.length];
      const chainIndices: number[] = [startIdx];
      let curr = (startIdx + 1) % n;
      while (curr !== endIdx) {
        chainIndices.push(curr);
        curr = (curr + 1) % n;
      }
      chainIndices.push(endIdx);

      if (chainIndices.length <= 3) continue;
      const isChainLocked = chainIndices.slice(0, -1).every(idx => edgeLocked[idx]);
      if (isChainLocked) continue;

      let totalTurn = 0;
      for (let k = 1; k < chainIndices.length - 1; k++) {
        totalTurn += turnAngles[chainIndices[k]];
      }

      const chainPts = chainIndices.map(idx => pts[idx]);
      const pStart = chainPts[0];
      const pEnd = chainPts[chainPts.length - 1];
      const chord = Math.hypot(pEnd[0] - pStart[0], pEnd[1] - pStart[1]);
      const { maxErr, worstIdx } = computeChainCubicFitError(chainPts);
      const errLimit = Math.max(4.0, chord * 0.015);

      if (maxErr > errLimit || totalTurn > maxTurnPerSpanRad) {
        const splitIdx = maxErr > errLimit
          ? chainIndices[worstIdx]
          : chainIndices[Math.floor(chainIndices.length / 2)];
        anchorKind[splitIdx] = turnAngles[splitIdx] >= (22 * Math.PI) / 180 ? 'corner' : 'smooth';
        added = true;
      }
    }
    if (!added) break;
    anchorIndices = collectAnchorIndices();
  }

  if (anchorIndices.length < 2) {
    return { polygon: pts, curvePoints: [], anchorTypes: pts.map(() => 'corner') };
  }

  // 4. Build chains between consecutive anchors and fit cubic Béziers to curved spans
  const newPolygon: Point[] = [];
  const newAnchorTypes: ('corner' | 'smooth')[] = [];
  const chains: { indices: number[]; points: Point[]; locked: boolean }[] = [];

  for (let a = 0; a < anchorIndices.length; a++) {
    const startIdx = anchorIndices[a];
    const endIdx = anchorIndices[(a + 1) % anchorIndices.length];
    const indices: number[] = [startIdx];
    let curr = (startIdx + 1) % n;
    while (curr !== endIdx) {
      indices.push(curr);
      curr = (curr + 1) % n;
    }
    indices.push(endIdx);

    const points = indices.map(i => pts[i]);
    const locked = indices.slice(0, -1).every(i => edgeLocked[i]);
    newPolygon.push(pts[startIdx]);
    newAnchorTypes.push(anchorKind[startIdx] === 'smooth' ? 'smooth' : 'corner');
    chains.push({ indices, points, locked });
  }

  // If the resulting simplified polygon has only 2 anchors (e.g. a 2-tip leaf),
  // insert midpoint smooth anchors on each arc if needed so `polygon` has >= 3 vertices
  // for standard polygon area/clipping routines while remaining completely smooth.
  if (newPolygon.length === 2) {
    const expandedPoly: Point[] = [];
    const expandedTypes: ('corner' | 'smooth')[] = [];
    const expandedChains: typeof chains = [];
    for (let c = 0; c < chains.length; c++) {
      const ch = chains[c];
      expandedPoly.push(newPolygon[c]);
      expandedTypes.push(newAnchorTypes[c]);
      if (ch.points.length >= 3) {
        const mid = Math.floor(ch.points.length / 2);
        expandedPoly.push(ch.points[mid]);
        expandedTypes.push('smooth');
        expandedChains.push({
          indices: ch.indices.slice(0, mid + 1),
          points: ch.points.slice(0, mid + 1),
          locked: ch.locked,
        });
        expandedChains.push({
          indices: ch.indices.slice(mid),
          points: ch.points.slice(mid),
          locked: ch.locked,
        });
      } else {
        expandedChains.push(ch);
      }
    }
    if (expandedPoly.length >= 3) {
      newPolygon.splice(0, newPolygon.length, ...expandedPoly);
      newAnchorTypes.splice(0, newAnchorTypes.length, ...expandedTypes);
      chains.splice(0, chains.length, ...expandedChains);
    }
  }

  if (newPolygon.length < 3) {
    return { polygon: pts, curvePoints: [], anchorTypes: pts.map(() => 'corner') };
  }

  const m = newPolygon.length;
  const curvePoints: CurvePoint[] = [];

  for (let i = 0; i < m; i++) {
    const ch = chains[i];
    if (ch.locked && ch.points.length <= 2) continue;

    const pStart = ch.points[0];
    const pEnd = ch.points[ch.points.length - 1];
    const chordLen = Math.hypot(pEnd[0] - pStart[0], pEnd[1] - pStart[1]);
    if (chordLen < 2) continue;

    if (ch.points.length >= 3) {
      // Check max deviation from the straight chord (and interior sagitta so corner stubs don't bow straight sides)
      let maxDev = 0;
      let maxMidDev = 0;
      const cdx = pEnd[0] - pStart[0];
      const cdy = pEnd[1] - pStart[1];
      const cLen2 = cdx * cdx + cdy * cdy;
      for (let k = 1; k < ch.points.length - 1; k++) {
        const pt = ch.points[k];
        const dev = pointLineDistance(pt, pStart, pEnd);
        maxDev = Math.max(maxDev, dev);
        const projT = cLen2 > 0 ? ((pt[0] - pStart[0]) * cdx + (pt[1] - pStart[1]) * cdy) / cLen2 : 0.5;
        if (projT >= 0.18 && projT <= 0.82) {
          maxMidDev = Math.max(maxMidDev, dev);
        }
      }
      const bothCorners = newAnchorTypes[i] === 'corner' && newAnchorTypes[(i + 1) % m] === 'corner';
      if (bothCorners) {
        if (maxDev <= Math.max(2.5, chordLen * 0.028) || maxMidDev <= Math.max(2.2, chordLen * 0.022)) {
          continue;
        }
      } else if (maxDev <= Math.max(1.8, chordLen * 0.015)) {
        continue;
      }

      const [ctrl1, ctrl2] = fitCubicBezierToChain(ch.points);
      curvePoints.push(makeCubicCurvePoint(i, ctrl1, ctrl2));
    } else if (newAnchorTypes[i] === 'smooth' || newAnchorTypes[(i + 1) % m] === 'smooth') {
      // Single-segment span adjacent to a smooth anchor: compute Catmull-Rom cubic controls
      const prevPt = newPolygon[(i - 1 + m) % m];
      const nextPt = newPolygon[(i + 2) % m];
      const tHat1 = newAnchorTypes[i] === 'smooth'
        ? normalizeVec(pEnd[0] - prevPt[0], pEnd[1] - prevPt[1])
        : normalizeVec(pEnd[0] - pStart[0], pEnd[1] - pStart[1]);
      const tHat2 = newAnchorTypes[(i + 1) % m] === 'smooth'
        ? normalizeVec(pStart[0] - nextPt[0], pStart[1] - nextPt[1])
        : normalizeVec(pStart[0] - pEnd[0], pStart[1] - pEnd[1]);
      curvePoints.push(
        makeCubicCurvePoint(
          i,
          [pStart[0] + tHat1[0] * (chordLen / 3), pStart[1] + tHat1[1] * (chordLen / 3)],
          [pEnd[0] + tHat2[0] * (chordLen / 3), pEnd[1] + tHat2[1] * (chordLen / 3)],
        ),
      );
    }
  }

  // 5. Enforce G1 tangent collinearity across every 'smooth' anchor using the solved cubic handles
  for (let a = 0; a < m; a++) {
    if (newAnchorTypes[a] !== 'smooth') continue;
    const prevEdgeIdx = (a - 1 + m) % m;
    const nextEdgeIdx = a;
    const cpPrev = curvePoints.find(c => c.edgeIdx === prevEdgeIdx);
    const cpNext = curvePoints.find(c => c.edgeIdx === nextEdgeIdx);
    if (!cpPrev || !cpNext) continue;

    const anchor = newPolygon[a];
    const prevStart = newPolygon[prevEdgeIdx];
    const nextEnd = newPolygon[(a + 1) % m];
    const [prevC1, prevC2] = curveToCubicControls(prevStart, anchor, cpPrev);
    const [nextC1, nextC2] = curveToCubicControls(anchor, nextEnd, cpNext);

    const vInX = prevC2[0] - anchor[0];
    const vInY = prevC2[1] - anchor[1];
    const vOutX = nextC1[0] - anchor[0];
    const vOutY = nextC1[1] - anchor[1];
    const lenIn = Math.hypot(vInX, vInY);
    const lenOut = Math.hypot(vOutX, vOutY);
    if (lenIn < 1e-3 || lenOut < 1e-3) continue;

    const uIn = [vInX / lenIn, vInY / lenIn];
    const uOut = [vOutX / lenOut, vOutY / lenOut];
    const tHat = normalizeVec(uOut[0] - uIn[0], uOut[1] - uIn[1]);
    if (Math.hypot(tHat[0], tHat[1]) < 1e-3) continue;

    const alignedPrevC2: Point = [anchor[0] - tHat[0] * lenIn, anchor[1] - tHat[1] * lenIn];
    const alignedNextC1: Point = [anchor[0] + tHat[0] * lenOut, anchor[1] + tHat[1] * lenOut];
    Object.assign(cpPrev, makeCubicCurvePoint(prevEdgeIdx, prevC1, alignedPrevC2));
    Object.assign(cpNext, makeCubicCurvePoint(nextEdgeIdx, alignedNextC1, nextC2));
  }

  return { polygon: newPolygon, curvePoints, anchorTypes: newAnchorTypes };
}

/**
 * Smooth a piece's boundary while keeping neighbor-shared seams locked and sharp
 * structural tips intact, returning simplified anchors + fitted cubic Bézier curves.
 */
export function smoothPieceGeometry(
  polygon: Point[],
  curvePoints: CurvePoint[] = [],
  neighbors: Point[][] = [],
  seamTolerancePx = 2.5,
): {
  polygon: Point[];
  curvePoints: CurvePoint[];
  anchorTypes: ('corner' | 'smooth')[];
} {
  if (curvePoints.length === 0 && polygon.length >= 6) {
    const fitted = fitSmoothPieceCurves(polygon, neighbors, {
      cornerAngleDeg: 40,
      seamTolerancePx,
    });
    if (fitted.curvePoints.length > 0) {
      return fitted;
    }
  }

  const dense = dedupeConsecutivePoints(flattenCurves(polygon, curvePoints, 0.5), 0.5);
  const n = dense.length;
  if (n < 3) {
    return { polygon, curvePoints, anchorTypes: polygon.map(() => 'corner') };
  }

  const sharpTipRad = (78 * Math.PI) / 180;
  const locked = dense.map(pt => neighbors.length > 0 && pointToNeighborsDistance(pt, neighbors) <= seamTolerancePx);
  const turns = dense.map((cur, i) =>
    turningAngleRad(dense[(i - 1 + n) % n], cur, dense[(i + 1) % n]),
  );

  // If every unlocked vertex is a sharp corner (e.g. a manual 4-gon), allow smoothing free corners
  const hasModerateUnlocked = dense.some((_, i) => !locked[i] && turns[i] < sharpTipRad);

  const chaikinPass = (pts: Point[]): Point[] => {
    const m = pts.length;
    const ptLocked = pts.map(pt => neighbors.length > 0 && pointToNeighborsDistance(pt, neighbors) <= seamTolerancePx);
    const ptTurns = pts.map((cur, i) =>
      turningAngleRad(pts[(i - 1 + m) % m], cur, pts[(i + 1) % m]),
    );
    const out: Point[] = [];
    for (let i = 0; i < m; i++) {
      const curr = pts[i];
      const prev = pts[(i - 1 + m) % m];
      const next = pts[(i + 1) % m];
      const preserveSharp = hasModerateUnlocked && ptTurns[i] >= sharpTipRad;
      if (ptLocked[i] || preserveSharp) {
        out.push(curr);
      } else {
        out.push([0.25 * prev[0] + 0.75 * curr[0], 0.25 * prev[1] + 0.75 * curr[1]]);
        out.push([0.75 * curr[0] + 0.25 * next[0], 0.75 * curr[1] + 0.25 * next[1]]);
      }
    }
    return dedupeConsecutivePoints(out, 0.5);
  };

  const smoothedDense = chaikinPass(chaikinPass(dense));
  return fitSmoothPieceCurves(smoothedDense, neighbors, {
    cornerAngleDeg: 58,
    seamTolerancePx,
    preserveBevels: true,
  });
}

/**
 * Inset a closed polygon inward by `insetPx` pixels (miter-bevel offset) to
 * account for copper foil or lead came heart thickness when printing cut templates.
 */
export function insetPolygon(polygon: Point[], insetPx: number): Point[] {
  if (insetPx <= 0 || polygon.length < 3) return polygon;
  const pts = dedupeConsecutivePoints(polygon, 0.25);
  const n = pts.length;
  if (n < 3) return polygon;

  // Determine signed area so inward normal points into the polygon interior
  let signed = 0;
  for (let i = 0; i < n; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[(i + 1) % n];
    signed += x1 * y2 - x2 * y1;
  }
  const origArea = Math.abs(signed) / 2;
  if (origArea < 1) return polygon;
  const orient = signed >= 0 ? 1 : -1;

  // Inward unit normal for each directed edge i -> i+1
  const normals: Point[] = [];
  for (let i = 0; i < n; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[(i + 1) % n];
    const dx = x2 - x1, dy = y2 - y1;
    const len = Math.hypot(dx, dy);
    if (len < 1e-6) {
      normals.push([0, 0]);
    } else {
      normals.push([(-orient * dy) / len, (orient * dx) / len]);
    }
  }

  const miterLimit = 2.2;
  const offsetPts: Point[] = [];
  for (let i = 0; i < n; i++) {
    const nPrev = normals[(i - 1 + n) % n];
    const nCurr = normals[i];
    const bx = nPrev[0] + nCurr[0];
    const by = nPrev[1] + nCurr[1];
    const bLen = Math.hypot(bx, by);
    if (bLen < 1e-6) {
      offsetPts.push([pts[i][0] + nCurr[0] * insetPx, pts[i][1] + nCurr[1] * insetPx]);
      continue;
    }
    const ux = bx / bLen, uy = by / bLen;
    const cosHalf = ux * nCurr[0] + uy * nCurr[1];
    const miterScale = cosHalf > 1e-3 ? Math.min(miterLimit, 1 / cosHalf) : miterLimit;
    offsetPts.push([
      pts[i][0] + ux * insetPx * miterScale,
      pts[i][1] + uy * insetPx * miterScale,
    ]);
  }

  const newArea = computePolygonArea(offsetPts);
  // Guard against degenerate inversion on tiny sliver pieces
  if (newArea < origArea * 0.05 || newArea > origArea) {
    const c = computeCentroid(pts);
    return pts.map(([x, y]) => [c.x + (x - c.x) * 0.9, c.y + (y - c.y) * 0.9]);
  }
  return offsetPts;
}

/**
 * Convert a piece's polygon and optional `curvePoints` into an exact SVG `<path d="...">`
 * string using native cubic Bézier (`C`) commands for curved edges.
 */
export function pieceToSvgPath(polygon: Point[], curvePoints?: CurvePoint[]): string {
  if (polygon.length === 0) return '';
  const n = polygon.length;
  const curveMap = new Map((curvePoints ?? []).map(cp => [cp.edgeIdx, cp]));
  const fmt = (v: number) => Math.round(v * 100) / 100;
  const parts: string[] = [`M ${fmt(polygon[0][0])} ${fmt(polygon[0][1])}`];

  for (let i = 0; i < n; i++) {
    const start = polygon[i];
    const end = polygon[(i + 1) % n];
    const curve = curveMap.get(i);
    if (curve) {
      const [c1, c2] = curveToCubicControls(start, end, curve);
      parts.push(`C ${fmt(c1[0])} ${fmt(c1[1])}, ${fmt(c2[0])} ${fmt(c2[1])}, ${fmt(end[0])} ${fmt(end[1])}`);
    } else {
      parts.push(`L ${fmt(end[0])} ${fmt(end[1])}`);
    }
  }
  parts.push('Z');
  return parts.join(' ');
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
      Math.abs(maxArea - subjectArea) <= Math.max(0.5, subjectArea * 1e-4)
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

export function translateCurvesWithAnchor(
  curves: CurvePoint[],
  vertexIdx: number,
  vertexCount: number,
  delta: [number, number],
): CurvePoint[] {
  const previousEdge = (vertexIdx - 1 + vertexCount) % vertexCount;
  return curves.map(curve => {
    if (isCubicCurvePoint(curve)) {
      if (curve.edgeIdx === vertexIdx) {
        return { ...curve, ctrl: [curve.ctrl[0] + delta[0], curve.ctrl[1] + delta[1]] };
      }
      if (curve.edgeIdx === previousEdge) {
        return { ...curve, ctrl2: [curve.ctrl2[0] + delta[0], curve.ctrl2[1] + delta[1]] };
      }
      return curve;
    }
    if (curve.edgeIdx === vertexIdx || curve.edgeIdx === previousEdge) {
      return { ...curve, ctrl: [curve.ctrl[0] + delta[0] / 2, curve.ctrl[1] + delta[1] / 2] };
    }
    return curve;
  });
}
