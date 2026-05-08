import { useState, useRef, useEffect } from 'react';
import type { Piece, GlassSheet } from '../types';

interface Props {
  piece: Piece;
  sheets: GlassSheet[];
  onLabelChange: (label: string) => void;
  onSheetChange: (sheetId: string) => void;
  onAddSheet: () => void;
  onDelete: () => void;
}

export function PieceProperties({ piece, sheets, onLabelChange, onSheetChange, onAddSheet, onDelete }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(piece.label);
  const inputRef = useRef<HTMLInputElement>(null);

  // Sync draft when piece changes
  useEffect(() => {
    setDraft(piece.label);
    setEditing(false);
  }, [piece.id, piece.label]);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  function commitLabel() {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== piece.label) onLabelChange(trimmed);
    else setDraft(piece.label);
    setEditing(false);
  }

  function handleLabelKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') { e.preventDefault(); commitLabel(); }
    if (e.key === 'Escape') { setDraft(piece.label); setEditing(false); }
  }

  function handleSheetSelect(e: React.ChangeEvent<HTMLSelectElement>) {
    if (e.target.value === '__new__') onAddSheet();
    else onSheetChange(e.target.value);
  }

  return (
    <div
      onPointerDown={e => e.stopPropagation()}
      onClick={e => e.stopPropagation()}
      onWheel={e => e.stopPropagation()}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 10px',
        background: '#ffffff',
        border: '1px solid #e5e7eb',
        borderRadius: '8px',
        boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
        flexShrink: 0,
        minHeight: 40,
        pointerEvents: 'auto',
      }}
    >
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commitLabel}
          onKeyDown={handleLabelKeyDown}
          style={{
            width: 140,
            padding: '2px 6px',
            border: '1px solid #6366f1',
            borderRadius: 4,
            fontSize: 12,
            outline: 'none',
            background: '#fff',
          }}
        />
      ) : (
        <span
          onClick={() => setEditing(true)}
          title="Click to rename"
          style={{
            fontSize: 12,
            fontWeight: 500,
            color: '#111827',
            cursor: 'text',
            minWidth: 80,
            maxWidth: 160,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            padding: '2px 4px',
            borderRadius: 3,
            border: '1px solid transparent',
          }}
          onMouseEnter={e => (e.currentTarget.style.borderColor = '#d1d5db')}
          onMouseLeave={e => (e.currentTarget.style.borderColor = 'transparent')}
        >
          {piece.label}
        </span>
      )}

      <div style={{ width: 1, height: 18, background: '#e5e7eb', flexShrink: 0 }} />

      <label style={{ fontSize: 11, color: '#6b7280', flexShrink: 0 }}>Sheet</label>
      <select
        value={piece.glassSheetId}
        onChange={handleSheetSelect}
        style={{
          padding: '2px 6px',
          border: '1px solid #d1d5db',
          borderRadius: 4,
          fontSize: 12,
          background: '#fff',
          cursor: 'pointer',
          maxWidth: 140,
        }}
      >
        {sheets.map(s => (
          <option key={s.id} value={s.id}>{s.label}</option>
        ))}
        <option disabled>──────</option>
        <option value="__new__">Add sheet…</option>
      </select>

      <div style={{ flex: 1 }} />

      <button
        onClick={onDelete}
        title="Delete piece (Del)"
        style={{
          background: 'none',
          border: '1px solid #fca5a5',
          borderRadius: 4,
          color: '#ef4444',
          cursor: 'pointer',
          fontSize: 11,
          padding: '2px 8px',
          flexShrink: 0,
        }}
        onMouseEnter={e => { e.currentTarget.style.background = '#fef2f2'; }}
        onMouseLeave={e => { e.currentTarget.style.background = 'none'; }}
      >
        Delete
      </button>
    </div>
  );
}
