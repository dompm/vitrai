import { useTranslation } from 'react-i18next';

interface ViewportControlsProps {
  zoomPercent: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onActualSize: () => void;
}

/** Compact, reusable controls following common design-tool zoom conventions. */
export function ViewportControls({
  zoomPercent,
  onZoomIn,
  onZoomOut,
  onFit,
  onActualSize,
}: ViewportControlsProps) {
  const { t } = useTranslation();

  return (
    <div className="viewport-controls" role="group" aria-label={t('zoomControls')}>
      <button type="button" onClick={onZoomOut} aria-label={t('zoomOut')} title={`${t('zoomOut')} (−)`}>
        −
      </button>
      <button
        type="button"
        className="viewport-zoom-value"
        onClick={onActualSize}
        aria-label={t('zoomActualSize')}
        title={`${t('zoomActualSize')} (Shift+0)`}
      >
        {Math.round(zoomPercent)}%
      </button>
      <button type="button" onClick={onZoomIn} aria-label={t('zoomIn')} title={`${t('zoomIn')} (+)`}>
        +
      </button>
      <span className="viewport-controls-separator" aria-hidden="true" />
      <button type="button" className="viewport-fit-button" onClick={onFit} title={`${t('zoomFit')} (Shift+1)`}>
        {t('zoomFit')}
      </button>
    </div>
  );
}
