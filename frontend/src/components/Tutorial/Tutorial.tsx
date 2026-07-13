import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import useImage from 'use-image';
import type { Project } from '../../types';
import { TutorialBar } from './TutorialBar';
import { SpotlightPulse } from './SpotlightPulse';
import { STEPS, ANCHORED_STEPS, TUTORIAL_GROUND_TRUTH_POLYGONS, GT_PIECE_1, GT_PIECE_3, TrackId } from './types';
import type { AnchoredStepId, StepId } from './types';
import type { ToolId } from '../Toolbar';
import { computeBleedRatio, findMatchedGroundTruth } from '../../utils/geometry';

interface Props {
  /** Current step (null = inactive). */
  step: StepId | null;
  activeTrackId: TrackId | null;
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
  isLampProfileOpen?: boolean;
  isSymmetryEnabled?: boolean;
  isPacking?: boolean;
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
  isPacking = false,
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
  const initialSolderWidthRef = useRef<number | null>(null);
  const debounceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [hasSeenLoadingDialog, setHasSeenLoadingDialog] = useState(false);
  const [, patternImgStatus] = useImage(project.patternImageUrl || '');
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
    if (step !== 'fab-solder-thickness') {
      initialSolderWidthRef.current = null;
    }
  }, [step]);

  // Track initial solder width
  useEffect(() => {
    if (step === 'fab-solder-thickness' && initialSolderWidthRef.current === null) {
      initialSolderWidthRef.current = project.solderWidthMM ?? 4.5;
    }
  }, [step, project.solderWidthMM]);

  // AI-Tracing Step 1: Calibrate pattern
  useEffect(() => {
    if (step !== 'calibrate-pattern') return;
    if (project.patternScale && project.patternScale.pxPerUnit > 0 && patternTool !== 'measure') {
      onAdvance();
    }
  }, [step, project.patternScale, patternTool, onAdvance]);

  // AI-Tracing Step 2: Calibrate sheet
  useEffect(() => {
    if (step !== 'calibrate-sheet') return;
    const sheet = project.sheets.find(s => s.id === activeSheetId);
    if (sheet?.scale && sheet.scale.pxPerUnit > 0 && sheetTool !== 'measure') {
      if (pieceId && !selectedPieceIds.includes(pieceId)) onSelectPiece(pieceId);
      onAdvance();
    }
  }, [step, project.sheets, activeSheetId, pieceId, selectedPieceIds, sheetTool, onSelectPiece, onAdvance]);

  // AI-Tracing Step 3: Cut first piece
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

  // AI-Tracing Step 4: Refine first piece
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

  // AI-Tracing Step 5: Assign first glass
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
      onAdvance(); // Goes to 'position-first-texture'
    }
  }, [step, project.pieces, pieceId, onAdvance]);

  // AI-Tracing Step 6: Position texture
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
        onAdvance(); // Goes to 'done'
      }, 2000);
    }
  }, [step, project.pieces, pieceId, onAdvance]);

  // AI-Tracing Step 7: Cut second piece (leaf)
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

  // AI-Tracing Step 8: Refine second piece
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

  // AI-Tracing Step 9: Cut remaining pieces
  useEffect(() => {
    if (step !== 'cut-remaining-pieces') return;
    if (project.pieces.length > 0) {
      const badPiece = project.pieces.find(p => {
        const matchedGt = findMatchedGroundTruth(p.polygon, TUTORIAL_GROUND_TRUTH_POLYGONS);
        if (!matchedGt) return true;
        const bleed = computeBleedRatio(p.polygon, matchedGt);
        return bleed > 0.05;
      });

      if (badPiece) {
        onSetTrackedPiece(badPiece.id);
        onSelectPiece(badPiece.id);
        onSetStep('refine-remaining-pieces');
      } else if (project.pieces.length >= 4) {
        onAdvance();
      }
    }
  }, [step, project.pieces, onSetTrackedPiece, onSelectPiece, onSetStep, onAdvance]);

  // AI-Tracing Step 10: Refine remaining pieces
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
        isTrackedPieceClean = false;
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
        onAdvance();
      } else {
        onSetStep('cut-remaining-pieces');
      }
    }
  }, [step, project.pieces, pieceId, onSetTrackedPiece, onSelectPiece, onSetStep, onAdvance]);

  // Vector CAD Step 1: Blank canvas intro
  useEffect(() => {
    if (step !== 'vector-blank-canvas') return;
    if (patternTool === 'pen') {
      onAdvance();
    }
  }, [step, patternTool, onAdvance]);

  // Vector CAD Step 2: Draw pen shape
  useEffect(() => {
    if (step !== 'vector-draw-shape') return;
    if (project.pieces.length > 0) {
      const piece = project.pieces[project.pieces.length - 1];
      onSetTrackedPiece(piece.id);
      onSelectPiece(piece.id);
      onAdvance();
    }
  }, [step, project.pieces, onSetTrackedPiece, onSelectPiece, onAdvance]);

  // Vector CAD Step 3: Snap angles
  useEffect(() => {
    if (step !== 'vector-snap-angles') return;
    if (patternTool === 'select') {
      onAdvance();
    }
  }, [step, patternTool, onAdvance]);

  // Vector CAD Step 4: Curve edge
  useEffect(() => {
    if (step !== 'vector-curve-edge') return;
    const piece = project.pieces.find(p => p.id === pieceId);
    if (piece?.curvePoints && piece.curvePoints.length > 0) {
      onAdvance(); // Goes to 'vector-assign-glass'
    }
  }, [step, project.pieces, pieceId, onAdvance]);

  // Vector CAD Step 5: Assign glass
  useEffect(() => {
    if (step !== 'vector-assign-glass') return;
    const piece = project.pieces.find(p => p.id === pieceId);
    if (piece && piece.glassSheetId && piece.glassSheetId !== 'default-sheet-1') {
      onAdvance(); // Goes to 'vector-position-texture'
    }
  }, [step, project.pieces, pieceId, onAdvance]);

  // Vector CAD Step 6: Position texture
  const vectorPositionStartRef = useRef<{ x: number; y: number; rotation: number; scale: number } | null>(null);
  useEffect(() => {
    if (step !== 'vector-position-texture') {
      vectorPositionStartRef.current = null;
      return;
    }
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece) return;
    if (vectorPositionStartRef.current === null) {
      vectorPositionStartRef.current = { ...piece.transform };
      return;
    }
    const start = vectorPositionStartRef.current;
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
        onAdvance(); // Goes to 'done'
      }, 2000);
    }
  }, [step, project.pieces, pieceId, onAdvance]);

  // Lamp Creator Step 1: Profile dialog intro
  useEffect(() => {
    if (step !== 'lamp-profile-intro') return;
    if (isLampProfileOpen) {
      onAdvance();
    }
  }, [step, isLampProfileOpen, onAdvance]);

  // Lamp Creator Step 2: Edit profile points
  useEffect(() => {
    if (step !== 'lamp-edit-profile') return;
    if (!isLampProfileOpen) {
      onAdvance();
    }
  }, [step, isLampProfileOpen, onAdvance]);

  // Lamp Creator Step 3: Choose the Pen tool for one facet piece.
  useEffect(() => {
    if (step !== 'lamp-choose-pen') return;
    if (patternTool === 'pen') {
      onAdvance();
    }
  }, [step, patternTool, onAdvance]);

  // Lamp Creator Step 4: Draw one piece on the active facet.
  useEffect(() => {
    if (step !== 'lamp-draw-facet') return;
    if (project.pieces.length > 0) {
      onAdvance();
    }
  }, [step, project.pieces, onAdvance]);

  // Lamp Creator Step 5: Symmetrical pieces.
  useEffect(() => {
    if (step !== 'lamp-symmetry') return;
    if (isSymmetryEnabled) {
      onAdvance();
    }
  }, [step, isSymmetryEnabled, onAdvance]);

  // Lamp Creator Step 6: Preview 3D lamp
  // User completes it manually via "Complete" button

  // Fabrication Step 1: Solder Settings
  useEffect(() => {
    if (step !== 'fab-solder-thickness') return;
    if (initialSolderWidthRef.current !== null && project.solderWidthMM !== undefined) {
      if (Math.abs(project.solderWidthMM - initialSolderWidthRef.current) > 0.1) {
        onAdvance();
      }
    }
  }, [step, project.solderWidthMM, onAdvance]);

  // Fabrication Step 2: Smart Pack
  const wasPackingRef = useRef<boolean>(false);
  useEffect(() => {
    if (step !== 'fab-smart-pack') return;
    if (isPacking) {
      wasPackingRef.current = true;
    } else if (wasPackingRef.current && !isPacking) {
      wasPackingRef.current = false;
      onAdvance();
    }
  }, [step, isPacking, onAdvance]);

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
  const isPatternLoading = !!step && !!project.patternImageUrl && patternImgStatus === 'loading';

  const percent = downloadProgress != null ? Math.round(downloadProgress * 100) : null;
  const etaText = etaSeconds != null ? (etaSeconds > 60 ? `~${Math.ceil(etaSeconds/60)}m` : `${etaSeconds}s`) : '...';

  return (
    <>
      <TutorialBar
        step={step}
        onStart={onStartTour}
        onSkip={onSkip}
        onAdvance={onAdvance}
        onComplete={onComplete}
        customTitle={customTitle}
        customBody={customBody}
        activeTrackId={activeTrackId}
      />
      {currentSpotlightTarget && !showLoadingDialog && (
        <SpotlightPulse
          selector={currentSpotlightTarget}
          withBackdrop={
            currentSpotlightTarget !== '.canvas-well' &&
            ![
              'cut-remaining-pieces',
              'refine-remaining-pieces',
              'fab-smart-pack',
              'fab-solder-thickness',
              'fab-print-layout',
            ].includes(step)
          }
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
      {isPatternLoading && (
        <div className="move-confirm-backdrop" style={{ zIndex: 3000 }}>
          <div className="move-confirm-dialog" style={{ textAlign: 'center', padding: '30px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <div className="spinner-tiny" style={{ width: 32, height: 32, marginBottom: 16 }} />
            <p className="move-confirm-title" style={{ marginBottom: 8 }}>
              {t('loadingImageTitle')}
            </p>
            <p className="move-confirm-body" style={{ margin: 0 }}>
              {t('loadingImageBody')}
            </p>
          </div>
        </div>
      )}
    </>
  );
}
