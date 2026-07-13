import { describe, expect, it, vi } from 'vitest';
vi.mock('react-konva', () => ({ Stage: () => null, Layer: () => null, Image: () => null, Line: () => null, Group: () => null, Rect: () => null, Circle: () => null, Text: () => null }));
vi.mock('use-image', () => ({ default: () => [null] }));
import { findAlignmentGuides, findLengthSnap, findPenSnapTarget, findShiftAlignmentGuides } from '../../components/ResultPanel';
import { createPenSnapIndex, queryAlignment, queryLengthSnap, queryShiftAlignment, queryVertexSnap } from '../snapping/penSnapIndex';
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
      const last: [number, number] = [random() * 1100, random() * 300];
      const theta = Math.round(random() * 8) * Math.PI / 4;
      expect(queryShiftAlignment(index, cursor, last, theta, scale, 14)).toEqual(
        findShiftAlignmentGuides(cursor, last, theta, pieces, scale),
      );
    }
  });

  it('preserves piece iteration order for equal-distance ties', () => {
    const pieces = makeInteractionPieces(2, 6);
    const index = createPenSnapIndex(pieces);
    const cursor: [number, number] = [52.5, 30];
    expect(queryVertexSnap(index, cursor, 1, 14)).toEqual(findPenSnapTarget(cursor, pieces, 1));
  });

  it('preserves project order for equal-length ties regardless of active-point order', () => {
    const pieces = makeInteractionPieces(8, 6);
    const index = createPenSnapIndex(pieces);
    const active: [number, number][] = [pieces[7].polygon[0], pieces[0].polygon[0]];
    const last: [number, number] = [100, 100];
    const cursor: [number, number] = [117, 100];
    expect(queryLengthSnap(index, cursor, last, active, 1, 14)).toEqual(
      findLengthSnap(cursor, last, pieces, active, 1, 14),
    );
  });

  it.each([6, 24, 96])('matches linear equal-length ties across randomized active drafts at %i vertices', vertexCount => {
    const pieces = makeInteractionPieces(100, vertexCount);
    const index = createPenSnapIndex(pieces);
    let seed = 987654321 + vertexCount;
    const random = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 0x100000000;
    };

    for (let sample = 0; sample < 200; sample += 1) {
      const selected = Array.from({ length: 2 + Math.floor(random() * 3) }, () =>
        Math.floor(random() * pieces.length),
      );
      const active = selected.map(pieceIndex => {
        const polygon = pieces[pieceIndex].polygon;
        return polygon[Math.floor(random() * polygon.length)];
      });
      if (random() < 0.5) active.reverse();

      const reference = pieces[selected[0]].polygon;
      const edge = Math.floor(random() * reference.length);
      const p1 = reference[edge];
      const p2 = reference[(edge + 1) % reference.length];
      const targetLength = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
      const scale = 0.5 + random() * 3;
      const last: [number, number] = [random() * 1100, random() * 300];
      const angle = random() * Math.PI * 2;
      const length = targetLength + (random() - 0.5) * (12 / scale);
      const cursor: [number, number] = [last[0] + Math.cos(angle) * length, last[1] + Math.sin(angle) * length];

      expect(queryLengthSnap(index, cursor, last, active, scale, 14)).toEqual(
        findLengthSnap(cursor, last, pieces, active, scale, 14),
      );
    }
  });
});
