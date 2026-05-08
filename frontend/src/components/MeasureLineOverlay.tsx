import { Line, Circle, Group } from 'react-konva';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { MeasureLine } from '../hooks/useMeasure';

interface Props {
  line: MeasureLine;
  effectiveScale: number;
  imageWidth: number;
  imageHeight: number;
  onUpdateP1: (x: number, y: number) => void;
  onUpdateP2: (x: number, y: number) => void;
  onCursorChange: (cursor: string) => void;
}

export function MeasureLineOverlay({
  line, effectiveScale: es, imageWidth: W, imageHeight: H,
  onUpdateP1, onUpdateP2, onCursorChange,
}: Props) {
  const { x1, y1, x2, y2 } = line;

  function clampedDrag(e: KonvaEventObject<DragEvent>, onUpdate: (x: number, y: number) => void) {
    const x = Math.max(0, Math.min(W, e.target.x()));
    const y = Math.max(0, Math.min(H, e.target.y()));
    e.target.x(x);
    e.target.y(y);
    onUpdate(x, y);
  }

  return (
    <Group>
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
        onDragMove={e => clampedDrag(e, onUpdateP1)}
      />
      <Circle
        x={x2} y={y2} radius={7 / es}
        fill="#f59e0b" stroke="white" strokeWidth={1.5 / es}
        draggable
        onMouseEnter={() => onCursorChange('move')}
        onMouseLeave={() => onCursorChange('default')}
        onDragMove={e => clampedDrag(e, onUpdateP2)}
      />
    </Group>
  );
}
