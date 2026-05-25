import { useEffect, useState, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ResultPanel } from './components/ResultPanel';
import { SheetPanel } from './components/SheetPanel';
import { MoveConfirmDialog } from './components/MoveConfirmDialog';
import { ShortcutsOverlay } from './components/ShortcutsOverlay';
import { AddSheetMenu } from './components/AddSheetMenu';

import { Lamp3DPreview } from './components/Lamp3DPreview';
import { LampProfileDialog } from './components/LampProfileDialog';
import { useProject } from './hooks/useProject';
import { subtractPolygons, computeCentroid, snapPolygonToNeighbors, smoothPolygon, flattenCurves, arePolygonsEqual } from './utils/geometry';
import { computeImageSwatch } from './utils/swatch';
import { getSamBackend } from './samBackend';
import type { BoundingBox, GlassSheet, CurvePoint } from './types';
import {
  IconUndo, IconRedo, IconGlobe, IconUpload, IconDownload, IconPrinter, IconSpark,
} from './components/icons';
import { STORAGE_KEY, STEPS, STEP_ORDER } from './components/Tutorial/types';
import type { StepId, PersistedTutorialState } from './components/Tutorial/types';
import { Tutorial } from './components/Tutorial/Tutorial';
import { DEFAULT_PROJECT } from './defaultProject';
import type { ToolId } from './components/Toolbar';
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

const getSnapRadius = (width: number) => Math.max(8, Math.min(40, width * 0.01));

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

