import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StepId, ANCHORED_STEPS, TrackId, TRACK_STEPS } from './types';

function TrackArtwork({ track }: { track: TrackId }) {
  switch (track) {
    case 'vector-drawing':
      return (
        <svg width="26" height="26" viewBox="0 0 28 28" fill="none" aria-hidden="true">
          <path d="M14 3L23 14L14 25L5 14Z" fill="#F3D9A4" fillOpacity="0.55" />
          <path d="M14 3L23 14L14 14Z" fill="#8FB39A" fillOpacity="0.45" />
          <path d="M14 3L23 14L14 25L5 14Z" stroke="#2D2620" strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M5 14Q14 10 23 14" stroke="#2D2620" strokeWidth="1.35" />
          <line x1="14" y1="3" x2="14" y2="25" stroke="#2D2620" strokeWidth="1.35" />
          <circle cx="14" cy="12" r="2.1" fill="#FFFDF9" stroke="#B7791F" strokeWidth="1.5" />
        </svg>
      );
    case 'ai-tracing':
      return (
        <svg width="26" height="26" viewBox="0 0 28 28" fill="none" aria-hidden="true">
          <rect x="4" y="5" width="20" height="18" rx="2.5" fill="#F5F1E9" stroke="#2D2620" strokeWidth="1.4" />
          <path d="M4 17L11 11L17 16L24 11V20.5C24 21.88 22.88 23 21.5 23H6.5C5.12 23 4 21.88 4 20.5V17Z" fill="#7FA6BE" fillOpacity="0.48" />
          <path d="M17 16L24 11V23H14L17 16Z" fill="#E6B86A" fillOpacity="0.52" />
          <circle cx="10.5" cy="9.5" r="2.2" fill="#E6B86A" stroke="#2D2620" strokeWidth="1.2" />
          <path d="M4 17L11 11L17 16L24 11" stroke="#2D2620" strokeWidth="1.35" strokeLinejoin="round" />
          <path d="M17 16L14 23" stroke="#2D2620" strokeWidth="1.35" />
        </svg>
      );
    case 'lamp-creator':
      return (
        <svg width="26" height="26" viewBox="0 0 28 28" fill="none" aria-hidden="true">
          <path d="M9 6H19L23.5 17H4.5L9 6Z" fill="#F2CA7E" fillOpacity="0.55" />
          <path d="M11.5 6H16.5L18 17H10L11.5 6Z" fill="#8FB39A" fillOpacity="0.45" />
          <path d="M9 6H19L23.5 17H4.5L9 6Z" stroke="#2D2620" strokeWidth="1.5" strokeLinejoin="round" />
          <path d="M11.5 6L10 17M16.5 6L18 17" stroke="#2D2620" strokeWidth="1.25" />
          <path d="M6.8 11.5H21.2" stroke="#2D2620" strokeWidth="1.2" />
          <path d="M14 17V23M10.5 23H17.5" stroke="#2D2620" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      );
    case 'fabrication':
      return (
        <svg width="26" height="26" viewBox="0 0 28 28" fill="none" aria-hidden="true">
          <rect x="4" y="4" width="20" height="14" rx="2" fill="#F5F1E9" stroke="#2D2620" strokeWidth="1.4" />
          <path d="M6.5 6.5H13V15.5H6.5Z" fill="#E6B86A" fillOpacity="0.55" stroke="#2D2620" strokeWidth="1.2" />
          <path d="M15 6.5H21.5L19 15.5H15Z" fill="#8FB39A" fillOpacity="0.5" stroke="#2D2620" strokeWidth="1.2" />
          <rect x="4" y="20.5" width="20" height="4" rx="1" fill="#FFFDF9" stroke="#2D2620" strokeWidth="1.3" />
          <path d="M8 20.5V22.7M12 20.5V23.3M16 20.5V22.7M20 20.5V23.3" stroke="#B7791F" strokeWidth="1.2" />
        </svg>
      );
  }
}

interface TutorialBarProps {
  step: StepId;
  onStart: (trackId?: TrackId) => void;
  onSkip: () => void;
  onContinue?: () => void;
  continueLabel?: string;
  continueDisabled?: boolean;
  onComplete: () => void;
  customTitle?: string;
  customBody?: string;
  activeTrackId?: TrackId | null;
}

