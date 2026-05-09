import { useState, useRef, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Stage, Layer, Image as KonvaImage, Line, Group, Circle } from 'react-konva';
import useImage from 'use-image';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { Piece, GlassSheet, TextureTransform, Crop, Scale } from '../types';
import { computeCentroid } from '../utils/geometry';
import { toImageCoords, toScreenCoords } from '../utils/viewport';
import { Toolbar, SelectIcon, CropIcon, MeasureIcon } from './Toolbar';
import type { ToolId } from './Toolbar';
import { SelectAnimation, CropAnimation, MeasureAnimation } from './ToolTooltipAnimations';
import { CropOverlay } from './CropOverlay';
import { MeasureInput } from './MeasureInput';
import { MeasureLineOverlay } from './MeasureLineOverlay';
import { useViewport } from '../hooks/useViewport';
import { useMeasure } from '../hooks/useMeasure';


// Display-pixel constants — independent of zoom or image resolution
const STROKE_IDLE = 2.5;
const STROKE_SELECTED = 3;
const HANDLE_RADIUS = 10;
const HANDLE_STEM = 1.5;
const HANDLE_BORDER = 2;
const HANDLE_GAP = 18; // extra gap beyond the bounding radius, in display px

interface PieceOutlineProps {
  piece: Piece;
  isSelected: boolean;
  effectiveScale: number;
  onSelect: (multi?: boolean) => void;
  onTransformChange: (t: Partial<TextureTransform>) => void;
  onRotateStart: () => void;
}

function PieceOutline({ piece, isSelected, effectiveScale, onSelect, onTransformChange, onRotateStart }: PieceOutlineProps) {
  const { x, y, rotation, scale } = piece.transform;
  const centroid = computeCentroid(piece.polygon);
  const relPts = piece.polygon.flatMap(([px, py]) => [px - centroid.x, py - centroid.y]);

  // Combined divisor so sizes stay fixed in display pixels
  const es = effectiveScale * scale;

  // Bounding radius in display px, converted to local coords for the handle stem
  const radiusPx = Math.max(
    ...piece.polygon.map(([px, py]) => Math.hypot(px - centroid.x, py - centroid.y))
  ) * es;
  const handleOffset = (radiusPx + HANDLE_GAP + HANDLE_RADIUS) / es;

  // Prevent drag from starting when the pointer went down on the rotation handle
  const dragStartedFromHandle = useRef(false);

  function handleClick(e: KonvaEventObject<MouseEvent>) {
    e.cancelBubble = true;
    onSelect(e.evt.shiftKey);
  }

  function handleDragStart(e: KonvaEventObject<DragEvent>) {
    if (dragStartedFromHandle.current) {
      dragStartedFromHandle.current = false;
      e.target.stopDrag();
    }
  }

  function handleDragMove(e: KonvaEventObject<DragEvent>) {
    onTransformChange({ x: e.target.x(), y: e.target.y() });
  }

  function handleRotateDown(e: KonvaEventObject<PointerEvent>) {
    e.cancelBubble = true;
    dragStartedFromHandle.current = true;
    onRotateStart();
  }

  return (
    <Group
      x={x} y={y}
      rotation={(rotation * 180) / Math.PI}
      scaleX={scale} scaleY={scale}
      draggable={isSelected}
      onClick={handleClick} onTap={handleClick}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
    >
      <Line
        points={relPts}
        stroke={isSelected ? '#4f46e5' : 'rgba(79,70,229,0.65)'}
        strokeWidth={isSelected ? STROKE_SELECTED / es : STROKE_IDLE / es}
        fill={isSelected ? 'rgba(79,70,229,0.10)' : 'rgba(79,70,229,0.04)'}
        closed
      />
      {isSelected && (
        <>
          <Line
            points={[0, 0, 0, -handleOffset]}
            stroke="rgba(79,70,229,0.55)" strokeWidth={HANDLE_STEM / es}
            listening={false}
          />
          <Circle
            x={0} y={-handleOffset}
            radius={HANDLE_RADIUS / es}
            fill="#4f46e5" stroke="white" strokeWidth={HANDLE_BORDER / es}
            onPointerDown={handleRotateDown}
          />
        </>
      )}
    </Group>
  );
}

