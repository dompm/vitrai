import { memo, useState, useRef, useMemo, useEffect } from 'react';

const IS_TOUCH = typeof window !== 'undefined' && window.matchMedia('(pointer: coarse)').matches;
import { useTranslation } from 'react-i18next';
import { Stage, Layer, Image as KonvaImage, Line, Group, Circle, Rect } from 'react-konva';
import { CANVAS } from '../theme';
import useImage from 'use-image';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { Piece, GlassSheet, TextureTransform, Crop, Scale } from '../types';
import { computeCentroid, flattenCurves } from '../utils/geometry';
import { packPiecesSmart, defaultCuttingGapPx } from '../utils/packing';
import { toImageCoords, toScreenCoords } from '../utils/viewport';
import { Toolbar, SelectIcon, CropIcon, MeasureIcon, HandIcon } from './Toolbar';
import type { ToolId } from './Toolbar';
import { SelectAnimation, CropAnimation, MeasureAnimation, PanAnimation, PackAnimation } from './ToolTooltipAnimations';
import { ToolTooltip } from './ToolTooltip';
import { CropOverlay } from './CropOverlay';
import { MeasureInput } from './MeasureInput';
import { MeasureLineOverlay } from './MeasureLineOverlay';
import { useViewport } from '../hooks/useViewport';
import { useMeasure } from '../hooks/useMeasure';
import { ViewportControls } from './ViewportControls';
import { getPieceGeometry } from '../editor/geometry/pieceGeometry';
import { PieceTransformPreviewStore, usePieceTransformPreview } from '../editor/interaction/pieceTransformPreviewStore';
import { ViewportGroup, ViewportSubscriber, useViewportEffectiveScale, type ViewportStore } from '../editor/viewport/viewportStore';


// Display-pixel constants — independent of zoom or image resolution
const STROKE_IDLE = 2.5;
const STROKE_SELECTED = 3;
const HANDLE_RADIUS = 10;
const HANDLE_STEM = 1.5;
const HANDLE_BORDER = 2;
const HANDLE_GAP = 18; // extra gap beyond the bounding radius, in display px
const MOVE_SNAP_TOLERANCE_PX = 8;
const ROTATION_SNAP_RADIANS = Math.PI / 12; // 15°, matching common design tools

interface AxisAlignedBounds {
  left: number;
  right: number;
  top: number;
  bottom: number;
  centerX: number;
  centerY: number;
}

function getTransformedBounds(piece: Piece, x = piece.transform.x, y = piece.transform.y): AxisAlignedBounds {
  const displayPolygon = flattenCurves(piece.polygon, piece.curvePoints);
  const centroid = computeCentroid(displayPolygon);
  const { rotation, scale } = piece.transform;
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);
  const transformed = displayPolygon.map(([px, py]) => {
    const localX = (px - centroid.x) * scale;
    const localY = (py - centroid.y) * scale;
    return {
      x: x + localX * cos - localY * sin,
      y: y + localX * sin + localY * cos,
    };
  });
  const xs = transformed.map(point => point.x);
  const ys = transformed.map(point => point.y);
  const left = Math.min(...xs);
  const right = Math.max(...xs);
  const top = Math.min(...ys);
  const bottom = Math.max(...ys);
  return { left, right, top, bottom, centerX: (left + right) / 2, centerY: (top + bottom) / 2 };
}

interface SnapCandidate {
  delta: number;
  guide: number;
}

function nearestSnap(candidates: SnapCandidate[], tolerance: number) {
  let best: SnapCandidate | null = null;
  let distance = tolerance;
  for (const candidate of candidates) {
    const candidateDistance = Math.abs(candidate.delta);
    if (candidateDistance < distance) {
      best = candidate;
      distance = candidateDistance;
    }
  }
  return best;
}

function snapPiecePosition(
  piece: Piece,
  x: number,
  y: number,
  otherPieces: Piece[],
  sheetBounds: AxisAlignedBounds,
  tolerance: number,
) {
  const moving = getTransformedBounds(piece, x, y);
  const xCandidates = [
    { delta: sheetBounds.left - moving.left, guide: sheetBounds.left },
    { delta: sheetBounds.right - moving.right, guide: sheetBounds.right },
    { delta: sheetBounds.centerX - moving.centerX, guide: sheetBounds.centerX },
  ];
  const yCandidates = [
    { delta: sheetBounds.top - moving.top, guide: sheetBounds.top },
    { delta: sheetBounds.bottom - moving.bottom, guide: sheetBounds.bottom },
    { delta: sheetBounds.centerY - moving.centerY, guide: sheetBounds.centerY },
  ];

  for (const other of otherPieces) {
    if (other.id === piece.id) continue;
    const target = getTransformedBounds(other);
    xCandidates.push(
      { delta: target.left - moving.left, guide: target.left },
      { delta: target.right - moving.left, guide: target.right },
      { delta: target.left - moving.right, guide: target.left },
      { delta: target.right - moving.right, guide: target.right },
      { delta: target.centerX - moving.centerX, guide: target.centerX },
    );
    yCandidates.push(
      { delta: target.top - moving.top, guide: target.top },
      { delta: target.bottom - moving.top, guide: target.bottom },
      { delta: target.top - moving.bottom, guide: target.top },
      { delta: target.bottom - moving.bottom, guide: target.bottom },
      { delta: target.centerY - moving.centerY, guide: target.centerY },
    );
  }

  const xSnap = nearestSnap(xCandidates, tolerance);
  const ySnap = nearestSnap(yCandidates, tolerance);
  return {
    x: x + (xSnap?.delta ?? 0),
    y: y + (ySnap?.delta ?? 0),
    guideX: xSnap?.guide ?? null,
    guideY: ySnap?.guide ?? null,
  };
}

