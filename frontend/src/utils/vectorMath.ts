export type VectorPoint = [number, number];

export interface VectorBounds {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export function isPointWithinBounds(
  point: VectorPoint,
  bounds: VectorBounds,
  padding = 0,
): boolean {
  return point[0] >= bounds.left - padding
    && point[0] <= bounds.right + padding
    && point[1] >= bounds.top - padding
    && point[1] <= bounds.bottom + padding;
}

/** Constrain a point to the nearest angular increment around an origin. */
export function constrainToAngle(
  cursor: VectorPoint,
  origin: VectorPoint,
  increment = Math.PI / 4,
): VectorPoint {
  const dx = cursor[0] - origin[0];
  const dy = cursor[1] - origin[1];
  const radius = Math.hypot(dx, dy);
  const theta = Math.round(Math.atan2(dy, dx) / increment) * increment;
  return [origin[0] + radius * Math.cos(theta), origin[1] + radius * Math.sin(theta)];
}

/** Pick the closest candidate in screen space, with stable value tie-breaking. */
export function nearestCandidate<T extends { value: number; position: number }>(
  target: number,
  candidates: T[],
  effectiveScale: number,
  tolerancePx: number,
): T | null {
  const safeScale = Math.max(effectiveScale, Number.EPSILON);
  const tolerance = tolerancePx / safeScale;
  return candidates
    .map(candidate => ({ candidate, distance: Math.abs(target - candidate.position) }))
    .filter(item => item.distance < tolerance)
    .sort((a, b) => a.distance - b.distance || a.candidate.value - b.candidate.value)[0]?.candidate ?? null;
}
