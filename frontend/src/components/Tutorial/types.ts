export type TrackId = 'ai-tracing' | 'vector-drawing' | 'lamp-creator' | 'fabrication';

export type StepId =
  | 'welcome'
  // ai-tracing steps
  | 'calibrate-pattern'
  | 'cut-first-piece'
  | 'refine-first-piece'
  | 'trace-hand-pen'
  | 'assign-first-glass'
  | 'position-first-texture'
  // vector-drawing steps
  | 'vector-blank-canvas'
  | 'vector-draw-shape'
  | 'vector-snap-angles'
  | 'vector-curve-edge'
  | 'vector-assign-glass'
  | 'vector-position-texture'
  // lamp-creator steps
  | 'lamp-profile-intro'
  | 'lamp-edit-profile'
  | 'lamp-choose-pen'
  | 'lamp-draw-facet'
  | 'lamp-symmetry'
  | 'lamp-preview-3d'
  // fabrication steps
  | 'fab-solder-thickness'
  | 'fab-smart-pack'
  | 'fab-print-layout'
  | 'done';

export const TRACK_STEPS: Record<TrackId, StepId[]> = {
  'ai-tracing': [
    'welcome',
    'calibrate-pattern',
    'cut-first-piece',
    'refine-first-piece',
    'trace-hand-pen',
    'assign-first-glass',
    'position-first-texture',
    'done',
  ],
  'vector-drawing': [
    'welcome',
    'vector-blank-canvas',
    'vector-draw-shape',
    'vector-snap-angles',
    'vector-curve-edge',
    'vector-assign-glass',
    'vector-position-texture',
    'done',
  ],
  'lamp-creator': [
    'welcome',
    'lamp-profile-intro',
    'lamp-edit-profile',
    'lamp-symmetry',
    'lamp-choose-pen',
    'lamp-draw-facet',
    'lamp-preview-3d',
    'done',
  ],
  'fabrication': [
    'welcome',
    'fab-smart-pack',
    'fab-solder-thickness',
    'fab-print-layout',
    'done',
  ],
};

export type TargetPanel = 'pattern' | 'glass';

export interface StepConfig {
  id: StepId;
  /** CSS selector for the spotlight pulse highlight; if absent, no spotlight. */
  spotlightTarget?: string;
  /** Which panel the user should be looking at. */
  panel?: TargetPanel;
}

/** Steps that show the bottom instruction bar with spotlight (all but the welcome/done overlays). */
export type AnchoredStepId = Exclude<StepId, 'welcome' | 'done'>;

export const ANCHORED_STEPS: StepId[] = [
  'calibrate-pattern',
  'cut-first-piece',
  'refine-first-piece',
  'trace-hand-pen',
  'assign-first-glass',
  'position-first-texture',
  'vector-blank-canvas',
  'vector-draw-shape',
  'vector-snap-angles',
  'vector-curve-edge',
  'vector-assign-glass',
  'vector-position-texture',
  'lamp-profile-intro',
  'lamp-edit-profile',
  'lamp-choose-pen',
  'lamp-draw-facet',
  'lamp-symmetry',
  'lamp-preview-3d',
  'fab-solder-thickness',
  'fab-smart-pack',
  'fab-print-layout',
];

export const STEPS: Record<AnchoredStepId, StepConfig> = {
  // ai-tracing
  'calibrate-pattern': {
    id: 'calibrate-pattern',
    spotlightTarget: '[data-tutorial-panel="pattern"] [data-tool-id="measure"]',
    panel: 'pattern',
  },
  'cut-first-piece': {
    id: 'cut-first-piece',
    spotlightTarget: '[data-tutorial-panel="pattern"] [data-tool-id="box"]',
    panel: 'pattern',
  },
  'refine-first-piece': {
    id: 'refine-first-piece',
    spotlightTarget: '[data-tutorial-target="piece-refine-buttons"]',
    panel: 'pattern',
  },
  'trace-hand-pen': {
    id: 'trace-hand-pen',
    spotlightTarget: '[data-tutorial-panel="pattern"] [data-tool-id="pen"]',
    panel: 'pattern',
  },
  'assign-first-glass': {
    id: 'assign-first-glass',
    spotlightTarget: '[data-tutorial-target="piece-glass-select"]',
    panel: 'pattern',
  },
  'position-first-texture': {
    id: 'position-first-texture',
    panel: 'glass',
  },

  // vector-drawing
  'vector-blank-canvas': {
    id: 'vector-blank-canvas',
    spotlightTarget: '[data-tutorial-panel="pattern"] [data-tool-id="pen"]',
    panel: 'pattern',
  },
  'vector-draw-shape': {
    id: 'vector-draw-shape',
    panel: 'pattern',
  },
  'vector-snap-angles': {
    id: 'vector-snap-angles',
    spotlightTarget: '[data-tutorial-panel="pattern"] [data-tool-id="select"]',
    panel: 'pattern',
  },
  'vector-curve-edge': {
    id: 'vector-curve-edge',
    panel: 'pattern',
  },
  'vector-assign-glass': {
    id: 'vector-assign-glass',
    spotlightTarget: '[data-tutorial-target="piece-glass-select"]',
    panel: 'pattern',
  },
  'vector-position-texture': {
    id: 'vector-position-texture',
    panel: 'glass',
  },

  // lamp-creator
  'lamp-profile-intro': {
    id: 'lamp-profile-intro',
    spotlightTarget: '[data-tutorial-target="lamp-profile-button"]',
    panel: 'pattern',
  },
  'lamp-edit-profile': {
    id: 'lamp-edit-profile',
    spotlightTarget: '[data-tutorial-target="lamp-profile-editor"]',
    panel: 'pattern',
  },
  'lamp-choose-pen': {
    id: 'lamp-choose-pen',
    spotlightTarget: '[data-tutorial-panel="pattern"] [data-tool-id="pen"]',
    panel: 'pattern',
  },
  'lamp-draw-facet': {
    id: 'lamp-draw-facet',
    panel: 'pattern',
  },
  'lamp-symmetry': {
    id: 'lamp-symmetry',
    spotlightTarget: '[data-tutorial-target="lamp-symmetry-button"]',
    panel: 'pattern',
  },
  'lamp-preview-3d': {
    id: 'lamp-preview-3d',
    spotlightTarget: '[data-tutorial-target="lamp-3d-preview"]',
    panel: 'pattern',
  },

  // fabrication
  'fab-solder-thickness': {
    id: 'fab-solder-thickness',
    spotlightTarget: '[data-tutorial-target="solder-settings"]',
    panel: 'pattern',
  },
  'fab-smart-pack': {
    id: 'fab-smart-pack',
    spotlightTarget: '[data-tutorial-target="smart-pack-button"]',
    panel: 'glass',
  },
  'fab-print-layout': {
    id: 'fab-print-layout',
    spotlightTarget: '[data-tutorial-target="print-button"]',
    panel: 'pattern',
  },
};

export const STORAGE_KEY = 'vitrai-tutorial-state';

export interface PersistedTutorialState {
  /** Last step the user was on, or null if completed. */
  step: StepId | null;
  /** The active track identifier. */
  activeTrackId: TrackId | null;
  /** Set true once the user has either completed or explicitly skipped. */
  completed: boolean;
  /** ID of the piece the tour is following (set after cut-piece). */
  pieceId: string | null;
  previousProjectName?: string | null;
}
