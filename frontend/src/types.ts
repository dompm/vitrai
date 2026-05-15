export interface TextureTransform {
  x: number;        // outline center x on glass sheet (glass sheet pixels)
  y: number;        // outline center y on glass sheet (glass sheet pixels)
  rotation: number; // rotation in radians
  scale: number;    // glass pixels per pattern pixel
}

export interface Crop {
  top: number;    // pixels to hide from top
  left: number;
  bottom: number; // pixels to hide from bottom
  right: number;  // pixels to hide from right
}

export type ScaleUnit = 'mm' | 'cm' | 'in';
export interface Scale {
  pxPerUnit: number;
  unit: ScaleUnit;
  line: { x1: number; y1: number; x2: number; y2: number };
}

export interface BoundingBox {
  x1: number; y1: number;
  x2: number; y2: number;
}

export interface PromptPoint {
  x: number;
  y: number;
  label: 1 | 0; // 1 for positive, 0 for negative
}

export interface Piece {
  id: string;
  label: string;
  polygon: [number, number][]; // points in pattern image pixel coordinates
  glassSheetId: string;
  transform: TextureTransform;
  promptBox?: BoundingBox;
  promptPoints?: PromptPoint[];
  notes?: string;
}

export interface GlassSheet {
  id: string;
  label: string;
  imageUrl: string;
  crop: Crop;
  scale: Scale | null;
  naturalWidth?: number;
  naturalHeight?: number;
}

export interface Project {
  name: string;
  patternImageUrl: string;
  patternWidth: number;
  patternHeight: number;
  patternCrop: Crop;
  patternScale: Scale | null;
  pieces: Piece[];
  sheets: GlassSheet[];
}
