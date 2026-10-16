import type { Piece } from '../../types';
import { flattenCurves } from '../../utils/geometry';
import { getPieceGeometry } from '../geometry/pieceGeometry';

interface IndexedVertex {
  x: number;
  y: number;
  order: number;
}

interface IndexedAnchor extends IndexedVertex {
  prevX: number;
  prevY: number;
  nextX: number;
  nextY: number;
}

interface ExtraSnapPoint {
  pt: [number, number];
  label?: string;
}

interface SnapTarget {
  pt: [number, number];
  label?: string;
}

interface IndexedSegment {
  start: [number, number];
  end: [number, number];
  order: number;
}

interface EdgeSnapCache {
  effectiveScale: number;
  cellSize: number;
  segments: readonly IndexedSegment[];
  grid: ReadonlyMap<string, readonly number[]>;
}

const edgeSnapCaches = new WeakMap<PenSnapIndex, EdgeSnapCache>();

export interface PenSnapIndex {
  readonly pieces: readonly Piece[];
  /** Flattened display vertices, matching alignment and Shift-alignment behavior. */
  readonly vertices: readonly IndexedVertex[];
  readonly byX: readonly IndexedVertex[];
  readonly byY: readonly IndexedVertex[];
  /** Editable polygon anchors, matching vertex-snap behavior on curved pieces. */
  readonly anchors: readonly IndexedAnchor[];
  readonly anchorsByX: readonly IndexedAnchor[];
  readonly segmentsByPiece: ReadonlyArray<readonly { length: number; p1: [number, number]; p2: [number, number] }[]>;
  readonly piecesByVertex: ReadonlyMap<string, readonly number[]>;
}

export function createPenSnapIndex(pieces: Piece[]): PenSnapIndex {
  const vertices: IndexedVertex[] = [];
  const anchors: IndexedAnchor[] = [];
  const segmentsByPiece: Array<Array<{ length: number; p1: [number, number]; p2: [number, number] }>> = [];
  const piecesByVertexMutable = new Map<string, number[]>();
  let vertexOrder = 0;
  let anchorOrder = 0;

  for (const [pieceIndex, piece] of pieces.entries()) {
    const geometry = getPieceGeometry(piece.polygon, piece.curvePoints);
    const displayPolygon = geometry.displayPolygon;
    segmentsByPiece[pieceIndex] = geometry.segments;

    displayPolygon.forEach(([x, y]) => {
      vertices.push({ x, y, order: vertexOrder++ });
      const key = `${x},${y}`;
      const matchingPieces = piecesByVertexMutable.get(key) ?? [];
      if (matchingPieces[matchingPieces.length - 1] !== pieceIndex) matchingPieces.push(pieceIndex);
      piecesByVertexMutable.set(key, matchingPieces);
    });

    piece.polygon.forEach(([x, y], index) => {
      const prev = piece.polygon[(index - 1 + piece.polygon.length) % piece.polygon.length];
      const next = piece.polygon[(index + 1) % piece.polygon.length];
      anchors.push({
        x,
        y,
        prevX: prev[0],
        prevY: prev[1],
        nextX: next[0],
        nextY: next[1],
        order: anchorOrder++,
      });
    });
  }

  return {
    pieces,
    vertices,
    byX: [...vertices].sort((a, b) => a.x - b.x || a.order - b.order),
    byY: [...vertices].sort((a, b) => a.y - b.y || a.order - b.order),
    anchors,
    anchorsByX: [...anchors].sort((a, b) => a.x - b.x || a.order - b.order),
    segmentsByPiece,
    piecesByVertex: piecesByVertexMutable,
  };
}

function gridKey(x: number, y: number) {
  return `${x},${y}`;
}

function createEdgeSnapCache(index: PenSnapIndex, effectiveScale: number): EdgeSnapCache {
  const safeScale = Math.max(effectiveScale, 0.01);
  const cellSize = 64 / safeScale;
  const segments: IndexedSegment[] = [];
  const grid = new Map<string, number[]>();

  for (const piece of index.pieces) {
    const path = flattenCurves(piece.polygon, piece.curvePoints, 0.5 / safeScale);
    for (let pathIndex = 0; pathIndex < path.length; pathIndex += 1) {
      const start = path[pathIndex];
      const end = path[(pathIndex + 1) % path.length];
      const segment: IndexedSegment = { start, end, order: segments.length };
      segments.push(segment);
      const minCellX = Math.floor(Math.min(start[0], end[0]) / cellSize);
      const maxCellX = Math.floor(Math.max(start[0], end[0]) / cellSize);
      const minCellY = Math.floor(Math.min(start[1], end[1]) / cellSize);
      const maxCellY = Math.floor(Math.max(start[1], end[1]) / cellSize);
      for (let cellX = minCellX; cellX <= maxCellX; cellX += 1) {
        for (let cellY = minCellY; cellY <= maxCellY; cellY += 1) {
          const key = gridKey(cellX, cellY);
          const entries = grid.get(key) ?? [];
          entries.push(segment.order);
          grid.set(key, entries);
        }
      }
    }
  }

  return { effectiveScale, cellSize, segments, grid };
}

