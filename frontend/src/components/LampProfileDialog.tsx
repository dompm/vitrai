import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { LampConfig, LampProfilePoint } from '../types';

interface Props {
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

export function LampProfileDialog({ initialConfig, isFirstTime, onCancel, onConfirm }: Props) {
  const { t } = useTranslation();
  const [facetCount, setFacetCount] = useState(initialConfig.facetCount);
  const [profilePoints, setProfilePoints] = useState<LampProfilePoint[]>(initialConfig.profilePoints);

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

        <div style={{ display: 'flex', justifyContent: 'center', margin: '12px 0 4px' }}>
          <LampProfileSketch profilePoints={profilePoints} facetCount={facetCount} />
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

interface SketchProps {
  profilePoints: LampProfilePoint[];
  facetCount: number;
}

function LampProfileSketch({ profilePoints, facetCount }: SketchProps) {
  if (profilePoints.length < 2) return null;

  // Layout: 160x140 sketch box, 10px margin.
  const W = 160;
  const H = 140;
  const PAD = 12;

  const maxR = Math.max(...profilePoints.map(p => p.r));
  const minY = Math.min(...profilePoints.map(p => p.y));
  const maxY = Math.max(...profilePoints.map(p => p.y));
  const drawH = H - 2 * PAD;
  // Reserve a bit of vertical room for the bottom ellipse arc.
  const usableH = drawH - 10;
  const sx = (W / 2 - PAD) / Math.max(1, maxR);
  const sy = usableH / Math.max(1, maxY - minY);
  const s = Math.min(sx, sy);

  const px = (r: number) => W / 2 + r * s;
  const py = (y: number) => PAD + (y - minY) * s;

  const top = profilePoints[0];
  const bot = profilePoints[profilePoints.length - 1];
  const topRpx = top.r * s;
  const botRpx = bot.r * s;
  // Ellipse "depth" — perspective hint. Wider at base.
  const ellipseRy = (r: number) => Math.max(2, r * 0.22);

  const rightSide = profilePoints.map(p => `${px(p.r)},${py(p.y)}`).join(' ');
  const leftSide = [...profilePoints].reverse().map(p => `${px(-p.r)},${py(p.y)}`).join(' ');

  const stroke = 'var(--amber-ink)';
  const strokeW = 1.4;

  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ background: 'var(--paper)', border: '1px solid var(--hairline-2)', borderRadius: 8 }}
      aria-hidden="true"
    >
      {/* Faint facet hints — vertical lines on the inside */}
      {facetCount >= 3 && Array.from({ length: Math.min(facetCount, 8) - 1 }).map((_, i) => {
        const t = (i + 1) / Math.min(facetCount, 8);
        const x = px(-maxR + 2 * maxR * t);
        return (
          <line
            key={i}
            x1={x}
            y1={py(top.y) + ellipseRy(topRpx) * 0.2}
            x2={x}
            y2={py(bot.y) - ellipseRy(botRpx) * 0.2}
            stroke={stroke}
            strokeWidth={0.5}
            opacity={0.2}
          />
        );
      })}

      {/* Top ellipse (full ring — full lip visible from above) */}
      <ellipse
        cx={W / 2}
        cy={py(top.y)}
        rx={topRpx}
        ry={ellipseRy(topRpx)}
        fill="none"
        stroke={stroke}
        strokeWidth={strokeW}
      />

      {/* Right silhouette */}
      <polyline points={rightSide} fill="none" stroke={stroke} strokeWidth={strokeW} strokeLinejoin="round" />
      {/* Left silhouette */}
      <polyline points={leftSide} fill="none" stroke={stroke} strokeWidth={strokeW} strokeLinejoin="round" />

      {/* Bottom ellipse front-half (back half is hidden by the lamp body) */}
      <path
        d={`M ${px(-bot.r)},${py(bot.y)} A ${botRpx},${ellipseRy(botRpx)} 0 0 0 ${px(bot.r)},${py(bot.y)}`}
        fill="none"
        stroke={stroke}
        strokeWidth={strokeW}
      />
      {/* Bottom ellipse back-half (dashed to suggest hidden edge) */}
      <path
        d={`M ${px(-bot.r)},${py(bot.y)} A ${botRpx},${ellipseRy(botRpx)} 0 0 1 ${px(bot.r)},${py(bot.y)}`}
        fill="none"
        stroke={stroke}
        strokeWidth={strokeW * 0.7}
        strokeDasharray="2 3"
        opacity={0.5}
      />
    </svg>
  );
}
