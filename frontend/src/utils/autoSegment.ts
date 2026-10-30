import { DEFAULT_GLASS_ASSETS, type DefaultGlassAsset } from '../assets';
import type { Crop, GlassSheet } from '../types';
import { computePolygonArea } from './geometry';
import { maskToPolygon, smoothMaskLogits } from './maskContour';

function pointInPolygon(pt: [number, number], vs: [number, number][]): boolean {
  const [x, y] = pt;
  let inside = false;
  for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
    const [xi, yi] = vs[i];
    const [xj, yj] = vs[j];
    const intersect = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

export interface ProposedGlassCell {
  /** Bounding box [x1, y1, x2, y2] in full pattern coordinates. */
  box: [number, number, number, number];
  /** Interior pole of inaccessibility [x, y] in full pattern coordinates. */
  point: [number, number];
  /** Polygon [x, y][] in full pattern coordinates extracted from the expanded cell mask. */
  polygon: [number, number][];
  /** Sampled median interior color (#rrggbb). */
  color: string;
  /** Area in full pattern square pixels. */
  area: number;
}

export interface ProposeCellsOptions {
  cropLeft?: number;
  cropTop?: number;
  cropW?: number;
  cropH?: number;
}

const DEFAULT_SWATCHES: Record<string, string> = {
  Turquoise: '#054443',
  Orange: '#d96b12',
  Amber: '#c88a1e',
  Green: '#1e7a2e',
  'Cobalt Blue': '#153a8a',
  Red: '#8e141e',
  Pink: '#a8385b',
  White: '#d8dde0',
  Black: '#141816',
};

export function parseHexRgb(hex: string): [number, number, number] {
  const clean = hex.trim().replace(/^#/, '');
  if (clean.length === 3) {
    return [
      parseInt(clean[0] + clean[0], 16) || 0,
      parseInt(clean[1] + clean[1], 16) || 0,
      parseInt(clean[2] + clean[2], 16) || 0,
    ];
  }
  return [
    parseInt(clean.slice(0, 2), 16) || 0,
    parseInt(clean.slice(2, 4), 16) || 0,
    parseInt(clean.slice(4, 6), 16) || 0,
  ];
}

export function rgbToHsv(r: number, g: number, b: number): { h: number; s: number; v: number } {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const d = max - min;
  const s = max === 0 ? 0 : d / max;
  const v = max;

  let h = 0;
  if (d > 1e-6) {
    if (max === rn) {
      h = ((gn - bn) / d) % 6;
    } else if (max === gn) {
      h = (bn - rn) / d + 2;
    } else {
      h = (rn - gn) / d + 4;
    }
    h *= 60;
    if (h < 0) h += 360;
  }
  return { h, s, v };
}

/**
 * Classify a sampled piece RGB/hex color into one of the 9 built-in simple
 * stained-glass sheets in `DEFAULT_GLASS_ASSETS`. Uses HSV hue/saturation/value
 * invariants so both backlit window photos and reflected-light patterns map
 * accurately to their corresponding glass color.
 */
export function classifyGlassColor(
  color: string | [number, number, number],
): DefaultGlassAsset & { swatch: string } {
  const [r, g, b] = typeof color === 'string' ? parseHexRgb(color) : color;
  const { h, s, v } = rgbToHsv(r, g, b);

  const byLabel = (label: string): DefaultGlassAsset & { swatch: string } => {
    const asset = DEFAULT_GLASS_ASSETS.find(a => a.label === label) ?? DEFAULT_GLASS_ASSETS[0];
    return { ...asset, swatch: DEFAULT_SWATCHES[asset.label] ?? '#888888' };
  };

  // Very dark -> Black glass
  if (v < 0.16 || (s < 0.18 && v < 0.28)) {
    return byLabel('Black');
  }

  // Low saturation -> White / clear glass
  if (s < 0.12 || (s < 0.15 && v > 0.90)) {
    return byLabel('White');
  }

  // Chromatic glass classification by Hue + Saturation/Value
  if (h >= 345 || h < 15) {
    if (s < 0.58 && v > 0.62) return byLabel('Pink');
    return byLabel('Red');
  }
  if (h >= 15 && h < 36) {
    // Warm low-saturation cream/tan/honey -> Amber; vivid -> Orange
    if (s < 0.52) return byLabel('Amber');
    return byLabel('Orange');
  }
  if (h >= 36 && h < 60) {
    return byLabel('Amber');
  }
  if (h >= 60 && h < 162) {
    return byLabel('Green');
  }
  if (h >= 162 && h < 205) {
    return byLabel('Turquoise');
  }
  if (h >= 205 && h < 285) {
    return byLabel('Cobalt Blue');
  }
  return byLabel('Pink');
}

/**
 * Find an existing sheet in `existingSheets` matching `hexColor`, or return a
 * newly constructed `GlassSheet` from `DEFAULT_GLASS_ASSETS` so auto-segmented
 * pieces automatically get color-matched glass sheets.
 */
export function resolveGlassSheetForColor(
  hexColor: string,
  existingSheets: GlassSheet[],
  fallbackSheetId: string,
): { sheetId: string; newSheet?: GlassSheet } {
  if (!hexColor) return { sheetId: fallbackSheetId };
  const target = classifyGlassColor(hexColor);
  const targetLabelLower = target.label.toLowerCase();

  // 1. Direct match by built-in URL or label (including tutorial /assets/green.jpg & /assets/orange.jpg)
  const directMatch = existingSheets.find(s => {
    const labelLower = s.label.trim().toLowerCase();
    if (s.imageUrl === target.url) return true;
    if (labelLower === targetLabelLower || labelLower.startsWith(targetLabelLower + ' ')) return true;
    if (target.label === 'Green' && s.imageUrl.endsWith('/green.jpg')) return true;
    if (target.label === 'Orange' && s.imageUrl.endsWith('/orange.jpg')) return true;
    return false;
  });
  if (directMatch) {
    return { sheetId: directMatch.id };
  }

  // 2. Match against existing custom sheet swatches if a custom sheet classifies to the same glass family
  const swatchMatch = existingSheets.find(s => {
    if (!s.swatch) return false;
    return classifyGlassColor(s.swatch).label === target.label;
  });
  if (swatchMatch) {
    return { sheetId: swatchMatch.id };
  }

  // 3. Create a new sheet from DEFAULT_GLASS_ASSETS
  const newSheet: GlassSheet = {
    id: `sheet-${crypto.randomUUID()}`,
    label: target.label,
    imageUrl: target.url,
    crop: { top: 0, left: 0, bottom: 0, right: 0 },
    scale: target.scale,
    naturalWidth: 800,
    naturalHeight: 800,
    swatch: target.swatch,
  };
  return { sheetId: newSheet.id, newSheet };
}

/**
 * Extract enclosed stained-glass cell proposals, interior prompt points,
 * smoothed polygons, and sampled glass colors from a downsampled RGBA pattern image.
 */
export function proposeStainedGlassCells(
  data: Uint8ClampedArray,
  W: number,
  H: number,
  opts: ProposeCellsOptions = {},
): ProposedGlassCell[] {
  const cropLeft = opts.cropLeft ?? 0;
  const cropTop = opts.cropTop ?? 0;
  const cropW = opts.cropW ?? W;
  const cropH = opts.cropH ?? H;

  const N = W * H;
  if (N === 0 || data.length < N * 4) return [];

  const lum = new Float32Array(N);
  const sat = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const r = data[i * 4];
    const g = data[i * 4 + 1];
    const b = data[i * 4 + 2];
    lum[i] = 0.299 * r + 0.587 * g + 0.114 * b;
    const maxC = Math.max(r, g, b);
    const minC = Math.min(r, g, b);
    sat[i] = maxC > 0 ? ((maxC - minC) / maxC) * 255 : 0;
  }

  // Integral image of luminance for fast local mean
  const integral = new Float64Array((W + 1) * (H + 1));
  for (let y = 0; y < H; y++) {
    let rowSum = 0;
    for (let x = 0; x < W; x++) {
      rowSum += lum[y * W + x];
      integral[(y + 1) * (W + 1) + (x + 1)] = integral[y * (W + 1) + (x + 1)] + rowSum;
    }
  }
  const localMean = (x: number, y: number, rad: number): number => {
    const x0 = Math.max(0, x - rad);
    const y0 = Math.max(0, y - rad);
    const x1 = Math.min(W - 1, x + rad);
    const y1 = Math.min(H - 1, y + rad);
    const count = (x1 - x0 + 1) * (y1 - y0 + 1);
    const sum =
      integral[(y1 + 1) * (W + 1) + (x1 + 1)] -
      integral[y0 * (W + 1) + (x1 + 1)] -
      integral[(y1 + 1) * (W + 1) + x0] +
      integral[y0 * (W + 1) + x0];
    return sum / count;
  };

  const rad = Math.max(4, Math.round(Math.min(W, H) * 0.03));
  const barrier = new Uint8Array(N);
  const strongDark = new Uint8Array(N);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const idx = y * W + x;
      const l = lum[idx];
      const m = localMean(x, y, rad);
      if (l < 52 || (l < 78 && m - l > 14)) {
        strongDark[idx] = 1;
      }
      if (l < 65 || (l < 140 && m - l > 14)) {
        barrier[idx] = 1;
      }
    }
  }

  // 1px morphological closing to seal tiny specular gaps on solder lines
  const dilated = new Uint8Array(N);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      let any = 0;
      for (let dy = -1; dy <= 1 && !any; dy++) {
        const ny = y + dy;
        if (ny < 0 || ny >= H) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= W) continue;
          if (barrier[ny * W + nx]) {
            any = 1;
            break;
          }
        }
      }
      dilated[y * W + x] = any;
    }
  }
  const closed = new Uint8Array(N);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      let all = 1;
      for (let dy = -1; dy <= 1 && all; dy++) {
        const ny = y + dy;
        if (ny < 0 || ny >= H) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= W) continue;
          if (!dilated[ny * W + nx]) {
            all = 0;
            break;
          }
        }
      }
      closed[y * W + x] = all;
    }
  }

  // Connected components on !closed
  const rawLabels = new Int32Array(N);
  const queue = new Int32Array(N);
  let nextRawLabel = 1;

  interface RawComp {
    rawLabel: number;
    pixels: Int32Array;
    minX: number;
    minY: number;
    maxX: number;
    maxY: number;
    borderTouches: number;
    sidesTouched: number;
    borderPerimeterFrac: number;
    darkBoundaryFrac: number;
    meanSat: number;
    meanLum: number;
    isWrappingBackground: boolean;
  }

  const rawComps: RawComp[] = [];
  let hasWrappingBackground = false;

  for (let i = 0; i < N; i++) {
    if (closed[i] || rawLabels[i] !== 0) continue;
    const rawLabel = nextRawLabel++;
    let head = 0;
    let tail = 0;
    queue[tail++] = i;
    rawLabels[i] = rawLabel;

    let minX = W;
    let minY = H;
    let maxX = 0;
    let maxY = 0;
    let borderTouches = 0;
    let topTouches = 0;
    let bottomTouches = 0;
    let leftTouches = 0;
    let rightTouches = 0;
    let boundaryCount = 0;
    let strongDarkBoundaryCount = 0;
    let sumSat = 0;
    let sumLum = 0;

    while (head < tail) {
      const curr = queue[head++];
      const cx = curr % W;
      const cy = (curr - cx) / W;
      if (cx < minX) minX = cx;
      if (cx > maxX) maxX = cx;
      if (cy < minY) minY = cy;
      if (cy > maxY) maxY = cy;
      if (cx === 0) { borderTouches++; leftTouches++; }
      if (cx === W - 1) { borderTouches++; rightTouches++; }
      if (cy === 0) { borderTouches++; topTouches++; }
      if (cy === H - 1) { borderTouches++; bottomTouches++; }
      sumSat += sat[curr];
      sumLum += lum[curr];

      let isBoundary = false;
      const n0 = cx > 0 ? curr - 1 : -1;
      const n1 = cx < W - 1 ? curr + 1 : -1;
      const n2 = cy > 0 ? curr - W : -1;
      const n3 = cy < H - 1 ? curr + W : -1;
      for (const n of [n0, n1, n2, n3]) {
        if (n >= 0) {
          if (closed[n]) {
            isBoundary = true;
          } else if (rawLabels[n] === 0) {
            rawLabels[n] = rawLabel;
            queue[tail++] = n;
          }
        }
      }
      if (isBoundary) {
        boundaryCount++;
        let nearStrong = false;
        for (let dy = -2; dy <= 2 && !nearStrong; dy++) {
          const ny = cy + dy;
          if (ny < 0 || ny >= H) continue;
          for (let dx = -2; dx <= 2; dx++) {
            const nx = cx + dx;
            if (nx < 0 || nx >= W) continue;
            if (strongDark[ny * W + nx]) {
              nearStrong = true;
              break;
            }
          }
        }
        if (nearStrong) strongDarkBoundaryCount++;
      }
    }

    const area = tail;
    const areaFrac = area / N;
    const sidesTouched =
      (topTouches > 2 ? 1 : 0) +
      (bottomTouches > 2 ? 1 : 0) +
      (leftTouches > 2 ? 1 : 0) +
      (rightTouches > 2 ? 1 : 0);
    const borderPerimeterFrac = borderTouches / (2 * (W + H));
    const isWrappingBackground = sidesTouched >= 3 || borderPerimeterFrac > 0.22 || areaFrac > 0.70;
    if (isWrappingBackground && areaFrac > 0.15) {
      hasWrappingBackground = true;
    }

    if (areaFrac < 0.0015 || areaFrac > 0.70) continue;

    const darkBoundaryFrac = boundaryCount > 0 ? strongDarkBoundaryCount / boundaryCount : 0;
    rawComps.push({
      rawLabel,
      pixels: queue.slice(0, tail),
      minX,
      minY,
      maxX,
      maxY,
      borderTouches,
      sidesTouched,
      borderPerimeterFrac,
      darkBoundaryFrac,
      meanSat: sumSat / area,
      meanLum: sumLum / area,
      isWrappingBackground,
    });
  }

  // Filter valid stained-glass cell seeds
  const validComps = rawComps.filter(c => {
    if (c.isWrappingBackground) return false;
    if (c.darkBoundaryFrac < 0.08) return false;
    if (c.borderTouches > 0) {
      if (c.darkBoundaryFrac < 0.25) return false;
      if (hasWrappingBackground && c.meanSat < 45 && c.darkBoundaryFrac < 0.50) return false;
    }
    return true;
  });

  if (validComps.length === 0) return [];

  // Re-index valid cells 1..K and compute pole of inaccessibility + interior color for each cell
  const cellLabels = new Int32Array(N);
  const poles: [number, number][] = [];
  const colors: string[] = [];
  const distBuf = new Int32Array(N);

  for (let idx = 0; idx < validComps.length; idx++) {
    const cellId = idx + 1;
    const comp = validComps[idx];
    for (let k = 0; k < comp.pixels.length; k++) {
      cellLabels[comp.pixels[k]] = cellId;
    }
  }

  for (let idx = 0; idx < validComps.length; idx++) {
    const cellId = idx + 1;
    const comp = validComps[idx];
    const pixels = comp.pixels;
    let head = 0;
    let tail = 0;
    let sumX = 0;
    let sumY = 0;

    for (let k = 0; k < pixels.length; k++) {
      const p = pixels[k];
      const px = p % W;
      const py = (p - px) / W;
      sumX += px;
      sumY += py;
      const isEdge =
        px === 0 ||
        px === W - 1 ||
        py === 0 ||
        py === H - 1 ||
        cellLabels[p - 1] !== cellId ||
        cellLabels[p + 1] !== cellId ||
        cellLabels[p - W] !== cellId ||
        cellLabels[p + W] !== cellId;
      if (isEdge) {
        distBuf[p] = 1;
        queue[tail++] = p;
      } else {
        distBuf[p] = 0;
      }
    }

    const centroidX = sumX / pixels.length;
    const centroidY = sumY / pixels.length;

    while (head < tail) {
      const curr = queue[head++];
      const d = distBuf[curr];
      const cx = curr % W;
      const cy = (curr - cx) / W;
      const neighbors = [
        cx > 0 ? curr - 1 : -1,
        cx < W - 1 ? curr + 1 : -1,
        cy > 0 ? curr - W : -1,
        cy < H - 1 ? curr + W : -1,
      ];
      for (const n of neighbors) {
        if (n >= 0 && cellLabels[n] === cellId && distBuf[n] === 0) {
          distBuf[n] = d + 1;
          queue[tail++] = n;
        }
      }
    }

    let maxDist = 0;
    let bestP = pixels[0];
    let bestCentroidDist = Infinity;
    for (let k = 0; k < pixels.length; k++) {
      const p = pixels[k];
      const d = distBuf[p];
      const px = p % W;
      const py = (p - px) / W;
      const cd = Math.hypot(px - centroidX, py - centroidY);
      if (d > maxDist || (d === maxDist && cd < bestCentroidDist)) {
        maxDist = d;
        bestP = p;
        bestCentroidDist = cd;
      }
    }
    const poleGridX = bestP % W;
    const poleGridY = (bestP - poleGridX) / W;
    poles.push([
      cropLeft + ((poleGridX + 0.5) / W) * cropW,
      cropTop + ((poleGridY + 0.5) / H) * cropH,
    ]);

    // Sample interior color away from dark solder border and extreme white glare
    const minInteriorDist = Math.min(3, Math.max(1, maxDist - 1));
    const rs: number[] = [];
    const gs: number[] = [];
    const bs: number[] = [];
    const allRs: number[] = [];
    const allGs: number[] = [];
    const allBs: number[] = [];
    const step = Math.max(1, Math.floor(pixels.length / 500));

    for (let k = 0; k < pixels.length; k += step) {
      const p = pixels[k];
      if (distBuf[p] < minInteriorDist) continue;
      const r = data[p * 4];
      const g = data[p * 4 + 1];
      const b = data[p * 4 + 2];
      allRs.push(r);
      allGs.push(g);
      allBs.push(b);
      if (!(lum[p] > 246 && sat[p] < 20)) {
        rs.push(r);
        gs.push(g);
        bs.push(b);
      }
    }

    const useR = rs.length >= Math.max(5, allRs.length * 0.2) ? rs : allRs;
    const useG = rs.length >= Math.max(5, allRs.length * 0.2) ? gs : allGs;
    const useB = rs.length >= Math.max(5, allRs.length * 0.2) ? bs : allBs;
    if (useR.length === 0) {
      useR.push(data[bestP * 4]);
      useG.push(data[bestP * 4 + 1]);
      useB.push(data[bestP * 4 + 2]);
    }
    useR.sort((a, b) => a - b);
    useG.sort((a, b) => a - b);
    useB.sort((a, b) => a - b);
    const mid = useR.length >> 1;
    const hex =
      '#' +
      [useR[mid], useG[mid], useB[mid]]
        .map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0'))
        .join('');
    colors.push(hex);
  }

  // Simultaneous multi-label watershed expansion across dark solder barriers so
  // adjacent glass cells meet flush at the solder centerline.
  const maxExpandSteps = Math.max(2, Math.round(Math.min(W, H) * 0.01));
  const expandDist = new Int32Array(N);
  let wHead = 0;
  let wTail = 0;
  for (let i = 0; i < N; i++) {
    const cid = cellLabels[i];
    if (cid === 0) continue;
    const cx = i % W;
    const cy = (i - cx) / W;
    if (
      (cx > 0 && cellLabels[i - 1] === 0) ||
      (cx < W - 1 && cellLabels[i + 1] === 0) ||
      (cy > 0 && cellLabels[i - W] === 0) ||
      (cy < H - 1 && cellLabels[i + W] === 0)
    ) {
      queue[wTail++] = i;
    }
  }

  while (wHead < wTail) {
    const curr = queue[wHead++];
    const cid = cellLabels[curr];
    const d = expandDist[curr];
    if (d >= maxExpandSteps) continue;
    const cx = curr % W;
    const cy = (curr - cx) / W;
    const neighbors = [
      cx > 0 ? curr - 1 : -1,
      cx < W - 1 ? curr + 1 : -1,
      cy > 0 ? curr - W : -1,
      cy < H - 1 ? curr + W : -1,
    ];
    for (const n of neighbors) {
      if (n < 0 || cellLabels[n] !== 0) continue;
      // Only expand into dark solder/barrier pixels, never into bright exterior background
      if (!closed[n] && lum[n] > 145) continue;
      cellLabels[n] = cid;
      expandDist[n] = d + 1;
      queue[wTail++] = n;
    }
  }

  // Extract polygon and bounding box for each expanded cell
  const results: ProposedGlassCell[] = [];
  for (let idx = 0; idx < validComps.length; idx++) {
    const cellId = idx + 1;
    let minX = W;
    let minY = H;
    let maxX = 0;
    let maxY = 0;
    let count = 0;
    for (let i = 0; i < N; i++) {
      if (cellLabels[i] !== cellId) continue;
      count++;
      const x = i % W;
      const y = (i - x) / W;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
    if (count < 9) continue;

    const polyGrid = extractCellContourPolygon(cellLabels, cellId, W, H, minX, minY, maxX, maxY);
    if (polyGrid.length < 3) continue;

    const polygon: [number, number][] = polyGrid.map(([gx, gy]) => [
      Math.round((cropLeft + (gx / W) * cropW) * 10) / 10,
      Math.round((cropTop + (gy / H) * cropH) * 10) / 10,
    ]);

    const box: [number, number, number, number] = [
      Math.round(cropLeft + (minX / W) * cropW),
      Math.round(cropTop + (minY / H) * cropH),
      Math.round(cropLeft + ((maxX + 1) / W) * cropW),
      Math.round(cropTop + ((maxY + 1) / H) * cropH),
    ];

    const area = computePolygonArea(polygon);
    if (area < 25) continue;

    results.push({
      box,
      point: [Math.round(poles[idx][0]), Math.round(poles[idx][1])],
      polygon,
      color: colors[idx],
      area,
    });
  }

  // Sort cells top-to-bottom, left-to-right for deterministic piece numbering
  results.sort((a, b) => a.box[1] - b.box[1] || a.box[0] - b.box[0]);
  return results;
}

