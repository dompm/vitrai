import { Line, Circle, Group } from 'react-konva';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { MeasureLine } from '../hooks/useMeasure';
import type { Crop } from '../types';

interface Props {
  line: MeasureLine;
  effectiveScale: number;
  imageWidth: number;
  imageHeight: number;
  crop: Crop;
  onUpdateP1: (x: number, y: number) => void;
  onUpdateP2: (x: number, y: number) => void;
  onCursorChange: (cursor: string) => void;
}

export function MeasureLineOverlay({
  line, effectiveScale: es, imageWidth: W, imageHeight: H, crop,
  onUpdateP1, onUpdateP2, onCursorChange,
}: Props) {
  const { x1, y1, x2, y2 } = line;

  const minX = crop.left;
  const maxX = W - crop.right;
  const minY = crop.top;
  const maxY = H - crop.bottom;

  function clampedDrag(e: KonvaEventObject<DragEvent>, onUpdate: (x: number, y: number) => void) {
    const x = Math.max(minX, Math.min(maxX, e.target.x()));
    const y = Math.max(minY, Math.min(maxY, e.target.y()));
    e.target.x(x);
    e.target.y(y);
    onUpdate(x, y);
  }

  function handleGroupDrag(e: KonvaEventObject<DragEvent>) {
    if (e.target.name() !== 'measure-group') return;
    const dx = e.target.x();
    const dy = e.target.y();
    onUpdateP1(x1 + dx, y1 + dy);
    onUpdateP2(x2 + dx, y2 + dy);
    e.target.position({ x: 0, y: 0 });
  }

  return (
    <Group name="measure-group" draggable onDragMove={handleGroupDrag}>
      {/* Thick invisible hit area for the line */}
      <Line
        points={[x1, y1, x2, y2]}
        stroke="transparent"
        strokeWidth={20 / es}
        onMouseEnter={() => onCursorChange('move')}
        onMouseLeave={() => onCursorChange('default')}
      />
      <Line
        points={[x1, y1, x2, y2]}
        stroke="#f59e0b" strokeWidth={2 / es}
        dash={[6 / es, 3 / es]} listening={false}
      />
      <Circle
        x={x1} y={y1} radius={7 / es}
        fill="#f59e0b" stroke="white" strokeWidth={1.5 / es}
        draggable
        onMouseEnter={() => onCursorChange('move')}
        onMouseLeave={() => onCursorChange('default')}
        onDragMove={e => {
          e.cancelBubble = true;
          clampedDrag(e, onUpdateP1);
        }}
      />
      <Circle
        x={x2} y={y2} radius={7 / es}
        fill="#f59e0b" stroke="white" strokeWidth={1.5 / es}
        draggable
        onMouseEnter={() => onCursorChange('move')}
        onMouseLeave={() => onCursorChange('default')}
        onDragMove={e => {
          e.cancelBubble = true;
          clampedDrag(e, onUpdateP2);
        }}
      />
    </Group>
  );
}
