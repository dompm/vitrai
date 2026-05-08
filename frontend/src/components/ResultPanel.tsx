import { useState } from 'react';
import { Stage, Layer, Image as KonvaImage, Line, Group, Rect } from 'react-konva';
import useImage from 'use-image';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { Piece, Project, Crop, BoundingBox, Scale } from '../types';
import { computeCentroid } from '../utils/geometry';
import { Toolbar, SelectIcon, CropIcon, MeasureIcon, BoxIcon } from './Toolbar';
import type { ToolId } from './Toolbar';
import { CropOverlay } from './CropOverlay';
import { MeasureInput } from './MeasureInput';
import { MeasureLineOverlay } from './MeasureLineOverlay';
import { useViewport } from '../hooks/useViewport';
import { useMeasure } from '../hooks/useMeasure';
import { toImageCoords, toScreenCoords } from '../utils/viewport';
import { PieceProperties } from './PieceProperties';

const TOOLS = [
  { id: 'select' as ToolId, label: 'Select', icon: <SelectIcon /> },
  { id: 'box' as ToolId, label: 'Add piece (draw box)', icon: <BoxIcon /> },
  { id: 'crop' as ToolId, label: 'Crop pattern', icon: <CropIcon /> },
  { id: 'measure' as ToolId, label: 'Set pattern scale', icon: <MeasureIcon /> },
];

interface PieceOverlayProps {
  piece: Piece;
  glassImageUrl: string;
  isSelected: boolean;
  isPending: boolean;
  effectiveScale: number;
  onSelect: () => void;
}

function PieceOverlay({ piece, glassImageUrl, isSelected, isPending, effectiveScale, onSelect }: PieceOverlayProps) {
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
    onSelect();
  }

  const xs = piece.polygon.map(p => p[0]);
  const ys = piece.polygon.map(p => p[1]);

  return (
    <Group onClick={handleClick} onTap={handleClick}>
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
        stroke={isPending ? '#f59e0b' : isSelected ? '#4f46e5' : 'rgba(79,70,229,0.7)'}
        strokeWidth={isSelected ? 3 / effectiveScale : 2 / effectiveScale}
        dash={isPending ? [6 / effectiveScale, 4 / effectiveScale] : undefined}
        closed listening={false}
      />
    </Group>
  );
}

interface ResultPanelProps {
  project: Project;
  selectedPieceId: string | null;
  pendingPieceIds: ReadonlySet<string>;
  onSelectPiece: (id: string | null) => void;
  onPatternCropChange: (c: Partial<Crop>) => void;
  onPatternScaleChange: (s: Scale | null) => void;
  onAddPiece: (box: BoundingBox) => void;
  onUpdatePieceLabel: (id: string, label: string) => void;
  onUpdatePieceSheet: (id: string, sheetId: string) => void;
  onAddSheetAndAssignPiece: (id: string) => void;
  onDeletePiece: (id: string) => void;
}

const MIN_BOX_PX = 10;