export function queryEdgeSnap(
  index: PenSnapIndex,
  cursor: [number, number],
  effectiveScale: number,
  tolerancePx: number,
): [number, number] | null {
  let cache = edgeSnapCaches.get(index);
  if (!cache || cache.effectiveScale !== effectiveScale) {
    cache = createEdgeSnapCache(index, effectiveScale);
    edgeSnapCaches.set(index, cache);
  }

  const tolerance = tolerancePx / effectiveScale;
  const minCellX = Math.floor((cursor[0] - tolerance) / cache.cellSize);
  const maxCellX = Math.floor((cursor[0] + tolerance) / cache.cellSize);
  const minCellY = Math.floor((cursor[1] - tolerance) / cache.cellSize);
  const maxCellY = Math.floor((cursor[1] + tolerance) / cache.cellSize);
  const candidateOrders = new Set<number>();
  for (let cellX = minCellX; cellX <= maxCellX; cellX += 1) {
    for (let cellY = minCellY; cellY <= maxCellY; cellY += 1) {
      cache.grid.get(gridKey(cellX, cellY))?.forEach(order => candidateOrders.add(order));
    }
  }

  let best: [number, number] | null = null;
  let bestDistance = tolerancePx;
  for (const order of [...candidateOrders].sort((a, b) => a - b)) {
    const segment = cache.segments[order];
    const dx = segment.end[0] - segment.start[0];
    const dy = segment.end[1] - segment.start[1];
    const lengthSquared = dx * dx + dy * dy;
    if (lengthSquared === 0) continue;
    const parameter = Math.max(0, Math.min(1,
      ((cursor[0] - segment.start[0]) * dx + (cursor[1] - segment.start[1]) * dy) / lengthSquared,
    ));
    const projected: [number, number] = [
      segment.start[0] + parameter * dx,
      segment.start[1] + parameter * dy,
    ];
    const distance = Math.hypot(projected[0] - cursor[0], projected[1] - cursor[1]) * effectiveScale;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = projected;
    }
  }
  return best;
}

export function queryLengthSnap(
  index: PenSnapIndex,
  cursor: [number, number],
  lastPoint: [number, number],
  activePoints: [number, number][],
  effectiveScale: number,
  tolerancePx: number,
) {
  const segments: Array<{ length: number; p1: [number, number]; p2: [number, number] }> = [];
  for (let i = 0; i < activePoints.length - 1; i += 1) {
    const p1 = activePoints[i];
    const p2 = activePoints[i + 1];
    segments.push({ length: Math.hypot(p2[0] - p1[0], p2[1] - p1[1]), p1, p2 });
  }
  const pieceIds = new Set<number>();
  activePoints.forEach(point => index.piecesByVertex.get(`${point[0]},${point[1]}`)?.forEach(id => pieceIds.add(id)));
  index.segmentsByPiece.forEach((pieceSegments, pieceIndex) => {
    if (pieceIds.has(pieceIndex)) segments.push(...pieceSegments);
  });
  const currentLength = Math.hypot(cursor[0] - lastPoint[0], cursor[1] - lastPoint[1]);
  let best: (typeof segments)[number] | null = null;
  let bestDifference = tolerancePx / effectiveScale;
  for (const segment of segments) {
    const difference = Math.abs(segment.length - currentLength);
    if (difference < bestDifference) {
      bestDifference = difference;
      best = segment;
    }
  }
  return best ? { matchLength: best.length, matchingSegment: { p1: best.p1, p2: best.p2 } } : null;
}

function lowerBound<T extends IndexedVertex>(values: readonly T[], target: number, axis: 'x' | 'y') {
  let low = 0;
  let high = values.length;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (values[mid][axis] < target) low = mid + 1;
    else high = mid;
  }
  return low;
}

function range<T extends IndexedVertex>(values: readonly T[], value: number, tolerance: number, axis: 'x' | 'y') {
  const result: T[] = [];
  for (let index = lowerBound(values, value - tolerance, axis); index < values.length; index += 1) {
    if (values[index][axis] > value + tolerance) break;
    result.push(values[index]);
  }
  return result;
}

