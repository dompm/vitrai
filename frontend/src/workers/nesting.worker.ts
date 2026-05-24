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
}

export type NestingWorkerMessage = NestingStartMessage;
export type NestingWorkerResponse = NestingProgressMessage | NestingCompleteMessage;

self.onmessage = (e: MessageEvent<NestingWorkerMessage>) => {
  if (e.data.type === 'START') {
    const { pieces, bin, allowRotations, gapPx } = e.data.payload;
    const placedPolys: Polygon[] = [];

    // Sort pieces by area or bounding box size descending, so larger pieces are packed first
    // In actual implementation, we might receive them already sorted by height, but area is generally better for nesting.
    
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
            x: result.x + piece.centroidOffsetX, // We return the top-left offset to match how frontend places the transform
            y: result.y + piece.centroidOffsetY,
            rotation: result.rotation
          }
        });
      }
    }

    self.postMessage({ type: 'COMPLETE' });
  }
};
