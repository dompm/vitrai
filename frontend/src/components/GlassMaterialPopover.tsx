import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { useTranslation } from 'react-i18next';
import { CANVAS } from '../theme';
import type { GlassCategory, GlassMaterialParams, GlassSheet, GlassSurface } from '../types';
import { GLASS_CATEGORIES, GLASS_SURFACES, getSheetMaterial, materialForCategory } from '../utils/glassMaterial';
import { getGlassEstimator } from '../glassEstimator';

interface Props {
  sheet: GlassSheet;
  onUpdateMaterial: (m: Partial<GlassMaterialParams>, skipHistory?: boolean) => void;
}

function GemIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 3h12l4 6-10 13L2 9z" />
      <path d="M11 3 8 9l4 13 4-13-3-6" />
      <path d="M2 9h20" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ animation: 'spin 1s linear infinite' }}>
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
      <style>{`@keyframes spin { 100% { transform: rotate(360deg); } }`}</style>
    </svg>
  );
}

type EstimatePhase = 'idle' | 'loading' | 'analyzing';

export function GlassMaterialPopover({ sheet, onUpdateMaterial }: Props) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<EstimatePhase>('idle');
  const [progress, setProgress] = useState(0);
  const [estimateError, setEstimateError] = useState<string | null>(null);

  const material = getSheetMaterial(sheet);
  const estimatorAvailable = getGlassEstimator().isAvailable();
  const isEstimating = phase !== 'idle';

  useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('pointerdown', handleClickOutside);
    return () => document.removeEventListener('pointerdown', handleClickOutside);
  }, [isOpen]);

  async function handleEstimate() {
    if (isEstimating || !estimatorAvailable) return;
    const estimator = getGlassEstimator();
    setEstimateError(null);
    setPhase('loading');
    setProgress(0);
    let lastUpdate = 0;
    estimator.onProgress = (fraction) => {
      const now = Date.now();
      if (now - lastUpdate > 100 || fraction >= 1) {
        lastUpdate = now;
        setProgress(fraction);
      }
    };
    estimator.onStatus = (text) => {
      setPhase(text === 'analyzing' ? 'analyzing' : 'loading');
    };
    try {
      const params = await estimator.estimate(sheet.imageUrl);
      onUpdateMaterial(params);
    } catch (err) {
      console.warn('[GlassMaterial] estimation failed:', err);
      setEstimateError(t('estimateFailed', "Couldn't analyze the photo — keeping current values."));
    } finally {
      setPhase('idle');
    }
  }

  const sourceLabel =
    material.source === 'estimated' ? t('materialSourceEstimated', 'Estimated from photo')
    : material.source === 'user' ? t('materialSourceCustom', 'Custom')
    : t('materialSourceDefault', 'Default');

  const labelStyle: CSSProperties = {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    fontSize: '13px', color: CANVAS.lead, padding: '2px 0',
  };
  const selectStyle: CSSProperties = { maxWidth: '55%', fontSize: '13px' };

  return (
    <div className="tooltip-wrapper" ref={popoverRef}>
      <button
        type="button"
        className={`tool-btn ${isOpen ? 'active' : ''}`}
        onClick={() => setIsOpen(o => !o)}
        aria-label={t('glassMaterial', 'Material')}
      >
        {isEstimating ? <Spinner /> : <GemIcon />}
        <span className="tool-label">{t('glassMaterial', 'Material')}</span>
      </button>

      {!isOpen && <span className="tooltip-tip">{t('tooltipMaterialDesc', 'Set how this glass transmits and scatters light in the 3D preview')}</span>}

      {isOpen && (
        <div className="solder-popover">
          <div className="solder-popover-section">
            <span className="solder-popover-title" style={{ marginBottom: '4px', display: 'block' }}>{t('glassMaterial', 'Material')}</span>
            <span style={{ display: 'block', fontSize: '11px', color: '#8a8378', marginBottom: '12px' }}>{sourceLabel}</span>

            <label style={{ ...labelStyle, marginBottom: '8px' }}>
              {t('glassCategory', 'Glass type')}
              <select
                value={material.category}
                disabled={isEstimating}
                onChange={e => onUpdateMaterial(materialForCategory(e.target.value as GlassCategory, material.surface))}
                style={selectStyle}
              >
                {GLASS_CATEGORIES.map(c => (
                  <option key={c} value={c}>{t(`glassCategory_${c}`, c)}</option>
                ))}
              </select>
            </label>

            <label style={{ ...labelStyle, marginBottom: '8px' }}>
              {t('glassSurface', 'Surface')}
              <select
                value={material.surface}
                disabled={isEstimating}
                onChange={e => onUpdateMaterial({ surface: e.target.value as GlassSurface, source: 'user' })}
                style={selectStyle}
              >
                {GLASS_SURFACES.map(s => (
                  <option key={s} value={s}>{t(`glassSurface_${s}`, s)}</option>
                ))}
              </select>
            </label>

            <label style={{ ...labelStyle, flexDirection: 'column', alignItems: 'stretch', gap: '2px', marginBottom: '8px' }}>
              <span>{t('translucency', 'Translucency')} — {Math.round(material.translucency * 100)}%</span>
              <input
                type="range" min={0} max={1} step={0.01}
                value={material.translucency}
                disabled={isEstimating}
                onChange={e => onUpdateMaterial({ translucency: Number(e.target.value), source: 'user' }, true)}
                onPointerUp={e => onUpdateMaterial({ translucency: Number((e.target as HTMLInputElement).value), source: 'user' })}
                style={{ accentColor: CANVAS.amber }}
              />
            </label>

            <label style={{ ...labelStyle, flexDirection: 'column', alignItems: 'stretch', gap: '2px', marginBottom: '8px' }}>
              <span>{t('roughnessLabel', 'Roughness')} — {Math.round(material.roughness * 100)}%</span>
              <input
                type="range" min={0} max={1} step={0.01}
                value={material.roughness}
                disabled={isEstimating}
                onChange={e => onUpdateMaterial({ roughness: Number(e.target.value), source: 'user' }, true)}
                onPointerUp={e => onUpdateMaterial({ roughness: Number((e.target as HTMLInputElement).value), source: 'user' })}
                style={{ accentColor: CANVAS.amber }}
              />
            </label>

            <label style={{ ...labelStyle, marginBottom: '16px' }}>
              {t('glowTint', 'Glow tint')}
              <input
                type="color"
                value={material.glowTint ?? '#ffffff'}
                disabled={isEstimating}
                onChange={e => onUpdateMaterial({ glowTint: e.target.value, source: 'user' }, true)}
                onBlur={e => onUpdateMaterial({ glowTint: e.target.value, source: 'user' })}
                style={{ width: '40px', height: '24px', padding: 0, border: 'none', background: 'none', cursor: 'pointer' }}
              />
            </label>

            <button
              type="button"
              onClick={handleEstimate}
              disabled={isEstimating || !estimatorAvailable}
              title={!estimatorAvailable ? t('estimateNeedsWebgpu', 'Requires a WebGPU-capable browser') : undefined}
              style={{
                width: '100%',
                padding: '8px 12px',
                background: CANVAS.amber,
                color: CANVAS.paper,
                border: 'none',
                borderRadius: '6px',
                fontWeight: 600,
                cursor: (isEstimating || !estimatorAvailable) ? 'not-allowed' : 'pointer',
                opacity: (isEstimating || !estimatorAvailable) ? 0.5 : 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
              }}
            >
              {isEstimating && <Spinner />}
              {phase === 'loading' && progress > 0 && progress < 1
                ? t('estimateDownloading', 'Downloading model… {{percent}}%', { percent: Math.round(progress * 100) })
                : phase === 'analyzing' || (phase === 'loading' && progress >= 1)
                  ? t('estimateAnalyzing', 'Analyzing photo…')
                  : phase === 'loading'
                    ? t('estimatePreparing', 'Preparing…')
                    : t('estimateFromPhoto', 'Estimate from photo')}
            </button>

            {phase === 'loading' && progress > 0 && progress < 1 && (
              <div style={{ marginTop: '8px', height: '4px', borderRadius: '2px', background: 'rgba(0,0,0,0.08)', overflow: 'hidden' }}>
                <div style={{ width: `${Math.round(progress * 100)}%`, height: '100%', background: CANVAS.amber, transition: 'width 0.2s' }} />
              </div>
            )}

            {!isEstimating && !estimateError && (
              <span style={{ display: 'block', fontSize: '11px', color: '#8a8378', marginTop: '8px' }}>
                {estimatorAvailable
                  ? t('estimateFirstUseNote', 'First use downloads ~1.5 GB (cached afterwards).')
                  : t('estimateNeedsWebgpu', 'Requires a WebGPU-capable browser')}
              </span>
            )}
            {estimateError && (
              <span style={{ display: 'block', fontSize: '11px', color: CANVAS.ruby, marginTop: '8px' }}>{estimateError}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
