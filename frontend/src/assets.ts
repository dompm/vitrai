import type { Scale } from './types';

/**
 * Uncropped photos used by the on-boarding tutorial (DEFAULT_PROJECT).
 * The label "Orange" is matched in defaultProject.ts to apply a scale, so
 * don't rename it without updating that check.
 */
export const TUTORIAL_GLASS_ASSETS = [
  { url: '/assets/green.png', label: 'Green' },
  { url: '/assets/orange.png', label: 'Orange' },
] as const;

/**
 * Built-in hammered-glass swatches offered by the "Add sheet" dropdown.
 * Pre-calibrated: every swatch is an 800×800 JPEG cropped from a photo of
 * a 12-inch glass tile, so the full image width = 12 inches.
 */
const DEFAULT_SCALE: Scale = {
  pxPerUnit: 800 / 12,
  unit: 'in',
  line: { x1: 0, y1: 400, x2: 800, y2: 400 },
};

export interface DefaultGlassAsset {
  url: string;
  label: string;
  scale: Scale;
}

export const DEFAULT_GLASS_ASSETS: readonly DefaultGlassAsset[] = [
  { url: '/assets/glass/turquoise.jpg', label: 'Turquoise', scale: DEFAULT_SCALE },
  { url: '/assets/glass/orange.jpg', label: 'Orange', scale: DEFAULT_SCALE },
  { url: '/assets/glass/amber.jpg', label: 'Amber', scale: DEFAULT_SCALE },
  { url: '/assets/glass/yellow.jpg', label: 'Yellow', scale: DEFAULT_SCALE },
  { url: '/assets/glass/green.jpg', label: 'Green', scale: DEFAULT_SCALE },
  { url: '/assets/glass/blue.jpg', label: 'Cobalt Blue', scale: DEFAULT_SCALE },
  { url: '/assets/glass/red.jpg', label: 'Red', scale: DEFAULT_SCALE },
  { url: '/assets/glass/pink.jpg', label: 'Pink', scale: DEFAULT_SCALE },
  { url: '/assets/glass/white.jpg', label: 'White', scale: DEFAULT_SCALE },
  { url: '/assets/glass/black.jpg', label: 'Black', scale: DEFAULT_SCALE },
];
