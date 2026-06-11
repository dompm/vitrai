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

export interface CurvePoint {
  edgeIdx: number;            // index of the start vertex of the curved edge
  ctrl: [number, number];     // quadratic bezier control point (image coords)
}

export interface Piece {
  id: string;
  label: string;
  polygon: [number, number][]; // clean vertex skeleton — never grows from curve edits
  curvePoints?: CurvePoint[];  // parametric curves on edges; absent = all straight
  glassSheetId: string;
  transform: TextureTransform;
  promptBox?: BoundingBox;
  promptPoints?: PromptPoint[];
  tierIndex?: number;          // if present, this piece belongs to a lamp tier
  facetIndex?: number;         // column index for symmetry mirroring
  symmetryGroupId?: string;    // links symmetrical duplicates
}

export type GlassCategory = 'transparent' | 'wispy' | 'opalescent' | 'opaque';
export type GlassSurface = 'smooth' | 'seedy' | 'hammered' | 'rippled';

export interface GlassMaterialParams {
  category: GlassCategory;
  surface: GlassSurface;
  translucency: number;  // 0..1 — drives both transmission and lit-from-within glow
  roughness: number;     // 0..1
  glowTint?: string;     // hex, default '#ffffff'
  source: 'default' | 'estimated' | 'user';
}

export interface GlassSheet {
  id: string;
  label: string;
  imageUrl: string;
  crop: Crop;
  scale: Scale | null;
  naturalWidth?: number;
  naturalHeight?: number;
  swatch?: string; // dominant color, e.g. "#3a6da8"
  material?: GlassMaterialParams;
}

export type SolderColor = 'black' | 'silver' | 'copper';

export interface LampProfilePoint {
  r: number;
  y: number;
}

export interface LampConfig {
  facetCount: number;
  profilePoints: LampProfilePoint[];
  activeTierIndex: number;
  // When true, the lamp surface is treated as continuous: each tier unrolls to
  // its true smooth shape (rectangle for a cylinder, annular sector for a cone)
  // instead of N flat facets. `facetCount` is ignored except for visualization.
  smooth?: boolean;
  bulbIntensity?: number; // 0..2, brightness of the bulb inside the lamp (default 1)
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
  solderWidthMM?: number;
  solderColor?: SolderColor;
  projectType?: 'flat' | 'lamp';
  lampConfig?: LampConfig;
}

