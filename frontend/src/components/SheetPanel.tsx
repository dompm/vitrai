import { useState, useRef, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Stage, Layer, Image as KonvaImage, Line, Group, Circle, Text } from 'react-konva';
import useImage from 'use-image';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { Piece, GlassSheet, TextureTransform, Crop, Scale } from '../types';
import { computeCentroid } from '../utils/geometry';
import { toImageCoords, toScreenCoords } from '../utils/viewport';
import { Toolbar, SelectIcon, CropIcon, MeasureIcon, HandIcon, CornersIcon } from './Toolbar';
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
  listening?: boolean;
}

function PieceOutline({
  piece, isSelected, effectiveScale, onSelect, onTransformChange, onRotateStart,
  fillOnly, strokeOnly, listening = true
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
      draggable={isSelected && strokeOnly}
      onClick={handleClick} onTap={handleClick}
      onDragStart={handleDragStart}
      onDragMove={handleDragMove}
      onDragEnd={handleDragEnd}
      listening={listening}
    >
      <Line
        points={relPts}
        stroke={fillOnly ? 'transparent' : (isSelected ? '#2563eb' : 'rgba(37,99,235,0.65)')}
        strokeWidth={isSelected ? STROKE_SELECTED / es : STROKE_IDLE / es}
        fill={strokeOnly ? 'transparent' : (isSelected ? 'rgba(37,99,235,0.10)' : 'rgba(37,99,235,0.04)')}
        closed
        hitStrokeWidth={strokeOnly ? 10 / es : 0}
      />
      {isSelected && strokeOnly && (
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
  onCornersChange: (corners: [[number, number], [number, number], [number, number], [number, number]] | undefined) => void;
  onWarpRequest: () => void;
  isWarping?: boolean;
}

export function SheetPanel({
  sheet, pieces, selectedPieceIds, onSelectPiece, onTransformChange, onCropChange, onScaleChange, onImageLoad,
  onCornersChange, onWarpRequest, isWarping,
}: SheetPanelProps) {
  const { t } = useTranslation();
  const [activeTool, setActiveTool] = useState<ToolId>('select');
  const [isSpaceDown, setIsSpaceDown] = useState(false);
  const [sheetImg] = useImage(sheet.warpedImageUrl ?? sheet.imageUrl);
  const sheetW = sheetImg?.width ?? 800;
  const sheetH = sheetImg?.height ?? 600;

  // Local corner state: synced from sheet.corners when entering corners tool
  const [localCorners, setLocalCorners] = useState<[[number, number], [number, number], [number, number], [number, number]] | null>(null);

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
      else if (e.key === 'k') handleToolChange('corners');
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
    if (isMiddleClick || activeTool === 'pan' || isSpaceDown) {
      vp.startPan(ptr);
      return;
    }

    if (!isBackground(e)) return;
    vp.startPan(ptr);
  }

  function handleCornerDragMove(idx: number, e: KonvaEventObject<DragEvent>) {
    if (!localCorners) return;
    const next = localCorners.map((c, i) =>
      i === idx ? [e.target.x(), e.target.y()] as [number, number] : c
    ) as [[number, number], [number, number], [number, number], [number, number]];
    setLocalCorners(next);
  }

  function handleCornerDragEnd(idx: number, e: KonvaEventObject<DragEvent>) {
    if (!localCorners) return;
    const next = localCorners.map((c, i) =>
      i === idx ? [e.target.x(), e.target.y()] as [number, number] : c
    ) as [[number, number], [number, number], [number, number], [number, number]];
    setLocalCorners(next);
    onCornersChange(next);
  }

  function handlePointerMove(e: KonvaEventObject<PointerEvent>) {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;

    if (rotatingPiece) {
      const { x, y } = toImageCoords(ptr, vp.pan, vp.effectiveScale);
      const newRotation =
        Math.atan2(y - rotatingPiece.transform.y, x - rotatingPiece.transform.x) + Math.PI / 2;
      onTransformChange(rotatingPieceId!, { rotation: newRotation }, true);
      return;
    }

    vp.movePan(ptr);
  }

  function handlePointerUp() {
    if (rotatingPiece) {
      onTransformChange(rotatingPieceId!, { rotation: rotatingPiece.transform.rotation }, false);
    }
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
    if (id === activeTool && id !== 'select') {
      setActiveTool('select');
      if (id === 'measure') measure.reset();
      if (id === 'corners') setLocalCorners(null);
      return;
    }

    if (activeTool === 'measure' && id !== 'measure') measure.reset();
    if (activeTool === 'corners' && id !== 'corners') setLocalCorners(null);

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
    }

    if (id === 'corners') {
      // Load saved corners or default to near-image-boundary quad
      const saved = sheet.corners;
      const pad = Math.min(sheetW, sheetH) * 0.1;
      setLocalCorners(saved ?? [
        [pad, pad],
        [sheetW - pad, pad],
        [sheetW - pad, sheetH - pad],
        [pad, sheetH - pad],
      ]);
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
  const containerCursor = rotatingPieceId ? 'grabbing' : isPanActive ? (vp.isPanning ? 'grabbing' : 'grab') : activeTool === 'corners' ? 'default' : 'default';

  const CORNER_RADIUS = 8;
  const CORNER_LABELS = ['1', '2', '3', '4'];

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
        name: t('tooltipScaleName'),
        shortcut: 'M',
        description: t('tooltipScaleDescSheet'),
        animation: <MeasureAnimation />,
      },
    },
    {
      id: 'corners' as ToolId,
      label: t('toolCorners'),
      icon: <CornersIcon />,
      tooltip: {
        name: t('tooltipCornersName'),
        shortcut: 'K',
        description: t('tooltipCornersDesc'),
        animation: <CornersIcon />,
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
            <Group x={vp.pan.x} y={vp.pan.y} scaleX={es} scaleY={es}>
              {/* Only the image and piece fills are clipped by the crop zone (unless we're actively cropping) */}
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

              {/* Outlines and tools are visible everywhere */}
              {pieces.map(piece => (
                <PieceOutline
                  key={piece.id}
                  piece={piece}
                  isSelected={selectedPieceIds.includes(piece.id)}
                  effectiveScale={es}
                  strokeOnly
                  onSelect={(multi) => onSelectPiece(piece.id, multi)}
                  onTransformChange={(t, skip) => onTransformChange(piece.id, t, skip)}
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
              {activeTool === 'corners' && localCorners && (() => {
                const pts = localCorners;
                const flatPts = pts.flatMap(([x, y]) => [x, y]);
                const r = CORNER_RADIUS / es;
                return (
                  <Group>
                    <Line
                      points={flatPts}
                      stroke="#f59e0b"
                      strokeWidth={2 / es}
                      closed
                      dash={[6 / es, 4 / es]}
                      listening={false}
                    />
                    {pts.map(([cx, cy], idx) => (
                      <Group key={idx}
                        x={cx} y={cy}
                        draggable
                        onDragMove={e => handleCornerDragMove(idx, e)}
                        onDragEnd={e => handleCornerDragEnd(idx, e)}
                      >
                        <Circle
                          radius={r}
                          fill="#f59e0b"
                          stroke="white"
                          strokeWidth={1.5 / es}
                        />
                        <Text
                          text={CORNER_LABELS[idx]}
                          fontSize={10 / es}
                          fill="white"
                          fontStyle="bold"
                          offsetX={3 / es}
                          offsetY={5 / es}
                          listening={false}
                        />
                      </Group>
                    ))}
                  </Group>
                );
              })()}
            </Group>
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
        {activeTool === 'corners' && (
          <div style={{
            position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)',
            display: 'flex', gap: 8, zIndex: 10,
          }}>
            {sheet.warpedImageUrl && (
              <button
                className="btn-ghost"
                style={{ fontSize: '0.8rem', padding: '5px 12px', color: '#dc2626', borderColor: '#fca5a5' }}
                onClick={() => { onCornersChange(undefined); handleToolChange('select'); }}
              >
                {t('clearWarp')}
              </button>
            )}
            <button
              className="btn-ghost"
              style={{ fontSize: '0.8rem', padding: '5px 12px', opacity: isWarping ? 0.6 : 1 }}
              disabled={!localCorners || !!isWarping}
              onClick={() => { if (localCorners) onCornersChange(localCorners); onWarpRequest(); }}
            >
              {isWarping ? t('applyingWarp') : t('applyWarp')}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
