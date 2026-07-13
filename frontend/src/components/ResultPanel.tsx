import { memo, useState, useEffect, useRef, useMemo } from 'react';

const IS_TOUCH = typeof window !== 'undefined' && window.matchMedia('(pointer: coarse)').matches;
import { useTranslation } from 'react-i18next';
import { Stage, Layer, Image as KonvaImage, Line, Group, Rect, Circle, Text as KonvaText } from 'react-konva';
import useImage from 'use-image';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { Piece, Project, Crop, BoundingBox, Scale, CurvePoint } from '../types';
import type { StepId } from './Tutorial/types';
import { computeCentroid, flattenCurves, ctrlToHandle, handleToCtrl, evaluateCubicBezier, isCubicCurvePoint, curveToCubicControls, alignHandle, splitCubicBezier, makeCubicCurvePoint } from '../utils/geometry';
import { Toolbar, SelectIcon, CropIcon, MeasureIcon, BoxIcon, DetectAllIcon, ViewIcon, HandIcon, PolygonIcon, PenIcon, PencilIcon } from './Toolbar';
import { IconUpload, IconSquare, IconLamp } from './icons';
import type { ToolId } from './Toolbar';
import { SelectAnimation, BoxAnimation, CropAnimation, MeasureAnimation, DetectAllAnimation, InspectAnimation, PanAnimation, PolygonAnimation, PenAnimation, PencilAnimation, SnappingAnimation, SolderAnimation, SymmetryAnimation, ProfileAnimation } from './ToolTooltipAnimations';
import { ToolTooltip } from './ToolTooltip';
import { CropOverlay } from './CropOverlay';
import { MeasureInput } from './MeasureInput';
import { MeasureLineOverlay } from './MeasureLineOverlay';
import { useViewport } from '../hooks/useViewport';
import { useMeasure } from '../hooks/useMeasure';
import { toImageCoords, toScreenCoords } from '../utils/viewport';
import { PieceProperties } from './PieceProperties';
import { ViewportControls } from './ViewportControls';
import { CANVAS } from '../theme';
import { computeUnrolledLamp, findLampEdgeSnap, getLampSnapPoints, LampSnapPoint, patternToSurfaceRobust } from '../utils/lampGeometry';
import { getSnapFractions } from '../utils/snapping';
import { constrainToAngle, isPointWithinBounds, nearestCandidate } from '../utils/vectorMath';
import { getPieceGeometry, type PieceGeometry } from '../editor/geometry/pieceGeometry';

function DragHandle({ onDrag, pointerEvents = 'auto' }: { onDrag: (delta: { x: number; y: number }) => void; pointerEvents?: 'auto' | 'none' }) {
  const last = useRef<{ x: number; y: number } | null>(null);
  return (
    <div
      onPointerDown={e => {
        e.stopPropagation();
        last.current = { x: e.clientX, y: e.clientY };
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      }}
      onPointerMove={e => {
        if (!last.current) return;
        onDrag({ x: e.clientX - last.current.x, y: e.clientY - last.current.y });
        last.current = { x: e.clientX, y: e.clientY };
      }}
      onPointerUp={() => { last.current = null; }}
      style={{
        height: 10,
        cursor: pointerEvents === 'none' ? 'inherit' : 'grab',
        pointerEvents,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: '8px 8px 0 0',
        background: 'var(--chrome-700)',
        borderBottom: '1px solid var(--hairline)',
        color: 'var(--text-dim)',
      }}
    >
      <svg width="20" height="4" viewBox="0 0 20 4"><circle cx="4" cy="2" r="1.5" fill="currentColor"/><circle cx="10" cy="2" r="1.5" fill="currentColor"/><circle cx="16" cy="2" r="1.5" fill="currentColor"/></svg>
    </div>
  );
}


interface PieceOverlayProps {
  piece: Piece;
  geometry: PieceGeometry;
  glassImageUrl: string;
  isSelected: boolean;
  isPending: boolean;
  opacity?: number;
  solderWidth: number;
  solderColor: string;
  onSelectPiece: (id: string | null, multi?: boolean) => void;
  selectionDisabled: boolean;
}

const PieceOverlay = memo(function PieceOverlay({ piece, geometry, glassImageUrl, isSelected, isPending, opacity = 1, solderWidth, solderColor, onSelectPiece, selectionDisabled }: PieceOverlayProps) {
  const [glassImg] = useImage(glassImageUrl);
  const [pulseHi, setPulseHi] = useState(false);
  useEffect(() => {
    if (!isPending) { setPulseHi(false); return; }
    const id = setInterval(() => setPulseHi(h => !h), 750);
    return () => clearInterval(id);
  }, [isPending]);
  const { x: tx, y: ty, rotation, scale } = piece.transform;
  const { flatPoints: flatPts, centroid, bounds, clipFunc: clipPolygon } = geometry;
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);

  function handleClick(e: KonvaEventObject<MouseEvent>) {
    e.cancelBubble = true;
    if (longPressFired.current) { longPressFired.current = false; return; }
    if (!selectionDisabled) onSelectPiece(piece.id, e.evt.shiftKey);
  }

  function handlePointerDown() {
    if (!IS_TOUCH) return;
    longPressFired.current = false;
    longPressTimer.current = setTimeout(() => {
      longPressFired.current = true;
      longPressTimer.current = null;
      if (!selectionDisabled) onSelectPiece(piece.id, true);
    }, 500);
  }

  function cancelLongPress() {
    if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null; }
  }

  return (
    <Group
      onClick={handleClick} onTap={handleClick} opacity={opacity}
      onPointerDown={handlePointerDown} onPointerMove={cancelLongPress} onPointerUp={cancelLongPress}
    >
      <Line points={flatPts} closed fill="rgba(0,0,0,0)" />
      <Group clipFunc={clipPolygon}>
        <Group
          x={centroid.x} y={centroid.y}
          rotation={(-rotation * 180) / Math.PI}
          scaleX={1 / scale} scaleY={1 / scale}
        >
          {glassImg && <KonvaImage image={glassImg} x={-tx} y={-ty} />}
        </Group>
        {isPending && (
          <Rect
            x={bounds.minX} y={bounds.minY}
            width={bounds.maxX - bounds.minX}
            height={bounds.maxY - bounds.minY}
            fill={`rgba(245,158,11,${pulseHi ? 0.28 : 0.10})`}
            listening={false}
          />
        )}
      </Group>
      <Line
        points={flatPts}
        stroke={isPending ? CANVAS.patternPending : isSelected ? CANVAS.amber : solderColor}
        strokeWidth={isSelected ? solderWidth * 1.25 : solderWidth}
        lineJoin="round"
        lineCap="round"
        closed listening={false}
      />
    </Group>
  );
});

interface ResultPanelProps {
  project: Project;
  selectedPieceIds: string[];
  pendingPieceIds: ReadonlySet<string>;
  onSelectPiece: (id: string | null, multi?: boolean) => void;
  onSelectPieces: (ids: string[]) => void;
  onPatternCropChange: (c: Partial<Crop>) => void;
  onPatternScaleChange: (s: Scale | null) => void;
  onAddPiece: (box: BoundingBox) => void;
  onAddManualPiece: (polygon: [number, number][], curvePoints?: CurvePoint[], anchorTypes?: ('corner' | 'smooth')[]) => void;
  onUpdatePieceLabel: (id: string, label: string) => void;
  onUpdatePieceSheet: (id: string, sheetId: string) => void;
  onUpdatePiecesSheet: (ids: string[], sheetId: string) => void;
  onAddSheetAndAssignPiece: (id: string, url?: string, label?: string) => void;
  onAddSheetAndAssignPieces: (ids: string[], url?: string, label?: string) => void;
  onDeletePiece: (id: string) => void;
  onDeletePieces: (ids: string[]) => void;
  onSmoothPiece: (id: string) => void;
  onSmoothPieces: (ids: string[]) => void;
  onUpdatePieceCurves: (id: string, curvePoints: CurvePoint[], anchorTypes?: ('corner' | 'smooth')[]) => void;
  onUpdatePiecePolygonAndCurves: (id: string, polygon: [number, number][], curvePoints: CurvePoint[], anchorTypes?: ('corner' | 'smooth')[]) => void;
  onUpdatePrompt: (pieceId: string, point: { x: number; y: number; label: 1 | 0 }) => void;
  onAutoSegment?: () => void;
  isAutoSegmenting?: boolean;
  isEncoding?: boolean;
  downloadProgress?: number | null;
  onUploadPattern: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onStartBlankCanvas: () => void;
  onStartLampMode?: () => void;
  debugMask?: { bitmap: ImageBitmap; width: number; height: number } | null;
  activeTool: ToolId;
  onChangeActiveTool: (tool: ToolId) => void;
  tutorialStep?: StepId | null;
  refineMode: 'add' | 'remove' | null;
  onRefineModeChange: (mode: 'add' | 'remove' | null) => void;
  onPenStatusChange?: (status: {
    coords: { x: number; y: number } | null;
    lastPoint: { x: number; y: number } | null;
  }) => void;
  onUpdateSolderWidthMM: (width: number) => void;
  onUpdateSolderColor: (color: import('../types').SolderColor) => void;
  onOpenLampProfile?: () => void;
  isSymmetryEnabled?: boolean;
  onToggleSymmetry?: (enabled: boolean) => void;
}

const getMinBoxSize = (width: number) => Math.max(10, width * 0.005);
export const SOLDER_COLORS = {
  black: '#1a1a1a',  // Charcoal black patina
  silver: '#7a828e', // Silver / Bright solder
  copper: '#a05c3f', // Copper patina
} as const;

const DEFAULT_SOLDER_WIDTH_MM = 4.5;

function getSolderWidth(scale: Scale | null, imgWidth: number, customWidthMM?: number) {
  const target = customWidthMM ?? DEFAULT_SOLDER_WIDTH_MM;
  if (!scale) {
    // If no scale is set, scale the baseline 0.6% image width by the ratio of custom width to default
    const ratio = target / DEFAULT_SOLDER_WIDTH_MM;
    return Math.max(2, imgWidth * 0.006 * ratio);
  }
  const { pxPerUnit, unit } = scale;
  if (unit === 'mm') return target * pxPerUnit;
  if (unit === 'cm') return (target / 10) * pxPerUnit;
  if (unit === 'in') return (target / 25.4) * pxPerUnit;
  return target;
}

function getSquareSegmentDistance(p: [number, number], p1: [number, number], p2: [number, number]): number {
  let x = p1[0];
  let y = p1[1];
  let dx = p2[0] - x;
  let dy = p2[1] - y;
  
  if (dx !== 0 || dy !== 0) {
    const t = ((p[0] - x) * dx + (p[1] - y) * dy) / (dx * dx + dy * dy);
    if (t > 1) {
      x = p2[0];
      y = p2[1];
    } else if (t > 0) {
      x += dx * t;
      y += dy * t;
    }
  }
  
  dx = p[0] - x;
  dy = p[1] - y;
  return dx * dx + dy * dy;
}

export function simplifyPath(points: [number, number][], epsilon: number): [number, number][] {
  if (points.length <= 2) return points;
  
  let maxSqDist = 0;
  let index = 0;
  const end = points.length - 1;
  
  for (let i = 1; i < end; i++) {
    const sqDist = getSquareSegmentDistance(points[i], points[0], points[end]);
    if (sqDist > maxSqDist) {
      index = i;
      maxSqDist = sqDist;
    }
  }
  
  if (maxSqDist > epsilon * epsilon) {
    const results1 = simplifyPath(points.slice(0, index + 1), epsilon);
    const results2 = simplifyPath(points.slice(index), epsilon);
    return results1.slice(0, results1.length - 1).concat(results2);
  }
  
  return [points[0], points[end]];
}

// Screen-space radius used for: pen tool snap-to-neighbor-vertex, and the
// "edge long enough" test that decides which vertices are eligible snap
// targets (and which corner handles are visible). Both share the threshold
// so the snap set always matches the visible handle set at any zoom.
const PEN_SNAP_PX = 14;
const TRACE_ONLY_TOOL_IDS = new Set<ToolId>(['box', 'detect-all', 'inspect']);

interface BezierAnchor {
  point: [number, number];
  in?: [number, number];
  out?: [number, number];
  smooth: boolean;
}

function anchorsToCurvePoints(anchors: BezierAnchor[]): CurvePoint[] {
  if (anchors.length < 2) return [];
  const curves: CurvePoint[] = [];
  for (let edgeIdx = 0; edgeIdx < anchors.length; edgeIdx++) {
    const from = anchors[edgeIdx];
    const to = anchors[(edgeIdx + 1) % anchors.length];
    if (!from.out && !to.in) continue;
    curves.push({
      edgeIdx,
      kind: 'cubic',
      ctrl: from.out ?? from.point,
      ctrl2: to.in ?? to.point,
    });
  }
  return curves;
}

function flattenOpenPenPath(anchors: BezierAnchor[], effectiveScale: number): [number, number][] {
  if (anchors.length === 0) return [];
  const result: [number, number][] = [anchors[0].point];
  for (let index = 0; index < anchors.length - 1; index++) {
    const from = anchors[index];
    const to = anchors[index + 1];
    if (!from.out && !to.in) {
      result.push(to.point);
      continue;
    }
    const ctrl1 = from.out ?? from.point;
    const ctrl2 = to.in ?? to.point;
    const estimate = Math.hypot(to.point[0] - from.point[0], to.point[1] - from.point[1]) * effectiveScale;
    const steps = Math.max(6, Math.min(32, Math.ceil(estimate / 20)));
    for (let step = 1; step <= steps; step++) {
      result.push(evaluateCubicBezier(from.point, ctrl1, ctrl2, to.point, step / steps));
    }
  }
  return result;
}

