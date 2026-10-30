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

  // Precision Selection & Transform Overlay
  // High-luminance Warm Gold (#FFD447) inside a thick dark casing (rgba(0,0,0,0.92))
  // so outlines have strong luminance contrast even on amber/orange hammered glass.
  selection: '#FFD447',
  selectionHalo: 'rgba(0, 0, 0, 0.92)',
  selectionFill: 'rgba(255, 212, 71, 0.14)',
  sheetSelectionFill: 'rgba(255, 255, 255, 0.16)',
  selectionHandle: '#ffffff',
  selectionHandleBorder: '#1c1917',
  selectionHandleStem: '#FFD447',
  selectionHandleStemHalo: 'rgba(0, 0, 0, 0.92)',

  // Precision vertex anchor nodes (square 6x6px white with dark + brass contrast)
  nodeFill: '#ffffff',
  nodeBorder: '#1c1917',
  nodeBorderWidth: 1.5,
  nodeSize: 6,

  // Idle piece outlines on cut sheets (dual-stroke white on dark casing)
  idleStroke: '#ffffff',
  idleHalo: 'rgba(0, 0, 0, 0.88)',
  idleFill: 'rgba(255, 255, 255, 0.05)',

  // Marquee selection box
  marqueeStroke: '#C48820',
  marqueeFill: 'rgba(196, 136, 32, 0.10)',

  // Backward-compatibility aliases for existing calls to amber*
  amber: '#C48820',
  amberSelectionFill: 'rgba(196, 136, 32, 0.12)',
  amberHandle: '#ffffff',
  amberHandleStem: '#C48820',
  amberIdleStroke: '#ffffff',
  amberIdleFill: 'rgba(255, 255, 255, 0.04)',
  amberSelectedFill: 'rgba(196, 136, 32, 0.12)',

  ruby: '#a13f30',        // --ruby — negative prompt points
  paper: '#ffffff',       // --paper — crisp neutral white for templates/canvas paper
  patternPending: '#d99b26', // burnished gold — pulsing while SAM segments
  promptBoxStroke: 'rgba(196, 136, 32, 0.35)',
  drawingBoxStroke: '#C48820',
  drawingBoxFill: 'rgba(196, 136, 32, 0.10)',
  handleStroke: '#C48820', // #C48820 border on white rotation handle knob
} as const;
