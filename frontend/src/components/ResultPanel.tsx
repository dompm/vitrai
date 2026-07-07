import { useState, useEffect, useRef, useMemo } from 'react';

const IS_TOUCH = typeof window !== 'undefined' && window.matchMedia('(pointer: coarse)').matches;
import { useTranslation } from 'react-i18next';
import { Stage, Layer, Image as KonvaImage, Line, Group, Rect, Circle, Text as KonvaText } from 'react-konva';
import useImage from 'use-image';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { Piece, Project, Crop, BoundingBox, Scale, CurvePoint } from '../types';
import type { StepId } from './Tutorial/types';
import { computeCentroid, flattenCurves, ctrlToHandle, handleToCtrl } from '../utils/geometry';
import { Toolbar, SelectIcon, CropIcon, MeasureIcon, BoxIcon, DetectAllIcon, ViewIcon, HandIcon, PenIcon, PencilIcon } from './Toolbar';
import { IconUpload, IconSquare, IconLamp } from './icons';
import type { ToolId } from './Toolbar';
import { SelectAnimation, BoxAnimation, CropAnimation, MeasureAnimation, DetectAllAnimation, InspectAnimation, PanAnimation, PenAnimation, PencilAnimation } from './ToolTooltipAnimations';
import { CropOverlay } from './CropOverlay';
import { MeasureInput } from './MeasureInput';
import { MeasureLineOverlay } from './MeasureLineOverlay';
import { useViewport } from '../hooks/useViewport';
import { useMeasure } from '../hooks/useMeasure';
import { toImageCoords, toScreenCoords } from '../utils/viewport';
import { PieceProperties } from './PieceProperties';
import { CANVAS } from '../theme';
import { computeUnrolledLamp, findLampEdgeSnap, getLampSnapPoints, LampSnapPoint, patternToSurfaceRobust } from '../utils/lampGeometry';
import { getSnapFractions } from '../utils/snapping';

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
  displayPolygon: [number, number][];
  glassImageUrl: string;
  isSelected: boolean;
  isPending: boolean;
  opacity?: number;
  solderWidth: number;
  solderColor: string;
  onSelect: (multi?: boolean) => void;
}

