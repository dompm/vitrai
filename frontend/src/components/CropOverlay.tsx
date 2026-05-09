import { Group, Rect, Line } from 'react-konva';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { Crop } from '../types';

interface Props {
  imageWidth: number;
  imageHeight: number;
  crop: Crop;
  effectiveScale: number;
  onCropChange: (c: Partial<Crop>) => void;
}

const DIM = 'rgba(0,0,0,0.42)';
const STROKE = '#2563eb';
const EDGE_HIT = 28;   // edge hit zone in display px
const ARM = 22;        // corner L-handle arm length in display px
const ARM_W = 4;       // corner arm thickness in display px
const CORNER_HIT = 20; // hit padding around each arm of the L in display px

interface CornerHandleProps {
  x: number;
  y: number;
  es: number;
  flipX: boolean;
  flipY: boolean;
  cursor: string;
  onDragMove: (e: KonvaEventObject<DragEvent>) => void;
  onCursorChange: (e: KonvaEventObject<MouseEvent>, cursor: string) => void;
}

function CornerHandle({ x, y, es, flipX, flipY, cursor, onDragMove, onCursorChange }: CornerHandleProps) {
  const arm = ARM / es;
  const w = ARM_W / es;
  const pad = CORNER_HIT / es;
  const sx = flipX ? -1 : 1;
  const sy = flipY ? -1 : 1;

  return (
    <Group
      x={x} y={y}
      draggable
      onDragMove={onDragMove}
      onMouseEnter={e => onCursorChange(e, cursor)}
      onMouseLeave={e => onCursorChange(e, 'default')}
    >
      {/* Horizontal arm hit area — follows the arm, doesn't bleed along the edge */}
      <Rect
        x={flipX ? -arm : 0}
        y={-pad / 2}
        width={arm}
        height={pad}
        fill="transparent"
      />
      {/* Vertical arm hit area — follows the arm, doesn't bleed along the edge */}
      <Rect
        x={-pad / 2}
        y={flipY ? -arm : 0}
        width={pad}
        height={arm}
        fill="transparent"
      />
      {/* L-shape: horizontal arm */}
      <Line
        points={[0, 0, sx * arm, 0]}
        stroke={STROKE}
        strokeWidth={w}
        lineCap="square"
        listening={false}
      />
      {/* L-shape: vertical arm */}
      <Line
        points={[0, 0, 0, sy * arm]}
        stroke={STROKE}
        strokeWidth={w}
        lineCap="square"
        listening={false}
      />
    </Group>
  );
}

