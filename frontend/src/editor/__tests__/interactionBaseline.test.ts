import { describe, expect, it, vi } from 'vitest';

vi.mock('react-konva', () => ({
  Stage: () => null,
  Layer: () => null,
  Image: () => null,
  Line: () => null,
  Group: () => null,
  Rect: () => null,
  Circle: () => null,
  Text: () => null,
}));
vi.mock('use-image', () => ({ default: () => [null] }));
import {
  findAlignmentGuides,
  findLengthSnap,
  findPenSnapTarget,
  findShiftAlignmentGuides,
  getCanvasSnapping,
  simplifyPath,
} from '../../components/ResultPanel';
import { makeInteractionPieces } from '../performance/fixtures';

const translate = (key: string) => key;

describe('interaction fixtures', () => {
  it.each([25, 100, 250, 500])('generates %i deterministic pieces', count => {
    const first = makeInteractionPieces(count, 24);
    const second = makeInteractionPieces(count, 24);
    expect(first).toEqual(second);
    expect(first).toHaveLength(count);
    expect(first[0].polygon).toHaveLength(24);
  });
});

describe('current Pen behavior', () => {
  const pieces = makeInteractionPieces(25, 6);

  it('snaps to the nearest eligible vertex inside 14 screen pixels', () => {
    expect(findPenSnapTarget([49, 30], pieces, 1)?.pt).toEqual([48, 30]);
    expect(findPenSnapTarget([1200, 900], pieces, 1)).toBeNull();
  });

  it('resolves independent horizontal and vertical alignment', () => {
    expect(findAlignmentGuides([48.5, 46], pieces, 1)).toEqual({
      snapped: [48, 45.588457268119896],
      guides: [
        { type: 'v', from: [48, 30], to: [48, 45.588457268119896] },
        { type: 'h', from: [21.000000000000004, 45.588457268119896], to: [48, 45.588457268119896] },
      ],
    });
  });

  it('preserves projected Shift alignment', () => {
    const result = findShiftAlignmentGuides([50, 50], [30, 30], Math.PI / 4, pieces, 1);
    expect(result.snapped[0]).toBeCloseTo(48);
    expect(result.snapped[1]).toBeCloseTo(48);
    expect(result.guides).toHaveLength(1);
  });

  it('finds equal length from the active draft', () => {
    const result = findLengthSnap([50, 30], [30, 30], [], [[10, 30], [30, 30]], 1);
    expect(result?.matchLength).toBe(20);
  });

  it('keeps edge and fractional canvas snapping', () => {
    const crop = { left: 10, right: 10, top: 20, bottom: 20 };
    expect(getCanvasSnapping(11, 50, crop, 210, 120, 1, translate).x).toBe(10);
    const fraction = getCanvasSnapping(105, 51, crop, 210, 120, 1, translate);
    expect(fraction.x).toBe(105);
    expect(fraction.labels).toContain('snapCenter');
  });
});

describe('current Pencil simplification', () => {
  it('preserves fixed reference outputs', () => {
    expect(simplifyPath([[0, 0], [1, 0.1], [2, 0], [3, 3], [4, 3]], 0.25)).toEqual([
      [0, 0], [2, 0], [3, 3], [4, 3],
    ]);
    expect(simplifyPath([[0, 0], [1, 1], [2, 2], [3, 3]], 0.1)).toEqual([[0, 0], [3, 3]]);
  });
});
