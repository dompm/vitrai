import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Piece, GlassSheet, Scale } from '../types';
import { IconTrash, IconSmooth, IconPlus, IconClose } from './icons';

interface MultiSelectionProps {
  count: number;
  sheets: GlassSheet[];
  onBulkSheetChange: (sheetId: string) => void;
  onBulkDelete: () => void;
  onBulkSmooth: () => void;
}

interface SingleSelectionProps {
  piece: Piece;
  sheets: GlassSheet[];
  patternScale: Scale | null;
  isPending: boolean;
  isEncoding: boolean;
  refineMode: 'add' | 'remove' | null;
  onLabelChange: (label: string) => void;
  onSheetChange: (sheetId: string) => void;
  onAddSheet: () => void;
  onNotesChange: (notes: string) => void;
  onRefineModeChange: (mode: 'add' | 'remove' | null) => void;
  onSmooth: () => void;
  onDelete: () => void;
}

type InspectorProps =
  | { kind: 'empty' }
  | ({ kind: 'single' } & SingleSelectionProps)
  | ({ kind: 'multi' } & MultiSelectionProps);

function polygonBounds(polygon: [number, number][]): { w: number; h: number } {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const [x, y] of polygon) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }
  return { w: maxX - minX, h: maxY - minY };
}

function formatRealSize(pxW: number, pxH: number, scale: Scale | null, t: (k: string) => string): string {
  if (!scale || scale.pxPerUnit === 0) return '— × —';
  const w = pxW / scale.pxPerUnit;
  const h = pxH / scale.pxPerUnit;
  const fmt = (n: number) => parseFloat(n.toPrecision(3)).toString();
  return `${fmt(w)} × ${fmt(h)} ${t('unit_' + scale.unit)}`;
}

