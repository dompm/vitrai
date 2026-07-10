import type { Piece, GlassSheet } from '../types';
import { computeCentroid, flattenCurves } from './geometry';
import NestingWorker from '../workers/nesting.worker?worker';
import type { NestingWorkerMessage, NestingWorkerResponse } from '../workers/nesting.worker';

export interface PiecePlacement {
  pieceId: string;
  x: number;
  y: number;
  rotation?: number;
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

const DEFAULT_CUTTING_GAP_MM = 2;

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

/** Resolves with the ids of pieces that did not fit on the sheet (left at their old position). */
export function packPiecesSmart(
  pieces: Piece[],
  sheet: GlassSheet,
  gapPx: number,
  allowRotations: boolean,
  onProgress: (placement: PiecePlacement) => void
): Promise<string[]> {
  return new Promise((resolve, reject) => {
    if (pieces.length === 0) {
      resolve([]);
      return;
    }

    const sw = sheet.naturalWidth ?? 800;
    const sh = sheet.naturalHeight ?? 600;
    const originX = sheet.crop.left;
    const originY = sheet.crop.top;
    
    // Construct the bin polygon
    const usableW = Math.max(1, sw - sheet.crop.left - sheet.crop.right);
    const usableH = Math.max(1, sh - sheet.crop.top - sheet.crop.bottom);
    const bin = [
      { x: 0, y: 0 },
      { x: usableW, y: 0 },
      { x: usableW, y: usableH },
      { x: 0, y: usableH }
    ];

    const worker = new NestingWorker();
    
    worker.onmessage = (e: MessageEvent<NestingWorkerResponse>) => {
      const msg = e.data;
      if (msg.type === 'PROGRESS') {
        onProgress({
          pieceId: msg.payload.pieceId,
          x: originX + msg.payload.x,
          y: originY + msg.payload.y,
          // The worker's rotation is relative to the baked-in base rotation.
          rotation: (baseRotationById.get(msg.payload.pieceId) ?? 0) + msg.payload.rotation
        });
      } else if (msg.type === 'COMPLETE') {
        worker.terminate();
        resolve(msg.payload.skippedPieceIds);
      } else if (msg.type === 'ERROR') {
        worker.terminate();
        reject(new Error(msg.payload.message));
      }
    };

    // Without these, a worker that fails to load or crashes leaves the
    // promise unsettled forever (and the caller's spinner stuck).
    worker.onerror = (e) => {
      worker.terminate();
      reject(new Error(e.message || 'Nesting worker failed to start'));
    };
    worker.onmessageerror = () => {
      worker.terminate();
      reject(new Error('Nesting worker message could not be deserialized'));
    };

    const baseRotationById = new Map(pieces.map(p => [p.id, p.transform.rotation]));
    const payloadPieces = pieces.map(p => {
      const flat = flattenCurves(p.polygon, p.curvePoints);
      const centroid = computeCentroid(flat);

      const s = p.transform.scale;
      const cos = Math.cos(p.transform.rotation);
      const sin = Math.sin(p.transform.rotation);
      // Bake the piece's current rotation into the base polygon so the
      // worker's trial rotations are relative to the user's orientation —
      // with rotations disabled, a manually rotated piece keeps its angle
      // instead of snapping back to 0.
      const poly = flat.map(([px, py]) => {
        const dx = s * (px - centroid.x);
        const dy = s * (py - centroid.y);
        return { x: cos * dx - sin * dy, y: sin * dx + cos * dy };
      });
      
      // Calculate a padded bounding box to account for gapPx on the piece
      // Alternatively, we handle gap in the math utility. We do handle it in the math utility now!
      return {
        id: p.id,
        polygon: poly,
        // When reconstructing the final position in SheetPanel, the UI sets Piece.transform.x to the centroid.
        // So we need to map the worker's top-left output back to the piece's original coordinate system logic.
        // Or wait! The worker just returns (x, y) as the displacement of the (0,0) origin of the piece.
        // Our piece poly is already centered at (0,0) (since we subtracted centroid).
        // That means placing this poly at (tx, ty) makes its centroid (tx, ty).
        // So centroidOffsetX/Y is exactly 0.
        centroidOffsetX: 0,
        centroidOffsetY: 0
      };
    });

    // Sort pieces by bounding box area descending
    payloadPieces.sort((a, b) => {
      let minXA=Infinity, maxXA=-Infinity, minYA=Infinity, maxYA=-Infinity;
      for (const pt of a.polygon) {
        if (pt.x < minXA) minXA=pt.x; if (pt.x > maxXA) maxXA=pt.x;
        if (pt.y < minYA) minYA=pt.y; if (pt.y > maxYA) maxYA=pt.y;
      }
      let minXB=Infinity, maxXB=-Infinity, minYB=Infinity, maxYB=-Infinity;
      for (const pt of b.polygon) {
        if (pt.x < minXB) minXB=pt.x; if (pt.x > maxXB) maxXB=pt.x;
        if (pt.y < minYB) minYB=pt.y; if (pt.y > maxYB) maxYB=pt.y;
      }
      return ((maxXB-minXB)*(maxYB-minYB)) - ((maxXA-minXA)*(maxYA-minYA));
    });

    worker.postMessage({
      type: 'START',
      payload: { pieces: payloadPieces, bin, allowRotations, gapPx }
    } as NestingWorkerMessage);
  });
}
