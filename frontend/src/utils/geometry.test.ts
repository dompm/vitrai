import { describe, expect, it } from 'vitest';
import {
  curveToCubicControls,
  evaluateCubicBezier,
  evaluateQuadraticBezier,
  flattenCurves,
  isCubicCurvePoint,
  makeCubicCurvePoint,
  quadraticToCubicControls,
  splitCubicBezier,
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
});
