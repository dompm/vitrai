import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { LampConfig, LampProfilePoint, Project } from '../types';
import { Lamp3DPreview } from './Lamp3DPreview';
import { computeUnrolledLamp, reflowLampPoints } from '../utils/lampGeometry';

interface Props {
  project: Project;
  initialConfig: LampConfig;
  isFirstTime?: boolean;
  onCancel: () => void;
  onConfirm: (config: Partial<LampConfig>) => void;
  onUpdatePatternScale?: (scale: import('../types').Scale) => void;
  hasTutorialBar?: boolean;
}

type Preset = 'cylinder' | 'cone' | 'dome' | 'pyramid' | 'tulip';

const PRESETS: Record<Preset, { facetCount: number; profilePoints: LampProfilePoint[]; smooth?: boolean }> = {
  cylinder: {
    facetCount: 6,
    smooth: true,
    profilePoints: [
      { r: 800, y: 0 },
      { r: 800, y: 2000 },
    ],
  },
  cone: {
    facetCount: 12,
    smooth: true,
    profilePoints: [
      { r: 400, y: 0 },
      { r: 1200, y: 2000 },
    ],
  },
  dome: {
    facetCount: 12,
    smooth: false,
    profilePoints: [
      { r: 400, y: 0 },
      { r: 800, y: 400 },
      { r: 1100, y: 1000 },
      { r: 1200, y: 1600 },
    ],
  },
  pyramid: {
    facetCount: 4,
    smooth: false,
    profilePoints: [
      { r: 200, y: 0 },
      { r: 1200, y: 2000 },
    ],
  },
  tulip: {
    facetCount: 12,
    smooth: false,
    profilePoints: [
      { r: 300, y: 0 },
      { r: 250, y: 300 },
      { r: 700, y: 1000 },
      { r: 1100, y: 1600 },
      { r: 1200, y: 1800 },
      { r: 1000, y: 2000 },
    ],
  },
};