export function queryVertexSnap(
  index: PenSnapIndex,
  cursor: [number, number],
  effectiveScale: number,
  thresholdPx: number,
  extraVertices?: readonly ExtraSnapPoint[],
): SnapTarget | null {
  const tolerance = thresholdPx / effectiveScale;
  let best: IndexedAnchor | null = null;
  let bestDistance = thresholdPx;

  for (const anchor of range(index.anchorsByX, cursor[0], tolerance, 'x')) {
    const nextLength = Math.hypot(anchor.nextX - anchor.x, anchor.nextY - anchor.y) * effectiveScale;
    const prevLength = Math.hypot(anchor.x - anchor.prevX, anchor.y - anchor.prevY) * effectiveScale;
    if (nextLength < thresholdPx && prevLength < thresholdPx) continue;
    const distance = Math.hypot(anchor.x - cursor[0], anchor.y - cursor[1]) * effectiveScale;
    if (distance < bestDistance || (distance === bestDistance && anchor.order < (best?.order ?? Infinity))) {
      bestDistance = distance;
      best = anchor;
    }
  }

  let result: SnapTarget | null = best ? { pt: [best.x, best.y] } : null;
  if (extraVertices) {
    for (const extra of extraVertices) {
      const distance = Math.hypot(extra.pt[0] - cursor[0], extra.pt[1] - cursor[1]) * effectiveScale;
      if (distance < bestDistance) {
        bestDistance = distance;
        result = { pt: [extra.pt[0], extra.pt[1]], label: extra.label };
      }
    }
  }
  return result;
}

export function queryAlignment(index: PenSnapIndex, cursor: [number, number], effectiveScale: number, thresholdPx: number) {
  const tolerance = thresholdPx / effectiveScale;
  const nearest = (axis: 'x' | 'y') => {
    let best: IndexedVertex | null = null;
    let bestDistance = thresholdPx;
    const values = axis === 'x' ? index.byX : index.byY;
    for (const vertex of range(values, cursor[axis === 'x' ? 0 : 1], tolerance, axis)) {
      const distance = Math.abs(vertex[axis] - cursor[axis === 'x' ? 0 : 1]) * effectiveScale;
      if (distance < bestDistance || (distance === bestDistance && vertex.order < (best?.order ?? Infinity))) {
        best = vertex;
        bestDistance = distance;
      }
    }
    return best;
  };
  const x = nearest('x');
  const y = nearest('y');
  const point: [number, number] = [x?.x ?? cursor[0], y?.y ?? cursor[1]];
  return {
    snapped: point,
    guides: [
      ...(x ? [{ type: 'v' as const, from: [x.x, x.y] as [number, number], to: point }] : []),
      ...(y ? [{ type: 'h' as const, from: [y.x, y.y] as [number, number], to: point }] : []),
    ],
  };
}

export function queryShiftAlignment(
  index: PenSnapIndex,
  cursor: [number, number],
  lastPoint: [number, number],
  theta: number,
  effectiveScale: number,
  thresholdPx: number,
) {
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  let bestDistance = thresholdPx;
  let snapped: [number, number] = cursor;
  let guide: { type: 'v' | 'h'; from: [number, number]; to: [number, number] } | null = null;
  for (const vertex of index.vertices) {
    if (Math.abs(cos) > 1e-5) {
      const radius = (vertex.x - lastPoint[0]) / cos;
      if (radius >= 0) {
        const projected: [number, number] = [vertex.x, lastPoint[1] + radius * sin];
        const distance = Math.hypot(cursor[0] - projected[0], cursor[1] - projected[1]) * effectiveScale;
        if (distance < bestDistance) {
          bestDistance = distance;
          snapped = projected;
          guide = { type: 'v', from: [vertex.x, vertex.y], to: projected };
        }
      }
    }
    if (Math.abs(sin) > 1e-5) {
      const radius = (vertex.y - lastPoint[1]) / sin;
      if (radius >= 0) {
        const projected: [number, number] = [lastPoint[0] + radius * cos, vertex.y];
        const distance = Math.hypot(cursor[0] - projected[0], cursor[1] - projected[1]) * effectiveScale;
        if (distance < bestDistance) {
          bestDistance = distance;
          snapped = projected;
          guide = { type: 'h', from: [vertex.x, vertex.y], to: projected };
        }
      }
    }
  }
  return { snapped, guides: guide ? [guide] : [] };
}
