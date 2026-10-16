import { Line } from 'react-konva';
import { CANVAS } from '../../theme';
import { PencilController, usePencilSnapshot } from '../../editor/interaction/pencilController';

export function PencilOverlay({ controller, effectiveScale }: { controller: PencilController; effectiveScale: number }) {
  const snapshot = usePencilSnapshot(controller);
  if (snapshot.flatPoints.length === 0) return null;
  return (
    <Line
      points={snapshot.flatPoints as number[]}
      stroke={CANVAS.amber}
      strokeWidth={2.5 / effectiveScale}
      lineJoin="round"
      lineCap="round"
      dash={[4 / effectiveScale, 3 / effectiveScale]}
      listening={false}
    />
  );
}
