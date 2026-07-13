import { describe, expect, it, vi } from 'vitest';
vi.mock('react-konva', () => ({ Stage: () => null, Layer: () => null, Image: () => null, Line: () => null, Group: () => null, Rect: () => null, Circle: () => null, Text: () => null }));
vi.mock('use-image', () => ({ default: () => [null] }));
import { findAlignmentGuides, findPenSnapTarget } from '../../components/ResultPanel';
import { createPenSnapIndex, queryAlignment, queryVertexSnap } from '../snapping/penSnapIndex';
import { makeInteractionPieces } from '../performance/fixtures';

describe('Pen snap index parity', () => {
  it.each([6, 24, 96])('matches linear vertex and alignment results at %i vertices', vertexCount => {
    const pieces = makeInteractionPieces(100, vertexCount);
    const index = createPenSnapIndex(pieces);
    let seed = 123456;
    const random = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 0x100000000;
    };
    for (let sample = 0; sample < 200; sample += 1) {
      const cursor: [number, number] = [random() * 1100, random() * 300];
      const scale = 0.5 + random() * 3;
      expect(queryVertexSnap(index, cursor, scale, 14)).toEqual(findPenSnapTarget(cursor, pieces, scale));
      expect(queryAlignment(index, cursor, scale, 14)).toEqual(findAlignmentGuides(cursor, pieces, scale));
    }
  });

  it('preserves piece iteration order for equal-distance ties', () => {
    const pieces = makeInteractionPieces(2, 6);
    const index = createPenSnapIndex(pieces);
    const cursor: [number, number] = [52.5, 30];
    expect(queryVertexSnap(index, cursor, 1, 14)).toEqual(findPenSnapTarget(cursor, pieces, 1));
  });
});
