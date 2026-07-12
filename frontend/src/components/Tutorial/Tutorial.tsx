import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Project } from '../../types';
import { TutorialBar } from './TutorialBar';
import { SpotlightPulse } from './SpotlightPulse';
import { STEPS, ANCHORED_STEPS, TUTORIAL_GROUND_TRUTH_POLYGONS, GT_PIECE_1, GT_PIECE_3 } from './types';
import type { AnchoredStepId, StepId } from './types';
import type { ToolId } from '../Toolbar';
import { computeBleedRatio, findMatchedGroundTruth } from '../../utils/geometry';

interface Props {
  /** Current step (null = inactive). */
  step: StepId | null;
  /** Tracked piece ID, set after the user cuts the first piece in step 2. */
  pieceId: string | null;
  project: Project;
  selectedPieceIds: string[];
  activeSheetId: string;
  patternTool: ToolId;
  sheetTool: ToolId;
  patternRefineMode: 'add' | 'remove' | null;
  isEncoding?: boolean;
  downloadProgress?: number | null;
  onAdvance: () => void;
  onSetStep: (step: StepId | null) => void;
  onSetTrackedPiece: (id: string) => void;
  onSelectPiece: (id: string | null, multi?: boolean) => void;
  onStartTour: () => void;
  onSkip: () => void;
  onComplete: () => void;
}