const transformsEqual = (a: TextureTransform, b: TextureTransform) =>
  a.x === b.x && a.y === b.y && a.rotation === b.rotation && a.scale === b.scale;

interface PieceOutlineProps {
  piece: Piece;
  isSelected: boolean;
  onSelect?: (multi?: boolean) => void;
  viewportStore: ViewportStore;
  previewStore: PieceTransformPreviewStore;
  onPreviewTransform?: (transform: TextureTransform, flush?: boolean) => void;
  onRotateStart?: (e: KonvaEventObject<PointerEvent>) => void;
  fillOnly?: boolean;
  strokeOnly?: boolean;
  handleOnly?: boolean;
  listening?: boolean;
  snapPieces?: Piece[];
  snapBounds?: AxisAlignedBounds;
  onSnapChange?: (guides: { x: number | null; y: number | null }) => void;
}

const PieceOutline = memo(function PieceOutline({
  piece, isSelected, viewportStore, onSelect, previewStore, onPreviewTransform, onRotateStart,
  fillOnly, strokeOnly, handleOnly, listening = true, snapPieces = [], snapBounds, onSnapChange,
}: PieceOutlineProps) {
  const effectiveScale = useViewportEffectiveScale(viewportStore);
  const renderedTransform = usePieceTransformPreview(previewStore, piece.id) ?? piece.transform;
  const { x, y, rotation, scale } = renderedTransform;
  const geometry = getPieceGeometry(piece.polygon, piece.curvePoints);
  const { centroid } = geometry;
  const relPts = useMemo(
    () => geometry.displayPolygon.flatMap(([px, py]) => [px - centroid.x, py - centroid.y]),
    [geometry, centroid],
  );

  // Combined divisor so sizes stay fixed in display pixels
  const es = effectiveScale * scale;

  // Bounding radius in display px, converted to local coords for the handle stem
  const radiusPx = geometry.localBoundingRadius * es;
  const handleOffset = (radiusPx + HANDLE_GAP + HANDLE_RADIUS) / es;

  // Prevent drag from starting when the pointer went down on the rotation handle
  const dragStartedFromHandle = useRef(false);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);

  function handleClick(e: KonvaEventObject<MouseEvent>) {
    e.cancelBubble = true;
    if (longPressFired.current) { longPressFired.current = false; return; }
    onSelect?.(e.evt.shiftKey);
  }

  function handlePointerDown() {
    if (!IS_TOUCH) return;
    longPressFired.current = false;
    longPressTimer.current = setTimeout(() => {
      longPressFired.current = true;
      longPressTimer.current = null;
      onSelect?.(true);
    }, 500);
  }

  function cancelLongPress() {
    if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null; }
  }

  function handleDragStart(e: KonvaEventObject<DragEvent>) {
    if (dragStartedFromHandle.current) {
      dragStartedFromHandle.current = false;
      e.target.stopDrag();
    }
  }

  function handleDragMove(e: KonvaEventObject<DragEvent>) {
    const bypassSnapping = e.evt.ctrlKey;
    const snapped = !bypassSnapping && snapBounds
      ? snapPiecePosition(
        piece,
        e.target.x(),
        e.target.y(),
        snapPieces,
        snapBounds,
        MOVE_SNAP_TOLERANCE_PX / effectiveScale,
      )
      : { x: e.target.x(), y: e.target.y(), guideX: null, guideY: null };
    const position = { x: snapped.x, y: snapped.y };
    e.target.position(position);
    onSnapChange?.({ x: snapped.guideX, y: snapped.guideY });
    const current = previewStore.get(piece.id) ?? renderedTransform;
    onPreviewTransform?.({ ...current, ...position });
  }

  function handleDragEnd(e: KonvaEventObject<DragEvent>) {
    onSnapChange?.({ x: null, y: null });
    const current = previewStore.get(piece.id) ?? renderedTransform;
    onPreviewTransform?.({ ...current, x: e.target.x(), y: e.target.y() }, true);
  }

  function handleRotateDown(e: KonvaEventObject<PointerEvent>) {
    e.cancelBubble = true;
    // Capture the pointer so the rotation keeps tracking (and properly
    // commits on pointerup) even if the pointer leaves the canvas.
    if (e.evt.pointerId !== undefined) e.target.getStage()?.content.setPointerCapture(e.evt.pointerId);
    dragStartedFromHandle.current = true;
    onRotateStart?.(e);
  }

  return (
    <Group
      x={x} y={y}
      rotation={(rotation * 180) / Math.PI}
      scaleX={scale} scaleY={scale}
      draggable={isSelected && strokeOnly && !handleOnly}
      onClick={handleOnly ? undefined : handleClick}
      onTap={handleOnly ? undefined : handleClick}
      onPointerDown={handleOnly ? undefined : handlePointerDown}
      onPointerMove={handleOnly ? undefined : cancelLongPress}
      onPointerUp={handleOnly ? undefined : cancelLongPress}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
      onDragEnd={handleDragEnd}
      listening={listening}
    >
      {!handleOnly && (
        <Line
          points={relPts}
          stroke={fillOnly ? 'transparent' : (isSelected ? CANVAS.amber : CANVAS.amberIdleStroke)}
          strokeWidth={isSelected ? STROKE_SELECTED / es : STROKE_IDLE / es}
          fill={strokeOnly ? 'transparent' : (isSelected ? CANVAS.amberSelectedFill : CANVAS.amberIdleFill)}
          closed
          hitStrokeWidth={strokeOnly ? 10 / es : 0}
        />
      )}
      {(handleOnly || (isSelected && strokeOnly && !fillOnly)) && (
        <>
          <Line
            points={[0, 0, 0, -handleOffset]}
            stroke={CANVAS.amberHandleStem} strokeWidth={HANDLE_STEM / es}
            listening={false}
          />
          <Circle
            x={0} y={-handleOffset}
            radius={HANDLE_RADIUS / es}
            fill={CANVAS.amberHandle} stroke={CANVAS.paper} strokeWidth={HANDLE_BORDER / es}
            onPointerDown={handleRotateDown}
          />
        </>
      )}
    </Group>
  );
});

const PackIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="1.5" />
    <rect x="5.5" y="5.5" width="6" height="6" rx="0.6" />
    <rect x="13" y="5.5" width="5.5" height="4" rx="0.6" />
    <rect x="5.5" y="13" width="4.5" height="5.5" rx="0.6" />
    <rect x="11.5" y="11" width="7" height="7.5" rx="0.6" />
  </svg>
);

interface SheetPanelProps {
  pieceTransformPreviewStore: PieceTransformPreviewStore;
  sheet: GlassSheet;
  pieces: Piece[];
  selectedPieceIds: string[];
  onSelectPiece: (id: string | null, multi?: boolean) => void;
  onTransformChange: (pieceId: string, t: Partial<TextureTransform>, skipHistory?: boolean) => void;
  onCommitTransforms: (updates: Array<{ pieceId: string; transform: TextureTransform }>) => void;
  onCropChange: (c: Partial<Crop>) => void;
  onScaleChange: (s: Scale | null) => void;
  onImageLoad?: (w: number, h: number) => void;
  activeTool: ToolId;
  onChangeActiveTool: (tool: ToolId) => void;
  showEmptyHint?: boolean;
  isTutorial?: boolean;
}

export function SheetPanel({
  pieceTransformPreviewStore, sheet, pieces, selectedPieceIds, onSelectPiece, onTransformChange, onCommitTransforms, onCropChange, onScaleChange, onImageLoad,
  showEmptyHint = false, activeTool, onChangeActiveTool, isTutorial = false,
}: SheetPanelProps) {
  const { t } = useTranslation();
  const selectedPieceIdSet = useMemo(() => new Set(selectedPieceIds), [selectedPieceIds]);
  // activeTool is now passed as a prop from the parent App component
  const [isSpaceDown, setIsSpaceDown] = useState(false);
  const [isPacking, setIsPacking] = useState(false);
  const [allowRotations, setAllowRotations] = useState(false);
  const [isPackPopoverOpen, setIsPackPopoverOpen] = useState(false);
  const packPopoverRef = useRef<HTMLDivElement>(null);
  const isPackPopoverOpenRef = useRef(isPackPopoverOpen);
  isPackPopoverOpenRef.current = isPackPopoverOpen;
  const panelRef = useRef<HTMLDivElement>(null);
  const panelHoveredRef = useRef(false);
  const capturedPointerRef = useRef<{ pointerId: number; target: Element } | null>(null);
  const rotationValueRef = useRef<number | null>(null);
  const groupMoveStartRef = useRef<{
    draggedId: string;
    transforms: Map<string, TextureTransform>;
  } | null>(null);
  const [sheetImg] = useImage(sheet.imageUrl);
  const sheetW = sheetImg?.width ?? 800;
  const sheetH = sheetImg?.height ?? 600;
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
      const panelHasFocus = panelRef.current?.contains(document.activeElement) ?? false;
      if (!panelHoveredRef.current && !panelHasFocus) return;
      const hasToolModifier = e.metaKey || e.ctrlKey || e.altKey;
      if (e.code === 'Space' && !e.repeat) {
        if (hasToolModifier) return;
        e.preventDefault();
        setIsSpaceDown(true);
        return;
      }
      const key = e.key.toLowerCase();
      if (!hasToolModifier && (key === '+' || key === '=')) {
        e.preventDefault();
        vp.zoomIn();
      } else if (!hasToolModifier && key === '-') {
        e.preventDefault();
        vp.zoomOut();
      } else if (!hasToolModifier && e.shiftKey && e.code === 'Digit1') {
        e.preventDefault();
        vp.fitToView();
      } else if (!hasToolModifier && e.shiftKey && e.code === 'Digit0') {
        e.preventDefault();
        vp.zoomToActualSize();
      } else if (!hasToolModifier && key === 'v') handleToolChange('select');
      else if (!hasToolModifier && key === 'h') handleToolChange('pan');
      else if (!hasToolModifier && key === 'c') handleToolChange('crop');
      else if (!hasToolModifier && key === 'm') handleToolChange('measure');
      else if (e.key === 'Escape') handleToolChange('select');
    }
    function handleKeyUp(e: KeyboardEvent) {
      if (e.code === 'Space') setIsSpaceDown(false);
    }
    function handleWindowBlur() {
      setIsSpaceDown(false);
    }
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('blur', handleWindowBlur);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('blur', handleWindowBlur);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTool]);

  useEffect(() => {
    if (!isPackPopoverOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (packPopoverRef.current && !packPopoverRef.current.contains(e.target as Node)) {
        setIsPackPopoverOpen(false);
      }
    }
    document.addEventListener('pointerdown', handleClickOutside);
    return () => document.removeEventListener('pointerdown', handleClickOutside);
  }, [isPackPopoverOpen]);

  useEffect(() => {
    if (sheetImg && onImageLoad) onImageLoad(sheetImg.width, sheetImg.height);
  }, [sheetImg]); // eslint-disable-line react-hooks/exhaustive-deps
  const vp = useViewport(sheetW, sheetH);
  const measure = useMeasure();
  const [marqueeBox, setMarqueeBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const marqueeJustEndedRef = useRef(false);
  const [moveSnapGuides, setMoveSnapGuides] = useState<{ x: number | null; y: number | null }>({ x: null, y: null });

  function handlePieceTransform(pieceId: string, transform: TextureTransform, flush = false) {
    const targetX = transform.x;
    const targetY = transform.y;
    const isGroupMove = selectedPieceIds.length > 1;
    if (!isGroupMove) {
      const update = { pieceId, transform };
      if (flush) {
        const committed = pieces.find(piece => piece.id === pieceId)?.transform;
        if (committed && transformsEqual(transform, committed)) {
          pieceTransformPreviewStore.clear(pieceId);
          return;
        }
        pieceTransformPreviewStore.flushMany([update]);
        onCommitTransforms([update]);
      } else {
        pieceTransformPreviewStore.scheduleMany([update]);
      }
      return;
    }
    if (!groupMoveStartRef.current) {
      groupMoveStartRef.current = {
        draggedId: pieceId,
        transforms: new Map(
          pieces
            .filter(piece => selectedPieceIds.includes(piece.id))
            .map(piece => [piece.id, { ...piece.transform }]),
        ),
      };
    }
    const gesture = groupMoveStartRef.current;
    const draggedStart = gesture.transforms.get(gesture.draggedId);
    if (!draggedStart) return;
    const dx = targetX - draggedStart.x;
    const dy = targetY - draggedStart.y;
    const updates = [...gesture.transforms.entries()].map(([id, start]) => ({
      pieceId: id,
      transform: { ...start, x: start.x + dx, y: start.y + dy },
    }));
    if (flush) {
      const committedTransforms = new Map(pieces.map(piece => [piece.id, piece.transform]));
      if (updates.every(update => {
        const committed = committedTransforms.get(update.pieceId);
        return committed != null && transformsEqual(update.transform, committed);
      })) {
        updates.forEach(update => pieceTransformPreviewStore.clear(update.pieceId));
        groupMoveStartRef.current = null;
        return;
      }
      pieceTransformPreviewStore.flushMany(updates);
      onCommitTransforms(updates);
      groupMoveStartRef.current = null;
    } else {
      pieceTransformPreviewStore.scheduleMany(updates);
    }
  }

  // When switching sheets, reload the ruler for the new sheet (if measure is active)
  useEffect(() => {
    measure.reset();
    if (activeTool === 'measure') {
      const saved = sheet.scale?.line;
      const cropL = sheet.crop.left;
      const cropT = sheet.crop.top;
      const cropR = sheetW - sheet.crop.right;
      const cropB = sheetH - sheet.crop.bottom;
      const defaultX1 = cropL + (cropR - cropL) * 0.25;
      const defaultX2 = cropL + (cropR - cropL) * 0.75;
      const defaultY = cropT + (cropB - cropT) * 0.5;
      const x1 = saved?.x1 ?? defaultX1;
      const y1 = saved?.y1 ?? defaultY;
      const x2 = saved?.x2 ?? defaultX2;
      const y2 = saved?.y2 ?? defaultY;
      measure.loadLine({ x1, y1, x2, y2 });
      if (!sheet.scale) {
        const px = Math.hypot(x2 - x1, y2 - y1);
        onScaleChange({ pxPerUnit: px / 6, unit: 'in', line: { x1, y1, x2, y2 } });
      }
    }
  }, [sheet.id, activeTool]); // eslint-disable-line react-hooks/exhaustive-deps

  const [rotatingPieceId, setRotatingPieceId] = useState<string | null>(null);
  const rotatingPiece = useMemo(
    () => pieces.find(p => p.id === rotatingPieceId) ?? null,
    [pieces, rotatingPieceId]
  );

  function isBackground(e: KonvaEventObject<PointerEvent | MouseEvent>) {
    return e.target.getType() === 'Stage' || (e.target as { attrs?: { id?: string } }).attrs?.id === 'bg';
  }

  function captureInteractionPointer(e: KonvaEventObject<PointerEvent>) {
    const target = e.evt.target;
    if (!(target instanceof Element) || !('setPointerCapture' in target)) return;
    try {
      (target as Element & { setPointerCapture: (pointerId: number) => void }).setPointerCapture(e.evt.pointerId);
      capturedPointerRef.current = { pointerId: e.evt.pointerId, target };
    } catch {
      // Pointer capture can fail if the browser has already ended the pointer.
    }
  }

  function releaseInteractionPointer() {
    const captured = capturedPointerRef.current;
    capturedPointerRef.current = null;
    if (!captured || !('releasePointerCapture' in captured.target)) return;
    try {
      (captured.target as Element & { releasePointerCapture: (pointerId: number) => void })
        .releasePointerCapture(captured.pointerId);
    } catch {
      // The browser may have released capture automatically.
    }
  }

  function beginRotation(piece: Piece, e: KonvaEventObject<PointerEvent>) {
    captureInteractionPointer(e);
    rotationValueRef.current = piece.transform.rotation;
    setRotatingPieceId(piece.id);
  }

  function handlePointerDown(e: KonvaEventObject<PointerEvent>) {
    const stage = e.target.getStage();
    const ptr = stage?.getPointerPosition();
    if (!ptr) return;
    // Capture the pointer so pan/marquee gestures still receive pointermove/
    // pointerup when the button is released outside the canvas; otherwise the
    // gesture sticks "on" until the next click.
    if (e.evt.pointerId !== undefined) stage?.content.setPointerCapture(e.evt.pointerId);
    const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);

    const isMiddleClick = e.evt && (e.evt as MouseEvent).button === 1;
    if (isMiddleClick || activeTool === 'pan' || isSpaceDown) {
      captureInteractionPointer(e);
      vp.startPan(ptr);
      return;
    }

    if (activeTool === 'select' && isBackground(e)) {
      if (!IS_TOUCH) {
        captureInteractionPointer(e);
        setMarqueeBox({ x1: x, y1: y, x2: x, y2: y });
      } else {
        captureInteractionPointer(e);
        vp.startPan(ptr);
      }
      return;
    }

    if (!isBackground(e)) return;
    captureInteractionPointer(e);
    vp.startPan(ptr);
  }

  function handlePointerMove(e: KonvaEventObject<PointerEvent>) {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;
    const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);

    if (marqueeBox) {
      setMarqueeBox(b => b ? { ...b, x2: x, y2: y } : null);
      return;
    }

    if (rotatingPiece) {
      const renderedTransform = pieceTransformPreviewStore.get(rotatingPiece.id) ?? rotatingPiece.transform;
      let newRotation =
        Math.atan2(y - renderedTransform.y, x - renderedTransform.x) + Math.PI / 2;
      if (e.evt.shiftKey) {
        newRotation = Math.round(newRotation / ROTATION_SNAP_RADIANS) * ROTATION_SNAP_RADIANS;
      }
      rotationValueRef.current = newRotation;
      pieceTransformPreviewStore.schedule(rotatingPiece.id, { ...renderedTransform, rotation: newRotation });
      return;
    }

    vp.movePan(ptr);
  }

  function handlePointerUp() {
    releaseInteractionPointer();
    setMoveSnapGuides({ x: null, y: null });
    if (marqueeBox) {
      const xmin = Math.min(marqueeBox.x1, marqueeBox.x2);
      const xmax = Math.max(marqueeBox.x1, marqueeBox.x2);
      const ymin = Math.min(marqueeBox.y1, marqueeBox.y2);
      const ymax = Math.max(marqueeBox.y1, marqueeBox.y2);

      const containsMode = marqueeBox.x2 >= marqueeBox.x1;
      const hitIds = pieces.filter(piece => {
        const bounds = getTransformedBounds(piece);
        return containsMode
          ? bounds.left >= xmin && bounds.right <= xmax && bounds.top >= ymin && bounds.bottom <= ymax
          : bounds.right >= xmin && bounds.left <= xmax && bounds.bottom >= ymin && bounds.top <= ymax;
      }).map(piece => piece.id);

      if (hitIds.length > 0) {
        hitIds.forEach((id, idx) => onSelectPiece(id, idx > 0));
      } else if (Math.abs(marqueeBox.x2 - marqueeBox.x1) < 2 && Math.abs(marqueeBox.y2 - marqueeBox.y1) < 2) {
        onSelectPiece(null);
      }
      // Konva synthesizes a `click` after this pointerup (it has no movement
      // threshold); suppress it so it can't clear the selection we just made.
      marqueeJustEndedRef.current = true;
      setTimeout(() => { marqueeJustEndedRef.current = false; }, 0);
      setMarqueeBox(null);
      return;
    }

    if (rotatingPiece) {
      const finalTransform = pieceTransformPreviewStore.get(rotatingPieceId!) ?? rotatingPiece.transform;
      if (transformsEqual(finalTransform, rotatingPiece.transform)) {
        pieceTransformPreviewStore.clear(rotatingPieceId!);
      } else {
        pieceTransformPreviewStore.flush(rotatingPieceId!, finalTransform);
        onCommitTransforms([{ pieceId: rotatingPieceId!, transform: finalTransform }]);
      }
    }
    rotationValueRef.current = null;
    setRotatingPieceId(null);
    vp.endPan();
  }

  function handlePointerCancel() {
    // A canceled rotation keeps the last visible angle and finalizes one history entry.
    if (rotatingPieceId && rotationValueRef.current != null) {
      const piece = pieces.find(candidate => candidate.id === rotatingPieceId);
      if (piece) {
        const finalTransform = pieceTransformPreviewStore.get(rotatingPieceId) ?? {
          ...piece.transform,
          rotation: rotationValueRef.current,
        };
        if (transformsEqual(finalTransform, piece.transform)) {
          pieceTransformPreviewStore.clear(rotatingPieceId);
        } else {
          pieceTransformPreviewStore.flush(rotatingPieceId, finalTransform);
          onCommitTransforms([{ pieceId: rotatingPieceId, transform: finalTransform }]);
        }
      }
    }
    setMarqueeBox(null);
    setMoveSnapGuides({ x: null, y: null });
    rotationValueRef.current = null;
    setRotatingPieceId(null);
    vp.endPan();
    releaseInteractionPointer();
  }

  function handleStageClick(e: KonvaEventObject<MouseEvent>) {
    if (marqueeJustEndedRef.current) return;
    if (!rotatingPieceId && activeTool === 'select' && isBackground(e)) onSelectPiece(null);
  }

  function handleMeasureConfirm(realLength: number, unit: Scale['unit']) {
    if (!measure.line) return;
    const px = Math.hypot(measure.line.x2 - measure.line.x1, measure.line.y2 - measure.line.y1);
    onScaleChange({ pxPerUnit: px / realLength, unit, line: { ...measure.line } });
  }

  function handleMeasureDragEnd(nx1: number, ny1: number, nx2: number, ny2: number) {
    const existing = sheet.scale;
    const newPxLen = Math.hypot(nx2 - nx1, ny2 - ny1);
    if (existing) {
      const oldPxLen = Math.hypot(existing.line.x2 - existing.line.x1, existing.line.y2 - existing.line.y1);
      const newPxPerUnit = oldPxLen > 0 ? newPxLen * existing.pxPerUnit / oldPxLen : existing.pxPerUnit;
      onScaleChange({ pxPerUnit: newPxPerUnit, unit: existing.unit, line: { x1: nx1, y1: ny1, x2: nx2, y2: ny2 } });
    } else {
      onScaleChange({ pxPerUnit: newPxLen / 6, unit: 'in', line: { x1: nx1, y1: ny1, x2: nx2, y2: ny2 } });
    }
  }

  function handleToolChange(id: ToolId) {
    if (id === activeTool && id !== 'select') {
      onChangeActiveTool('select');
      if (id === 'measure') measure.reset();
      return;
    }

    if (activeTool === 'measure' && id !== 'measure') measure.reset();
    if (id === 'measure') {
      const saved = sheet.scale?.line;
      const cropL = sheet.crop.left;
      const cropT = sheet.crop.top;
      const cropR = sheetW - sheet.crop.right;
      const cropB = sheetH - sheet.crop.bottom;

      const defaultX1 = isTutorial ? 764.712 : cropL + (cropR - cropL) * 0.25;
      const defaultX2 = isTutorial ? 2058.347 : cropL + (cropR - cropL) * 0.75;
      const defaultY = isTutorial ? 768 : cropT + (cropB - cropT) * 0.5;

      let x1 = saved?.x1 ?? defaultX1;
      let y1 = saved?.y1 ?? defaultY;
      let x2 = saved?.x2 ?? defaultX2;
      let y2 = saved?.y2 ?? defaultY;

      x1 = Math.max(0, Math.min(sheetW, x1));
      y1 = Math.max(0, Math.min(sheetH, y1));
      x2 = Math.max(0, Math.min(sheetW, x2));
      y2 = Math.max(0, Math.min(sheetH, y2));

      measure.loadLine({ x1, y1, x2, y2 });
      if (!sheet.scale) {
        const px = Math.hypot(x2 - x1, y2 - y1);
        onScaleChange({ pxPerUnit: px / 6, unit: 'in', line: { x1, y1, x2, y2 } });
      }
    }
    onChangeActiveTool(id);
  }

  function setCursor(cursor: string) {
    if (vp.containerRef.current) vp.containerRef.current.style.cursor = cursor;
  }

  const measurePxLength = measure.line
    ? Math.hypot(measure.line.x2 - measure.line.x1, measure.line.y2 - measure.line.y1)
    : 0;
  const isPanActive = activeTool === 'pan' || isSpaceDown;
  const containerCursor = rotatingPieceId ? 'grabbing' : isPanActive ? (vp.isPanning ? 'grabbing' : 'grab') : 'default';
  const sheetSnapBounds: AxisAlignedBounds = {
    left: sheet.crop.left,
    right: sheetW - sheet.crop.right,
    top: sheet.crop.top,
    bottom: sheetH - sheet.crop.bottom,
    centerX: (sheet.crop.left + sheetW - sheet.crop.right) / 2,
    centerY: (sheet.crop.top + sheetH - sheet.crop.bottom) / 2,
  };

  const TOOLS = useMemo(() => [
    {
      id: 'select' as ToolId,
      label: t('toolSelect'),
      icon: <SelectIcon />,
      tooltip: {
        name: t('tooltipSelectName'),
        shortcut: 'V',
        description: t('tooltipSelectDescSheet'),
        animation: <SelectAnimation />,
      },
    },
    {
      id: 'pan' as ToolId,
      label: t('toolPan'),
      icon: <HandIcon />,
      tooltip: {
        name: t('tooltipPanName'),
        shortcut: 'H, Space',
        description: t('tooltipPanDesc'),
        animation: <PanAnimation />,
      },
    },
    {
      id: 'crop' as ToolId,
      label: t('toolCropSheet'),
      icon: <CropIcon />,
      tooltip: {
        name: t('tooltipCropSheetName'),
        shortcut: 'C',
        description: t('tooltipCropSheetDesc'),
        animation: <CropAnimation />,
      },
    },
    {
      id: 'measure' as ToolId,
      label: t('toolScaleSheet'),
      icon: <MeasureIcon />,
      tooltip: {
        name: t('tooltipScaleName'), // Using the same "Set Scale" or "Measure" key
        shortcut: 'M',
        description: t('tooltipScaleDescSheet'),
        animation: <MeasureAnimation />,
      },
    },
  ].filter(tool => !IS_TOUCH || tool.id !== 'pan'), [t]);

  async function handleSmartPack() {
    if (pieces.length === 0 || isPacking) return;
    setIsPackPopoverOpen(false);
    setIsPacking(true);
    // Clear selection so handles don't follow jumping pieces
    onSelectPiece(null);

    const gapPx = defaultCuttingGapPx(sheet);
    try {
      // Record exactly one history entry (the pre-pack snapshot) on the first
      // placement so a single Cmd+Z reverts the whole pack; the remaining
      // streamed placements skip history.
      let historyRecorded = false;
      const skippedPieceIds = await packPiecesSmart(pieces, sheet, gapPx, allowRotations, (placement) => {
        onTransformChange(placement.pieceId, { x: placement.x, y: placement.y, rotation: placement.rotation }, historyRecorded);
        historyRecorded = true;
      });
      // Pieces too big for the sheet stay where they were — the packer just
      // leaves them out, so tell the user rather than silently dropping them.
      if (skippedPieceIds.length > 0) {
        alert(t('smartPackSkipped', { count: skippedPieceIds.length }));
      }
    } catch (err) {
      console.error('[SheetPanel] smart pack failed', err);
    } finally {
      setIsPacking(false);
    }
  }

  const packDisabled = pieces.length === 0 || isPacking;

  return (
    <div
      ref={panelRef}
      className="result-panel-inner"
      data-tutorial-panel="glass"
      tabIndex={-1}
      style={{ display: 'flex', flex: 1, minHeight: 0 }}
      onPointerEnter={() => { panelHoveredRef.current = true; }}
      onPointerLeave={() => { panelHoveredRef.current = false; }}
      onPointerDownCapture={() => panelRef.current?.focus({ preventScroll: true })}
    >
      <Toolbar tools={TOOLS} activeTool={activeTool} onSelectTool={handleToolChange}>
        <div className="toolbar-divider" />
        <div className="tooltip-wrapper" ref={packPopoverRef}>
          <button
            type="button"
            className={`tool-btn ${isPackPopoverOpen ? 'active' : ''}`}
            onClick={() => setIsPackPopoverOpen(o => !o)}
            disabled={packDisabled && !isPacking}
            aria-label={t('toolPack')}
          >
            {isPacking ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ animation: 'spin 1s linear infinite' }}>
                <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
              </svg>
            ) : <PackIcon />}
            <span className="tool-label">{isPacking ? t('packing', 'Packing...') : t('toolPack')}</span>
          </button>
          
          {!isPackPopoverOpen && (
            <ToolTooltip
              name={t('tooltipPackName')}
              shortcut=""
              description={t('tooltipPackDesc')}
              animation={<PackAnimation />}
            />
          )}
          
          {isPackPopoverOpen && (
            <div className="solder-popover">
              <div className="solder-popover-section">
                <span className="solder-popover-title" style={{ marginBottom: '12px', display: 'block' }}>{t('smartPack', 'Smart Pack')}</span>
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', color: 'var(--text-soft)', cursor: 'pointer', userSelect: 'none', padding: '4px 0', marginBottom: '16px' }}>
                  <input 
                    type="checkbox" 
                    checked={allowRotations} 
                    onChange={e => setAllowRotations(e.target.checked)} 
                    disabled={isPacking}
                    style={{ accentColor: CANVAS.amber, width: '16px', height: '16px' }}
                  />
                  {t('allowRotations', 'Allow Rotations')}
                </label>
                <button
                  type="button"
                  onClick={handleSmartPack}
                  disabled={isPacking || pieces.length === 0}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    background: CANVAS.amber,
                    color: CANVAS.paper,
                    border: 'none',
                    borderRadius: '6px',
                    fontWeight: 600,
                    cursor: (isPacking || pieces.length === 0) ? 'not-allowed' : 'pointer',
                    opacity: (isPacking || pieces.length === 0) ? 0.5 : 1
                  }}
                >
                  {t('startPacking', 'Start Packing')}
                </button>
              </div>
            </div>
          )}
        </div>
      </Toolbar>
      <div
        ref={vp.containerRef}
        className="canvas-well"
        style={{ flex: 1, overflow: 'hidden', cursor: containerCursor, position: 'relative', touchAction: 'none' }}
      >
        <Stage
          width={vp.dims.w} height={vp.dims.h}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerCancel}
          onClick={handleStageClick}
        >
          <Layer listening={false}>
            <ViewportGroup store={vp.store}>
              <Group
                {...(activeTool === 'crop' ? {} : {
                  clipX: sheet.crop.left,
                  clipY: sheet.crop.top,
                  clipWidth: Math.max(1, sheetW - sheet.crop.left - sheet.crop.right),
                  clipHeight: Math.max(1, sheetH - sheet.crop.top - sheet.crop.bottom),
                })}
              >
                {sheetImg && (
                  <KonvaImage id="bg" image={sheetImg} width={sheetW} height={sheetH} listening={false} />
                )}
              </Group>
            </ViewportGroup>
          </Layer>
          <Layer listening={false}>
            <ViewportGroup store={vp.store}>
              <Group
                {...(activeTool === 'crop' ? {} : {
                  clipX: sheet.crop.left,
                  clipY: sheet.crop.top,
                  clipWidth: Math.max(1, sheetW - sheet.crop.left - sheet.crop.right),
                  clipHeight: Math.max(1, sheetH - sheet.crop.top - sheet.crop.bottom),
                })}
              >
                {pieces.map(piece => (
                  <PieceOutline
                    key={piece.id + '-fill'}
                    piece={piece}
                    isSelected={selectedPieceIdSet.has(piece.id)}
                    viewportStore={vp.store}
                    previewStore={pieceTransformPreviewStore}
                    fillOnly
                    listening={false}
                  />
                ))}
              </Group>
            </ViewportGroup>
          </Layer>
          <Layer>
            <ViewportGroup store={vp.store}>
              {pieces.map(piece => (
                <PieceOutline
                  key={piece.id + '-stroke'}
                  piece={piece}
                  isSelected={selectedPieceIdSet.has(piece.id)}
                  viewportStore={vp.store}
                  previewStore={pieceTransformPreviewStore}
                  strokeOnly
                  onSelect={(multi) => onSelectPiece(piece.id, multi)}
                  onPreviewTransform={(transform, flush) => handlePieceTransform(piece.id, transform, flush)}
                  snapPieces={pieces}
                  snapBounds={sheetSnapBounds}
                  onSnapChange={setMoveSnapGuides}
                />
              ))}

              {pieces.map(piece => {
                if (!selectedPieceIdSet.has(piece.id)) return null;
                return (
                  <PieceOutline
                    key={piece.id + '-handle'}
                    piece={piece}
                    isSelected={true}
                    viewportStore={vp.store}
                    previewStore={pieceTransformPreviewStore}
                    handleOnly
                    onRotateStart={(e) => beginRotation(piece, e)}
                  />
                );
              })}
            </ViewportGroup>
            <ViewportSubscriber store={vp.store}>{(viewport) => { const es = viewport.effectiveScale; return <ViewportGroup store={vp.store}>
              {moveSnapGuides.x != null && (
                <Line
                  points={[moveSnapGuides.x, sheetSnapBounds.top, moveSnapGuides.x, sheetSnapBounds.bottom]}
                  stroke={CANVAS.amber}
                  strokeWidth={1 / es}
                  dash={[5 / es, 4 / es]}
                  listening={false}
                />
              )}
              {moveSnapGuides.y != null && (
                <Line
                  points={[sheetSnapBounds.left, moveSnapGuides.y, sheetSnapBounds.right, moveSnapGuides.y]}
                  stroke={CANVAS.amber}
                  strokeWidth={1 / es}
                  dash={[5 / es, 4 / es]}
                  listening={false}
                />
              )}
              {activeTool === 'crop' && (
                <CropOverlay
                  imageWidth={sheetW} imageHeight={sheetH}
                  crop={sheet.crop}
                  effectiveScale={es}
                  onCropChange={onCropChange}
                />
              )}
              {activeTool === 'measure' && measure.line && (
                <MeasureLineOverlay
                  line={measure.line}
                  effectiveScale={es}
                  imageWidth={sheetW} imageHeight={sheetH}
                  onUpdateP1={measure.updateP1}
                  onUpdateP2={measure.updateP2}
                  onCursorChange={setCursor}
                  onDragEnd={handleMeasureDragEnd}
                />
              )}
            </ViewportGroup>; }}</ViewportSubscriber>
            <ViewportSubscriber store={vp.store}>{(viewport) => { const es = viewport.effectiveScale; return <>
            {marqueeBox && (
              <Rect
                x={Math.min(marqueeBox.x1, marqueeBox.x2) * es + viewport.pan.x}
                y={Math.min(marqueeBox.y1, marqueeBox.y2) * es + viewport.pan.y}
                width={Math.abs(marqueeBox.x2 - marqueeBox.x1) * es}
                height={Math.abs(marqueeBox.y2 - marqueeBox.y1) * es}
                fill={CANVAS.amberSelectionFill}
                stroke={CANVAS.amber}
                strokeWidth={1}
                listening={false}
              />
            )}
            </>; }}</ViewportSubscriber>
          </Layer>
        </Stage>
        {showEmptyHint && (
          <div className="empty-sheet-hint" role="status">
            {t('emptySheetHint')}
          </div>
        )}
        <ViewportSubscriber store={vp.store}>{(viewport) => <>
        <ViewportControls
          zoomPercent={viewport.effectiveScale * 100}
          onZoomIn={vp.zoomIn}
          onZoomOut={vp.zoomOut}
          onFit={vp.fitToView}
          onActualSize={vp.zoomToActualSize}
        />
        {activeTool === 'measure' && measure.line && (() => {
          const midX = (measure.line.x1 + measure.line.x2) / 2;
          const midY = (measure.line.y1 + measure.line.y2) / 2;
          const sc = toScreenCoords(midX, midY, viewport.pan, viewport.effectiveScale);
          const saved = sheet.scale;
          return (
            <MeasureInput
              screenX={sc.x} screenY={sc.y}
              pixelLength={measurePxLength}
              initialValue={saved ? measurePxLength / saved.pxPerUnit : undefined}
              initialUnit={saved?.unit}
              onConfirm={handleMeasureConfirm}
              onCancel={() => handleToolChange('select')}
            />
          );
        })()}</>}</ViewportSubscriber>
      </div>
    </div>
  );
}
