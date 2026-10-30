import { describe, expect, it } from 'vitest';
import {
  arePolygonsEqual,
  curveToCubicControls,
  evaluateCubicBezier,
  evaluateQuadraticBezier,
  fitSmoothPieceCurves,
  flattenCurves,
  insetPolygon,
  isCubicCurvePoint,
  makeCubicCurvePoint,
  pieceToSvgPath,
  quadraticToCubicControls,
  smoothPieceGeometry,
  snapPolygonToNeighbors,
  splitCubicBezier,
  subtractPolygons,
} from './geometry';

describe('curve compatibility', () => {
  it('keeps legacy quadratic curves equivalent when converted to cubic controls', () => {
    const start: [number, number] = [0, 0];
    const control: [number, number] = [50, 80];
    const end: [number, number] = [100, 0];
    const [ctrl1, ctrl2] = quadraticToCubicControls(start, control, end);

    for (const t of [0, 0.1, 0.25, 0.5, 0.9, 1]) {
      const quadratic = evaluateQuadraticBezier(start, control, end, t);
      const cubic = evaluateCubicBezier(start, ctrl1, ctrl2, end, t);
      expect(cubic[0]).toBeCloseTo(quadratic[0], 8);
      expect(cubic[1]).toBeCloseTo(quadratic[1], 8);
    }
  });

  it('distinguishes saved cubic metadata from legacy quadratic metadata', () => {
    const cubic = makeCubicCurvePoint(0, [20, 40], [80, 40]);
    expect(isCubicCurvePoint(cubic)).toBe(true);
    expect(isCubicCurvePoint({ edgeIdx: 0, ctrl: [50, 50] })).toBe(false);
    expect(curveToCubicControls([0, 0], [100, 0], cubic)).toEqual([[20, 40], [80, 40]]);
  });

  it('splits cubic curves without a discontinuity', () => {
    const source = { start: [0, 0] as [number, number], ctrl1: [25, 80] as [number, number], ctrl2: [75, -20] as [number, number], end: [100, 0] as [number, number] };
    const [left, right] = splitCubicBezier(source, 0.37);
    expect(left.end[0]).toBeCloseTo(right.start[0], 10);
    expect(left.end[1]).toBeCloseTo(right.start[1], 10);
    const expected = evaluateCubicBezier(source.start, source.ctrl1, source.ctrl2, source.end, 0.37);
    expect(left.end[0]).toBeCloseTo(expected[0], 10);
    expect(left.end[1]).toBeCloseTo(expected[1], 10);
  });

  it('adaptively flattens a cubic while preserving polygon anchors', () => {
    const polygon: [number, number][] = [[0, 0], [100, 0], [100, 100]];
    const flattened = flattenCurves(polygon, [makeCubicCurvePoint(0, [20, 80], [80, 80])], 0.25);
    expect(flattened[0]).toEqual(polygon[0]);
    expect(flattened).toContainEqual(polygon[1]);
    expect(flattened.length).toBeGreaterThan(polygon.length);
  });

  it('clips an edited polygon against the visible boundary of a curved neighbor', () => {
    const neighbor = flattenCurves(
      [[0, 0], [100, 0], [100, 100], [0, 100]],
      [makeCubicCurvePoint(1, [130, 20], [130, 80])],
      0.25,
    );
    const crossingEdit: [number, number][] = [[90, 20], [160, 50], [90, 80]];
    const clipped = subtractPolygons(crossingEdit, [neighbor]);

    expect(clipped.length).toBeGreaterThanOrEqual(3);
    expect(clipped.every(([x]) => x >= 99.9)).toBe(true);
  });

  it('preserves exact vertex order when touching a neighbor along a shared edge', () => {
    const neighbor: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    const touching: [number, number][] = [[100, 10], [200, 10], [200, 90], [100, 90]];
    const clipped = subtractPolygons(touching, [neighbor]);
    expect(arePolygonsEqual(touching, clipped, 0.1)).toBe(true);
  });
});

