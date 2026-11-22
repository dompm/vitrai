import { describe, expect, it } from 'vitest';
import {
  computePenAnchorAfterDrag,
  shouldActivatePenDrag,
  type PenDragAnchor,
  type PenDragSession,
} from '../interaction/penGestures';

describe('penGestures', () => {
  describe('shouldActivatePenDrag', () => {
    it('does not activate on tiny jitter even after a long hold', () => {
      expect(shouldActivatePenDrag([100, 100], [104, 103], 500)).toBe(false);
    });

    it('does not activate on a fast click-and-move under 12px before 120ms', () => {
      expect(shouldActivatePenDrag([100, 100], [109, 100], 60)).toBe(false);
    });

    it('activates immediately once pointer moves >= 12px from raw pointerdown', () => {
      expect(shouldActivatePenDrag([100, 100], [112, 100], 20)).toBe(true);
    });

    it('activates at >= 6px once held for >= 120ms', () => {
      expect(shouldActivatePenDrag([100, 100], [106, 100], 120)).toBe(true);
    });
  });

  describe('computePenAnchorAfterDrag', () => {
    const baseSession: PenDragSession = {
      index: 1,
      downScreen: [100, 100],
      downTimeMs: 0,
      activated: true,
      isClosing: false,
      altLocked: false,
    };

    it('pulls symmetric smooth handles on a normal drag', () => {
      const anchor: PenDragAnchor = { point: [100, 100], smooth: false };
      const res = computePenAnchorAfterDrag({
        anchor,
        handle: [130, 80],
        effectiveScale: 1,
        altKey: false,
        session: baseSession,
      });
      expect(res.anchor.smooth).toBe(true);
      expect(res.anchor.out).toEqual([130, 80]);
      expect(res.anchor.in).toEqual([70, 120]);
    });

    it('freezes the incoming handle and pivots only the outgoing handle when Alt is pressed mid-drag', () => {
      const anchor: PenDragAnchor = {
        point: [100, 100],
        in: [70, 120],
        out: [130, 80],
        smooth: true,
      };
      const res = computePenAnchorAfterDrag({
        anchor,
        handle: [120, 140],
        effectiveScale: 1,
        altKey: true,
        session: baseSession,
      });
      expect(res.anchor.smooth).toBe(false);
      expect(res.anchor.in).toEqual([70, 120]);
      expect(res.anchor.out).toEqual([120, 140]);
      expect(res.session.altLocked).toBe(true);
    });

    it('preserves anchor 0 outgoing handle when Alt-dragging to close a path', () => {
      const closingAnchor: PenDragAnchor = {
        point: [50, 50],
        out: [80, 50],
        smooth: true,
      };
      const closingSession: PenDragSession = {
        ...baseSession,
        index: 0,
        isClosing: true,
        frozenOut: [80, 50],
      };
      const res = computePenAnchorAfterDrag({
        anchor: closingAnchor,
        handle: [50, 80],
        effectiveScale: 1,
        altKey: true,
        session: closingSession,
      });
      expect(res.anchor.smooth).toBe(false);
      expect(res.anchor.out).toEqual([80, 50]);
      expect(res.anchor.in).toEqual([50, 20]);
    });
  });
});
