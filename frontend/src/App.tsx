import { useEffect, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ResultPanel } from './components/ResultPanel';
import { SheetPanel } from './components/SheetPanel';
import { useProject } from './hooks/useProject';
import { encodeImage, segment, autoSegment } from './api';
import { subtractPolygons, computeCentroid } from './utils/geometry';
import type { BoundingBox, GlassSheet } from './types';
import './App.css';

interface SheetTabProps {
  sheet: GlassSheet;
  isActive: boolean;
  canDelete: boolean;
  onSelect: () => void;
  onRename: (label: string) => void;
  onDelete: () => void;
}

const UndoIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 7v6h6" />
    <path d="M21 17a9 9 0 00-9-9 9 9 0 00-6 2.3L3 13" />
  </svg>
);

const RedoIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 7v6h-6" />
    <path d="M3 17a9 9 0 019-9 9 9 0 016 2.3l3 2.7" />
  </svg>
);

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
    resetProject,
    loadProjectData,
    updatePatternImage,
    addSheetFromImage,
  } = useProject();

  const [patternImageId, setPatternImageId] = useState<string | null>(null);

  // Encode the pattern image when it changes so SAM can warm up.
  useEffect(() => {
    setPatternImageId(null);
    encodeImage(project.patternImageUrl)
      .then(setPatternImageId)
      .catch(() => { /* backend not running — SAM unavailable */ });
  }, [project.patternImageUrl]);

  async function handleAddPiece(box: BoundingBox) {
    const pieceId = addPieceFromBox(box, activeSheetId);
    if (!patternImageId) return;
    markPiecePending(pieceId);
    try {
      const polygon = await segment(patternImageId, box);
      console.log("Segment returned polygon of length:", polygon.length);
      const existingPieces = project.pieces.map(p => p.polygon);
      const clipped = subtractPolygons(polygon, existingPieces);
      console.log("Clipped polygon length:", clipped.length);
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
    
    markPiecePending(pieceId);
    try {
      const polygon = await segment(patternImageId, piece.promptBox, newPoints);
      const otherPieces = project.pieces.filter(p => p.id !== pieceId).map(p => p.polygon);
      const clipped = subtractPolygons(polygon, otherPieces);
      if (clipped.length >= 3) updatePiecePolygon(pieceId, clipped);
    } catch (e) {
      console.error(e);
    } finally {
      unmarkPiecePending(pieceId);
    }
  }

  const [isAutoSegmenting, setIsAutoSegmenting] = useState(false);

  async function handleAutoSegment() {
    if (!patternImageId || isAutoSegmenting) return;
    setIsAutoSegmenting(true);
    try {
      const polygons = await autoSegment(patternImageId, project.patternCrop);
      batchAddPieces(polygons, activeSheetId);
    } catch (e) {
      console.error("Auto segment failed:", e);
    } finally {
      setIsAutoSegmenting(false);
    }
  }

  const activeSheet = project.sheets.find(s => s.id === activeSheetId) ?? project.sheets[0];
  const selectedPiece = project.pieces.find(p => p.id === selectedPieceIds[selectedPieceIds.length - 1]) ?? null;
  const piecesOnActiveSheet = project.pieces.filter(p => p.glassSheetId === activeSheetId);

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
    a.download = "vitraux_project.json";
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

    let svgContent = `<svg width="${pwPhysical}${unit}" height="${phPhysical}${unit}" viewBox="${minX} ${minY} ${printWidth} ${printHeight}" xmlns="http://www.w3.org/2000/svg">`;
    svgContent += `<style>
      .piece-outline { fill: none; stroke: black; stroke-width: ${patternScale.pxPerUnit * 0.05}px; }
      .piece-label { font-family: sans-serif; font-size: ${patternScale.pxPerUnit * 0.5}px; fill: red; text-anchor: middle; dominant-baseline: middle; font-weight: bold; }
    </style>`;

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

  return (
    <div className="app">
      <header className="global-header">
        <div className="logo-container">
          <img src="/vitrai_logo.png" alt="Vitrai Logo" className="logo-img" />
          <h1 className="app-name">Vitrai</h1>
        </div>
        <div className="header-actions">
          <div style={{ display: 'flex', gap: 4, marginRight: 8 }}>
            <button className="btn-ghost" onClick={undo} disabled={!canUndo} title="Undo (Ctrl+Z)" style={{ padding: '4px 8px' }}>
              <UndoIcon />
            </button>
            <button className="btn-ghost" onClick={redo} disabled={!canRedo} title="Redo (Ctrl+Y)" style={{ padding: '4px 8px' }}>
              <RedoIcon />
            </button>
          </div>
          <button 
            className="btn-ghost" 
            onClick={() => i18n.changeLanguage(i18n.language === 'fr' ? 'en' : 'fr')}
            title={i18n.language === 'fr' ? 'Switch to English' : 'Passer en français'}
            style={{ fontSize: '0.8rem', fontWeight: 600, padding: '4px 8px' }}
          >
            {i18n.language === 'fr' ? 'EN' : 'FR'}
          </button>
          <div style={{ width: 1, height: 16, background: 'rgba(0,0,0,0.1)', margin: '0 8px' }} />
          <label className="btn-ghost" style={{ cursor: 'pointer' }}>
            {t('pattern')}
            <input type="file" accept="image/*" style={{ display: 'none' }} onChange={handleUploadPattern} />
          </label>
          <label className="btn-ghost" style={{ cursor: 'pointer' }}>
            {t('load')}
            <input type="file" accept=".json" style={{ display: 'none' }} onChange={handleLoadProject} />
          </label>
          <button className="btn-ghost" onClick={handleSaveProject} title={t('saveTooltip')}>
            {t('save')}
          </button>
          <div style={{ width: 1, height: 16, background: 'rgba(0,0,0,0.1)', margin: '0 8px' }} />
          <button className="btn-ghost" onClick={handlePrint} title={t('printTooltip')}>
            {t('print')}
          </button>
          <button className="btn-ghost" onClick={resetProject} title={t('resetTooltip')}>
            {t('reset')}
          </button>
        </div>
      </header>

      <div className="main-container">
        {/* ── Left: result view ── */}
        <div className="panel panel-left">
          <div className="panel-header">
            <span>{t('result')}</span>
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
          onUpdatePrompt={handleUpdatePrompt}
          onAutoSegment={handleAutoSegment}
          isAutoSegmenting={isAutoSegmenting}
          onUploadPattern={handleUploadPattern}
        />
      </div>

      {/* ── Right: glass sheet workspace ── */}
      <div className="panel panel-right">
        <div className="panel-header">
          <div className="sheet-tabs">
            {project.sheets.map(sheet => (
              <SheetTab
                key={sheet.id}
                sheet={sheet}
                isActive={sheet.id === activeSheetId}
                canDelete={project.sheets.length > 1}
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
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280', padding: 40, textAlign: 'center' }}>
            <div>
              <p style={{ fontSize: '1.1rem', fontWeight: 500, marginBottom: 8 }}>{t('noSheetsTitle')}</p>
              <p style={{ fontSize: '0.9rem' }}>{t('noSheetsDesc')}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  </div>
  );
}