describe('seam snapping and curve fitting for fabrication', () => {
  it('snaps directly to neighbor corners at T-junctions and bridges single-vertex seam gaps', () => {
    const neighbor: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    // Piece shares x=100 edge with neighbor: top vertex near [100, 0], middle vertex slightly pulled back at x=91, bottom vertex near [100, 100]
    const raw: [number, number][] = [[103, 2], [200, 0], [200, 100], [102, 98], [91, 50]];
    const snapped = snapPolygonToNeighbors(raw, [neighbor], 8);

    // Top and bottom corners snap directly to [100, 0] and [100, 100], and the mid-seam gap at x=91 is closed onto x=100
    expect(snapped).toContainEqual([100, 0]);
    expect(snapped).toContainEqual([100, 100]);
    expect(snapped.every(([x]) => x >= 100)).toBe(true);
  });

  it('converts a faceted leaf contour into smooth cubic Béziers while keeping sharp tips and shared seams locked', () => {
    const neighbor: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    // Leaf sharing the vertical seam from (100, 20) to (100, 80) and arching out to a sharp tip at (220, 50)
    const upperArc: [number, number][] = [
      [100, 20],
      [125, 8],
      [155, 4],
      [185, 14],
      [220, 50], // sharp tip
      [185, 86],
      [155, 96],
      [125, 92],
      [100, 80],
    ];
    const fitted = fitSmoothPieceCurves(upperArc, [neighbor], { seamTolerancePx: 2.5 });

    // Should simplify the 9 faceted points into structural anchors with cubic curves on the two free arcs
    expect(fitted.polygon.length).toBeLessThan(upperArc.length);
    expect(fitted.curvePoints.length).toBeGreaterThanOrEqual(2);
    // Sharp tip at [220, 50] and seam endpoints [100, 20], [100, 80] are preserved as corner anchors
    expect(fitted.polygon).toContainEqual([220, 50]);
    expect(fitted.polygon).toContainEqual([100, 20]);
    expect(fitted.polygon).toContainEqual([100, 80]);

    // The locked seam edge from [100, 80] -> [100, 20] must remain a straight un-curved segment
    const seamStartIdx = fitted.polygon.findIndex(p => p[0] === 100 && p[1] === 80);
    expect(seamStartIdx).toBeGreaterThanOrEqual(0);
    expect(fitted.curvePoints.some(cp => cp.edgeIdx === seamStartIdx)).toBe(false);
  });

  it('smoothPieceGeometry rounds moderate kinks while pinning neighbor-shared seams', () => {
    const neighbor: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    const kinked: [number, number][] = [
      [100, 20],
      [150, 5],
      [200, 50],
      [150, 95],
      [100, 80],
    ];
    const smoothed = smoothPieceGeometry(kinked, [], [neighbor], 2.5);
    expect(smoothed.polygon).toContainEqual([100, 20]);
    expect(smoothed.polygon).toContainEqual([100, 80]);
    expect(smoothed.curvePoints.length).toBeGreaterThan(0);
  });

  it('insets a polygon inward by exact physical allowance for foil/came pattern shears', () => {
    const square: [number, number][] = [[0, 0], [100, 0], [100, 80], [0, 80]];
    const inset = insetPolygon(square, 2.5);
    expect(inset).toHaveLength(4);
    expect(inset[0][0]).toBeCloseTo(2.5, 4);
    expect(inset[0][1]).toBeCloseTo(2.5, 4);
    expect(inset[2][0]).toBeCloseTo(97.5, 4);
    expect(inset[2][1]).toBeCloseTo(77.5, 4);
  });

  it('serializes curved pieces to native SVG cubic Bézier path commands', () => {
    const poly: [number, number][] = [[0, 0], [100, 0], [50, 80]];
    const curves = [makeCubicCurvePoint(0, [30, -20], [70, -20])];
    const d = pieceToSvgPath(poly, curves);
    expect(d).toContain('M 0 0');
    expect(d).toContain('C 30 -20, 70 -20, 100 0');
    expect(d).toContain('L 50 80');
    expect(d.endsWith('Z')).toBe(true);
  });
});
