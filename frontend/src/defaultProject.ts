import type { Project } from './types';

const NO_CROP = { top: 0, left: 0, bottom: 0, right: 0 };

export const DEFAULT_PROJECT: Project = {
  patternImageUrl: '/assets/mountains_pattern.png',
  patternWidth: 1214,
  patternHeight: 1156,
  patternCrop: NO_CROP,
  patternScale: null,
  pieces: [],
  sheets: [
    {
      id: 'sheet-1',
      label: 'Sheet 1',
      imageUrl: '/assets/glass1.jpg',
      crop: NO_CROP,
      scale: null,
    },
  ],
};
