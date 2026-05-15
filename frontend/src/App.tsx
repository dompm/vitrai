import { useEffect, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ResultPanel } from './components/ResultPanel';
import { SheetPanel } from './components/SheetPanel';
import { useProject } from './hooks/useProject';
import { subtractPolygons, computeCentroid, snapPolygonToNeighbors, smoothPolygon } from './utils/geometry';
import { getSamBackend } from './samBackend';
import type { BoundingBox, GlassSheet } from './types';
import {
  IconUndo, IconRedo, IconGlobe, IconUpload, IconDownload, IconPrinter,
} from './components/icons';
import './App.css';

interface SheetTabProps {
  sheet: GlassSheet;
  isActive: boolean;
  canDelete: boolean;
  onSelect: () => void;
  onRename: (label: string) => void;
  onDelete: () => void;
}

const getSnapRadius = (width: number) => Math.max(8, Math.min(40, width * 0.01));

function SheetTab({ sheet, isActive, canDelete, onSelect, onRename, onDelete }: SheetTabProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(sheet.label);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setDraft(sheet.label); }, [sheet.label]);
  useEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);

  function commit() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== sheet.label) onRename(trimmed);
    else setDraft(sheet.label);
    setEditing(false);
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
    <button
      className={`sheet-tab ${isActive ? 'active' : ''}`}
      onClick={onSelect}
      onDoubleClick={() => { setDraft(sheet.label); setEditing(true); }}
      style={{ display: 'flex', alignItems: 'center', gap: 4 }}
    >
      {sheet.label}
      {canDelete && (
        <span
          className="sheet-tab-close"
          onClick={e => { e.stopPropagation(); onDelete(); }}
        >
          ×
        </span>
      )}
    </button>
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
    updatePatternCrop,
    updatePatternScale,
    updateSheetCrop,
    updateSheetScale,
    deletePiece,
    updatePieceLabel,
    updatePieceSheet,
    deleteSheet,
    renameSheet,
    addSheet,
    addSheetAndAssignPiece,
    addPieceFromBox,
    updateSheetDimensions,
    batchAddPieces,
    updatePiecePolygon,
    updatePiecePrompt,
    addPiecePromptPoint,
    markPiecePending,
    unmarkPiecePending,
    undo,
    redo,
    canUndo,
    canRedo,
    loadProjectData,
    updatePatternImage,
    addSheetFromImage,
    availableProjects,
    setProjectName,
    createNewProject,
    switchProject,
    deleteProject,
  } = useProject();

  const [backendStatus, setBackendStatus] = useState('');
  const [patternImageId, setPatternImageId] = useState<string | null>(null);
  const [isAutoSegmenting, setIsAutoSegmenting] = useState(false);
  const [debugMask, setDebugMask] = useState<{ bitmap: ImageBitmap; width: number; height: number } | null>(null);
  const [debugMaskPieceId, setDebugMaskPieceId] = useState<string | null>(null);
  const [nameDraft, setNameDraft] = useState(project.name);
  const [isProjectDropdownOpen, setIsProjectDropdownOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const projectDropdownRef = useRef<HTMLDivElement>(null);
  const projectNameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setNameDraft(project.name); }, [project.name]);

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

  async function handleAddPiece(box: BoundingBox) {
    const pieceId = addPieceFromBox(box, activeSheetId);
    if (!patternImageId) return;
    markPiecePending(pieceId);
    try {
      const others = project.pieces.filter(p => p.id !== pieceId);
      const { polygon, debugMask } = await getSamBackend().segment(patternImageId, box);
      if (debugMask) { setDebugMask(debugMask); setDebugMaskPieceId(pieceId); }
      const snapped = snapPolygonToNeighbors(polygon, others.map(p => p.polygon), getSnapRadius(project.patternWidth));
      const clipped = subtractPolygons(snapped, others.map(p => p.polygon));
      if (clipped.length >= 3) updatePiecePolygon(pieceId, clipped);
    } catch (e) {
      console.error("SAM segment failed:", e);
    } finally {
      unmarkPiecePending(pieceId);
    }
  }

  async function handleUpdatePrompt(pieceId: string, point: { x: number; y: number; label: 1 | 0 }) {
    addPiecePromptPoint(pieceId, point);

    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece || !patternImageId) return;

    const newPoints = [...(piece.promptPoints || []), point];
    const others = project.pieces.filter(p => p.id !== pieceId);

    markPiecePending(pieceId);
    try {
      const { polygon, debugMask } = await getSamBackend().segment(patternImageId, piece.promptBox, newPoints);
      if (debugMask) { setDebugMask(debugMask); setDebugMaskPieceId(pieceId); }
      const snapped = snapPolygonToNeighbors(polygon, others.map(p => p.polygon), getSnapRadius(project.patternWidth));
      const clipped = subtractPolygons(snapped, others.map(p => p.polygon));
      if (clipped.length >= 3) updatePiecePolygon(pieceId, clipped);
    } catch (e) {
      console.error(e);
    } finally {
      unmarkPiecePending(pieceId);
    }
  }

  function handleSmoothPiece(pieceId: string) {
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece) return;
    updatePiecePolygon(pieceId, smoothPolygon(piece.polygon));
  }


  const activeSheet = project.sheets.find(s => s.id === activeSheetId) ?? project.sheets[0];
  const selectedPiece = project.pieces.find(p => p.id === selectedPieceIds[selectedPieceIds.length - 1]) ?? null;
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

      const isMod = e.ctrlKey || e.metaKey;
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
        selectedPieceIds.forEach(id => deletePiece(id));
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
    if (!file) return;
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
    e.target.value = '';
  };

  const handlePrint = () => {
    const { patternScale, pieces } = project;
    if (!patternScale || patternScale.pxPerUnit === 0) {
      alert(t('printNoScale'));
      return;
    }
    if (pieces.length === 0) return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    pieces.forEach(piece => {
      piece.polygon.forEach(pt => {
        if (pt[0] < minX) minX = pt[0];
        if (pt[1] < minY) minY = pt[1];
        if (pt[0] > maxX) maxX = pt[0];
        if (pt[1] > maxY) maxY = pt[1];
      });
    });

    const margin = patternScale.pxPerUnit * 0.5; // 0.5 physical units margin
    minX -= margin;
    minY -= margin;
    maxX += margin;
    maxY += margin;

    const printWidth = maxX - minX;
    const printHeight = maxY - minY;
    
    // Scale physical size based on user definition
    const pwPhysical = printWidth / patternScale.pxPerUnit;
    const phPhysical = printHeight / patternScale.pxPerUnit;
    const unit = patternScale.unit;

    let svgContent = `<svg width="${pwPhysical}${unit}" height="${phPhysical}${unit}" viewBox="${minX} ${minY} ${printWidth} ${printHeight}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">`;
    svgContent += `<style>
      .piece-outline { fill: none; stroke: black; stroke-width: ${patternScale.pxPerUnit * 0.05}px; }
      .piece-label { font-family: sans-serif; font-size: ${patternScale.pxPerUnit * 0.5}px; fill: red; text-anchor: middle; dominant-baseline: middle; font-weight: bold; }
    </style>`;

    // Background pattern image at half opacity
    svgContent += `<image href="${project.patternImageUrl}" x="0" y="0" width="${project.patternWidth}" height="${project.patternHeight}" opacity="0.4" />`;

    pieces.forEach((piece, index) => {
      const pointsStr = piece.polygon.map(p => `${p[0]},${p[1]}`).join(' ');
      svgContent += `<polygon points="${pointsStr}" class="piece-outline" />`;
      
      const centroid = computeCentroid(piece.polygon);
      const label = index + 1;
      svgContent += `<text x="${centroid.x}" y="${centroid.y}" class="piece-label">${label}</text>`;
    });

    svgContent += `</svg>`;

    const printWin = window.open('', '_blank');
    if (!printWin) return;
    printWin.document.write(`
      <html>
        <head>
          <title>Print Pattern - Vitrai</title>
          <style>
            body { margin: 0; padding: 0; display: flex; justify-content: center; background: white; }
            @media print {
              @page { margin: 0; }
              body { margin: 0; }
            }
          </style>
        </head>
        <body>
          ${svgContent}
          <script>
            window.onload = () => {
              window.print();
            };
          </script>
        </body>
      </html>
    `);
    printWin.document.close();
  };

  const handleAddSheetFromImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = ev.target?.result as string;
      addSheetFromImage(dataUrl, file.name);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

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
            onClick={() => {
              const name = 'Project ' + (availableProjects.length + 1);
              void createNewProject(name).then(() => {
                projectNameInputRef.current?.focus();
                projectNameInputRef.current?.select();
              });
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

            <div style={{ width: 1, height: 16, background: 'var(--hairline-2)', margin: '0 4px' }} />

            <button className="btn-ghost" onClick={handlePrint} title={t('printTooltip')}>
              {t('print')}
            </button>
          </div>

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
          onUpdatePieceLabel={updatePieceLabel}
          onUpdatePieceSheet={updatePieceSheet}
          onAddSheetAndAssignPiece={addSheetAndAssignPiece}
          onDeletePiece={deletePiece}
          onSmoothPiece={handleSmoothPiece}
          onUpdatePrompt={handleUpdatePrompt}
          onUploadPattern={handleUploadPattern}
          onAutoSegment={handleAutoSegment}
          isAutoSegmenting={isAutoSegmenting}
          isEncoding={!!project.patternImageUrl && patternImageId === null}
          debugMask={debugMask}
        />
      </div>

      {/* ── Right: glass sheet workspace ── */}
      <div className="panel panel-right">
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
                canDelete
                onSelect={() => setActiveSheetId(sheet.id)}
                onRename={label => renameSheet(sheet.id, label)}
                onDelete={() => deleteSheet(sheet.id)}
              />
            ))}
            <label className="sheet-tab" title={t('uploadSheetTooltip')} style={{ cursor: 'pointer' }}>
              +
              <input type="file" accept="image/*" style={{ display: 'none' }} onChange={handleAddSheetFromImage} />
            </label>
          </div>
        </div>

        {activeSheet ? (
          <SheetPanel
            sheet={activeSheet}
            pieces={piecesOnActiveSheet}
            selectedPieceIds={selectedPieceIds}
            onSelectPiece={selectPiece}
            onTransformChange={updatePieceTransform}
            onCropChange={c => updateSheetCrop(activeSheetId, c)}
            onScaleChange={s => updateSheetScale(activeSheetId, s)}
            onImageLoad={(w, h) => updateSheetDimensions(activeSheetId, w, h)}
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
          {backendStatus && (
            <>
              <span title="SAM2 backend">{backendStatus}</span>
              <span className="status-bar-divider" />
            </>
          )}
          <span style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>{i18n.language}</span>
          <span className="status-bar-divider" />
          <span className="status-bar-kbd">
            <kbd>?</kbd>
            <span>{t('statusShortcuts')}</span>
          </span>
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
        </div>
      </div>
  </div>
  );
}
