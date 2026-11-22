export interface PenDragAnchor {
  point: [number, number];
  in?: [number, number];
  out?: [number, number];
  smooth: boolean;
}

/**
 * Click-vs-drag thresholds for the Pen tool, measured from the raw pointerdown
 * screen position (never from the snapped anchor, which may be up to PEN_SNAP_PX away).
 *
 * Hybrid gate: activates immediately once the pointer moves >= 12 CSS px,
 * or after >= 6 CSS px when held for >= 120 ms. Fast click-and-move toward the
 * next corner won't accidentally pull curve handles.
 */
export const PEN_DRAG_FAST_PX = 12;
export const PEN_DRAG_HOLD_PX = 6;
export const PEN_DRAG_HOLD_MS = 120;
export const PEN_DRAG_RETRACT_PX = 4;

export interface PenDragSession {
  index: number;
  /** Raw pointerdown position in screen (stage) pixels. */
  downScreen: [number, number];
  downTimeMs: number;
  /** True once the pointer has crossed the click-vs-drag gate. */
  activated: boolean;
  /** True when clicking/dragging anchor 0 to close an existing >=3-anchor path. */
  isClosing: boolean;
  /** Handle frozen when Alt is held/pressed mid-drag so only the free handle pivots. */
  frozenIn?: [number, number];
  frozenOut?: [number, number];
  altLocked: boolean;
}

export function shouldActivatePenDrag(
  downScreen: [number, number],
  currentScreen: [number, number],
  elapsedMs: number,
): boolean {
  const dist = Math.hypot(currentScreen[0] - downScreen[0], currentScreen[1] - downScreen[1]);
  if (dist >= PEN_DRAG_FAST_PX) return true;
  return dist >= PEN_DRAG_HOLD_PX && elapsedMs >= PEN_DRAG_HOLD_MS;
}

export function computePenAnchorAfterDrag(opts: {
  anchor: PenDragAnchor;
  handle: [number, number];
  effectiveScale: number;
  altKey: boolean;
  session: PenDragSession;
}): { anchor: PenDragAnchor; session: PenDragSession } {
  const { anchor, handle, effectiveScale, altKey, session } = opts;
  const distToAnchorPx = Math.hypot(handle[0] - anchor.point[0], handle[1] - anchor.point[1]) * effectiveScale;

  // Pulling back onto the anchor retracts handles cleanly
  if (distToAnchorPx < PEN_DRAG_RETRACT_PX) {
    if (session.isClosing) {
      return {
        anchor: {
          point: anchor.point,
          out: session.frozenOut,
          smooth: false,
        },
        session,
      };
    }
    return {
      anchor: {
        point: anchor.point,
        in: altKey ? session.frozenIn : undefined,
        smooth: false,
      },
      session,
    };
  }

  const dx = handle[0] - anchor.point[0];
  const dy = handle[1] - anchor.point[1];
  const nextSession: PenDragSession = { ...session };

  if (altKey) {
    if (!nextSession.altLocked) {
      nextSession.altLocked = true;
      nextSession.frozenIn = anchor.in;
      nextSession.frozenOut = anchor.out;
    }
    if (session.isClosing) {
      // Closing with Alt: freeze anchor 0's existing outgoing handle, adjust only incoming handle
      return {
        anchor: {
          ...anchor,
          in: [anchor.point[0] - dx, anchor.point[1] - dy],
          out: nextSession.frozenOut,
          smooth: false,
        },
        session: nextSession,
      };
    }
    // Normal anchor with Alt: freeze incoming handle, pivot outgoing handle independently
    return {
      anchor: {
        ...anchor,
        in: nextSession.frozenIn,
        out: [anchor.point[0] + dx, anchor.point[1] + dy],
        smooth: false,
      },
      session: nextSession,
    };
  }

  nextSession.altLocked = false;
  return {
    anchor: {
      ...anchor,
      in: [anchor.point[0] - dx, anchor.point[1] - dy],
      out: [anchor.point[0] + dx, anchor.point[1] + dy],
      smooth: true,
    },
    session: nextSession,
  };
}
