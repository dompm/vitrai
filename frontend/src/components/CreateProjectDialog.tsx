import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Props {
  onCancel: () => void;
  onConfirm: (name: string, type: 'flat' | 'lamp') => void;
  defaultProjectName: string;
}

export function CreateProjectDialog({ onCancel, onConfirm, defaultProjectName }: Props) {
  const { t } = useTranslation();
  const [name, setName] = useState(defaultProjectName);
  const [type, setType] = useState<'flat' | 'lamp'>('flat');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onCancel]);

  function commit() {
    const trimmed = name.trim();
    if (trimmed) onConfirm(trimmed, type);
  }

  return (
    <div className="move-confirm-backdrop" onClick={onCancel}>
      <div
        className="move-confirm-dialog"
        style={{ width: 440, maxWidth: '90%' }}
        onClick={e => e.stopPropagation()}
      >
        <p
          className="move-confirm-title"
          style={{ fontFamily: '"Instrument Serif", Georgia, serif', fontSize: '1.8rem', fontWeight: 400, color: 'var(--text-bright)', marginBottom: 12 }}
        >
          {t('newProjectDialogTitle')}
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, margin: '16px 0' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-soft)' }}>
              {t('newProjectNameLabel')}
            </label>
            <input
              ref={inputRef}
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); commit(); } }}
              style={{
                width: '100%',
                background: 'var(--paper)',
                border: '1px solid var(--hairline-2)',
                borderRadius: 6,
                padding: '8px 12px',
                fontSize: 14,
                color: 'var(--text-bright)',
                outline: 'none',
                fontFamily: 'inherit',
              }}
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-soft)' }}>
              {t('newProjectTypeLabel')}
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <TypeCard
                selected={type === 'flat'}
                onSelect={() => setType('flat')}
                title={t('newProjectFlatTitle')}
                description={t('newProjectFlatDesc')}
              />
              <TypeCard
                selected={type === 'lamp'}
                onSelect={() => setType('lamp')}
                title={t('newProjectLampTitle')}
                description={t('newProjectLampDesc')}
              />
            </div>
          </div>
        </div>

        <div className="move-confirm-actions" style={{ marginTop: 20 }}>
          <button
            className="btn-ghost"
            onClick={onCancel}
            style={{ padding: '6px 14px', fontSize: 12.5, height: 32 }}
          >
            {t('moveConfirmCancel')}
          </button>
          <button
            className="btn-primary"
            onClick={commit}
            disabled={!name.trim()}
            style={{ height: 32 }}
          >
            {t('newProjectCreateButton')}
          </button>
        </div>
      </div>
    </div>
  );
}

interface TypeCardProps {
  selected: boolean;
  onSelect: () => void;
  title: string;
  description: string;
}

function TypeCard({ selected, onSelect, title, description }: TypeCardProps) {
  return (
    <div
      onClick={onSelect}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        padding: '12px 14px',
        border: `2px solid ${selected ? 'var(--amber)' : 'var(--hairline-2)'}`,
        background: selected ? 'var(--amber-soft)' : 'var(--paper)',
        borderRadius: 8,
        cursor: 'pointer',
        transition: 'border-color 0.15s, background-color 0.15s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, color: selected ? 'var(--amber-ink)' : 'var(--text-bright)' }}>
          {title}
        </span>
        <input
          type="radio"
          checked={selected}
          onChange={onSelect}
          style={{ accentColor: 'var(--amber)' }}
        />
      </div>
      <span style={{ fontSize: 12, color: 'var(--text-soft)' }}>
        {description}
      </span>
    </div>
  );
}
