import { describe, expect, it } from 'vitest';
import { getPieceGeometry } from '../geometry/pieceGeometry';
import { flattenCurves } from '../../utils/geometry';

describe('piece geometry cache', () => {
  const polygon: [number, number][] = [[0, 0], [10, 0], [10, 10], [0, 10]];

  it('keeps straight geometry referentially stable', () => {
    const first = getPieceGeometry(polygon);
    expect(getPieceGeometry(polygon)).toBe(first);
    expect(getPieceGeometry(polygon, [])).toBe(first);
    expect(first.centroid).toEqual({ x: 5, y: 5 });
    expect(first.bounds).toEqual({ minX: 0, minY: 0, maxX: 10, maxY: 10 });
    expect(first.segments.map(segment => segment.length)).toEqual([10, 10, 10, 10]);
  });

  it('keys curved geometry by both array identities without changing flattening', () => {
    const curves = [{ edgeIdx: 0, ctrl: [5, 5] as [number, number] }];
    const first = getPieceGeometry(polygon, curves);
    expect(getPieceGeometry(polygon, curves)).toBe(first);
    expect(first.displayPolygon).toEqual(flattenCurves(polygon, curves));
    expect(getPieceGeometry(polygon, [...curves])).not.toBe(first);
  });
});
