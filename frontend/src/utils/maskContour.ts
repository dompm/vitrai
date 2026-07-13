export interface MaskContourOptions {
  inputSize: number;
  scale: number;
  padX: number;
  padY: number;
  origW: number;
  origH: number;
  threshold?: number;
  simplifyRatio?: number;
  minSimplifyPx?: number;
}

type Point = [number, number];

interface Crossing {
  key: string;
  point: Point;
}

/**
 * Extract the largest closed iso-contour from mask logits and map it back to
 * the source image. Marching squares keeps the sub-pixel boundary encoded by
 * SAM's logits instead of walking through thresholded foreground pixels.
 */
export function maskToPolygon(
  data: Float32Array,
  width: number,
  height: number,
  options: MaskContourOptions,
): Point[] {
  if (width < 2 || height < 2 || data.length < width * height) return [];

  const {
    inputSize,
    scale,
    padX,
    padY,
    origW,
    origH,
    threshold = 0,
    simplifyRatio = 0.005,
    minSimplifyPx = 1.5,
  } = options;

  if (!(scale > 0) || !(inputSize > 0) || origW <= 0 || origH <= 0) return [];

  // Exclude letterbox padding: SAM sometimes assigns foreground to it, but it
  // can never be part of the source-image contour.
  const validMinX = Math.max(0, Math.floor(padX * width / inputSize));
  const validMinY = Math.max(0, Math.floor(padY * height / inputSize));
  const validMaxX = Math.min(width - 1, Math.ceil((padX + origW * scale) * width / inputSize) - 1);
  const validMaxY = Math.min(height - 1, Math.ceil((padY + origH * scale) * height / inputSize) - 1);
  if (validMaxX < validMinX || validMaxY < validMinY) return [];

  // A virtual negative border closes masks that touch an image edge. The
  // crossing falls effectively on the edge and is clamped after projection.
  const outside = threshold - 1e6;
  const sample = (x: number, y: number): number => {
    if (x < validMinX || x > validMaxX || y < validMinY || y > validMaxY) return outside;
    return data[y * width + x];
  };

  const nodes = new Map<string, Point>();
  const adjacency = new Map<string, string[]>();

  const connect = (a: Crossing, b: Crossing) => {
    nodes.set(a.key, a.point);
    nodes.set(b.key, b.point);
    const aNeighbors = adjacency.get(a.key) ?? [];
    const bNeighbors = adjacency.get(b.key) ?? [];
    aNeighbors.push(b.key);
    bNeighbors.push(a.key);
    adjacency.set(a.key, aNeighbors);
    adjacency.set(b.key, bNeighbors);
  };

  const interpolate = (a: number, b: number): number => {
    const delta = b - a;
    if (Math.abs(delta) < 1e-12) return 0.5;
    return Math.max(0, Math.min(1, (threshold - a) / delta));
  };

  for (let y = validMinY - 1; y <= validMaxY; y++) {
    for (let x = validMinX - 1; x <= validMaxX; x++) {
      const tl = sample(x, y);
      const tr = sample(x + 1, y);
      const br = sample(x + 1, y + 1);
      const bl = sample(x, y + 1);
      const state = (tl > threshold ? 1 : 0)
        | (tr > threshold ? 2 : 0)
        | (br > threshold ? 4 : 0)
        | (bl > threshold ? 8 : 0);
      if (state === 0 || state === 15) continue;

      const crossings: Array<Crossing | undefined> = [];
      const edge = (index: number): Crossing => {
        const cached = crossings[index];
        if (cached) return cached;
        let crossing: Crossing;
        if (index === 0) {
          crossing = { key: `h:${x}:${y}`, point: [x + interpolate(tl, tr), y] };
        } else if (index === 1) {
          crossing = { key: `v:${x + 1}:${y}`, point: [x + 1, y + interpolate(tr, br)] };
        } else if (index === 2) {
          crossing = { key: `h:${x}:${y + 1}`, point: [x + interpolate(bl, br), y + 1] };
        } else {
          crossing = { key: `v:${x}:${y}`, point: [x, y + interpolate(tl, bl)] };
        }
        crossings[index] = crossing;
        return crossing;
      };

      const pair = (a: number, b: number) => connect(edge(a), edge(b));
      switch (state) {
        case 1: pair(3, 0); break;
        case 2: pair(0, 1); break;
        case 3: pair(3, 1); break;
        case 4: pair(1, 2); break;
        case 5: {
          // Resolve diagonal saddles from the continuous cell value instead of
          // arbitrarily joining two otherwise separate regions.
          const centerInside = (tl + tr + br + bl) / 4 > threshold;
          if (centerInside) { pair(0, 1); pair(2, 3); }
          else { pair(3, 0); pair(1, 2); }
          break;
        }
        case 6: pair(0, 2); break;
        case 7: pair(3, 2); break;
        case 8: pair(2, 3); break;
        case 9: pair(0, 2); break;
        case 10: {
          const centerInside = (tl + tr + br + bl) / 4 > threshold;
          if (centerInside) { pair(3, 0); pair(1, 2); }
          else { pair(0, 1); pair(2, 3); }
          break;
        }
        case 11: pair(1, 2); break;
        case 12: pair(3, 1); break;
        case 13: pair(0, 1); break;
        case 14: pair(3, 0); break;
      }
    }
  }

  const loops = traceClosedLoops(nodes, adjacency);
  if (loops.length === 0) return [];

  let largest = loops[0];
  let largestArea = Math.abs(signedArea(largest));
  for (let i = 1; i < loops.length; i++) {
    const area = Math.abs(signedArea(loops[i]));
    if (area > largestArea) {
      largest = loops[i];
      largestArea = area;
    }
  }

  const toOriginal = largest.map(([maskX, maskY]): Point => [
    Math.max(0, Math.min(origW, (maskX * inputSize / width - padX) / scale)),
    Math.max(0, Math.min(origH, (maskY * inputSize / height - padY) / scale)),
  ]);

  const perimeter = polygonPerimeter(toOriginal);
  const epsilon = Math.max(minSimplifyPx, perimeter * simplifyRatio);
  return simplifyClosedPolygon(toOriginal, epsilon);
}

