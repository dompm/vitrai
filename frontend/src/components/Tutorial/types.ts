import type { ToolId } from '../Toolbar';

export type StepId =
  | 'welcome'
  | 'calibrate-pattern'
  | 'calibrate-sheet'
  | 'cut-piece'
  | 'assign-glass'
  | 'position-texture'
  | 'done';

export const STEP_ORDER: StepId[] = [
  'welcome',
  'calibrate-pattern',
  'calibrate-sheet',
  'cut-piece',
  'assign-glass',
  'position-texture',
  'done',
];

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

/** Steps that show the bottom instruction bar with spotlight. */
export const ANCHORED_STEPS: StepId[] = [
  'calibrate-pattern',
  'calibrate-sheet',
  'cut-piece',
  'assign-glass',
  'position-texture',
];

export const STEPS: Record<(typeof ANCHORED_STEPS)[number], StepConfig> = {
  'calibrate-pattern': {
    id: 'calibrate-pattern',
    spotlightTarget: '[data-tutorial-panel="pattern"] [data-tool-id="measure"]',
    panel: 'pattern',
    forceTool: 'measure',
  },
  'cut-piece': {
    id: 'cut-piece',
    spotlightTarget: '[data-tutorial-panel="pattern"] [data-tool-id="box"]',
    panel: 'pattern',
    forceTool: 'box',
  },
  'calibrate-sheet': {
    id: 'calibrate-sheet',
    spotlightTarget: '[data-tutorial-panel="glass"] [data-tool-id="measure"]',
    panel: 'glass',
    forceTool: 'measure',
  },
  'assign-glass': {
    id: 'assign-glass',
    spotlightTarget: '[data-tutorial-target="piece-glass-select"]',
    panel: 'pattern',
  },
  'position-texture': {
    id: 'position-texture',
    // No specific target — the user drags the piece on the glass canvas
    panel: 'glass',
  },
};

export const STORAGE_KEY = 'vitrai-tutorial-state';

export interface PersistedTutorialState {
  /** Last step the user was on, or null if completed. */
  step: StepId | null;
  /** Set true once the user has either completed or explicitly skipped. */
  completed: boolean;
  /** ID of the piece the tour is following (set after cut-piece). */
  pieceId: string | null;
}
