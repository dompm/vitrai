import type { ToolId } from '../Toolbar';

export type StepId =
  | 'welcome'
  | 'calibrate-pattern'
  | 'cut-piece'
  | 'calibrate-sheet'
  | 'assign-glass'
  | 'position-texture'
  | 'done';

export const STEP_ORDER: StepId[] = [
  'welcome',
  'calibrate-pattern',
  'cut-piece',
  'calibrate-sheet',
  'assign-glass',
  'position-texture',
  'done',
];

export type TargetPanel = 'pattern' | 'glass';

export interface StepConfig {
  id: StepId;
  /** CSS selector for the coach-mark anchor; if absent the mark renders centered. */
  target?: string;
  /** Preferred side of the target. Coach-mark will choose another if this side overflows. */
  side?: 'top' | 'bottom' | 'left' | 'right';
  /** Which panel the user should be looking at; tutorial may scroll/highlight it. */
  panel?: TargetPanel;
  /** Tool to switch the panel's toolbar to when this step becomes active. */
  forceTool?: ToolId;
}

export const STEPS: Record<Exclude<StepId, 'welcome' | 'done'>, StepConfig> = {
  'calibrate-pattern': {
    id: 'calibrate-pattern',
    target: '[data-tutorial-panel="pattern"] [data-tool-id="measure"]',
    side: 'right',
    panel: 'pattern',
    forceTool: 'measure',
  },
  'cut-piece': {
    id: 'cut-piece',
    target: '[data-tutorial-panel="pattern"] [data-tool-id="box"]',
    side: 'right',
    panel: 'pattern',
    forceTool: 'box',
  },
  'calibrate-sheet': {
    id: 'calibrate-sheet',
    target: '[data-tutorial-panel="glass"] [data-tool-id="measure"]',
    side: 'right',
    panel: 'glass',
    forceTool: 'measure',
  },
  'assign-glass': {
    id: 'assign-glass',
    target: '[data-tutorial-target="piece-glass-select"]',
    side: 'bottom',
    panel: 'pattern',
  },
  'position-texture': {
    id: 'position-texture',
    panel: 'glass',
  },
};

/** Ground-truth measurements for the bundled sample assets.
 * mountains_pattern.png is approximately 12 inches wide in the printed reference.
 * glass1/2/3.jpg are bundled-sheet stand-ins; assume 6 inches wide. */
export const SAMPLE_GROUND_TRUTH = {
  patternWidthInches: 12,
  sheetWidthInches: 6,
} as const;

export const STORAGE_KEY = 'vitrai-tutorial-state';

export interface PersistedTutorialState {
  /** Last step the user was on, or 'done' / null. */
  step: StepId | null;
  /** Set true once the user has either completed or explicitly skipped. */
  completed: boolean;
  /** ID of the piece the tour is following (set after cut-piece). */
  pieceId: string | null;
}
