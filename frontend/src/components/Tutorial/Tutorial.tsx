import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import useImage from 'use-image';
import type { Project } from '../../types';
import { TutorialBar } from './TutorialBar';
import { SpotlightPulse } from './SpotlightPulse';
import { STEPS, ANCHORED_STEPS, TrackId } from './types';
import type { AnchoredStepId, StepId } from './types';
import type { ToolId } from '../Toolbar';

interface Props {
  /** Current step (null = inactive). */
  step: StepId | null;
  activeTrackId: TrackId | null;
  /** Practice piece followed through assignment and texture placement. */
  pieceId: string | null;
  project: Project;
  selectedPieceIds: string[];
  activeSheetId: string;
  patternTool: ToolId;
  sheetTool: ToolId;
  patternRefineMode: 'add' | 'remove' | null;
  isEncoding?: boolean;
  downloadProgress?: number | null;
  isLampProfileOpen?: boolean;
  isSymmetryEnabled?: boolean;
  pendingPieceIds: ReadonlySet<string>;
  onExitRefine: () => void;
  onAdvance: () => void;
  onSetStep: (step: StepId | null) => void;
  onSetTrackedPiece: (id: string) => void;
  onSelectPiece: (id: string | null, multi?: boolean) => void;
  onStartTour: (trackId?: TrackId) => void;
  onSkip: () => void;
  onComplete: () => void;
}