/**
 * Suppress single-cell oscillations in decoder logits before they are enlarged
 * to the 1024px model-input space. A sigma near 1 smooths mask-grid noise while
 * keeping the zero crossing centered on broad, intentional boundaries.
 */
export function smoothMaskLogits(
  data: Float32Array,
  width: number,
  height: number,
  sigma: number,
): Float32Array {
  if (width < 1 || height < 1 || data.length < width * height) return new Float32Array();
  if (!(sigma > 0) || !Number.isFinite(sigma)) return data.slice();

  const radius = Math.max(1, Math.ceil(sigma * 3));
  const kernel = new Float64Array(radius * 2 + 1);
  let kernelSum = 0;
  for (let offset = -radius; offset <= radius; offset++) {
    const weight = Math.exp(-(offset * offset) / (2 * sigma * sigma));
    kernel[offset + radius] = weight;
    kernelSum += weight;
  }
  for (let i = 0; i < kernel.length; i++) kernel[i] /= kernelSum;

  const horizontal = new Float32Array(width * height);
  const output = new Float32Array(width * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let value = 0;
      for (let offset = -radius; offset <= radius; offset++) {
        const sourceX = Math.max(0, Math.min(width - 1, x + offset));
        value += data[y * width + sourceX] * kernel[offset + radius];
      }
      horizontal[y * width + x] = value;
    }
  }

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      let value = 0;
      for (let offset = -radius; offset <= radius; offset++) {
        const sourceY = Math.max(0, Math.min(height - 1, y + offset));
        value += horizontal[sourceY * width + x] * kernel[offset + radius];
      }
      output[y * width + x] = value;
    }
  }
  return output;
}

