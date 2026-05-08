import { useEffect, useState, useRef } from 'react';
import { ResultPanel } from './components/ResultPanel';
import { SheetPanel } from './components/SheetPanel';
import { PieceProperties } from './components/PieceProperties';
import { useProject } from './hooks/useProject';
import type { GlassSheet } from './types';
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
    resetProject,
  } = useProject();

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

  return (
    <div className="app">
      {/* ── Left: result view ── */}
      <div className="panel panel-left">
        <div className="panel-header">
          <span>Result</span>
          <button className="btn-ghost" onClick={resetProject} title="Reset to defaults">
            Reset
          </button>
        </div>
        <ResultPanel
          project={project}
          selectedPieceId={selectedPieceId}
          onSelectPiece={selectPiece}
          onPatternCropChange={updatePatternCrop}
          onPatternScaleChange={updatePatternScale}
          onAddPiece={box => addPieceFromBox(box, activeSheetId)}
        />
        {selectedPiece && (
          <PieceProperties
            piece={selectedPiece}
            sheets={project.sheets}
            onLabelChange={label => updatePieceLabel(selectedPiece.id, label)}
            onSheetChange={sheetId => updatePieceSheet(selectedPiece.id, sheetId)}
            onAddSheet={() => addSheetAndAssignPiece(selectedPiece.id)}
            onDelete={() => deletePiece(selectedPiece.id)}
          />
        )}
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
            <button className="sheet-tab" onClick={addSheet} title="Add sheet">+</button>
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
