import { useEffect, useMemo, useRef, useState } from 'react';
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
  const [selectedIdx, setSelectedIdx] = useState<number>(0);

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
    const next = PRESETS[p];
    setProfilePoints(next);
    setSelectedIdx(0);
  }

  function updatePoint(idx: number, patch: Partial<LampProfilePoint>) {
    setProfilePoints(prev => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
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
    onConfirm({ facetCount, profilePoints: sorted });
  }

  return (
    <div className="move-confirm-backdrop" onClick={onCancel}>
      <div
        className="move-confirm-dialog"
        style={{ width: 640, maxWidth: '94%', maxHeight: '92vh', overflowY: 'auto' }}
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
}

function ProfileEditor({
  profilePoints,
  selectedIdx,
  onSelectIdx,
  onUpdatePoint,
  onAddAfter,
  onDelete,
  onLabel,
}: ProfileEditorProps) {
  const W = 360;
  const H = 240;
  const PAD = 14;
  const GRID_MM = 50;       // single grid step (mm) — coarse, no minor grid
  const SNAP_GRID_MM = 10;  // grid snap resolution (mm)
  const SNAP_PX = 8;        // align-to-other-handle threshold (screen px)

  // Data bounds with a comfortable margin so the canvas accommodates dragging
  // past the current extent of the profile.
  const dataMaxR = Math.max(0, ...profilePoints.map(p => p.r));
  const dataMinY = profilePoints.length ? Math.min(...profilePoints.map(p => p.y)) : 0;
  const dataMaxY = profilePoints.length ? Math.max(...profilePoints.map(p => p.y)) : 200;
  // Round bounds up to the next major-grid step so axis ticks land cleanly.
  const round = (v: number, step: number) => Math.ceil(v / step) * step;
  const viewMaxR = Math.max(GRID_MM * 3, round(dataMaxR + 20, GRID_MM));
  const viewMinY = Math.min(0, dataMinY);
  const viewMaxY = Math.max(viewMinY + GRID_MM * 3, round(dataMaxY + 20, GRID_MM));

  const sx = (W - 2 * PAD) / viewMaxR;
  const sy = (H - 2 * PAD) / (viewMaxY - viewMinY);

  const toSx = (r: number) => PAD + r * sx;
  const toSy = (y: number) => PAD + (y - viewMinY) * sy;
  const fromSx = (xPx: number) => (xPx - PAD) / sx;
  const fromSy = (yPx: number) => viewMinY + (yPx - PAD) / sy;

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
      if (!snappedR) r = Math.round(r / SNAP_GRID_MM) * SNAP_GRID_MM;
      if (!snappedY) y = Math.round(y / SNAP_GRID_MM) * SNAP_GRID_MM;

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
  const mirroredPts = profilePoints.map(p => `${2 * PAD - toSx(p.r)},${toSy(p.y)}`).join(' ');

  const selected = profilePoints[selectedIdx];

  // Single coarse grid (~50 mm steps).
  const rTicks: number[] = [];
  for (let r = 0; r <= viewMaxR; r += GRID_MM) rTicks.push(r);
  const yTicks: number[] = [];
  for (let y = Math.ceil(viewMinY / GRID_MM) * GRID_MM; y <= viewMaxY; y += GRID_MM) yTicks.push(y);

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
            y1={PAD}
            x2={toSx(r)}
            y2={H - PAD}
            stroke="rgba(40, 30, 15, 0.10)"
            strokeWidth={1}
          />
        ))}
        {yTicks.map(y => (
          <line
            key={`gy-${y}`}
            x1={PAD}
            y1={toSy(y)}
            x2={W - PAD}
            y2={toSy(y)}
            stroke="rgba(40, 30, 15, 0.10)"
            strokeWidth={1}
          />
        ))}

        {/* Active alignment guides */}
        {activeGuides.v !== undefined && (
          <line
            x1={toSx(activeGuides.v)}
            y1={PAD - 4}
            x2={toSx(activeGuides.v)}
            y2={H - PAD + 4}
            stroke="var(--amber)"
            strokeWidth={1}
            strokeDasharray="4 3"
          />
        )}
        {activeGuides.h !== undefined && (
          <line
            x1={PAD - 4}
            y1={toSy(activeGuides.h)}
            x2={W - PAD + 4}
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
            <NumberField
              label="r (mm)"
              value={selected.r}
              onChange={v => onUpdatePoint(selectedIdx, { r: Math.max(0, v) })}
            />
            <NumberField
              label="y (mm)"
              value={selected.y}
              onChange={v => onUpdatePoint(selectedIdx, { y: v })}
            />
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
}

function NumberField({ label, value, onChange }: NumberFieldProps) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 12, color: 'var(--text-soft)', width: 56 }}>{label}</span>
      <input
        type="number"
        value={value}
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