/**
 * Trace and simplify the outer contour of `cellLabels === cellId` within its padded bbox.
 */
function extractCellContourPolygon(
  cellLabels: Int32Array,
  cellId: number,
  W: number,
  H: number,
  minX: number,
  minY: number,
  maxX: number,
  maxY: number,
): [number, number][] {
  const pad = 3;
  const x0 = Math.max(0, minX - pad);
  const y0 = Math.max(0, minY - pad);
  const x1 = Math.min(W - 1, maxX + pad);
  const y1 = Math.min(H - 1, maxY + pad);
  const bw = x1 - x0 + 3; // +2 for 1px outside border around local patch
  const bh = y1 - y0 + 3;
  // maskToPolygon assumes a square grid (width === height === inputSize)
  const size = Math.max(bw, bh);

  const field = new Float32Array(size * size).fill(-4);
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      if (cellLabels[y * W + x] === cellId) {
        field[(y - y0 + 1) * size + (x - x0 + 1)] = 4;
      }
    }
  }

  const smoothed = smoothMaskLogits(field, size, size, 1.1);
  const localPoly = maskToPolygon(smoothed, size, size, {
    inputSize: size,
    scale: 1,
    padX: 0,
    padY: 0,
    origW: size,
    origH: size,
    threshold: 0,
    simplifyRatio: 0.003,
    minSimplifyPx: 0.5,
  });

  return localPoly.map(([lx, ly]) => [
    Math.max(0, Math.min(W, x0 + lx - 0.5)),
    Math.max(0, Math.min(H, y0 + ly - 0.5)),
  ]);
}

