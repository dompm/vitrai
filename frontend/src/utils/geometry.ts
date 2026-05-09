import polygonClipping from 'polygon-clipping';

export function computeCentroid(polygon: [number, number][]): { x: number; y: number } {
  const x = polygon.reduce((s, p) => s + p[0], 0) / polygon.length;
  const y = polygon.reduce((s, p) => s + p[1], 0) / polygon.length;
  return { x, y };
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