export function App() {
  const { t, i18n } = useTranslation();
  const {
    project,
    selectedPieceIds,
    activeSheetId,
    pendingPieceIds,
    setActiveSheetId,
    selectPiece,
    selectPieces,
    updatePieceTransform,
    batchUpdatePieceTransforms,
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
    updatePiecePolygon,
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
  const [tutorialPieceId, setTutorialPieceId] = useState<string | null>(null);
  const [patternTool, setPatternTool] = useState<ToolId>('select');
  const [sheetTool, setSheetTool] = useState<ToolId>('select');
  const [patternRefineMode, setPatternRefineMode] = useState<'add' | 'remove' | null>(null);
  const [penStatus, setPenStatus] = useState<{
    coords: { x: number; y: number } | null;
    lastPoint: { x: number; y: number } | null;
  }>({ coords: null, lastPoint: null });
  const tutorialLoadedRef = useRef(false);
  const preTutorialProjectRef = useRef<string | null>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as PersistedTutorialState;
        if (!parsed.completed && parsed.step) {
          setTutorialStep(parsed.step);
          setTutorialPieceId(parsed.pieceId);
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
  }, []);

  const startTutorialTour = () => {
    preTutorialProjectRef.current = project.name;
    loadProjectData({ ...DEFAULT_PROJECT, name: 'Tutorial' });
    setPatternTool('select');
    setSheetTool('select');
    setTutorialStep('calibrate-pattern');
    setTutorialPieceId(null);
    const state: PersistedTutorialState = {
      step: 'calibrate-pattern',
      completed: false,
      pieceId: null,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  };

  const skipTutorial = async () => {
    setTutorialStep(null);
    setTutorialPieceId(null);
    const state: PersistedTutorialState = {
      step: null,
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
    setTutorialPieceId(null);
    const state: PersistedTutorialState = {
      step: null,
      completed: true,
      pieceId: null,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  };

  const advanceTutorial = () => {
    if (!tutorialStep) return;
    const currentIndex = STEP_ORDER.indexOf(tutorialStep);
    const nextStep = currentIndex >= 0 && currentIndex < STEP_ORDER.length - 1
      ? STEP_ORDER[currentIndex + 1]
      : null;

    setTutorialStep(nextStep);
    const state: PersistedTutorialState = {
      step: nextStep,
      completed: nextStep === null,
      pieceId: nextStep === null ? null : tutorialPieceId,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  };

  const handleSetTrackedPiece = (id: string) => {
    setTutorialPieceId(id);
    const state: PersistedTutorialState = {
      step: tutorialStep,
      completed: false,
      pieceId: id,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  };



  const [patternImageId, setPatternImageId] = useState<string | null>(null);
  const [isAutoSegmenting, setIsAutoSegmenting] = useState(false);
  const [debugMask, setDebugMask] = useState<{ bitmap: ImageBitmap; width: number; height: number } | null>(null);
  const [debugMaskPieceId, setDebugMaskPieceId] = useState<string | null>(null);
  const [nameDraft, setNameDraft] = useState(project.name);
  const [isProjectDropdownOpen, setIsProjectDropdownOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [pendingMove, setPendingMove] = useState<{ srcId: string; destId: string } | null>(null);
  const [suppressMoveConfirm, setSuppressMoveConfirm] = useState(false);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const [addSheetMenu, setAddSheetMenu] = useState<{ left: number; top: number } | null>(null);

  const [focusedPanelIdx, setFocusedPanelIdx] = useState<number | null>(null);
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
      setBackendStatus("No pattern image uploaded");
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
      const others = project.pieces.filter(p => p.id !== pieceId);
      const { polygon, debugMask } = await getSamBackend().segment(patternImageId, box);
      if (debugMask) { setDebugMask(debugMask); setDebugMaskPieceId(pieceId); }
      const neighborPolygons = others.map(p => flattenCurves(p.polygon, p.curvePoints));
      const snapped = snapPolygonToNeighbors(polygon, neighborPolygons, getSnapRadius(project.patternWidth));
      const clipped = subtractPolygons(snapped, neighborPolygons);
      // skipHistory: collapse with the parent addPieceFromBox action so one Cmd+Z reverts both
      if (clipped.length >= 3) updatePiecePolygon(pieceId, clipped, true);
    } catch (e) {
      console.error("SAM segment failed:", e);
    } finally {
      unmarkPiecePending(pieceId);
    }
  }

  function handleAddManualPiece(polygon: [number, number][], tierIndex?: number) {
    const others = project.pieces;
    const neighborPolygons = others.map(p => flattenCurves(p.polygon, p.curvePoints));
    const snapped = snapPolygonToNeighbors(polygon, neighborPolygons, getSnapRadius(project.patternWidth));
    const clipped = subtractPolygons(snapped, neighborPolygons);
    if (clipped.length >= 3) {
      addManualPiece(clipped, activeSheetId, tierIndex);
    }
  }

  async function handleUpdatePrompt(pieceId: string, point: { x: number; y: number; label: 1 | 0 }) {
    addPiecePromptPoint(pieceId, point);

    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece || !patternImageId) return;

    const newPoints = [...(piece.promptPoints || []), point];

    markPiecePending(pieceId);
    try {
      const { polygon, debugMask } = await getSamBackend().segment(patternImageId, piece.promptBox, newPoints);
      if (debugMask) { setDebugMask(debugMask); setDebugMaskPieceId(pieceId); }
      const others = project.pieces.filter(p => p.id !== pieceId);
      const neighborPolygons = others.map(p => flattenCurves(p.polygon, p.curvePoints));
      const snapped = snapPolygonToNeighbors(polygon, neighborPolygons, getSnapRadius(project.patternWidth));
      const clipped = subtractPolygons(snapped, neighborPolygons);
      // Clear curvePoints: SAM2 changes vertex topology, old ctrl indices are stale.
      // skipHistory: collapse with the parent addPiecePromptPoint action so one Cmd+Z reverts both.
      if (clipped.length >= 3) { updatePiecePolygonAndCurves(pieceId, clipped, [], true); }
    } catch (e) {
      console.error(e);
    } finally {
      unmarkPiecePending(pieceId);
    }
  }

  function handleSmoothPiece(pieceId: string) {
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece) return;
    updatePiecePolygonAndCurves(pieceId, smoothPolygon(piece.polygon), []);
  }

  function handleSmoothPieces(pieceIds: string[]) {
    // skipHistory = true for all but the last to avoid pushing many history entries
    pieceIds.forEach((id, idx) => {
      const piece = project.pieces.find(p => p.id === id);
      if (piece) {
        updatePiecePolygonAndCurves(id, smoothPolygon(piece.polygon), [], idx < pieceIds.length - 1);
      }
    });
  }

  function handleUpdatePiecePolygon(pieceId: string, polygon: [number, number][]) {
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece) return;
    const others = project.pieces.filter(p => p.id !== pieceId);
    const neighborPolygons = others.map(p => flattenCurves(p.polygon, p.curvePoints));
    const snapped = snapPolygonToNeighbors(polygon, neighborPolygons, getSnapRadius(project.patternWidth));
    const clipped = subtractPolygons(snapped, neighborPolygons);
    if (clipped.length >= 3) {
      if (clipped.length !== piece.polygon.length) {
        updatePiecePolygonAndCurves(pieceId, clipped, []);
      } else {
        updatePiecePolygon(pieceId, clipped);
      }
    }
  }

  function handleUpdatePieceCurves(pieceId: string, curvePoints: CurvePoint[]) {
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece) return;
    const flatPolygon = flattenCurves(piece.polygon, curvePoints);
    const others = project.pieces.filter(p => p.id !== pieceId);
    const neighborPolygons = others.map(p => flattenCurves(p.polygon, p.curvePoints));
    const snapped = snapPolygonToNeighbors(flatPolygon, neighborPolygons, getSnapRadius(project.patternWidth));
    const clipped = subtractPolygons(snapped, neighborPolygons);

    if (clipped.length >= 3 && !arePolygonsEqual(flatPolygon, clipped, 0.1)) {
      updatePiecePolygonAndCurves(pieceId, clipped, []);
    } else {
      updatePieceCurves(pieceId, curvePoints);
    }
  }


  const activeSheet = project.sheets.find(s => s.id === activeSheetId) ?? project.sheets[0];
  const piecesOnActiveSheet = project.pieces
    .filter(p => p.glassSheetId === activeSheetId)
    .sort((a, b) => {
      const aSelected = selectedPieceIds.includes(a.id) ? 1 : 0;
      const bSelected = selectedPieceIds.includes(b.id) ? 1 : 0;
      return aSelected - bSelected;
    });

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

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
      if (isMod && e.key === 'z') {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
        return;
      }
      if (isMod && e.key === 'y') {
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
  }, [selectedPieceIds, deletePiece, undo, redo]);

  const handleLoadProject = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target?.result as string);
        loadProjectData(data);
      } catch (err) {
        console.error(err);
        alert(t('invalidProject'));
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleSaveProject = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(project));
    const a = document.createElement('a');
    a.href = dataStr;
    a.download = `${project.name}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const handleUploadPattern = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      updatePatternImage(file);
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

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    pieces.forEach(piece => {
      const displayPoly = flattenCurves(piece.polygon, piece.curvePoints);
      displayPoly.forEach(pt => {
        if (pt[0] < minX) minX = pt[0];
        if (pt[1] < minY) minY = pt[1];
        if (pt[0] > maxX) maxX = pt[0];
        if (pt[1] > maxY) maxY = pt[1];
      });
    });

    const margin = patternScale.pxPerUnit * 0.5;
    minX -= margin;
    minY -= margin;
    maxX += margin;
    maxY += margin;

    const printWidth = maxX - minX;
    const printHeight = maxY - minY;

    const pxPerUnit = patternScale.pxPerUnit;
    const unit = patternScale.unit;

    // Convert scale to px/mm for page-size calculations
    let pxPerMm: number;
    if (unit === 'mm') pxPerMm = pxPerUnit;
    else if (unit === 'cm') pxPerMm = pxPerUnit / 10;
    else pxPerMm = pxPerUnit / 25.4;

    // A4 portrait (mm) — used as the tile size when tiling is needed
    const PAGE_W_MM = 210;
    const PAGE_H_MM = 297;
    const pageWPx = PAGE_W_MM * pxPerMm;
    const pageHPx = PAGE_H_MM * pxPerMm;

    // 10 mm overlap between adjacent tiles — covers typical printer hardware margins
    const OVERLAP_MM = 10;
    const overlapPx = OVERLAP_MM * pxPerMm;
    const stepXPx = pageWPx - overlapPx;
    const stepYPx = pageHPx - overlapPx;

    const cols = Math.max(1, Math.ceil(printWidth / stepXPx));
    const rows = Math.max(1, Math.ceil(printHeight / stepYPx));
    const totalPages = rows * cols;
    const needsTiling = totalPages > 1;

    const strokeWidth = pxPerUnit * 0.05;
    const fontSize = pxPerUnit * 0.5;
    const cutLineW = Math.max(strokeWidth * 0.4, pxPerMm * 0.25);
    const dash = overlapPx * 0.12;
    const crossSize = overlapPx * 0.22;

    const commonStyles = `
      .po { fill: none; stroke: #000; stroke-width: ${strokeWidth}px; }
      .pl { font-family: sans-serif; font-size: ${fontSize}px; fill: red; text-anchor: middle; dominant-baseline: middle; font-weight: bold; }
      .cl { fill: none; stroke: #aaa; stroke-width: ${cutLineW}px; stroke-dasharray: ${dash},${dash * 0.5}; }
      .am { stroke: #555; stroke-width: ${cutLineW}px; }
      .pg { font-family: sans-serif; font-size: ${fontSize * 0.45}px; fill: #aaa; }
    `;

    const imageTag = `<image href="${project.patternImageUrl}" x="0" y="0" width="${project.patternWidth}" height="${project.patternHeight}" opacity="0.4" />`;

    const polygonsContent = pieces.map((piece, index) => {
      const displayPoly = flattenCurves(piece.polygon, piece.curvePoints);
      const pts = displayPoly.map(p => `${p[0]},${p[1]}`).join(' ');
      const c = computeCentroid(displayPoly);
      return `<polygon points="${pts}" class="po" /><text x="${c.x}" y="${c.y}" class="pl">${index + 1}</text>`;
    }).join('');

    const pages: string[] = [];

    if (!needsTiling) {
      const pwPhysical = printWidth / pxPerUnit;
      const phPhysical = printHeight / pxPerUnit;
      pages.push(
        `<svg width="${pwPhysical}${unit}" height="${phPhysical}${unit}" viewBox="${minX} ${minY} ${printWidth} ${printHeight}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">` +
        `<style>${commonStyles}</style>${imageTag}${polygonsContent}</svg>`
      );
    } else {
      for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
          const tileMinX = minX + col * stepXPx;
          const tileMinY = minY + row * stepYPx;
          const pageNum = row * cols + col + 1;

          let annotations = '';

          // Dashed cut line at right overlap boundary
          if (col < cols - 1) {
            const cx = tileMinX + stepXPx;
            annotations += `<line x1="${cx}" y1="${tileMinY}" x2="${cx}" y2="${tileMinY + pageHPx}" class="cl" />`;
          }

          // Dashed cut line at bottom overlap boundary
          if (row < rows - 1) {
            const cy = tileMinY + stepYPx;
            annotations += `<line x1="${tileMinX}" y1="${cy}" x2="${tileMinX + pageWPx}" y2="${cy}" class="cl" />`;
          }

          // Crosshair at interior tile corners (where both cut lines meet)
          if (col < cols - 1 && row < rows - 1) {
            const cx = tileMinX + stepXPx;
            const cy = tileMinY + stepYPx;
            annotations +=
              `<line x1="${cx - crossSize}" y1="${cy}" x2="${cx + crossSize}" y2="${cy}" class="am" />` +
              `<line x1="${cx}" y1="${cy - crossSize}" x2="${cx}" y2="${cy + crossSize}" class="am" />`;
          }

          // Page number in bottom-right corner
          const lx = tileMinX + pageWPx - fontSize * 0.3;
          const ly = tileMinY + pageHPx - fontSize * 0.3;
          annotations += `<text x="${lx}" y="${ly}" class="pg" text-anchor="end">${pageNum}/${totalPages} (${col + 1},${row + 1})</text>`;

          pages.push(
            `<svg width="${PAGE_W_MM}mm" height="${PAGE_H_MM}mm" viewBox="${tileMinX} ${tileMinY} ${pageWPx} ${pageHPx}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">` +
            `<style>${commonStyles}</style>${imageTag}${polygonsContent}${annotations}</svg>`
          );
        }
      }
    }

    const printWin = window.open('', '_blank');
    if (!printWin) return;

    const pagesHtml = pages.map(svg => `<div class="page">${svg}</div>`).join('\n');
    const pageRule = needsTiling
      ? `@page { margin: 0; size: ${PAGE_W_MM}mm ${PAGE_H_MM}mm; }`
      : `@page { margin: 0; }`;

    printWin.document.write(`
      <html>
        <head>
          <title>Print Pattern - Vitrai</title>
          <style>
            body { margin: 0; padding: 0; background: white; }
            .page { display: flex; justify-content: center; }
            .page + .page { page-break-before: always; break-before: page; }
            @media print {
              ${pageRule}
              body { margin: 0; }
            }
          </style>
        </head>
        <body>
          ${pagesHtml}
          <script>
            window.onload = () => { window.print(); };
          </script>
        </body>
      </html>
    `);
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
          loadProjectData(data);
        } catch (err) {
          console.error(err);
          alert(t('invalidProject'));
        }
      };
      reader.readAsText(file);
    } else if (file.type.startsWith('image/')) {
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
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const penSegment = (() => {
    if (patternTool === 'pen' && penStatus.coords && penStatus.lastPoint) {
      const dx = penStatus.coords.x - penStatus.lastPoint.x;
      const dy = penStatus.coords.y - penStatus.lastPoint.y;
      const lengthPx = Math.hypot(dx, dy);
      let angle = Math.round((Math.atan2(-dy, dx) * 180) / Math.PI);
      if (angle < 0) angle += 360;
      return { lengthPx, angle };
    }
    return null;
  })();

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
              title="Click to rename"
            />
            <button
              className="project-chevron-btn"
              onClick={() => setIsProjectDropdownOpen(o => !o)}
              title="Switch project"
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
                          if (window.confirm(`Delete "${name}"? This cannot be undone.`)) {
                            void deleteProject(name);
                            setIsProjectDropdownOpen(false);
                          }
                        }}
                        title="Delete project"
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
              const defaultName = `Project ${availableProjects.length + 1}`;
              await createNewProject(defaultName, 'flat');
              projectNameInputRef.current?.focus();
              projectNameInputRef.current?.select();
            }}
            title="New project"
            style={{ fontSize: '1.1rem', lineHeight: 1, padding: '2px 8px' }}
          >
            +
          </button>

          <div style={{ width: 1, height: 16, background: 'var(--hairline-2)', margin: '0 4px' }} />

          {/* Undo / Redo */}
          <button className="btn-ghost" onClick={undo} disabled={!canUndo} title="Undo (Ctrl+Z)" style={{ padding: '4px 8px' }}>
            <IconUndo size={14} />
          </button>
          <button className="btn-ghost" onClick={redo} disabled={!canRedo} title="Redo (Ctrl+Y)" style={{ padding: '4px 8px' }}>
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
            title="Menu"
          >
            ···
          </button>

        </div>
      </header>

      <div className="main-container">
        {/* ── Left: pattern view ── */}
        <div className="panel panel-left">
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-eyebrow">{t('pattern')}</span>
              {project.patternImageUrl && (
                <span className="panel-title-subtitle">
                  {t('patternDimensions', { w: project.patternWidth, h: project.patternHeight })}
                </span>
              )}
            </div>
            {project.patternImageUrl && (
              <label className="btn-ghost" style={{ cursor: 'pointer' }} title={t('replacePatternTooltip')}>
                {t('replacePattern')}
                <input type="file" accept="image/*" style={{ display: 'none' }} onChange={handleUploadPattern} />
              </label>
            )}
          </div>
          <ResultPanel
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
            onUpdatePiecePolygon={handleUpdatePiecePolygon}
            onUpdatePieceCurves={handleUpdatePieceCurves}
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
            onPenStatusChange={setPenStatus}
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
            <div style={{ height: lampPreviewHeight, flexShrink: 0, position: 'relative', overflow: 'hidden', borderBottom: '1px solid var(--hairline)' }}>
              <Lamp3DPreview
                project={project}
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
              aria-label="Resize 3D preview"
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
            sheet={activeSheet}
            pieces={piecesOnActiveSheet}
            selectedPieceIds={selectedPieceIds}
            pendingPieceIds={pendingPieceIds}
            onSelectPiece={selectPiece}
            onSelectPieces={selectPieces}
            onUpdatePieceTransform={updatePieceTransform}
            onBatchTransformChange={batchUpdatePieceTransforms}
            onUpdatePieceLabel={updatePieceLabel}
            onUpdatePieceSheet={updatePieceSheet}
            onUpdatePiecesSheet={updatePiecesSheet}
            onCropChange={c => updateSheetCrop(activeSheetId, c)}
            onScaleChange={s => updateSheetScale(activeSheetId, s)}
            onImageLoad={(w, h) => updateSheetDimensions(activeSheetId, w, h)}
            onDeletePiece={deletePiece}
            onDeletePieces={deletePieces}
            onSmoothPiece={handleSmoothPiece}
            onSmoothPieces={handleSmoothPieces}
            onAddSheetAndAssignPiece={addSheetAndAssignPiece}
            onAddSheetAndAssignPieces={addSheetAndAssignPieces}
            activeTool={sheetTool}
            onChangeActiveTool={setSheetTool}
            isTutorial={project.name === 'Tutorial'}
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
          {patternTool === 'pen' && penStatus.coords && (
            <>
              <span className="status-bar-divider" />
              <span>
                {t('statusPenPosition')}: {penStatus.coords.x.toFixed(0)}, {penStatus.coords.y.toFixed(0)} px
                {project.patternScale && project.patternScale.pxPerUnit > 0 && (
                  ` (${(penStatus.coords.x / project.patternScale.pxPerUnit).toFixed(1)} × ${(penStatus.coords.y / project.patternScale.pxPerUnit).toFixed(1)} ${t('unit_' + project.patternScale.unit)})`
                )}
              </span>
              {penSegment && (
                <>
                  <span className="status-bar-divider" />
                  <span>
                    {t('statusPenLength')}: {penSegment.lengthPx.toFixed(0)} px
                    {project.patternScale && project.patternScale.pxPerUnit > 0 && (
                      ` (${(penSegment.lengthPx / project.patternScale.pxPerUnit).toFixed(1)} ${t('unit_' + project.patternScale.unit)})`
                    )}
                  </span>
                  <span className="status-bar-divider" />
                  <span>
                    {t('statusPenAngle')}: {penSegment.angle}°
                  </span>
                </>
              )}
            </>
          )}
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
            <span className="mobile-drawer-title">Menu</span>
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
          onClose={() => setAddSheetMenu(null)}
        />
      )}

      {lampProfileDialog && project.lampConfig && (
        <LampProfileDialog
          project={project}
          initialConfig={project.lampConfig}
          isFirstTime={lampProfileDialog.isFirstTime}
          onCancel={() => setLampProfileDialog(null)}
          onUpdatePatternScale={(scale) => updateProject(p => ({ ...p, patternScale: scale }))}
          onConfirm={config => {
            updateLampConfig(config);
            setLampProfileDialog(null);
          }}
        />
      )}
      <ShortcutsOverlay open={isShortcutsOpen} onClose={() => setIsShortcutsOpen(false)} onStartTutorial={startTutorialTour} />
      <Tutorial
        step={tutorialStep}
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
      />
  </div>
  );
}
