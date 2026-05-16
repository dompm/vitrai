import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { Project } from '../../types';
import { CoachMark } from './CoachMark';
import { STEPS } from './types';
import type { StepId } from './types';

const ANCHORED_STEPS: StepId[] = ['calibrate-pattern', 'cut-piece', 'calibrate-sheet', 'assign-glass', 'position-texture'];

interface Props {
  /** Current step (null = inactive). */
  step: StepId | null;
  /** Tracked piece ID, set after the user cuts the first piece in step 2. */
  pieceId: string | null;
  project: Project;
  selectedPieceIds: string[];
  activeSheetId: string;
  onAdvance: () => void;
  onSetTrackedPiece: (id: string) => void;
  onSelectPiece: (id: string) => void;
  onStartTour: () => void;
  onSkip: () => void;
  onComplete: () => void;
}

/**
 * Watches the project store and advances tutorial steps when the user performs
 * the real action. Renders the welcome modal and step coach-marks.
 */
export function Tutorial({
  step, pieceId, project, selectedPieceIds, activeSheetId,
  onAdvance, onSetTrackedPiece, onSelectPiece, onStartTour, onSkip, onComplete,
}: Props) {
  const { t } = useTranslation();

  // Snapshot of the piece transform at the start of step 5, to detect "moved".
  const positionStartRef = useRef<{ x: number; y: number; rotation: number; scale: number } | null>(null);
  // Initial glass sheet at the start of step 4, to detect "changed".
  const initialSheetRef = useRef<string | null>(null);

  // Reset transitional refs when stepping out of a step.
  useEffect(() => {
    if (step !== 'assign-glass') initialSheetRef.current = null;
    if (step !== 'position-texture') positionStartRef.current = null;
  }, [step]);

  // Step 1 → 2: pattern scale set.
  useEffect(() => {
    if (step !== 'calibrate-pattern') return;
    if (project.patternScale && project.patternScale.pxPerUnit > 0) onAdvance();
  }, [step, project.patternScale, onAdvance]);

  // Step 2 → 3: a piece exists. Track it.
  useEffect(() => {
    if (step !== 'cut-piece') return;
    if (project.pieces.length > 0) {
      const first = project.pieces[0];
      onSetTrackedPiece(first.id);
      onSelectPiece(first.id);
      onAdvance();
    }
  }, [step, project.pieces, onSetTrackedPiece, onSelectPiece, onAdvance]);

  // Step 3 → 4: active sheet has a scale.
  useEffect(() => {
    if (step !== 'calibrate-sheet') return;
    const sheet = project.sheets.find(s => s.id === activeSheetId);
    if (sheet?.scale && sheet.scale.pxPerUnit > 0) {
      if (pieceId && !selectedPieceIds.includes(pieceId)) onSelectPiece(pieceId);
      onAdvance();
    }
  }, [step, project.sheets, activeSheetId, pieceId, selectedPieceIds, onSelectPiece, onAdvance]);

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
    if (
      Math.abs(x - start.x) > 0.5 ||
      Math.abs(y - start.y) > 0.5 ||
      Math.abs(rotation - start.rotation) > 1e-4 ||
      Math.abs(scale - start.scale) > 1e-4
    ) {
      onAdvance();
    }
  }, [step, project.pieces, pieceId, onAdvance]);

  // ---- Render --------------------------------------------------------------

  if (step === null) return null;

  if (step === 'welcome') {
    return <WelcomeModal onStart={onStartTour} onSkip={onSkip} />;
  }

  if (step === 'done') {
    return (
      <CoachMark
        target={null}
        progress={null}
        eyebrow={t('tutorialEyebrow')}
        title={t('tutorialDoneTitle')}
        body={t('tutorialDoneBody')}
        primary={{ label: t('tutorialFinishButton'), onClick: onComplete }}
        onSkip={onComplete}
      />
    );
  }

  if (!ANCHORED_STEPS.includes(step)) return null;
  const cfg = STEPS[step];
  const stepIndex = ANCHORED_STEPS.indexOf(step) + 1;

  return (
    <CoachMark
      key={step}
      target={cfg.target ?? null}
      side={cfg.side}
      progress={{ current: stepIndex, total: ANCHORED_STEPS.length }}
      eyebrow={t(`tutorialStep${stepIndex}Eyebrow`)}
      title={t(`tutorialStep${stepIndex}Title`)}
      body={t(`tutorialStep${stepIndex}Body`)}
      onSkip={onSkip}
    />
  );
}

function WelcomeModal({ onStart, onSkip }: { onStart: () => void; onSkip: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="coach-mark coach-mark--centered" role="dialog" aria-modal="true">
      <div className="coach-mark-card coach-mark-card--welcome">
        <div className="coach-mark-eyebrow">{t('tutorialEyebrow')}</div>
        <h2 className="coach-mark-title coach-mark-title--lg">{t('tutorialWelcomeTitle')}</h2>
        <p className="coach-mark-body">{t('tutorialWelcomeSubtitle')}</p>
        <div className="coach-mark-actions">
          <button className="btn-primary" onClick={onStart}>{t('tutorialStartButton')}</button>
          <button className="coach-mark-skip" onClick={onSkip}>{t('tutorialSkipButton')}</button>
        </div>
      </div>
    </div>
  );
}