export function CropOverlay({ imageWidth: W, imageHeight: H, crop, effectiveScale: es, onCropChange }: Props) {
  const ix = crop.left;
  const iy = crop.top;
  const iw = W - crop.left - crop.right;
  const ih = H - crop.top - crop.bottom;

  function setCursor(e: KonvaEventObject<MouseEvent>, cursor: string) {
    const c = e.target.getStage()?.container();
    if (c) c.style.cursor = cursor;
  }

  return (
    <Group>
      {/* Dim bands outside the crop rect */}
      <Rect x={0} y={0} width={W} height={iy} fill={DIM} listening={false} />
      <Rect x={0} y={iy + ih} width={W} height={H - iy - ih} fill={DIM} listening={false} />
      <Rect x={0} y={iy} width={ix} height={ih} fill={DIM} listening={false} />
      <Rect x={ix + iw} y={iy} width={W - ix - iw} height={ih} fill={DIM} listening={false} />

      {/* Edge handles */}
      <Line
        x={0} y={crop.top}
        points={[0, 0, W, 0]}
        stroke={STROKE} strokeWidth={2 / es} hitStrokeWidth={EDGE_HIT / es}
        draggable
        onDragMove={e => {
          const y = Math.max(0, Math.min(H - crop.bottom - 20, e.target.y()));
          e.target.x(0); e.target.y(y);
          onCropChange({ top: Math.round(y) });
        }}
        onMouseEnter={e => setCursor(e, 'ns-resize')}
        onMouseLeave={e => setCursor(e, 'default')}
      />
      <Line
        x={0} y={H - crop.bottom}
        points={[0, 0, W, 0]}
        stroke={STROKE} strokeWidth={2 / es} hitStrokeWidth={EDGE_HIT / es}
        draggable
        onDragMove={e => {
          const y = Math.max(crop.top + 20, Math.min(H, e.target.y()));
          e.target.x(0); e.target.y(y);
          onCropChange({ bottom: Math.round(H - y) });
        }}
        onMouseEnter={e => setCursor(e, 'ns-resize')}
        onMouseLeave={e => setCursor(e, 'default')}
      />
      <Line
        x={crop.left} y={0}
        points={[0, 0, 0, H]}
        stroke={STROKE} strokeWidth={2 / es} hitStrokeWidth={EDGE_HIT / es}
        draggable
        onDragMove={e => {
          const x = Math.max(0, Math.min(W - crop.right - 20, e.target.x()));
          e.target.x(x); e.target.y(0);
          onCropChange({ left: Math.round(x) });
        }}
        onMouseEnter={e => setCursor(e, 'ew-resize')}
        onMouseLeave={e => setCursor(e, 'default')}
      />
      <Line
        x={W - crop.right} y={0}
        points={[0, 0, 0, H]}
        stroke={STROKE} strokeWidth={2 / es} hitStrokeWidth={EDGE_HIT / es}
        draggable
        onDragMove={e => {
          const x = Math.max(crop.left + 20, Math.min(W, e.target.x()));
          e.target.x(x); e.target.y(0);
          onCropChange({ right: Math.round(W - x) });
        }}
        onMouseEnter={e => setCursor(e, 'ew-resize')}
        onMouseLeave={e => setCursor(e, 'default')}
      />

      {/* Corner handles — drag both axes simultaneously */}
      <CornerHandle
        x={ix} y={iy} es={es} flipX={false} flipY={false} cursor="nwse-resize"
        onCursorChange={setCursor}
        onDragMove={e => {
          const x = Math.max(0, Math.min(W - crop.right - 20, e.target.x()));
          const y = Math.max(0, Math.min(H - crop.bottom - 20, e.target.y()));
          e.target.x(x); e.target.y(y);
          onCropChange({ left: Math.round(x), top: Math.round(y) });
        }}
      />
      <CornerHandle
        x={ix + iw} y={iy} es={es} flipX={true} flipY={false} cursor="nesw-resize"
        onCursorChange={setCursor}
        onDragMove={e => {
          const x = Math.max(crop.left + 20, Math.min(W, e.target.x()));
          const y = Math.max(0, Math.min(H - crop.bottom - 20, e.target.y()));
          e.target.x(x); e.target.y(y);
          onCropChange({ right: Math.round(W - x), top: Math.round(y) });
        }}
      />
      <CornerHandle
        x={ix} y={iy + ih} es={es} flipX={false} flipY={true} cursor="nesw-resize"
        onCursorChange={setCursor}
        onDragMove={e => {
          const x = Math.max(0, Math.min(W - crop.right - 20, e.target.x()));
          const y = Math.max(crop.top + 20, Math.min(H, e.target.y()));
          e.target.x(x); e.target.y(y);
          onCropChange({ left: Math.round(x), bottom: Math.round(H - y) });
        }}
      />
      <CornerHandle
        x={ix + iw} y={iy + ih} es={es} flipX={true} flipY={true} cursor="nwse-resize"
        onCursorChange={setCursor}
        onDragMove={e => {
          const x = Math.max(crop.left + 20, Math.min(W, e.target.x()));
          const y = Math.max(crop.top + 20, Math.min(H, e.target.y()));
          e.target.x(x); e.target.y(y);
          onCropChange({ right: Math.round(W - x), bottom: Math.round(H - y) });
        }}
      />
    </Group>
  );
}
