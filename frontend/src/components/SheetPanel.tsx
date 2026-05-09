import { useState, useRef, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Stage, Layer, Image as KonvaImage, Line, Group, Circle, Rect } from 'react-konva';
import useImage from 'use-image';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { Piece, GlassSheet, TextureTransform, Crop, Scale } from '../types';
import { computeCentroid } from '../utils/geometry';
import { toImageCoords, toScreenCoords } from '../utils/viewport';
import { Toolbar, SelectIcon, CropIcon, MeasureIcon, HandIcon } from './Toolbar';
import type { ToolId } from './Toolbar';
import { SelectAnimation, CropAnimation, MeasureAnimation, PanAnimation } from './ToolTooltipAnimations';
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
  onSelect?: (multi?: boolean) => void;
  onTransformChange?: (t: Partial<TextureTransform>, skipHistory?: boolean) => void;
  onRotateStart?: () => void;
  fillOnly?: boolean;
  strokeOnly?: boolean;
  handleOnly?: boolean;
  listening?: boolean;
}

function PieceOutline({
  piece, isSelected, effectiveScale, onSelect, onTransformChange, onRotateStart,
  fillOnly, strokeOnly, handleOnly, listening = true
}: PieceOutlineProps) {
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
    onSelect?.(e.evt.shiftKey);
  }

  function handleDragStart(e: KonvaEventObject<DragEvent>) {
    if (dragStartedFromHandle.current) {
      dragStartedFromHandle.current = false;
      e.target.stopDrag();
    }
  }

  function handleDragMove(e: KonvaEventObject<DragEvent>) {
    onTransformChange?.({ x: e.target.x(), y: e.target.y() }, true);
  }

  function handleDragEnd(e: KonvaEventObject<DragEvent>) {
    onTransformChange?.({ x: e.target.x(), y: e.target.y() }, false);
  }

  function handleRotateDown(e: KonvaEventObject<PointerEvent>) {
    e.cancelBubble = true;
    dragStartedFromHandle.current = true;
    onRotateStart?.();
  }

  return (
    <Group
      x={x} y={y}
      rotation={(rotation * 180) / Math.PI}
      scaleX={scale} scaleY={scale}
      draggable={isSelected && strokeOnly && !handleOnly}
      onClick={handleOnly ? undefined : handleClick}
      onTap={handleOnly ? undefined : handleClick}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
      onDragEnd={handleDragEnd}
      listening={listening}
    >
      {!handleOnly && (
        <Line
          points={relPts}
          stroke={fillOnly ? 'transparent' : (isSelected ? '#2563eb' : 'rgba(37,99,235,0.65)')}
          strokeWidth={isSelected ? STROKE_SELECTED / es : STROKE_IDLE / es}
          fill={strokeOnly ? 'transparent' : (isSelected ? 'rgba(37,99,235,0.10)' : 'rgba(37,99,235,0.04)')}
          closed
          hitStrokeWidth={strokeOnly ? 10 / es : 0}
        />
      )}
      {(handleOnly || (isSelected && strokeOnly && !fillOnly)) && (
        <>
          <Line
            points={[0, 0, 0, -handleOffset]}
            stroke="rgba(37,99,235,0.55)" strokeWidth={HANDLE_STEM / es}
            listening={false}
          />
          <Circle
            x={0} y={-handleOffset}
            radius={HANDLE_RADIUS / es}
            fill="#2563eb" stroke="white" strokeWidth={HANDLE_BORDER / es}
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
  onTransformChange: (pieceId: string, t: Partial<TextureTransform>, skipHistory?: boolean) => void;
  onCropChange: (c: Partial<Crop>) => void;
  onScaleChange: (s: Scale | null) => void;
  onImageLoad?: (w: number, h: number) => void;
}

export function SheetPanel({
  sheet, pieces, selectedPieceIds, onSelectPiece, onTransformChange, onCropChange, onScaleChange, onImageLoad,
}: SheetPanelProps) {
  const { t } = useTranslation();
  const [activeTool, setActiveTool] = useState<ToolId>('select');
  const [isSpaceDown, setIsSpaceDown] = useState(false);
  const [sheetImg] = useImage(sheet.imageUrl);
  const sheetW = sheetImg?.width ?? 800;
  const sheetH = sheetImg?.height ?? 600;

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;
      if (e.code === 'Space' && !e.repeat) {
        e.preventDefault();
        setIsSpaceDown(true);
        return;
      }
      if (e.key === 'v') handleToolChange('select');
      else if (e.key === 'h') handleToolChange('pan');
      else if (e.key === 'c') handleToolChange('crop');
      else if (e.key === 'm') handleToolChange('measure');
      else if (e.key === 'Escape') handleToolChange('select');
    }
    function handleKeyUp(e: KeyboardEvent) {
      if (e.code === 'Space') setIsSpaceDown(false);
    }
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTool]);

  useEffect(() => {
    if (sheetImg && onImageLoad) onImageLoad(sheetImg.width, sheetImg.height);
  }, [sheetImg]); // eslint-disable-line react-hooks/exhaustive-deps
  const vp = useViewport(sheetW, sheetH);
  const measure = useMeasure();
  const [marqueeBox, setMarqueeBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);

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
        onScaleChange({ pxPerUnit: px / 12, unit: 'in', line: { x1, y1, x2, y2 } });
      }
    }
  }, [sheet.id]); // eslint-disable-line react-hooks/exhaustive-deps

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
    const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);

    const isMiddleClick = e.evt && (e.evt as MouseEvent).button === 1;
    if (isMiddleClick || activeTool === 'pan' || isSpaceDown) {
      vp.startPan(ptr);
      return;
    }

    if (activeTool === 'select' && isBackground(e)) {
      setMarqueeBox({ x1: x, y1: y, x2: x, y2: y });
      return;
    }

    if (!isBackground(e)) return;
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
      const newRotation =
        Math.atan2(y - rotatingPiece.transform.y, x - rotatingPiece.transform.x) + Math.PI / 2;
      onTransformChange(rotatingPieceId!, { rotation: newRotation }, true);
      return;
    }

    vp.movePan(ptr);
  }

  function handlePointerUp() {
    if (marqueeBox) {
      const xmin = Math.min(marqueeBox.x1, marqueeBox.x2);
      const xmax = Math.max(marqueeBox.x1, marqueeBox.x2);
      const ymin = Math.min(marqueeBox.y1, marqueeBox.y2);
      const ymax = Math.max(marqueeBox.y1, marqueeBox.y2);

      const hitIds: string[] = [];
      pieces.forEach(p => {
        const { x, y } = computeCentroid(p.polygon);
        if (x >= xmin && x <= xmax && y >= ymin && y <= ymax) hitIds.push(p.id);
      });

      if (hitIds.length > 0) {
        hitIds.forEach((id, idx) => onSelectPiece(id, idx > 0));
      } else if (Math.abs(marqueeBox.x2 - marqueeBox.x1) < 2 && Math.abs(marqueeBox.y2 - marqueeBox.y1) < 2) {
        onSelectPiece(null);
      }
      setMarqueeBox(null);
      return;
    }

    if (rotatingPiece) {
      onTransformChange(rotatingPieceId!, { rotation: rotatingPiece.transform.rotation }, false);
    }
    setRotatingPieceId(null);
    vp.endPan();
  }

  function handleWheel(e: KonvaEventObject<WheelEvent>) {
    e.evt.preventDefault();
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;
    vp.handleWheel(e.evt, ptr);
  }

  function handleStageClick(e: KonvaEventObject<MouseEvent>) {
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
      onScaleChange({ pxPerUnit: newPxLen / 12, unit: 'in', line: { x1: nx1, y1: ny1, x2: nx2, y2: ny2 } });
    }
  }

  function handleToolChange(id: ToolId) {
    if (id === activeTool && id !== 'select') {
      setActiveTool('select');
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

      const defaultX1 = cropL + (cropR - cropL) * 0.25;
      const defaultX2 = cropL + (cropR - cropL) * 0.75;
      const defaultY = cropT + (cropB - cropT) * 0.5;

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
        onScaleChange({ pxPerUnit: px / 12, unit: 'in', line: { x1, y1, x2, y2 } });
      }
    }
    setActiveTool(id);
  }

  function setCursor(cursor: string) {
    if (vp.containerRef.current) vp.containerRef.current.style.cursor = cursor;
  }

  const es = vp.effectiveScale;
  const measurePxLength = measure.line
    ? Math.hypot(measure.line.x2 - measure.line.x1, measure.line.y2 - measure.line.y1)
    : 0;
  const isPanActive = activeTool === 'pan' || isSpaceDown;
  const containerCursor = rotatingPieceId ? 'grabbing' : isPanActive ? (vp.isPanning ? 'grabbing' : 'grab') : 'default';

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
          onWheel={handleWheel}
          onClick={handleStageClick}
        >
          <Layer>
            <Group x={vp.pan.x} y={vp.pan.y} scaleX={es} scaleY={es}>
              <Group
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
                    key={piece.id + '-fill'}
                    piece={piece}
                    isSelected={selectedPieceIds.includes(piece.id)}
                    effectiveScale={es}
                    fillOnly
                    listening={false}
                  />
                ))}
              </Group>

              {pieces.map(piece => (
                <PieceOutline
                  key={piece.id + '-stroke'}
                  piece={piece}
                  isSelected={selectedPieceIds.includes(piece.id)}
                  effectiveScale={es}
                  strokeOnly
                  onSelect={(multi) => onSelectPiece(piece.id, multi)}
                  onTransformChange={(t, skip) => onTransformChange(piece.id, t, skip)}
                />
              ))}

              {pieces.map(piece => {
                if (!selectedPieceIds.includes(piece.id)) return null;
                return (
                  <PieceOutline
                    key={piece.id + '-handle'}
                    piece={piece}
                    isSelected={true}
                    effectiveScale={es}
                    handleOnly
                    onRotateStart={() => setRotatingPieceId(piece.id)}
                  />
                );
              })}
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
            </Group>
            {marqueeBox && (
              <Rect
                x={Math.min(marqueeBox.x1, marqueeBox.x2) * es + vp.pan.x}
                y={Math.min(marqueeBox.y1, marqueeBox.y2) * es + vp.pan.y}
                width={Math.abs(marqueeBox.x2 - marqueeBox.x1) * es}
                height={Math.abs(marqueeBox.y2 - marqueeBox.y1) * es}
                fill="rgba(37,99,235,0.2)"
                stroke="#2563eb"
                strokeWidth={1}
                listening={false}
              />
            )}
          </Layer>
        </Stage>
        {activeTool === 'measure' && measure.line && (() => {
          const midX = (measure.line.x1 + measure.line.x2) / 2;
          const midY = (measure.line.y1 + measure.line.y2) / 2;
          const sc = toScreenCoords(midX, midY, vp.pan, vp.effectiveScale);
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
