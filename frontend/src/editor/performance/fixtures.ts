import type { Piece, Project } from '../../types';
import { EMPTY_PROJECT } from '../../defaultProject';

export const INTERACTION_SHEET_ID = 'interaction-performance-sheet';
export const INTERACTION_SHEET = {
  id: INTERACTION_SHEET_ID,
  label: 'Performance glass',
  imageUrl: '',
  crop: { top: 0, left: 0, bottom: 0, right: 0 },
  scale: null,
  naturalWidth: 1200,
  naturalHeight: 900,
} as const;

export const INTERACTION_PIECE_COUNTS = [25, 100, 250, 500] as const;
export const INTERACTION_VERTEX_COUNTS = [6, 24, 96] as const;

function polygonFor(index: number, vertexCount: number): [number, number][] {
  const column = index % 25;
  const row = Math.floor(index / 25);
  const centerX = 30 + column * 44;
  const centerY = 30 + row * 44;
  return Array.from({ length: vertexCount }, (_, vertexIndex) => {
    const angle = (vertexIndex / vertexCount) * Math.PI * 2;
    const radius = vertexIndex % 2 === 0 ? 18 : 15;
    return [centerX + Math.cos(angle) * radius, centerY + Math.sin(angle) * radius];
  });
}

export function makeInteractionPieces(pieceCount: number, vertexCount: number): Piece[] {
  return Array.from({ length: pieceCount }, (_, index) => ({
    id: `perf-${pieceCount}-${vertexCount}-${index}`,
    label: `Piece ${index + 1}`,
    polygon: polygonFor(index, vertexCount),
    glassSheetId: INTERACTION_SHEET_ID,
    transform: { x: 30 + (index % 25) * 44, y: 30 + Math.floor(index / 25) * 44, rotation: 0, scale: 1 },
  }));
}

export function makeInteractionProject(pieceCount: number, vertexCount: number): Project {
  return {
    ...EMPTY_PROJECT,
    name: `interaction-${pieceCount}x${vertexCount}`,
    sheets: [{ ...INTERACTION_SHEET }],
    pieces: makeInteractionPieces(pieceCount, vertexCount),
  };
}
