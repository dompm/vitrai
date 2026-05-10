import polygonClipping from 'polygon-clipping';

export function computeCentroid(polygon: [number, number][]): { x: number; y: number } {
  const x = polygon.reduce((s, p) => s + p[0], 0) / polygon.length;
  const y = polygon.reduce((s, p) => s + p[1], 0) / polygon.length;
  return { x, y };
}

export function smoothPolygon(pts: [number, number][]): [number, number][] {
  if (pts.length < 3) return pts;
  const n = pts.length;
  const out: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const [cx, cy] = pts[i];
    const [nx, ny] = pts[(i + 1) % n];
    out.push([cx * 0.75 + nx * 0.25, cy * 0.75 + ny * 0.25]);
    out.push([cx * 0.25 + nx * 0.75, cy * 0.25 + ny * 0.75]);
  }
  return out;
}

export function snapPolygonToNeighbors(
  polygon: [number, number][],
  neighbors: [number, number][][],
  radius: number,
): [number, number][] {
  if (neighbors.length === 0 || polygon.length < 3) return polygon;
  const r2 = radius * radius;

  return polygon.map(([px, py]) => {
    let bestD2 = r2;
    let bestX = px, bestY = py;
    for (const nb of neighbors) {
      for (let i = 0; i < nb.length; i++) {
        const [ax, ay] = nb[i];
        const [bx, by] = nb[(i + 1) % nb.length];
        const dx = bx - ax, dy = by - ay;
        const len2 = dx * dx + dy * dy;
        let t = 0;
        if (len2 > 0) {
          t = ((px - ax) * dx + (py - ay) * dy) / len2;
          if (t < 0) t = 0; else if (t > 1) t = 1;
        }
        const cx = ax + t * dx, cy = ay + t * dy;
        const ex = px - cx, ey = py - cy;
        const d2 = ex * ex + ey * ey;
        if (d2 < bestD2) { bestD2 = d2; bestX = cx; bestY = cy; }
      }
    }
    return [bestX, bestY] as [number, number];
  });
}

export function subtractPolygons(subject: [number, number][], clipPolygons: [number, number][][]): [number, number][] {
  if (clipPolygons.length === 0) return subject;
  
  try {
    const subjPoly = [subject];
    const clipPolys = clipPolygons.map(p => [p]);
    
    const diff = polygonClipping.difference(subjPoly, ...clipPolys);
    
    if (diff.length === 0) return [];
    
    let largestRing: [number, number][] = [];
    let maxArea = -1;
    
    for (const multi of diff) {
      const ring = multi[0];
      let area = 0;
      for (let i = 0; i < ring.length - 1; i++) {
        area += ring[i][0] * ring[i+1][1] - ring[i+1][0] * ring[i][1];
      }
      area = Math.abs(area) / 2;
      
      if (area > maxArea) {
        maxArea = area;
        largestRing = ring as [number, number][];
      }
    }
    
    return largestRing;
  } catch (e) {
    console.warn("Clipping failed", e);
    return subject;
  }
}
