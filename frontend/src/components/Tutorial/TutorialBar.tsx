import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StepId, ANCHORED_STEPS, TrackId, TRACK_STEPS } from './types';
import { IconSpark, IconSquare, IconLamp, IconRuler } from '../icons';

interface TutorialBarProps {
  step: StepId;
  onStart: (trackId?: TrackId) => void;
  onSkip: () => void;
  onComplete: () => void;
  customTitle?: string;
  customBody?: string;
  activeTrackId?: TrackId | null;
}

export function TutorialBar({ step, onStart, onSkip, onComplete, customTitle, customBody, activeTrackId }: TutorialBarProps) {
  const { t } = useTranslation();
  const [selectedTrack, setSelectedTrack] = useState<TrackId>('ai-tracing');

  if (step === 'welcome') {
    return (
      <div className="tutorial-modal-overlay" role="dialog" aria-modal="true">
        <div className="tutorial-modal-card tutorial-modal-card--welcome-grid">
          <div className="tutorial-modal-eyebrow">{t('tutorialEyebrow')}</div>
          <h2 className="tutorial-modal-title">{t('tutorialWelcomeTitle')}</h2>
          <p className="tutorial-modal-body">{t('tutorialWelcomeSubtitle')}</p>

          <div className="tutorial-track-grid">
            <button
              type="button"
              className={`tutorial-track-card ${selectedTrack === 'ai-tracing' ? 'active' : ''}`}
              onClick={() => setSelectedTrack('ai-tracing')}
            >
              <div className="tutorial-track-icon"><IconSpark size={24} /></div>
              <h3 className="tutorial-track-card-title">{t('tutorialTrackAiTracingTitle')}</h3>
              <p className="tutorial-track-card-desc">{t('tutorialTrackAiTracingDesc')}</p>
            </button>
            <button
              type="button"
              className={`tutorial-track-card ${selectedTrack === 'vector-drawing' ? 'active' : ''}`}
              onClick={() => setSelectedTrack('vector-drawing')}
            >
              <div className="tutorial-track-icon"><IconSquare size={24} /></div>
              <h3 className="tutorial-track-card-title">{t('tutorialTrackVectorDrawingTitle')}</h3>
              <p className="tutorial-track-card-desc">{t('tutorialTrackVectorDrawingDesc')}</p>
            </button>
            <button
              type="button"
              className={`tutorial-track-card ${selectedTrack === 'lamp-creator' ? 'active' : ''}`}
              onClick={() => setSelectedTrack('lamp-creator')}
            >
              <div className="tutorial-track-icon"><IconLamp size={24} /></div>
              <h3 className="tutorial-track-card-title">{t('tutorialTrackLampCreatorTitle')}</h3>
              <p className="tutorial-track-card-desc">{t('tutorialTrackLampCreatorDesc')}</p>
            </button>
            <button
              type="button"
              className={`tutorial-track-card ${selectedTrack === 'fabrication' ? 'active' : ''}`}
              onClick={() => setSelectedTrack('fabrication')}
            >
              <div className="tutorial-track-icon"><IconRuler size={24} /></div>
              <h3 className="tutorial-track-card-title">{t('tutorialTrackFabricationTitle')}</h3>
              <p className="tutorial-track-card-desc">{t('tutorialTrackFabricationDesc')}</p>
            </button>
          </div>

          <div className="tutorial-modal-actions" style={{ marginTop: '24px' }}>
            <button className="btn-primary" onClick={() => onStart(selectedTrack)}>
              {t('tutorialStartButton')}
            </button>
            <button className="btn-ghost" onClick={onSkip}>
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

  return (
    <div className="tutorial-bar" role="complementary">
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
          {t(`tutorialStep${step}Eyebrow` as any, t(`tutorialStep${currentStepIndex}Eyebrow` as any))}
        </div>
      </div>

      <div className="tutorial-bar-center">
        <span className="tutorial-bar-instruction-title">
          {customTitle || t(`tutorialStep${step}Title` as any, t(`tutorialStep${currentStepIndex}Title` as any))}:
        </span>{' '}
        <span className="tutorial-bar-instruction-body">
          {customBody || t(`tutorialStep${step}Body` as any, t(`tutorialStep${currentStepIndex}Body` as any))}
        </span>
      </div>

      <div className="tutorial-bar-right">
        <button className="btn-ghost btn-sm" onClick={onSkip}>
          {t('tutorialSkipButton')}
        </button>
      </div>
    </div>
  );
}
