import { useEffect, useState, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ResultPanel } from './components/ResultPanel';
import { SheetPanel } from './components/SheetPanel';
import { MoveConfirmDialog } from './components/MoveConfirmDialog';
import { ShortcutsOverlay } from './components/ShortcutsOverlay';
import { GlassLibraryDialog } from './components/GlassLibraryDialog';
import { AddSheetMenu } from './components/AddSheetMenu';

import { Lamp3DPreview } from './components/Lamp3DPreview';
import { LampProfileDialog } from './components/LampProfileDialog';
import { useProject } from './hooks/useProject';
import {
  subtractPolygons,
  computeCentroid,
  snapPolygonToNeighbors,
  flattenCurves,
  arePolygonsEqual,
  fitSmoothPieceCurves,
  smoothPieceGeometry,
  insetPolygon,
  pieceToSvgPath,
  translateCurvesWithAnchor,
} from './utils/geometry';
import { computeImageSwatch } from './utils/swatch';
import { getSamBackend } from './samBackend';
import type { BoundingBox, GlassSheet, CurvePoint, Scale, Project } from './types';
import {
  IconUndo, IconRedo, IconGlobe, IconUpload, IconDownload, IconPrinter, IconSpark,
} from './components/icons';
import { STORAGE_KEY, TRACK_STEPS } from './components/Tutorial/types';
import type { StepId, PersistedTutorialState, TrackId } from './components/Tutorial/types';
import { Tutorial } from './components/Tutorial/Tutorial';
import { DEFAULT_PROJECT } from './defaultProject';
import { parseProject } from './storage/projectSchema';
import type { ToolId } from './components/Toolbar';
import { PieceTransformPreviewStore } from './editor/interaction/pieceTransformPreviewStore';
import { PenStatusStore, usePenStatus } from './editor/interaction/penStatusStore';
import './App.css';

interface SheetTabProps {
  sheet: GlassSheet;
  isActive: boolean;
  isEmpty: boolean;
  canDelete: boolean;
  pieceCount: number;
  pieceCountBySheet: Record<string, number>;
  allSheets: GlassSheet[];
  onSelect: () => void;
  onRename: (label: string) => void;
  onDelete: () => void;
  onMoveAllTo: (destSheetId: string) => void;
  onMoveAllFromSrc: (srcSheetId: string) => void;
  onNewSheetFromImage: () => void;
}

const getSnapRadius = (width: number) => Math.max(10, Math.round(width * 0.015));

function SheetTab({
  sheet, isActive, isEmpty, canDelete, pieceCount, pieceCountBySheet, allSheets,
  onSelect, onRename, onDelete, onMoveAllTo, onMoveAllFromSrc, onNewSheetFromImage,
}: SheetTabProps) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(sheet.label);
  const [menuPos, setMenuPos] = useState<{ x: number; y: number } | null>(null);
  const [submenu, setSubmenu] = useState<'moveTo' | 'moveFrom' | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);

  useEffect(() => { setDraft(sheet.label); }, [sheet.label]);
  useEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);

  useEffect(() => {
    if (!menuPos) return;
    function close() { setMenuPos(null); setSubmenu(null); }
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', close);
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', close);
    };
  }, [menuPos]);

  const otherSheets = allSheets.filter(s => s.id !== sheet.id);
  const sheetsWithPieces = otherSheets.filter(s => (pieceCountBySheet[s.id] ?? 0) > 0);

  function commit() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== sheet.label) onRename(trimmed);
    else setDraft(sheet.label);
    setEditing(false);
  }

  function startEditing() {
    setDraft(sheet.label);
    setEditing(true);
  }

  function handleContextMenu(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setMenuPos({ x: e.clientX, y: e.clientY });
  }

  function handlePointerDown(e: React.PointerEvent) {
    if (e.pointerType !== 'touch') return;
    longPressFired.current = false;
    longPressTimer.current = setTimeout(() => {
      longPressFired.current = true;
      setMenuPos({ x: e.clientX, y: e.clientY });
    }, 500);
  }

  function cancelLongPress() {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  }

  function handleClick() {
    if (longPressFired.current) {
      longPressFired.current = false;
      return;
    }
    onSelect();
  }

  if (editing) {
    return (
      <input
        ref={inputRef}
        className="sheet-tab active"
        value={draft}
        onChange={e => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={e => {
          if (e.key === 'Enter') { e.preventDefault(); commit(); }
          if (e.key === 'Escape') { setDraft(sheet.label); setEditing(false); }
        }}
        style={{ width: Math.max(56, draft.length * 7 + 28), padding: '3px 8px' }}
      />
    );
  }

  return (
    <>
      <button
        className={`sheet-tab ${isActive ? 'active' : ''}${isEmpty ? ' is-empty' : ''}`}
        onClick={handleClick}
        onDoubleClick={startEditing}
        onContextMenu={handleContextMenu}
        onPointerDown={handlePointerDown}
        onPointerUp={cancelLongPress}
        onPointerMove={cancelLongPress}
        onPointerCancel={cancelLongPress}
      >
        <span
          className="sheet-tab-swatch"
          style={{ background: sheet.swatch ?? 'var(--text-dim)' }}
          aria-hidden="true"
        />
        <span className="sheet-tab-label">{sheet.label}</span>
        {canDelete && (
          <span
            className="sheet-tab-close"
            onClick={e => { e.stopPropagation(); onDelete(); }}
            role="button"
            aria-label={t('delete')}
          >
            ×
          </span>
        )}
      </button>
      {menuPos && (
        <div
          className="sheet-tab-menu"
          style={{ left: menuPos.x, top: menuPos.y }}
          onMouseDown={e => e.stopPropagation()}
        >
          <button
            className="sheet-tab-menu-item"
            onClick={() => { setMenuPos(null); startEditing(); }}
            onMouseEnter={() => setSubmenu(null)}
          >
            {t('contextRename')}
          </button>

          {(() => {
            const moveToDisabled = pieceCount === 0;
            const moveFromDisabled = sheetsWithPieces.length === 0;
            return (
              <>
                <div
                  className={`sheet-tab-menu-item has-submenu${submenu === 'moveTo' ? ' open' : ''}${moveToDisabled ? ' is-disabled' : ''}`}
                  onClick={e => {
                    if (moveToDisabled) return;
                    e.stopPropagation();
                    setSubmenu(s => s === 'moveTo' ? null : 'moveTo');
                  }}
                  onMouseEnter={() => setSubmenu(moveToDisabled ? null : 'moveTo')}
                  aria-disabled={moveToDisabled}
                >
                  <span className="sheet-tab-menu-label">
                    {moveToDisabled
                      ? t('contextMoveAllEmpty')
                      : t('contextMoveAll', { count: pieceCount })}
                  </span>
                  <span className="sheet-tab-menu-caret">▸</span>
                  {!moveToDisabled && submenu === 'moveTo' && (
                    <div className="sheet-tab-submenu" onMouseDown={e => e.stopPropagation()}>
                      {otherSheets.length === 0 ? (
                        <div className="sheet-tab-menu-item is-disabled">
                          {t('contextNoOtherSheets')}
                        </div>
                      ) : (
                        otherSheets.map(s => (
                          <button
                            key={s.id}
                            className="sheet-tab-menu-item"
                            onClick={() => { setMenuPos(null); setSubmenu(null); onMoveAllTo(s.id); }}
                          >
                            <span className="sheet-tab-menu-label">{s.label}</span>
                            <span className="sheet-tab-menu-count">({pieceCountBySheet[s.id] ?? 0})</span>
                          </button>
                        ))
                      )}
                      <div className="sheet-tab-menu-divider" />
                      <button
                        className="sheet-tab-menu-item"
                        onClick={() => { setMenuPos(null); setSubmenu(null); onNewSheetFromImage(); }}
                      >
                        {t('contextNewFromImage')}
                      </button>
                    </div>
                  )}
                </div>

                <div
                  className={`sheet-tab-menu-item has-submenu${submenu === 'moveFrom' ? ' open' : ''}${moveFromDisabled ? ' is-disabled' : ''}`}
                  onClick={e => {
                    if (moveFromDisabled) return;
                    e.stopPropagation();
                    setSubmenu(s => s === 'moveFrom' ? null : 'moveFrom');
                  }}
                  onMouseEnter={() => setSubmenu(moveFromDisabled ? null : 'moveFrom')}
                  aria-disabled={moveFromDisabled}
                >
                  <span className="sheet-tab-menu-label">{t('contextMoveHereFrom')}</span>
                  <span className="sheet-tab-menu-caret">▸</span>
                  {!moveFromDisabled && submenu === 'moveFrom' && (
                    <div className="sheet-tab-submenu" onMouseDown={e => e.stopPropagation()}>
                      {sheetsWithPieces.map(s => (
                        <button
                          key={s.id}
                          className="sheet-tab-menu-item"
                          onClick={() => { setMenuPos(null); setSubmenu(null); onMoveAllFromSrc(s.id); }}
                        >
                          <span className="sheet-tab-menu-label">{s.label}</span>
                          <span className="sheet-tab-menu-count">({pieceCountBySheet[s.id] ?? 0})</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </>
            );
          })()}

          {canDelete && (
            <button
              className="sheet-tab-menu-item sheet-tab-menu-item-danger"
              onClick={() => { setMenuPos(null); onDelete(); }}
              onMouseEnter={() => setSubmenu(null)}
            >
              {t('contextDelete')}
            </button>
          )}
        </div>
      )}
    </>
  );
}

function PenStatusDisplay({ store, active, scale }: { store: PenStatusStore; active: boolean; scale: Scale | null }) {
  const { t } = useTranslation();
  const status = usePenStatus(store);
  if (!active || !status.coords) return null;
  const dx = status.lastPoint ? status.coords.x - status.lastPoint.x : 0;
  const dy = status.lastPoint ? status.coords.y - status.lastPoint.y : 0;
  const lengthPx = status.lastPoint ? Math.hypot(dx, dy) : null;
  let angle = Math.round((Math.atan2(-dy, dx) * 180) / Math.PI);
  if (angle < 0) angle += 360;
  return <>
    <span className="status-bar-divider" />
    <span>{t('statusPenPosition')}: {status.coords.x.toFixed(0)}, {status.coords.y.toFixed(0)} px{scale && scale.pxPerUnit > 0 ? ` (${(status.coords.x / scale.pxPerUnit).toFixed(1)} × ${(status.coords.y / scale.pxPerUnit).toFixed(1)} ${t('unit_' + scale.unit)})` : ''}</span>
    {lengthPx !== null && <><span className="status-bar-divider" /><span>{t('statusPenLength')}: {lengthPx.toFixed(0)} px{scale && scale.pxPerUnit > 0 ? ` (${(lengthPx / scale.pxPerUnit).toFixed(1)} ${t('unit_' + scale.unit)})` : ''}</span><span className="status-bar-divider" /><span>{t('statusPenAngle')}: {angle}°</span></>}
  </>;
}

function PatternDimensionsEditor({ project, onUpdateDimensions }: { project: Project; onUpdateDimensions: (width: number, height: number) => void }) {
  const [editing, setEditing] = useState(false);
  const scale = project.patternScale;
  const hasScale = Boolean(scale && scale.pxPerUnit > 0);
  const unit = hasScale ? scale!.unit : 'px';

  const activeWidthPx = Math.max(1, project.patternWidth - project.patternCrop.left - project.patternCrop.right);
  const activeHeightPx = Math.max(1, project.patternHeight - project.patternCrop.top - project.patternCrop.bottom);

  const displayW = hasScale ? Number((activeWidthPx / scale!.pxPerUnit).toFixed(1)) : Math.round(activeWidthPx);
  const displayH = hasScale ? Number((activeHeightPx / scale!.pxPerUnit).toFixed(1)) : Math.round(activeHeightPx);

  const [draftW, setDraftW] = useState(String(displayW));
  const [draftH, setDraftH] = useState(String(displayH));

  useEffect(() => {
    if (!editing) {
      setDraftW(String(displayW));
      setDraftH(String(displayH));
    }
  }, [displayW, displayH, editing]);

  const commit = () => {
    const wVal = parseFloat(draftW);
    const hVal = parseFloat(draftH);
    if (!isNaN(wVal) && !isNaN(hVal) && wVal > 0 && hVal > 0) {
      const finalW = hasScale ? wVal * scale!.pxPerUnit : wVal;
      const finalH = hasScale ? hVal * scale!.pxPerUnit : hVal;
      onUpdateDimensions(finalW, finalH);
    } else {
      setDraftW(String(displayW));
      setDraftH(String(displayH));
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: '#ffffff', border: '1px solid var(--hairline-2)', borderRadius: 4, padding: '1px 5px', fontSize: 11 }}>
        <input
          type="number"
          step={hasScale ? '0.1' : '1'}
          value={draftW}
          onChange={e => setDraftW(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false); }}
          autoFocus
          style={{ width: 44, border: 'none', background: 'transparent', textAlign: 'right', fontSize: 11, padding: 0, outline: 'none', color: 'inherit' }}
        />
        <span style={{ color: 'var(--text-dim)' }}>×</span>
        <input
          type="number"
          step={hasScale ? '0.1' : '1'}
          value={draftH}
          onChange={e => setDraftH(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false); }}
          style={{ width: 44, border: 'none', background: 'transparent', textAlign: 'left', fontSize: 11, padding: 0, outline: 'none', color: 'inherit' }}
        />
        <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>{unit}</span>
        <button
          onClick={commit}
          style={{ border: 'none', background: '#292524', color: '#ffffff', borderRadius: 3, padding: '1px 5px', fontSize: 10, cursor: 'pointer', marginLeft: 2 }}
        >
          ✓
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setEditing(true)}
      title="Click to resize canvas / artboard"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 3,
        background: 'transparent',
        border: '1px solid transparent',
        borderRadius: 4,
        padding: '1px 5px',
        color: 'var(--text-dim)',
        fontSize: 11,
        fontFamily: 'inherit',
        cursor: 'pointer',
        transition: 'background 0.1s, border-color 0.1s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = 'var(--chrome-700)';
        e.currentTarget.style.borderColor = 'var(--hairline)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = 'transparent';
        e.currentTarget.style.borderColor = 'transparent';
      }}
    >
      <span>{displayW} × {displayH} {unit}</span>
      <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ opacity: 0.6 }}>
        <path d="M11 2l3 3-9 9H2v-3l9-9z" />
      </svg>
    </button>
  );
}

