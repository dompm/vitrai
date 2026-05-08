import { useEffect, useState, useRef } from 'react';
import { ResultPanel } from './components/ResultPanel';
import { SheetPanel } from './components/SheetPanel';
import { useProject } from './hooks/useProject';
import { encodeImage, segment, autoSegment } from './api';
import { subtractPolygons } from './utils/geometry';
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
  const {
    project,
    selectedPieceId,
    activeSheetId,
    pendingPieceIds,
    setActiveSheetId,
    selectPiece,
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
    updatePiecePolygon,
    markPiecePending,
    unmarkPiecePending,
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
    const piece = project.pieces.find(p => p.id === pieceId);
    if (!piece || !patternImageId) return;
    
    const newPoints = [...(piece.promptPoints || []), point];
    updatePiecePrompt(pieceId, piece.promptBox, newPoints);
    
    markPiecePending(pieceId);
    try {
      const polygon = await segment(patternImageId, undefined, newPoints);
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
      
      const newPieces = [];
      for (let i = 0; i < polygons.length; i++) {
        const poly = polygons[i];
        const pieceId = crypto.randomUUID();
        
        // Compute bounding box for the piece
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const [x, y] of poly) {
          if (x < minX) minX = x;
          if (y < minY) minY = y;
          if (x > maxX) maxX = x;
          if (y > maxY) maxY = y;
        }
        const box: BoundingBox = { x1: minX, y1: minY, x2: maxX, y2: maxY };
        
        newPieces.push({
          id: pieceId,
          label: `Piece ${project.pieces.length + i + 1}`,
          polygon: poly,
          glassSheetId: activeSheetId,
          transform: { x: 400, y: 300, rotation: 0, scale: 1 },
          promptBox: box,
          promptPoints: [],
        });
      }

      setProject(prev => persist({
        ...prev,
        pieces: [...prev.pieces, ...newPieces]
      }));
    } catch (e) {
      console.error("Auto segment failed:", e);
    } finally {
      setIsAutoSegmenting(false);
    }
  }

  const activeSheet = project.sheets.find(s => s.id === activeSheetId) ?? project.sheets[0];
  const selectedPiece = project.pieces.find(p => p.id === selectedPieceId) ?? null;
  const piecesOnActiveSheet = project.pieces.filter(p => p.glassSheetId === activeSheetId);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!selectedPieceId) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === 'Delete' || e.key === 'Backspace') deletePiece(selectedPieceId);
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedPieceId, deletePiece]);

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
        alert('Invalid project file');
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
      {/* ── Left: result view ── */}
      <div className="panel panel-left">
        <div className="panel-header">
          <span>Result</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <label className="btn-ghost" style={{ cursor: 'pointer' }}>
              Pattern
              <input type="file" accept="image/*" style={{ display: 'none' }} onChange={handleUploadPattern} />
            </label>
            <label className="btn-ghost" style={{ cursor: 'pointer' }}>
              Load
              <input type="file" accept=".json" style={{ display: 'none' }} onChange={handleLoadProject} />
            </label>
            <button className="btn-ghost" onClick={handleSaveProject} title="Save project">
              Save
            </button>
            <button className="btn-ghost" onClick={resetProject} title="Reset to defaults">
              Reset
            </button>
          </div>
        </div>
        <ResultPanel
          project={project}
          selectedPieceId={selectedPieceId}
          pendingPieceIds={pendingPieceIds}
          onSelectPiece={selectPiece}
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
            <label className="sheet-tab" title="Upload sheet" style={{ cursor: 'pointer' }}>
              +
              <input type="file" accept="image/*" style={{ display: 'none' }} onChange={handleAddSheetFromImage} />
            </label>
          </div>
        </div>

        {activeSheet && (
          <SheetPanel
            sheet={activeSheet}
            pieces={piecesOnActiveSheet}
            selectedPieceId={selectedPieceId}
            onSelectPiece={selectPiece}
            onTransformChange={updatePieceTransform}
            onCropChange={c => updateSheetCrop(activeSheetId, c)}
            onScaleChange={s => updateSheetScale(activeSheetId, s)}
          />
        )}
      </div>
    </div>
  );
}
