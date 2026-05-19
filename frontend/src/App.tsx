import { useEffect, useState, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ResultPanel } from './components/ResultPanel';
import { SheetPanel } from './components/SheetPanel';
import { useProject } from './hooks/useProject';
import { subtractPolygons, computeCentroid, snapPolygonToNeighbors, smoothPolygon } from './utils/geometry';
import { computeImageSwatch } from './utils/swatch';
import { getSamBackend } from './samBackend';
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

const getSnapRadius = (width: number) => Math.max(8, Math.min(40, width * 0.01));

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
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(sheet.label);
  const [menuPos, setMenuPos] = useState<{ x: number; y: number } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);

  useEffect(() => { setDraft(sheet.label); }, [sheet.label]);
  useEffect(() => { if (editing) inputRef.current?.select(); }, [editing]);

  useEffect(() => {
    if (!menuPos) return;
    function close() { setMenuPos(null); }
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', close);
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', close);
    };
  }, [menuPos]);

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
        className={`sheet-tab ${isActive ? 'active' : ''}`}
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
          >
            {t('contextRename')}
          </button>
          {canDelete && (
            <button
              className="sheet-tab-menu-item sheet-tab-menu-item-danger"
              onClick={() => { setMenuPos(null); onDelete(); }}
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
    updatePatternCrop,
    updatePatternScale,
    updateSheetCrop,
    updateSheetScale,
    deletePiece,
    updatePieceLabel,
    updatePieceSheet,
    deleteSheet,
    renameSheet,
    updateSheetSwatch,
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
    saveStatus,
    retrySave,
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
      piece.polygon.forEach(pt => {
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
      const pts = piece.polygon.map(p => `${p[0]},${p[1]}`).join(' ');
      const c = computeCentroid(piece.polygon);
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

          <div style={{ width: 1, height: 16, background: 'var(--hairline-2)', margin: '0 4px' }} />

          {/* Undo / Redo */}
          <button className="btn-ghost" onClick={undo} disabled={!canUndo} title="Undo (Ctrl+Z)" style={{ padding: '4px 8px' }}>
            <UndoIcon />
          </button>
          <button className="btn-ghost" onClick={redo} disabled={!canRedo} title="Redo (Ctrl+Y)" style={{ padding: '4px 8px' }}>
            <RedoIcon />
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
              {t('load')}
              <input type="file" accept=".json" style={{ display: 'none' }} onChange={handleLoadProject} />
            </label>
            <button className="btn-ghost" onClick={handleSaveProject} title={t('saveTooltip')}>
              {t('save')}
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
            🌐 {i18n.language === 'fr' ? 'Switch to English' : 'Passer en français'}
          </button>

          <div className="mobile-drawer-divider" />

          <label className="mobile-drawer-item" style={{ cursor: 'pointer' }}>
            📂 {t('load')}
            <input type="file" accept=".json" style={{ display: 'none' }} onChange={e => { handleLoadProject(e); setIsMobileMenuOpen(false); }} />
          </label>

          <button className="mobile-drawer-item" onClick={() => { handleSaveProject(); setIsMobileMenuOpen(false); }}>
            💾 {t('save')}
          </button>

          <div className="mobile-drawer-divider" />

          <button className="mobile-drawer-item" onClick={() => { handlePrint(); setIsMobileMenuOpen(false); }}>
            🖨️ {t('print')}
          </button>
        </div>
      </div>
  </div>
  );
}
