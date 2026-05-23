import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { LampConfig, LampProfilePoint, Project } from '../types';
import { Lamp3DPreview } from './Lamp3DPreview';

interface Props {
  project: Project;
  initialConfig: LampConfig;
  isFirstTime?: boolean;
  onCancel: () => void;
  onConfirm: (config: Partial<LampConfig>) => void;
}

type Preset = 'cylinder' | 'cone' | 'dome' | 'pyramid';

const PRESETS: Record<Preset, LampProfilePoint[]> = {
  cylinder: [
    { r: 80, y: 0 },
    { r: 80, y: 200 },
  ],
  cone: [
    { r: 40, y: 0 },
    { r: 120, y: 200 },
  ],
  dome: [
    { r: 20, y: 0 },
    { r: 80, y: 60 },
    { r: 100, y: 140 },
    { r: 60, y: 200 },
  ],
  pyramid: [
    { r: 10, y: 0 },
    { r: 120, y: 200 },
  ],
};

export function LampProfileDialog({ project, initialConfig, isFirstTime, onCancel, onConfirm }: Props) {
  const { t } = useTranslation();
  const [facetCount, setFacetCount] = useState(initialConfig.facetCount);
  const [profilePoints, setProfilePoints] = useState<LampProfilePoint[]>(initialConfig.profilePoints);

  const previewProject = useMemo<Project>(() => ({
    ...project,
    lampConfig: { facetCount, profilePoints, activeTierIndex: initialConfig.activeTierIndex },
  }), [project, facetCount, profilePoints, initialConfig.activeTierIndex]);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel();
    }
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onCancel]);

  function applyPreset(p: Preset) {
    setProfilePoints(PRESETS[p]);
  }

  function commit() {
    onConfirm({ facetCount, profilePoints });
  }

  return (
    <div className="move-confirm-backdrop" onClick={onCancel}>
      <div
        className="move-confirm-dialog"
        style={{ width: 480, maxWidth: '90%' }}
        onClick={e => e.stopPropagation()}
      >
        <p
          className="move-confirm-title"
          style={{ fontFamily: '"Instrument Serif", Georgia, serif', fontSize: '1.8rem', fontWeight: 400, color: 'var(--text-bright)', marginBottom: 4 }}
        >
          {isFirstTime ? t('lampSetupTitle') : t('lampProfileTitle')}
        </p>
        {isFirstTime && (
          <p style={{ fontSize: 12.5, color: 'var(--text-soft)', marginBottom: 12 }}>
            {t('lampSetupSubtitle')}
          </p>
        )}

        <div
          style={{
            width: '100%',
            height: 240,
            background: '#ffffff',
            border: '1px solid var(--hairline-2)',
            borderRadius: 8,
            overflow: 'hidden',
            margin: '12px 0 4px',
          }}
        >
          <Lamp3DPreview
            project={previewProject}
            selectedPieceIds={[]}
            onSelectPiece={() => {}}
            onUpdateLampConfig={() => {}}
            activeSheetId=""
            onSetFocusedPanelIdx={() => {}}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, margin: '16px 0' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-soft)' }}>
              {t('lampProfilePresets')}
            </label>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {(Object.keys(PRESETS) as Preset[]).map(p => (
                <button
                  key={p}
                  className="btn-ghost"
                  onClick={() => applyPreset(p)}
                  style={{ textTransform: 'capitalize', padding: '6px 12px', fontSize: 12 }}
                >
                  {t(`lampPreset_${p}`)}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-soft)' }}>
                {t('lampProfileFacets')}
              </label>
              <span style={{ fontSize: 12, color: 'var(--text-bright)', fontVariantNumeric: 'tabular-nums' }}>{facetCount}</span>
            </div>
            <input
              type="range"
              min={3}
              max={24}
              step={1}
              value={facetCount}
              onChange={e => setFacetCount(parseInt(e.target.value, 10))}
              style={{ width: '100%' }}
            />
          </div>

          <div style={{ fontSize: 12, color: 'var(--text-soft)', lineHeight: 1.5 }}>
            {t('lampProfileHint')}
          </div>
        </div>

        <div className="move-confirm-actions" style={{ marginTop: 8 }}>
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
            style={{ height: 32 }}
          >
            {isFirstTime ? t('lampSetupConfirm') : t('lampProfileConfirm')}
          </button>
        </div>
      </div>
    </div>
  );
}

