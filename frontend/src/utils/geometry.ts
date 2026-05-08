export function computeCentroid(polygon: [number, number][]): { x: number; y: number } {
  const x = polygon.reduce((s, p) => s + p[0], 0) / polygon.length;
  const y = polygon.reduce((s, p) => s + p[1], 0) / polygon.length;
  return { x, y };
}
