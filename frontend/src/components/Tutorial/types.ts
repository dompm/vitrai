import type { ToolId } from '../Toolbar';

export type TrackId = 'ai-tracing' | 'vector-drawing' | 'lamp-creator' | 'fabrication';

export type StepId =
  | 'welcome'
  // ai-tracing steps
  | 'calibrate-pattern'
  | 'calibrate-sheet'
  | 'cut-first-piece'
  | 'refine-first-piece'
  | 'assign-first-glass'
  | 'position-first-texture'
  | 'cut-second-piece'
  | 'refine-second-piece'
  | 'cut-remaining-pieces'
  | 'refine-remaining-pieces'
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
    'calibrate-sheet',
    'cut-first-piece',
    'refine-first-piece',
    'assign-first-glass',
    'position-first-texture',
    'cut-second-piece',
    'refine-second-piece',
    'cut-remaining-pieces',
    'refine-remaining-pieces',
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
    'lamp-preview-3d',
    'done',
  ],
  'fabrication': [
    'welcome',
    'fab-solder-thickness',
    'fab-smart-pack',
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
  /** Tool to force-switch the panel's toolbar to when this step becomes active. */
  forceTool?: ToolId;
}

/** Steps that show the bottom instruction bar with spotlight (all but the welcome/done overlays). */
export type AnchoredStepId = Exclude<StepId, 'welcome' | 'done'>;

export const ANCHORED_STEPS: StepId[] = [
  'calibrate-pattern',
  'calibrate-sheet',
  'cut-first-piece',
  'refine-first-piece',
  'assign-first-glass',
  'position-first-texture',
  'cut-second-piece',
  'refine-second-piece',
  'cut-remaining-pieces',
  'refine-remaining-pieces',
  'vector-blank-canvas',
  'vector-draw-shape',
  'vector-snap-angles',
  'vector-curve-edge',
  'vector-assign-glass',
  'vector-position-texture',
  'lamp-profile-intro',
  'lamp-edit-profile',
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
  'calibrate-sheet': {
    id: 'calibrate-sheet',
    spotlightTarget: '[data-tutorial-panel="glass"] [data-tool-id="measure"]',
    panel: 'glass',
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
  'assign-first-glass': {
    id: 'assign-first-glass',
    spotlightTarget: '[data-tutorial-target="piece-glass-select"]',
    panel: 'pattern',
  },
  'position-first-texture': {
    id: 'position-first-texture',
    panel: 'glass',
  },
  'cut-second-piece': {
    id: 'cut-second-piece',
    spotlightTarget: '[data-tutorial-panel="pattern"] [data-tool-id="box"]',
    panel: 'pattern',
  },
  'refine-second-piece': {
    id: 'refine-second-piece',
    spotlightTarget: '[data-tutorial-target="piece-refine-buttons"]',
    panel: 'pattern',
  },
  'cut-remaining-pieces': {
    id: 'cut-remaining-pieces',
    spotlightTarget: '[data-tutorial-panel="pattern"] [data-tool-id="box"]',
    panel: 'pattern',
  },
  'refine-remaining-pieces': {
    id: 'refine-remaining-pieces',
    spotlightTarget: '[data-tutorial-target="piece-refine-buttons"]',
    panel: 'pattern',
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
    spotlightTarget: '.lamp-profile-canvas',
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
}

// Ground truth polygons for the target orange slice and leaves in the tutorial.
export const GT_PIECE_1: [number, number][] = [
  [1474.21875, 1446.328125],
  [1956.328125, 1968.28125],
  [2526.09375, 2227.265625],
  [2494.21875, 2410.546875],
  [2267.109375, 2717.34375],
  [2119.6875, 2848.828125],
  [1868.671875, 2972.34375],
  [1434.375, 2980.3125],
  [1155.46875, 2844.84375],
  [916.40625, 2557.96875],
  [844.6875, 2366.71875],
  [1075.78125, 2020.078125],
  [1175.390625, 1613.671875],
  [1470.234375, 1450.3125]
];

export const GT_PIECE_2: [number, number][] = [
  [1514.0625, 1374.609375],
  [1940.390625, 1310.859375],
  [1944.375, 1306.875],
  [2302.96875, 1366.640625],
  [2510.15625, 1478.203125],
  [2705.390625, 1713.28125],
  [2912.578125, 2091.796875],
  [2912.578125, 2139.609375],
  [2460.3515625, 2197.3828125],
  [2466.328125, 2151.5625],
  [2071.902290239726, 2020.8149614726028],
  [1820.633482662254, 1821.3721744112006],
  [1514.0625, 1374.609375]
];

export const GT_PIECE_3: [number, number][] = [
  [398.4375, 2111.71875],
  [410.390625, 2055.9375],
  [557.8125, 1972.265625],
  [713.203125, 1828.828125],
  [996.09375, 1386.5625],
  [1000.078125, 1382.578125],
  [1083.75, 1406.484375],
  [1167.421875, 1577.8125],
  [1170.3329361796173, 1634.3072453871612],
  [1054.9399038461538, 2051.340144230769],
  [902.3076923076923, 2280.2884615384614],
  [893.1129807692307, 2294.080528846154],
  [887.5961538461538, 2302.355769230769],
  [877.7884615384615, 2317.0673076923076],
  [852.0432692307693, 2355.685096153846],
  [768.984375, 2366.71875],
  [422.34375, 2729.296875],
  [398.4375, 2685.46875],
  [398.4375, 2111.71875]
];

export const GT_PIECE_4: [number, number][] = [
  [127.5, 2147.578125],
  [139.453125, 2020.078125],
  [207.1875, 1812.890625],
  [426.328125, 1354.6875],
  [589.6875, 1231.171875],
  [848.671875, 1143.515625],
  [972.1875, 1031.953125],
  [976.171875, 1027.96875],
  [1039.921875, 1039.921875],
  [1055.859375, 1111.640625],
  [1012.7078419811321, 1386.1866155660377],
  [1000.078125, 1382.578125],
  [996.09375, 1386.5625],
  [969.5513684699343, 1428.0583359132013],
  [912.1161966507315, 1517.8513510108282],
  [679.9405950479234, 1828.828125],
  [557.8125, 1972.265625],
  [410.390625, 2055.9375],
  [398.4375, 2111.71875]
];

export const TUTORIAL_GROUND_TRUTH_POLYGONS: [number, number][][] = [
  GT_PIECE_1,
  GT_PIECE_2,
  GT_PIECE_3,
  GT_PIECE_4,
];

export const IS_PLACEHOLDER_GROUND_TRUTH = false;

