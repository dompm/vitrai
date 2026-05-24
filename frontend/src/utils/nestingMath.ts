import pc from 'polygon-clipping';
import type { Pair } from 'polygon-clipping';

export type Point = { x: number; y: number };
export type Polygon = Point[];

export interface NestingResult {
  x: number;
  y: number;
  rotation: number;
}

// Convert our simple polygons to polygon-clipping format (Ring)
function toRing(poly: Polygon): Pair[] {
  return poly.map(p => [p.x, p.y] as Pair);
}

// Check if poly1 and poly2 intersect
function polygonsIntersect(poly1: Polygon, poly2: Polygon): boolean {
  const r1 = toRing(poly1);
  const r2 = toRing(poly2);
  const intersection = pc.intersection([[r1]], [[r2]]);
  return intersection.length > 0;
}

// Check if poly is completely inside the bin
function polygonInsideBin(poly: Polygon, bin: Polygon): boolean {
  const rp = toRing(poly);
  const rb = toRing(bin);
  // If the difference between poly and bin is empty, poly is fully inside bin
  const diff = pc.difference([[rp]], [[rb]]);
  return diff.length === 0;
}

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
    // To keep it top-left gravity (like shelf packing), we start from minY
    for (let ty = binBounds.minY; ty <= binBounds.maxY - bounds.h; ty += step) {
      for (let tx = binBounds.minX; tx <= binBounds.maxX - bounds.w; tx += step) {
        // Fast bounding box rejection against placed pieces
        const translatedBB = {
          minX: tx + bounds.minX - gapPx,
          minY: ty + bounds.minY - gapPx,
          maxX: tx + bounds.maxX + gapPx,
          maxY: ty + bounds.maxY + gapPx
        };
        
        let bbConflict = false;
        for (const placed of placedPolys) {
          const pBB = getBoundingBox(placed);
          if (
            translatedBB.minX < pBB.maxX &&
            translatedBB.maxX > pBB.minX &&
            translatedBB.minY < pBB.maxY &&
            translatedBB.maxY > pBB.minY
          ) {
            bbConflict = true;
            break;
          }
        }
        
        if (bbConflict) continue;
        
        // Exact polygon intersection tests
        const candidatePoly = translatePolygon(rotatedBase, tx, ty);
        
        // 1. Must be inside bin
        if (!polygonInsideBin(candidatePoly, bin)) {
          continue;
        }
        
        // 2. Must not intersect placed pieces (with gap)
        let exactConflict = false;
        // Expand candidate slightly for gap testing
        // For simplicity with polygon-clipping, we just translate the gap logic via bounding box, 
        // but for exact gap we would offset the polygon. Here we do an exact intersection on the 
        // actual polygons if BB passed. If we want cutting gap, we can just enforce the BB check we did.
        for (const placed of placedPolys) {
           if (polygonsIntersect(candidatePoly, placed)) {
             exactConflict = true;
             break;
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
