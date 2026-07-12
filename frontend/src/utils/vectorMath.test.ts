import { describe, expect, it } from 'vitest';
import { constrainToAngle, nearestCandidate } from './vectorMath';

describe('vector constraints', () => {
  it('makes a 45 degree constraint final', () => {
    const result = constrainToAngle([9, 7], [0, 0]);
    expect(result[0]).toBeCloseTo(result[1], 10);
    expect(Math.hypot(...result)).toBeCloseTo(Math.hypot(9, 7), 10);
  });

  it('selects the nearest snap candidate rather than enumeration order', () => {
    const candidates = [
      { value: 1 / 3, position: 33.333 },
      { value: 3 / 8, position: 37.5 },
    ];
    expect(nearestCandidate(37, candidates, 1, 14)?.value).toBe(3 / 8);
  });

  it('uses screen-space tolerance at every zoom level', () => {
    const candidate = [{ value: 0.5, position: 50 }];
    expect(nearestCandidate(55, candidate, 2, 14)).not.toBeNull();
    expect(nearestCandidate(58, candidate, 2, 14)).toBeNull();
  });
});
