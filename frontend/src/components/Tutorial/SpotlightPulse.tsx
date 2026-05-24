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

function readAnchor(selector: string): Anchor | null {
  const el = document.querySelector(selector);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
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
