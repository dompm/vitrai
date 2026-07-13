import type { Piece } from '../../types';
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

export interface PenSnapIndex {
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
    vertices,
    byX: [...vertices].sort((a, b) => a.x - b.x || a.order - b.order),
    byY: [...vertices].sort((a, b) => a.y - b.y || a.order - b.order),
    anchors,
    anchorsByX: [...anchors].sort((a, b) => a.x - b.x || a.order - b.order),
    segmentsByPiece,
    piecesByVertex: piecesByVertexMutable,
  };
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
  pieceIds.forEach(id => segments.push(...index.segmentsByPiece[id]));
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