function SinglePiece(props: SingleSelectionProps) {
  const { t } = useTranslation();
  const {
    piece, sheets, patternScale, isPending, isEncoding, refineMode,
    onLabelChange, onSheetChange, onAddSheet, onNotesChange, onRefineModeChange, onSmooth, onDelete,
  } = props;

  const [labelDraft, setLabelDraft] = useState(piece.label);
  const [labelEditing, setLabelEditing] = useState(false);
  const labelRef = useRef<HTMLInputElement>(null);
  const [notesDraft, setNotesDraft] = useState(piece.notes ?? '');
  const notesDebounce = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => { setLabelDraft(piece.label); setLabelEditing(false); }, [piece.id, piece.label]);
  useEffect(() => { setNotesDraft(piece.notes ?? ''); }, [piece.id, piece.notes]);
  useEffect(() => { if (labelEditing) labelRef.current?.select(); }, [labelEditing]);
  useEffect(() => () => clearTimeout(notesDebounce.current), []);

  function commitLabel() {
    const trimmed = labelDraft.trim();
    if (trimmed && trimmed !== piece.label) onLabelChange(trimmed);
    else setLabelDraft(piece.label);
    setLabelEditing(false);
  }

  function handleNotesChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const v = e.target.value;
    setNotesDraft(v);
    clearTimeout(notesDebounce.current);
    notesDebounce.current = setTimeout(() => onNotesChange(v), 250);
  }

  function handleSheetSelect(e: React.ChangeEvent<HTMLSelectElement>) {
    if (e.target.value === '__new__') onAddSheet();
    else onSheetChange(e.target.value);
  }

  const bounds = polygonBounds(piece.polygon);
  const realSize = formatRealSize(bounds.w, bounds.h, patternScale, t);

  return (
    <div className="inspector-body">
      <div className="inspector-section inspector-heading">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="inspector-eyebrow">{t('piece')} {piece.label}</div>
          {labelEditing ? (
            <input
              ref={labelRef}
              className="inspector-title-input"
              value={labelDraft}
              onChange={e => setLabelDraft(e.target.value)}
              onBlur={commitLabel}
              onKeyDown={e => {
                if (e.key === 'Enter') { e.preventDefault(); commitLabel(); }
                if (e.key === 'Escape') { setLabelDraft(piece.label); setLabelEditing(false); }
              }}
            />
          ) : (
            <button
              className="inspector-title"
              onClick={() => setLabelEditing(true)}
              title={t('clickToRename')}
            >
              {piece.label}
            </button>
          )}
        </div>
        <button
          className="inspector-icon-btn inspector-icon-btn-danger"
          onClick={onDelete}
          title={t('deletePieceTooltip')}
        >
          <IconTrash size={16} />
        </button>
      </div>

      <div className="inspector-section">
        <label className="inspector-field-label">{t('inspectorGlassSheet')}</label>
        <select
          className="inspector-select"
          value={piece.glassSheetId}
          onChange={handleSheetSelect}
        >
          {!sheets.some(s => s.id === piece.glassSheetId) && (
            <option value={piece.glassSheetId} disabled>—</option>
          )}
          {sheets.map(s => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
          <option disabled>──────</option>
          <option value="__new__">{t('addSheetOption')}</option>
        </select>
      </div>

      <div className="inspector-section">
        <label className="inspector-field-label">{t('inspectorApproxSize')}</label>
        <div className="inspector-static">{realSize}</div>
      </div>

      <div className="inspector-section">
        <label className="inspector-field-label">{t('inspectorRefineShape')}</label>
        <div className="inspector-refine-row">
          <button
            className={`inspector-pill ${refineMode === 'add' ? 'is-active is-add' : ''}`}
            onClick={() => !isPending && !isEncoding && onRefineModeChange(refineMode === 'add' ? null : 'add')}
            disabled={isPending || isEncoding}
            title={`${t('addPositivePoint')} [A]`}
          >
            <IconPlus size={14} /> {t('inspectorAddRegion')}
          </button>
          <button
            className={`inspector-pill ${refineMode === 'remove' ? 'is-active is-remove' : ''}`}
            onClick={() => !isPending && !isEncoding && onRefineModeChange(refineMode === 'remove' ? null : 'remove')}
            disabled={isPending || isEncoding}
            title={`${t('addNegativePoint')} [S]`}
          >
            <IconClose size={14} /> {t('inspectorCutShape')}
          </button>
        </div>
        <button
          className="inspector-text-btn"
          onClick={onSmooth}
          disabled={isPending || isEncoding}
          title={t('smoothPieceTooltip')}
        >
          <IconSmooth size={14} /> {t('inspectorSmoothCorners')}
        </button>
      </div>

      <div className="inspector-section">
        <label className="inspector-field-label" htmlFor={`notes-${piece.id}`}>{t('inspectorNotes')}</label>
        <textarea
          id={`notes-${piece.id}`}
          className="inspector-textarea"
          value={notesDraft}
          onChange={handleNotesChange}
          placeholder={t('inspectorNotesPlaceholder')}
          rows={3}
        />
      </div>
    </div>
  );
}

function MultiSelection({ count, sheets, onBulkSheetChange, onBulkDelete, onBulkSmooth }: MultiSelectionProps) {
  const { t } = useTranslation();
  return (
    <div className="inspector-body">
      <div className="inspector-section inspector-heading">
        <div style={{ flex: 1 }}>
          <div className="inspector-eyebrow">{t('inspectorSelection')}</div>
          <div className="inspector-title-static">{t('inspectorPiecesSelected', { count })}</div>
        </div>
      </div>

      <div className="inspector-section">
        <label className="inspector-field-label">{t('inspectorChangeGlass')}</label>
        <select
          className="inspector-select"
          defaultValue=""
          onChange={e => { if (e.target.value) onBulkSheetChange(e.target.value); }}
        >
          <option value="">—</option>
          {sheets.map(s => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>
      </div>

      <div className="inspector-section">
        <button className="inspector-text-btn" onClick={onBulkSmooth}>
          <IconSmooth size={14} /> {t('inspectorSmoothAll')}
        </button>
        <button className="inspector-text-btn inspector-text-btn-danger" onClick={onBulkDelete}>
          <IconTrash size={14} /> {t('inspectorDeleteAll')}
        </button>
      </div>
    </div>
  );
}

function EmptyInspector() {
  const { t } = useTranslation();
  return (
    <div className="inspector-empty">
      <p>{t('inspectorEmpty')}</p>
    </div>
  );
}

export function Inspector(props: InspectorProps) {
  const { t } = useTranslation();
  return (
    <div className="panel panel-inspector">
      <div className="panel-header">
        <div className="panel-title">
          <span className="panel-title-eyebrow">{t('inspectorTitle')}</span>
        </div>
      </div>
      {props.kind === 'empty' ? (
        <EmptyInspector />
      ) : props.kind === 'single' ? (
        <SinglePiece {...props} />
      ) : (
        <MultiSelection {...props} />
      )}
    </div>
  );
}
