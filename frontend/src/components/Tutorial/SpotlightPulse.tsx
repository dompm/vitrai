import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';

interface Anchor {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface SpotlightPulseProps {
  selector: string;
  withBackdrop?: boolean;
}

// A comma-separated selector is a priority list (popover control before its
// launcher), not document order. Ignore hidden responsive copies and clip the
// ring to the same scroll containers as the real control.
export function readAnchor(selector: string): Anchor | null {
  for (const candidate of selector.split(',')) {
    for (const el of document.querySelectorAll(candidate.trim())) {
      const rect = el.getBoundingClientRect();
      if (!rect.width || !rect.height || getComputedStyle(el).visibility === 'hidden') continue;
      let left = Math.max(0, rect.left), top = Math.max(0, rect.top);
      let right = Math.min(window.innerWidth, rect.right), bottom = Math.min(window.innerHeight, rect.bottom);
      for (let parent = el.parentElement; parent; parent = parent.parentElement) {
        const style = getComputedStyle(parent);
        const bounds = parent.getBoundingClientRect();
        if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) {
          left = Math.max(left, bounds.left); right = Math.min(right, bounds.right);
        }
        if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) {
          top = Math.max(top, bounds.top); bottom = Math.min(bottom, bounds.bottom);
        }
      }
      if (right > left && bottom > top) return { x: left, y: top, width: right - left, height: bottom - top };
    }
  }
  return null;
}

export function SpotlightPulse({ selector, withBackdrop = false }: SpotlightPulseProps) {
  const [anchor, setAnchor] = useState<Anchor | null>(null);

  useEffect(() => {
    let raf = 0;
    function tick() {
      const next = readAnchor(selector);
      if (next) {
        setAnchor(prev => {
          if (
            prev &&
            prev.x === next.x &&
            prev.y === next.y &&
            prev.width === next.width &&
            prev.height === next.height
          ) {
            return prev;
          }
          return next;
        });
      } else {
        setAnchor(null);
      }
      raf = requestAnimationFrame(tick);
    }
    tick();
    return () => cancelAnimationFrame(raf);
  }, [selector]);

  if (!anchor) return null;

  const commonRect = {
    left: anchor.x - 4,
    top: anchor.y - 4,
    width: anchor.width + 8,
    height: anchor.height + 8,
  };

  return createPortal(
    <>
      {withBackdrop && (
        <div
          className="tutorial-spotlight-backdrop"
          style={{
            position: 'fixed',
            ...commonRect,
            pointerEvents: 'none',
            zIndex: 1040,
            borderRadius: 8,
          }}
        />
      )}
      <div
        className="tutorial-spotlight-pulse"
        aria-hidden="true"
        data-tutorial-spotlight={selector}
        style={{
          position: 'fixed',
          ...commonRect,
          pointerEvents: 'none',
          zIndex: 2000,
          borderRadius: 8,
        }}
      />
    </>,
    document.body
  );
}
