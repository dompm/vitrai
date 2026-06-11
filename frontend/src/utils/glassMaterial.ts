import type { GlassCategory, GlassMaterialParams, GlassSheet, GlassSurface, Scale } from '../types';

// Per-category optical presets. `translucency` is the single user-facing knob;
// the category sets where it lands by default and what range makes sense.
interface CategoryPreset {
  transmissionBase: number;
  translucencyDefault: number;
  translucencyRange: [number, number];
  roughnessDefault: number;
  roughnessRange: [number, number];
}

export const CATEGORY_PRESETS: Record<GlassCategory, CategoryPreset> = {
  transparent: {
    transmissionBase: 0.9,
    translucencyDefault: 0.85,
    translucencyRange: [0.6, 1.0],
    roughnessDefault: 0.05,
    roughnessRange: [0.0, 0.3],
  },
  wispy: {
    transmissionBase: 0.5,
    translucencyDefault: 0.6,
    translucencyRange: [0.35, 0.8],
    roughnessDefault: 0.2,
    roughnessRange: [0.05, 0.5],
  },
  opalescent: {
    transmissionBase: 0.15,
    translucencyDefault: 0.35,
    translucencyRange: [0.15, 0.55],
    roughnessDefault: 0.35,
    roughnessRange: [0.15, 0.6],
  },
  opaque: {
    transmissionBase: 0.0,
    translucencyDefault: 0.1,
    translucencyRange: [0.0, 0.25],
    roughnessDefault: 0.5,
    roughnessRange: [0.3, 0.85],
  },
};

export const SURFACE_ROUGHNESS_OFFSET: Record<GlassSurface, number> = {
  smooth: 0,
  seedy: 0.05,
  rippled: 0.1,
  hammered: 0.15,
};

export const GLASS_CATEGORIES = Object.keys(CATEGORY_PRESETS) as GlassCategory[];
export const GLASS_SURFACES = Object.keys(SURFACE_ROUGHNESS_OFFSET) as GlassSurface[];

export const DEFAULT_MATERIAL: GlassMaterialParams = {
  category: 'opalescent',
  surface: 'smooth',
  translucency: 0.35,
  roughness: 0.35,
  source: 'default',
};

export function getSheetMaterial(sheet: GlassSheet): GlassMaterialParams {
  return sheet.material ?? DEFAULT_MATERIAL;
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

/** Defaults for a freshly selected category, e.g. when the user switches the dropdown. */
export function materialForCategory(category: GlassCategory, surface: GlassSurface = 'smooth'): GlassMaterialParams {
  const preset = CATEGORY_PRESETS[category];
  return {
    category,
    surface,
    translucency: preset.translucencyDefault,
    roughness: clamp(preset.roughnessDefault + SURFACE_ROUGHNESS_OFFSET[surface], 0, 1),
    source: 'user',
  };
}

// Glow strength multiplier under ACES tone mapping; tuned alongside BULB_SCALE
// in Lamp3DPreview.
const EMISSIVE_SCALE = 1.0;
const GLASS_THICKNESS_MM = 3;

export interface GlassRenderParams {
  transmission: number;
  roughness: number;
  ior: number;
  thickness: number; // in pattern px
  emissiveIntensity: number;
}

export function toRenderParams(
  params: GlassMaterialParams,
  bulbIntensity: number,
  patternScale: Scale | null,
): GlassRenderParams {
  const preset = CATEGORY_PRESETS[params.category];
  const transmission = preset.transmissionBase === 0
    ? 0
    : clamp(preset.transmissionBase * (params.translucency / preset.translucencyDefault), 0, 0.95);

  // Geometry lives in pattern pixels, so a real-world thickness must go
  // through the pattern scale (same conversion as the solder radius).
  let thickness = GLASS_THICKNESS_MM;
  if (patternScale) {
    const { pxPerUnit, unit } = patternScale;
    if (unit === 'in') thickness = (GLASS_THICKNESS_MM / 25.4) * pxPerUnit;
    else if (unit === 'cm') thickness = (GLASS_THICKNESS_MM / 10) * pxPerUnit;
    else thickness = GLASS_THICKNESS_MM * pxPerUnit;
  }

  return {
    transmission,
    roughness: clamp(params.roughness, 0, 1),
    ior: 1.5,
    thickness,
    emissiveIntensity: bulbIntensity * params.translucency * EMISSIVE_SCALE,
  };
}

// ── VLM prompts & response parsing ──────────────────────────────────────────
// Two single-letter multiple-choice questions instead of one free-form JSON
// answer: small VLMs are reliable classifiers but poor at structured numeric
// output, so the numbers come from the category presets instead.

export const VLM_CATEGORY_PROMPT = `This is a photo of a sheet of stained glass. How much light would pass through this glass?
Answer with ONLY one letter:
A = clear transparent glass, you could see shapes through it
B = translucent colored glass with wispy white streaks mixed in
C = milky opalescent glass, would glow when backlit but cannot be seen through
D = dense dark glass that blocks nearly all light
Answer:`;

export const VLM_SURFACE_PROMPT = `This is a photo of a sheet of stained glass. What is the surface texture of the glass?
Answer with ONLY one letter:
A = smooth and even
B = seedy, with tiny bubbles inside
C = hammered, with small round dimples
D = rippled, with long wavy ridges
Answer:`;

const CATEGORY_BY_LETTER: GlassCategory[] = ['transparent', 'wispy', 'opalescent', 'opaque'];
const SURFACE_BY_LETTER: GlassSurface[] = ['smooth', 'seedy', 'hammered', 'rippled'];

function parseLetter(text: string): number | null {
  const m = text.toUpperCase().match(/\b([ABCD])\b/);
  return m ? m[1].charCodeAt(0) - 65 : null;
}

/**
 * Combine the two single-letter answers into material params. Unparseable
 * answers fall back to the defaults, so the worst case is a sensible material.
 */
export function parseVlmChoices(categoryAnswer: string, surfaceAnswer: string): GlassMaterialParams {
  const catIdx = parseLetter(categoryAnswer);
  const surfIdx = parseLetter(surfaceAnswer);
  const category = catIdx !== null ? CATEGORY_BY_LETTER[catIdx] : DEFAULT_MATERIAL.category;
  const surface = surfIdx !== null ? SURFACE_BY_LETTER[surfIdx] : DEFAULT_MATERIAL.surface;
  const preset = CATEGORY_PRESETS[category];
  return {
    category,
    surface,
    translucency: preset.translucencyDefault,
    roughness: clamp(preset.roughnessDefault + SURFACE_ROUGHNESS_OFFSET[surface], 0, 1),
    source: 'estimated',
  };
}
