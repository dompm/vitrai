/**
 * Canvas / Konva colors.
 *
 * Konva (the canvas-rendering library) needs concrete color values at runtime
 * and can't read CSS variables. Keep every theme-aware color used inside the
 * canvas in this single module so the rest of the JSX stays hex-free.
 *
 * Keep these in sync with the `--*` tokens in App.css.
 */
export const CANVAS = {
  lead: '#1a1a1a',        // --lead — solder lines between pieces
  amber: '#c08a1f',       // --amber — selection accent
  amberSelectionFill: 'rgba(192, 138, 31, 0.10)',
  amberHandle: '#c08a1f',
  amberHandleStem: 'rgba(192, 138, 31, 0.6)',
  amberIdleStroke: 'rgba(192, 138, 31, 0.7)',
  amberIdleFill: 'rgba(192, 138, 31, 0.06)',
  amberSelectedFill: 'rgba(192, 138, 31, 0.14)',
  ruby: '#a13f30',        // --ruby — negative prompt points
  paper: '#fffefa',       // --paper
  patternPending: '#f59e0b', // amber-500 — pulsing while SAM segments
  promptBoxStroke: 'rgba(245,158,11,0.3)',
  drawingBoxStroke: '#f59e0b',
  drawingBoxFill: 'rgba(245,158,11,0.08)',
  handleStroke: '#fffefa', // matches --paper, for white-on-amber rotation handle
} as const;
