import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { Piece, GlassSheet } from '../types';

interface Props {
  piece: Piece;
  sheets: GlassSheet[];
  onLabelChange: (label: string) => void;
  onSheetChange: (sheetId: string) => void;
  onAddSheet: () => void;
  onDelete: () => void;
  onSmooth?: () => void;
  refineMode?: 'add' | 'remove' | null;
  onRefineModeChange?: (mode: 'add' | 'remove' | null) => void;
  isPending?: boolean;
  isEncoding?: boolean;
  pointerEvents?: 'auto' | 'none';
}

export function PieceProperties({ piece, sheets, onLabelChange, onSheetChange, onAddSheet, onDelete, onSmooth, refineMode, onRefineModeChange, isPending, isEncoding, pointerEvents = 'auto' }: Props) {
  const { t } = useTranslation();
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
        pointerEvents,
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
          title={t('clickToRename')}
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

      <label style={{ fontSize: 11, color: '#6b7280', flexShrink: 0 }}>{t('sheet')}</label>
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
        <option value="__new__">{t('addSheetOption')}</option>
      </select>

      <div style={{ flex: 1 }} />

      {onRefineModeChange && (
        <>
          <div style={{ width: 1, height: 18, background: '#e5e7eb', flexShrink: 0 }} />
          <button
            onClick={() => !isPending && !isEncoding && onRefineModeChange(refineMode === 'add' ? null : 'add')}
            disabled={isPending || isEncoding}
            title={`${t('addPositivePoint')} [A]`}
            style={{
              background: refineMode === 'add' ? '#dbeafe' : 'none',
              border: 'none',
              borderRadius: 4,
              color: refineMode === 'add' ? '#1d4ed8' : '#6b7280',
              cursor: (isPending || isEncoding) ? 'not-allowed' : 'pointer',
              fontSize: 16,
              padding: '0 6px',
              fontWeight: 'bold',
              opacity: (isPending || isEncoding) ? 0.5 : 1,
            }}
          >
            +
          </button>
          <button
            onClick={() => !isPending && !isEncoding && onRefineModeChange(refineMode === 'remove' ? null : 'remove')}
            disabled={isPending || isEncoding}
            title={`${t('addNegativePoint')} [S]`}
            style={{
              background: refineMode === 'remove' ? '#fee2e2' : 'none',
              border: 'none',
              borderRadius: 4,
              color: refineMode === 'remove' ? '#b91c1c' : '#6b7280',
              cursor: (isPending || isEncoding) ? 'not-allowed' : 'pointer',
              fontSize: 16,
              padding: '0 6px',
              fontWeight: 'bold',
              opacity: (isPending || isEncoding) ? 0.5 : 1,
            }}
          >
            -
          </button>
        </>
      )}

      {isPending && (
        <>
          <div style={{ width: 1, height: 18, background: '#e5e7eb', flexShrink: 0 }} />
          <div style={{ display: 'flex', alignItems: 'center', marginLeft: 4 }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83">
                <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite" />
              </path>
            </svg>
          </div>
        </>
      )}

      <div style={{ width: 1, height: 18, background: '#e5e7eb', flexShrink: 0 }} />

      {onSmooth && (
        <button
          onClick={onSmooth}
          title={t('smoothPieceTooltip')}
          style={{
            background: 'none',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            color: '#374151',
            cursor: (isPending || isEncoding) ? 'not-allowed' : 'pointer',
            fontSize: 11,
            padding: '2px 8px',
            flexShrink: 0,
            marginRight: 4,
            opacity: (isPending || isEncoding) ? 0.5 : 1,
          }}
          disabled={isPending || isEncoding}
          onMouseEnter={e => { e.currentTarget.style.background = '#f3f4f6'; }}
          onMouseLeave={e => { e.currentTarget.style.background = 'none'; }}
        >
          {t('smooth')}
        </button>
      )}

      <button
        onClick={onDelete}
        title={t('deletePieceTooltip')}
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
        {t('delete')}
      </button>
    </div>
  );
}
