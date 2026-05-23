/**
 * Uncropped photos used by the on-boarding tutorial (DEFAULT_PROJECT).
 * The label "Orange" is matched in defaultProject.ts to apply a scale, so
 * don't rename it without updating that check.
 */
export const TUTORIAL_GLASS_ASSETS = [
  { url: '/assets/green.png', label: 'Green' },
  { url: '/assets/orange.png', label: 'Orange' },
] as const;

/** Built-in hammered-glass swatches offered by the "Add sheet" dropdown. */
export const DEFAULT_GLASS_ASSETS = [
  { url: '/assets/glass/turquoise.jpg', label: 'Turquoise' },
  { url: '/assets/glass/orange.jpg', label: 'Orange' },
  { url: '/assets/glass/amber.jpg', label: 'Amber' },
  { url: '/assets/glass/green.jpg', label: 'Green' },
  { url: '/assets/glass/blue.jpg', label: 'Cobalt Blue' },
  { url: '/assets/glass/red.jpg', label: 'Red' },
  { url: '/assets/glass/pink.jpg', label: 'Pink' },
  { url: '/assets/glass/white.jpg', label: 'White' },
  { url: '/assets/glass/black.jpg', label: 'Black' },
] as const;