function translateCurvesWithAnchor(
  curves: CurvePoint[],
  vertexIdx: number,
  vertexCount: number,
  delta: [number, number],
): CurvePoint[] {
  const previousEdge = (vertexIdx - 1 + vertexCount) % vertexCount;
  return curves.map(curve => {
    if (isCubicCurvePoint(curve)) {
      if (curve.edgeIdx === vertexIdx) {
        return { ...curve, ctrl: [curve.ctrl[0] + delta[0], curve.ctrl[1] + delta[1]] };
      }
      if (curve.edgeIdx === previousEdge) {
        return { ...curve, ctrl2: [curve.ctrl2[0] + delta[0], curve.ctrl2[1] + delta[1]] };
      }
      return curve;
    }
    if (curve.edgeIdx === vertexIdx || curve.edgeIdx === previousEdge) {
      return { ...curve, ctrl: [curve.ctrl[0] + delta[0] / 2, curve.ctrl[1] + delta[1] / 2] };
    }
    return curve;
  });
}

function moveCubicHandle(
  curves: CurvePoint[],
  polygon: [number, number][],
  edgeIdx: number,
  side: 'ctrl' | 'ctrl2',
  point: [number, number],
  breakPair: boolean,
): CurvePoint[] {
  const count = polygon.length;
  const anchorIdx = side === 'ctrl' ? edgeIdx : (edgeIdx + 1) % count;
  const anchor = polygon[anchorIdx];
  const oppositeEdge = side === 'ctrl' ? (edgeIdx - 1 + count) % count : (edgeIdx + 1) % count;
  const oppositeSide: 'ctrl' | 'ctrl2' = side === 'ctrl' ? 'ctrl2' : 'ctrl';
  const opposite = curves.find(curve => curve.edgeIdx === oppositeEdge && isCubicCurvePoint(curve));
  const oppositePoint = opposite && isCubicCurvePoint(opposite) ? opposite[oppositeSide] : undefined;
  const alignedOpposite = !breakPair && oppositePoint
    ? alignHandle(anchor, point, Math.hypot(oppositePoint[0] - anchor[0], oppositePoint[1] - anchor[1]))
    : null;

  return curves.map(curve => {
    if (!isCubicCurvePoint(curve)) return curve;
    if (curve.edgeIdx === edgeIdx) return { ...curve, [side]: point };
    if (alignedOpposite && curve.edgeIdx === oppositeEdge) return { ...curve, [oppositeSide]: alignedOpposite };
    return curve;
  });
}

function insertAnchorOnEdge(
  polygon: [number, number][],
  curves: CurvePoint[],
  edgeIdx: number,
): { polygon: [number, number][]; curves: CurvePoint[]; insertedAt: number; curved: boolean } {
  const nextIdx = (edgeIdx + 1) % polygon.length;
  const start = polygon[edgeIdx];
  const end = polygon[nextIdx];
  const curve = curves.find(item => item.edgeIdx === edgeIdx);
  const insertedAt = edgeIdx + 1;
  let point: [number, number] = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
  const nextCurves: CurvePoint[] = [];

  for (const item of curves) {
    if (item.edgeIdx === edgeIdx) continue;
    nextCurves.push({ ...item, edgeIdx: item.edgeIdx > edgeIdx ? item.edgeIdx + 1 : item.edgeIdx });
  }

  if (curve) {
    const [ctrl1, ctrl2] = curveToCubicControls(start, end, curve);
    const [left, right] = splitCubicBezier({ start, ctrl1, ctrl2, end }, 0.5);
    point = left.end;
    nextCurves.push(makeCubicCurvePoint(edgeIdx, left.ctrl1, left.ctrl2));
    nextCurves.push(makeCubicCurvePoint(edgeIdx + 1, right.ctrl1, right.ctrl2));
  }

  const nextPolygon = [...polygon];
  nextPolygon.splice(insertedAt, 0, point);
  return { polygon: nextPolygon, curves: nextCurves, insertedAt, curved: !!curve };
}

function isStructuralCorner(
  polygon: [number, number][],
  idx: number,
  effectiveScale: number,
  thresholdPx = PEN_SNAP_PX,
): boolean {
  const len = polygon.length;
  const [x, y] = polygon[idx];
  const next = polygon[(idx + 1) % len];
  const prev = polygon[(idx - 1 + len) % len];
  const edgeLen = Math.hypot(next[0] - x, next[1] - y) * effectiveScale;
  const prevEdgeLen = Math.hypot(x - prev[0], y - prev[1]) * effectiveScale;
  return edgeLen >= thresholdPx || prevEdgeLen >= thresholdPx;
}

export function findPenSnapTarget(
  cursor: [number, number],
  pieces: Piece[],
  effectiveScale: number,
  extraVertices?: LampSnapPoint[],
): { pt: [number, number]; label?: string } | null {
  let best: { pt: [number, number]; label?: string } | null = null;
  let bestPxDist = PEN_SNAP_PX;
  for (const piece of pieces) {
    const polygon = piece.polygon;
    for (let i = 0; i < polygon.length; i++) {
      if (!isStructuralCorner(polygon, i, effectiveScale)) continue;
      const dx = polygon[i][0] - cursor[0];
      const dy = polygon[i][1] - cursor[1];
      const dist = Math.hypot(dx, dy) * effectiveScale;
      if (dist < bestPxDist) {
        bestPxDist = dist;
        best = { pt: [polygon[i][0], polygon[i][1]] };
      }
    }
  }
  if (extraVertices) {
    for (const sv of extraVertices) {
      const [vx, vy] = sv.pt;
      const dist = Math.hypot(vx - cursor[0], vy - cursor[1]) * effectiveScale;
      if (dist < bestPxDist) {
        bestPxDist = dist;
        best = { pt: [vx, vy], label: sv.label };
      }
    }
  }
  return best;
}

function findEdgeSnapTarget(
  cursor: [number, number],
  pieces: Piece[],
  effectiveScale: number,
  tolerancePx = PEN_SNAP_PX,
): [number, number] | null {
  let best: [number, number] | null = null;
  let bestDistance = tolerancePx;
  for (const piece of pieces) {
    const path = flattenCurves(piece.polygon, piece.curvePoints, 0.5 / Math.max(effectiveScale, 0.01));
    for (let index = 0; index < path.length; index++) {
      const start = path[index];
      const end = path[(index + 1) % path.length];
      const dx = end[0] - start[0];
      const dy = end[1] - start[1];
      const lengthSquared = dx * dx + dy * dy;
      if (lengthSquared === 0) continue;
      const parameter = Math.max(0, Math.min(1,
        ((cursor[0] - start[0]) * dx + (cursor[1] - start[1]) * dy) / lengthSquared,
      ));
      const projected: [number, number] = [start[0] + parameter * dx, start[1] + parameter * dy];
      const distance = Math.hypot(projected[0] - cursor[0], projected[1] - cursor[1]) * effectiveScale;
      if (distance < bestDistance) {
        bestDistance = distance;
        best = projected;
      }
    }
  }
  return best;
}

export function getCanvasSnapping(
  x: number,
  y: number,
  crop: Crop,
  patternWidth: number,
  patternHeight: number,
  effectiveScale: number,
  t: (key: string) => string,
  disableFractions = false,
  customBounds?: { left: number; right: number; top: number; bottom: number },
  thresholdPx = PEN_SNAP_PX
): { x: number; y: number; guides: AlignmentGuide[]; labels: string[] } {
  const threshold = thresholdPx / effectiveScale;
  let targetX = x;
  let targetY = y;
  const guides: AlignmentGuide[] = [];
  const labels: string[] = [];

  const left = customBounds ? customBounds.left : crop.left;
  const right = customBounds ? customBounds.right : patternWidth - crop.right;
  const top = customBounds ? customBounds.top : crop.top;
  const bottom = customBounds ? customBounds.bottom : patternHeight - crop.bottom;
  const W = right - left;
  const H = bottom - top;

  // 1. Edge Snapping (Highest Priority)
  let snappedX = false;
  let snappedY = false;

  if (Math.abs(x - left) < threshold) {
    targetX = left;
    snappedX = true;
    guides.push({ type: 'v', from: [left, top], to: [left, bottom] });
  } else if (Math.abs(x - right) < threshold) {
    targetX = right;
    snappedX = true;
    guides.push({ type: 'v', from: [right, top], to: [right, bottom] });
  }

  if (Math.abs(y - top) < threshold) {
    targetY = top;
    snappedY = true;
    guides.push({ type: 'h', from: [left, top], to: [right, top] });
  } else if (Math.abs(y - bottom) < threshold) {
    targetY = bottom;
    snappedY = true;
    guides.push({ type: 'h', from: [left, bottom], to: [right, bottom] });
  }

  // 2. Fractional Snapping (Lower Priority)
  if (!disableFractions) {
    const FRACTIONS = getSnapFractions(t);

    const minGap = 32; // minimum screen pixels between active guides

    // Choose the nearest eligible division, rather than the first fraction in
    // denominator order, so dense guides never win over a closer target.
    if (!snappedX && W > 0) {
      const candidate = nearestCandidate(
        x,
        FRACTIONS
          .map(frac => ({ ...frac, position: left + frac.value * W }))
          .filter(item => Math.min(Math.abs(item.position - left), Math.abs(item.position - right)) * effectiveScale >= minGap),
        effectiveScale,
        thresholdPx,
      );
      if (candidate) {
        targetX = candidate.position;
        snappedX = true;
        guides.push({ type: 'v', from: [candidate.position, top], to: [candidate.position, bottom] });
        labels.push(candidate.label);
      }
    }

    if (!snappedY && H > 0) {
      const candidate = nearestCandidate(
        y,
        FRACTIONS
          .map(frac => ({ ...frac, position: top + frac.value * H }))
          .filter(item => Math.min(Math.abs(item.position - top), Math.abs(item.position - bottom)) * effectiveScale >= minGap),
        effectiveScale,
        thresholdPx,
      );
      if (candidate) {
        targetY = candidate.position;
        snappedY = true;
        guides.push({ type: 'h', from: [left, candidate.position], to: [right, candidate.position] });
        labels.push(candidate.label);
      }
    }
  }

  return { x: targetX, y: targetY, guides, labels };
}

interface AlignmentGuide {
  type: 'h' | 'v';
  from: [number, number];
  to: [number, number];
}

interface LengthGuide {
  matchLength: number;
  center: [number, number];
  snappedPoint: [number, number];
  matchingSegment: { p1: [number, number]; p2: [number, number] };
}

export function findAlignmentGuides(
  cursor: [number, number],
  pieces: Piece[],
  effectiveScale: number,
  tolerancePx = PEN_SNAP_PX,
): { snapped: [number, number]; guides: AlignmentGuide[] } {
  let snapX: number | null = null;
  let snapY: number | null = null;
  let bestDistX = tolerancePx;
  let bestDistY = tolerancePx;
  let guideV: [number, number] | null = null;
  let guideH: [number, number] | null = null;

  for (const piece of pieces) {
    const polygon = flattenCurves(piece.polygon, piece.curvePoints);
    for (const v of polygon) {
      const dx = Math.abs(v[0] - cursor[0]) * effectiveScale;
      if (dx < bestDistX) {
        bestDistX = dx;
        snapX = v[0];
        guideV = [v[0], v[1]];
      }
      const dy = Math.abs(v[1] - cursor[1]) * effectiveScale;
      if (dy < bestDistY) {
        bestDistY = dy;
        snapY = v[1];
        guideH = [v[0], v[1]];
      }
    }
  }

  const snapped: [number, number] = [
    snapX !== null ? snapX : cursor[0],
    snapY !== null ? snapY : cursor[1],
  ];

  const guides: AlignmentGuide[] = [];
  if (snapX !== null && guideV) {
    guides.push({ type: 'v', from: guideV, to: [snapped[0], snapped[1]] });
  }
  if (snapY !== null && guideH) {
    guides.push({ type: 'h', from: guideH, to: [snapped[0], snapped[1]] });
  }

  return { snapped, guides };
}

export function findShiftAlignmentGuides(
  cursor: [number, number],
  lastPt: [number, number],
  snappedTheta: number,
  pieces: Piece[],
  effectiveScale: number,
  tolerancePx = PEN_SNAP_PX,
): { snapped: [number, number]; guides: AlignmentGuide[] } {
  const cosT = Math.cos(snappedTheta);
  const sinT = Math.sin(snappedTheta);
  
  let bestDist = tolerancePx;
  let snapped: [number, number] = [cursor[0], cursor[1]];
  let guide: AlignmentGuide | null = null;

  for (const piece of pieces) {
    const poly = flattenCurves(piece.polygon, piece.curvePoints);
    for (const v of poly) {
      if (Math.abs(cosT) > 1e-5) {
        const rx = (v[0] - lastPt[0]) / cosT;
        if (rx >= 0) {
          const px = v[0];
          const py = lastPt[1] + rx * sinT;
          const distPx = Math.hypot(cursor[0] - px, cursor[1] - py) * effectiveScale;
          if (distPx < bestDist) {
            bestDist = distPx;
            snapped = [px, py];
            guide = { type: 'v', from: [v[0], v[1]], to: [px, py] };
          }
        }
      }
      
      if (Math.abs(sinT) > 1e-5) {
        const ry = (v[1] - lastPt[1]) / sinT;
        if (ry >= 0) {
          const px = lastPt[0] + ry * cosT;
          const py = v[1];
          const distPx = Math.hypot(cursor[0] - px, cursor[1] - py) * effectiveScale;
          if (distPx < bestDist) {
            bestDist = distPx;
            snapped = [px, py];
            guide = { type: 'h', from: [v[0], v[1]], to: [px, py] };
          }
        }
      }
    }
  }

  return { snapped, guides: guide ? [guide] : [] };
}

