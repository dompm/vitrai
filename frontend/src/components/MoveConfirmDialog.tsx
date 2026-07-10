import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  count: number;
  srcLabel: string;
  destLabel: string;
  onCancel: () => void;
  onConfirm: (dontAskAgain: boolean) => void;
}

export function MoveConfirmDialog({ count, srcLabel, destLabel, onCancel, onConfirm }: Props) {
  const { t } = useTranslation();
  const [dontAsk, setDontAsk] = useState(false);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    confirmRef.current?.focus();
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        // Capture phase + stopPropagation: the Esc that dismisses this dialog
        // must not also reach the panels' window handlers (which would reset
        // tools / discard an in-progress pen polygon — see #94).
        e.preventDefault();
        e.stopPropagation();
        onCancel();
      }
    }
    window.addEventListener('keydown', handleKey, true);
    return () => window.removeEventListener('keydown', handleKey, true);
  }, [onCancel]);

  return (
    <div className="move-confirm-backdrop" onClick={onCancel}>
      <div className="move-confirm-dialog" onClick={e => e.stopPropagation()}>
        <p className="move-confirm-title">
          {t('moveConfirmTitle', { count, src: srcLabel, dest: destLabel })}
        </p>
        <p className="move-confirm-body">
          {t('moveConfirmBody', { src: srcLabel })}
        </p>
        <label className="move-confirm-dontask">
          <input
            type="checkbox"
            checked={dontAsk}
            onChange={e => setDontAsk(e.target.checked)}
          />
          <span>{t('moveConfirmDontAsk')}</span>
        </label>
        <div className="move-confirm-actions">
          <button className="btn-ghost" onClick={onCancel}>
            {t('moveConfirmCancel')}
          </button>
          <button
            ref={confirmRef}
            className="btn-primary"
            onClick={() => onConfirm(dontAsk)}
          >
            {t('moveConfirmConfirm')}
          </button>
        </div>
      </div>
    </div>
  );
}
