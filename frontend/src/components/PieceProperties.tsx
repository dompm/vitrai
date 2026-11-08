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
  onStraighten?: () => void;
  refineMode?: 'add' | 'remove' | null;
  onRefineModeChange?: (mode: 'add' | 'remove' | null) => void;
  isPending?: boolean;
  isEncoding?: boolean;
  pointerEvents?: 'auto' | 'none';
  multiple?: boolean;
}

export function PieceProperties({
  piece,
  sheets,
  onLabelChange,
  onSheetChange,
  onAddSheet,
  onDelete,
  onSmooth,
  onStraighten,
  refineMode,
  onRefineModeChange,
  isPending,
  isEncoding,
  pointerEvents = 'auto',
  multiple,
}: Props) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(piece.label);
  const [deleteHover, setDeleteHover] = useState(false);
  const [smoothHover, setSmoothHover] = useState(false);
  const [straightenHover, setStraightenHover] = useState(false);
  const [selectHover, setSelectHover] = useState(false);
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

  const currentSheet = sheets.find(s => s.id === piece.glassSheetId);

  return (
    <div
      onPointerDown={e => e.stopPropagation()}
      onClick={e => e.stopPropagation()}
      onWheel={e => e.stopPropagation()}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '5px 12px',
        background: '#ffffff',
        border: '1px solid rgba(0, 0, 0, 0.08)',
        borderRadius: 8,
        boxShadow: '0 4px 16px rgba(0, 0, 0, 0.08), 0 1px 3px rgba(0, 0, 0, 0.04)',
        flexShrink: 0,
        minHeight: 38,
        pointerEvents,
      }}
    >
      {/* ── Group 1: Piece Label ── */}
      {editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commitLabel}
          onKeyDown={handleLabelKeyDown}
          style={{
            width: 110,
            padding: '2px 6px',
            border: '1px solid #C48820',
            borderRadius: 5,
            fontSize: 12,
            outline: 'none',
            background: '#ffffff',
            color: 'var(--text-bright)',
            fontFamily: 'inherit',
          }}
          disabled={multiple}
        />
      ) : (
        <span
          onClick={() => { if (!multiple) setEditing(true); }}
          title={multiple ? '' : t('clickToRename')}
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: multiple ? 'var(--text-dim)' : 'var(--text-bright)',
            cursor: multiple ? 'default' : 'text',
            minWidth: 50,
            maxWidth: 140,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            padding: '3px 6px',
            borderRadius: 5,
            transition: 'background-color 0.15s ease',
          }}
          onMouseEnter={e => { if (!multiple) e.currentTarget.style.backgroundColor = '#F4F2ED'; }}
          onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent'; }}
        >
          {piece.label}
        </span>
      )}

      {/* ── Divider 1 ── */}
      <div style={{ width: 1, height: 16, background: '#E6E3DC', flexShrink: 0 }} />

      {/* ── Group 2: Sheet Selector with Swatch Dot ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 11, color: 'var(--text-dim)', fontWeight: 500 }}>{t('sheet')}:</span>
        <div
          onMouseEnter={() => setSelectHover(true)}
          onMouseLeave={() => setSelectHover(false)}
          style={{
            position: 'relative',
            display: 'inline-flex',
            alignItems: 'center',
          }}
        >
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              background: selectHover ? '#E5E2DA' : '#F4F2ED',
              borderRadius: 6,
              padding: '3px 8px',
              fontSize: 12,
              color: 'var(--text-bright)',
              fontWeight: 500,
              pointerEvents: 'none',
              transition: 'background-color 0.15s ease',
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                backgroundColor: currentSheet?.swatch ?? '#78716C',
                display: 'inline-block',
                flexShrink: 0,
                boxShadow: '0 0 0 1px rgba(0, 0, 0, 0.12)',
              }}
            />
            <span style={{ maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {currentSheet?.label ?? (piece.glassSheetId === '__multiple__' ? '—' : t('sheet'))}
            </span>
            <span style={{ fontSize: 9, color: 'var(--text-dim)', marginLeft: 1 }}>▾</span>
          </div>
          <select
            data-tutorial-target="piece-glass-select"
            value={piece.glassSheetId}
            onChange={handleSheetSelect}
            style={{
              position: 'absolute',
              inset: 0,
              opacity: 0,
              cursor: 'pointer',
              width: '100%',
              height: '100%',
              border: 'none',
              outline: 'none',
            }}
          >
            <option value="__multiple__" disabled hidden>—</option>
            {!sheets.some(s => s.id === piece.glassSheetId) && piece.glassSheetId !== '__multiple__' && (
              <option value={piece.glassSheetId} disabled>—</option>
            )}
            {sheets.map(s => (
              <option key={s.id} value={s.id}>{s.label}</option>
            ))}
            <option disabled>──────</option>
            <option value="__new__">{t('addSheetOption')}</option>
          </select>
        </div>
      </div>

      {/* ── Divider 2 ── */}
      <div style={{ width: 1, height: 16, background: '#E6E3DC', flexShrink: 0 }} />

      {/* ── Group 3: Actions (+, -, Smooth, Pending) ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        {onRefineModeChange && (
          <div data-tutorial-target="piece-refine-buttons" style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <button
              data-tutorial-target="piece-refine-add"
              onClick={() => !isPending && !isEncoding && !multiple && onRefineModeChange(refineMode === 'add' ? null : 'add')}
              disabled={isPending || isEncoding || multiple}
              title={`${t('addPositivePoint')} [A]`}
              style={{
                background: refineMode === 'add' ? '#292524' : '#F4F2ED',
                border: 'none',
                borderRadius: 5,
                color: refineMode === 'add' ? '#ffffff' : 'var(--text-soft)',
                cursor: (isPending || isEncoding || multiple) ? 'not-allowed' : 'pointer',
                fontSize: 14,
                width: 24,
                height: 24,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 600,
                opacity: (isPending || isEncoding || multiple) ? 0.4 : 1,
                transition: 'all 0.15s ease',
              }}
            >
              +
            </button>
            <button
              data-tutorial-target="piece-refine-remove"
              onClick={() => !isPending && !isEncoding && !multiple && onRefineModeChange(refineMode === 'remove' ? null : 'remove')}
              disabled={isPending || isEncoding || multiple}
              title={`${t('addNegativePoint')} [S]`}
              style={{
                background: refineMode === 'remove' ? '#DC2626' : '#F4F2ED',
                border: 'none',
                borderRadius: 5,
                color: refineMode === 'remove' ? '#ffffff' : 'var(--text-soft)',
                cursor: (isPending || isEncoding || multiple) ? 'not-allowed' : 'pointer',
                fontSize: 14,
                width: 24,
                height: 24,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 600,
                opacity: (isPending || isEncoding || multiple) ? 0.4 : 1,
                transition: 'all 0.15s ease',
              }}
            >
              −
            </button>
          </div>
        )}

        {isPending && (
          <div style={{ display: 'flex', alignItems: 'center', padding: '0 4px' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#C48820" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83">
                <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite" />
              </path>
            </svg>
          </div>
        )}

        {onSmooth && (
          <button
            onClick={onSmooth}
            title={t('smoothPieceTooltip')}
            disabled={isPending || isEncoding}
            onMouseEnter={() => setSmoothHover(true)}
            onMouseLeave={() => setSmoothHover(false)}
            style={{
              background: smoothHover ? '#E5E2DA' : '#F4F2ED',
              border: 'none',
              borderRadius: 6,
              color: 'var(--text-soft)',
              cursor: (isPending || isEncoding) ? 'not-allowed' : 'pointer',
              fontSize: 11.5,
              fontWeight: 500,
              padding: '4px 9px',
              flexShrink: 0,
              opacity: (isPending || isEncoding) ? 0.4 : 1,
              fontFamily: 'inherit',
              transition: 'background-color 0.15s ease',
            }}
          >
            {t('smooth')}
          </button>
        )}

        {onStraighten && (
          <button
            onClick={onStraighten}
            title={t('straightenPieceTooltip', 'Reset curved edges to crisp straight lines')}
            disabled={isPending || isEncoding}
            onMouseEnter={() => setStraightenHover(true)}
            onMouseLeave={() => setStraightenHover(false)}
            style={{
              background: straightenHover ? '#E5E2DA' : '#F4F2ED',
              border: 'none',
              borderRadius: 6,
              color: 'var(--text-soft)',
              cursor: (isPending || isEncoding) ? 'not-allowed' : 'pointer',
              fontSize: 11.5,
              fontWeight: 500,
              padding: '4px 9px',
              flexShrink: 0,
              opacity: (isPending || isEncoding) ? 0.4 : 1,
              fontFamily: 'inherit',
              transition: 'background-color 0.15s ease',
            }}
          >
            {t('straighten', 'Straighten')}
          </button>
        )}
      </div>

      {/* ── Divider 3 ── */}
      <div style={{ width: 1, height: 16, background: '#E6E3DC', flexShrink: 0 }} />

      {/* ── Group 4: Delete Action (neutral muted by default, red on hover) ── */}
      <button
        onClick={onDelete}
        title={t('deletePieceTooltip')}
        data-tutorial-target="piece-delete"
        onMouseEnter={() => setDeleteHover(true)}
        onMouseLeave={() => setDeleteHover(false)}
        style={{
          background: deleteHover ? '#FEF2F2' : 'transparent',
          border: 'none',
          borderRadius: 6,
          color: deleteHover ? '#DC2626' : '#78716C',
          cursor: 'pointer',
          fontSize: 11.5,
          fontWeight: 500,
          padding: '4px 9px',
          flexShrink: 0,
          fontFamily: 'inherit',
          transition: 'all 0.15s ease',
        }}
      >
        {t('delete')}
      </button>
    </div>
  );
}
