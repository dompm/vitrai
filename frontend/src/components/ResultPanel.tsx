import { useState, useEffect, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Stage, Layer, Image as KonvaImage, Line, Group, Rect, Circle } from 'react-konva';
import useImage from 'use-image';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { Piece, Project, Crop, BoundingBox, Scale } from '../types';
import { computeCentroid } from '../utils/geometry';
import { Toolbar, SelectIcon, CropIcon, MeasureIcon, BoxIcon, DetectAllIcon } from './Toolbar';
import type { ToolId } from './Toolbar';
import { SelectAnimation, BoxAnimation, CropAnimation, MeasureAnimation, DetectAllAnimation } from './ToolTooltipAnimations';
import { CropOverlay } from './CropOverlay';
import { MeasureInput } from './MeasureInput';
import { MeasureLineOverlay } from './MeasureLineOverlay';
import { useViewport } from '../hooks/useViewport';
import { useMeasure } from '../hooks/useMeasure';
import { toImageCoords, toScreenCoords } from '../utils/viewport';
import { PieceProperties } from './PieceProperties';

function DragHandle({ onDrag }: { onDrag: (delta: { x: number; y: number }) => void }) {
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
        cursor: 'grab',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: '8px 8px 0 0',
        background: '#f3f4f6',
        borderBottom: '1px solid #e5e7eb',
      }}
    >
      <svg width="20" height="4" viewBox="0 0 20 4"><circle cx="4" cy="2" r="1.5" fill="#9ca3af"/><circle cx="10" cy="2" r="1.5" fill="#9ca3af"/><circle cx="16" cy="2" r="1.5" fill="#9ca3af"/></svg>
    </div>
  );
}


interface PieceOverlayProps {
  piece: Piece;
  glassImageUrl: string;
  isSelected: boolean;
  isPending: boolean;
  effectiveScale: number;
  opacity?: number;
  solderWidth: number;
  onSelect: (multi?: boolean) => void;
}

