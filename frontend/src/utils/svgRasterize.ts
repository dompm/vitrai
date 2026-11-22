import type { Scale } from '../types';
import {
  extractRegionsFromMask,
  parseSvgVectors,
  type SvgAnalysisStats,
  type SvgCanvasTarget,
  type SvgImportMode,
  type SvgImportedPiece,
} from './svgImport';

export interface SvgImportResult {
  mode: SvgImportMode;
  recommendedMode: SvgImportMode;
  pieces: SvgImportedPiece[];
  canvasWidth: number;
  canvasHeight: number;
  scale: Scale;
  stats: SvgAnalysisStats;
}

const RASTER_MAX_DIM = 1200;
const RASTER_PAD = 4; // white border so strokes touching the viewBox edge remain enclosed

/**
 * Ensure the SVG root carries explicit pixel width/height attributes matching its viewBox
 * so browsers render it crisply at the target canvas resolution.
 */
function prepareSvgForRaster(svgText: string, w: number, h: number): string {
  return svgText.replace(/<svg\b([^>]*)>/i, (_full, attrs: string) => {
    const cleaned = attrs
      .replace(/\s+width\s*=\s*(?:"[^"]*"|'[^']*')/gi, '')
      .replace(/\s+height\s*=\s*(?:"[^"]*"|'[^']*')/gi, '');
    return `<svg${cleaned} width="${w}" height="${h}">`;
  });
}

function loadSvgImage(svgText: string, w: number, h: number): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const prepared = prepareSvgForRaster(svgText, w, h);
    const blob = new Blob([prepared], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = (err) => {
      URL.revokeObjectURL(url);
      reject(err);
    };
    img.src = url;
  });
}

/**
 * Render an SVG onto an offscreen canvas, threshold dark strokes/lead-webs into a wall mask,
 * and flood-fill all enclosed interior regions into Vitrai pieces.
 */
export async function rasterizeSvgToRegions(
  svgText: string,
  canvasWidth: number,
  canvasHeight: number,
  fitBox?: { x: number; y: number; width: number; height: number },
): Promise<SvgImportedPiece[]> {
  const destW = fitBox ? fitBox.width : canvasWidth;
  const destH = fitBox ? fitBox.height : canvasHeight;
  const destX = fitBox ? fitBox.x : 0;
  const destY = fitBox ? fitBox.y : 0;

  const longest = Math.max(destW, destH);
  const rasterScale = Math.min(1, RASTER_MAX_DIM / longest);
  const drawW = Math.max(32, Math.round(destW * rasterScale));
  const drawH = Math.max(32, Math.round(destH * rasterScale));
  const rw = drawW + RASTER_PAD * 2;
  const rh = drawH + RASTER_PAD * 2;

  const img = await loadSvgImage(svgText, drawW, drawH);

  const canvas = document.createElement('canvas');
  canvas.width = rw;
  canvas.height = rh;
  const ctx = canvas.getContext('2d');
  if (!ctx) return [];

  // White background so transparent regions are open and dark strokes/lines are walls
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, rw, rh);
  ctx.drawImage(img, RASTER_PAD, RASTER_PAD, drawW, drawH);

  const { data } = ctx.getImageData(0, 0, rw, rh);
  const rawMask = new Uint8Array(rw * rh);
  for (let i = 0; i < rw * rh; i++) {
    const r = data[i * 4];
    const g = data[i * 4 + 1];
    const b = data[i * 4 + 2];
    const lum = 0.299 * r + 0.587 * g + 0.114 * b;
    // Any non-white pixel (dark stroke or colored lead line) is treated as a wall
    if (lum < 215) {
      rawMask[i] = 1;
    }
  }

  // Light 1px dilation bridges sub-pixel gaps in thin anti-aliased strokes
  const dilated = new Uint8Array(rw * rh);
  for (let y = 1; y < rh - 1; y++) {
    const row = y * rw;
    for (let x = 1; x < rw - 1; x++) {
      const idx = row + x;
      if (
        rawMask[idx] ||
        rawMask[idx - 1] || rawMask[idx + 1] ||
        rawMask[idx - rw] || rawMask[idx + rw]
      ) {
        dilated[idx] = 1;
      }
    }
  }

  // Map raster coordinates (subtracting RASTER_PAD) back to Vitrai pattern space
  const sx = destW / drawW;
  const sy = destH / drawH;
  const rawPieces = extractRegionsFromMask(dilated, rw, rh, {
    targetWidth: rw * sx,
    targetHeight: rh * sy,
    offsetX: destX - RASTER_PAD * sx,
    offsetY: destY - RASTER_PAD * sy,
    simplifyEpsilon: 1.8,
  });

  return rawPieces;
}

/**
 * Import an SVG string into Vitrai pieces.
 * Automatically detects whether the SVG consists of closed vector shapes (`shapes`)
 * or intersecting linework / lead webs (`lines`), unless `mode` is explicitly specified.
 */
export async function importSvg(
  svgText: string,
  options?: {
    mode?: 'auto' | SvgImportMode;
    target?: SvgCanvasTarget;
  },
): Promise<SvgImportResult> {
  const vectorResult = parseSvgVectors(svgText, options?.target);
  const requested = options?.mode ?? 'auto';
  const chosenMode: SvgImportMode = requested === 'auto' ? vectorResult.recommendedMode : requested;

  if (chosenMode === 'shapes') {
    // If auto picked shapes but found nothing (rare), fall back to line detection
    if (requested === 'auto' && vectorResult.pieces.length === 0) {
      const linePieces = await rasterizeSvgToRegions(
        svgText,
        vectorResult.canvasWidth,
        vectorResult.canvasHeight,
        options?.target?.fitBox,
      );
      return {
        mode: 'lines',
        recommendedMode: vectorResult.recommendedMode,
        pieces: linePieces,
        canvasWidth: vectorResult.canvasWidth,
        canvasHeight: vectorResult.canvasHeight,
        scale: vectorResult.scale,
        stats: vectorResult.stats,
      };
    }

    return {
      mode: 'shapes',
      recommendedMode: vectorResult.recommendedMode,
      pieces: vectorResult.pieces,
      canvasWidth: vectorResult.canvasWidth,
      canvasHeight: vectorResult.canvasHeight,
      scale: vectorResult.scale,
      stats: vectorResult.stats,
    };
  }

  const linePieces = await rasterizeSvgToRegions(
    svgText,
    vectorResult.canvasWidth,
    vectorResult.canvasHeight,
    options?.target?.fitBox,
  );

  // If auto picked lines but found nothing while closed shapes exist, fall back to shapes
  if (requested === 'auto' && linePieces.length === 0 && vectorResult.pieces.length > 0) {
    return {
      mode: 'shapes',
      recommendedMode: vectorResult.recommendedMode,
      pieces: vectorResult.pieces,
      canvasWidth: vectorResult.canvasWidth,
      canvasHeight: vectorResult.canvasHeight,
      scale: vectorResult.scale,
      stats: vectorResult.stats,
    };
  }

  return {
    mode: 'lines',
    recommendedMode: vectorResult.recommendedMode,
    pieces: linePieces,
    canvasWidth: vectorResult.canvasWidth,
    canvasHeight: vectorResult.canvasHeight,
    scale: vectorResult.scale,
    stats: vectorResult.stats,
  };
}
