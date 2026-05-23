import type { Project, Scale } from './types';
import { GLASS_ASSETS } from './assets';

const NO_CROP = { top: 0, left: 0, bottom: 0, right: 0 };

const ORANGE_SCALE: Scale = {
  pxPerUnit: 1300 / 12,
  unit: 'in',
  line: { x1: 758, y1: 768, x2: 2058, y2: 768 },
};

export const DEFAULT_PROJECT: Project = {
  name: 'Orange Pattern',
  patternImageUrl: '/assets/orange-pattern.jpg',
  patternWidth: 3072,
  patternHeight: 4080,
  patternCrop: NO_CROP,
  patternScale: null,
  pieces: [],
  sheets: GLASS_ASSETS.map((g, i) => {
    const isOrange = g.label === 'Orange';
    return {
      id: `sheet-${i + 1}`,
      label: g.label,
      imageUrl: g.url,
      crop: NO_CROP,
      scale: isOrange ? ORANGE_SCALE : null,
    };
  }),
};
export const EMPTY_PROJECT: Project = {
  name: 'Untitled Project',
  patternImageUrl: '',
  patternWidth: 800,
  patternHeight: 600,
  patternCrop: NO_CROP,
  patternScale: null,
  pieces: [],
  sheets: [],
};
