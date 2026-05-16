import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

interface Anchor {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Props {
  /** CSS selector for the element to point at. If null, the card renders centered. */
  target: string | null;
  /** Preferred placement; the card flips to the opposite side if it would overflow. */
  side?: 'top' | 'bottom' | 'left' | 'right';
  /** Step number for the progress dots ('1/6' etc.); pass null to hide. */
  progress?: { current: number; total: number } | null;
  /** Header label above the title. */
  eyebrow?: string;
  /** Big serif title. */
  title: string;
  /** Body paragraph. */
  body: string;
  /** Primary CTA (e.g. "Got it" on the final step). When omitted, the user is expected to perform the real action. */
  primary?: { label: string; onClick: () => void };
  /** Always-visible skip-tour link. */
  onSkip: () => void;
}

const CARD_WIDTH = 320;
const GAP = 14;

/** Returns the closest visible bounding rect for the selector, or null. */
function readAnchor(selector: string): Anchor | null {
  const el = document.querySelector(selector);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
}

export function CoachMark({
  target, side = 'right', progress, eyebrow, title, body, primary, onSkip,
}: Props) {
  const [anchor, setAnchor] = useState<Anchor | null>(target ? readAnchor(target) : null);
  const cardRef = useRef<HTMLDivElement>(null);

  // Track the target's position. ResizeObserver covers layout shifts; rAF covers
  // pan/zoom changes on Konva canvases (which don't fire DOM events).
  useEffect(() => {
    if (!target) { setAnchor(null); return; }
    let raf = 0;
    function tick() {
      setAnchor(prev => {
        const next = readAnchor(target!);
        if (!next) return prev;
        if (prev &&
            prev.x === next.x && prev.y === next.y &&
            prev.width === next.width && prev.height === next.height) return prev;
        return next;
      });
      raf = requestAnimationFrame(tick);
    }
    tick();
    return () => cancelAnimationFrame(raf);
  }, [target]);

  // Hoist focus into the card so keyboard users land here.
  useLayoutEffect(() => { cardRef.current?.focus(); }, [target]);

  // Centered fallback when there's no target.
  if (!anchor) {
    return (
      <div className="coach-mark coach-mark--centered" role="dialog" aria-modal="false">
        <div ref={cardRef} tabIndex={-1} className="coach-mark-card">
          <CoachContent
            progress={progress} eyebrow={eyebrow} title={title} body={body}
            primary={primary} onSkip={onSkip}
          />
        </div>
      </div>
    );
  }

  const vw = window.innerWidth;
  const vh = window.innerHeight;

  // Compute placement, flipping if the preferred side would overflow.
  let placement = side;
  if (placement === 'right' && anchor.x + anchor.width + GAP + CARD_WIDTH > vw - 16) placement = 'left';
  if (placement === 'left' && anchor.x - GAP - CARD_WIDTH < 16) placement = 'right';
  if (placement === 'top' && anchor.y - GAP < 16) placement = 'bottom';
  if (placement === 'bottom' && anchor.y + anchor.height + GAP > vh - 200) placement = 'top';

  let left = 0, top = 0;
  switch (placement) {
    case 'right':
      left = anchor.x + anchor.width + GAP;
      top = Math.max(16, anchor.y + anchor.height / 2 - 80);
      break;
    case 'left':
      left = anchor.x - GAP - CARD_WIDTH;
      top = Math.max(16, anchor.y + anchor.height / 2 - 80);
      break;
    case 'top':
      left = Math.max(16, Math.min(vw - CARD_WIDTH - 16, anchor.x + anchor.width / 2 - CARD_WIDTH / 2));
      top = anchor.y - GAP;
      break;
    case 'bottom':
      left = Math.max(16, Math.min(vw - CARD_WIDTH - 16, anchor.x + anchor.width / 2 - CARD_WIDTH / 2));
      top = anchor.y + anchor.height + GAP;
      break;
  }

  // Translate top-anchored cards up by their own height.
  const transform = placement === 'top' ? 'translateY(-100%)' : '';

  return (
    <div className="coach-mark" role="dialog" aria-modal="false">
      <CoachHighlight anchor={anchor} />
      <div
        ref={cardRef}
        tabIndex={-1}
        className={`coach-mark-card coach-mark-card--${placement}`}
        style={{ left, top, transform, width: CARD_WIDTH }}
      >
        <CoachContent
          progress={progress} eyebrow={eyebrow} title={title} body={body}
          primary={primary} onSkip={onSkip}
        />
      </div>
    </div>
  );
}

function CoachHighlight({ anchor }: { anchor: Anchor }) {
  return (
    <>
      {/* Translucent ring around the target. */}
      <div
        className="coach-mark-ring"
        style={{
          left: anchor.x - 4,
          top: anchor.y - 4,
          width: anchor.width + 8,
          height: anchor.height + 8,
        }}
        aria-hidden="true"
      />
    </>
  );
}

function CoachContent({
  progress, eyebrow, title, body, primary, onSkip,
}: Pick<Props, 'progress' | 'eyebrow' | 'title' | 'body' | 'primary' | 'onSkip'>) {
  return (
    <>
      {progress && (
        <div className="coach-mark-progress" aria-label={`Step ${progress.current} of ${progress.total}`}>
          {Array.from({ length: progress.total }).map((_, i) => (
            <span
              key={i}
              className={`coach-mark-progress-dot${i < progress.current ? ' is-active' : ''}`}
            />
          ))}
        </div>
      )}
      {eyebrow && <div className="coach-mark-eyebrow">{eyebrow}</div>}
      <h3 className="coach-mark-title">{title}</h3>
      <p className="coach-mark-body">{body}</p>
      <div className="coach-mark-actions">
        {primary && (
          <button className="btn-primary" onClick={primary.onClick}>
            {primary.label}
          </button>
        )}
        <button className="coach-mark-skip" onClick={onSkip}>
          Skip tour
        </button>
      </div>
    </>
  );
}