export function findLengthSnap(
  cursor: [number, number],
  lastPt: [number, number],
  pieces: Piece[],
  activePolygonPoints: [number, number][],
  effectiveScale: number,
  tolerancePx = PEN_SNAP_PX,
) {
  const segments: { length: number; p1: [number, number]; p2: [number, number] }[] = [];
  
  if (activePolygonPoints.length > 1) {
    for (let i = 0; i < activePolygonPoints.length - 1; i++) {
      const p1 = activePolygonPoints[i];
      const p2 = activePolygonPoints[i + 1];
      segments.push({
        length: Math.hypot(p2[0] - p1[0], p2[1] - p1[1]),
        p1,
        p2,
      });
    }
  }

  if (activePolygonPoints.length > 0) {
    for (const piece of pieces) {
      const poly = flattenCurves(piece.polygon, piece.curvePoints);
      let shares = false;
      for (const ap of activePolygonPoints) {
        for (const pp of poly) {
          if (ap[0] === pp[0] && ap[1] === pp[1]) {
            shares = true;
            break;
          }
        }
        if (shares) break;
      }
      if (shares) {
        for (let i = 0; i < poly.length; i++) {
          const p1 = poly[i];
          const p2 = poly[(i + 1) % poly.length];
          segments.push({
            length: Math.hypot(p2[0] - p1[0], p2[1] - p1[1]),
            p1,
            p2,
          });
        }
      }
    }
  }

  const dx = cursor[0] - lastPt[0];
  const dy = cursor[1] - lastPt[1];
  const currentLen = Math.hypot(dx, dy);

  let bestMatch: typeof segments[0] | null = null;
  let bestDistPx = tolerancePx;
  for (const seg of segments) {
    const dist = Math.abs(currentLen - seg.length);
    const distPx = dist * effectiveScale;
    if (distPx < bestDistPx) {
      bestDistPx = distPx;
      bestMatch = seg;
    }
  }

  if (bestMatch) {
    return {
      matchLength: bestMatch.length,
      matchingSegment: { p1: bestMatch.p1, p2: bestMatch.p2 },
    };
  }
  return null;
}

