import { useEffect, useRef } from 'react';
import type { Project } from '../../types';
import { TutorialBar } from './TutorialBar';
import { SpotlightPulse } from './SpotlightPulse';
import { STEPS, ANCHORED_STEPS } from './types';
import type { StepId } from './types';
import type { ToolId } from '../Toolbar';

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
  onAdvance: () => void;
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
  onAdvance,
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

  // Reset transitional refs when stepping out of a step.
  useEffect(() => {
    if (step !== 'assign-glass') initialSheetRef.current = null;
    if (step !== 'position-texture') positionStartRef.current = null;
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

  // Step 3 → 4: a piece exists. Track it.
  useEffect(() => {
    if (step !== 'cut-piece') return;
    if (project.pieces.length > 0) {
      const first = project.pieces[0];
      onSetTrackedPiece(first.id);
      onSelectPiece(first.id);
      onAdvance();
    }
  }, [step, project.pieces, onSetTrackedPiece, onSelectPiece, onAdvance]);

  // Step 4 → 5: tracked piece's glassSheetId changed.
  useEffect(() => {
    if (step !== 'assign-glass') return;
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece) return;
    if (initialSheetRef.current === null) {
      initialSheetRef.current = piece.glassSheetId;
      return;
    }
    if (piece.glassSheetId !== initialSheetRef.current) {
      positionStartRef.current = { ...piece.transform };
      onAdvance();
    }
  }, [step, project.pieces, pieceId, onAdvance]);

  // Step 5 → 6: tracked piece's transform changed from its post-assignment snapshot.
  useEffect(() => {
    if (step !== 'position-texture') return;
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
    if (dist > 40 || rotDiff > 0.15 || scaleDiff > 0.1) {
      onAdvance();
    }
  }, [step, project.pieces, pieceId, onAdvance]);

  if (step === null) return null;

  const activeConfig = ANCHORED_STEPS.includes(step) ? STEPS[step] : null;

  return (
    <>
      <TutorialBar
        step={step}
        onStart={onStartTour}
        onSkip={onSkip}
        onComplete={onComplete}
      />
      {activeConfig?.spotlightTarget && (
        <SpotlightPulse selector={activeConfig.spotlightTarget} />
      )}
    </>
  );
}
