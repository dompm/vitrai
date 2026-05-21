import { useTranslation } from 'react-i18next';
import { StepId, ANCHORED_STEPS } from './types';

interface TutorialBarProps {
  step: StepId;
  onStart: () => void;
  onSkip: () => void;
  onComplete: () => void;
}

export function TutorialBar({ step, onStart, onSkip, onComplete }: TutorialBarProps) {
  const { t } = useTranslation();

  if (step === 'welcome') {
    return (
      <div className="tutorial-modal-overlay" role="dialog" aria-modal="true">
        <div className="tutorial-modal-card tutorial-modal-card--welcome">
          <div className="tutorial-modal-eyebrow">{t('tutorialEyebrow')}</div>
          <h2 className="tutorial-modal-title">{t('tutorialWelcomeTitle')}</h2>
          <p className="tutorial-modal-body">{t('tutorialWelcomeSubtitle')}</p>
          <div className="tutorial-modal-actions">
            <button className="btn-primary" onClick={onStart}>
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
          <div className="tutorial-modal-actions">
            <button className="btn-primary" onClick={onComplete}>
              {t('tutorialFinishButton')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!ANCHORED_STEPS.includes(step)) return null;

  const currentStepIndex = ANCHORED_STEPS.indexOf(step) + 1;
  const totalSteps = ANCHORED_STEPS.length;

  return (
    <div className="tutorial-bar" role="complementary">
      <div className="tutorial-bar-left">
        <div className="tutorial-progress-dots" aria-label={`Step ${currentStepIndex} of ${totalSteps}`}>
          {ANCHORED_STEPS.map((_, i) => (
            <span
              key={i}
              className={`tutorial-progress-dot${i < currentStepIndex ? ' is-active' : ''}`}
            />
          ))}
        </div>
        <div className="tutorial-step-label">
          {t(`tutorialStep${currentStepIndex}Eyebrow`)}
        </div>
      </div>

      <div className="tutorial-bar-center">
        <span className="tutorial-bar-instruction-title">
          {t(`tutorialStep${currentStepIndex}Title`)}:
        </span>{' '}
        <span className="tutorial-bar-instruction-body">
          {t(`tutorialStep${currentStepIndex}Body`)}
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