/**
 * Validate whether a SAM2-decoded polygon is consistent with a proposed cell
 * without leaking into neighboring cells or collapsing.
 */
export function isValidRefinedPolygon(
  samPolygon: [number, number][],
  cell: ProposedGlassCell,
): boolean {
  if (!samPolygon || samPolygon.length < 3) return false;
  const samArea = computePolygonArea(samPolygon);
  if (samArea < cell.area * 0.55 || samArea > cell.area * 1.35) return false;

  const [bx1, by1, bx2, by2] = cell.box;
  const bw = Math.max(1, bx2 - bx1);
  const bh = Math.max(1, by2 - by1);
  const pad = Math.max(12, Math.max(bw, bh) * 0.08);

  for (const [x, y] of samPolygon) {
    if (x < bx1 - pad || x > bx2 + pad || y < by1 - pad || y > by2 + pad) {
      return false;
    }
  }

  if (!pointInPolygon(cell.point, samPolygon)) {
    return false;
  }
  return true;
}

/**
 * Load an image URL onto an offscreen canvas and propose stained-glass cells
 * directly on the main thread or worker without waiting for the 300MB SAM2 encoder.
 */
export async function proposeStainedGlassCellsFromUrl(
  imageUrl: string,
  crop?: Crop,
): Promise<ProposedGlassCell[]> {
  const blob = await fetch(imageUrl).then(r => r.blob());
  const bitmap = await createImageBitmap(blob);
  const origW = bitmap.width;
  const origH = bitmap.height;

  const cropLeft = Math.max(0, Math.min(origW - 1, Math.round(crop?.left ?? 0)));
  const cropTop = Math.max(0, Math.min(origH - 1, Math.round(crop?.top ?? 0)));
  const cropRight = Math.max(cropLeft + 1, Math.min(origW, Math.round(origW - (crop?.right ?? 0))));
  const cropBottom = Math.max(cropTop + 1, Math.min(origH, Math.round(origH - (crop?.bottom ?? 0))));
  const cropW = cropRight - cropLeft;
  const cropH = cropBottom - cropTop;

  const maxGridDim = 384;
  const gridScale = Math.min(1, maxGridDim / Math.max(cropW, cropH));
  const gridW = Math.max(16, Math.round(cropW * gridScale));
  const gridH = Math.max(16, Math.round(cropH * gridScale));

  let data: Uint8ClampedArray;
  if (typeof OffscreenCanvas !== 'undefined') {
    const canvas = new OffscreenCanvas(gridW, gridH);
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(bitmap, cropLeft, cropTop, cropW, cropH, 0, 0, gridW, gridH);
    data = ctx.getImageData(0, 0, gridW, gridH).data;
  } else {
    const canvas = document.createElement('canvas');
    canvas.width = gridW;
    canvas.height = gridH;
    const ctx = canvas.getContext('2d')!;
    ctx.drawImage(bitmap, cropLeft, cropTop, cropW, cropH, 0, 0, gridW, gridH);
    data = ctx.getImageData(0, 0, gridW, gridH).data;
  }
  bitmap.close();

  return proposeStainedGlassCells(data, gridW, gridH, {
    cropLeft,
    cropTop,
    cropW,
    cropH,
  });
}