export function Tutorial({
  step,
  activeTrackId,
  pieceId,
  project,
  selectedPieceIds,
  activeSheetId,
  patternTool,
  sheetTool,
  patternRefineMode,
  isEncoding,
  downloadProgress,
  isLampProfileOpen = false,
  isSymmetryEnabled = false,
  pendingPieceIds,
  onExitRefine,
  onAdvance,
  onSetStep,
  onSetTrackedPiece,
  onSelectPiece,
  onStartTour,
  onSkip,
  onComplete,
}: Props) {
  const { t } = useTranslation();
  const [, imageStatus] = useImage(project.patternImageUrl || '');
  const [dismissedLoading, setDismissedLoading] = useState(false);
  const piece = project.pieces.find(p => p.id === pieceId);
  const patternCanvas = '[data-tutorial-panel="pattern"] .canvas-well';
  const glassCanvas = '[data-tutorial-panel="glass"] .canvas-well';
  const previousStep = useRef<StepId | null>(null);
  const [solderStart, setSolderStart] = useState<number | null>(null);
  const profileStart = useRef(project.lampConfig);

  useEffect(() => {
    if (previousStep.current !== step) {
      previousStep.current = step;
      if (step === 'fab-solder-thickness') setSolderStart(project.solderWidthMM ?? 4.5);
      else setSolderStart(null);
    }
    if (step === 'welcome') {
      setDismissedLoading(false);
      profileStart.current = project.lampConfig;
    }
    switch (step) {
      case 'calibrate-pattern':
        if (project.patternScale && patternTool !== 'measure') onAdvance();
        break;
      case 'cut-first-piece':
      case 'vector-draw-shape':
      case 'lamp-draw-facet': {
        const created = project.pieces[0];
        if (created && (step !== 'cut-first-piece' || !pendingPieceIds.has(created.id))) {
          onSetTrackedPiece(created.id);
          onSelectPiece(created.id);
          onAdvance();
        }
        break;
      }
      case 'refine-first-piece':
        if (!piece) onSetStep('cut-first-piece');
        break;
      case 'trace-hand-pen':
        if (project.pieces.length >= 2) {
          if (piece) onSelectPiece(piece.id);
          onAdvance();
        }
        break;
      case 'vector-blank-canvas':
      case 'lamp-choose-pen':
        if (patternTool === 'pen') onAdvance();
        break;
      case 'vector-snap-angles':
        if (!piece) { onSetStep('vector-blank-canvas'); break; }
        if (patternTool === 'select' && piece && selectedPieceIds.includes(piece.id)) onAdvance();
        break;
      case 'position-first-texture':
      case 'vector-position-texture':
      case 'vector-curve-edge':
        if (!piece) onSetStep(activeTrackId === 'ai-tracing' ? 'cut-first-piece' : 'vector-blank-canvas');
        break;
      case 'assign-first-glass':
      case 'vector-assign-glass':
        if (!piece) onSetStep(activeTrackId === 'ai-tracing' ? 'cut-first-piece' : 'vector-blank-canvas');
        else if (piece.glassSheetId === project.sheets[1]?.id) onAdvance();
        break;
      case 'lamp-profile-intro':
        if (isLampProfileOpen) {
          profileStart.current = project.lampConfig;
          onAdvance();
        }
        break;
      case 'lamp-edit-profile':
        if (!isLampProfileOpen) {
          // Cancel is not completion; Save replaces the lamp config.
          if (project.lampConfig !== profileStart.current) onAdvance();
          else onSetStep('lamp-profile-intro');
        }
        break;
      case 'lamp-symmetry':
        if (isSymmetryEnabled) onAdvance();
        break;
      case 'fab-solder-thickness':
        // Keep the slider available until the learner chooses Continue.
        break;

    }
  }, [step, project, piece, patternTool, sheetTool, activeSheetId, selectedPieceIds,
    isLampProfileOpen, isSymmetryEnabled, pendingPieceIds, activeTrackId,
    onAdvance, onSetStep, onSetTrackedPiece, onSelectPiece]);

  if (step === null) return null;
  const config = ANCHORED_STEPS.includes(step) ? STEPS[step as AnchoredStepId] : null;
  let target = config?.spotlightTarget;
  let continueLabel: string | undefined;
  let continueDisabled = false;
  let customBody: string | undefined;
  let customTitle: string | undefined;

  const needsSelection = ['refine-first-piece', 'assign-first-glass', 'vector-snap-angles', 'vector-curve-edge',
    'vector-assign-glass', 'position-first-texture', 'vector-position-texture'].includes(step);
  const selectTrackedPiece = needsSelection && piece && (!selectedPieceIds.includes(piece.id) || activeSheetId !== piece.glassSheetId);

  if (step === 'calibrate-pattern' && patternTool === 'measure' && !project.patternScale) target = patternCanvas;
  if (step === 'cut-first-piece' && patternTool === 'box') target = patternCanvas;
  if (step === 'vector-draw-shape' || step === 'lamp-draw-facet' || step === 'vector-curve-edge') target = patternCanvas;
  if (step === 'position-first-texture' || step === 'vector-position-texture') {
    target = sheetTool === 'select' ? glassCanvas : '[data-tutorial-panel="glass"] [data-tool-id="select"]';
    continueLabel = t('tutorialTextureDone');
    continueDisabled = !piece;
  }
  if (step === 'refine-first-piece') {
    target = patternRefineMode ? patternCanvas : '[data-tutorial-target="piece-refine-buttons"]';
    continueLabel = t('tutorialLooksGoodButton');
    continueDisabled = !piece || !!isEncoding || pendingPieceIds.has(piece.id);
  }
  if (step === 'trace-hand-pen') {
    target = patternTool === 'pen' ? patternCanvas : '[data-tutorial-panel="pattern"] [data-tool-id="pen"]';
    continueLabel = t('tutorialContinue');
  }
  if (step === 'vector-curve-edge') {
    if (patternTool !== 'select') target = '[data-tutorial-panel="pattern"] [data-tool-id="select"]';
    continueLabel = piece?.curvePoints?.length ? t('tutorialContinue') : t('tutorialSkipCurve');
  }
  if (step === 'lamp-edit-profile') {
    customBody = t('tutorialLampEditHelp');
  }
  if (step === 'lamp-preview-3d') continueLabel = t('tutorialCompleteStepButton');
  if (step === 'fab-solder-thickness') {
    target = '[data-tutorial-target="solder-slider"], [data-tutorial-target="solder-settings"]';
    continueLabel = t('tutorialContinue');
    continueDisabled = solderStart === null || Math.abs((project.solderWidthMM ?? 4.5) - solderStart) < 0.01;
  }
  if (step === 'fab-smart-pack') {
    target = '[data-tutorial-target="start-packing"], [data-tutorial-target="smart-pack-button"]';
  }
  if (step === 'fab-print-layout') {
    continueLabel = t('tutorialCompleteStepButton');
  }
  if (selectTrackedPiece) {
    target = patternCanvas;
    customTitle = t('tutorialSelectPieceTitle');
    customBody = t('tutorialSelectPieceBody');
    continueLabel = t('tutorialSelectPieceAction');
    continueDisabled = false;
  }
  const onContinue = () => {
    if (selectTrackedPiece) {
      onSelectPiece(piece.id);
      return;
    }
    onExitRefine();
    if (step === 'trace-hand-pen' && piece) {
      onSelectPiece(piece.id);
    }
    onAdvance();
  };
  const loading = step === 'cut-first-piece' && !!isEncoding && !dismissedLoading;

  return (
    <>
      <TutorialBar step={step} onStart={onStartTour} onSkip={onSkip}
        onComplete={onComplete} customTitle={customTitle} customBody={customBody}
        activeTrackId={activeTrackId} onContinue={continueLabel ? onContinue : undefined}
        continueLabel={continueLabel} continueDisabled={continueDisabled} />
      {target && !loading && <SpotlightPulse key={`${step}:${target}`} selector={target} />}
      {loading && (
        <div className="move-confirm-backdrop" style={{ zIndex: 3000 }}>
          <div className="move-confirm-dialog" role="dialog" aria-modal="true">
            <p className="move-confirm-title">{t('tutorialModelLoadingTitle', 'Preparing the tracing tools')}</p>
            <p className="move-confirm-body">{t('tutorialModelLoadingBody', 'The AI model runs in your browser. The first download can take a few minutes. You can close this message and wait for the Cut tool to become available.')}</p>
            {downloadProgress != null && <p>{Math.round(downloadProgress * 100)}%</p>}
            <button className="btn-primary" onClick={() => setDismissedLoading(true)}>{t('tutorialModelLoadingOk', 'Got it')}</button>
          </div>
        </div>
      )}
      {imageStatus === 'failed' && step !== 'welcome' && step !== 'done' && (
        <div className="tutorial-image-error" role="alert">{t('tutorialImageFailed')}</div>
      )}
    </>
  );
}