export function App() {
  const { t, i18n } = useTranslation();
  const [pieceTransformPreviewStore] = useState(() => new PieceTransformPreviewStore());
  const [penStatusStore] = useState(() => new PenStatusStore());
  const {
    project,
    isLoaded,
    selectedPieceIds,
    activeSheetId,
    pendingPieceIds,
    setActiveSheetId,
    selectPiece,
    selectPieces,
    updatePieceTransform,
    commitPieceTransforms,
    updatePatternCrop,
    updatePatternScale,
    updateSheetCrop,
    updateSheetScale,
    deletePiece,
    deletePieces,
    updatePieceLabel,
    updatePieceSheet,
    updatePiecesSheet,
    deleteSheet,
    renameSheet,
    updateSheetSwatch,
    addSheetAndAssignPiece,
    addSheetAndAssignPieces,
    addPieceFromBox,
    addManualPiece,
    updateSheetDimensions,
    batchAddPieces,
    updatePieceCurves,
    updatePiecePolygonAndCurves,
    addPiecePromptPoint,
    markPiecePending,
    unmarkPiecePending,
    updateSolderWidthMM,
    updateSolderColor,
    undo,
    redo,
    canUndo,
    canRedo,
    loadProjectData,
    updatePatternImage,
    updatePatternDimensions,
    startBlankCanvas,
    startLampMode,
    addSheetFromImage,
    moveAllPiecesBetweenSheets,
    addSheetFromImageAndMovePieces,
    updateLampConfig,
    availableProjects,
    setProjectName,
    createNewProject,
    switchProject,
    deleteProject,
    saveStatus,
    retrySave,
    isSymmetryEnabled,
    setIsSymmetryEnabled,
  } = useProject();

  // Always-current project, for async handlers that resolve after re-renders.
  const projectRef = useRef(project);
  projectRef.current = project;

  useEffect(() => {
    pieceTransformPreviewStore.reconcile(project.pieces);
  }, [pieceTransformPreviewStore, project.pieces]);

  useEffect(() => {
    pieceTransformPreviewStore.cancelAll();
  }, [pieceTransformPreviewStore, project.name]);

  useEffect(() => () => pieceTransformPreviewStore.cancelAll(), [pieceTransformPreviewStore]);

  const [backendStatus, setBackendStatus] = useState('');
  const [downloadProgress, setDownloadProgress] = useState<number | null>(null);

  useEffect(() => {
    let lastUpdate = 0;
    const backend = getSamBackend(setBackendStatus);
    backend.onProgress = (fraction) => {
      const now = Date.now();
      if (fraction >= 1 || now - lastUpdate > 250) {
        lastUpdate = now;
        setDownloadProgress(fraction);
        if (fraction >= 1) {
          setTimeout(() => setDownloadProgress(null), 500);
        }
      }
    };
  }, []);

  const [tutorialStep, setTutorialStep] = useState<StepId | null>(null);
  const [tutorialActiveTrackId, setTutorialActiveTrackId] = useState<TrackId | null>(null);
  const [tutorialPieceId, setTutorialPieceId] = useState<string | null>(null);
  const [patternTool, setPatternTool] = useState<ToolId>('select');
  const [sheetTool, setSheetTool] = useState<ToolId>('select');
  const [patternRefineMode, setPatternRefineMode] = useState<'add' | 'remove' | null>(null);
  const tutorialLoadedRef = useRef(false);
  const preTutorialProjectRef = useRef<string | null>(null);

  useEffect(() => {
    // Wait for the OPFS project load before deciding whether to show the
    // welcome tutorial — at mount `project` is still the empty placeholder,
    // so a returning user with saved work (but cleared localStorage) would
    // be dumped into the tutorial on top of their project.
    if (!isLoaded || tutorialLoadedRef.current) return;
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as PersistedTutorialState;
        if (!parsed.completed && parsed.step) {
          preTutorialProjectRef.current = parsed.previousProjectName ?? null;
          const track = parsed.activeTrackId;
          if (track && TRACK_STEPS[track]?.includes(parsed.step) && project.name === 'Tutorial') {
            setTutorialStep(parsed.step === 'lamp-edit-profile' ? 'lamp-profile-intro' : parsed.step);
            setTutorialActiveTrackId(track);
            setTutorialPieceId(parsed.pieceId);
            if (track === 'lamp-creator' && ['lamp-choose-pen', 'lamp-draw-facet', 'lamp-preview-3d'].includes(parsed.step)) {
              setIsSymmetryEnabled(true);
            }
          } else {
            setTutorialStep('welcome');
          }
        }
      } else {
        const hasWork = project.pieces.length > 0 || (project.patternScale && project.patternScale.pxPerUnit > 0);
        if (!hasWork) {
          setTutorialStep('welcome');
        }
      }
    } catch (e) {
      console.error('[Tutorial] failed to load state', e);
    } finally {
      tutorialLoadedRef.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoaded]);

  useEffect(() => {
    if (tutorialStep && tutorialStep !== 'welcome' && project.name !== 'Tutorial') {
      setTutorialStep(null);
      setTutorialActiveTrackId(null);
      setTutorialPieceId(null);
    }
  }, [project.name, tutorialStep]);

  const startTutorialTour = async (trackId?: TrackId) => {
    if (project.name !== 'Tutorial') preTutorialProjectRef.current = project.name;
    setPatternTool('select');
    setSheetTool('select');
    setIsSymmetryEnabled(false);
    setPatternRefineMode(null);
    setLampProfileDialog(null);
    if (!trackId) {
      setTutorialStep('welcome');
      setTutorialActiveTrackId(null);
      setTutorialPieceId(null);
      return;
    }
    setTutorialActiveTrackId(trackId);

    // Setup initial project state based on trackId
    if (trackId === 'ai-tracing') {
      await loadProjectData({ ...DEFAULT_PROJECT, name: 'Tutorial', sheets: DEFAULT_PROJECT.sheets.map(sheet => ({
        ...sheet,
        scale: sheet.scale ?? { pxPerUnit: (2058.347 - 764.712) / 12, unit: 'in', line: { x1: 764.712, y1: 768, x2: 2058.347, y2: 768 } },
      })) });
      setTutorialStep('calibrate-pattern');
    } else if (trackId === 'vector-drawing') {
      // Blank canvas project
      await loadProjectData({
        version: DEFAULT_PROJECT.version,
        name: 'Tutorial',
        patternImageUrl: '',
        patternWidth: 1000,
        patternHeight: 1000,
        patternCrop: { top: 0, left: 0, bottom: 0, right: 0 },
        patternScale: {
          pxPerUnit: 100,
          unit: 'in',
          line: { x1: 0, y1: 500, x2: 1000, y2: 500 },
        },
        pieces: [],
        sheets: [
          {
            id: 'default-sheet-1',
            label: 'Default Glass (Green)',
            imageUrl: '/assets/glass/green.jpg',
            crop: { top: 0, left: 0, bottom: 0, right: 0 },
            scale: { pxPerUnit: 800 / 12, unit: 'in', line: { x1: 0, y1: 400, x2: 800, y2: 400 } },
            naturalWidth: 800,
            naturalHeight: 800,
            swatch: '#a5d6a7'
          },
          {
            id: 'default-sheet-2',
            label: 'Cobalt Blue',
            imageUrl: '/assets/glass/blue.jpg',
            crop: { top: 0, left: 0, bottom: 0, right: 0 },
            scale: { pxPerUnit: 800 / 12, unit: 'in', line: { x1: 0, y1: 400, x2: 800, y2: 400 } },
            naturalWidth: 800,
            naturalHeight: 800,
            swatch: '#1e88e5'
          }
        ]
      });
      setTutorialStep('vector-blank-canvas');
    } else if (trackId === 'lamp-creator') {
      // 3D Lamp Creator template
      await loadProjectData({
        version: DEFAULT_PROJECT.version,
        name: 'Tutorial',
        projectType: 'lamp',
        lampConfig: {
          facetCount: 6,
          profilePoints: [
            { r: 50, y: 0 },
            { r: 100, y: 80 },
            { r: 100, y: 140 },
          ],
          activeTierIndex: 0,
        },
        patternImageUrl: '',
        patternWidth: 1000,
        patternHeight: 1000,
        patternCrop: { top: 0, left: 0, bottom: 0, right: 0 },
        patternScale: {
          pxPerUnit: 10,
          unit: 'in',
          line: { x1: 0, y1: 0, x2: 100, y2: 0 }
        },
        pieces: [],
        sheets: [
          {
            id: 'default-sheet-1',
            label: 'Cobalt Blue Glass Sheet',
            imageUrl: '/assets/glass/blue.jpg',
            crop: { top: 0, left: 0, bottom: 0, right: 0 },
            scale: { pxPerUnit: 800 / 12, unit: 'in', line: { x1: 0, y1: 400, x2: 800, y2: 400 } },
            naturalWidth: 800,
            naturalHeight: 800,
            swatch: '#1e88e5'
          }
        ]
      });
      setTutorialStep('lamp-profile-intro');
    } else if (trackId === 'fabrication') {
      // Fabrication layout and nesting template
      await loadProjectData({
        version: DEFAULT_PROJECT.version,
        name: 'Tutorial',
        patternImageUrl: '',
        patternWidth: 1000,
        patternHeight: 1000,
        patternCrop: { top: 0, left: 0, bottom: 0, right: 0 },
        patternScale: {
          pxPerUnit: 100,
          unit: 'in',
          line: { x1: 0, y1: 0, x2: 100, y2: 0 }
        },
        pieces: [
          {
            id: 'p1',
            label: 'Petal',
            polygon: [[80, 80], [145, 55], [205, 95], [175, 190], [105, 205], [65, 145]],
            glassSheetId: 'sheet-1',
            transform: { x: 500, y: 180, rotation: 0.35, scale: 2 / 3 }
          },
          {
            id: 'p2',
            label: 'Leaf',
            polygon: [[260, 80], [350, 115], [390, 205], [315, 235], [245, 175]],
            glassSheetId: 'sheet-1',
            transform: { x: 180, y: 430, rotation: -0.5, scale: 2 / 3 }
          },
          {
            id: 'p3',
            label: 'Corner',
            polygon: [[430, 80], [560, 80], [560, 135], [500, 135], [500, 230], [430, 230]],
            glassSheetId: 'sheet-1',
            transform: { x: 600, y: 430, rotation: 0.2, scale: 2 / 3 }
          }
        ],
        sheets: [
          {
            id: 'sheet-1',
            label: 'Cobalt Blue Glass Sheet',
            imageUrl: '/assets/glass/blue.jpg',
            crop: { top: 0, left: 0, bottom: 0, right: 0 },
            scale: {
              pxPerUnit: 800 / 12,
              unit: 'in',
              line: { x1: 0, y1: 400, x2: 800, y2: 400 }
            },
            naturalWidth: 800,
            naturalHeight: 800,
            swatch: '#1e88e5'
          }
        ]
      });
      setTutorialStep('fab-smart-pack');
    }

    setTutorialPieceId(null);
    const state: PersistedTutorialState = {
      step: trackId === 'ai-tracing' ? 'calibrate-pattern' :
            trackId === 'vector-drawing' ? 'vector-blank-canvas' :
            trackId === 'lamp-creator' ? 'lamp-profile-intro' : 'fab-smart-pack',
      activeTrackId: trackId,
      completed: false,
      pieceId: null,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  };

  const skipTutorial = async () => {
    setLampProfileDialog(null);
    setPatternRefineMode(null);
    setPatternTool('select');
    setSheetTool('select');
    setIsSymmetryEnabled(false);
    setTutorialStep(null);
    setTutorialActiveTrackId(null);
    setTutorialPieceId(null);
    const state: PersistedTutorialState = {
      step: null,
      activeTrackId: null,
      completed: true,
      pieceId: null,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    const prev = preTutorialProjectRef.current;
    preTutorialProjectRef.current = null;
    if (prev && prev !== 'Tutorial' && project.name === 'Tutorial') {
      await switchProject(prev);
      await deleteProject('Tutorial');
    }
  };

  const completeTutorial = () => {
    setTutorialStep(null);
    setTutorialActiveTrackId(null);
    setTutorialPieceId(null);
    const state: PersistedTutorialState = {
      step: null,
      activeTrackId: null,
      completed: true,
      pieceId: null,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  };

  const advanceTutorial = () => {
    if (!tutorialStep || !tutorialActiveTrackId) return;
    const trackSteps = TRACK_STEPS[tutorialActiveTrackId];
    if (!trackSteps) return;

    const currentIndex = trackSteps.indexOf(tutorialStep);
    const nextStep = currentIndex >= 0 && currentIndex < trackSteps.length - 1
      ? trackSteps[currentIndex + 1]
      : null;

    setTutorialStep(nextStep);
  };

  const handleSetTrackedPiece = (id: string) => setTutorialPieceId(id);

  useEffect(() => {
    if (!tutorialLoadedRef.current) return;
    const state: PersistedTutorialState = {
      step: tutorialStep,
      activeTrackId: tutorialActiveTrackId,
      completed: tutorialStep === null,
      pieceId: tutorialPieceId,
      previousProjectName: preTutorialProjectRef.current,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [tutorialStep, tutorialActiveTrackId, tutorialPieceId]);



  const [patternImageId, setPatternImageId] = useState<string | null>(null);
  const [isAutoSegmenting, setIsAutoSegmenting] = useState(false);
  const [debugMask, setDebugMaskState] = useState<{ bitmap: ImageBitmap; width: number; height: number } | null>(null);
  const [debugMaskPieceId, setDebugMaskPieceId] = useState<string | null>(null);
  // Close the previous ImageBitmap when replacing it — they pin large
  // buffers and repeated refine clicks accumulate tens of MB otherwise.
  const setDebugMask = (m: { bitmap: ImageBitmap; width: number; height: number } | null) => {
    setDebugMaskState(prev => {
      if (prev && prev.bitmap !== m?.bitmap) prev.bitmap.close();
      return m;
    });
  };
  const [nameDraft, setNameDraft] = useState(project.name);
  const [isProjectDropdownOpen, setIsProjectDropdownOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [pendingMove, setPendingMove] = useState<{ srcId: string; destId: string } | null>(null);
  const [suppressMoveConfirm, setSuppressMoveConfirm] = useState(false);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const [showGlassLibrary, setShowGlassLibrary] = useState(false);
  const [addSheetMenu, setAddSheetMenu] = useState<{ left: number; top: number } | null>(null);

  const [, setFocusedPanelIdx] = useState<number | null>(null);
  const [lampPreviewHeight, setLampPreviewHeight] = useState<number>(320);
  const [lampProfileDialog, setLampProfileDialog] = useState<{ isFirstTime: boolean } | null>(null);
  const isLamp = project.projectType === 'lamp';

  function startLampPreviewResize(e: React.PointerEvent) {
    e.preventDefault();
    const startY = e.clientY;
    const startH = lampPreviewHeight;
    function onMove(ev: PointerEvent) {
      const next = Math.max(120, Math.min(800, startH + (ev.clientY - startY)));
      setLampPreviewHeight(next);
    }
    function onUp() {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    }
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }
  const moveSourceSheetIdRef = useRef<string | null>(null);
  const newSheetFileInputRef = useRef<HTMLInputElement>(null);
  const projectDropdownRef = useRef<HTMLDivElement>(null);
  const projectNameInputRef = useRef<HTMLInputElement>(null);

  const pieceCountBySheet = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const s of project.sheets) counts[s.id] = 0;
    for (const p of project.pieces) {
      counts[p.glassSheetId] = (counts[p.glassSheetId] ?? 0) + 1;
    }
    return counts;
  }, [project.sheets, project.pieces]);

  useEffect(() => { setNameDraft(project.name); }, [project.name]);

  // Ensure each glass sheet has a precomputed swatch (used to color its tab).
  useEffect(() => {
    let cancelled = false;
    project.sheets.forEach(sheet => {
      if (sheet.swatch || !sheet.imageUrl) return;
      computeImageSwatch(sheet.imageUrl)
        .then(hex => { if (!cancelled) updateSheetSwatch(sheet.id, hex); })
        .catch(err => console.warn('[swatch] failed for sheet', sheet.id, err));
    });
    return () => { cancelled = true; };
  }, [project.sheets, updateSheetSwatch]);

  useEffect(() => {
    if (!isProjectDropdownOpen) return;
    function handleOutsideClick(e: MouseEvent) {
      if (projectDropdownRef.current && !projectDropdownRef.current.contains(e.target as Node)) {
        setIsProjectDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [isProjectDropdownOpen]);

  useEffect(() => {
    if (debugMaskPieceId && !project.pieces.some(p => p.id === debugMaskPieceId)) {
      setDebugMask(null);
      setDebugMaskPieceId(null);
    }
  }, [project.pieces, debugMaskPieceId]);

  // Re-encode whenever the pattern image changes.
  useEffect(() => {
    setPatternImageId(null);
    if (!project.patternImageUrl) {
      setBackendStatus(t('statusNoPatternImage', 'No pattern image uploaded'));
      return;
    }
    const backend = getSamBackend(setBackendStatus);
    let cancelled = false;
    backend.encode(project.patternImageUrl)
      .then(id => { if (!cancelled) setPatternImageId(id); })
      .catch(err => { console.error("[App] SAM encode failed:", err); });
    return () => { cancelled = true; };
  }, [project.patternImageUrl]);

  async function handleAutoSegment() {
    if (!patternImageId) return;
    setIsAutoSegmenting(true);
    try {
      const polygons = await getSamBackend().autoSegment(patternImageId);
      batchAddPieces(polygons, activeSheetId);
    } catch (e) {
      console.error("Auto segment failed:", e);
    } finally {
      setIsAutoSegmenting(false);
    }
  }

  async function handleAddPiece(box: BoundingBox, tierIndex?: number) {
    const pieceId = addPieceFromBox(box, activeSheetId, tierIndex);
    if (!patternImageId) return;
    markPiecePending(pieceId);
    try {
      const { polygon, debugMask } = await getSamBackend().segment(patternImageId, box);
      if (debugMask) { setDebugMask(debugMask); setDebugMaskPieceId(pieceId); }
      // Read neighbors through the ref, not the render-time snapshot: another
      // segmentation may have finished while this one was awaiting, and
      // clipping against its pre-segment polygon would leave the two pieces
      // overlapping.
      const latest = projectRef.current;
      const others = latest.pieces.filter(p => p.id !== pieceId);
      const neighborPolygons = others.map(p => flattenCurves(p.polygon, p.curvePoints));
      const snapRadius = getSnapRadius(latest.patternWidth);
      const snapped = snapPolygonToNeighbors(polygon, neighborPolygons, snapRadius);
      const clipped = subtractPolygons(snapped, neighborPolygons);
      // skipHistory: collapse with the parent addPieceFromBox action so one Cmd+Z reverts both
      if (clipped.length >= 3) {
        const fitted = fitSmoothPieceCurves(clipped, neighborPolygons, {
          cornerAngleDeg: 40,
          seamTolerancePx: Math.max(2.5, snapRadius * 0.25),
        });
        updatePiecePolygonAndCurves(pieceId, fitted.polygon, fitted.curvePoints, true, fitted.anchorTypes);
      }
    } catch (e) {
      console.error("SAM segment failed:", e);
    } finally {
      unmarkPiecePending(pieceId);
    }
  }

  function handleAddManualPiece(
    polygon: [number, number][],
    curvePoints: CurvePoint[] = [],
    anchorTypes: ('corner' | 'smooth')[] = [],
    tierIndex?: number,
  ) {
    const others = project.pieces;
    const neighborPolygons = others.map(p => flattenCurves(p.polygon, p.curvePoints));
    const displayPolygon = flattenCurves(polygon, curvePoints);
    // Curved paths are already snapped interactively at their true anchors.
    // Snapping dense curve samples here would destroy their editable controls.
    const snapped = curvePoints.length > 0
      ? displayPolygon
      : snapPolygonToNeighbors(polygon, neighborPolygons, getSnapRadius(project.patternWidth));
    const clipped = subtractPolygons(snapped, neighborPolygons);
    if (clipped.length >= 3) {
      const keptCurves = curvePoints.length > 0 && arePolygonsEqual(displayPolygon, clipped, 0.1);
      addManualPiece(
        keptCurves ? polygon : clipped,
        activeSheetId,
        tierIndex,
        keptCurves ? curvePoints : [],
        keptCurves ? anchorTypes : [],
      );
    }
  }

  async function handleUpdatePrompt(pieceId: string, point: { x: number; y: number; label: 1 | 0 }) {
    addPiecePromptPoint(pieceId, point);

    // Read through the ref so rapid refine clicks build on the freshest
    // prompt-point list — a stale render snapshot here would silently drop
    // the previous click's point from the request.
    const piece = projectRef.current.pieces.find(p => p.id === pieceId);
    if (!piece || !patternImageId) return;

    const newPoints = [...(piece.promptPoints || []), point];

    markPiecePending(pieceId);
    try {
      const { polygon, debugMask } = await getSamBackend().segment(patternImageId, piece.promptBox, newPoints);
      if (debugMask) { setDebugMask(debugMask); setDebugMaskPieceId(pieceId); }
      const latest = projectRef.current;
      const others = latest.pieces.filter(p => p.id !== pieceId);
      const neighborPolygons = others.map(p => flattenCurves(p.polygon, p.curvePoints));
      const snapRadius = getSnapRadius(latest.patternWidth);
      const snapped = snapPolygonToNeighbors(polygon, neighborPolygons, snapRadius);
      const clipped = subtractPolygons(snapped, neighborPolygons);
      // Re-fit smooth curves on the refined contour while keeping shared seams locked.
      // skipHistory: collapse with the parent addPiecePromptPoint action so one Cmd+Z reverts both.
      if (clipped.length >= 3) {
        const fitted = fitSmoothPieceCurves(clipped, neighborPolygons, {
          cornerAngleDeg: 40,
          seamTolerancePx: Math.max(2.5, snapRadius * 0.25),
        });
        updatePiecePolygonAndCurves(pieceId, fitted.polygon, fitted.curvePoints, true, fitted.anchorTypes);
      }
    } catch (e) {
      console.error(e);
    } finally {
      unmarkPiecePending(pieceId);
    }
  }

  function handleSmoothPiece(pieceId: string) {
    handleSmoothPieces([pieceId]);
  }

  function handleSmoothPieces(pieceIds: string[]) {
    const snapRadius = getSnapRadius(projectRef.current.patternWidth);
    const seamTol = Math.max(2.5, snapRadius * 0.25);
    // Pass 1: Snap & clip target pieces against neighbors so both sides of every joint meet flush
    pieceIds.forEach(id => {
      const latest = projectRef.current;
      const piece = latest.pieces.find(p => p.id === id);
      if (!piece) return;
      const neighborPolygons = latest.pieces
        .filter(p => p.id !== id)
        .map(p => flattenCurves(p.polygon, p.curvePoints));
      const dense = flattenCurves(piece.polygon, piece.curvePoints, 0.5);
      const snapped = snapPolygonToNeighbors(dense, neighborPolygons, snapRadius);
      const clipped = subtractPolygons(snapped, neighborPolygons);
      if (clipped.length >= 3) {
        updatePiecePolygonAndCurves(id, clipped, [], true);
      }
    });

    // Pass 2: Fit smooth cubic Béziers while keeping all snapped neighbor seams locked
    pieceIds.forEach((id, idx) => {
      const latest = projectRef.current;
      const piece = latest.pieces.find(p => p.id === id);
      if (!piece) return;
      const neighborPolygons = latest.pieces
        .filter(p => p.id !== id)
        .map(p => flattenCurves(p.polygon, p.curvePoints));
      const smoothed = smoothPieceGeometry(piece.polygon, [], neighborPolygons, seamTol);
      updatePiecePolygonAndCurves(
        id,
        smoothed.polygon,
        smoothed.curvePoints,
        idx < pieceIds.length - 1,
        smoothed.anchorTypes,
      );
    });
  }

  function handleStraightenPiece(pieceId: string) {
    handleStraightenPieces([pieceId]);
  }

  function handleStraightenPieces(pieceIds: string[]) {
    pieceIds.forEach((id, idx) => {
      const latest = projectRef.current;
      const piece = latest.pieces.find(p => p.id === id);
      if (!piece) return;
      updatePiecePolygonAndCurves(
        id,
        piece.polygon,
        [],
        idx < pieceIds.length - 1,
        piece.polygon.map(() => 'corner' as const),
      );
    });
  }

  function constrainEditedPieceGeometry(
    pieceId: string,
    polygon: [number, number][],
    curvePoints: CurvePoint[],
    anchorTypes?: ('corner' | 'smooth')[],
    overrideNeighbors?: [number, number][][],
  ) {
    const latest = projectRef.current;
    const neighborPolygons = overrideNeighbors ?? latest.pieces
      .filter(piece => piece.id !== pieceId)
      .map(piece => flattenCurves(piece.polygon, piece.curvePoints));
    const displayPolygon = flattenCurves(polygon, curvePoints);
    const clipped = subtractPolygons(displayPolygon, neighborPolygons);
    if (clipped.length < 3) return null;

    // Preserve editable Bézier metadata when the proposed edit is valid. If
    // it crosses another piece, fall back to the clipped outline: topology may
    // change at the intersection, so the old control-point indices no longer
    // describe the resulting boundary.
    if (arePolygonsEqual(displayPolygon, clipped, 0.1)) {
      return { polygon, curvePoints, anchorTypes, clipped: false };
    }
    return { polygon: clipped, curvePoints: [] as CurvePoint[], anchorTypes: undefined, clipped: true };
  }

  function handleUpdatePieceCurves(pieceId: string, curvePoints: CurvePoint[], anchorTypes?: ('corner' | 'smooth')[]) {
    const piece = projectRef.current.pieces.find(candidate => candidate.id === pieceId);
    if (!piece) return;
    const constrained = constrainEditedPieceGeometry(pieceId, piece.polygon, curvePoints, anchorTypes);
    if (!constrained) return;
    if (!constrained.clipped) {
      updatePieceCurves(pieceId, curvePoints, false, anchorTypes);
      return;
    }
    updatePiecePolygonAndCurves(pieceId, constrained.polygon, constrained.curvePoints, false);
  }

  function handleUpdatePieceGeometry(
    pieceId: string,
    polygon: [number, number][],
    curvePoints: CurvePoint[],
    anchorTypes?: ('corner' | 'smooth')[],
    coupledMove?: { origin: [number, number]; target: [number, number] },
  ) {
    const latest = projectRef.current;
    const coupledUpdates: { id: string; polygon: [number, number][]; curvePoints: CurvePoint[]; anchorTypes?: ('corner' | 'smooth')[] }[] = [];

    if (coupledMove) {
      const [ox, oy] = coupledMove.origin;
      const [tx, ty] = coupledMove.target;
      const delta: [number, number] = [tx - ox, ty - oy];
      if (Math.hypot(delta[0], delta[1]) > 1e-3) {
        for (const other of latest.pieces) {
          if (other.id === pieceId) continue;
          const vIdx = other.polygon.findIndex(([vx, vy]) => Math.hypot(vx - ox, vy - oy) <= 2.5);
          if (vIdx >= 0) {
            const nextPoly = [...other.polygon];
            nextPoly[vIdx] = [tx, ty];
            const nextCurves = translateCurvesWithAnchor(
              other.curvePoints ?? [],
              vIdx,
              other.polygon.length,
              delta,
            );
            coupledUpdates.push({
              id: other.id,
              polygon: nextPoly,
              curvePoints: nextCurves,
              anchorTypes: other.anchorTypes,
            });
          }
        }
      }
    }

    const updatedNeighborPolygons = latest.pieces
      .filter(p => p.id !== pieceId)
      .map(p => {
        const coupled = coupledUpdates.find(u => u.id === p.id);
        return coupled
          ? flattenCurves(coupled.polygon, coupled.curvePoints)
          : flattenCurves(p.polygon, p.curvePoints);
      });

    const constrained = constrainEditedPieceGeometry(
      pieceId,
      polygon,
      curvePoints,
      anchorTypes,
      updatedNeighborPolygons,
    );
    if (!constrained) return;

    for (const u of coupledUpdates) {
      updatePiecePolygonAndCurves(u.id, u.polygon, u.curvePoints, true, u.anchorTypes);
    }
    updatePiecePolygonAndCurves(
      pieceId,
      constrained.polygon,
      constrained.curvePoints,
      false,
      constrained.anchorTypes,
    );
  }


  const activeSheet = useMemo(
    () => project.sheets.find(s => s.id === activeSheetId) ?? project.sheets[0],
    [project.sheets, activeSheetId],
  );
  const piecesOnActiveSheet = useMemo(() => {
    const selected = new Set(selectedPieceIds);
    return project.pieces
      .filter(p => p.glassSheetId === activeSheetId)
      .sort((a, b) => Number(selected.has(a.id)) - Number(selected.has(b.id)));
  }, [project.pieces, activeSheetId, selectedPieceIds]);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLSelectElement) return;

      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        setIsShortcutsOpen(o => !o);
        return;
      }

      const isMod = e.ctrlKey || e.metaKey;
      if (isMod && e.key === 'Enter') {
        e.preventDefault();
        if (printRef.current.ready) printRef.current.fn();
        return;
      }
      // Compare lowercase: Shift (Cmd+Shift+Z) and Caps Lock both make
      // e.key uppercase, which used to leave the redo branch unreachable.
      if (isMod && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
        return;
      }
      if (isMod && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        redo();
        return;
      }

      if (selectedPieceIds.length === 0) return;
      if (e.key === 'Delete' || e.key === 'Backspace') {
        deletePieces(selectedPieceIds);
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedPieceIds, deletePieces, undo, redo]);

  // Validates/migrates/repairs a just-parsed project file (see
  // storage/projectSchema.ts) and either loads it — surfacing a warning if
  // anything had to be dropped — or refuses it with an explanatory alert.
  const handleProjectFileData = (data: unknown) => {
    const result = parseProject(data);
    if (!result.ok) {
      alert(t(result.reasonKey));
      return;
    }
    loadProjectData(result.project);
    if (result.repairs.length > 0) {
      const details = result.repairs.map(r => t(r.reasonKey, { path: r.path })).join('\n');
      alert(t('schemaRepairWarning', { details }));
    }
  };

  const handleLoadProject = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target?.result as string);
        handleProjectFileData(data);
      } catch (err) {
        console.error(err);
        alert(t('invalidProject'));
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleSaveProject = () => {
    // Blob instead of a data: URI — projects embed base64 images and easily
    // exceed browser URL length limits.
    const blob = new Blob([JSON.stringify(project)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${project.name}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  };

  const loadPatternImageFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      const img = new Image();
      img.onload = () => {
        updatePatternImage(dataUrl, img.width, img.height);
      };
      img.src = dataUrl;
    };
    reader.readAsDataURL(file);
  };

  const handleUploadPattern = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      loadPatternImageFile(file);
      setPatternTool('select');
    }
  };

  const handleStartLampMode = () => {
    startLampMode();
    setLampProfileDialog({ isFirstTime: true });
  };

  const isPrintReady = !!project.patternScale && project.patternScale.pxPerUnit > 0 && project.pieces.length > 0;
  const printNotReadyReason = !project.patternScale || project.patternScale.pxPerUnit === 0
    ? t('printNoScale')
    : project.pieces.length === 0
      ? t('printNoPieces')
      : '';

  const printRef = useRef<{ ready: boolean; fn: () => void }>({ ready: false, fn: () => {} });

  const handlePrint = () => {
    if (!isPrintReady) return;
    const { patternScale, pieces } = project;
    if (!patternScale || patternScale.pxPerUnit === 0) return;
    if (pieces.length === 0) return;

    const pxPerUnit = patternScale.pxPerUnit;
    const unit = patternScale.unit;

    // Convert scale to px/mm for physical joint-allowance & page-size math
    let pxPerMm: number;
    if (unit === 'mm') pxPerMm = pxPerUnit;
    else if (unit === 'cm') pxPerMm = pxPerUnit / 10;
    else pxPerMm = pxPerUnit / 25.4;

    const snapRadius = getSnapRadius(project.patternWidth);
    const seamTol = Math.max(2.5, snapRadius * 0.25);

    // Build sequential seam-healed & curve-fitted geometry so even legacy/un-curved
    // projects print with flush solder joints and smooth cubic Bézier contours.
    const workingPieces = pieces.map(p => ({
      ...p,
      polygon: [...p.polygon],
      curvePoints: p.curvePoints ? [...p.curvePoints] : [],
    }));

    // Sequentially smooth & snap each piece against already-smoothed preceding pieces
    // so every shared solder seam has a single canonical smooth curve on both sides.
    for (let i = 0; i < workingPieces.length; i++) {
      const target = workingPieces[i];
      if (target.curvePoints && target.curvePoints.length > 0) continue;
      const precedingPolys = workingPieces
        .slice(0, i)
        .map(p => flattenCurves(p.polygon, p.curvePoints, 0.25));
      const snapped = snapPolygonToNeighbors(target.polygon, precedingPolys, snapRadius);
      const clipped = subtractPolygons(snapped, precedingPolys);
      const basePoly = clipped.length >= 3 ? clipped : target.polygon;
      const fitted = smoothPieceGeometry(basePoly, [], precedingPolys, seamTol);
      workingPieces[i] = {
        ...target,
        polygon: fitted.polygon,
        curvePoints: fitted.curvePoints,
      };
    }

    const buildInsetSvgPath = (
      poly: [number, number][],
      curves: CurvePoint[],
      insetMm: number,
    ): string => {
      if (insetMm <= 0) {
        return pieceToSvgPath(poly, curves);
      }
      const dense = flattenCurves(poly, curves, 0.15);
      const insetPts = insetPolygon(dense, insetMm * pxPerMm);
      return pieceToSvgPath(insetPts, []);
    };

    const solderWidthMm = project.solderWidthMM ?? 4.5;
    const solderInsetMm = Number((solderWidthMm / 2).toFixed(2));

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    workingPieces.forEach(piece => {
      const displayPoly = flattenCurves(piece.polygon, piece.curvePoints, 0.25);
      displayPoly.forEach(pt => {
        if (pt[0] < minX) minX = pt[0];
        if (pt[1] < minY) minY = pt[1];
        if (pt[0] > maxX) maxX = pt[0];
        if (pt[1] > maxY) maxY = pt[1];
      });
    });

    // Reserve bottom margin for the 1:1 physical verification scale bar
    const marginPx = Math.max(pxPerMm * 12, pxPerUnit * 0.45);
    const bottomRulerReservePx = pxPerMm * 18;
    minX -= marginPx;
    minY -= marginPx;
    maxX += marginPx;
    maxY += marginPx + bottomRulerReservePx;

    const printWidth = maxX - minX;
    const printHeight = maxY - minY;

    const sheetIndexMap = new Map<string, number>();
    project.sheets.forEach((s, idx) => sheetIndexMap.set(s.id, idx + 1));

    const serializedPieces = pieces.map((rawPiece, idx) => {
      const fairPiece = workingPieces[idx];
      const fairDense = flattenCurves(fairPiece.polygon, fairPiece.curvePoints, 0.25);
      const centroid = computeCentroid(fairDense);
      let bMinX = Infinity, bMinY = Infinity, bMaxX = -Infinity, bMaxY = -Infinity;
      for (const [px, py] of fairDense) {
        if (px < bMinX) bMinX = px;
        if (py < bMinY) bMinY = py;
        if (px > bMaxX) bMaxX = px;
        if (py > bMaxY) bMaxY = py;
      }
      const minSpan = Math.min(bMaxX - bMinX, bMaxY - bMinY);
      const grainAngleDeg = Number(((-(rawPiece.transform?.rotation ?? 0) * 180) / Math.PI).toFixed(1));
      const sheetNum = sheetIndexMap.get(rawPiece.glassSheetId) ?? 1;

      return {
        num: idx + 1,
        sheetNum,
        cx: Number(centroid.x.toFixed(2)),
        cy: Number(centroid.y.toFixed(2)),
        minSpan: Number(minSpan.toFixed(1)),
        grainAngleDeg,
        fair: {
          d0: buildInsetSvgPath(fairPiece.polygon, fairPiece.curvePoints ?? [], 0),
          dFoil: buildInsetSvgPath(fairPiece.polygon, fairPiece.curvePoints ?? [], 0.5),
          dCame: buildInsetSvgPath(fairPiece.polygon, fairPiece.curvePoints ?? [], 1.0),
          dSolder: buildInsetSvgPath(fairPiece.polygon, fairPiece.curvePoints ?? [], solderInsetMm),
        },
        raw: {
          d0: buildInsetSvgPath(rawPiece.polygon, rawPiece.curvePoints ?? [], 0),
          dFoil: buildInsetSvgPath(rawPiece.polygon, rawPiece.curvePoints ?? [], 0.5),
          dCame: buildInsetSvgPath(rawPiece.polygon, rawPiece.curvePoints ?? [], 1.0),
          dSolder: buildInsetSvgPath(rawPiece.polygon, rawPiece.curvePoints ?? [], solderInsetMm),
        },
      };
    });

    const printWin = window.open('', '_blank');
    if (!printWin) return;

    const payloadJson = JSON.stringify({
      projectName: project.name || 'Vitrai Pattern',
      patternImageUrl: project.patternImageUrl || '',
      patternWidth: project.patternWidth,
      patternHeight: project.patternHeight,
      minX,
      minY,
      printWidth,
      printHeight,
      pxPerUnit,
      unit,
      pxPerMm,
      solderWidthMm,
      solderInsetMm,
      sheetCount: project.sheets.length,
      pieces: serializedPieces,
    });

    printWin.document.write(`<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Print Pattern (1:1) — ${project.name || 'Vitrai'}</title>
    <style>
      :root {
        --bg-stone: #f3efe8;
        --paper: #fcfaf6;
        --ink: #1e1b18;
        --ink-muted: #655e55;
        --brass: #9f6f28;
        --brass-hover: #875c1d;
        --hairline: #ddd5c7;
      }
      * { box-sizing: border-box; }
      body {
        margin: 0;
        padding: 0;
        background: var(--bg-stone);
        color: var(--ink);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
      }
      .studio-bar {
        position: sticky;
        top: 0;
        z-index: 20;
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 12px 20px;
        padding: 12px 20px;
        background: var(--paper);
        border-bottom: 1px solid var(--hairline);
        box-shadow: 0 2px 10px rgba(30, 27, 24, 0.06);
      }
      .studio-brand {
        display: flex;
        align-items: baseline;
        gap: 10px;
      }
      .studio-title {
        font-family: Georgia, "Times New Roman", serif;
        font-size: 16px;
        font-weight: 600;
        letter-spacing: -0.01em;
      }
      .studio-subtitle {
        font-size: 12px;
        color: var(--ink-muted);
      }
      .studio-controls {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 12px 16px;
        font-size: 12.5px;
      }
      .ctrl-group {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .ctrl-label {
        font-weight: 600;
        color: var(--ink-muted);
        text-transform: uppercase;
        font-size: 10.5px;
        letter-spacing: 0.05em;
      }
      select {
        padding: 5px 8px;
        border: 1px solid var(--hairline);
        border-radius: 5px;
        background: #fff;
        color: var(--ink);
        font-size: 12.5px;
        font-weight: 500;
      }
      label.chk {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        cursor: pointer;
        user-select: none;
        color: var(--ink);
      }
      .btn-print {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 7px 14px;
        background: var(--brass);
        color: #fff;
        border: none;
        border-radius: 6px;
        font-size: 12.5px;
        font-weight: 600;
        cursor: pointer;
      }
      .btn-print:hover {
        background: var(--brass-hover);
      }
      .workspace {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 24px;
        padding: 28px 20px 48px;
      }
      .page {
        background: #ffffff;
        box-shadow: 0 4px 20px rgba(30, 27, 24, 0.10);
        border: 1px solid #e2dcd0;
        display: flex;
        justify-content: center;
        align-items: center;
      }
      @media screen {
        .page.single-sheet svg {
          max-width: calc(100vw - 64px);
          max-height: calc(100vh - 140px);
          width: auto;
          height: auto;
        }
      }
      .page + .page {
        page-break-before: always;
        break-before: page;
      }
      @media print {
        .studio-bar { display: none !important; }
        body { background: #ffffff; }
        .workspace { padding: 0; gap: 0; }
        .page { box-shadow: none; border: none; }
      }
    </style>
    <style id="dynamic-page-style"></style>
  </head>
  <body>
    <header class="studio-bar">
      <div class="studio-brand">
        <span class="studio-title">Vitrai 1:1 Fabrication Pattern</span>
        <span class="studio-subtitle" id="summary-meta"></span>
      </div>
      <div class="studio-controls">
        <div class="ctrl-group">
          <span class="ctrl-label">Allowance</span>
          <select id="sel-allowance">
            <option value="foil" selected>Copper Foil — 1.0 mm gap (0.5 mm inset)</option>
            <option value="came">Lead Came — 2.0 mm heart (1.0 mm inset)</option>
            <option value="solder">Solder Width — ${solderWidthMm.toFixed(1)} mm (${solderInsetMm.toFixed(2)} mm inset)</option>
            <option value="zero">Centerline Only — 0 mm inset</option>
          </select>
        </div>
        <div class="ctrl-group">
          <span class="ctrl-label">Paper</span>
          <select id="sel-paper">
            <option value="single" selected>Single Sheet (1:1 Full Size)</option>
            <option value="letter">Letter Tiles (8.5 × 11 in)</option>
            <option value="a4">A4 Tiles (210 × 297 mm)</option>
          </select>
        </div>
        <label class="chk" title="Fit smooth cubic Bézier curves to faceted contours and lock shared solder seams">
          <input type="checkbox" id="chk-smooth" checked />
          Smooth contours
        </label>
        <label class="chk" title="Show dashed solder joint centerlines between inset piece cut lines">
          <input type="checkbox" id="chk-centerlines" checked />
          Joint centerlines
        </label>
        <label class="chk" title="Show glass grain / texture orientation arrow from piece placement on glass sheet">
          <input type="checkbox" id="chk-grain" checked />
          Grain arrows
        </label>
        <label class="chk" title="Show reference pattern photo at 22% opacity">
          <input type="checkbox" id="chk-photo" />
          Reference photo
        </label>
        <button class="btn-print" id="btn-trigger-print" type="button">
          Print / Save PDF
        </button>
      </div>
    </header>
    <main class="workspace" id="pages-root"></main>
    <script>
      const DATA = ${payloadJson};

      function renderPages() {
        const allowance = document.getElementById('sel-allowance').value;
        const paper = document.getElementById('sel-paper').value;
        const useSmooth = document.getElementById('chk-smooth').checked;
        const showCenterlines = document.getElementById('chk-centerlines').checked;
        const showGrain = document.getElementById('chk-grain').checked;
        const showPhoto = document.getElementById('chk-photo').checked;

        const pxPerMm = DATA.pxPerMm;
        const cutStrokeW = Math.max(0.45 * pxPerMm, 1.1);
        const centerStrokeW = Math.max(0.24 * pxPerMm, 0.7);
        const centerDash = (1.6 * pxPerMm).toFixed(2) + ',' + (1.3 * pxPerMm).toFixed(2);
        const fontSize = Math.max(3.6 * pxPerMm, Math.min(6.5 * pxPerMm, DATA.printWidth * 0.042));
        const subFontSize = fontSize * 0.56;

        const wMm = (DATA.printWidth - 2 * Math.max(pxPerMm * 12, DATA.pxPerUnit * 0.45)) / pxPerMm;
        const hMm = (DATA.printHeight - 2 * Math.max(pxPerMm * 12, DATA.pxPerUnit * 0.45) - pxPerMm * 18) / pxPerMm;
        const allowanceLabel = allowance === 'foil'
          ? '0.5 mm foil inset (1.0 mm gap)'
          : allowance === 'came'
            ? '1.0 mm came inset (2.0 mm heart)'
            : allowance === 'solder'
              ? DATA.solderInsetMm + ' mm inset (' + DATA.solderWidthMm + ' mm gap)'
              : '0 mm inset (exact centerline)';

        document.getElementById('summary-meta').textContent =
          DATA.pieces.length + ' pieces · ' + (wMm / 10).toFixed(1) + ' × ' + (hMm / 10).toFixed(1) + ' cm · ' + allowanceLabel;

        const commonStyles = \`
          .cut-path { fill: rgba(255,255,255,0.01); stroke: #111111; stroke-width: \${cutStrokeW.toFixed(2)}px; stroke-linejoin: round; stroke-linecap: round; }
          .center-path { fill: none; stroke: #8c8275; stroke-width: \${centerStrokeW.toFixed(2)}px; stroke-dasharray: \${centerDash}; stroke-linejoin: round; }
          .num-halo { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: \${fontSize.toFixed(2)}px; font-weight: 700; fill: none; stroke: #ffffff; stroke-width: \${(fontSize * 0.24).toFixed(2)}px; stroke-linejoin: round; text-anchor: middle; dominant-baseline: central; }
          .num-txt { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: \${fontSize.toFixed(2)}px; font-weight: 700; fill: #181512; text-anchor: middle; dominant-baseline: central; }
          .grain-line { stroke: #7a5219; stroke-width: \${Math.max(0.28 * pxPerMm, 0.85).toFixed(2)}px; stroke-linecap: round; fill: none; }
          .scale-bar { stroke: #181512; stroke-width: \${Math.max(0.35 * pxPerMm, 1.0).toFixed(2)}px; fill: none; }
          .scale-txt { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: \${(2.8 * pxPerMm).toFixed(2)}px; font-weight: 600; fill: #3d3730; }
          .tile-cut { fill: none; stroke: #999; stroke-width: \${centerStrokeW.toFixed(2)}px; stroke-dasharray: \${(3 * pxPerMm).toFixed(1)},\${(2 * pxPerMm).toFixed(1)}; }
          .tile-mark { stroke: #444; stroke-width: \${centerStrokeW.toFixed(2)}px; }
          .tile-pg { font-family: sans-serif; font-size: \${(3.0 * pxPerMm).toFixed(2)}px; fill: #666; }
        \`;

        const imageTag = (showPhoto && DATA.patternImageUrl)
          ? \`<image href="\${DATA.patternImageUrl}" x="0" y="0" width="\${DATA.patternWidth}" height="\${DATA.patternHeight}" opacity="0.22" />\`
          : '';

        // 1. Dashed assembly centerlines (drawn underneath cut lines when allowance > 0)
        let centerlinesSvg = '';
        if (showCenterlines && allowance !== 'zero') {
          centerlinesSvg = DATA.pieces.map(p => {
            const geom = useSmooth ? p.fair : p.raw;
            return \`<path d="\${geom.d0}" class="center-path" />\`;
          }).join('');
        }

        // 2. Solid inward-offset glass cut lines + piece numbers + grain direction arrows
        const piecesSvg = DATA.pieces.map(p => {
          const geom = useSmooth ? p.fair : p.raw;
          const dCut = allowance === 'foil'
            ? geom.dFoil
            : allowance === 'came'
              ? geom.dCame
              : allowance === 'solder'
                ? geom.dSolder
                : geom.d0;

          const labelY = showGrain ? p.cy - fontSize * 0.22 : p.cy;
          let grainSvg = '';
          if (showGrain && p.minSpan > fontSize * 1.4) {
            const halfLen = Math.min(fontSize * 0.72, p.minSpan * 0.22);
            const head = halfLen * 0.34;
            const gy = p.cy + fontSize * 0.56;
            grainSvg =
              \`<g transform="translate(\${p.cx},\${gy}) rotate(\${p.grainAngleDeg})">\` +
              \`<line x1="\${(-halfLen).toFixed(2)}" y1="0" x2="\${halfLen.toFixed(2)}" y2="0" class="grain-line" />\` +
              \`<polyline points="\${(halfLen - head).toFixed(2)},\${(-head * 0.65).toFixed(2)} \${halfLen.toFixed(2)},0 \${(halfLen - head).toFixed(2)},\${(head * 0.65).toFixed(2)}" class="grain-line" />\` +
              \`<polyline points="\${(-halfLen + head).toFixed(2)},\${(-head * 0.65).toFixed(2)} \${(-halfLen).toFixed(2)},0 \${(-halfLen + head).toFixed(2)},\${(head * 0.65).toFixed(2)}" class="grain-line" />\` +
              \`</g>\`;
          }

          return (
            \`<path d="\${dCut}" class="cut-path" />\` +
            grainSvg +
            \`<text x="\${p.cx}" y="\${labelY.toFixed(2)}" class="num-halo">\${p.num}</text>\` +
            \`<text x="\${p.cx}" y="\${labelY.toFixed(2)}" class="num-txt">\${p.num}</text>\`
          );
        }).join('');

        // 3. 1:1 Scale verification ruler bar in bottom margin
        const barLenMm = DATA.unit === 'in' ? 50.8 : 50;
        const barLabel = DATA.unit === 'in' ? '2.00 in (50.8 mm) — 1:1 Scale Check' : '50 mm (5.0 cm) — 1:1 Scale Check';
        const barLenPx = barLenMm * pxPerMm;
        const barX = DATA.minX + 10 * pxPerMm;
        const barY = DATA.minY + DATA.printHeight - 7 * pxPerMm;
        const tickH = 2.2 * pxPerMm;
        const scaleBarSvg =
          \`<g>\` +
          \`<line x1="\${barX.toFixed(2)}" y1="\${barY.toFixed(2)}" x2="\${(barX + barLenPx).toFixed(2)}" y2="\${barY.toFixed(2)}" class="scale-bar" />\` +
          \`<line x1="\${barX.toFixed(2)}" y1="\${(barY - tickH).toFixed(2)}" x2="\${barX.toFixed(2)}" y2="\${(barY + tickH).toFixed(2)}" class="scale-bar" />\` +
          \`<line x1="\${(barX + barLenPx / 2).toFixed(2)}" y1="\${(barY - tickH * 0.7).toFixed(2)}" x2="\${(barX + barLenPx / 2).toFixed(2)}" y2="\${(barY + tickH * 0.7).toFixed(2)}" class="scale-bar" />\` +
          \`<line x1="\${(barX + barLenPx).toFixed(2)}" y1="\${(barY - tickH).toFixed(2)}" x2="\${(barX + barLenPx).toFixed(2)}" y2="\${(barY + tickH).toFixed(2)}" class="scale-bar" />\` +
          \`<text x="\${(barX + barLenPx + 3.5 * pxPerMm).toFixed(2)}" y="\${(barY + 0.9 * pxPerMm).toFixed(2)}" class="scale-txt">\${barLabel} · \${allowanceLabel}</text>\` +
          \`</g>\`;

        const pages = [];
        const pageStyleEl = document.getElementById('dynamic-page-style');

        if (paper === 'single') {
          const pwPhysical = (DATA.printWidth / DATA.pxPerUnit).toFixed(3);
          const phPhysical = (DATA.printHeight / DATA.pxPerUnit).toFixed(3);
          pageStyleEl.textContent = '@media print { @page { margin: 0; } }';
          pages.push(
            \`<svg width="\${pwPhysical}\${DATA.unit}" height="\${phPhysical}\${DATA.unit}" viewBox="\${DATA.minX} \${DATA.minY} \${DATA.printWidth} \${DATA.printHeight}" xmlns="http://www.w3.org/2000/svg">\` +
            \`<style>\${commonStyles}</style>\${imageTag}\${centerlinesSvg}\${piecesSvg}\${scaleBarSvg}</svg>\`
          );
        } else {
          const pageWMm = paper === 'letter' ? 215.9 : 210;
          const pageHMm = paper === 'letter' ? 279.4 : 297;
          const overlapMm = 10;
          const pageWPx = pageWMm * pxPerMm;
          const pageHPx = pageHMm * pxPerMm;
          const overlapPx = overlapMm * pxPerMm;
          const stepXPx = pageWPx - overlapPx;
          const stepYPx = pageHPx - overlapPx;
          const cols = Math.max(1, Math.ceil(DATA.printWidth / stepXPx));
          const rows = Math.max(1, Math.ceil(DATA.printHeight / stepYPx));
          const totalPages = rows * cols;
          const crossSize = overlapPx * 0.22;

          pageStyleEl.textContent = \`@media print { @page { margin: 0; size: \${pageWMm}mm \${pageHMm}mm; } }\`;

          for (let row = 0; row < rows; row++) {
            for (let col = 0; col < cols; col++) {
              const tileMinX = DATA.minX + col * stepXPx;
              const tileMinY = DATA.minY + row * stepYPx;
              const pageNum = row * cols + col + 1;
              let annotations = '';
              if (col < cols - 1) {
                const cx = tileMinX + stepXPx;
                annotations += \`<line x1="\${cx}" y1="\${tileMinY}" x2="\${cx}" y2="\${tileMinY + pageHPx}" class="tile-cut" />\`;
              }
              if (row < rows - 1) {
                const cy = tileMinY + stepYPx;
                annotations += \`<line x1="\${tileMinX}" y1="\${cy}" x2="\${tileMinX + pageWPx}" y2="\${cy}" class="tile-cut" />\`;
              }
              if (col < cols - 1 && row < rows - 1) {
                const cx = tileMinX + stepXPx;
                const cy = tileMinY + stepYPx;
                annotations +=
                  \`<line x1="\${cx - crossSize}" y1="\${cy}" x2="\${cx + crossSize}" y2="\${cy}" class="tile-mark" />\` +
                  \`<line x1="\${cx}" y1="\${cy - crossSize}" x2="\${cx}" y2="\${cy + crossSize}" class="tile-mark" />\`;
              }
              const lx = tileMinX + pageWPx - 5 * pxPerMm;
              const ly = tileMinY + pageHPx - 5 * pxPerMm;
              annotations += \`<text x="\${lx}" y="\${ly}" class="tile-pg" text-anchor="end">Page \${pageNum}/\${totalPages} (R\${row + 1}·C\${col + 1})</text>\`;

              pages.push(
                \`<svg width="\${pageWMm}mm" height="\${pageHMm}mm" viewBox="\${tileMinX} \${tileMinY} \${pageWPx} \${pageHPx}" xmlns="http://www.w3.org/2000/svg">\` +
                \`<style>\${commonStyles}</style>\${imageTag}\${centerlinesSvg}\${piecesSvg}\${scaleBarSvg}\${annotations}</svg>\`
              );
            }
          }
        }

        const pageClass = paper === 'single' ? 'page single-sheet' : 'page';
        document.getElementById('pages-root').innerHTML = pages.map(svg => \`<div class="\${pageClass}">\${svg}</div>\`).join('\\n');
      }

      ['sel-allowance', 'sel-paper', 'chk-smooth', 'chk-centerlines', 'chk-grain', 'chk-photo'].forEach(id => {
        document.getElementById(id).addEventListener('change', renderPages);
      });
      document.getElementById('btn-trigger-print').addEventListener('click', () => window.print());

      renderPages();
    </script>
  </body>
</html>`);
    printWin.document.close();
  };

  printRef.current = { ready: isPrintReady, fn: handlePrint };

  const handleAddSheetFromFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      addSheetFromImage(dataUrl, file.name);
    };
    reader.readAsDataURL(file);
  };

  const handleNewSheetFromImageWithMove = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const srcId = moveSourceSheetIdRef.current;
    moveSourceSheetIdRef.current = null;
    e.target.value = '';
    if (!file || !srcId) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      addSheetFromImageAndMovePieces(dataUrl, file.name, srcId);
    };
    reader.readAsDataURL(file);
  };

  const requestMove = (srcId: string, destId: string) => {
    if (srcId === destId) return;
    if (suppressMoveConfirm) {
      moveAllPiecesBetweenSheets(srcId, destId);
      return;
    }
    setPendingMove({ srcId, destId });
  };

  const triggerNewSheetFromImage = (srcId: string) => {
    moveSourceSheetIdRef.current = srcId;
    newSheetFileInputRef.current?.click();
  };

  const pendingMoveLabels = pendingMove
    ? {
        src: project.sheets.find(s => s.id === pendingMove.srcId)?.label ?? '',
        dest: project.sheets.find(s => s.id === pendingMove.destId)?.label ?? '',
        count: pieceCountBySheet[pendingMove.srcId] ?? 0,
      }
    : null;

  const commitProjectName = () => {
    const trimmed = nameDraft.trim();
    if (trimmed && trimmed !== project.name) setProjectName(trimmed);
    else setNameDraft(project.name);
  };

  const handleGlobalDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (!file) return;

    if (file.type === 'application/json' || file.name.endsWith('.json')) {
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const data = JSON.parse(ev.target?.result as string);
          handleProjectFileData(data);
        } catch (err) {
          console.error(err);
          alert(t('invalidProject'));
        }
      };
      reader.readAsText(file);
    } else if (file.type.startsWith('image/')) {
      loadPatternImageFile(file);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  return (
    <div 
      className="app" 
      onDrop={handleGlobalDrop}
      onDragOver={handleDragOver}
    >
      <header className="global-header">
        <div className="logo-container">
          <img src="/vitrai_logo.svg" alt="Vitrai Logo" className="logo-img" />
          <h1 className="app-name">Vitrai</h1>
        </div>

        <div className="header-actions">
          {/* Project controls */}
          <div ref={projectDropdownRef} style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 1 }}>
            <input
              ref={projectNameInputRef}
              className="project-name-input"
              value={nameDraft}
              onChange={e => setNameDraft(e.target.value)}
              onFocus={e => e.target.select()}
              onBlur={commitProjectName}
              onKeyDown={e => {
                if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                if (e.key === 'Escape') { setNameDraft(project.name); (e.target as HTMLInputElement).blur(); }
              }}
              title={t('clickToRename')}
            />
            <button
              className="project-chevron-btn"
              onClick={() => setIsProjectDropdownOpen(o => !o)}
              title={t('switchProjectTooltip', 'Switch project')}
            >
              ▾
            </button>

            {isProjectDropdownOpen && (
              <div className="project-dropdown">
                {availableProjects.map(name => (
                  <div
                    key={name}
                    className={`project-dropdown-item${name === project.name ? ' active' : ''}`}
                    onClick={() => { void switchProject(name); setIsProjectDropdownOpen(false); }}
                  >
                    <span className="project-dropdown-check">{name === project.name ? '✓' : ''}</span>
                    <span className="project-dropdown-name">{name}</span>
                    {availableProjects.length > 1 && (
                      <button
                        className="project-delete-btn"
                        onClick={e => {
                          e.stopPropagation();
                          if (window.confirm(t('confirmDeleteProject', { defaultValue: 'Delete "{{name}}"? This cannot be undone.', name }))) {
                            void deleteProject(name);
                            setIsProjectDropdownOpen(false);
                          }
                        }}
                        title={t('deleteProjectTooltip', 'Delete project')}
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
          <button
            className="btn-ghost"
            onClick={async () => {
              const defaultName = t('defaultProjectName', { defaultValue: 'Project {{num}}', num: availableProjects.length + 1 });
              await createNewProject(defaultName, 'flat');
              projectNameInputRef.current?.focus();
              projectNameInputRef.current?.select();
            }}
            title={t('newProjectTooltip', 'New project')}
            style={{ fontSize: '1.1rem', lineHeight: 1, padding: '2px 8px' }}
          >
            +
          </button>

          <div style={{ width: 1, height: 16, background: 'var(--hairline-2)', margin: '0 4px' }} />

          {/* Undo / Redo */}
          <button className="btn-ghost" onClick={undo} disabled={!canUndo} title={t('undoTooltip', 'Undo (Ctrl+Z)')} style={{ padding: '4px 8px' }}>
            <IconUndo size={14} />
          </button>
          <button className="btn-ghost" onClick={redo} disabled={!canRedo} title={t('redoTooltip', 'Redo (Ctrl+Y)')} style={{ padding: '4px 8px' }}>
            <IconRedo size={14} />
          </button>

          <div className="header-secondary">
            <button
              className="btn-ghost"
              onClick={() => setIsShortcutsOpen(true)}
              title={t('shortcutsTitle')}
              style={{ fontWeight: 600, padding: '4px 8px' }}
              aria-label={t('shortcutsTitle')}
            >
              ?
            </button>

            <button
              className="btn-ghost"
              onClick={() => i18n.changeLanguage(i18n.language === 'fr' ? 'en' : 'fr')}
              title={i18n.language === 'fr' ? 'Switch to English' : 'Passer en français'}
              style={{ fontSize: '0.8rem', fontWeight: 600, padding: '4px 8px' }}
            >
              {i18n.language === 'fr' ? 'EN' : 'FR'}
            </button>

            <div style={{ width: 1, height: 16, background: 'var(--hairline-2)', margin: '0 4px' }} />

            <label className="btn-ghost" style={{ cursor: 'pointer' }}>
              {t('openProject')}
              <input type="file" accept=".json" style={{ display: 'none' }} onChange={handleLoadProject} />
            </label>
            <button className="btn-ghost" onClick={handleSaveProject} title={t('saveTooltip')}>
              {t('saveCopy')}
            </button>

          </div>

          <div style={{ width: 12 }} />

          <button
            className={`btn-primary header-print${isPrintReady ? '' : ' is-muted'}`}
            onClick={() => isPrintReady ? handlePrint() : undefined}
            title={isPrintReady ? t('printPrimaryTooltip') : printNotReadyReason}
            aria-disabled={!isPrintReady}
            data-tutorial-target="print-button"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M6 9V3h12v6" />
              <rect x="3" y="9" width="18" height="9" rx="1.5" />
              <rect x="7" y="14" width="10" height="7" rx="0.8" />
            </svg>
            {t('printPrimary')}
          </button>

          <button
            className="mobile-menu-btn"
            onClick={() => setIsMobileMenuOpen(true)}
            title={t('menuTitle', 'Menu')}
          >
            ···
          </button>

        </div>
      </header>

      <div className="main-container">
        {/* ── Left: pattern view ── */}
        <div className="panel panel-left">
          <div className="panel-header">
            <div className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="panel-title-eyebrow">{t('pattern')}</span>
              <PatternDimensionsEditor
                project={project}
                onUpdateDimensions={updatePatternDimensions}
              />
            </div>
            {project.patternImageUrl && (
              <label className="btn-ghost" style={{ cursor: 'pointer' }} title={t('replacePatternTooltip')}>
                {t('replacePattern')}
                <input type="file" accept="image/*" style={{ display: 'none' }} onChange={handleUploadPattern} />
              </label>
            )}
          </div>
          <ResultPanel
            key={tutorialActiveTrackId ?? 'project'}
            pieceTransformPreviewStore={pieceTransformPreviewStore}
            project={project}
            selectedPieceIds={selectedPieceIds}
            pendingPieceIds={pendingPieceIds}
            onSelectPiece={selectPiece}
            onSelectPieces={selectPieces}
            onPatternCropChange={updatePatternCrop}
            onPatternScaleChange={updatePatternScale}
            onAddPiece={handleAddPiece}
            onAddManualPiece={handleAddManualPiece}
            onUpdatePieceLabel={updatePieceLabel}
            onUpdatePieceSheet={updatePieceSheet}
            onUpdatePiecesSheet={updatePiecesSheet}
            onAddSheetAndAssignPiece={addSheetAndAssignPiece}
            onAddSheetAndAssignPieces={addSheetAndAssignPieces}
            onDeletePiece={deletePiece}
            onDeletePieces={deletePieces}
            onSmoothPiece={handleSmoothPiece}
            onSmoothPieces={handleSmoothPieces}
            onStraightenPiece={handleStraightenPiece}
            onStraightenPieces={handleStraightenPieces}
            onUpdatePieceCurves={handleUpdatePieceCurves}
            onUpdatePiecePolygonAndCurves={handleUpdatePieceGeometry}
            onUpdatePrompt={handleUpdatePrompt}
            onUploadPattern={handleUploadPattern}
            onStartBlankCanvas={startBlankCanvas}
            onStartLampMode={handleStartLampMode}
            onAutoSegment={handleAutoSegment}
            isAutoSegmenting={isAutoSegmenting}
            isEncoding={!!project.patternImageUrl && patternImageId === null}
            downloadProgress={downloadProgress}
            debugMask={debugMask}
            activeTool={patternTool}
            onChangeActiveTool={setPatternTool}
            tutorialStep={tutorialStep}
            refineMode={patternRefineMode}
            onRefineModeChange={setPatternRefineMode}
            penStatusStore={penStatusStore}
            onUpdateSolderWidthMM={updateSolderWidthMM}
            onUpdateSolderColor={updateSolderColor}
            onOpenLampProfile={isLamp ? (() => setLampProfileDialog({ isFirstTime: false })) : undefined}
            isSymmetryEnabled={isSymmetryEnabled}
            onToggleSymmetry={setIsSymmetryEnabled}
          />
        </div>

      {/* ── Right: glass sheet workspace ── */}
      <div className="panel panel-right">
        {isLamp && (
          <>
            <div data-tutorial-target="lamp-3d-preview" style={{ height: lampPreviewHeight, flexShrink: 0, position: 'relative', overflow: 'hidden', borderBottom: '1px solid var(--hairline)' }}>
              <Lamp3DPreview
                project={project}
                pieceTransformPreviewStore={pieceTransformPreviewStore}
                selectedPieceIds={selectedPieceIds}
                onSelectPiece={selectPiece}
                onUpdateLampConfig={updateLampConfig}
                activeSheetId={activeSheetId}
                onSetFocusedPanelIdx={setFocusedPanelIdx}
              />
            </div>
            <div
              onPointerDown={startLampPreviewResize}
              style={{
                height: 6,
                cursor: 'row-resize',
                background: 'var(--chrome-700)',
                flexShrink: 0,
                position: 'relative',
              }}
              role="separator"
              aria-orientation="horizontal"
              aria-label={t('resizePreviewLabel', 'Resize 3D preview')}
            >
              <div style={{ position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%, -50%)', width: 30, height: 2, background: 'var(--hairline-2)', borderRadius: 1 }} />
            </div>
          </>
        )}
        <div className="panel-header">
          <div className="panel-title" style={{ flexShrink: 0 }}>
            <span className="panel-title-eyebrow">{t('glass')}</span>
            <span className="panel-title-subtitle">
              {t('sheets', { count: project.sheets.length })}
            </span>
          </div>
          <div className="sheet-tabs">
            {project.sheets.map(sheet => (
              <SheetTab
                key={sheet.id}
                sheet={sheet}
                isActive={sheet.id === activeSheetId}
                isEmpty={(pieceCountBySheet[sheet.id] ?? 0) === 0}
                canDelete
                pieceCount={pieceCountBySheet[sheet.id] ?? 0}
                pieceCountBySheet={pieceCountBySheet}
                allSheets={project.sheets}
                onSelect={() => setActiveSheetId(sheet.id)}
                onRename={label => renameSheet(sheet.id, label)}
                onDelete={() => deleteSheet(sheet.id)}
                onMoveAllTo={destId => requestMove(sheet.id, destId)}
                onMoveAllFromSrc={srcId => requestMove(srcId, sheet.id)}
                onNewSheetFromImage={() => triggerNewSheetFromImage(sheet.id)}
              />
            ))}
            <button
              type="button"
              className="sheet-tab"
              title={t('addSheetTooltip')}
              onClick={e => {
                if (addSheetMenu) { setAddSheetMenu(null); return; }
                const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                setAddSheetMenu({ left: rect.left, top: rect.bottom + 4 });
              }}
            >
              +
            </button>
            <input
              ref={newSheetFileInputRef}
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={handleNewSheetFromImageWithMove}
            />
          </div>
        </div>

        {activeSheet ? (
          <SheetPanel
            key={tutorialActiveTrackId ?? 'project'}
            pieceTransformPreviewStore={pieceTransformPreviewStore}
            sheet={activeSheet}
            pieces={piecesOnActiveSheet}
            selectedPieceIds={selectedPieceIds}
            onSelectPiece={selectPiece}
            onTransformChange={updatePieceTransform}
            onCommitTransforms={commitPieceTransforms}
            onCropChange={(c, skipHistory) => updateSheetCrop(activeSheetId, c, skipHistory)}
            onScaleChange={s => updateSheetScale(activeSheetId, s)}
            onImageLoad={(w, h) => updateSheetDimensions(activeSheetId, w, h)}
            showEmptyHint={
              piecesOnActiveSheet.length === 0 &&
              project.pieces.length > 0
            }
            activeTool={sheetTool}
            onChangeActiveTool={setSheetTool}
            isTutorial={project.name === 'Tutorial'}
            onPackingComplete={() => { if (tutorialStep === 'fab-smart-pack') advanceTutorial(); }}
          />
        ) : (
          <div className="canvas-well" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-soft)', padding: 40, textAlign: 'center' }}>
            <div>
              <p style={{ fontFamily: '"Instrument Serif", Georgia, serif', fontSize: '1.5rem', fontWeight: 400, color: 'var(--text-bright)', marginBottom: 8 }}>{t('noSheetsTitle')}</p>
              <p style={{ fontSize: '0.9rem' }}>{t('noSheetsDesc')}</p>
            </div>
          </div>
        )}
      </div>
    </div>

      {/* Status bar */}
      <div className="status-bar">
        <div className="status-bar-section">
          <span>
            {project.pieces.length} {project.pieces.length === 1 ? t('piece').toLowerCase() : t('pieces')}
          </span>
          <span className="status-bar-divider" />
          <span>
            {project.patternScale
              ? `${t('statusScale')} · ${parseFloat(project.patternScale.pxPerUnit.toFixed(2))} px/${t('unit_' + project.patternScale.unit)}`
              : t('statusNoScale')}
          </span>
          <PenStatusDisplay
            store={penStatusStore}
            active={patternTool === 'pen' || patternTool === 'polygon'}
            scale={project.patternScale}
          />
          {activeSheet && (
            <>
              <span className="status-bar-divider" />
              <span>
                {t('sheet')}: {activeSheet.label}
              </span>
            </>
          )}
        </div>
        <div className="status-bar-section">
          <div className={`autosave autosave-${saveStatus}`} role="status" aria-live="polite">
            <span className="autosave-dot" />
            <span className="autosave-label">
              {saveStatus === 'saving' ? t('autosaveSaving')
                : saveStatus === 'error' ? t('autosaveFailed')
                : t('autosaveSaved')}
            </span>
            {saveStatus === 'saved' && (
              <span className="autosave-info" title={t('autosaveOfflineHint')}>ⓘ</span>
            )}
            {saveStatus === 'error' && (
              <button className="autosave-retry" onClick={retrySave}>{t('autosaveRetry')}</button>
            )}
          </div>
          <span className="status-bar-divider" />
          {backendStatus && (
            <>
              <span title="SAM2 backend">{backendStatus}</span>
              <span className="status-bar-divider" />
            </>
          )}
          <span style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>{i18n.language}</span>
          <span className="status-bar-divider" />
          <button className="status-bar-kbd status-bar-kbd-btn" onClick={() => setIsShortcutsOpen(true)}>
            <kbd>?</kbd>
            <span>{t('statusShortcuts')}</span>
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      <div className={`mobile-drawer${isMobileMenuOpen ? ' open' : ''}`}>
        <div className="mobile-drawer-backdrop" onClick={() => setIsMobileMenuOpen(false)} />
        <div className="mobile-drawer-panel">
          <div className="mobile-drawer-header">
            <span className="mobile-drawer-title">{t('menuTitle', 'Menu')}</span>
            <button className="mobile-drawer-close" onClick={() => setIsMobileMenuOpen(false)}>×</button>
          </div>

          <button
            className="mobile-drawer-item"
            onClick={() => { i18n.changeLanguage(i18n.language === 'fr' ? 'en' : 'fr'); setIsMobileMenuOpen(false); }}
          >
            <IconGlobe size={18} />
            <span>{i18n.language === 'fr' ? 'Switch to English' : 'Passer en français'}</span>
          </button>

          <div className="mobile-drawer-divider" />

          <label className="mobile-drawer-item" style={{ cursor: 'pointer' }}>
            <IconUpload size={18} />
            <span>{t('openProject')}</span>
            <input type="file" accept=".json" style={{ display: 'none' }} onChange={e => { handleLoadProject(e); setIsMobileMenuOpen(false); }} />
          </label>

          <button className="mobile-drawer-item" onClick={() => { handleSaveProject(); setIsMobileMenuOpen(false); }}>
            <IconDownload size={18} />
            <span>{t('saveCopy')}</span>
          </button>

          <div className="mobile-drawer-divider" />

          <button className="mobile-drawer-item" onClick={() => { handlePrint(); setIsMobileMenuOpen(false); }}>
            <IconPrinter size={18} />
            <span>{t('print')}</span>
          </button>

          <div className="mobile-drawer-divider" />

          <button
            className="mobile-drawer-item"
            onClick={() => { setTutorialStep('welcome'); setIsMobileMenuOpen(false); }}
          >
            <IconSpark size={18} />
            <span>{t('tutorialMenuItem')}</span>
          </button>

          <div className="mobile-drawer-divider" />

          <button className="mobile-drawer-item" onClick={() => { setIsShortcutsOpen(true); setIsMobileMenuOpen(false); }}>
            <span style={{ width: 18, textAlign: 'center', fontWeight: 600 }}>?</span>
            <span>{t('shortcutsTitle')}</span>
          </button>
        </div>
      </div>

      {pendingMove && pendingMoveLabels && (
        <MoveConfirmDialog
          count={pendingMoveLabels.count}
          srcLabel={pendingMoveLabels.src}
          destLabel={pendingMoveLabels.dest}
          onCancel={() => setPendingMove(null)}
          onConfirm={dontAsk => {
            if (dontAsk) setSuppressMoveConfirm(true);
            moveAllPiecesBetweenSheets(pendingMove.srcId, pendingMove.destId);
            setPendingMove(null);
          }}
        />
      )}
      {addSheetMenu && (
        <AddSheetMenu
          anchor={addSheetMenu}
          currentProjectName={project.name}
          onPickUrl={(url, label, scale) => addSheetFromImage(url, label, scale ?? null)}
          onUpload={handleAddSheetFromFile}
          onOpenLibrary={() => setShowGlassLibrary(true)}
          onClose={() => setAddSheetMenu(null)}
        />
      )}

      {showGlassLibrary && (
        <GlassLibraryDialog
          onPick={(url, label, scale) => addSheetFromImage(url, label, scale)}
          onClose={() => setShowGlassLibrary(false)}
        />
      )}

      {lampProfileDialog && project.lampConfig && (
        <LampProfileDialog
          project={project}
          initialConfig={project.lampConfig}
          isFirstTime={lampProfileDialog.isFirstTime}
          onCancel={() => setLampProfileDialog(null)}
          onUpdatePatternScale={updatePatternScale}
          hasTutorialBar={!!tutorialStep}
          onConfirm={config => {
            updateLampConfig(config);
            setLampProfileDialog(null);
          }}
        />
      )}
      <ShortcutsOverlay open={isShortcutsOpen} onClose={() => setIsShortcutsOpen(false)} onStartTutorial={startTutorialTour} />
      <Tutorial
        step={tutorialStep}
        activeTrackId={tutorialActiveTrackId}
        pieceId={tutorialPieceId}
        project={project}
        selectedPieceIds={selectedPieceIds}
        activeSheetId={activeSheetId}
        patternTool={patternTool}
        sheetTool={sheetTool}
        patternRefineMode={patternRefineMode}
        onAdvance={advanceTutorial}
        onSetStep={setTutorialStep}
        onSetTrackedPiece={handleSetTrackedPiece}
        onSelectPiece={selectPiece}
        onStartTour={startTutorialTour}
        onSkip={skipTutorial}
        onComplete={completeTutorial}
        isEncoding={!!project.patternImageUrl && patternImageId === null}
        downloadProgress={downloadProgress}
        isLampProfileOpen={lampProfileDialog !== null}
        isSymmetryEnabled={isSymmetryEnabled}
        pendingPieceIds={pendingPieceIds}
        onExitRefine={() => setPatternRefineMode(null)}
      />
  </div>
  );
}
