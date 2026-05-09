import { useState } from 'react';

export type MeasureLine = { x1: number; y1: number; x2: number; y2: number };

export function useMeasure() {
  const [line, setLine] = useState<MeasureLine | null>(null);

  function loadLine(l: MeasureLine) { setLine({ ...l }); }
  function updateP1(x: number, y: number) { setLine(l => l ? { ...l, x1: x, y1: y } : null); }
  function updateP2(x: number, y: number) { setLine(l => l ? { ...l, x2: x, y2: y } : null); }
  function reset() { setLine(null); }

  return { line, loadLine, updateP1, updateP2, reset };
}
