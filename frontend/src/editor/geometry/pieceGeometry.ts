import type { CurvePoint } from '../../types';
import { flattenCurves } from '../../utils/geometry';

export interface PieceGeometry {
  displayPolygon: [number, number][];
  flatPoints: number[];
  centroid: { x: number; y: number };
  bounds: { minX: number; minY: number; maxX: number; maxY: number };
  localBoundingRadius: number;
  segments: Array<{
    p1: [number, number];
    p2: [number, number];
    length: number;
  }>;
  clipFunc: (ctx: any) => void;
}

const straightCache = new WeakMap<[number, number][], PieceGeometry>();
const curvedCache = new WeakMap<
  [number, number][],
  WeakMap<CurvePoint[], PieceGeometry>
>();

function buildGeometry(
  polygon: [number, number][],
  curvePoints?: CurvePoint[],
): PieceGeometry {
  const displayPolygon = flattenCurves(polygon, curvePoints);
  const flatPoints = displayPolygon.flat();
  let sumX = 0;
  let sumY = 0;
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const [x, y] of displayPolygon) {
    sumX += x;
    sumY += y;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }

  const count = displayPolygon.length;
  const centroid = count > 0 ? { x: sumX / count, y: sumY / count } : { x: 0, y: 0 };
  let localBoundingRadius = 0;
  for (const [x, y] of displayPolygon) {
    localBoundingRadius = Math.max(
      localBoundingRadius,
      Math.hypot(x - centroid.x, y - centroid.y),
    );
  }

  const segments = displayPolygon.map((p1, index) => {
    const p2 = displayPolygon[(index + 1) % displayPolygon.length] ?? p1;
    return { p1, p2, length: Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) };
  });
  const clipFunc = (ctx: any) => {
    ctx.beginPath();
    displayPolygon.forEach(([x, y], index) => {
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
  };

  return {
    displayPolygon,
    flatPoints,
    centroid,
    bounds: count > 0 ? { minX, minY, maxX, maxY } : { minX: 0, minY: 0, maxX: 0, maxY: 0 },
    localBoundingRadius,
    segments,
    clipFunc,
  };
}

export function getPieceGeometry(
  polygon: [number, number][],
  curvePoints?: CurvePoint[],
): PieceGeometry {
  if (!curvePoints || curvePoints.length === 0) {
    const cached = straightCache.get(polygon);
    if (cached) return cached;
    const geometry = buildGeometry(polygon);
    straightCache.set(polygon, geometry);
    return geometry;
  }

  let byCurves = curvedCache.get(polygon);
  if (!byCurves) {
    byCurves = new WeakMap<CurvePoint[], PieceGeometry>();
    curvedCache.set(polygon, byCurves);
  }
  const cached = byCurves.get(curvePoints);
  if (cached) return cached;
  const geometry = buildGeometry(polygon, curvePoints);
  byCurves.set(curvePoints, geometry);
  return geometry;
}
