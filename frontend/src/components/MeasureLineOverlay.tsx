import { useRef } from 'react';
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
  onDragEnd?: (x1: number, y1: number, x2: number, y2: number) => void;
}

export function MeasureLineOverlay({
  line, effectiveScale: es, imageWidth: W, imageHeight: H,
  onUpdateP1, onUpdateP2, onCursorChange, onDragEnd,
}: Props) {
  const { x1, y1, x2, y2 } = line;

  const dragStart = useRef<{ x1: number; y1: number; x2: number; y2: number } | null>(null);

  function clampedDrag(e: KonvaEventObject<DragEvent>, onUpdate: (x: number, y: number) => void) {
    const x = Math.max(0, Math.min(W, e.target.x()));
    const y = Math.max(0, Math.min(H, e.target.y()));
    e.target.x(x);
    e.target.y(y);
    onUpdate(x, y);
  }

  function handleGroupDragStart(e: KonvaEventObject<DragEvent>) {
    if (e.target.name() !== 'measure-group') return;
    dragStart.current = { x1, y1, x2, y2 };
  }

  function handleGroupDragEnd(e: KonvaEventObject<DragEvent>) {
    if (e.target.name() !== 'measure-group' || !dragStart.current) return;
    const dx = e.target.x();
    const dy = e.target.y();
    const nx1 = dragStart.current.x1 + dx;
    const ny1 = dragStart.current.y1 + dy;
    const nx2 = dragStart.current.x2 + dx;
    const ny2 = dragStart.current.y2 + dy;
    onUpdateP1(nx1, ny1);
    onUpdateP2(nx2, ny2);
    onDragEnd?.(nx1, ny1, nx2, ny2);
    e.target.position({ x: 0, y: 0 });
    dragStart.current = null;
  }

  return (
    <Group name="measure-group" draggable onDragStart={handleGroupDragStart} onDragEnd={handleGroupDragEnd}>
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
        onDragEnd={e => {
          e.cancelBubble = true;
          const fx = Math.max(0, Math.min(W, e.target.x()));
          const fy = Math.max(0, Math.min(H, e.target.y()));
          onDragEnd?.(fx, fy, x2, y2);
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
        onDragEnd={e => {
          e.cancelBubble = true;
          const fx = Math.max(0, Math.min(W, e.target.x()));
          const fy = Math.max(0, Math.min(H, e.target.y()));
          onDragEnd?.(x1, y1, fx, fy);
        }}
      />
    </Group>
  );
}
