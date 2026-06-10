// Custom robust polygon intersection logic

export type Point = { x: number; y: number };
export type Polygon = Point[];

export interface NestingResult {
  x: number;
  y: number;
  rotation: number;
}

// Check if two line segments intersect
function segmentsIntersect(p1: Point, p2: Point, p3: Point, p4: Point): boolean {
  const ccw = (A: Point, B: Point, C: Point) => (C.y - A.y) * (B.x - A.x) > (B.y - A.y) * (C.x - A.x);
  return ccw(p1, p3, p4) !== ccw(p2, p3, p4) && ccw(p1, p2, p3) !== ccw(p1, p2, p4);
}

// Ray-casting algorithm for point in polygon
function pointInPolygon(point: Point, vs: Polygon): boolean {
  let inside = false;
  for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
    const xi = vs[i].x, yi = vs[i].y;
    const xj = vs[j].x, yj = vs[j].y;
    const intersect = ((yi > point.y) !== (yj > point.y)) && 
                      (point.x < (xj - xi) * (point.y - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

// Squared distance from point p to segment ab
function pointSegDist2(p: Point, a: Point, b: Point): number {
  const abx = b.x - a.x, aby = b.y - a.y;
  const apx = p.x - a.x, apy = p.y - a.y;
  const len2 = abx * abx + aby * aby;
  const t = len2 > 0 ? Math.max(0, Math.min(1, (apx * abx + apy * aby) / len2)) : 0;
  const dx = apx - t * abx, dy = apy - t * aby;
  return dx * dx + dy * dy;
}

// True if the polygons overlap, one contains the other, or (gapPx > 0) any
// pair of edges comes closer than gapPx — the cutting clearance the glass
// cutter needs between pieces.
function polygonsConflict(poly1: Polygon, poly2: Polygon, gapPx: number): boolean {
  const gap2 = gapPx > 0 ? gapPx * gapPx : 0;
  // 1. Edge intersections / proximity. Checking each vertex of one polygon
  // against each edge of the other (both directions) covers the minimum
  // distance between non-crossing segments.
  for (let i = 0; i < poly1.length; i++) {
    const p1 = poly1[i];
    const p2 = poly1[(i + 1) % poly1.length];
    for (let j = 0; j < poly2.length; j++) {
      const p3 = poly2[j];
      const p4 = poly2[(j + 1) % poly2.length];
      if (segmentsIntersect(p1, p2, p3, p4)) return true;
      if (gap2 > 0 && (pointSegDist2(p1, p3, p4) < gap2 || pointSegDist2(p3, p1, p2) < gap2)) return true;
    }
  }

  // 2. Poly1 inside Poly2 (test first vertex)
  if (poly1.length > 0 && pointInPolygon(poly1[0], poly2)) return true;

  // 3. Poly2 inside Poly1 (test first vertex)
  if (poly2.length > 0 && pointInPolygon(poly2[0], poly1)) return true;

  return false;
}

// Check if poly is completely inside the bin
// (Removed polygonInsideBin as it's redundant for rectangular bins when bounding box is clamped)

// Rotate a polygon around the origin (0,0)
function rotatePolygon(poly: Polygon, angleRad: number): Polygon {
  if (angleRad === 0) return poly;
  const cos = Math.cos(angleRad);
  const sin = Math.sin(angleRad);
  return poly.map(p => ({
    x: p.x * cos - p.y * sin,
    y: p.x * sin + p.y * cos
  }));
}

// Translate a polygon
function translatePolygon(poly: Polygon, dx: number, dy: number): Polygon {
  return poly.map(p => ({
    x: p.x + dx,
    y: p.y + dy
  }));
}

function getBoundingBox(poly: Polygon) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const p of poly) {
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }
  return { minX, minY, maxX, maxY, w: maxX - minX, h: maxY - minY };
}

// A simple geometry math function to find the best placement for a new polygon
// against a list of already placed polygons and a bin boundary.
export function findBestPlacement(
  polyToPlace: Polygon,
  placedPolys: Polygon[],
  bin: Polygon,
  allowRotations: boolean,
  gapPx: number
): NestingResult | null {
  // Try different rotations: 0, 90, 180, 270 degrees if allowed
  const rotations = allowRotations ? [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2] : [0];
  
  const binBounds = getBoundingBox(bin);
  
  let bestResult: NestingResult | null = null;
  let bestScore = Infinity; // We want to minimize Y, then minimize X (bottom-left fit or top-left fit)
  
  // We'll search on a grid to approximate NFP boundaries.
  // The smaller the grid, the more precise but slower. We can adapt step size based on piece size.
  const step = Math.max(5, Math.min(binBounds.w, binBounds.h) * 0.02);

  for (const rotation of rotations) {
    const rotatedBase = rotatePolygon(polyToPlace, rotation);
    const bounds = getBoundingBox(rotatedBase);
    
    // Scan possible translation vectors
    // Ensure the piece's bounding box stays strictly within the bin
    const startY = binBounds.minY - bounds.minY + gapPx;
    const endY = binBounds.maxY - bounds.maxY - gapPx;
    const startX = binBounds.minX - bounds.minX + gapPx;
    const endX = binBounds.maxX - bounds.maxX - gapPx;

    for (let ty = startY; ty <= endY; ty += step) {
      for (let tx = startX; tx <= endX; tx += step) {
        // Fast bounding box rejection against placed pieces, inflated by
        // gapPx so the exact check also sees near-misses within the gap.
        const translatedBB = {
          minX: tx + bounds.minX - gapPx,
          minY: ty + bounds.minY - gapPx,
          maxX: tx + bounds.maxX + gapPx,
          maxY: ty + bounds.maxY + gapPx
        };

        let exactConflict = false;

        for (const placed of placedPolys) {
          const pBB = getBoundingBox(placed);
          // If (inflated) bounding boxes overlap, test exact polygon
          // intersection plus the cutting-gap clearance
          if (
            translatedBB.minX < pBB.maxX &&
            translatedBB.maxX > pBB.minX &&
            translatedBB.minY < pBB.maxY &&
            translatedBB.maxY > pBB.minY
          ) {
            const testPoly = translatePolygon(rotatedBase, tx, ty);
            if (polygonsConflict(testPoly, placed, gapPx)) {
              exactConflict = true;
              break;
            }
          }
        }
        
        if (exactConflict) continue;
        
        // Score: Top-Left gravity (minimize Y primarily, X secondarily)
        // or Bottom-Left. Let's do Top-Left to match the previous shelf heuristic gravity.
        const score = ty * 1000 + tx;
        if (score < bestScore) {
          bestScore = score;
          bestResult = { x: tx, y: ty, rotation };
        }
      }
      // Early exit if we found a very good row (optional optimization)
      // if (bestResult && ty > bestResult.y + step * 2) break; 
    }
  }

  return bestResult;
}
