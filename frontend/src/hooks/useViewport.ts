import { useState, useEffect, useRef } from 'react';

interface Dims { w: number; h: number; }

const MIN_EFFECTIVE_SCALE = 0.01; // 1%
const MAX_EFFECTIVE_SCALE = 32; // 3200%

function clampZoom(value: number, displayScale: number) {
  const safeDisplayScale = Math.max(displayScale, Number.EPSILON);
  return Math.max(
    MIN_EFFECTIVE_SCALE / safeDisplayScale,
    Math.min(MAX_EFFECTIVE_SCALE / safeDisplayScale, value),
  );
}

/**
 * Manages zoom, pan, and container measurement for a Konva panel.
 *
 * Wheel behavior (Figma/Illustrator style):
 *   - ctrlKey (pinch on trackpad): zoom centered on cursor
 *   - plain scroll: pan
 *
 * Touch behavior:
 *   - 1 finger: pan (delegated to Stage pointer handlers via startPan/movePan)
 *   - 2 fingers: pinch-to-zoom centered on midpoint, with simultaneous pan
 */
export function useViewport(imageW: number, imageH: number) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState<Dims>({ w: 800, h: 600 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const initializedRef = useRef(false);

  // Mutable refs so native handlers (added once) always see current values
  const zoomRef = useRef(zoom);
  const panRef = useRef(pan);
  const dimsRef = useRef(dims);
  const imageWRef = useRef(imageW);
  const imageHRef = useRef(imageH);

  const isPanning = useRef(false);
  // State mirror of isPanning: reading a mutated ref at render time left the
  // UI stale (cursor stuck on "grabbing", piece popover stuck pointer-events:
  // none) because endPan() never triggered a re-render.
  const [isPanningState, setIsPanningState] = useState(false);
  const lastPanPtr = useRef<{ x: number; y: number } | null>(null);
  const isPinchingRef = useRef(false);

  zoomRef.current = zoom;
  panRef.current = pan;
  dimsRef.current = dims;
  imageWRef.current = imageW;
  imageHRef.current = imageH;

  function currentDisplayScale() {
    const d = dimsRef.current;
    const iw = imageWRef.current;
    const ih = imageHRef.current;
    return iw > 0 && ih > 0 ? Math.min(d.w / iw, d.h / ih) : 1;
  }

  /** Set zoom while keeping the image point under `anchor` stationary. */
  function setZoomAround(nextZoom: number, anchor?: { x: number; y: number }) {
    const d = dimsRef.current;
    const point = anchor ?? { x: d.w / 2, y: d.h / 2 };
    const ds = currentDisplayScale();
    const previousZoom = zoomRef.current;
    const previousPan = panRef.current;
    const clampedZoom = clampZoom(nextZoom, ds);
    const previousEffectiveScale = ds * previousZoom;
    const nextEffectiveScale = ds * clampedZoom;

    setZoom(clampedZoom);
    if (previousEffectiveScale <= 0) return;
    setPan({
      x: point.x - (point.x - previousPan.x) * nextEffectiveScale / previousEffectiveScale,
      y: point.y - (point.y - previousPan.y) * nextEffectiveScale / previousEffectiveScale,
    });
  }

  function zoomIn() {
    setZoomAround(zoomRef.current * 1.25);
  }

  function zoomOut() {
    setZoomAround(zoomRef.current / 1.25);
  }

  /** Fit the full image in the viewport. */
  function fitToView() {
    const d = dimsRef.current;
    const ds = currentDisplayScale();
    setZoom(1);
    setPan({
      x: (d.w - imageWRef.current * ds) / 2,
      y: (d.h - imageHRef.current * ds) / 2,
    });
  }

  /** Show one image pixel as one screen pixel (the conventional 100% view). */
  function zoomToActualSize() {
    const ds = currentDisplayScale();
    if (ds > 0) setZoomAround(1 / ds);
  }

  // Container measurement
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect;
      const previousDims = dimsRef.current;
      const iw = imageWRef.current;
      const ih = imageHRef.current;
      const previousDisplayScale = iw > 0 && ih > 0
        ? Math.min(previousDims.w / iw, previousDims.h / ih)
        : 1;
      const nextDisplayScale = iw > 0 && ih > 0 ? Math.min(width / iw, height / ih) : 1;
      const previousEffectiveScale = previousDisplayScale * zoomRef.current;
      const nextEffectiveScale = nextDisplayScale * zoomRef.current;
      const previousPan = panRef.current;

      // Preserve the image point at the viewport center when the panel resizes.
      if (initializedRef.current && previousEffectiveScale > 0) {
        const imageCenterX = (previousDims.w / 2 - previousPan.x) / previousEffectiveScale;
        const imageCenterY = (previousDims.h / 2 - previousPan.y) / previousEffectiveScale;
        setPan({
          x: width / 2 - imageCenterX * nextEffectiveScale,
          y: height / 2 - imageCenterY * nextEffectiveScale,
        });
      }
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
      if (e.ctrlKey) {
        const rect = el.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const raw = e.deltaY * (e.deltaMode === 1 ? 20 : e.deltaMode === 2 ? 400 : 1);
        const factor = Math.pow(0.996, raw);
        setZoomAround(zoomRef.current * factor, { x: mx, y: my });
      } else {
        setPan(p => ({ x: p.x - e.deltaX, y: p.y - e.deltaY }));
      }
    };
    el.addEventListener('wheel', handler, { passive: false });
    return () => el.removeEventListener('wheel', handler);
  }, []); // runs once; state accessed via refs

  // Pinch-to-zoom — native touch handler so we can preventDefault
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let lastDist = 0;
    let lastMidX = 0;
    let lastMidY = 0;

    function pinchDist(t: TouchList) {
      return Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
    }

    function pinchMid(t: TouchList, rect: DOMRect) {
      return {
        x: (t[0].clientX + t[1].clientX) / 2 - rect.left,
        y: (t[0].clientY + t[1].clientY) / 2 - rect.top,
      };
    }

    function onTouchStart(e: TouchEvent) {
      if (e.touches.length !== 2) return;
      e.preventDefault();
      isPinchingRef.current = true;
      // Cancel any active single-finger pan
      isPanning.current = false;
      setIsPanningState(false);
      lastPanPtr.current = null;
      const rect = el!.getBoundingClientRect();
      lastDist = pinchDist(e.touches);
      const m = pinchMid(e.touches, rect);
      lastMidX = m.x;
      lastMidY = m.y;
    }

    function onTouchMove(e: TouchEvent) {
      if (e.touches.length !== 2 || !isPinchingRef.current) return;
      e.preventDefault();
      const iw = imageWRef.current;
      const ih = imageHRef.current;
      const d = dimsRef.current;
      const ds = iw > 0 && ih > 0 ? Math.min(d.w / iw, d.h / ih) : 1;

      const newDist = pinchDist(e.touches);
      const rect = el!.getBoundingClientRect();
      const m = pinchMid(e.touches, rect);

      if (lastDist > 0) {
        const factor = newDist / lastDist;
        const prev = zoomRef.current;
        const prevPan = panRef.current;
        const newZoom = clampZoom(prev * factor, ds);
        const oldEff = ds * prev;
        const newEff = ds * newZoom;
        // Keep the image point that was under lastMid pinned to the new mid.
        // Simultaneously handles zoom and the translation of the midpoint.
        setZoom(newZoom);
        setPan({
          x: m.x - (lastMidX - prevPan.x) * newEff / oldEff,
          y: m.y - (lastMidY - prevPan.y) * newEff / oldEff,
        });
      }

      lastDist = newDist;
      lastMidX = m.x;
      lastMidY = m.y;
    }

    function onTouchEnd(e: TouchEvent) {
      if (e.touches.length < 2) {
        isPinchingRef.current = false;
        lastDist = 0;
      }
    }

    el.addEventListener('touchstart', onTouchStart, { passive: false });
    el.addEventListener('touchmove', onTouchMove, { passive: false });
    el.addEventListener('touchend', onTouchEnd, { passive: false });
    return () => {
      el.removeEventListener('touchstart', onTouchStart);
      el.removeEventListener('touchmove', onTouchMove);
      el.removeEventListener('touchend', onTouchEnd);
    };
  }, []); // runs once; state accessed via refs

  function startPan(pos: { x: number; y: number }) {
    if (isPinchingRef.current) return;
    isPanning.current = true;
    setIsPanningState(true);
    lastPanPtr.current = pos;
  }

  function movePan(pos: { x: number; y: number }) {
    if (!isPanning.current || !lastPanPtr.current || isPinchingRef.current) return;
    const dx = pos.x - lastPanPtr.current.x;
    const dy = pos.y - lastPanPtr.current.y;
    lastPanPtr.current = pos;
    setPan(p => ({ x: p.x + dx, y: p.y + dy }));
  }

  function endPan() {
    isPanning.current = false;
    setIsPanningState(false);
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
    isPanning: isPanningState,
    startPan,
    movePan,
    endPan,
    setZoomAround,
    zoomIn,
    zoomOut,
    fitToView,
    zoomToActualSize,
  };
}