export function ResultPanel({
  project, selectedPieceId, pendingPieceIds, onSelectPiece, onPatternCropChange, onPatternScaleChange, onAddPiece,
  onUpdatePieceLabel, onUpdatePieceSheet, onAddSheetAndAssignPiece, onDeletePiece,
}: ResultPanelProps) {
  const [activeTool, setActiveTool] = useState<ToolId>('select');
  const { patternWidth: pw, patternHeight: ph } = project;
  const vp = useViewport(pw, ph);
  const [patternImg] = useImage(project.patternImageUrl);
  const sheetMap = Object.fromEntries(project.sheets.map(s => [s.id, s]));
  const [drawingBox, setDrawingBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const measure = useMeasure();

  function isBackground(e: KonvaEventObject<PointerEvent | MouseEvent>) {
    return e.target.getType() === 'Stage' || (e.target as { attrs?: { id?: string } }).attrs?.id === 'bg';
  }

  function handlePointerDown(e: KonvaEventObject<PointerEvent>) {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;
    if (activeTool === 'box') {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      setDrawingBox({ x1: x, y1: y, x2: x, y2: y });
      return;
    }
    if (!isBackground(e)) return;
    vp.startPan(ptr);
  }

  function handlePointerMove(e: KonvaEventObject<PointerEvent>) {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;
    if (drawingBox) {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      setDrawingBox(b => b ? { ...b, x2: x, y2: y } : null);
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
    vp.endPan();
  }

  function handleStageClick(e: KonvaEventObject<MouseEvent>) {
    if (activeTool === 'select' && isBackground(e)) onSelectPiece(null);
  }

  function handleMeasureConfirm(realLength: number, unit: Scale['unit']) {
    if (!measure.line) return;
    const px = Math.hypot(measure.line.x2 - measure.line.x1, measure.line.y2 - measure.line.y1);
    onPatternScaleChange({ pxPerUnit: px / realLength, unit, line: { ...measure.line } });
  }

  function handleToolChange(id: ToolId) {
    if (activeTool === 'measure' && id !== 'measure') measure.reset();
    if (id === 'measure') {
      const saved = project.patternScale?.line;
      measure.loadLine(saved ?? { x1: pw * 0.25, y1: ph * 0.5, x2: pw * 0.75, y2: ph * 0.5 });
    }
    setActiveTool(id);
  }

  const containerCursor = activeTool === 'box' ? 'crosshair' : 'default';
  const es = vp.effectiveScale;
  const measurePxLength = measure.line
    ? Math.hypot(measure.line.x2 - measure.line.x1, measure.line.y2 - measure.line.y1)
    : 0;

  function setCursor(cursor: string) {
    if (vp.containerRef.current) vp.containerRef.current.style.cursor = cursor;
  }

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
          onClick={handleStageClick}
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
                <KonvaImage id="bg" image={patternImg} width={pw} height={ph} />
              )}
              {project.pieces.map(piece => {
                const sheet = sheetMap[piece.glassSheetId];
                return (
                  <PieceOverlay
                    key={piece.id}
                    piece={piece}
                    glassImageUrl={sheet?.imageUrl ?? ''}
                    isSelected={piece.id === selectedPieceId}
                    isPending={pendingPieceIds.has(piece.id)}
                    effectiveScale={es}
                    onSelect={() => onSelectPiece(piece.id)}
                  />
                );
              })}
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
              {activeTool === 'measure' && measure.line && (
                <MeasureLineOverlay
                  line={measure.line}
                  effectiveScale={es}
                  imageWidth={pw} imageHeight={ph}
                  onUpdateP1={measure.updateP1}
                  onUpdateP2={measure.updateP2}
                  onCursorChange={setCursor}
                />
              )}
            </Group>
          </Layer>
        </Stage>
        {activeTool === 'measure' && measure.line && (() => {
          const sc = toScreenCoords(measure.line.x2, measure.line.y2, vp.pan, vp.effectiveScale);
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
        {selectedPieceId && (() => {
          const piece = project.pieces.find(p => p.id === selectedPieceId);
          if (!piece) return null;
          const centroid = computeCentroid(piece.polygon);
          const sc = toScreenCoords(centroid.x, centroid.y, vp.pan, vp.effectiveScale);
          return (
            <div style={{
              position: 'absolute',
              left: sc.x,
              top: sc.y,
              transform: 'translate(-50%, -100%)',
              marginTop: -10,
              zIndex: 10
            }}>
              <PieceProperties
                piece={piece}
                sheets={project.sheets}
                onLabelChange={label => onUpdatePieceLabel(piece.id, label)}
                onSheetChange={sheetId => onUpdatePieceSheet(piece.id, sheetId)}
                onAddSheet={() => onAddSheetAndAssignPiece(piece.id)}
                onDelete={() => onDeletePiece(piece.id)}
              />
            </div>
          );
        })()}
      </div>
    </div>
  );
}
