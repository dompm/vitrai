import type { Project } from './types';
import { GLASS_ASSETS } from './assets';

const NO_CROP = { top: 0, left: 0, bottom: 0, right: 0 };

export const DEFAULT_PROJECT: Project = {
  patternImageUrl: '/assets/mountains_pattern.png',
  patternWidth: 1214,
  patternHeight: 1156,
  patternCrop: NO_CROP,
  patternScale: null,
  pieces: [],
  sheets: GLASS_ASSETS.map((g, i) => ({
    id: `sheet-${i + 1}`,
    label: g.label,
    imageUrl: g.url,
    crop: NO_CROP,
    scale: null,
  })),
};