function PieceOverlay({ piece, displayPolygon, glassImageUrl, isSelected, isPending, opacity = 1, solderWidth, solderColor, onSelect }: PieceOverlayProps) {
  const [glassImg] = useImage(glassImageUrl);
  const [pulseHi, setPulseHi] = useState(false);
  useEffect(() => {
    if (!isPending) { setPulseHi(false); return; }
    const id = setInterval(() => setPulseHi(h => !h), 750);
    return () => clearInterval(id);
  }, [isPending]);
  const { x: tx, y: ty, rotation, scale } = piece.transform;
  const centroid = computeCentroid(displayPolygon);
  const flatPts = displayPolygon.flat();
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);

  function clipPolygon(ctx: any) {
    ctx.beginPath();
    displayPolygon.forEach(([x, y], i) => {
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath();
  }

  function handleClick(e: KonvaEventObject<MouseEvent>) {
    e.cancelBubble = true;
    if (longPressFired.current) { longPressFired.current = false; return; }
    onSelect(e.evt.shiftKey);
  }

  function handlePointerDown() {
    if (!IS_TOUCH) return;
    longPressFired.current = false;
    longPressTimer.current = setTimeout(() => {
      longPressFired.current = true;
      longPressTimer.current = null;
      onSelect(true);
    }, 500);
  }

  function cancelLongPress() {
    if (longPressTimer.current) { clearTimeout(longPressTimer.current); longPressTimer.current = null; }
  }

  const xs = displayPolygon.map(p => p[0]);
  const ys = displayPolygon.map(p => p[1]);

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
            x={Math.min(...xs)} y={Math.min(...ys)}
            width={Math.max(...xs) - Math.min(...xs)}
            height={Math.max(...ys) - Math.min(...ys)}
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
}

interface ResultPanelProps {
  project: Project;
  selectedPieceIds: string[];
  pendingPieceIds: ReadonlySet<string>;
  onSelectPiece: (id: string | null, multi?: boolean) => void;
  onSelectPieces: (ids: string[]) => void;
  onPatternCropChange: (c: Partial<Crop>) => void;
  onPatternScaleChange: (s: Scale | null) => void;
  onAddPiece: (box: BoundingBox) => void;
  onAddManualPiece: (polygon: [number, number][]) => void;
  onUpdatePieceLabel: (id: string, label: string) => void;
  onUpdatePieceSheet: (id: string, sheetId: string) => void;
  onUpdatePiecesSheet: (ids: string[], sheetId: string) => void;
  onAddSheetAndAssignPiece: (id: string, url?: string, label?: string) => void;
  onAddSheetAndAssignPieces: (ids: string[], url?: string, label?: string) => void;
  onDeletePiece: (id: string) => void;
  onDeletePieces: (ids: string[]) => void;
  onSmoothPiece: (id: string) => void;
  onSmoothPieces: (ids: string[]) => void;
  onUpdatePiecePolygon: (id: string, polygon: [number, number][]) => void;
  onUpdatePieceCurves: (id: string, curvePoints: CurvePoint[]) => void;
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

function getTooltipAnchor(piece: Piece, allPieces: Piece[], _pw: number, _ph: number, vp: { pan: {x: number, y: number}, effectiveScale: number, dims: {w: number, h: number} }) {
  const xs = piece.polygon.map(p => p[0]);
  const ys = piece.polygon.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;

  const otherPieces = allPieces.filter(p => p.id !== piece.id);
  
  const score = { top: 1.1, bottom: 1.0, left: 1.0, right: 1.0 };
  
  // Penalize edges (in screen space)
  const toScreen = (ix: number, iy: number) => ({
    x: ix * vp.effectiveScale + vp.pan.x,
    y: iy * vp.effectiveScale + vp.pan.y
  });

  const sTop = toScreen(midX, minY);
  const sBottom = toScreen(midX, maxY);
  const sLeft = toScreen(minX, midY);
  const sRight = toScreen(maxX, midY);

  if (sTop.y < 100) score.top -= 10;
  if (sBottom.y > vp.dims.h - 100) score.bottom -= 10;
  if (sLeft.x < 200) score.left -= 10;
  if (sRight.x > vp.dims.w - 200) score.right -= 10;

  // Prefer sides with more neighbors
  otherPieces.forEach(p => {
    const c = computeCentroid(p.polygon);
    if (c.y < minY) score.top += 1;
    else if (c.y > maxY) score.bottom += 1;
    if (c.x < minX) score.left += 1;
    else if (c.x > maxX) score.right += 1;
  });

  const bestSide = (Object.keys(score) as Array<keyof typeof score>).reduce((a, b) => score[a] > score[b] ? a : b);

  if (bestSide === 'top') return { x: midX, y: minY, transform: 'translate(-50%, -100%)', margin: '0 0 24px 0' };
  if (bestSide === 'bottom') return { x: midX, y: maxY, transform: 'translate(-50%, 0)', margin: '24px 0 0 0' };
  if (bestSide === 'left') return { x: minX, y: midY, transform: 'translate(-100%, -50%)', margin: '0 24px 0 0' };
  return { x: maxX, y: midY, transform: 'translate(0, -50%)', margin: '0 0 0 24px' };
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

function simplifyPath(points: [number, number][], epsilon: number): [number, number][] {
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

function findPenSnapTarget(
  cursor: [number, number],
  pieces: Piece[],
  effectiveScale: number,
  extraVertices?: LampSnapPoint[],
): { pt: [number, number]; label?: string } | null {
  let best: { pt: [number, number]; label?: string } | null = null;
  let bestPxDist = PEN_SNAP_PX;
  for (const piece of pieces) {
    const polygon = flattenCurves(piece.polygon, piece.curvePoints);
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

function getCanvasSnapping(
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

    // X fractional snapping
    if (!snappedX && W > 0) {
      const activeXValues = [left, right];
      for (const frac of FRACTIONS) {
        const posX = left + frac.value * W;
        const tooClose = activeXValues.some(val => Math.abs(posX - val) * effectiveScale < minGap);
        if (!tooClose) {
          activeXValues.push(posX);
          if (Math.abs(x - posX) < threshold) {
            targetX = posX;
            snappedX = true;
            guides.push({ type: 'v', from: [posX, top], to: [posX, bottom] });
            labels.push(frac.label);
            break;
          }
        }
      }
    }

    // Y fractional snapping
    if (!snappedY && H > 0) {
      const activeYValues = [top, bottom];
      for (const frac of FRACTIONS) {
        const posY = top + frac.value * H;
        const tooClose = activeYValues.some(val => Math.abs(posY - val) * effectiveScale < minGap);
        if (!tooClose) {
          activeYValues.push(posY);
          if (Math.abs(y - posY) < threshold) {
            targetY = posY;
            snappedY = true;
            guides.push({ type: 'h', from: [left, posY], to: [right, posY] });
            labels.push(frac.label);
            break;
          }
        }
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

function findAlignmentGuides(
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

function findShiftAlignmentGuides(
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

function findLengthSnap(
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
  onUpdatePiecePolygon, onUpdatePieceCurves, onUpdatePrompt,
  onAutoSegment, isAutoSegmenting, isEncoding, downloadProgress, onUploadPattern, onStartBlankCanvas, onStartLampMode, debugMask, activeTool, onChangeActiveTool,
  tutorialStep, refineMode, onRefineModeChange, onPenStatusChange,
  onUpdateSolderWidthMM, onUpdateSolderColor, onOpenLampProfile,
  isSymmetryEnabled = false, onToggleSymmetry,
}: ResultPanelProps) {
  const { t } = useTranslation();
  const [isSolderPopoverOpen, setIsSolderPopoverOpen] = useState(false);
  const solderPopoverRef = useRef<HTMLDivElement>(null);
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
  const vp = useViewport(pw, ph);

  const [activePolygonPoints, setActivePolygonPoints] = useState<[number, number][]>([]);
  const [hoverPoint, setHoverPoint] = useState<[number, number] | null>(null);
  const [hoverSnapped, setHoverSnapped] = useState(false);
  const activePolygonPointsRef = useRef(activePolygonPoints);
  activePolygonPointsRef.current = activePolygonPoints;

  const [, setIsShiftDown] = useState(false);
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

  function updateHoverPoint(imageX: number, imageY: number, shiftPressed: boolean) {
    if (activeTool !== 'pen') return;

    // 1. Vertex snapping is highest priority
    const snap = findPenSnapTarget([imageX, imageY], piecesRef.current, effectiveScaleRef.current, lampSnapPointsRef.current);
    if (snap) {
      setHoverPoint(snap.pt);
      setHoverSnapped(true);
      setActiveAlignmentGuides([]);
      setActiveLengthGuide(null);
      setActiveSnapLabels(snap.label ? [snap.label] : []);
      return;
    }

    // 1b. Lamp seam edge snap — project onto nearest seam line.
    if (unrolledLampRef.current) {
      const edgeSnap = findLampEdgeSnap([imageX, imageY], unrolledLampRef.current, effectiveScaleRef.current, PEN_SNAP_PX);
      if (edgeSnap) {
        setHoverPoint(edgeSnap);
        setHoverSnapped(true);
        setActiveAlignmentGuides([]);
        setActiveLengthGuide(null);
        return;
      }
    }

    let finalX = imageX;
    let finalY = imageY;
    let alignmentGuides: AlignmentGuide[] = [];
    let lengthGuide: LengthGuide | null = null;

    if (activePolygonPointsRef.current.length > 0) {
      const lastPt = activePolygonPointsRef.current[activePolygonPointsRef.current.length - 1];

      let theta = Math.atan2(imageY - lastPt[1], imageX - lastPt[0]);
      if (shiftPressed) {
        theta = Math.round(theta / (Math.PI / 4)) * (Math.PI / 4);
      }

      // 2. Length Snapping
      const lenSnap = findLengthSnap(
        [imageX, imageY],
        lastPt,
        piecesRef.current,
        activePolygonPointsRef.current,
        effectiveScaleRef.current
      );

      if (lenSnap) {
        finalX = lastPt[0] + lenSnap.matchLength * Math.cos(theta);
        finalY = lastPt[1] + lenSnap.matchLength * Math.sin(theta);

        lengthGuide = {
          matchLength: lenSnap.matchLength,
          center: lastPt,
          snappedPoint: [finalX, finalY],
          matchingSegment: lenSnap.matchingSegment,
        };
      } else {
        if (shiftPressed) {
          const align = findShiftAlignmentGuides(
            [imageX, imageY],
            lastPt,
            theta,
            piecesRef.current,
            effectiveScaleRef.current
          );
          if (align.guides.length > 0) {
            finalX = align.snapped[0];
            finalY = align.snapped[1];
            alignmentGuides = align.guides;
          } else {
            const r = Math.hypot(imageX - lastPt[0], imageY - lastPt[1]);
            finalX = lastPt[0] + r * Math.cos(theta);
            finalY = lastPt[1] + r * Math.sin(theta);
          }
        } else {
          // 3. Horizontal/Vertical Alignment Snapping
          const align = findAlignmentGuides(
            [imageX, imageY],
            piecesRef.current,
            effectiveScaleRef.current
          );
          finalX = align.snapped[0];
          finalY = align.snapped[1];
          alignmentGuides = align.guides;
        }
      }
    } else {
      // 3. Horizontal/Vertical Alignment Snapping
      const align = findAlignmentGuides(
        [imageX, imageY],
        piecesRef.current,
        effectiveScaleRef.current
      );
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

    const edgeSnap = getCanvasSnapping(
      finalX,
      finalY,
      project.patternCrop,
      project.patternWidth,
      project.patternHeight,
      effectiveScaleRef.current,
      t,
      false, // Never disable fractions, we want them!
      customBounds
    );
    finalX = edgeSnap.x;
    finalY = edgeSnap.y;
    if (edgeSnap.guides.length > 0) {
      alignmentGuides = [...alignmentGuides, ...edgeSnap.guides];
    }
    setActiveSnapLabels(edgeSnap.labels);

    setHoverPoint([finalX, finalY]);
    setHoverSnapped(false);
    setActiveAlignmentGuides(alignmentGuides);
    setActiveLengthGuide(lengthGuide);
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

  useEffect(() => {
    onRefineModeChange(null);
    setTooltipDrag({x: 0, y: 0});
  }, [selectedPieceIds]);

  const onPenStatusChangeRef = useRef(onPenStatusChange);
  onPenStatusChangeRef.current = onPenStatusChange;

  const lastPoint = activePolygonPoints.length > 0 ? activePolygonPoints[activePolygonPoints.length - 1] : null;
  useEffect(() => {
    if (activeTool === 'pen') {
      onPenStatusChangeRef.current?.({
        coords: hoverPoint ? { x: hoverPoint[0], y: hoverPoint[1] } : null,
        lastPoint: lastPoint ? { x: lastPoint[0], y: lastPoint[1] } : null,
      });
    } else {
      onPenStatusChangeRef.current?.({ coords: null, lastPoint: null });
    }
  }, [hoverPoint, lastPoint, activeTool]);

  // Capture phase — the ONLY thing that belongs here is the pen Cmd+Z
  // vertex-pop, which must beat App.tsx's bubble-phase undo regardless of
  // registration order. Everything else (tool shortcuts, Escape, …) lives in
  // the bubble-phase handler below so that an open modal's capture-phase
  // Escape handler (which stops propagation, see #115) suppresses it — this
  // panel doesn't need to know a modal is open.
  function handleKeyDownCapture(e: KeyboardEvent) {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
    if ((e.metaKey || e.ctrlKey) && e.key === 'z' && activeTool === 'pen' && activePolygonPointsRef.current.length > 0) {
      // Pop the last placed vertex. stopImmediatePropagation blocks App.tsx's
      // window listener from also firing project undo on the same event.
      e.preventDefault();
      e.stopImmediatePropagation();
      setActivePolygonPoints(prev => prev.slice(0, -1));
    }
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
    if (e.code === 'Space' && !e.repeat) {
      e.preventDefault();
      setIsSpaceDown(true);
      return;
    }
    if (e.key === 'Shift') {
      if (!e.repeat) {
        setIsShiftDown(true);
        if (lastMousePosRef.current) {
          updateHoverPoint(lastMousePosRef.current.x, lastMousePosRef.current.y, true);
        }
      }
    }
    // Don't let browser/app shortcuts (Cmd+C, Cmd+S, Cmd+V, …) trigger tool changes.
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    // Scope single-key shortcuts to the hovered panel (matching SheetPanel);
    // without this, one keystroke switches tools on both panels at once.
    if (!isPointerInsideRef.current) return;
    // Compare case-insensitively so the shortcuts survive Caps Lock.
    const key = e.key.toLowerCase();
    if (key === 'v') handleToolChange('select');
    else if (key === 'h') handleToolChange('pan');
    else if (key === 'b' && !isEncoding) handleToolChange('box');
    else if (key === 'p') handleToolChange('pen');
    else if (key === 'n') handleToolChange('pencil');
    else if (key === 'c') handleToolChange('crop');
    else if (key === 'm') handleToolChange('measure');
    else if (key === 'i') handleToolChange('inspect');
    else if (key === 'a') onRefineModeChange(refineModeRef.current === 'add' ? null : 'add');
    else if (key === 's') onRefineModeChange(refineModeRef.current === 'remove' ? null : 'remove');
    else if (e.key === 'Enter') {
      if (activeTool === 'pen' && activePolygonPointsRef.current.length >= 3) {
        commitActivePolygon();
      }
    }
    else if (e.key === 'Escape') {
      if (isSolderPopoverOpenRef.current) {
        setIsSolderPopoverOpen(false);
      } else if (refineModeRef.current) {
        onRefineModeChange(null);
      } else if (activePolygonPointsRef.current.length > 0) {
        setActivePolygonPoints([]);
        setHoverPoint(null);
        setHoverSnapped(false);
        setActiveSnapLabels([]);
      } else {
        handleToolChange('select');
      }
    }
  }
  function handleKeyUp(e: KeyboardEvent) {
    if (e.code === 'Space') setIsSpaceDown(false);
    if (e.key === 'Shift') {
      setIsShiftDown(false);
      if (lastMousePosRef.current) {
        updateHoverPoint(lastMousePosRef.current.x, lastMousePosRef.current.y, false);
      }
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
    if (!isFirstPending) return;
    let animId: number;
    const tick = () => {
      setDashOffset(prev => (prev + 1.5) % 40);
      animId = requestAnimationFrame(tick);
    };
    animId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animId);
  }, [tutorialStep, project.pieces.length]);
  
  const [patternImg] = useImage(project.patternImageUrl);
  const sheetMap = Object.fromEntries(project.sheets.map(s => [s.id, s]));
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
    if (evt && evt.target instanceof Element && evt.pointerId !== undefined) {
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

    if (activeTool === 'pen') {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      const isShift = e.evt ? e.evt.shiftKey : false;
      let targetX = x;
      let targetY = y;
      const snap = findPenSnapTarget([x, y], project.pieces, vp.effectiveScale, lampSnapPoints);
      const edgeSnap = !snap && unrolledLamp
        ? findLampEdgeSnap([x, y], unrolledLamp, vp.effectiveScale, PEN_SNAP_PX)
        : null;
      if (snap) {
        targetX = snap.pt[0];
        targetY = snap.pt[1];
        if (snap.label) {
          setActiveSnapLabels([snap.label]);
        }
      } else if (edgeSnap) {
        targetX = edgeSnap[0];
        targetY = edgeSnap[1];
      } else if (activePolygonPointsRef.current.length > 0) {
        const lastPt = activePolygonPointsRef.current[activePolygonPointsRef.current.length - 1];

        let theta = Math.atan2(y - lastPt[1], x - lastPt[0]);
        if (isShift) {
          theta = Math.round(theta / (Math.PI / 4)) * (Math.PI / 4);
        }

        const lenSnap = findLengthSnap(
          [x, y],
          lastPt,
          project.pieces,
          activePolygonPointsRef.current,
          vp.effectiveScale
        );

        if (lenSnap) {
          targetX = lastPt[0] + lenSnap.matchLength * Math.cos(theta);
          targetY = lastPt[1] + lenSnap.matchLength * Math.sin(theta);
        } else if (isShift) {
          const align = findShiftAlignmentGuides(
            [x, y],
            lastPt,
            theta,
            project.pieces,
            vp.effectiveScale
          );
          if (align.guides.length > 0) {
            targetX = align.snapped[0];
            targetY = align.snapped[1];
          } else {
            const r = Math.hypot(x - lastPt[0], y - lastPt[1]);
            targetX = lastPt[0] + r * Math.cos(theta);
            targetY = lastPt[1] + r * Math.sin(theta);
          }
        } else {
          const align = findAlignmentGuides(
            [x, y],
            project.pieces,
            vp.effectiveScale
          );
          targetX = align.snapped[0];
          targetY = align.snapped[1];
        }
      } else {
        const align = findAlignmentGuides(
          [x, y],
          project.pieces,
          vp.effectiveScale
        );
        targetX = align.snapped[0];
        targetY = align.snapped[1];
      }

      if (!snap) {
        let customBounds = undefined;
        if (project.projectType === 'lamp' && unrolledLamp && unrolledLamp.mode === 'faceted') {
          const N = project.lampConfig?.facetCount ?? 6;
          const surf = patternToSurfaceRobust(targetX, targetY, unrolledLamp, N);
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

        const edgeSnap = getCanvasSnapping(
          targetX,
          targetY,
          project.patternCrop,
          project.patternWidth,
          project.patternHeight,
          vp.effectiveScale,
          t,
          false,
          customBounds
        );
        targetX = edgeSnap.x;
        targetY = edgeSnap.y;
      }

      // ---- ABSOLUTE SHIFT CONSTRAINT ENFORCER ----
      // If Shift is held, the angle constraint MUST win over all other snapping.
      if (isShift && activePolygonPointsRef.current.length > 0) {
        const lastPt = activePolygonPointsRef.current[activePolygonPointsRef.current.length - 1];
        const theta = Math.round(Math.atan2(y - lastPt[1], x - lastPt[0]) / (Math.PI / 4)) * (Math.PI / 4);
        const dx = Math.cos(theta);
        const dy = Math.sin(theta);
        
        const snappedX = Math.abs(targetX - x) > 1e-3;
        const snappedY = Math.abs(targetY - y) > 1e-3;
        
        let finalX = targetX;
        let finalY = targetY;
        
        if (Math.abs(dx) < 1e-5) {
          finalX = lastPt[0]; // must be purely vertical
        } else if (Math.abs(dy) < 1e-5) {
          finalY = lastPt[1]; // must be purely horizontal
        } else if (snappedX || snappedY) {
          // It snapped to an edge or point. We must intersect the constraint ray with the snapped coordinate.
          if (snappedX && snappedY) {
             const rx = (finalX - lastPt[0]) / dx;
             const ry = (finalY - lastPt[1]) / dy;
             if (Math.abs(rx) < Math.abs(ry)) finalY = lastPt[1] + rx * dy;
             else finalX = lastPt[0] + ry * dx;
          } else if (snappedX) {
             const r = (finalX - lastPt[0]) / dx;
             finalY = lastPt[1] + r * dy;
          } else if (snappedY) {
             const r = (finalY - lastPt[1]) / dy;
             finalX = lastPt[0] + r * dx;
          }
        } else {
          // No external snap applied, simply constrain point to the ray
          const r = Math.hypot(x - lastPt[0], y - lastPt[1]);
          finalX = lastPt[0] + r * dx;
          finalY = lastPt[1] + r * dy;
        }
        
        targetX = finalX;
        targetY = finalY;
      }

      if (activePolygonPointsRef.current.length >= 3) {
        const [startX, startY] = activePolygonPointsRef.current[0];
        const dist = Math.hypot(targetX - startX, targetY - startY) * vp.effectiveScale;
        if (dist < 15) {
          commitActivePolygon();
          return;
        }
      }
      setActivePolygonPoints(prev => [...prev, [targetX, targetY]]);
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
    if (activeTool === 'pen') {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      lastMousePosRef.current = { x, y };
      const isShift = e.evt ? e.evt.shiftKey : false;
      setIsShiftDown(isShift);
      updateHoverPoint(x, y, isShift);
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
      const hitIds = project.pieces.filter(p => {
        const centroid = computeCentroid(p.polygon);
        return centroid.x >= box.x1 && centroid.x <= box.x2 && centroid.y >= box.y1 && centroid.y <= box.y2;
      }).map(p => p.id);

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
    if (id === activeTool && id !== 'select') {
      onChangeActiveTool('select');
      if (id === 'measure') measure.reset();
      return;
    }

    if (id !== 'pen') {
      setActivePolygonPoints([]);
      setHoverPoint(null);
      setHoverSnapped(false);
      lastMousePosRef.current = null;
      setActiveAlignmentGuides([]);
      setActiveLengthGuide(null);
      setActiveSnapLabels([]);
    }
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
          : activeTool === 'pen'
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

  const TOOLS = BASE_TOOLS
    .filter(tool => !IS_TOUCH || tool.id !== 'pan')
    .map(tool => {
    if (tool.id === 'box') return { ...tool, disabled: !!isEncoding, loading: isEncoding ? (downloadProgress ?? true) : false };
    if (tool.id === 'detect-all') return { ...tool, disabled: !!isAutoSegmenting || !onAutoSegment || !!isEncoding, loading: isAutoSegmenting ? true : (isEncoding ? (downloadProgress ?? true) : false) };
    return tool;
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
        <div className="tooltip-wrapper" ref={solderPopoverRef}>
          <button
            className={`tool-btn solder-tool-btn ${isSolderPopoverOpen ? 'active' : ''}`}
            onClick={() => setIsSolderPopoverOpen(o => !o)}
            aria-label={t('solderThicknessTooltip')}
            data-tutorial-target="solder-settings"
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
          
          {!isSolderPopoverOpen && <span className="tooltip-tip">{t('solderThicknessTooltip')}</span>}
          
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
                data-tutorial-target="lamp-symmetry-button"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="9" strokeDasharray="2 2" />
                  <circle cx="12" cy="12" r="3" />
                  <path d="M12 3v6" />
                  <path d="M12 15v6" />
                  <path d="M3 12h6" />
                  <path d="M15 12h6" />
                </svg>
              </button>
              <span className="tooltip-tip">{t('lampSymmetryTooltip')}</span>
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
                data-tutorial-target="lamp-profile-button"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <ellipse cx="12" cy="5" rx="6" ry="2" />
                  <path d="M6 5 L4 19" />
                  <path d="M18 5 L20 19" />
                  <ellipse cx="12" cy="19" rx="8" ry="2.5" />
                </svg>
              </button>
              <span className="tooltip-tip">{t('lampProfileButtonTooltip')}</span>
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
              onPointerLeave={() => {
                if (activeTool === 'pen') {
                  setHoverPoint(null);
                  setActiveSnapLabels([]);
                }
              }}
              onPointerCancel={handlePointerCancel}
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
                    const isSelected = selectedPieceIds.includes(piece.id);
                    // Corner drag: override polygon directly (activeDragPolygon)
                    const basePolygon = (isSelected && activeDragPolygon) ? activeDragPolygon : piece.polygon;
                    // Midpoint drag: override curvePoints (activeDragCurvePoints); polygon stays clean
                    const baseCurves = (isSelected && activeDragCurvePoints) ? activeDragCurvePoints : piece.curvePoints;
                    const displayPolygon = flattenCurves(basePolygon, baseCurves);
                    return (
                      <PieceOverlay
                        key={piece.id}
                        piece={piece}
                        displayPolygon={displayPolygon}
                        glassImageUrl={sheet?.imageUrl ?? ''}
                        isSelected={isSelected}
                        isPending={pendingPieceIds.has(piece.id)}
                        solderWidth={solderWidth}
                        solderColor={SOLDER_COLORS[project.solderColor ?? 'black'] ?? SOLDER_COLORS.black}
                        onSelect={(multi) => { if (!refineMode) onSelectPiece(piece.id, multi); }}
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
                  {activeTool === 'pen' && (activePolygonPoints.length > 0 || hoverPoint) && (
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
                    if (!selectedPieceIds.includes(piece.id) || !piece.promptPoints) return null;
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
                                newPolygon[idx] = [e.target.x(), e.target.y()];
                                setActiveDragPolygon(newPolygon);
                              }}
                              onDragEnd={(e) => {
                                if (!dragStartPolygon) { setDraggedCorner(null); return; }
                                const newPolygon = [...dragStartPolygon];
                                newPolygon[idx] = [e.target.x(), e.target.y()];
                                // Curves use absolute ctrl coordinates so they adapt naturally
                                // to the moved corner — no need to drop them
                                onUpdatePiecePolygon(selectedId, newPolygon);
                                setDraggedCorner(null);
                                setDragStartPolygon(null);
                                setActiveDragPolygon(null);
                              }}
                              onMouseEnter={(e) => {
                                const stage = e.target.getStage();
                                if (stage) stage.container().style.cursor = 'move';
                              }}
                              onMouseLeave={(e) => {
                                const stage = e.target.getStage();
                                if (stage) stage.container().style.cursor = 'default';
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
                          const existingCtrl = (activeDragCurvePoints ?? piece.curvePoints ?? []).find(cp => cp.edgeIdx === idx)?.ctrl;
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
                            />
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
                glassSheetId: project.pieces.filter(p => selectedPieceIds.includes(p.id))
                  .every((p, _, arr) => p.glassSheetId === arr[0].glassSheetId) 
                    ? piece.glassSheetId 
                    : '__multiple__'
              } : piece;

              const anchor = getTooltipAnchor(piece, project.pieces, pw, ph, vp);
              const sc = toScreenCoords(anchor.x, anchor.y, vp.pan, vp.effectiveScale);
              const isDrawing = drawingBox !== null
                || pencilPoints.length > 0
                || (activeTool === 'pen' && activePolygonPoints.length > 0)
                || draggedCorner !== null
                || draggedMidpoint !== null;
              const isInteracting = isDrawing || marqueeBox !== null || vp.isPanning || isSpaceDown;

              return (
                <div style={{
                  position: 'absolute',
                  left: sc.x + tooltipDrag.x,
                  top: sc.y + tooltipDrag.y,
                  transform: anchor.transform,
                  padding: anchor.margin,
                  zIndex: 10,
                  pointerEvents: isInteracting ? 'none' : 'auto',
                  opacity: isInteracting ? 0 : 0.95,
                  transition: 'opacity 0.2s ease, transform 0.3s ease-out',
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
