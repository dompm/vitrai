import { useState, useEffect, useRef } from 'react';

interface Dims { w: number; h: number; }

/**
 * Manages zoom, pan, and container measurement for a Konva panel.
 *
 * Wheel behavior (Figma/Illustrator style):
 *   - ctrlKey (pinch on trackpad): zoom centered on cursor
 *   - plain scroll: pan
 */
export function useViewport(imageW: number, imageH: number) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState<Dims>({ w: 800, h: 600 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const initializedRef = useRef(false);

  // Mutable refs so the native wheel handler (added once) always sees current values
  const zoomRef = useRef(zoom);
  const panRef = useRef(pan);
  const dimsRef = useRef(dims);
  const imageWRef = useRef(imageW);
  const imageHRef = useRef(imageH);

  zoomRef.current = zoom;
  panRef.current = pan;
  dimsRef.current = dims;
  imageWRef.current = imageW;
  imageHRef.current = imageH;

  // Container measurement
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      setDims({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Derived values
  const displayScale =
    imageW > 0 && imageH > 0 ? Math.min(dims.w / imageW, dims.h / imageH) : 1;
  const displayScaleRef = useRef(displayScale);
  displayScaleRef.current = displayScale;

  const effectiveScale = displayScale * zoom;

  // Center pan once per image change (or on first valid dims)
  useEffect(() => {
    initializedRef.current = false;
  }, [imageW, imageH]);

  useEffect(() => {
    if (initializedRef.current || imageW <= 0 || dims.w <= 0) return;
    initializedRef.current = true;
    const scale = Math.min(dims.w / imageW, dims.h / imageH);
    setZoom(1);
    setPan({
      x: (dims.w - imageW * scale) / 2,
      y: (dims.h - imageH * scale) / 2,
    });
  }, [imageW, imageH, dims.w, dims.h]);

  // Native (non-passive) wheel handler — added once, uses refs
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const iw = imageWRef.current;
      const ih = imageHRef.current;
      const d = dimsRef.current;
      const ds = iw > 0 && ih > 0 ? Math.min(d.w / iw, d.h / ih) : 1;

      if (e.ctrlKey) {
        // Pinch / Ctrl+scroll → zoom centred on cursor
        const rect = el.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        // Normalise deltaY to pixel-equivalent units so speed is consistent
        // across deltaMode=0 (pixels), 1 (lines), 2 (pages) and device settings.
        const raw = e.deltaY * (e.deltaMode === 1 ? 20 : e.deltaMode === 2 ? 400 : 1);
        // ~40 % zoom change per 100 normalised units — matches Figma / Miro feel.
        const factor = Math.pow(0.996, raw);

        const prev = zoomRef.current;
        const prevPan = panRef.current;
        const newZoom = Math.max(0.1, Math.min(20, prev * factor));
        const oldEff = ds * prev;
        const newEff = ds * newZoom;
        setZoom(newZoom);
        setPan({
          x: mx - (mx - prevPan.x) * newEff / oldEff,
          y: my - (my - prevPan.y) * newEff / oldEff,
        });
      } else {
        // Two-finger scroll → pan
        setPan(p => ({ x: p.x - e.deltaX, y: p.y - e.deltaY }));
      }
    };
    el.addEventListener('wheel', handler, { passive: false });
    return () => el.removeEventListener('wheel', handler);
  }, []); // runs once; state accessed via refs

  // Pan via pointer drag — call these from Stage event handlers
  const isPanning = useRef(false);
  const lastPanPtr = useRef<{ x: number; y: number } | null>(null);

  function startPan(pos: { x: number; y: number }) {
    isPanning.current = true;
    lastPanPtr.current = pos;
  }

  function movePan(pos: { x: number; y: number }) {
    if (!isPanning.current || !lastPanPtr.current) return;
    const dx = pos.x - lastPanPtr.current.x;
    const dy = pos.y - lastPanPtr.current.y;
    lastPanPtr.current = pos;
    setPan(p => ({ x: p.x + dx, y: p.y + dy }));
  }

  function endPan() {
    isPanning.current = false;
    lastPanPtr.current = null;
  }

  return {
    containerRef,
    dims,
    displayScale,
    effectiveScale,
    zoom,
    pan,
    zoomRef,
    panRef,
    displayScaleRef,
    startPan,
    movePan,
    endPan,
  };
}