export function ResultPanel({
  project, selectedPieceIds, pendingPieceIds, onSelectPiece, onSelectPieces, onPatternCropChange, onPatternScaleChange, onAddPiece,
  onAddManualPiece,
  onUpdatePieceLabel, onUpdatePieceSheet, onUpdatePiecesSheet, onAddSheetAndAssignPiece, onAddSheetAndAssignPieces, onDeletePiece, onDeletePieces, onSmoothPiece, onSmoothPieces,
  onUpdatePieceCurves, onUpdatePiecePolygonAndCurves, onUpdatePrompt,
  onAutoSegment, isAutoSegmenting, isEncoding, downloadProgress, onUploadPattern, onStartBlankCanvas, onStartLampMode, debugMask, activeTool, onChangeActiveTool,
  tutorialStep, refineMode, onRefineModeChange, onPenStatusChange,
  onUpdateSolderWidthMM, onUpdateSolderColor, onOpenLampProfile,
  isSymmetryEnabled = false, onToggleSymmetry,
}: ResultPanelProps) {
  const { t } = useTranslation();
  const selectedPieceIdSet = useMemo(() => new Set(selectedPieceIds), [selectedPieceIds]);
  const [isSolderPopoverOpen, setIsSolderPopoverOpen] = useState(false);
  const solderPopoverRef = useRef<HTMLDivElement>(null);
  const snapMenuRef = useRef<HTMLDivElement>(null);
  const isSolderPopoverOpenRef = useRef(isSolderPopoverOpen);
  isSolderPopoverOpenRef.current = isSolderPopoverOpen;

  useEffect(() => {
    if (!isSolderPopoverOpen) return;
    function handleOutsideClick(e: MouseEvent) {
      if (solderPopoverRef.current && !solderPopoverRef.current.contains(e.target as Node)) {
        setIsSolderPopoverOpen(false);
      }
    }
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [isSolderPopoverOpen]);

  // activeTool is now passed as a prop from the parent App component
  const [isSpaceDown, setIsSpaceDown] = useState(false);
  const refineModeRef = useRef(refineMode);
  refineModeRef.current = refineMode;

  const { patternWidth: pw, patternHeight: ph } = project;
  const isTraceMode = project.projectType !== 'lamp' && Boolean(project.patternImageUrl);
  const vp = useViewport(pw, ph);

  function isInsideDrawableBounds(point: [number, number], padding = 0) {
    return isPointWithinBounds(point, {
      left: project.patternCrop.left,
      right: pw - project.patternCrop.right,
      top: project.patternCrop.top,
      bottom: ph - project.patternCrop.bottom,
    }, padding);
  }

  function clearDraftHoverFeedback() {
    lastMousePosRef.current = null;
    setHoverPoint(null);
    setHoverSnapped(false);
    setActiveAlignmentGuides([]);
    setActiveLengthGuide(null);
    setActiveSnapLabels([]);
  }

  useEffect(() => {
    if (!isTraceMode && TRACE_ONLY_TOOL_IDS.has(activeTool)) {
      onChangeActiveTool('select');
    }
  }, [activeTool, isTraceMode, onChangeActiveTool]);

  const [activePolygonPoints, setActivePolygonPoints] = useState<[number, number][]>([]);
  const [activePenAnchors, setActivePenAnchors] = useState<BezierAnchor[]>([]);
  const [penDragIndex, setPenDragIndex] = useState<number | null>(null);
  const penDragIndexRef = useRef<number | null>(null);
  const [hoverPoint, setHoverPoint] = useState<[number, number] | null>(null);
  const [hoverSnapped, setHoverSnapped] = useState(false);
  const activePolygonPointsRef = useRef(activePolygonPoints);
  activePolygonPointsRef.current = activePolygonPoints;
  const activePenAnchorsRef = useRef(activePenAnchors);
  activePenAnchorsRef.current = activePenAnchors;

  const [, setIsShiftDown] = useState(false);
  const [snapEnabled, setSnapEnabled] = useState(true);
  const [snapMenuOpen, setSnapMenuOpen] = useState(false);
  const [snapSettings, setSnapSettings] = useState({
    anchors: true,
    edges: true,
    alignment: true,
    canvas: true,
    equalLength: true,
  });
  useEffect(() => {
    if (!snapMenuOpen) return;
    function closeSnapMenu(event: PointerEvent | KeyboardEvent) {
      if (event instanceof KeyboardEvent && event.key !== 'Escape') return;
      if (event instanceof PointerEvent && snapMenuRef.current?.contains(event.target as Node)) return;
      setSnapMenuOpen(false);
    }
    document.addEventListener('pointerdown', closeSnapMenu);
    window.addEventListener('keydown', closeSnapMenu);
    return () => {
      document.removeEventListener('pointerdown', closeSnapMenu);
      window.removeEventListener('keydown', closeSnapMenu);
    };
  }, [snapMenuOpen]);
  const lastMousePosRef = useRef<{ x: number; y: number } | null>(null);
  // Tracks whether the pointer is over this panel, so single-key tool
  // shortcuts only apply here instead of firing into both panels at once.
  const isPointerInsideRef = useRef(false);

  const piecesRef = useRef(project.pieces);
  piecesRef.current = project.pieces;
  const effectiveScaleRef = useRef(vp.effectiveScale);
  effectiveScaleRef.current = vp.effectiveScale;

  const [activeAlignmentGuides, setActiveAlignmentGuides] = useState<AlignmentGuide[]>([]);
  const [activeLengthGuide, setActiveLengthGuide] = useState<LengthGuide | null>(null);
  const [activeSnapLabels, setActiveSnapLabels] = useState<string[]>([]);

  function updateHoverPoint(
    imageX: number,
    imageY: number,
    shiftPressed: boolean,
    suppressSnap = false,
  ): [number, number] | null {
    if (activeTool !== 'polygon' && activeTool !== 'pen') return null;
    suppressSnap = suppressSnap || !snapEnabled;

    const pathPoints = activeTool === 'polygon'
      ? activePolygonPointsRef.current
      : activePenAnchorsRef.current.map(anchor => anchor.point);
    const lastPt = pathPoints[pathPoints.length - 1];

    if (suppressSnap) {
      const raw: [number, number] = [imageX, imageY];
      const result = shiftPressed && lastPt ? constrainToAngle(raw, lastPt) : raw;
      setHoverPoint(result);
      setHoverSnapped(false);
      setActiveAlignmentGuides([]);
      setActiveLengthGuide(null);
      setActiveSnapLabels([]);
      return result;
    }

    // True polygon anchors are the highest-priority snap targets. Flattened
    // curve samples are deliberately excluded so editable anchors remain the
    // only magnetic points on curved paths.
    const snap = snapSettings.anchors
      ? findPenSnapTarget([imageX, imageY], piecesRef.current, effectiveScaleRef.current, lampSnapPointsRef.current)
      : null;
    if (snap) {
      const constrained = shiftPressed && lastPt ? constrainToAngle(snap.pt, lastPt) : snap.pt;
      const exact = Math.hypot(constrained[0] - snap.pt[0], constrained[1] - snap.pt[1]) * effectiveScaleRef.current < 0.75;
      const result = exact ? snap.pt : constrained;
      setHoverPoint(result);
      setHoverSnapped(exact);
      setActiveAlignmentGuides([]);
      setActiveLengthGuide(null);
      setActiveSnapLabels(exact && snap.label ? [snap.label] : []);
      return result;
    }

    const edgeTarget = snapSettings.edges
      ? findEdgeSnapTarget([imageX, imageY], piecesRef.current, effectiveScaleRef.current)
      : null;
    if (edgeTarget) {
      const constrained = shiftPressed && lastPt ? constrainToAngle(edgeTarget, lastPt) : edgeTarget;
      const exact = Math.hypot(constrained[0] - edgeTarget[0], constrained[1] - edgeTarget[1]) * effectiveScaleRef.current < 0.75;
      const result = exact ? edgeTarget : constrained;
      setHoverPoint(result);
      setHoverSnapped(exact);
      setActiveAlignmentGuides([]);
      setActiveLengthGuide(null);
      setActiveSnapLabels([]);
      return result;
    }

    // 1b. Lamp seam edge snap — project onto nearest seam line.
    if (unrolledLampRef.current) {
      const edgeSnap = findLampEdgeSnap([imageX, imageY], unrolledLampRef.current, effectiveScaleRef.current, PEN_SNAP_PX);
      if (edgeSnap) {
        setHoverPoint(edgeSnap);
        setHoverSnapped(true);
        setActiveAlignmentGuides([]);
        setActiveLengthGuide(null);
        return edgeSnap;
      }
    }

    let finalX = imageX;
    let finalY = imageY;
    let alignmentGuides: AlignmentGuide[] = [];
    let lengthGuide: LengthGuide | null = null;

    if (lastPt) {
      let theta = Math.atan2(imageY - lastPt[1], imageX - lastPt[0]);
      if (shiftPressed) theta = Math.round(theta / (Math.PI / 4)) * (Math.PI / 4);

      const lenSnap = snapSettings.equalLength ? findLengthSnap(
        [imageX, imageY],
        lastPt,
        piecesRef.current,
        pathPoints,
        effectiveScaleRef.current,
      ) : null;

      if (lenSnap) {
        finalX = lastPt[0] + lenSnap.matchLength * Math.cos(theta);
        finalY = lastPt[1] + lenSnap.matchLength * Math.sin(theta);
        lengthGuide = {
          matchLength: lenSnap.matchLength,
          center: lastPt,
          snappedPoint: [finalX, finalY],
          matchingSegment: lenSnap.matchingSegment,
        };
      } else if (shiftPressed) {
        const align = findShiftAlignmentGuides(
          [imageX, imageY], lastPt, theta, piecesRef.current, effectiveScaleRef.current,
        );
        if (align.guides.length > 0) {
          finalX = align.snapped[0];
          finalY = align.snapped[1];
          alignmentGuides = align.guides;
        } else {
          [finalX, finalY] = constrainToAngle([imageX, imageY], lastPt);
        }
      } else if (snapSettings.alignment) {
        const align = findAlignmentGuides([imageX, imageY], piecesRef.current, effectiveScaleRef.current);
        finalX = align.snapped[0];
        finalY = align.snapped[1];
        alignmentGuides = align.guides;
      }
    } else if (snapSettings.alignment) {
      const align = findAlignmentGuides([imageX, imageY], piecesRef.current, effectiveScaleRef.current);
      finalX = align.snapped[0];
      finalY = align.snapped[1];
      alignmentGuides = align.guides;
    }

    let customBounds = undefined;
    if (project.projectType === 'lamp' && unrolledLamp && unrolledLamp.mode === 'faceted') {
      const N = project.lampConfig?.facetCount ?? 6;
      const surf = patternToSurfaceRobust(finalX, finalY, unrolledLamp, N);
      const strip = unrolledLamp.strips[surf.facetIdx];
      const tier = strip?.tiers[surf.tierIdx];
      if (strip && tier) {
        const maxChord = Math.max(tier.topChord, tier.botChord);
        customBounds = {
          left: strip.centerX - maxChord / 2,
          right: strip.centerX + maxChord / 2,
          top: tier.topY,
          bottom: tier.botY
        };
      }
    }

    const edgeSnap = snapSettings.canvas
      ? getCanvasSnapping(
        finalX, finalY, project.patternCrop, project.patternWidth,
        project.patternHeight, effectiveScaleRef.current, t, false, customBounds,
      )
      : { x: finalX, y: finalY, guides: [] as AlignmentGuide[], labels: [] as string[] };
    finalX = edgeSnap.x;
    finalY = edgeSnap.y;
    if (edgeSnap.guides.length > 0) alignmentGuides = [...alignmentGuides, ...edgeSnap.guides];

    // Modifier constraints are absolute: lower-priority canvas/alignment snaps
    // may suggest a point, but must never bend a promised 45° segment.
    if (shiftPressed && lastPt) {
      const theta = Math.round(Math.atan2(imageY - lastPt[1], imageX - lastPt[0]) / (Math.PI / 4)) * (Math.PI / 4);
      const radius = Math.hypot(finalX - lastPt[0], finalY - lastPt[1]);
      const constrained: [number, number] = [
        lastPt[0] + radius * Math.cos(theta),
        lastPt[1] + radius * Math.sin(theta),
      ];
      const invalidatedSnap = Math.hypot(constrained[0] - finalX, constrained[1] - finalY) * effectiveScaleRef.current > 0.75;
      finalX = constrained[0];
      finalY = constrained[1];
      if (invalidatedSnap) {
        alignmentGuides = [];
        lengthGuide = null;
        edgeSnap.labels = [];
      }
    }

    const result: [number, number] = [finalX, finalY];
    setActiveSnapLabels(edgeSnap.labels);
    setHoverPoint(result);
    setHoverSnapped(false);
    setActiveAlignmentGuides(alignmentGuides);
    setActiveLengthGuide(lengthGuide);
    return result;
  }

  function resolveEditedAnchor(
    cursor: [number, number],
    dragOrigin: [number, number],
    pieceId: string,
    shiftPressed: boolean,
    suppressSnap: boolean,
  ): [number, number] {
    suppressSnap = suppressSnap || !snapEnabled;
    if (suppressSnap) return shiftPressed ? constrainToAngle(cursor, dragOrigin) : cursor;
    const otherPieces = piecesRef.current.filter(piece => piece.id !== pieceId);
    const anchorSnap = snapSettings.anchors
      ? findPenSnapTarget(cursor, otherPieces, effectiveScaleRef.current)
      : null;
    let result: [number, number] = anchorSnap?.pt
      ?? (snapSettings.edges ? findEdgeSnapTarget(cursor, otherPieces, effectiveScaleRef.current) : null)
      ?? cursor;
    let guides: AlignmentGuide[] = [];
    if (result === cursor) {
      const aligned = snapSettings.alignment
        ? findAlignmentGuides(cursor, otherPieces, effectiveScaleRef.current)
        : { snapped: cursor, guides: [] };
      result = aligned.snapped;
      guides = aligned.guides;
      const canvas = snapSettings.canvas
        ? getCanvasSnapping(
          result[0], result[1], project.patternCrop, project.patternWidth,
          project.patternHeight, effectiveScaleRef.current, t,
        )
        : { x: result[0], y: result[1], guides: [] as AlignmentGuide[], labels: [] as string[] };
      result = [canvas.x, canvas.y];
      guides = [...guides, ...canvas.guides];
      setActiveSnapLabels(canvas.labels);
    } else {
      setActiveSnapLabels([]);
    }
    if (shiftPressed) {
      const constrained = constrainToAngle(result, dragOrigin);
      if (Math.hypot(constrained[0] - result[0], constrained[1] - result[1]) * effectiveScaleRef.current > 0.75) {
        guides = [];
        setActiveSnapLabels([]);
      }
      result = constrained;
    }
    setActiveAlignmentGuides(guides);
    return result;
  }

  const [draggedCorner, setDraggedCorner] = useState<{ pieceId: string; idx: number } | null>(null);
  const [draggedMidpoint, setDraggedMidpoint] = useState<{ pieceId: string; edgeIdx: number } | null>(null);
  const [dragStartPolygon, setDragStartPolygon] = useState<[number, number][] | null>(null);
  const [activeDragPolygon, setActiveDragPolygon] = useState<[number, number][] | null>(null);
  // Parametric: live curvePoints during a midpoint drag (polygon stays unchanged)
  const [activeDragCurvePoints, setActiveDragCurvePoints] = useState<CurvePoint[] | null>(null);
  const dragStartCurvePointsRef = useRef<CurvePoint[]>([]);

  const [pencilPoints, setPencilPoints] = useState<[number, number][]>([]);

  const [tooltipDrag, setTooltipDrag] = useState<{x: number; y: number}>({x: 0, y: 0});
  const addSheetInputRef = useRef<HTMLInputElement>(null);
  const [pieceForNewSheet, setPieceForNewSheet] = useState<string | null>(null);

  const handleAddSheetClick = (pieceId: string) => {
    setPieceForNewSheet(pieceId);
    addSheetInputRef.current?.click();
  };

  const handleAddSheetFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !pieceForNewSheet) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      if (pieceForNewSheet === '__multiple__') {
        onAddSheetAndAssignPieces(selectedPieceIds, dataUrl, file.name);
      } else {
        onAddSheetAndAssignPiece(pieceForNewSheet, dataUrl, file.name);
      }
    };
    reader.readAsDataURL(file);
    e.target.value = '';
    setPieceForNewSheet(null);
  };

  const solderWidth = useMemo(() => getSolderWidth(project.patternScale, project.patternWidth, project.solderWidthMM), [project.patternScale, project.patternWidth, project.solderWidthMM]);
  const isLamp = project.projectType === 'lamp';
  const unrolledLamp = useMemo(() => (isLamp ? computeUnrolledLamp(project.lampConfig) : null), [isLamp, project.lampConfig]);
  const lampSnapPoints = useMemo(() => (unrolledLamp ? getLampSnapPoints(unrolledLamp, vp.effectiveScale, t) : undefined), [unrolledLamp, vp.effectiveScale, t]);
  const lampSnapPointsRef = useRef(lampSnapPoints);
  lampSnapPointsRef.current = lampSnapPoints;
  const unrolledLampRef = useRef(unrolledLamp);
  unrolledLampRef.current = unrolledLamp;

  function commitActivePolygon() {
    if (activePolygonPointsRef.current.length >= 3) {
      onAddManualPiece(activePolygonPointsRef.current);
    }
    setActivePolygonPoints([]);
    setHoverPoint(null);
    setHoverSnapped(false);
    setActiveAlignmentGuides([]);
    setActiveLengthGuide(null);
    setActiveSnapLabels([]);
  }

  function clearActivePen() {
    setActivePenAnchors([]);
    setPenDragIndex(null);
    penDragIndexRef.current = null;
    setHoverPoint(null);
    setHoverSnapped(false);
    setActiveAlignmentGuides([]);
    setActiveLengthGuide(null);
    setActiveSnapLabels([]);
  }

  function commitActivePen() {
    const anchors = activePenAnchorsRef.current;
    if (anchors.length >= 3) {
      const polygon = anchors.map(anchor => anchor.point);
      const area = Math.abs(polygon.reduce((sum, point, index) => {
        const next = polygon[(index + 1) % polygon.length];
        return sum + point[0] * next[1] - next[0] * point[1];
      }, 0)) / 2;
      if (area * vp.effectiveScale * vp.effectiveScale >= 4) {
        onAddManualPiece(
          polygon,
          anchorsToCurvePoints(anchors),
          anchors.map(anchor => anchor.smooth ? 'smooth' : 'corner'),
        );
      }
    }
    clearActivePen();
  }

  useEffect(() => {
    onRefineModeChange(null);
    setTooltipDrag({x: 0, y: 0});
  }, [selectedPieceIds]);

  const onPenStatusChangeRef = useRef(onPenStatusChange);
  onPenStatusChangeRef.current = onPenStatusChange;

  const lastPoint = activeTool === 'pen'
    ? activePenAnchors[activePenAnchors.length - 1]?.point ?? null
    : activePolygonPoints[activePolygonPoints.length - 1] ?? null;
  useEffect(() => {
    if (activeTool === 'polygon' || activeTool === 'pen') {
      onPenStatusChangeRef.current?.({
        coords: hoverPoint ? { x: hoverPoint[0], y: hoverPoint[1] } : null,
        lastPoint: lastPoint ? { x: lastPoint[0], y: lastPoint[1] } : null,
      });
    } else {
      onPenStatusChangeRef.current?.({ coords: null, lastPoint: null });
    }
  }, [hoverPoint, lastPoint, activeTool]);

  // Capture only draft undo so it wins over the app-level history handler.
  // All other shortcuts remain in bubble phase, allowing open modals to stop
  // Escape and single-key commands before they reach the canvas.
  function handleKeyDownCapture(e: KeyboardEvent) {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
    if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'z') return;
    if (activeTool === 'polygon' && activePolygonPointsRef.current.length > 0) {
      e.preventDefault();
      e.stopImmediatePropagation();
      setActivePolygonPoints(prev => prev.slice(0, -1));
    } else if (activeTool === 'pen' && activePenAnchorsRef.current.length > 0) {
      e.preventDefault();
      e.stopImmediatePropagation();
      setActivePenAnchors(prev => prev.slice(0, -1));
    }
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
    if (e.key === 'Control') {
      if (lastMousePosRef.current) updateHoverPoint(lastMousePosRef.current.x, lastMousePosRef.current.y, e.shiftKey, true);
      return;
    }
    if (e.code === 'Space' && !e.repeat) {
      if (!isPointerInsideRef.current) return;
      e.preventDefault();
      setIsSpaceDown(true);
      return;
    }
    if (e.key === 'Shift') {
      if (!e.repeat && lastMousePosRef.current) {
        setIsShiftDown(true);
        updateHoverPoint(lastMousePosRef.current.x, lastMousePosRef.current.y, true, e.ctrlKey);
      }
      return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey || !isPointerInsideRef.current) return;

    const key = e.key.toLowerCase();
    if (e.key === '+' || e.key === '=') { e.preventDefault(); vp.zoomIn(); return; }
    if (e.key === '-') { e.preventDefault(); vp.zoomOut(); return; }
    if (e.shiftKey && e.code === 'Digit1') { e.preventDefault(); vp.fitToView(); return; }
    if (e.shiftKey && e.code === 'Digit0') { e.preventDefault(); vp.zoomToActualSize(); return; }

    if (key === 'v') handleToolChange('select');
    else if (key === 'h') handleToolChange('pan');
    else if (key === 'b' && isTraceMode && !isEncoding) handleToolChange('box');
    else if (key === 'p') handleToolChange(e.shiftKey ? 'polygon' : 'pen');
    else if (key === 'n') handleToolChange('pencil');
    else if (key === 'c') handleToolChange('crop');
    else if (key === 'm') handleToolChange('measure');
    else if (key === 'i' && isTraceMode) handleToolChange('inspect');
    else if (key === 'a') onRefineModeChange(refineModeRef.current === 'add' ? null : 'add');
    else if (key === 's') onRefineModeChange(refineModeRef.current === 'remove' ? null : 'remove');
    else if (e.key === 'Enter') {
      if (activeTool === 'polygon' && activePolygonPointsRef.current.length >= 3) commitActivePolygon();
      else if (activeTool === 'pen' && activePenAnchorsRef.current.length >= 3) commitActivePen();
    } else if (e.key === 'Escape') {
      if (isSolderPopoverOpenRef.current) setIsSolderPopoverOpen(false);
      else if (refineModeRef.current) onRefineModeChange(null);
      else if (activePolygonPointsRef.current.length > 0) {
        setActivePolygonPoints([]);
        setHoverPoint(null);
        setHoverSnapped(false);
        setActiveSnapLabels([]);
      } else if (activePenAnchorsRef.current.length > 0) clearActivePen();
      else handleToolChange('select');
    }
  }

  function handleKeyUp(e: KeyboardEvent) {
    if (e.code === 'Space') setIsSpaceDown(false);
    if (e.key === 'Control' && lastMousePosRef.current) {
      updateHoverPoint(lastMousePosRef.current.x, lastMousePosRef.current.y, e.shiftKey, false);
    }
    if (e.key === 'Shift') {
      setIsShiftDown(false);
      if (lastMousePosRef.current) updateHoverPoint(lastMousePosRef.current.x, lastMousePosRef.current.y, false, e.ctrlKey);
    }
  }

  // Dispatch through a ref so the listeners always see the latest render's
  // closures. The previous [activeTool]-dep effect kept stale captures of
  // isEncoding, project and measure alive between tool changes ('b' stayed
  // dead after encoding finished; 'm' calibrated against an old crop).
  const keyHandlersRef = useRef({ downCapture: handleKeyDownCapture, down: handleKeyDown, up: handleKeyUp });
  keyHandlersRef.current = { downCapture: handleKeyDownCapture, down: handleKeyDown, up: handleKeyUp };

  useEffect(() => {
    const downCapture = (e: KeyboardEvent) => keyHandlersRef.current.downCapture(e);
    const down = (e: KeyboardEvent) => keyHandlersRef.current.down(e);
    const up = (e: KeyboardEvent) => keyHandlersRef.current.up(e);
    // Capture phase only for the pen Cmd+Z vertex-pop, which must run before
    // App.tsx's bubble-phase undo listener regardless of registration order.
    // The rest stay bubble-phase so an open modal can stop them (see above).
    window.addEventListener('keydown', downCapture, true);
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', downCapture, true);
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, []);

  const [drawingBox, setDrawingBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [marqueeBox, setMarqueeBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [dashOffset, setDashOffset] = useState(0);

  useEffect(() => {
    const isFirstPending = tutorialStep === 'cut-first-piece' && project.pieces.length === 0;
    const isSecondPending = tutorialStep === 'cut-second-piece' && project.pieces.length <= 1;
    if (!isFirstPending && !isSecondPending) return;
    let animId: number;
    const tick = () => {
      setDashOffset(prev => (prev + 1.5) % 40);
      animId = requestAnimationFrame(tick);
    };
    animId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animId);
  }, [tutorialStep, project.pieces.length]);
  
  const [patternImg] = useImage(project.patternImageUrl);
  const sheetMap = useMemo(
    () => Object.fromEntries(project.sheets.map(s => [s.id, s])),
    [project.sheets],
  );
  const measure = useMeasure();

  function isBackground(e: KonvaEventObject<PointerEvent | MouseEvent>) {
    return e.target.getType() === 'Stage' || (e.target as { attrs?: { id?: string } }).attrs?.id === 'bg';
  }

  // Capture the pointer for the duration of a drag gesture so pointermove/
  // pointerup keep arriving even when the pointer leaves the canvas before
  // release — otherwise the gesture (pan, box, marquee, pencil) sticks "on"
  // and keeps following the bare cursor when it re-enters.
  function capturePointer(e: KonvaEventObject<PointerEvent>) {
    const evt = e.evt;
    if (evt?.target instanceof Element && evt.pointerId !== undefined) {
      try { evt.target.setPointerCapture(evt.pointerId); } catch { /* pointer already gone */ }
    }
  }

  function handlePointerDown(e: KonvaEventObject<PointerEvent>) {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;

    const isMiddleClick = e.evt && (e.evt as MouseEvent).button === 1;
    if (isMiddleClick || activeTool === 'pan' || isSpaceDown) {
      capturePointer(e);
      vp.startPan(ptr);
      return;
    }
    
    const lastSelectedId = selectedPieceIds[selectedPieceIds.length - 1];
    if (refineMode && lastSelectedId && !isEncoding) {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      onUpdatePrompt(lastSelectedId, { x, y, label: refineMode === 'add' ? 1 : 0 });
      return;
    }

    if (activeTool === 'polygon') {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      if (activePolygonPointsRef.current.length >= 3) {
        const [startX, startY] = activePolygonPointsRef.current[0];
        const dist = Math.hypot(x - startX, y - startY) * vp.effectiveScale;
        if (dist < 15) {
          commitActivePolygon();
          return;
        }
      }
      const resolved = updateHoverPoint(x, y, e.evt.shiftKey, e.evt.ctrlKey) ?? [x, y];
      if (!isInsideDrawableBounds(resolved)) {
        clearDraftHoverFeedback();
        return;
      }
      setActivePolygonPoints(prev => [...prev, resolved]);
      return;
    }

    if (activeTool === 'pen') {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      const anchors = activePenAnchorsRef.current;
      if (anchors.length >= 3) {
        const [startX, startY] = anchors[0].point;
        if (Math.hypot(x - startX, y - startY) * vp.effectiveScale < 15) {
          commitActivePen();
          return;
        }
      }
      const resolved = updateHoverPoint(x, y, e.evt.shiftKey, e.evt.ctrlKey) ?? [x, y];
      if (!isInsideDrawableBounds(resolved)) {
        clearDraftHoverFeedback();
        return;
      }
      capturePointer(e);
      const index = anchors.length;
      penDragIndexRef.current = index;
      setPenDragIndex(index);
      setActivePenAnchors(prev => [...prev, { point: resolved, smooth: false }]);
      return;
    }

    if (activeTool === 'pencil') {
      capturePointer(e);
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      setPencilPoints([[x, y]]);
      return;
    }

    if (activeTool === 'box' && !isEncoding) {
      capturePointer(e);
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      setDrawingBox({ x1: x, y1: y, x2: x, y2: y });
      return;
    }

    if (activeTool === 'select' && isBackground(e)) {
      capturePointer(e);
      if (IS_TOUCH) {
        vp.startPan(ptr);
      } else {
        const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
        setMarqueeBox({ x1: x, y1: y, x2: x, y2: y });
      }
      return;
    }
  }

  function handlePointerMove(e: KonvaEventObject<PointerEvent>) {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;
    if (activeTool === 'pen' && penDragIndexRef.current !== null) {
      const index = penDragIndexRef.current;
      const anchor = activePenAnchorsRef.current[index];
      if (!anchor) return;
      const handlePoint = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      let handle: [number, number] = [handlePoint.x, handlePoint.y];
      if (e.evt.shiftKey) handle = constrainToAngle(handle, anchor.point);
      const dx = handle[0] - anchor.point[0];
      const dy = handle[1] - anchor.point[1];
      setActivePenAnchors(prev => prev.map((item, itemIndex) => itemIndex === index ? {
        ...item,
        in: [item.point[0] - dx, item.point[1] - dy],
        out: [item.point[0] + dx, item.point[1] + dy],
        smooth: !e.evt.altKey,
      } : item));
      return;
    }
    if (drawingBox) {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      setDrawingBox(b => b ? { ...b, x2: x, y2: y } : null);
      return;
    }
    if (marqueeBox) {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      setMarqueeBox(b => b ? { ...b, x2: x, y2: y } : null);
      return;
    }
    if (activeTool === 'polygon' || activeTool === 'pen') {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      const edgeSnapPadding = PEN_SNAP_PX / Math.max(vp.effectiveScale, Number.EPSILON);
      if (!isInsideDrawableBounds([x, y], edgeSnapPadding)) {
        clearDraftHoverFeedback();
        return;
      }
      lastMousePosRef.current = { x, y };
      const isShift = e.evt ? e.evt.shiftKey : false;
      setIsShiftDown(isShift);
      const resolved = updateHoverPoint(x, y, isShift, e.evt.ctrlKey);
      if (resolved && !isInsideDrawableBounds(resolved)) clearDraftHoverFeedback();
      return;
    }
    if (activeTool === 'pencil') {
      if (pencilPoints.length > 0) {
        const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
        setPencilPoints(prev => [...prev, [x, y]]);
      }
      return;
    }
    vp.movePan(ptr);
  }

  function handlePointerUp() {
    if (penDragIndexRef.current !== null) {
      penDragIndexRef.current = null;
      setPenDragIndex(null);
      return;
    }
    if (drawingBox) {
      const box: BoundingBox = {
        x1: Math.min(drawingBox.x1, drawingBox.x2),
        y1: Math.min(drawingBox.y1, drawingBox.y2),
        x2: Math.max(drawingBox.x1, drawingBox.x2),
        y2: Math.max(drawingBox.y1, drawingBox.y2),
      };
      const minBox = getMinBoxSize(pw);
      if (box.x2 - box.x1 >= minBox && box.y2 - box.y1 >= minBox) {
        onAddPiece(box);
      }
      setDrawingBox(null);
      return;
    }
    if (marqueeBox) {
      const box = {
        x1: Math.min(marqueeBox.x1, marqueeBox.x2),
        y1: Math.min(marqueeBox.y1, marqueeBox.y2),
        x2: Math.max(marqueeBox.x1, marqueeBox.x2),
        y2: Math.max(marqueeBox.y1, marqueeBox.y2),
      };
      const containsMode = marqueeBox.x2 >= marqueeBox.x1;
      const hitIds = project.pieces.filter(piece => {
        const display = flattenCurves(piece.polygon, piece.curvePoints);
        const xs = display.map(point => point[0]);
        const ys = display.map(point => point[1]);
        const bounds = { left: Math.min(...xs), right: Math.max(...xs), top: Math.min(...ys), bottom: Math.max(...ys) };
        return containsMode
          ? bounds.left >= box.x1 && bounds.right <= box.x2 && bounds.top >= box.y1 && bounds.bottom <= box.y2
          : bounds.right >= box.x1 && bounds.left <= box.x2 && bounds.bottom >= box.y1 && bounds.top <= box.y2;
      }).map(piece => piece.id);

      if (hitIds.length > 0) {
        onSelectPieces(hitIds);
      } else if (Math.abs(marqueeBox.x2 - marqueeBox.x1) < 2 && Math.abs(marqueeBox.y2 - marqueeBox.y1) < 2) {
        onSelectPiece(null);
      }
      setMarqueeBox(null);
      return;
    }
    if (activeTool === 'pencil') {
      if (pencilPoints.length >= 3) {
        const simplified = simplifyPath(pencilPoints, 2 / vp.effectiveScale);
        if (simplified.length >= 3) {
          onAddManualPiece(simplified);
        }
      }
      setPencilPoints([]);
      return;
    }
    vp.endPan();
  }

  // The browser cancelled the gesture (OS gesture, tab switch, capture lost):
  // abort in-progress drags without committing anything.
  function handlePointerCancel() {
    if (penDragIndexRef.current !== null) {
      const cancelledIndex = penDragIndexRef.current;
      setActivePenAnchors(prev => prev.filter((_, index) => index !== cancelledIndex));
      penDragIndexRef.current = null;
      setPenDragIndex(null);
    }
    setDrawingBox(null);
    setMarqueeBox(null);
    setPencilPoints([]);
    vp.endPan();
  }

  function handleMeasureConfirm(realLength: number, unit: Scale['unit']) {
    if (!measure.line) return;
    const px = Math.hypot(measure.line.x2 - measure.line.x1, measure.line.y2 - measure.line.y1);
    onPatternScaleChange({ pxPerUnit: px / realLength, unit, line: { ...measure.line } });
  }

  function handleToolChange(id: ToolId) {
    if (!isTraceMode && TRACE_ONLY_TOOL_IDS.has(id)) return;
    if (id === activeTool && id !== 'select') {
      if (id === 'polygon') setActivePolygonPoints([]);
      if (id === 'pen') clearActivePen();
      onChangeActiveTool('select');
      if (id === 'measure') measure.reset();
      return;
    }

    if (id !== 'polygon') {
      setActivePolygonPoints([]);
      setHoverPoint(null);
      setHoverSnapped(false);
      lastMousePosRef.current = null;
      setActiveAlignmentGuides([]);
      setActiveLengthGuide(null);
      setActiveSnapLabels([]);
    }
    if (id !== 'pen') clearActivePen();
    if (id !== 'pencil') {
      setPencilPoints([]);
    }
    setDraggedCorner(null);
    setDraggedMidpoint(null);
    setDragStartPolygon(null);
    setActiveDragPolygon(null);
    setActiveDragCurvePoints(null);

    if (id === 'detect-all') {
      if (!isEncoding) onAutoSegment?.();
      return;
    }
    onRefineModeChange(null);
    if (activeTool === 'measure' && id !== 'measure') measure.reset();
    if (id === 'measure') {
      const saved = project.patternScale?.line;
      const cropL = project.patternCrop.left;
      const cropT = project.patternCrop.top;
      const cropR = pw - project.patternCrop.right;
      const cropB = ph - project.patternCrop.bottom;
      
      const isTutorial = project.name === 'Tutorial';
      const defaultX1 = isTutorial ? 142.774 : cropL + (cropR - cropL) * 0.25;
      const defaultX2 = isTutorial ? 2859.777 : cropL + (cropR - cropL) * 0.75;
      const defaultY = isTutorial ? 2040 : cropT + (cropB - cropT) * 0.5;

      let x1 = saved?.x1 ?? defaultX1;
      let y1 = saved?.y1 ?? defaultY;
      let x2 = saved?.x2 ?? defaultX2;
      let y2 = saved?.y2 ?? defaultY;

      x1 = Math.max(cropL, Math.min(cropR, x1));
      y1 = Math.max(cropT, Math.min(cropB, y1));
      x2 = Math.max(cropL, Math.min(cropR, x2));
      y2 = Math.max(cropT, Math.min(cropB, y2));

      measure.loadLine({ x1, y1, x2, y2 });

      // If there's no scale yet, initialize a default one (6 inches)
      if (!project.patternScale) {
        const px = Math.hypot(x2 - x1, y2 - y1);
        onPatternScaleChange({
          pxPerUnit: px / 6,
          unit: 'in',
          line: { x1, y1, x2, y2 }
        });
      }
    }
    onChangeActiveTool(id);
  }

  function handleMeasureDragEnd(nx1: number, ny1: number, nx2: number, ny2: number) {
    if (!project.patternScale) return;
    const oldLine = project.patternScale.line;
    const oldPx = Math.hypot(oldLine.x2 - oldLine.x1, oldLine.y2 - oldLine.y1);
    const newPx = Math.hypot(nx2 - nx1, ny2 - ny1);
    const newPxPerUnit = oldPx > 0 ? (newPx / oldPx) * project.patternScale.pxPerUnit : project.patternScale.pxPerUnit;
    onPatternScaleChange({
      ...project.patternScale,
      pxPerUnit: newPxPerUnit,
      line: { x1: nx1, y1: ny1, x2: nx2, y2: ny2 }
    });
  }

  const isPanActive = activeTool === 'pan' || isSpaceDown;
  const containerCursor = isPanActive 
    ? (vp.isPanning ? 'grabbing' : 'grab') 
    : refineMode === 'add' 
      ? 'crosshair' 
      : refineMode === 'remove' 
        ? 'no-drop' 
        : activeTool === 'box' 
          ? 'crosshair' 
          : activeTool === 'polygon' || activeTool === 'pen'
            ? 'crosshair'
            : 'default';
  const es = vp.effectiveScale;
  const measurePxLength = measure.line
    ? Math.hypot(measure.line.x2 - measure.line.x1, measure.line.y2 - measure.line.y1)
    : 0;

  function setCursor(cursor: string) {
    if (vp.containerRef.current) vp.containerRef.current.style.cursor = cursor;
  }

  const BASE_TOOLS = useMemo(() => [
    {
      id: 'select' as ToolId,
      label: t('toolSelect'),
      icon: <SelectIcon />,
      tooltip: {
        name: t('tooltipSelectName'),
        shortcut: 'V',
        description: t('tooltipSelectDescPattern'),
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
      id: 'box' as ToolId,
      label: t('toolDrawBox'),
      icon: <BoxIcon />,
      tooltip: {
        name: t('tooltipBoxName'),
        shortcut: 'B',
        description: t('tooltipBoxDesc'),
        animation: <BoxAnimation />,
      },
    },
    {
      id: 'polygon' as ToolId,
      label: t('toolDrawPolygon'),
      icon: <PolygonIcon />,
      tooltip: {
        name: t('tooltipPolygonName'),
        shortcut: 'Shift+P',
        description: t('tooltipPolygonDesc'),
        animation: <PolygonAnimation />,
      },
    },
    {
      id: 'pen' as ToolId,
      label: t('toolDrawPen'),
      icon: <PenIcon />,
      tooltip: {
        name: t('tooltipPenName'),
        shortcut: 'P',
        description: t('tooltipPenDesc'),
        animation: <PenAnimation />,
      },
    },
    {
      id: 'pencil' as ToolId,
      label: t('toolDrawPencil'),
      icon: <PencilIcon />,
      tooltip: {
        name: t('tooltipPencilName'),
        shortcut: 'N',
        description: t('tooltipPencilDesc'),
        animation: <PencilAnimation />,
      },
    },
    {
      id: 'detect-all' as ToolId,
      label: t('toolDetectAll'),
      icon: <DetectAllIcon />,
      tooltip: {
        name: t('tooltipDetectAllName'),
        shortcut: '',
        description: t('tooltipDetectAllDesc'),
        animation: <DetectAllAnimation />,
      },
    },
    {
      id: 'crop' as ToolId,
      label: t('toolCropPattern'),
      icon: <CropIcon />,
      tooltip: {
        name: t('tooltipCropPatternName'),
        shortcut: 'C',
        description: t('tooltipCropPatternDesc'),
        animation: <CropAnimation />,
      },
    },
    {
      id: 'measure' as ToolId,
      label: t('toolScalePattern'),
      icon: <MeasureIcon />,
      tooltip: {
        name: t('tooltipScaleName'),
        shortcut: 'M',
        description: t('tooltipScaleDescPattern'),
        animation: <MeasureAnimation />,
      },
    },
    {
      id: 'inspect' as ToolId,
      label: t('toolInspect'),
      icon: <ViewIcon />,
      tooltip: {
        name: t('tooltipInspectName'),
        shortcut: 'I',
        description: t('tooltipInspectDesc'),
        animation: <InspectAnimation />,
      },
    },
  ], [t]);

  const TOOLS = [...BASE_TOOLS]
    .filter(tool => (!IS_TOUCH || tool.id !== 'pan') && (isTraceMode || !TRACE_ONLY_TOOL_IDS.has(tool.id)))
    .sort((a, b) => Number(TRACE_ONLY_TOOL_IDS.has(a.id)) - Number(TRACE_ONLY_TOOL_IDS.has(b.id)))
    .map(tool => {
    const sectionedTool = tool.id === 'box' ? { ...tool, sectionStart: true } : tool;
    if (tool.id === 'box') return { ...sectionedTool, disabled: !!isEncoding, loading: isEncoding ? (downloadProgress ?? true) : false };
    if (tool.id === 'detect-all') return { ...sectionedTool, disabled: !!isAutoSegmenting || !onAutoSegment || !!isEncoding, loading: isAutoSegmenting ? true : (isEncoding ? (downloadProgress ?? true) : false) };
    return sectionedTool;
  });

  return (
    <div
      className="result-panel-inner"
      data-tutorial-panel="pattern"
      style={{ display: 'flex', flex: 1, minHeight: 0 }}
      onPointerEnter={() => { isPointerInsideRef.current = true; }}
      onPointerLeave={() => { isPointerInsideRef.current = false; }}
    >
      <Toolbar tools={TOOLS} activeTool={activeTool} onSelectTool={handleToolChange}>
        <div className="toolbar-divider" />
        <div className="tooltip-wrapper snap-tooltip-wrapper" ref={snapMenuRef}>
          <button
            type="button"
            className={`tool-btn ${snapMenuOpen ? 'active' : ''}`}
            aria-haspopup="dialog"
            aria-expanded={snapMenuOpen}
            aria-label={t('snapSettings')}
            onClick={() => setSnapMenuOpen(open => !open)}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M6 7v5a6 6 0 0 0 12 0V7" />
              <rect x="3.5" y="3.5" width="5" height="4" rx="0.75" fill="currentColor" stroke="none" />
              <rect x="15.5" y="3.5" width="5" height="4" rx="0.75" fill="currentColor" stroke="none" />
              {!snapEnabled && <path d="M4 4l16 16" />}
            </svg>
            <span className="tool-label">{t('snap')}</span>
          </button>
          {!snapMenuOpen && (
            <ToolTooltip
              name={t('snap')}
              shortcut="Ctrl"
              description={t('snapToggleHint')}
              animation={<SnappingAnimation />}
            />
          )}
          {snapMenuOpen && (
            <div className="snap-settings-popover" role="dialog" aria-label={t('snapSettings')} onPointerDown={event => event.stopPropagation()}>
              <strong>{t('snapSettings')}</strong>
              <label className="snap-master-toggle">
                <input
                  type="checkbox"
                  checked={snapEnabled}
                  onChange={event => setSnapEnabled(event.target.checked)}
                />
                <span>{t('snapToggle')}</span>
              </label>
              {([
                ['anchors', 'snapAnchors'],
                ['edges', 'snapEdges'],
                ['alignment', 'snapAlignment'],
                ['canvas', 'snapCanvas'],
                ['equalLength', 'snapEqualLength'],
              ] as const).map(([setting, label]) => (
                <label key={setting} className={!snapEnabled ? 'snap-setting-disabled' : undefined}>
                  <input
                    type="checkbox"
                    checked={snapSettings[setting]}
                    disabled={!snapEnabled}
                    onChange={event => setSnapSettings(current => ({ ...current, [setting]: event.target.checked }))}
                  />
                  <span>{t(label)}</span>
                </label>
              ))}
              <small>{t('snapBypassHint')}</small>
            </div>
          )}
        </div>
        <div className="toolbar-divider" />
        <div className="tooltip-wrapper" ref={solderPopoverRef}>
          <button
            className={`tool-btn solder-tool-btn ${isSolderPopoverOpen ? 'active' : ''}`}
            onClick={() => setIsSolderPopoverOpen(o => !o)}
            aria-label={t('solderThicknessTooltip')}
          >
            {/* Custom line thickness stack icon */}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="4" y1="6" x2="20" y2="6" strokeWidth="1" />
              <line x1="4" y1="12" x2="20" y2="12" strokeWidth="2.5" />
              <line x1="4" y1="18" x2="20" y2="18" strokeWidth="4.5" />
            </svg>
            <span className="tool-label" style={{ fontSize: '9px', fontWeight: 600, marginTop: '2px' }}>
              {(project.solderWidthMM ?? 4.5).toFixed(1)}
            </span>
          </button>
          
          {!isSolderPopoverOpen && (
            <ToolTooltip
              name={t('tooltipSolderName')}
              shortcut=""
              description={t('solderThicknessTooltip')}
              animation={<SolderAnimation />}
            />
          )}
          
          {isSolderPopoverOpen && (
            <div className="solder-popover">
              <div className="solder-popover-section">
                <div className="solder-popover-label-row">
                  <span className="solder-popover-title">{t('solderThickness')}</span>
                  <span className="solder-popover-val">{(project.solderWidthMM ?? 4.5).toFixed(1)} mm</span>
                </div>
                <input
                  type="range"
                  min="1.0"
                  max="10.0"
                  step="0.5"
                  value={project.solderWidthMM ?? 4.5}
                  onChange={e => onUpdateSolderWidthMM(parseFloat(e.target.value))}
                  className="solder-popover-slider"
                />
              </div>
              <div className="solder-popover-divider" />
              <div className="solder-popover-section">
                <span className="solder-popover-title" style={{ marginBottom: '8px', display: 'block' }}>{t('solderFinish')}</span>
                <div className="solder-swatches">
                  {(['black', 'silver', 'copper'] as const).map(color => {
                    const active = (project.solderColor ?? 'black') === color;
                    const hexColor = SOLDER_COLORS[color];
                    const label = t(`solder${color.charAt(0).toUpperCase() + color.slice(1)}`);
                    return (
                      <button
                        key={color}
                        type="button"
                        className={`solder-swatch-btn ${active ? 'active' : ''}`}
                        onClick={() => onUpdateSolderColor(color)}
                        title={label}
                        aria-label={label}
                        style={{
                          '--swatch-color': hexColor,
                        } as React.CSSProperties}
                      >
                        <span className="solder-swatch-circle" />
                        <span className="solder-swatch-label">{label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>
        {project.projectType === 'lamp' && onToggleSymmetry && (
          <>
            <div className="toolbar-divider" />
            <div className="tooltip-wrapper">
              <button
                className={`tool-btn ${isSymmetryEnabled ? 'active' : ''}`}
                onClick={() => onToggleSymmetry(!isSymmetryEnabled)}
                aria-label={t('lampSymmetryTooltip')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="3" x2="12" y2="21" strokeDasharray="3 2" />
                  <path d="M 5,7 L 10,12 L 5,17 Z" />
                  <path d="M 19,7 L 14,12 L 19,17 Z" />
                </svg>
              </button>
              <ToolTooltip
                name={t('tooltipSymmetryName')}
                shortcut=""
                description={t('lampSymmetryTooltip')}
                animation={<SymmetryAnimation />}
              />
            </div>
          </>
        )}
        {onOpenLampProfile && (
          <>
            <div className="toolbar-divider" />
            <div className="tooltip-wrapper">
              <button
                className="tool-btn"
                onClick={onOpenLampProfile}
                aria-label={t('lampProfileButtonTooltip')}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <ellipse cx="12" cy="5" rx="6" ry="2" />
                  <path d="M6 5 L4 19" />
                  <path d="M18 5 L20 19" />
                  <ellipse cx="12" cy="19" rx="8" ry="2.5" />
                </svg>
              </button>
              <ToolTooltip
                name={t('tooltipProfileName')}
                shortcut=""
                description={t('lampProfileButtonTooltip')}
                animation={<ProfileAnimation />}
              />
            </div>
          </>
        )}
      </Toolbar>
      <div
        ref={vp.containerRef}
        className="canvas-well"
        style={{ flex: 1, overflow: 'hidden', cursor: containerCursor, position: 'relative', display: 'flex', flexDirection: 'column', touchAction: 'none' }}
      >
        {!project.patternImageUrl && !project.patternScale ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-soft)', padding: 40, textAlign: 'center' }}>
            <div style={{ maxWidth: 800 }}>
              <p style={{ fontFamily: '"Instrument Serif", Georgia, serif', fontSize: '2rem', fontWeight: 400, color: 'var(--text-bright)', marginBottom: 32 }}>What would you like to build?</p>
              
              <div className="onboarding-grid">
                <label className="onboarding-card">
                  <div className="onboarding-card-icon">
                    <IconUpload size={28} />
                  </div>
                  <h3>Trace an Image</h3>
                  <p>Upload a 2D pattern image to trace stained glass pieces over.</p>
                  <input type="file" accept="image/*" style={{ display: 'none' }} onChange={onUploadPattern} />
                </label>

                <button className="onboarding-card" onClick={onStartBlankCanvas}>
                  <div className="onboarding-card-icon">
                    <IconSquare size={28} />
                  </div>
                  <h3>Blank Flat Canvas</h3>
                  <p>Start with a blank workspace to draw a flat window from scratch.</p>
                </button>

                {onStartLampMode && (
                  <button className="onboarding-card" onClick={onStartLampMode}>
                    <div className="onboarding-card-icon">
                      <IconLamp size={28} />
                    </div>
                    <h3>3D Lamp Shade</h3>
                    <p>Design a 3D lamp, draw patterns across its facets, and preview in real-time.</p>
                  </button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <>
            <Stage
              width={vp.dims.w} height={vp.dims.h}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerCancel}
              onPointerLeave={() => {
                if (activeTool === 'polygon' || activeTool === 'pen') {
                  setHoverPoint(null);
                  setActiveSnapLabels([]);
                }
              }}
              onContextMenu={e => e.evt.preventDefault()}
            >
              <Layer>
                <Group
                  x={vp.pan.x} y={vp.pan.y}
                  scaleX={es} scaleY={es}
                  {...(activeTool === 'crop' ? {} : {
                    clipX: project.patternCrop.left,
                    clipY: project.patternCrop.top,
                    clipWidth: Math.max(1, pw - project.patternCrop.left - project.patternCrop.right),
                    clipHeight: Math.max(1, ph - project.patternCrop.top - project.patternCrop.bottom),
                  })}
                >
                  {isLamp && unrolledLamp && unrolledLamp.mode === 'faceted' && unrolledLamp.strips.length > 0 ? (
                    <>
                      {unrolledLamp.strips.map((strip, si) => (
                        <Line
                          key={`strip-poly-${si}`}
                          points={strip.outline.flat()}
                          closed
                          fill="#fffefa"
                          stroke="rgba(40, 30, 15, 0.32)"
                          strokeWidth={1.5 / es}
                          listening={false}
                        />
                      ))}
                      {unrolledLamp.strips.map((strip, si) =>
                        strip.tierSeams.map((s, i) => (
                          <Line
                            key={`tierseam-${si}-${i}`}
                            points={[s.x1, s.y1, s.x2, s.y2]}
                            stroke="rgba(40, 30, 15, 0.18)"
                            strokeWidth={0.8 / es}
                            listening={false}
                          />
                        ))
                      )}
                    </>
                  ) : isLamp && unrolledLamp && unrolledLamp.mode === 'smooth' && unrolledLamp.tiers.length > 0 ? (
                    <>
                      {unrolledLamp.tiers.map((tier, ti) => (
                        <Line
                          key={`smooth-tier-${ti}`}
                          points={tier.outline.flat()}
                          closed
                          fill="#fffefa"
                          stroke="rgba(40, 30, 15, 0.32)"
                          strokeWidth={1.5 / es}
                          listening={false}
                        />
                      ))}
                    </>
                  ) : (() => {
                    const cL = project.patternCrop.left;
                    const cT = project.patternCrop.top;
                    const cR = project.patternCrop.right;
                    const cB = project.patternCrop.bottom;
                    const ux = Math.min(0, cL);
                    const uy = Math.min(0, cT);
                    const uw = Math.max(pw, pw - cR) - ux;
                    const uh = Math.max(ph, ph - cB) - uy;
                    return (
                      <Rect
                        x={ux} y={uy}
                        width={uw} height={uh}
                        fill="#fffefa"
                        listening={false}
                      />
                    );
                  })()}
                  {!isLamp && patternImg && (
                    <KonvaImage
                      id="bg"
                      image={patternImg}
                      width={pw} height={ph}
                      opacity={activeTool === 'box' ? 0.5 : 1}
                    />
                  )}
                  {activeTool !== 'inspect' && project.pieces.map(piece => {
                    const sheet = sheetMap[piece.glassSheetId];
                    const isSelected = selectedPieceIdSet.has(piece.id);
                    // Corner drag: override polygon directly (activeDragPolygon)
                    const basePolygon = (isSelected && activeDragPolygon) ? activeDragPolygon : piece.polygon;
                    // Midpoint drag: override curvePoints (activeDragCurvePoints); polygon stays clean
                    const baseCurves = (isSelected && activeDragCurvePoints) ? activeDragCurvePoints : piece.curvePoints;
                    const geometry = getPieceGeometry(basePolygon, baseCurves);
                    return (
                      <PieceOverlay
                        key={piece.id}
                        piece={piece}
                        geometry={geometry}
                        glassImageUrl={sheet?.imageUrl ?? ''}
                        isSelected={isSelected}
                        isPending={pendingPieceIds.has(piece.id)}
                        solderWidth={solderWidth}
                        solderColor={SOLDER_COLORS[project.solderColor ?? 'black'] ?? SOLDER_COLORS.black}
                        onSelectPiece={onSelectPiece}
                        selectionDisabled={Boolean(refineMode)}
                      />
                    );
                  })}
                  {debugMask && activeTool === 'box' && (
                    <KonvaImage
                      image={debugMask.bitmap as unknown as HTMLImageElement}
                      x={0} y={0}
                      width={debugMask.width} height={debugMask.height}
                      listening={false}
                      globalCompositeOperation="difference"
                    />
                  )}
                  {activeTool === 'polygon' && (activePolygonPoints.length > 0 || hoverPoint) && (
                    <Group>
                      {/* Alignment Guides */}
                      {activeAlignmentGuides.map((guide, idx) => (
                        <Group key={`align-guide-${idx}`} listening={false}>
                          <Line
                            points={[guide.from[0], guide.from[1], guide.to[0], guide.to[1]]}
                            stroke="rgba(192, 138, 31, 0.4)"
                            strokeWidth={1 / es}
                            dash={[4 / es, 4 / es]}
                          />
                          <Circle
                            x={guide.from[0]}
                            y={guide.from[1]}
                            radius={4.5 / es}
                            fill={CANVAS.paper}
                            stroke={CANVAS.amber}
                            strokeWidth={1.5 / es}
                          />
                        </Group>
                      ))}

                      {/* Equal Length Guide */}
                      {activeLengthGuide && (
                        <Group listening={false}>
                          <Circle
                            x={activeLengthGuide.center[0]}
                            y={activeLengthGuide.center[1]}
                            radius={activeLengthGuide.matchLength}
                            stroke="rgba(192, 138, 31, 0.25)"
                            strokeWidth={1.5 / es}
                            dash={[6 / es, 6 / es]}
                          />
                          <Line
                            points={[
                              activeLengthGuide.matchingSegment.p1[0],
                              activeLengthGuide.matchingSegment.p1[1],
                              activeLengthGuide.matchingSegment.p2[0],
                              activeLengthGuide.matchingSegment.p2[1],
                            ]}
                            stroke={CANVAS.amber}
                            strokeWidth={4 / es}
                            lineCap="round"
                            opacity={0.8}
                          />
                        </Group>
                      )}

                      {activePolygonPoints.length > 1 && (
                        <Line
                          points={activePolygonPoints.flat()}
                          stroke={CANVAS.amber}
                          strokeWidth={2.5 / es}
                          lineJoin="round"
                          lineCap="round"
                        />
                      )}
                      {hoverPoint && activePolygonPoints.length > 0 && (
                        <Line
                          points={[activePolygonPoints[activePolygonPoints.length - 1], hoverPoint].flat()}
                          stroke={CANVAS.amber}
                          strokeWidth={2.5 / es}
                          dash={[4 / es, 4 / es]}
                        />
                      )}
                      {hoverPoint && hoverSnapped && (
                        <Circle
                          x={hoverPoint[0]}
                          y={hoverPoint[1]}
                          radius={6 / es}
                          fill={CANVAS.amber}
                          stroke={CANVAS.paper}
                          strokeWidth={2 / es}
                        />
                      )}
                      {activePolygonPoints.map(([x, y], idx) => {
                        const isStart = idx === 0;
                        const isCloseEnough = isStart && hoverPoint && (Math.hypot(hoverPoint[0] - x, hoverPoint[1] - y) * es < 15);
                        return (
                          <Circle
                            key={idx}
                            x={x}
                            y={y}
                            radius={(isStart ? (isCloseEnough ? 8 : 6) : 4.5) / es}
                            fill={isStart ? (isCloseEnough ? CANVAS.patternPending : CANVAS.amber) : CANVAS.paper}
                            stroke={CANVAS.amber}
                            strokeWidth={2 / es}
                            shadowColor="#000"
                            shadowBlur={3}
                            shadowOpacity={0.2}
                            onMouseEnter={(e) => {
                              const stage = e.target.getStage();
                              if (stage) stage.container().style.cursor = 'pointer';
                            }}
                            onMouseLeave={(e) => {
                              const stage = e.target.getStage();
                              if (stage) stage.container().style.cursor = containerCursor;
                            }}
                          />
                        );
                      })}

                      {/* Snap Labels (Center, 1/3, etc.) */}
                      {hoverPoint && activeSnapLabels.length > 0 && (
                        <Group x={hoverPoint[0]} y={hoverPoint[1] - 18 / es} listening={false}>
                          {(() => {
                            const text = activeSnapLabels.join(' · ');
                            const fontSize = 10.5 / es;
                            const textWidth = text.length * (6 / es);
                            const paddingX = 6 / es;
                            const paddingY = 3.5 / es;
                            const rectW = textWidth + paddingX * 2;
                            const rectH = fontSize + paddingY * 2;
                            return (
                              <Group>
                                <Rect
                                  x={-rectW / 2}
                                  y={-rectH / 2}
                                  width={rectW}
                                  height={rectH}
                                  fill="rgba(40, 30, 15, 0.85)"
                                  cornerRadius={4 / es}
                                />
                                <KonvaText
                                  text={text}
                                  fontSize={fontSize}
                                  fontFamily='"Inter Tight", system-ui, -apple-system, sans-serif'
                                  fill="#fffefa"
                                  align="center"
                                  verticalAlign="middle"
                                  x={-rectW / 2}
                                  y={-rectH / 2}
                                  width={rectW}
                                  height={rectH}
                                />
                              </Group>
                            );
                          })()}
                        </Group>
                      )}
                    </Group>
                  )}
                  {activeTool === 'pen' && (activePenAnchors.length > 0 || hoverPoint) && (
                    <Group>
                      {activeAlignmentGuides.map((guide, idx) => (
                        <Line
                          key={`pen-guide-${idx}`}
                          points={[guide.from[0], guide.from[1], guide.to[0], guide.to[1]]}
                          stroke="rgba(192, 138, 31, 0.45)"
                          strokeWidth={1 / es}
                          dash={[4 / es, 4 / es]}
                          listening={false}
                        />
                      ))}
                      {activePenAnchors.length > 1 && (
                        <Line
                          points={flattenOpenPenPath(activePenAnchors, es).flat()}
                          stroke={CANVAS.amber}
                          strokeWidth={2.5 / es}
                          lineJoin="round"
                          lineCap="round"
                          listening={false}
                        />
                      )}
                      {hoverPoint && activePenAnchors.length > 0 && penDragIndex === null && (
                        <Line
                          points={[activePenAnchors[activePenAnchors.length - 1].point, hoverPoint].flat()}
                          stroke={CANVAS.amber}
                          strokeWidth={2.5 / es}
                          dash={[4 / es, 4 / es]}
                          listening={false}
                        />
                      )}
                      {activePenAnchors.map((anchor, index) => {
                        const isStart = index === 0;
                        const isClose = isStart && hoverPoint && Math.hypot(
                          hoverPoint[0] - anchor.point[0], hoverPoint[1] - anchor.point[1],
                        ) * es < 15;
                        return (
                          <Group key={`pen-anchor-${index}`}>
                            {anchor.in && (
                              <>
                                <Line
                                  points={[anchor.in[0], anchor.in[1], anchor.point[0], anchor.point[1]]}
                                  stroke={CANVAS.amberHandleStem}
                                  strokeWidth={1.25 / es}
                                  listening={false}
                                />
                                <Circle x={anchor.in[0]} y={anchor.in[1]} radius={3.5 / es} fill={CANVAS.paper} stroke={CANVAS.amber} strokeWidth={1.25 / es} listening={false} />
                              </>
                            )}
                            {anchor.out && (
                              <>
                                <Line
                                  points={[anchor.point[0], anchor.point[1], anchor.out[0], anchor.out[1]]}
                                  stroke={CANVAS.amberHandleStem}
                                  strokeWidth={1.25 / es}
                                  listening={false}
                                />
                                <Circle x={anchor.out[0]} y={anchor.out[1]} radius={3.5 / es} fill={CANVAS.paper} stroke={CANVAS.amber} strokeWidth={1.25 / es} listening={false} />
                              </>
                            )}
                            <Rect
                              x={anchor.point[0] - (isStart ? 5 : 4) / es}
                              y={anchor.point[1] - (isStart ? 5 : 4) / es}
                              width={(isStart ? 10 : 8) / es}
                              height={(isStart ? 10 : 8) / es}
                              fill={isStart ? (isClose ? CANVAS.patternPending : CANVAS.amber) : CANVAS.paper}
                              stroke={CANVAS.amber}
                              strokeWidth={1.75 / es}
                            />
                          </Group>
                        );
                      })}
                    </Group>
                  )}
                  {activeTool === 'pencil' && pencilPoints.length > 0 && (
                    <Line
                      points={pencilPoints.flat()}
                      stroke={CANVAS.amber}
                      strokeWidth={2.5 / es}
                      lineJoin="round"
                      lineCap="round"
                      dash={[4 / es, 3 / es]}
                    />
                  )}
                  {marqueeBox && (
                    <Rect
                      x={Math.min(marqueeBox.x1, marqueeBox.x2)}
                      y={Math.min(marqueeBox.y1, marqueeBox.y2)}
                      width={Math.abs(marqueeBox.x2 - marqueeBox.x1)}
                      height={Math.abs(marqueeBox.y2 - marqueeBox.y1)}
                      fill={CANVAS.amberSelectionFill}
                      stroke={CANVAS.amber}
                      strokeWidth={1.5 / es}
                      dash={[4 / es, 2 / es]}
                      listening={false}
                    />
                  )}
                  {activeTool === 'crop' && (
                    <CropOverlay
                      imageWidth={pw} imageHeight={ph}
                      crop={project.patternCrop}
                      effectiveScale={es}
                      onCropChange={onPatternCropChange}
                    />
                  )}
                  {activeTool === 'box' && drawingBox && (
                    <Rect
                      x={Math.min(drawingBox.x1, drawingBox.x2)}
                      y={Math.min(drawingBox.y1, drawingBox.y2)}
                      width={Math.abs(drawingBox.x2 - drawingBox.x1)}
                      height={Math.abs(drawingBox.y2 - drawingBox.y1)}
                      stroke={CANVAS.drawingBoxStroke}
                      strokeWidth={2 / es}
                      fill={CANVAS.drawingBoxFill}
                      dash={[6 / es, 4 / es]}
                      listening={false}
                    />
                  )}
                  {tutorialStep === 'cut-first-piece' && project.pieces.length === 0 && (
                    <Rect
                      x={924.124254866509}
                      y={1487.1442620225096}
                      width={2505.188986758742 - 924.124254866509}
                      height={2998.9258239124047 - 1487.1442620225096}
                      stroke="#fbbf24"
                      strokeWidth={3 / es}
                      dash={[10 / es, 6 / es]}
                      dashOffset={dashOffset}
                      fill="rgba(251, 191, 36, 0.05)"
                      listening={false}
                    />
                  )}
                  {tutorialStep === 'cut-second-piece' && project.pieces.length <= 1 && (
                    <Rect
                      x={364.7371555449281}
                      y={1249.5130966562972}
                      width={1264.3137687154938 - 364.7371555449281}
                      height={2725.2637575643917 - 1249.5130966562972}
                      stroke="#fbbf24"
                      strokeWidth={3 / es}
                      dash={[10 / es, 6 / es]}
                      dashOffset={dashOffset}
                      fill="rgba(251, 191, 36, 0.05)"
                      listening={false}
                    />
                  )}
                  {(() => {
                    const lastId = selectedPieceIds[selectedPieceIds.length - 1];
                    const piece = project.pieces.find(p => p.id === lastId);
                    if (piece?.promptBox) {
                      return (
                        <Rect
                          x={piece.promptBox.x1}
                          y={piece.promptBox.y1}
                          width={piece.promptBox.x2 - piece.promptBox.x1}
                          height={piece.promptBox.y2 - piece.promptBox.y1}
                          stroke={CANVAS.promptBoxStroke}
                          strokeWidth={1 / es}
                          dash={[4 / es, 6 / es]}
                          listening={false}
                        />
                      );
                    }
                    return null;
                  })()}
                  {project.pieces.map(piece => {
                    if (!selectedPieceIdSet.has(piece.id) || !piece.promptPoints) return null;
                    return piece.promptPoints.map((pt, i) => (
                      <Circle
                        key={i}
                        x={pt.x} y={pt.y}
                        radius={5 / es}
                        fill={pt.label === 1 ? CANVAS.amber : CANVAS.ruby}
                        listening={false}
                      />
                    ));
                  })}
                  {activeTool === 'select' && selectedPieceIds.length === 1 && (() => {
                    const selectedId = selectedPieceIds[0];
                    const piece = project.pieces.find(p => p.id === selectedId);
                    if (!piece) return null;

                    const referencePolygon = dragStartPolygon || piece.polygon;
                    const len = referencePolygon.length;
                    // Min screen-space edge length to show a handle (avoids clutter on dense polygons)
                    const MIN_HANDLE_PX = 14;

                    return (
                      <Group>
                        {/* Corner handles — only on edges long enough to be worth dragging */}
                        {referencePolygon.map(([x, y], idx) => {
                          // Show corner if either adjacent edge is long enough
                          if (!isStructuralCorner(referencePolygon, idx, es, MIN_HANDLE_PX) && draggedCorner?.idx !== idx) return null;

                          const currentX = (draggedCorner?.idx === idx && activeDragPolygon)
                            ? activeDragPolygon[idx][0] : x;
                          const currentY = (draggedCorner?.idx === idx && activeDragPolygon)
                            ? activeDragPolygon[idx][1] : y;

                          return (
                            <Circle
                              key={`corner-${idx}`}
                              x={currentX}
                              y={currentY}
                              radius={6 / es}
                              fill={CANVAS.paper}
                              stroke={CANVAS.amber}
                              strokeWidth={2 / es}
                              draggable
                              onDragStart={() => {
                                setDraggedCorner({ pieceId: selectedId, idx });
                                setDragStartPolygon(piece.polygon);
                                dragStartCurvePointsRef.current = piece.curvePoints ?? [];
                                setActiveDragPolygon(piece.polygon);
                              }}
                              onDragMove={(e) => {
                                if (!dragStartPolygon) return;
                                const newPolygon = [...dragStartPolygon];
                                const origin = dragStartPolygon[idx];
                                const resolved = resolveEditedAnchor(
                                  [e.target.x(), e.target.y()], origin, selectedId,
                                  e.evt.shiftKey, e.evt.ctrlKey,
                                );
                                e.target.position({ x: resolved[0], y: resolved[1] });
                                newPolygon[idx] = resolved;
                                const delta: [number, number] = [resolved[0] - origin[0], resolved[1] - origin[1]];
                                setActiveDragPolygon(newPolygon);
                                setActiveDragCurvePoints(translateCurvesWithAnchor(
                                  dragStartCurvePointsRef.current, idx, dragStartPolygon.length, delta,
                                ));
                              }}
                              onDragEnd={(e) => {
                                if (!dragStartPolygon) { setDraggedCorner(null); return; }
                                const newPolygon = [...dragStartPolygon];
                                const origin = dragStartPolygon[idx];
                                const resolved = resolveEditedAnchor(
                                  [e.target.x(), e.target.y()], origin, selectedId,
                                  e.evt.shiftKey, e.evt.ctrlKey,
                                );
                                newPolygon[idx] = resolved;
                                const delta: [number, number] = [resolved[0] - origin[0], resolved[1] - origin[1]];
                                const newCurves = translateCurvesWithAnchor(
                                  dragStartCurvePointsRef.current, idx, dragStartPolygon.length, delta,
                                );
                                onUpdatePiecePolygonAndCurves(selectedId, newPolygon, newCurves);
                                setDraggedCorner(null);
                                setDragStartPolygon(null);
                                setActiveDragPolygon(null);
                                setActiveDragCurvePoints(null);
                                setActiveAlignmentGuides([]);
                                setActiveSnapLabels([]);
                              }}
                              onMouseEnter={(e) => {
                                const stage = e.target.getStage();
                                if (stage) stage.container().style.cursor = 'move';
                              }}
                              onMouseLeave={(e) => {
                                const stage = e.target.getStage();
                                if (stage) stage.container().style.cursor = 'default';
                              }}
                              onDblClick={() => {
                                const anchorTypes = piece.anchorTypes?.length === referencePolygon.length
                                  ? [...piece.anchorTypes]
                                  : referencePolygon.map(() => 'corner' as const);
                                anchorTypes[idx] = anchorTypes[idx] === 'smooth' ? 'corner' : 'smooth';
                                onUpdatePieceCurves(selectedId, piece.curvePoints ?? [], anchorTypes);
                              }}
                            />
                          );
                        })}

                        {/* Midpoint (curve) handles — hidden while dragging a corner */}
                        {!draggedCorner && referencePolygon.map(([x, y], idx) => {
                          const idxNext = (idx + 1) % len;
                          const B = referencePolygon[idxNext];
                          const dist = Math.hypot(B[0] - x, B[1] - y) * es;
                          const isActive = draggedMidpoint?.edgeIdx === idx;
                          if (dist < MIN_HANDLE_PX && !isActive) return null;

                          // Position the handle at the bezier midpoint if a curve exists
                          const existingCurve = (activeDragCurvePoints ?? piece.curvePoints ?? []).find(cp => cp.edgeIdx === idx);
                          if (existingCurve && isCubicCurvePoint(existingCurve)) return null;
                          const existingCtrl = existingCurve?.ctrl;
                          const [hx, hy] = existingCtrl
                            ? ctrlToHandle([x, y], B, existingCtrl)
                            : [(x + B[0]) / 2, (y + B[1]) / 2];

                          return (
                            <Circle
                              key={`mid-${idx}`}
                              x={hx}
                              y={hy}
                              radius={5 / es}
                              fill={CANVAS.amber}
                              stroke={CANVAS.paper}
                              strokeWidth={1.5 / es}
                              draggable
                              onDragStart={() => {
                                setDraggedMidpoint({ pieceId: selectedId, edgeIdx: idx });
                                dragStartCurvePointsRef.current = piece.curvePoints ?? [];
                                setActiveDragCurvePoints(piece.curvePoints ?? []);
                              }}
                              onDragMove={(e) => {
                                const A: [number, number] = [x, y];
                                const ctrl = handleToCtrl(A, B, [e.target.x(), e.target.y()]);
                                const updated = dragStartCurvePointsRef.current.filter(cp => cp.edgeIdx !== idx);
                                updated.push({ edgeIdx: idx, ctrl });
                                setActiveDragCurvePoints(updated);
                              }}
                              onDragEnd={(e) => {
                                const A: [number, number] = [x, y];
                                const ctrl = handleToCtrl(A, B, [e.target.x(), e.target.y()]);
                                const updated = (piece.curvePoints ?? []).filter(cp => cp.edgeIdx !== idx);
                                updated.push({ edgeIdx: idx, ctrl });
                                onUpdatePieceCurves(selectedId, updated);
                                setDraggedMidpoint(null);
                                setActiveDragCurvePoints(null);
                              }}
                              onMouseEnter={(e) => {
                                const stage = e.target.getStage();
                                if (stage) stage.container().style.cursor = 'pointer';
                              }}
                              onMouseLeave={(e) => {
                                const stage = e.target.getStage();
                                if (stage) stage.container().style.cursor = 'default';
                              }}
                              onDblClick={() => {
                                const inserted = insertAnchorOnEdge(
                                  piece.polygon, piece.curvePoints ?? [], idx,
                                );
                                const anchorTypes = piece.anchorTypes?.length === piece.polygon.length
                                  ? [...piece.anchorTypes]
                                  : piece.polygon.map(() => 'corner' as const);
                                anchorTypes.splice(inserted.insertedAt, 0, inserted.curved ? 'smooth' : 'corner');
                                onUpdatePiecePolygonAndCurves(
                                  selectedId, inserted.polygon, inserted.curves, anchorTypes,
                                );
                              }}
                            />
                          );
                        })}

                        {/* Conventional cubic direction handles. Shift constrains
                            the handle angle; Alt/Option breaks the paired handle. */}
                        {!draggedCorner && (activeDragCurvePoints ?? piece.curvePoints ?? []).map(curve => {
                          if (!isCubicCurvePoint(curve)) return null;
                          const edgeIdx = curve.edgeIdx;
                          const nextIdx = (edgeIdx + 1) % len;
                          const A = referencePolygon[edgeIdx];
                          const B = referencePolygon[nextIdx];
                          const [ctrl1, ctrl2] = curveToCubicControls(A, B, curve);
                          const midpoint = evaluateCubicBezier(A, ctrl1, ctrl2, B, 0.5);

                          const renderHandle = (side: 'ctrl' | 'ctrl2', handle: [number, number], anchor: [number, number]) => (
                            <Group key={`cubic-${edgeIdx}-${side}`}>
                              <Line
                                points={[anchor[0], anchor[1], handle[0], handle[1]]}
                                stroke={CANVAS.amberHandleStem}
                                strokeWidth={1.25 / es}
                                listening={false}
                              />
                              <Circle
                                x={handle[0]}
                                y={handle[1]}
                                radius={4 / es}
                                fill={CANVAS.paper}
                                stroke={CANVAS.amber}
                                strokeWidth={1.5 / es}
                                draggable
                                onDragStart={() => {
                                  dragStartCurvePointsRef.current = activeDragCurvePoints ?? piece.curvePoints ?? [];
                                  setActiveDragCurvePoints(dragStartCurvePointsRef.current);
                                }}
                                onDragMove={(e) => {
                                  let point: [number, number] = [e.target.x(), e.target.y()];
                                  if (e.evt.shiftKey) point = constrainToAngle(point, anchor);
                                  e.target.position({ x: point[0], y: point[1] });
                                  const anchorIdx = side === 'ctrl' ? edgeIdx : nextIdx;
                                  const isCorner = piece.anchorTypes?.[anchorIdx] === 'corner';
                                  setActiveDragCurvePoints(moveCubicHandle(
                                    dragStartCurvePointsRef.current, referencePolygon, edgeIdx, side, point, e.evt.altKey || isCorner,
                                  ));
                                }}
                                onDragEnd={(e) => {
                                  let point: [number, number] = [e.target.x(), e.target.y()];
                                  if (e.evt.shiftKey) point = constrainToAngle(point, anchor);
                                  const anchorIdx = side === 'ctrl' ? edgeIdx : nextIdx;
                                  const isCorner = piece.anchorTypes?.[anchorIdx] === 'corner';
                                  const updated = moveCubicHandle(
                                    dragStartCurvePointsRef.current, referencePolygon, edgeIdx, side, point, e.evt.altKey || isCorner,
                                  );
                                  const anchorTypes = piece.anchorTypes?.length === referencePolygon.length
                                    ? [...piece.anchorTypes]
                                    : referencePolygon.map((_, index) => {
                                      const hasCubic = updated.some(item => isCubicCurvePoint(item) && (item.edgeIdx === index || (item.edgeIdx + 1) % len === index));
                                      return hasCubic ? 'smooth' as const : 'corner' as const;
                                    });
                                  if (e.evt.altKey) anchorTypes[anchorIdx] = 'corner';
                                  onUpdatePieceCurves(selectedId, updated, anchorTypes);
                                  setActiveDragCurvePoints(null);
                                }}
                              />
                            </Group>
                          );

                          return (
                            <Group key={`cubic-edge-${edgeIdx}`}>
                              <Circle
                                x={midpoint[0]}
                                y={midpoint[1]}
                                radius={3 / es}
                                fill={CANVAS.amber}
                                opacity={0.55}
                                onDblClick={() => {
                                  const inserted = insertAnchorOnEdge(
                                    piece.polygon, piece.curvePoints ?? [], edgeIdx,
                                  );
                                  const anchorTypes = piece.anchorTypes?.length === piece.polygon.length
                                    ? [...piece.anchorTypes]
                                    : piece.polygon.map(() => 'corner' as const);
                                  anchorTypes.splice(inserted.insertedAt, 0, 'smooth');
                                  onUpdatePiecePolygonAndCurves(
                                    selectedId, inserted.polygon, inserted.curves, anchorTypes,
                                  );
                                }}
                              />
                              {renderHandle('ctrl', ctrl1, A)}
                              {renderHandle('ctrl2', ctrl2, B)}
                            </Group>
                          );
                        })}
                      </Group>
                    );
                  })()}
                  {activeTool === 'measure' && measure.line && (
                    <MeasureLineOverlay
                      line={measure.line}
                      effectiveScale={es}
                      imageWidth={pw} imageHeight={ph}
                      onUpdateP1={measure.updateP1}
                      onUpdateP2={measure.updateP2}
                      onDragEnd={handleMeasureDragEnd}
                      onCursorChange={setCursor}
                    />
                  )}
                </Group>
              </Layer>
            </Stage>
            <ViewportControls
              zoomPercent={vp.effectiveScale * 100}
              onZoomIn={vp.zoomIn}
              onZoomOut={vp.zoomOut}
              onFit={vp.fitToView}
              onActualSize={vp.zoomToActualSize}
            />
            {activeTool === 'measure' && measure.line && (() => {
              const midX = (measure.line.x1 + measure.line.x2) / 2;
              const midY = (measure.line.y1 + measure.line.y2) / 2;
              const sc = toScreenCoords(midX, midY, vp.pan, vp.effectiveScale);
              const saved = project.patternScale;
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
            })()}
            {activeTool !== 'inspect' && (() => {
              if (selectedPieceIds.length === 0) return null;
              
              const isMultiple = selectedPieceIds.length > 1;
              const lastId = selectedPieceIds[selectedPieceIds.length - 1];
              const piece = project.pieces.find(p => p.id === lastId);
              if (!piece) return null;
              
              // For multiple selection, we construct a dummy piece for PieceProperties
              const displayPiece = isMultiple ? {
                ...piece,
                id: '__multiple__',
                label: t('pieces', { count: selectedPieceIds.length }),
                // If all selected pieces share the same sheet, show it; otherwise, use a special value
                glassSheetId: project.pieces.filter(p => selectedPieceIdSet.has(p.id))
                  .every((p, _, arr) => p.glassSheetId === arr[0].glassSheetId) 
                    ? piece.glassSheetId 
                    : '__multiple__'
              } : piece;

              const isDrawing = drawingBox !== null
                || pencilPoints.length > 0
                || (activeTool === 'polygon' && activePolygonPoints.length > 0)
                || (activeTool === 'pen' && activePenAnchors.length > 0)
                || draggedCorner !== null
                || draggedMidpoint !== null;
              const isInteracting = isDrawing || marqueeBox !== null || vp.isPanning || isSpaceDown;

              return (
                <div style={{
                  position: 'absolute',
                  right: 12 - tooltipDrag.x,
                  top: 12 + tooltipDrag.y,
                  zIndex: 10,
                  maxWidth: 'calc(100% - 24px)',
                  pointerEvents: isInteracting ? 'none' : 'auto',
                  opacity: isInteracting ? 0 : 0.95,
                  transition: 'opacity 0.2s ease',
                }}>
                  <div style={{ pointerEvents: isInteracting ? 'none' : 'auto' }}>
                    <DragHandle 
                      onDrag={delta => setTooltipDrag(d => ({ x: d.x + delta.x, y: d.y + delta.y }))} 
                      pointerEvents={isInteracting ? 'none' : 'auto'}
                    />
                    <PieceProperties
                      piece={displayPiece}
                      sheets={project.sheets}
                      onLabelChange={label => onUpdatePieceLabel(piece.id, label)}
                      onSheetChange={sheetId => {
                        if (isMultiple) onUpdatePiecesSheet(selectedPieceIds, sheetId);
                        else onUpdatePieceSheet(piece.id, sheetId);
                      }}
                      onAddSheet={() => handleAddSheetClick(isMultiple ? '__multiple__' : piece.id)}
                      onDelete={() => {
                        if (isMultiple) onDeletePieces(selectedPieceIds);
                        else onDeletePiece(piece.id);
                      }}
                      onSmooth={() => {
                        if (isMultiple) onSmoothPieces(selectedPieceIds);
                        else onSmoothPiece(piece.id);
                      }}
                      refineMode={refineMode}
                      onRefineModeChange={onRefineModeChange}
                      isPending={selectedPieceIds.some(id => pendingPieceIds.has(id))}
                      isEncoding={isEncoding}
                      pointerEvents={isInteracting ? 'none' : 'auto'}
                      multiple={isMultiple}
                    />
                  </div>
                </div>
              );
            })()}
            <input
              type="file"
              ref={addSheetInputRef}
              style={{ display: 'none' }}
              accept="image/*"
              onChange={handleAddSheetFileChange}
            />
          </>
        )}
      </div>
    </div>
  );
}