export function Tutorial({
  step,
  pieceId,
  project,
  selectedPieceIds,
  activeSheetId,
  patternTool,
  sheetTool,
  patternRefineMode,
  isEncoding,
  downloadProgress,
  onAdvance,
  onSetStep,
  onSetTrackedPiece,
  onSelectPiece,
  onStartTour,
  onSkip,
  onComplete,
}: Props) {
  // Snapshot of the piece transform at the start of step 5, to detect "moved".
  const positionStartRef = useRef<{ x: number; y: number; rotation: number; scale: number } | null>(null);
  // Initial glass sheet at the start of step 4, to detect "changed".
  const initialSheetRef = useRef<string | null>(null);
  const debounceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [hasSeenLoadingDialog, setHasSeenLoadingDialog] = useState(false);
  const [etaSeconds, setEtaSeconds] = useState<number | null>(null);
  const progressHistoryRef = useRef<{ time: number; fraction: number }[]>([]);

  useEffect(() => {
    if (downloadProgress == null || downloadProgress === 0) {
      progressHistoryRef.current = [];
      setEtaSeconds(null);
      return;
    }
    
    const now = Date.now();
    const history = progressHistoryRef.current;
    history.push({ time: now, fraction: downloadProgress });
    
    // Keep only the last 3 seconds of history for a dynamic but stable ETA
    while (history.length > 0 && now - history[0].time > 3000) {
      history.shift();
    }

    if (history.length > 1) {
      const first = history[0];
      const last = history[history.length - 1];
      const timeDiff = last.time - first.time;
      const fracDiff = last.fraction - first.fraction;
      
      // Compute ETA if we have at least 500ms of history and some progress
      if (timeDiff > 500 && fracDiff > 0.001) {
        const remainingFrac = 1 - last.fraction;
        const timePerFrac = timeDiff / fracDiff;
        setEtaSeconds(Math.ceil((remainingFrac * timePerFrac) / 1000));
      }
    }
  }, [downloadProgress]);

  // Reset transitional refs when stepping out of a step.
  useEffect(() => {
    if (step !== 'assign-first-glass') initialSheetRef.current = null;
    if (step !== 'position-first-texture') {
      positionStartRef.current = null;
      if (debounceTimeoutRef.current) {
        clearTimeout(debounceTimeoutRef.current);
        debounceTimeoutRef.current = null;
      }
    }
  }, [step]);

  // Step 1 → 2: pattern scale set & scale tool closed.
  useEffect(() => {
    if (step !== 'calibrate-pattern') return;
    if (project.patternScale && project.patternScale.pxPerUnit > 0 && patternTool !== 'measure') {
      onAdvance();
    }
  }, [step, project.patternScale, patternTool, onAdvance]);

  // Step 2 → 3: active sheet has a scale & scale tool closed.
  useEffect(() => {
    if (step !== 'calibrate-sheet') return;
    const sheet = project.sheets.find(s => s.id === activeSheetId);
    if (sheet?.scale && sheet.scale.pxPerUnit > 0 && sheetTool !== 'measure') {
      if (pieceId && !selectedPieceIds.includes(pieceId)) onSelectPiece(pieceId);
      onAdvance();
    }
  }, [step, project.sheets, activeSheetId, pieceId, selectedPieceIds, sheetTool, onSelectPiece, onAdvance]);

  // Step 3 (cut-first-piece) → 4 (refine-first-piece) or 5 (assign-first-glass)
  // Triggered when a piece is created.
  useEffect(() => {
    if (step !== 'cut-first-piece') return;
    if (project.pieces.length > 0) {
      const piece = project.pieces[0];
      onSetTrackedPiece(piece.id);
      onSelectPiece(piece.id);

      const matchedGt = findMatchedGroundTruth(piece.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
      const isOrange = matchedGt === GT_PIECE_1;
      const bleed = isOrange ? computeBleedRatio(piece.polygon, GT_PIECE_1) : 1.0;
      
      if (!isOrange || bleed > 0.05) {
        onSetStep('refine-first-piece');
      } else {
        onSetStep('assign-first-glass');
      }
    }
  }, [step, project.pieces, onSetTrackedPiece, onSelectPiece, onSetStep]);

  // Step 4 (refine-first-piece) → 3 (cut-first-piece) or 5 (assign-first-glass)
  useEffect(() => {
    if (step !== 'refine-first-piece') return;
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece) {
      onSetStep('cut-first-piece');
      return;
    }

    const matchedGt = findMatchedGroundTruth(piece.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
    const isOrange = matchedGt === GT_PIECE_1;
    const bleed = isOrange ? computeBleedRatio(piece.polygon, GT_PIECE_1) : 1.0;
    const isClean = isOrange && bleed <= 0.05;

    if (isClean && patternRefineMode === null) {
      onSetStep('assign-first-glass');
    }
  }, [step, project.pieces, pieceId, patternRefineMode, onSetStep]);

  // Step 5 (assign-first-glass) → 6 (position-first-texture)
  useEffect(() => {
    if (step !== 'assign-first-glass') return;
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece) return;
    if (initialSheetRef.current === null) {
      initialSheetRef.current = piece.glassSheetId;
      return;
    }
    if (piece.glassSheetId !== initialSheetRef.current) {
      positionStartRef.current = { ...piece.transform };
      onSetStep('position-first-texture');
    }
  }, [step, project.pieces, pieceId, onSetStep]);

  // Step 6 (position-first-texture) → 7 (cut-second-piece)
  useEffect(() => {
    if (step !== 'position-first-texture') return;
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece) return;
    if (positionStartRef.current === null) {
      positionStartRef.current = { ...piece.transform };
      return;
    }
    const start = positionStartRef.current;
    const { x, y, rotation, scale } = piece.transform;
    const dist = Math.hypot(x - start.x, y - start.y);
    const rotDiff = Math.abs(rotation - start.rotation);
    const scaleDiff = Math.abs(scale - start.scale);

    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
      debounceTimeoutRef.current = null;
    }

    if (dist > 40 || rotDiff > 0.15 || scaleDiff > 0.1) {
      debounceTimeoutRef.current = setTimeout(() => {
        onSetStep('cut-second-piece');
      }, 2000);
    }
  }, [step, project.pieces, pieceId, onSetStep]);

  // Step 7 (cut-second-piece) → 8 (refine-second-piece) or 9 (cut-remaining-pieces)
  useEffect(() => {
    if (step !== 'cut-second-piece') return;
    if (project.pieces.length > 1) {
      const secondPiece = project.pieces.find(p => p.id !== pieceId);
      if (secondPiece) {
        onSetTrackedPiece(secondPiece.id);
        onSelectPiece(secondPiece.id);

        const matchedGt = findMatchedGroundTruth(secondPiece.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
        const isLeaf3 = matchedGt === GT_PIECE_3;
        const bleed = isLeaf3 ? computeBleedRatio(secondPiece.polygon, GT_PIECE_3) : 1.0;

        if (!isLeaf3 || bleed > 0.05) {
          onSetStep('refine-second-piece');
        } else {
          onSetStep('cut-remaining-pieces');
        }
      }
    }
  }, [step, project.pieces, pieceId, onSetTrackedPiece, onSelectPiece, onSetStep]);

  // Step 8 (refine-second-piece) → 7 (cut-second-piece) or 9 (cut-remaining-pieces)
  useEffect(() => {
    if (step !== 'refine-second-piece') return;
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece) {
      onSetStep('cut-second-piece');
      return;
    }

    const matchedGt = findMatchedGroundTruth(piece.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
    const isLeaf3 = matchedGt === GT_PIECE_3;
    const bleed = isLeaf3 ? computeBleedRatio(piece.polygon, GT_PIECE_3) : 1.0;
    const isClean = isLeaf3 && bleed <= 0.05;

    if (isClean && patternRefineMode === null) {
      onSetStep('cut-remaining-pieces');
    }
  }, [step, project.pieces, pieceId, patternRefineMode, onSetStep]);

  // Step 9 (cut-remaining-pieces) → 10 (refine-remaining-pieces) or done
  useEffect(() => {
    if (step !== 'cut-remaining-pieces') return;
    if (project.pieces.length > 0) {
      // Find if any leaf piece is bad (bleed > 5% or matches nothing)
      const badPiece = project.pieces.find(p => {
        const matchedGt = findMatchedGroundTruth(p.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
        if (!matchedGt) return true; // matches nothing = bad
        const bleed = computeBleedRatio(p.polygon, matchedGt);
        return bleed > 0.05;
      });

      if (badPiece) {
        onSetTrackedPiece(badPiece.id);
        onSelectPiece(badPiece.id);
        onSetStep('refine-remaining-pieces');
      } else if (project.pieces.length >= 4) {
        onAdvance(); // Move to 'done' (next after refine-remaining-pieces)
      }
    }
  }, [step, project.pieces, onSetTrackedPiece, onSelectPiece, onSetStep, onAdvance]);

  // Step 10 (refine-remaining-pieces) → 9 (cut-remaining-pieces) or done
  useEffect(() => {
    if (step !== 'refine-remaining-pieces') return;
    const piece = project.pieces.find(p => p.id === pieceId);

    let isTrackedPieceClean = false;
    if (!piece) {
      isTrackedPieceClean = true;
    } else {
      const matchedGt = findMatchedGroundTruth(piece.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
      if (matchedGt) {
        const bleed = computeBleedRatio(piece.polygon, matchedGt);
        isTrackedPieceClean = bleed <= 0.05;
      } else {
        isTrackedPieceClean = false; // wildly out of place, must delete
      }
    }

    if (isTrackedPieceClean) {
      const otherBad = project.pieces.find(p => {
        const matchedGt = findMatchedGroundTruth(p.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
        if (!matchedGt) return true;
        const bleed = computeBleedRatio(p.polygon, matchedGt);
        return bleed > 0.05;
      });

      if (otherBad) {
        onSetTrackedPiece(otherBad.id);
        onSelectPiece(otherBad.id);
      } else if (project.pieces.length >= 4) {
        onAdvance(); // Move to 'done'
      } else {
        onSetStep('cut-remaining-pieces');
      }
    }
  }, [step, project.pieces, pieceId, onSetTrackedPiece, onSelectPiece, onSetStep, onAdvance]);

  const { t } = useTranslation();

  if (step === null) return null;

  const activeConfig = ANCHORED_STEPS.includes(step) ? STEPS[step as AnchoredStepId] : null;

  // Build dynamic text overrides for refinement steps depending on the tracked piece's state.
  let customTitle: string | undefined = undefined;
  let customBody: string | undefined = undefined;
  let currentSpotlightTarget = activeConfig?.spotlightTarget;

  if (step === 'refine-first-piece' && pieceId) {
    const piece = project.pieces.find(p => p.id === pieceId);
    if (piece) {
      const matchedGt = findMatchedGroundTruth(piece.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
      const isOrange = matchedGt === GT_PIECE_1;
      const bleed = isOrange ? computeBleedRatio(piece.polygon, GT_PIECE_1) : 1.0;
      const isClean = isOrange && bleed <= 0.05;

      if (isClean && patternRefineMode !== null) {
        customTitle = t('tutorialExitRefineTitle');
        customBody = t('tutorialExitRefineBody');
        currentSpotlightTarget = '[data-tutorial-target="piece-refine-remove"]';
      } else if (matchedGt !== GT_PIECE_1) {
        customTitle = t('tutorialStep4TitleOutOfPlace');
        customBody = t('tutorialStep4BodyOutOfPlace');
        currentSpotlightTarget = '[data-tutorial-target="piece-delete"]';
      } else {
        customTitle = t('tutorialStep4Title');
        customBody = t('tutorialStep4Body');
        currentSpotlightTarget = patternRefineMode === null
          ? '[data-tutorial-target="piece-refine-remove"]'
          : undefined;
      }
    }
  } else if (step === 'refine-second-piece' && pieceId) {
    const piece = project.pieces.find(p => p.id === pieceId);
    if (piece) {
      const matchedGt = findMatchedGroundTruth(piece.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
      const isLeaf3 = matchedGt === GT_PIECE_3;
      const bleed = isLeaf3 ? computeBleedRatio(piece.polygon, GT_PIECE_3) : 1.0;
      const isClean = isLeaf3 && bleed <= 0.05;

      if (isClean && patternRefineMode !== null) {
        customTitle = t('tutorialExitRefineTitle');
        customBody = t('tutorialExitRefineBody');
        currentSpotlightTarget = '[data-tutorial-target="piece-refine-remove"]';
      } else if (matchedGt !== GT_PIECE_3) {
        customTitle = t('tutorialStep8TitleOutOfPlace');
        customBody = t('tutorialStep8BodyOutOfPlace');
        currentSpotlightTarget = '[data-tutorial-target="piece-delete"]';
      } else {
        customTitle = t('tutorialStep8Title');
        customBody = t('tutorialStep8Body');
        currentSpotlightTarget = patternRefineMode === null
          ? '[data-tutorial-target="piece-refine-remove"]'
          : undefined;
      }
    }
  } else if (step === 'refine-remaining-pieces' && pieceId) {
    const piece = project.pieces.find(p => p.id === pieceId);
    if (piece) {
      const matchedGt = findMatchedGroundTruth(piece.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
      if (!matchedGt) {
        customTitle = t('tutorialStep10TitleOutOfPlace');
        customBody = t('tutorialStep10BodyOutOfPlace');
        currentSpotlightTarget = '[data-tutorial-target="piece-delete"]';
      } else {
        customTitle = t('tutorialStep10Title');
        customBody = t('tutorialStep10Body');
        currentSpotlightTarget = patternRefineMode === null
          ? '[data-tutorial-target="piece-refine-remove"]'
          : undefined;
      }
    }
  }

  // Remove the spotlight on the tool icons if they are already in the requested mode
  if (step === 'calibrate-pattern' && patternTool === 'measure') {
    currentSpotlightTarget = undefined;
  } else if (step === 'calibrate-sheet' && sheetTool === 'measure') {
    currentSpotlightTarget = undefined;
  } else if (
    (step === 'cut-first-piece' || step === 'cut-second-piece' || step === 'cut-remaining-pieces') &&
    patternTool === 'box'
  ) {
    currentSpotlightTarget = undefined;
  }

  // Show loading dialog if they are asked to cut the first piece but the model is still loading
  const showLoadingDialog = step === 'cut-first-piece' && isEncoding && !hasSeenLoadingDialog;

  const percent = downloadProgress != null ? Math.round(downloadProgress * 100) : null;
  const etaText = etaSeconds != null ? (etaSeconds > 60 ? `~${Math.ceil(etaSeconds/60)}m` : `${etaSeconds}s`) : '...';

  return (
    <>
      <TutorialBar
        step={step}
        onStart={onStartTour}
        onSkip={onSkip}
        onComplete={onComplete}
        customTitle={customTitle}
        customBody={customBody}
      />
      {currentSpotlightTarget && !showLoadingDialog && (
        <SpotlightPulse
          selector={currentSpotlightTarget}
          withBackdrop={!['cut-remaining-pieces', 'refine-remaining-pieces'].includes(step)}
        />
      )}
      {showLoadingDialog && (
        <div className="move-confirm-backdrop" style={{ zIndex: 3000 }}>
          <div className="move-confirm-dialog">
            <p className="move-confirm-title">
              {t('tutorialModelLoadingTitle', 'Downloading AI Model')}
            </p>
            <p className="move-confirm-body">
              {t('tutorialModelLoadingBody', 'The segmentation model is currently downloading to your browser. This may take a few moments depending on your connection, but it only happens the very first time you use the app!')}
            </p>
            {percent != null && (
              <p className="move-confirm-body" style={{ fontWeight: 'bold', marginTop: '1rem' }}>
                Progress: {percent}% (ETA: {etaText})
              </p>
            )}
            <div className="move-confirm-actions" style={{ justifyContent: 'flex-end' }}>
              <button className="btn-primary" onClick={() => setHasSeenLoadingDialog(true)}>
                {t('tutorialModelLoadingOk', 'Got it')}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