function PieceOverlay({ piece, glassImageUrl, isSelected, isPending, effectiveScale, opacity = 1, solderWidth, onSelect }: PieceOverlayProps) {
  const [glassImg] = useImage(glassImageUrl);
  const { x: tx, y: ty, rotation, scale } = piece.transform;
  const centroid = computeCentroid(piece.polygon);
  const flatPts = piece.polygon.flat();

  function clipPolygon(ctx: CanvasRenderingContext2D) {
    ctx.beginPath();
    piece.polygon.forEach(([x, y], i) => {
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath();
  }

  function handleClick(e: KonvaEventObject<MouseEvent>) {
    e.cancelBubble = true;
    onSelect(e.evt.shiftKey);
  }

  const xs = piece.polygon.map(p => p[0]);
  const ys = piece.polygon.map(p => p[1]);

  return (
    <Group onClick={handleClick} onTap={handleClick} opacity={opacity}>
      <Group clipFunc={clipPolygon}>
        <Group
          x={centroid.x} y={centroid.y}
          rotation={(rotation * 180) / Math.PI}
          scaleX={1 / scale} scaleY={1 / scale}
        >
          {glassImg && <KonvaImage image={glassImg} x={-tx} y={-ty} />}
        </Group>
        {isPending && (
          <Rect
            x={Math.min(...xs)} y={Math.min(...ys)}
            width={Math.max(...xs) - Math.min(...xs)}
            height={Math.max(...ys) - Math.min(...ys)}
            fill="rgba(245,158,11,0.18)"
            listening={false}
          />
        )}
      </Group>
      <Line
        points={flatPts}
        stroke={isPending ? '#f59e0b' : isSelected ? '#4338ca' : '#2d2d2d'}
        strokeWidth={isSelected ? solderWidth * 1.25 : solderWidth}
        dash={isPending ? [solderWidth * 2, solderWidth] : undefined}
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
  onUpdatePieceLabel: (id: string, label: string) => void;
  onUpdatePieceSheet: (id: string, sheetId: string) => void;
  onAddSheetAndAssignPiece: (id: string) => void;
  onDeletePiece: (id: string) => void;
  onUpdatePrompt: (pieceId: string, point: { x: number; y: number; label: 1 | 0 }) => void;
  onAutoSegment?: () => void;
  isAutoSegmenting?: boolean;
}

const MIN_BOX_PX = 10;
const DEFAULT_SOLDER_WIDTH_MM = 4.5;

function getSolderWidth(scale: Scale | null, imgWidth: number) {
  if (!scale) {
    // If no scale is set, default to a width that is 0.6% of the image width.
    // For a 1000px image, this is 6px. For 4000px, it's 24px.
    return Math.max(2, imgWidth * 0.006);
  }
  const { pxPerUnit, unit } = scale;
  const target = DEFAULT_SOLDER_WIDTH_MM;
  if (unit === 'mm') return target * pxPerUnit;
  if (unit === 'cm') return (target / 10) * pxPerUnit;
  if (unit === 'in') return (target / 25.4) * pxPerUnit;
  return target;
}

export function ResultPanel({
  project, selectedPieceIds, pendingPieceIds, onSelectPiece, onSelectPieces, onPatternCropChange, onPatternScaleChange, onAddPiece,
  onUpdatePieceLabel, onUpdatePieceSheet, onAddSheetAndAssignPiece, onDeletePiece, onUpdatePrompt,
  onAutoSegment, isAutoSegmenting,
}: ResultPanelProps) {
  const { t } = useTranslation();
  const [activeTool, setActiveTool] = useState<ToolId>('select');
  const [refineMode, setRefineMode] = useState<'add' | 'remove' | null>(null);

  const [tooltipDrag, setTooltipDrag] = useState<{x: number; y: number}>({x: 0, y: 0});
  const [rulerDrag, setRulerDrag] = useState<{x: number; y: number}>({x: 0, y: 0});

  const solderWidth = useMemo(() => getSolderWidth(project.patternScale, project.patternWidth), [project.patternScale, project.patternWidth]);

  useEffect(() => {
    setRefineMode(null);
    setTooltipDrag({x: 0, y: 0});
    setRulerDrag({x: 0, y: 0});
  }, [selectedPieceIds]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
      if (e.key === 'v') handleToolChange('select');
      else if (e.key === 'b') handleToolChange('box');
      else if (e.key === 'c') handleToolChange('crop');
      else if (e.key === 'm') handleToolChange('measure');
      else if (e.key === 'Escape') handleToolChange('select');
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTool]);

  const { patternWidth: pw, patternHeight: ph } = project;
  const vp = useViewport(pw, ph);
  const [patternImg] = useImage(project.patternImageUrl);
  const sheetMap = Object.fromEntries(project.sheets.map(s => [s.id, s]));
  const [drawingBox, setDrawingBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [marqueeBox, setMarqueeBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const measure = useMeasure();

  function isBackground(e: KonvaEventObject<PointerEvent | MouseEvent>) {
    return e.target.getType() === 'Stage' || (e.target as { attrs?: { id?: string } }).attrs?.id === 'bg';
  }

  function handlePointerDown(e: KonvaEventObject<PointerEvent>) {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;

    const isMiddleClick = e.evt && (e.evt as MouseEvent).button === 1;
    if (isMiddleClick) {
      vp.startPan(ptr);
      return;
    }
    
    const lastSelectedId = selectedPieceIds[selectedPieceIds.length - 1];
    if (refineMode && lastSelectedId) {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      onUpdatePrompt(lastSelectedId, { x, y, label: refineMode === 'add' ? 1 : 0 });
      return;
    }

    if (activeTool === 'box') {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      setDrawingBox({ x1: x, y1: y, x2: x, y2: y });
      return;
    }

    if (activeTool === 'select' && isBackground(e)) {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      setMarqueeBox({ x1: x, y1: y, x2: x, y2: y });
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
      if (box.x2 - box.x1 >= MIN_BOX_PX && box.y2 - box.y1 >= MIN_BOX_PX) {
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
    vp.endPan();
  }

  function handleMeasureConfirm(realLength: number, unit: Scale['unit']) {
    if (!measure.line) return;
    const px = Math.hypot(measure.line.x2 - measure.line.x1, measure.line.y2 - measure.line.y1);
    onPatternScaleChange({ pxPerUnit: px / realLength, unit, line: { ...measure.line } });
  }

  function handleToolChange(id: ToolId) {
    if (id === 'detect-all') {
      onAutoSegment?.();
      return;
    }
    setRefineMode(null);
    if (activeTool === 'measure' && id !== 'measure') measure.reset();
    if (id === 'measure') {
      setRulerDrag({ x: 0, y: 0 });
      const saved = project.patternScale?.line;
      const cropL = project.patternCrop.left;
      const cropT = project.patternCrop.top;
      const cropR = pw - project.patternCrop.right;
      const cropB = ph - project.patternCrop.bottom;
      
      const defaultX1 = cropL + (cropR - cropL) * 0.25;
      const defaultX2 = cropL + (cropR - cropL) * 0.75;
      const defaultY = cropT + (cropB - cropT) * 0.5;

      let x1 = saved?.x1 ?? defaultX1;
      let y1 = saved?.y1 ?? defaultY;
      let x2 = saved?.x2 ?? defaultX2;
      let y2 = saved?.y2 ?? defaultY;

      x1 = Math.max(cropL, Math.min(cropR, x1));
      y1 = Math.max(cropT, Math.min(cropB, y1));
      x2 = Math.max(cropL, Math.min(cropR, x2));
      y2 = Math.max(cropT, Math.min(cropB, y2));
      
      measure.loadLine({ x1, y1, x2, y2 });
    }
    setActiveTool(id);
  }

  const containerCursor = refineMode === 'add' ? 'crosshair' : refineMode === 'remove' ? 'no-drop' : activeTool === 'box' ? 'crosshair' : 'default';
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
  ], [t]);

  const TOOLS = BASE_TOOLS.map(tool =>
    tool.id === 'detect-all'
      ? { ...tool, disabled: isAutoSegmenting || !onAutoSegment, loading: !!isAutoSegmenting }
      : tool
  );

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <Toolbar tools={TOOLS} activeTool={activeTool} onSelectTool={handleToolChange} />
      <div
        ref={vp.containerRef}
        style={{ flex: 1, overflow: 'hidden', cursor: containerCursor, position: 'relative' }}
      >
        <Stage
          width={vp.dims.w} height={vp.dims.h}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        >
          <Layer>
            <Group
              x={vp.pan.x} y={vp.pan.y}
              scaleX={es} scaleY={es}
              clipX={activeTool === 'crop' ? 0 : project.patternCrop.left}
              clipY={activeTool === 'crop' ? 0 : project.patternCrop.top}
              clipWidth={activeTool === 'crop' ? pw : Math.max(1, pw - project.patternCrop.left - project.patternCrop.right)}
              clipHeight={activeTool === 'crop' ? ph : Math.max(1, ph - project.patternCrop.top - project.patternCrop.bottom)}
            >
              {patternImg && (
                <KonvaImage 
                  id="bg" 
                  image={patternImg} 
                  width={pw} height={ph} 
                  opacity={activeTool === 'box' ? 0.5 : 1} 
                />
              )}
              {project.pieces.map(piece => {
                const sheet = sheetMap[piece.glassSheetId];
                const isSelected = selectedPieceIds.includes(piece.id);
                return (
                  <PieceOverlay
                    key={piece.id}
                    piece={piece}
                    glassImageUrl={sheet?.imageUrl ?? ''}
                    isSelected={isSelected}
                    isPending={pendingPieceIds.has(piece.id)}
                    effectiveScale={es}
                    solderWidth={solderWidth}
                    onSelect={(multi) => onSelectPiece(piece.id, multi)}
                  />
                );
              })}
              {marqueeBox && (
                <Rect
                  x={Math.min(marqueeBox.x1, marqueeBox.x2)}
                  y={Math.min(marqueeBox.y1, marqueeBox.y2)}
                  width={Math.abs(marqueeBox.x2 - marqueeBox.x1)}
                  height={Math.abs(marqueeBox.y2 - marqueeBox.y1)}
                  fill="rgba(67, 56, 202, 0.08)"
                  stroke="#4338ca"
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
                  stroke="#f59e0b"
                  strokeWidth={2 / es}
                  fill="rgba(245,158,11,0.08)"
                  dash={[6 / es, 4 / es]}
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
                      stroke="rgba(245,158,11,0.3)"
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
                    fill={pt.label === 1 ? '#4338ca' : '#ef4444'}
                    listening={false}
                  />
                ));
              })}
              {activeTool === 'measure' && measure.line && (
                <MeasureLineOverlay
                  line={measure.line}
                  effectiveScale={es}
                  imageWidth={pw} imageHeight={ph}
                  crop={project.patternCrop}
                  onUpdateP1={measure.updateP1}
                  onUpdateP2={measure.updateP2}
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
              screenX={sc.x + rulerDrag.x} screenY={sc.y + rulerDrag.y}
              pixelLength={measurePxLength}
              initialValue={saved ? measurePxLength / saved.pxPerUnit : undefined}
              initialUnit={saved?.unit}
              onConfirm={handleMeasureConfirm}
              onCancel={() => handleToolChange('select')}
              onDrag={delta => setRulerDrag(d => ({ x: d.x + delta.x, y: d.y + delta.y }))}
            />
          );
        })()}
        {(() => {
          const lastId = selectedPieceIds[selectedPieceIds.length - 1];
          const piece = project.pieces.find(p => p.id === lastId);
          if (!piece) return null;
          
          const ys = piece.polygon.map(p => p[1]);
          const minY = Math.min(...ys);
          const xs = piece.polygon.map(p => p[0]);
          const minX = Math.min(...xs);
          const maxX = Math.max(...xs);
          const centerX = (minX + maxX) / 2;

          const sc = toScreenCoords(centerX, minY, vp.pan, vp.effectiveScale);

          return (
            <div style={{
              position: 'absolute',
              left: sc.x + tooltipDrag.x,
              top: sc.y + tooltipDrag.y,
              transform: 'translate(-50%, -100%)',
              marginTop: -12,
              zIndex: 10,
              pointerEvents: 'none',
            }}>
              <div style={{ pointerEvents: 'auto' }}>
                <DragHandle onDrag={delta => setTooltipDrag(d => ({ x: d.x + delta.x, y: d.y + delta.y }))} />
                <PieceProperties
                  piece={piece}
                  sheets={project.sheets}
                  onLabelChange={label => onUpdatePieceLabel(piece.id, label)}
                  onSheetChange={sheetId => onUpdatePieceSheet(piece.id, sheetId)}
                  onAddSheet={() => onAddSheetAndAssignPiece(piece.id)}
                  onDelete={() => onDeletePiece(piece.id)}
                  refineMode={refineMode}
                  onRefineModeChange={setRefineMode}
                  isPending={pendingPieceIds.has(piece.id)}
                />
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}
