import type { Piece, GlassSheet } from '../types';
import { computeCentroid, flattenCurves } from './geometry';

export interface PiecePlacement {
  pieceId: string;
  x: number;
  y: number;
}

interface PieceRect {
  pieceId: string;
  w: number;
  h: number;
  // Offset from the top-left of the padded AABB back to the piece centroid.
  centroidOffsetX: number;
  centroidOffsetY: number;
}

function computePieceRect(piece: Piece, gapPx: number): PieceRect {
  const flat = flattenCurves(piece.polygon, piece.curvePoints);
  const centroid = computeCentroid(flat);
  const cos = Math.cos(piece.transform.rotation);
  const sin = Math.sin(piece.transform.rotation);
  const s = piece.transform.scale;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [px, py] of flat) {
    const dx = px - centroid.x;
    const dy = py - centroid.y;
    const x = s * (cos * dx - sin * dy);
    const y = s * (sin * dx + cos * dy);
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  return {
    pieceId: piece.id,
    w: (maxX - minX) + gapPx * 2,
    h: (maxY - minY) + gapPx * 2,
    centroidOffsetX: -minX + gapPx,
    centroidOffsetY: -minY + gapPx,
  };
}

/**
 * Lay pieces out left-to-right, top-to-bottom into the sheet's usable area
 * (shelf-next-fit, sorted by height descending). Rotation is preserved.
 */
export function packPiecesOnSheet(
  pieces: Piece[],
  sheet: GlassSheet,
  gapPx: number,
): PiecePlacement[] {
  if (pieces.length === 0) return [];

  const sw = sheet.naturalWidth ?? 800;
  const sh = sheet.naturalHeight ?? 600;
  const usableW = Math.max(1, sw - sheet.crop.left - sheet.crop.right);
  const usableH = Math.max(1, sh - sheet.crop.top - sheet.crop.bottom);
  const originX = sheet.crop.left;
  const originY = sheet.crop.top;

  const rects = pieces.map(p => computePieceRect(p, gapPx));
  const order = rects
    .map((r, i) => ({ r, i }))
    .sort((a, b) => b.r.h - a.r.h);

  const placements: PiecePlacement[] = [];
  let cursorX = 0;
  let cursorY = 0;
  let rowHeight = 0;

  for (const { r } of order) {
    if (cursorX > 0 && cursorX + r.w > usableW) {
      cursorX = 0;
      cursorY += rowHeight;
      rowHeight = 0;
    }
    // If the new row would spill past the bottom, wrap back to the top so
    // overflow pieces overlap earlier rows on the sheet instead of falling
    // off the cropped area entirely.
    if (cursorY + r.h > usableH) {
      cursorY = 0;
    }
    placements.push({
      pieceId: r.pieceId,
      x: originX + cursorX + r.centroidOffsetX,
      y: originY + cursorY + r.centroidOffsetY,
    });
    cursorX += r.w;
    if (r.h > rowHeight) rowHeight = r.h;
  }

  return placements;
}

const DEFAULT_CUTTING_GAP_MM = 5;

/** Cutting gap in glass-px. Uses the sheet's scale when known, else a sane fallback. */
export function defaultCuttingGapPx(sheet: GlassSheet): number {
  const s = sheet.scale;
  if (s && s.pxPerUnit > 0) {
    const pxPerMm = s.unit === 'mm'
      ? s.pxPerUnit
      : s.unit === 'cm'
        ? s.pxPerUnit / 10
        : s.pxPerUnit / 25.4;
    return pxPerMm * DEFAULT_CUTTING_GAP_MM;
  }
  const sw = sheet.naturalWidth ?? 800;
  return Math.max(8, sw * 0.01);
}
