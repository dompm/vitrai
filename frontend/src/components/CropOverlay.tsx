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
const HIT = 18; // visual hit width in display px

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

      {/* Top handle */}
      <Line
        x={0} y={crop.top}
        points={[0, 0, W, 0]}
        stroke={STROKE} strokeWidth={2 / es} hitStrokeWidth={HIT / es}
        draggable
        onDragMove={(e: KonvaEventObject<DragEvent>) => {
          const y = Math.max(0, Math.min(H - crop.bottom - 20, e.target.y()));
          e.target.y(y);
          onCropChange({ top: Math.round(y) });
        }}
        onMouseEnter={(e: KonvaEventObject<MouseEvent>) => setCursor(e, 'ns-resize')}
        onMouseLeave={(e: KonvaEventObject<MouseEvent>) => setCursor(e, 'default')}
      />

      {/* Bottom handle */}
      <Line
        x={0} y={H - crop.bottom}
        points={[0, 0, W, 0]}
        stroke={STROKE} strokeWidth={2 / es} hitStrokeWidth={HIT / es}
        draggable
        onDragMove={(e: KonvaEventObject<DragEvent>) => {
          const y = Math.max(crop.top + 20, Math.min(H, e.target.y()));
          e.target.y(y);
          onCropChange({ bottom: Math.round(H - y) });
        }}
        onMouseEnter={(e: KonvaEventObject<MouseEvent>) => setCursor(e, 'ns-resize')}
        onMouseLeave={(e: KonvaEventObject<MouseEvent>) => setCursor(e, 'default')}
      />

      {/* Left handle */}
      <Line
        x={crop.left} y={0}
        points={[0, 0, 0, H]}
        stroke={STROKE} strokeWidth={2 / es} hitStrokeWidth={HIT / es}
        draggable
        onDragMove={(e: KonvaEventObject<DragEvent>) => {
          const x = Math.max(0, Math.min(W - crop.right - 20, e.target.x()));
          e.target.x(x);
          onCropChange({ left: Math.round(x) });
        }}
        onMouseEnter={(e: KonvaEventObject<MouseEvent>) => setCursor(e, 'ew-resize')}
        onMouseLeave={(e: KonvaEventObject<MouseEvent>) => setCursor(e, 'default')}
      />

      {/* Right handle */}
      <Line
        x={W - crop.right} y={0}
        points={[0, 0, 0, H]}
        stroke={STROKE} strokeWidth={2 / es} hitStrokeWidth={HIT / es}
        draggable
        onDragMove={(e: KonvaEventObject<DragEvent>) => {
          const x = Math.max(crop.left + 20, Math.min(W, e.target.x()));
          e.target.x(x);
          onCropChange({ right: Math.round(W - x) });
        }}
        onMouseEnter={(e: KonvaEventObject<MouseEvent>) => setCursor(e, 'ew-resize')}
        onMouseLeave={(e: KonvaEventObject<MouseEvent>) => setCursor(e, 'default')}
      />
    </Group>
  );
}