function traceClosedLoops(nodes: Map<string, Point>, adjacency: Map<string, string[]>): Point[][] {
  const usedEdges = new Set<string>();
  const loops: Point[][] = [];
  const edgeId = (a: string, b: string) => a < b ? `${a}|${b}` : `${b}|${a}`;

  for (const [start, neighbors] of adjacency) {
    for (const first of neighbors) {
      if (usedEdges.has(edgeId(start, first))) continue;

      const loop: Point[] = [];
      let previous = start;
      let current = first;
      usedEdges.add(edgeId(start, first));
      const startPoint = nodes.get(start);
      if (!startPoint) continue;
      loop.push(startPoint);

      let closed = false;
      for (let safety = 0; safety <= nodes.size; safety++) {
        const point = nodes.get(current);
        if (!point) break;
        if (current === start) {
          closed = true;
          break;
        }
        loop.push(point);

        const next = (adjacency.get(current) ?? []).find(candidate =>
          candidate !== previous && !usedEdges.has(edgeId(current, candidate))
        );
        if (!next) break;
        usedEdges.add(edgeId(current, next));
        previous = current;
        current = next;
      }

      if (closed && loop.length >= 3) loops.push(loop);
    }
  }
  return loops;
}

function signedArea(points: Point[]): number {
  let area = 0;
  for (let i = 0; i < points.length; i++) {
    const [x1, y1] = points[i];
    const [x2, y2] = points[(i + 1) % points.length];
    area += x1 * y2 - x2 * y1;
  }
  return area / 2;
}

function polygonPerimeter(points: Point[]): number {
  let perimeter = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    perimeter += Math.hypot(a[0] - b[0], a[1] - b[1]);
  }
  return perimeter;
}

/** Douglas-Peucker simplification with two stable anchors for a closed loop. */
export function simplifyClosedPolygon(points: Point[], epsilon: number): Point[] {
  if (points.length <= 3 || epsilon <= 0) return points.slice();

  let first = 0;
  for (let i = 1; i < points.length; i++) {
    if (points[i][0] < points[first][0]
      || (points[i][0] === points[first][0] && points[i][1] < points[first][1])) {
      first = i;
    }
  }

  let opposite = first;
  let farthestSq = -1;
  for (let i = 0; i < points.length; i++) {
    const dx = points[i][0] - points[first][0];
    const dy = points[i][1] - points[first][1];
    const distanceSq = dx * dx + dy * dy;
    if (distanceSq > farthestSq) {
      farthestSq = distanceSq;
      opposite = i;
    }
  }
  if (opposite === first) return points.slice(0, 3);

  const arc = (from: number, to: number): Point[] => {
    const result: Point[] = [points[from]];
    for (let i = (from + 1) % points.length; i !== to; i = (i + 1) % points.length) {
      result.push(points[i]);
    }
    result.push(points[to]);
    return result;
  };

  const forward = simplifyOpenPolyline(arc(first, opposite), epsilon);
  const backward = simplifyOpenPolyline(arc(opposite, first), epsilon);
  return [...forward.slice(0, -1), ...backward.slice(0, -1)];
}

function simplifyOpenPolyline(points: Point[], epsilon: number): Point[] {
  if (points.length <= 2) return points.slice();
  const keep = new Uint8Array(points.length);
  keep[0] = 1;
  keep[points.length - 1] = 1;
  const stack: Array<[number, number]> = [[0, points.length - 1]];

  while (stack.length > 0) {
    const [start, end] = stack.pop()!;
    const [x1, y1] = points[start];
    const [x2, y2] = points[end];
    const dx = x2 - x1;
    const dy = y2 - y1;
    const length = Math.hypot(dx, dy);
    let farthest = -1;
    let maxDistance = epsilon;

    for (let i = start + 1; i < end; i++) {
      const [px, py] = points[i];
      const distance = length < 1e-12
        ? Math.hypot(px - x1, py - y1)
        : Math.abs(dy * px - dx * py + x2 * y1 - y2 * x1) / length;
      if (distance > maxDistance) {
        maxDistance = distance;
        farthest = i;
      }
    }

    if (farthest >= 0) {
      keep[farthest] = 1;
      stack.push([start, farthest], [farthest, end]);
    }
  }

  return points.filter((_, index) => keep[index] === 1);
}