interface SheetPanelProps {
  sheet: GlassSheet;
  pieces: Piece[];
  selectedPieceIds: string[];
  onSelectPiece: (id: string | null, multi?: boolean) => void;
  onTransformChange: (pieceId: string, t: Partial<TextureTransform>) => void;
  onCropChange: (c: Partial<Crop>) => void;
  onScaleChange: (s: Scale | null) => void;
  onImageLoad?: (w: number, h: number) => void;
}

export function SheetPanel({
  sheet, pieces, selectedPieceIds, onSelectPiece, onTransformChange, onCropChange, onScaleChange, onImageLoad,
}: SheetPanelProps) {
  const { t } = useTranslation();
  const [activeTool, setActiveTool] = useState<ToolId>('select');
  const [sheetImg] = useImage(sheet.imageUrl);
  const sheetW = sheetImg?.width ?? 800;
  const sheetH = sheetImg?.height ?? 600;

  useEffect(() => {
    if (sheetImg && onImageLoad) onImageLoad(sheetImg.width, sheetImg.height);
  }, [sheetImg]); // eslint-disable-line react-hooks/exhaustive-deps
  const vp = useViewport(sheetW, sheetH);
  const measure = useMeasure();

  const [rotatingPieceId, setRotatingPieceId] = useState<string | null>(null);
  const rotatingPiece = useMemo(
    () => pieces.find(p => p.id === rotatingPieceId) ?? null,
    [pieces, rotatingPieceId]
  );

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

    if (!isBackground(e)) return;
    vp.startPan(ptr);
  }

  function handlePointerMove(e: KonvaEventObject<PointerEvent>) {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;

    if (rotatingPiece) {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      const newRotation =
        Math.atan2(y - rotatingPiece.transform.y, x - rotatingPiece.transform.x) + Math.PI / 2;
      onTransformChange(rotatingPieceId!, { rotation: newRotation });
      return;
    }

    vp.movePan(ptr);
  }

  function handlePointerUp() {
    setRotatingPieceId(null);
    vp.endPan();
  }

  function handleStageClick(e: KonvaEventObject<MouseEvent>) {
    if (!rotatingPieceId && activeTool === 'select' && isBackground(e)) onSelectPiece(null);
  }

  function handleMeasureConfirm(realLength: number, unit: Scale['unit']) {
    if (!measure.line) return;
    const px = Math.hypot(measure.line.x2 - measure.line.x1, measure.line.y2 - measure.line.y1);
    onScaleChange({ pxPerUnit: px / realLength, unit, line: { ...measure.line } });
  }

  function handleToolChange(id: ToolId) {
    if (activeTool === 'measure' && id !== 'measure') measure.reset();
    if (id === 'measure') {
      const saved = sheet.scale?.line;
      const cropL = sheet.crop.left;
      const cropT = sheet.crop.top;
      const cropR = sheetW - sheet.crop.right;
      const cropB = sheetH - sheet.crop.bottom;
      
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

  function setCursor(cursor: string) {
    if (vp.containerRef.current) vp.containerRef.current.style.cursor = cursor;
  }

  const es = vp.effectiveScale;
  const containerCursor = rotatingPieceId ? 'grabbing' : 'default';
  const measurePxLength = measure.line
    ? Math.hypot(measure.line.x2 - measure.line.x1, measure.line.y2 - measure.line.y1)
    : 0;

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
  ], [t]);

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
              clipX={activeTool === 'crop' ? 0 : sheet.crop.left}
              clipY={activeTool === 'crop' ? 0 : sheet.crop.top}
              clipWidth={activeTool === 'crop' ? sheetW : Math.max(1, sheetW - sheet.crop.left - sheet.crop.right)}
              clipHeight={activeTool === 'crop' ? sheetH : Math.max(1, sheetH - sheet.crop.top - sheet.crop.bottom)}
            >
              {sheetImg && (
                <KonvaImage id="bg" image={sheetImg} width={sheetW} height={sheetH} />
              )}
              {pieces.map(piece => (
                <PieceOutline
                  key={piece.id}
                  piece={piece}
                  isSelected={selectedPieceIds.includes(piece.id)}
                  effectiveScale={es}
                  onSelect={(multi) => onSelectPiece(piece.id, multi)}
                  onTransformChange={t => onTransformChange(piece.id, t)}
                  onRotateStart={() => setRotatingPieceId(piece.id)}
                />
              ))}
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
                  crop={sheet.crop}
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
        })()}
      </div>
    </div>
  );
}