export function LampProfileDialog({ project, initialConfig, isFirstTime, onCancel, onConfirm, onUpdatePatternScale, hasTutorialBar }: Props) {
  const { t } = useTranslation();
  const [facetCount, setFacetCount] = useState(initialConfig.facetCount);
  const [smooth, setSmooth] = useState<boolean>(!!initialConfig.smooth);
  const [profilePoints, setProfilePoints] = useState<LampProfilePoint[]>(initialConfig.profilePoints);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);

  const FACET_MIN = 3;
  const FACET_MAX = 24;
  // The slider's effective range goes one tick past FACET_MAX to represent "Smooth".
  const sliderValue = smooth ? FACET_MAX + 1 : facetCount;

  const previewProject = useMemo<Project>(() => {
    const mergedConfig = { facetCount, profilePoints, activeTierIndex: initialConfig.activeTierIndex, smooth };
    if (!project.lampConfig) return { ...project, lampConfig: mergedConfig };

    const oldN = project.lampConfig.facetCount;
    const newN = mergedConfig.facetCount;
    const oldUnrolled = computeUnrolledLamp(project.lampConfig);
    const newUnrolled = computeUnrolledLamp(mergedConfig);

    const reflowedPieces = project.pieces.map(piece => {
      const newPolygon = reflowLampPoints(piece.polygon, oldUnrolled, newUnrolled, oldN, newN);

      const newCurvePoints = piece.curvePoints?.map(cp => {
        const [newCtrl] = reflowLampPoints([cp.ctrl], oldUnrolled, newUnrolled, oldN, newN);
        return { ...cp, ctrl: newCtrl };
      });

      const newPromptPoints = piece.promptPoints?.map(pt => {
        const [newPt] = reflowLampPoints([[pt.x, pt.y]], oldUnrolled, newUnrolled, oldN, newN);
        return { ...pt, x: newPt[0], y: newPt[1] };
      });

      let newPromptBox = piece.promptBox;
      if (piece.promptBox) {
        const [p1, p2] = reflowLampPoints(
          [[piece.promptBox.x1, piece.promptBox.y1], [piece.promptBox.x2, piece.promptBox.y2]],
          oldUnrolled,
          newUnrolled,
          oldN,
          newN
        );
        newPromptBox = {
          x1: Math.min(p1[0], p2[0]),
          y1: Math.min(p1[1], p2[1]),
          x2: Math.max(p1[0], p2[0]),
          y2: Math.max(p1[1], p2[1]),
        };
      }

      return {
        ...piece,
        polygon: newPolygon,
        curvePoints: newCurvePoints,
        promptPoints: newPromptPoints,
        promptBox: newPromptBox,
      };
    });

    return {
      ...project,
      lampConfig: mergedConfig,
      pieces: reflowedPieces,
    };
  }, [project, facetCount, profilePoints, initialConfig.activeTierIndex, smooth]);

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        // Capture phase + stopPropagation, like the other modals: the Esc that
        // dismisses this dialog must not also reach the panels' (bubble-phase)
        // window handlers, which would reset tools / discard a pen polygon.
        e.preventDefault();
        e.stopPropagation();
        onCancel();
      }
    }
    window.addEventListener('keydown', handleKey, true);
    return () => window.removeEventListener('keydown', handleKey, true);
  }, [onCancel]);

  function applyPreset(p: Preset) {
    const preset = PRESETS[p];
    setProfilePoints(preset.profilePoints);
    setFacetCount(preset.facetCount);
    setSmooth(!!preset.smooth);
    setSelectedIdx(0);
  }

  function updatePoint(idx: number, patch: Partial<LampProfilePoint>) {
    setProfilePoints(prev => prev.map((p, i) => {
      if (i !== idx) return p;
      return { ...p, ...patch, y: patch.y ?? p.y };
    }));
  }

  function addPointAfter(idx: number) {
    setProfilePoints(prev => {
      const next = [...prev];
      const a = next[idx];
      const b = next[idx + 1] ?? { r: a.r, y: a.y + 40 };
      next.splice(idx + 1, 0, { r: (a.r + b.r) / 2, y: (a.y + b.y) / 2 });
      return next;
    });
    setSelectedIdx(idx + 1);
  }

  function deletePoint(idx: number) {
    if (profilePoints.length <= 2) return;
    setProfilePoints(prev => prev.filter((_, i) => i !== idx));
    setSelectedIdx(Math.max(0, idx - 1));
  }

  function commit() {
    // Sort top-to-bottom by y on commit so downstream geometry stays well-defined.
    const sorted = [...profilePoints].sort((a, b) => a.y - b.y);
    onConfirm({ facetCount, profilePoints: sorted, smooth });
  }

  const scale = project.patternScale || { pxPerUnit: 100, unit: 'in' as const };

  return (
    <div className="move-confirm-backdrop" onClick={onCancel}>
      <div
        className="move-confirm-dialog"
        style={{ width: 640, maxWidth: '94%', maxHeight: '92vh', overflowY: 'auto', paddingBottom: hasTutorialBar ? 90 : 20 }}
        onClick={e => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <p
            className="move-confirm-title"
            style={{ fontFamily: '"Instrument Serif", Georgia, serif', fontSize: '1.8rem', fontWeight: 400, color: 'var(--text-bright)', margin: 0 }}
          >
            {isFirstTime ? t('lampSetupTitle') : t('lampProfileTitle')}
          </p>
          {onUpdatePatternScale && project.patternScale && (
            <select
              value={project.patternScale.unit}
              onChange={e => onUpdatePatternScale({ ...project.patternScale!, unit: e.target.value as import('../types').ScaleUnit })}
              style={{ padding: '4px 8px', borderRadius: 4, background: 'var(--paper)', color: 'var(--text-bright)', border: '1px solid var(--hairline-2)', outline: 'none' }}
            >
              <option value="in">{t('unit_in')}</option>
              <option value="cm">{t('unit_cm')}</option>
              <option value="mm">{t('unit_mm')}</option>
            </select>
          )}
        </div>
        {isFirstTime && (
          <p style={{ fontSize: 12.5, color: 'var(--text-soft)', marginBottom: 12 }}>
            {t('lampSetupSubtitle')}
          </p>
        )}

        <div
          style={{
            width: '100%',
            height: 220,
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

        <div style={{ display: 'flex', gap: 12, margin: '12px 0' }}>
          <ProfileEditor
            profilePoints={profilePoints}
            selectedIdx={selectedIdx}
            onSelectIdx={setSelectedIdx}
            onUpdatePoint={updatePoint}
            onAddAfter={addPointAfter}
            onDelete={deletePoint}
            onLabel={t('lampProfileEditorLabel')}
            unit={scale.unit}
            pxPerUnit={scale.pxPerUnit}
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
              <span style={{ fontSize: 12, color: 'var(--text-bright)', fontVariantNumeric: 'tabular-nums' }}>
                {smooth ? t('lampProfileSmooth') : facetCount}
              </span>
            </div>
            <input
              type="range"
              min={FACET_MIN}
              max={FACET_MAX + 1}
              step={1}
              value={sliderValue}
              onChange={e => {
                const v = parseInt(e.target.value, 10);
                if (v > FACET_MAX) {
                  setSmooth(true);
                } else {
                  setSmooth(false);
                  setFacetCount(v);
                }
              }}
              style={{ width: '100%' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-dim)' }}>
              <span>{FACET_MIN}</span>
              <span>{t('lampProfileSmooth')}</span>
            </div>
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

interface ProfileEditorProps {
  profilePoints: LampProfilePoint[];
  selectedIdx: number;
  onSelectIdx: (idx: number) => void;
  onUpdatePoint: (idx: number, patch: Partial<LampProfilePoint>) => void;
  onAddAfter: (idx: number) => void;
  onDelete: (idx: number) => void;
  onLabel: string;
  unit: import('../types').ScaleUnit;
  pxPerUnit: number;
}

function ProfileEditor({
  profilePoints,
  selectedIdx,
  onSelectIdx,
  onUpdatePoint,
  onAddAfter,
  onDelete,
  onLabel,
  unit,
  pxPerUnit,
}: ProfileEditorProps) {
  const W = 360;
  const H = 240;
  const PAD_LEFT = 32;
  const PAD_RIGHT = 16;
  const PAD_TOP = 12;
  const PAD_BOTTOM = 22;
  
  const gridStepPhys = unit === 'mm' ? 10 : (unit === 'cm' ? 2 : 1);
  // Guard against a zero/invalid pattern scale: GRID_RAW = 0 turns the tick
  // loops below into infinite loops and NaNs the view bounds.
  const safePxPerUnit = Number.isFinite(pxPerUnit) && pxPerUnit > 0 ? pxPerUnit : 1;
  const GRID_RAW = gridStepPhys * safePxPerUnit;
  const SNAP_RAW = unit === 'in' ? (safePxPerUnit / 8) : (unit === 'cm' ? (safePxPerUnit / 4) : safePxPerUnit);
  const SNAP_PX = 8;        // align-to-other-handle threshold (screen px)

  // Data bounds with a comfortable margin so the canvas accommodates dragging
  // past the current extent of the profile.
  const dataMaxR = Math.max(0, ...profilePoints.map(p => p.r));
  const dataMinY = profilePoints.length ? Math.min(...profilePoints.map(p => p.y)) : 0;
  const dataMaxY = profilePoints.length ? Math.max(...profilePoints.map(p => p.y)) : 200;
  // Round bounds up to the next major-grid step so axis ticks land cleanly.
  const round = (v: number, step: number) => Math.ceil(v / step) * step;
  const viewMaxR = Math.max(GRID_RAW * 3, round(dataMaxR + (GRID_RAW / 2), GRID_RAW));
  const viewMinY = Math.min(0, dataMinY);
  const viewMaxY = Math.max(viewMinY + GRID_RAW * 3, round(dataMaxY + (GRID_RAW / 2), GRID_RAW));

  const sx = (W - PAD_LEFT - PAD_RIGHT) / viewMaxR;
  const sy = (H - PAD_TOP - PAD_BOTTOM) / (viewMaxY - viewMinY);

  const toSx = (r: number) => PAD_LEFT + r * sx;
  const toSy = (y: number) => PAD_TOP + (y - viewMinY) * sy;
  const fromSx = (xPx: number) => (xPx - PAD_LEFT) / sx;
  const fromSy = (yPx: number) => viewMinY + (yPx - PAD_TOP) / sy;

  const svgRef = useRef<SVGSVGElement>(null);
  const [activeGuides, setActiveGuides] = useState<{ v?: number; h?: number }>({});

  function pointerToCoords(ev: PointerEvent | React.PointerEvent): [number, number] {
    const svg = svgRef.current;
    if (!svg) return [0, 0];
    const rect = svg.getBoundingClientRect();
    const x = ((ev as PointerEvent).clientX - rect.left) * (W / rect.width);
    const y = ((ev as PointerEvent).clientY - rect.top) * (H / rect.height);
    return [fromSx(x), fromSy(y)];
  }

  function startDrag(idx: number, e: React.PointerEvent) {
    e.preventDefault();
    e.stopPropagation();
    onSelectIdx(idx);
    const startR = profilePoints[idx].r;
    const startY = profilePoints[idx].y;

    function onMove(ev: PointerEvent) {
      let [r, y] = pointerToCoords(ev);

      // Shift = lock the drag to the dominant axis from the starting position.
      if (ev.shiftKey) {
        if (Math.abs(r - startR) > Math.abs(y - startY)) y = startY;
        else r = startR;
      }

      // Alignment snap: match r or y to any other handle within SNAP_PX.
      const guides: { v?: number; h?: number } = {};
      let snappedR = false;
      let snappedY = false;
      for (let i = 0; i < profilePoints.length; i++) {
        if (i === idx) continue;
        const p = profilePoints[i];
        if (!snappedR && Math.abs(toSx(p.r) - toSx(r)) < SNAP_PX) {
          r = p.r;
          guides.v = p.r;
          snappedR = true;
        }
        if (!snappedY && Math.abs(toSy(p.y) - toSy(y)) < SNAP_PX) {
          y = p.y;
          guides.h = p.y;
          snappedY = true;
        }
      }

      // Grid snap on any axis that hasn't already been alignment-snapped.
      if (!snappedR) r = Math.round(r / SNAP_RAW) * SNAP_RAW;
      if (!snappedY) y = Math.round(y / SNAP_RAW) * SNAP_RAW;

      r = Math.max(0, r);

      setActiveGuides(guides);
      onUpdatePoint(idx, { r, y });
    }

    function onUp() {
      setActiveGuides({});
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    }

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }

  const polylinePts = profilePoints.map(p => `${toSx(p.r)},${toSy(p.y)}`).join(' ');
  const mirroredPts = profilePoints.map(p => `${2 * PAD_LEFT - toSx(p.r)},${toSy(p.y)}`).join(' ');

  const selected = profilePoints[selectedIdx];

  // Major grid lines
  const rTicks: number[] = [];
  for (let r = 0; r <= viewMaxR; r += GRID_RAW) rTicks.push(r);
  const yTicks: number[] = [];
  for (let y = Math.ceil(viewMinY / GRID_RAW) * GRID_RAW; y <= viewMaxY; y += GRID_RAW) yTicks.push(y);

  return (
    <>
      <svg
        ref={svgRef}
        width={W}
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        style={{ background: '#ffffff', border: '1px solid var(--hairline-2)', borderRadius: 8, touchAction: 'none', flexShrink: 0 }}
      >
        {/* Grid */}
        {rTicks.map(r => (
          <line
            key={`gr-${r}`}
            x1={toSx(r)}
            y1={PAD_TOP}
            x2={toSx(r)}
            y2={H - PAD_BOTTOM}
            stroke="rgba(40, 30, 15, 0.10)"
            strokeWidth={1}
          />
        ))}
        {yTicks.map(y => (
          <line
            key={`gy-${y}`}
            x1={PAD_LEFT}
            y1={toSy(y)}
            x2={W - PAD_RIGHT}
            y2={toSy(y)}
            stroke="rgba(40, 30, 15, 0.10)"
            strokeWidth={1}
          />
        ))}

        {/* Axis Ticks/Labels */}
        {rTicks.map(r => (
          <text
            key={`lbl-r-${r}`}
            x={toSx(r)}
            y={H - PAD_BOTTOM + 13}
            textAnchor="middle"
            fill="var(--text-dim)"
            style={{ fontSize: 9, fontFamily: 'var(--font-sans, sans-serif)', opacity: 0.6 }}
          >
            {r}
          </text>
        ))}
        {yTicks.map(y => (
          <text
            key={`lbl-y-${y}`}
            x={PAD_LEFT - 6}
            y={toSy(y) + 3}
            textAnchor="end"
            fill="var(--text-dim)"
            style={{ fontSize: 9, fontFamily: 'var(--font-sans, sans-serif)', opacity: 0.6 }}
          >
            {y}
          </text>
        ))}

        {/* Active alignment guides */}
        {activeGuides.v !== undefined && (
          <line
            x1={toSx(activeGuides.v)}
            y1={PAD_TOP - 4}
            x2={toSx(activeGuides.v)}
            y2={H - PAD_BOTTOM + 4}
            stroke="var(--amber)"
            strokeWidth={1}
            strokeDasharray="4 3"
          />
        )}
        {activeGuides.h !== undefined && (
          <line
            x1={PAD_LEFT - 4}
            y1={toSy(activeGuides.h)}
            x2={W - PAD_RIGHT + 4}
            y2={toSy(activeGuides.h)}
            stroke="var(--amber)"
            strokeWidth={1}
            strokeDasharray="4 3"
          />
        )}

        {/* Mirrored silhouette (subtle, just for vase-feel context) */}
        <polyline
          points={mirroredPts}
          fill="none"
          stroke="rgba(40, 30, 15, 0.18)"
          strokeWidth={1}
          strokeDasharray="2 3"
        />

        {/* Profile curve */}
        <polyline points={polylinePts} fill="none" stroke="var(--amber-ink)" strokeWidth={1.6} />

        {/* Handles */}
        {profilePoints.map((p, i) => {
          const cx = toSx(p.r);
          const cy = toSy(p.y);
          const isSel = i === selectedIdx;
          return (
            <circle
              key={i}
              cx={cx}
              cy={cy}
              r={isSel ? 7 : 5}
              fill={isSel ? 'var(--amber)' : '#ffffff'}
              stroke="var(--amber-ink)"
              strokeWidth={isSel ? 2 : 1.4}
              style={{ cursor: 'grab' }}
              onPointerDown={e => startDrag(i, e)}
            />
          );
        })}
      </svg>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, minWidth: 0 }}>
        <label style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-soft)' }}>
          {onLabel}
        </label>
        {selected && (
          <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <NumberField
              label={`r (${unit})`}
              value={selected ? Number((selected.r / pxPerUnit).toFixed(3)) : 0}
              step={unit === 'in' ? 0.125 : (unit === 'cm' ? 0.5 : 1)}
              onChange={v => onUpdatePoint(selectedIdx, { r: Math.max(0, v * pxPerUnit), y: selected.y })}
            />
            <NumberField
              label={`y (${unit})`}
              value={selected ? Number((selected.y / pxPerUnit).toFixed(3)) : 0}
              step={unit === 'in' ? 0.125 : (unit === 'cm' ? 0.5 : 1)}
              onChange={v => onUpdatePoint(selectedIdx, { r: selected.r, y: v * pxPerUnit })}
            />
          </div>
          </>
        )}
        <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
          <button
            className="btn-ghost"
            onClick={() => onAddAfter(selectedIdx)}
            style={{ padding: '4px 10px', fontSize: 12 }}
          >
            + Add point
          </button>
          <button
            className="btn-ghost"
            onClick={() => onDelete(selectedIdx)}
            disabled={profilePoints.length <= 2}
            style={{ padding: '4px 10px', fontSize: 12 }}
          >
            Delete
          </button>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.4, marginTop: 4 }}>
          Drag any handle to reshape the profile. Click a handle to edit it numerically.
        </div>
      </div>
    </>
  );
}

interface NumberFieldProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  step?: number;
}

function NumberField({ label, value, onChange, disabled, step }: NumberFieldProps) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, opacity: disabled ? 0.5 : 1 }}>
      <span style={{ fontSize: 12, color: 'var(--text-soft)', width: 56 }}>{label}</span>
      <input
        type="number"
        value={value}
        disabled={disabled}
        step={step ?? 'any'}
        onChange={e => {
          const n = parseFloat(e.target.value);
          if (!Number.isNaN(n)) onChange(n);
        }}
        style={{
          flex: 1,
          minWidth: 0,
          background: 'var(--paper)',
          border: '1px solid var(--hairline-2)',
          borderRadius: 5,
          padding: '4px 8px',
          fontSize: 12,
          color: 'var(--text-bright)',
          outline: 'none',
          fontFamily: 'inherit',
          fontVariantNumeric: 'tabular-nums',
        }}
      />
    </label>
  );
}
