import { findBestPlacement, Polygon } from '../utils/nestingMath';

export interface NestingStartMessage {
  type: 'START';
  payload: {
    pieces: { id: string; polygon: Polygon; centroidOffsetX: number; centroidOffsetY: number }[];
    bin: Polygon;
    allowRotations: boolean;
    gapPx: number;
  };
}

export interface NestingProgressMessage {
  type: 'PROGRESS';
  payload: {
    pieceId: string;
    x: number;
    y: number;
    rotation: number;
  };
}

export interface NestingCompleteMessage {
  type: 'COMPLETE';
  // Pieces that could not be placed (e.g. larger than the sheet's usable
  // area); they keep their old position and the caller should tell the user.
  payload: { skippedPieceIds: string[] };
}

export interface NestingErrorMessage {
  type: 'ERROR';
  payload: { message: string };
}

export type NestingWorkerMessage = NestingStartMessage;
export type NestingWorkerResponse = NestingProgressMessage | NestingCompleteMessage | NestingErrorMessage;

self.onmessage = (e: MessageEvent<NestingWorkerMessage>) => {
  if (e.data.type === 'START') {
    const { pieces, bin, allowRotations, gapPx } = e.data.payload;
    const placedPolys: Polygon[] = [];
    const skippedPieceIds: string[] = [];

    try {
      for (const piece of pieces) {
        const result = findBestPlacement(piece.polygon, placedPolys, bin, allowRotations, gapPx);
        if (result) {
          // Transform the placed piece to add to our placed polys list
          const cos = Math.cos(result.rotation);
          const sin = Math.sin(result.rotation);
          const finalPoly = piece.polygon.map(p => {
            const rx = p.x * cos - p.y * sin;
            const ry = p.x * sin + p.y * cos;
            return { x: rx + result.x, y: ry + result.y };
          });
          
          placedPolys.push(finalPoly);
          
          self.postMessage({
            type: 'PROGRESS',
            payload: {
              pieceId: piece.id,
              x: result.x + piece.centroidOffsetX,
              y: result.y + piece.centroidOffsetY,
              rotation: result.rotation
            }
          });
        } else {
          skippedPieceIds.push(piece.id);
        }
      }
    } catch (err) {
      self.postMessage({
        type: 'ERROR',
        payload: { message: err instanceof Error ? err.message : String(err) },
      });
      return;
    }
    self.postMessage({ type: 'COMPLETE', payload: { skippedPieceIds } });
  }
};