export function TutorialBar({ step, onStart, onSkip, onContinue, continueLabel, continueDisabled, onComplete, customTitle, customBody, activeTrackId }: TutorialBarProps) {
  const { t } = useTranslation();
  const [selectedTrack, setSelectedTrack] = useState<TrackId>('vector-drawing');

  if (step === 'welcome') {
    return (
      <div className="tutorial-modal-overlay" role="dialog" aria-modal="true">
        <div className="tutorial-modal-card tutorial-modal-card--welcome-grid">
          <div className="tutorial-modal-eyebrow">{t('tutorialEyebrow')}</div>
          <h2 className="tutorial-modal-title">{t('tutorialWelcomeTitle')}</h2>
          <p className="tutorial-modal-body">{t('tutorialWelcomeSubtitle')}</p>

          <div className="tutorial-track-grid">
            {([
              { id: 'vector-drawing' as TrackId, titleKey: 'tutorialTrackVectorDrawingTitle', descKey: 'tutorialTrackVectorDrawingDesc' },
              { id: 'ai-tracing' as TrackId, titleKey: 'tutorialTrackAiTracingTitle', descKey: 'tutorialTrackAiTracingDesc' },
              { id: 'lamp-creator' as TrackId, titleKey: 'tutorialTrackLampCreatorTitle', descKey: 'tutorialTrackLampCreatorDesc' },
              { id: 'fabrication' as TrackId, titleKey: 'tutorialTrackFabricationTitle', descKey: 'tutorialTrackFabricationDesc' },
            ]).map(track => {
              const isSelected = selectedTrack === track.id;
              return (
                <button
                  key={track.id}
                  type="button"
                  className={`tutorial-track-card ${isSelected ? 'active' : ''}`}
                  aria-pressed={isSelected}
                  onClick={() => setSelectedTrack(track.id)}
                >
                  <div className="tutorial-track-card-top">
                    <div className="tutorial-track-icon">
                      <TrackArtwork track={track.id} />
                    </div>
                    <h3 className="tutorial-track-card-title">{t(track.titleKey)}</h3>
                  </div>
                  <p className="tutorial-track-card-desc">{t(track.descKey)}</p>
                </button>
              );
            })}
          </div>

          <div className="tutorial-modal-actions tutorial-modal-actions--welcome">
            <button className="btn-primary tutorial-welcome-start" onClick={() => onStart(selectedTrack)}>
              {t('tutorialStartButton')}
            </button>
            <button className="tutorial-welcome-skip" onClick={onSkip}>
              {t('tutorialSkipButton')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (step === 'done') {
    return (
      <div className="tutorial-modal-overlay" role="dialog" aria-modal="true">
        <div className="tutorial-modal-card tutorial-modal-card--done">
          <div className="tutorial-modal-eyebrow">{t('tutorialEyebrow')}</div>
          <h2 className="tutorial-modal-title">{t('tutorialDoneTitle')}</h2>
          <p className="tutorial-modal-body">{t('tutorialDoneBody')}</p>
          <div className="tutorial-modal-actions" style={{ gap: '12px' }}>
            <button className="btn-primary" onClick={() => onStart()}>
              {t('tutorialChooseAnotherTrackButton')}
            </button>
            <button className="btn-ghost" onClick={onComplete}>
              {t('tutorialFinishButton')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const trackSteps = activeTrackId ? TRACK_STEPS[activeTrackId] : null;
  const trackAnchoredSteps = trackSteps ? trackSteps.filter(s => s !== 'welcome' && s !== 'done') : ANCHORED_STEPS;

  if (!trackAnchoredSteps.includes(step)) return null;

  const currentStepIndex = trackAnchoredSteps.indexOf(step) + 1;
  const totalSteps = trackAnchoredSteps.length;
  const text = (part: string) => t(`tutorialStep${step}${part}`);

  return (
    <div className="tutorial-bar" role="complementary" aria-label={t('tutorialEyebrow')} data-tutorial-step={step}>
      <div className="tutorial-bar-left">
        <div className="tutorial-progress-dots" aria-label={`Step ${currentStepIndex} of ${totalSteps}`}>
          {trackAnchoredSteps.map((_, i) => (
            <span
              key={i}
              className={`tutorial-progress-dot${i < currentStepIndex ? ' is-active' : ''}`}
            />
          ))}
        </div>
        <div className="tutorial-step-label">
          {t('tutorialStepCount', { current: currentStepIndex, total: totalSteps })}
        </div>
      </div>

      <div className="tutorial-bar-center">
        <span className="tutorial-bar-instruction-title">
          {customTitle || text('Title')}:
        </span>{' '}
        <span className="tutorial-bar-instruction-body">
          {customBody || text('Body')}
        </span>
      </div>

      <div className="tutorial-bar-right">
        {onContinue && (
          <button className="btn-primary btn-sm" onClick={onContinue} disabled={continueDisabled}>
            {continueLabel}
          </button>
        )}
        <button className="btn-ghost btn-sm" onClick={onSkip}>
          {t('tutorialSkipButton')}
        </button>
      </div>
    </div>
  );
}
