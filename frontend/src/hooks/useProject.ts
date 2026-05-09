import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import type { Project, TextureTransform, Crop, BoundingBox, Piece, Scale, GlassSheet } from '../types';
import { DEFAULT_PROJECT, EMPTY_PROJECT } from '../defaultProject';
import { GLASS_ASSETS } from '../assets';

const STORAGE_KEY = 'vitraux-project';

function loadProject(): Project {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return JSON.parse(saved) as Project;
  } catch {
    // ignore
  }
  return EMPTY_PROJECT;
}

function toPxPerMm(s: Scale): number {
  if (s.unit === 'mm') return s.pxPerUnit;
  if (s.unit === 'cm') return s.pxPerUnit / 10;
  return s.pxPerUnit / 25.4; // inches
}

function calibratedScale(patternScale: Scale | null, sheetScale: Scale | null): number | null {
  if (!patternScale || !sheetScale) return null;
  return toPxPerMm(sheetScale) / toPxPerMm(patternScale);
}

function applyScales(project: Project, sheetId?: string): Project {
  const pieces = project.pieces.map(p => {
    if (sheetId && p.glassSheetId !== sheetId) return p;
    const sheet = project.sheets.find(s => s.id === p.glassSheetId);
    const s = calibratedScale(project.patternScale, sheet?.scale ?? null);
    if (s === null) return p;
    return { ...p, transform: { ...p.transform, scale: s } };
  });
  return { ...project, pieces };
}

function makeNewSheet(prev: Project, t: (key: string) => string): GlassSheet {
  const glass = GLASS_ASSETS[prev.sheets.length % GLASS_ASSETS.length];
  return {
    id: `sheet-${Date.now()}`,
    label: `${t('sheet')} ${prev.sheets.length + 1}`,
    imageUrl: glass.url,
    crop: { top: 0, left: 0, bottom: 0, right: 0 },
    scale: null,
  };
}

export function useProject() {
  const { t } = useTranslation();
  const [project, setProject] = useState<Project>(loadProject);
  const [selectedPieceIds, setSelectedPieceIds] = useState<string[]>([]);
  const [activeSheetId, setActiveSheetId] = useState<string>(
    () => loadProject().sheets[0]?.id ?? ''
  );
  const [pendingPieceIds, setPendingPieceIds] = useState<ReadonlySet<string>>(new Set());
  const [undoStack, setUndoStack] = useState<Project[]>([]);
  const [redoStack, setRedoStack] = useState<Project[]>([]);

  // Keep activeSheetId valid if the active sheet is ever deleted
  useEffect(() => {
    if (project.sheets.length > 0 && !project.sheets.find(s => s.id === activeSheetId)) {
      setActiveSheetId(project.sheets[0].id);
    }
  }, [project.sheets, activeSheetId]);

  const pushHistory = useCallback((prev: Project) => {
    setUndoStack(u => [...u.slice(-49), prev]);
    setRedoStack([]);
  }, []);

  const updateProject = useCallback((updater: (p: Project) => Project, skipHistory = false) => {
    setProject(prev => {
      const next = updater(prev);
      if (!skipHistory) {
        setUndoStack(u => [...u.slice(-49), prev]);
        setRedoStack([]);
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const undo = useCallback(() => {
    setUndoStack(u => {
      if (u.length === 0) return u;
      const prev = u[u.length - 1];
      const newStack = u.slice(0, -1);
      setProject(current => {
        setRedoStack(r => [...r, current]);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(prev));
        return prev;
      });
      return newStack;
    });
  }, []);

  const redo = useCallback(() => {
    setRedoStack(r => {
      if (r.length === 0) return r;
      const next = r[r.length - 1];
      const newStack = r.slice(0, -1);
      setProject(current => {
        setUndoStack(u => [...u, current]);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        return next;
      });
      return newStack;
    });
  }, []);

  const updatePieceTransform = useCallback(
    (pieceId: string, transform: Partial<TextureTransform>, skipHistory = false) => {
      updateProject(prev => ({
        ...prev,
        pieces: prev.pieces.map(p =>
          p.id === pieceId ? { ...p, transform: { ...p.transform, ...transform } } : p
        ),
      }), skipHistory);
    },
    [updateProject]
  );

  const updatePiecePrompt = useCallback(
    (pieceId: string, promptBox: BoundingBox | undefined, promptPoints: Piece['promptPoints']) => {
      updateProject(prev => ({
        ...prev,
        pieces: prev.pieces.map(p =>
          p.id === pieceId ? { ...p, promptBox, promptPoints } : p
        ),
      }));
    },
    [updateProject]
  );

  const addPiecePromptPoint = useCallback((pieceId: string, point: { x: number; y: number; label: 1 | 0 }) => {
    updateProject(prev => ({
      ...prev,
      pieces: prev.pieces.map(p => 
        p.id === pieceId ? { ...p, promptPoints: [...(p.promptPoints || []), point] } : p
      )
    }));
  }, [updateProject]);

  const updatePatternCrop = useCallback((crop: Partial<Crop>) => {
    updateProject(prev => ({ ...prev, patternCrop: { ...prev.patternCrop, ...crop } }));
  }, [updateProject]);

  const updateSheetCrop = useCallback((sheetId: string, crop: Partial<Crop>) => {
    updateProject(prev => ({
      ...prev,
      sheets: prev.sheets.map(s =>
        s.id === sheetId ? { ...s, crop: { ...s.crop, ...crop } } : s
      ),
    }));
  }, [updateProject]);

  const selectPiece = useCallback((id: string | null, multi = false) => {
    setSelectedPieceIds(prev => {
      if (!id) return [];
      if (multi) {
        if (prev.includes(id)) return prev.filter(p => p !== id);
        return [...prev, id];
      }
      return [id];
    });
    if (id) {
      setProject(prev => {
        const piece = prev.pieces.find(p => p.id === id);
        if (piece) setActiveSheetId(piece.glassSheetId);
        return prev;
      });
    }
  }, []);

  const selectPieces = useCallback((ids: string[]) => {
    setSelectedPieceIds(ids);
    if (ids.length > 0) {
      setProject(prev => {
        const last = prev.pieces.find(p => p.id === ids[ids.length - 1]);
        if (last) setActiveSheetId(last.glassSheetId);
        return prev;
      });
    }
  }, []);

  const deletePiece = useCallback((pieceId: string) => {
    updateProject(prev => ({ ...prev, pieces: prev.pieces.filter(p => p.id !== pieceId) }));
    setSelectedPieceIds(ids => ids.filter(id => id !== pieceId));
  }, [updateProject]);

  const updatePieceLabel = useCallback((pieceId: string, label: string) => {
    updateProject(prev => ({
      ...prev,
      pieces: prev.pieces.map(p => p.id === pieceId ? { ...p, label } : p)
    }));
  }, [updateProject]);

  const updatePieceSheet = useCallback((pieceId: string, sheetId: string) => {
    updateProject(prev => {
      const sheet = prev.sheets.find(s => s.id === sheetId);
      const sw = sheet?.naturalWidth ?? 800;
      const sh = sheet?.naturalHeight ?? 600;
      const crop = sheet?.crop ?? { top: 0, left: 0, bottom: 0, right: 0 };
      const cx = (crop.left + sw - crop.right) / 2;
      const cy = (crop.top + sh - crop.bottom) / 2;

      const next = {
        ...prev,
        pieces: prev.pieces.map(p =>
          p.id === pieceId ? { ...p, glassSheetId: sheetId, transform: { ...p.transform, x: cx, y: cy } } : p
        )
      };
      return applyScales(next, sheetId);
    });
    setActiveSheetId(sheetId);
  }, [updateProject]);

  const deleteSheet = useCallback((sheetId: string) => {
    updateProject(prev => {
      if (prev.sheets.length <= 1) return prev;
      const remaining = prev.sheets.filter(s => s.id !== sheetId);
      const fallbackId = remaining[0].id;
      return {
        ...prev,
        sheets: remaining,
        pieces: prev.pieces.map(p => p.glassSheetId === sheetId ? { ...p, glassSheetId: fallbackId } : p),
      };
    });
  }, [updateProject]);

  const renameSheet = useCallback((sheetId: string, label: string) => {
    updateProject(prev => ({
      ...prev,
      sheets: prev.sheets.map(s => s.id === sheetId ? { ...s, label } : s)
    }));
  }, [updateProject]);

  const addSheet = useCallback(() => {
    updateProject(prev => {
      const newSheet = makeNewSheet(prev, t);
      setActiveSheetId(newSheet.id);
      return { ...prev, sheets: [...prev.sheets, newSheet] };
    });
  }, [updateProject, t]);

  const addSheetAndAssignPiece = useCallback((pieceId: string) => {
    updateProject(prev => {
      const newSheet = makeNewSheet(prev, t);
      setActiveSheetId(newSheet.id);
      
      // Default center for a new sheet
      const cx = 400; 
      const cy = 300;

      const next = {
        ...prev,
        sheets: [...prev.sheets, newSheet],
        pieces: prev.pieces.map(p =>
          p.id === pieceId ? { ...p, glassSheetId: newSheet.id, transform: { ...p.transform, x: cx, y: cy } } : p
        ),
      };
      return applyScales(next, newSheet.id);
    });
  }, [updateProject, t]);

  const updatePatternScale = useCallback((scale: Scale | null) => {
    updateProject(prev => applyScales({ ...prev, patternScale: scale }));
  }, [updateProject]);

  const updateSheetScale = useCallback((sheetId: string, scale: Scale | null) => {
    updateProject(prev => {
      const sheets = prev.sheets.map(s => s.id === sheetId ? { ...s, scale } : s);
      return applyScales({ ...prev, sheets }, sheetId);
    });
  }, [updateProject]);

  const addPieceFromBox = useCallback((box: BoundingBox, sheetId: string): string => {
    const { x1, y1, x2, y2 } = box;
    const polygon: Piece['polygon'] = [
      [x1, y1], [x2, y1], [x2, y2], [x1, y2],
    ];
    const id = crypto.randomUUID();
    updateProject(prev => {
      const label = `${t('piece')} ${prev.pieces.length + 1}`;
      const sheet = prev.sheets.find(s => s.id === sheetId);
      const s = calibratedScale(prev.patternScale, sheet?.scale ?? null) ?? 1;
      const sw = sheet?.naturalWidth ?? 800;
      const sh = sheet?.naturalHeight ?? 600;
      const crop = sheet?.crop ?? { top: 0, left: 0, bottom: 0, right: 0 };
      const cx = (crop.left + sw - crop.right) / 2;
      const cy = (crop.top + sh - crop.bottom) / 2;
      const newPiece: Piece = {
        id, label, polygon, glassSheetId: sheetId,
        transform: { x: cx, y: cy, rotation: 0, scale: s },
        promptBox: box, promptPoints: [],
      };
      setSelectedPieceIds([newPiece.id]);
      return { ...prev, pieces: [...prev.pieces, newPiece] };
    });
    return id;
  }, [updateProject, t]);

  const updateSheetDimensions = useCallback((sheetId: string, w: number, h: number) => {
    updateProject(prev => {
      const sheet = prev.sheets.find(s => s.id === sheetId);
      if (!sheet || (sheet.naturalWidth === w && sheet.naturalHeight === h)) return prev;
      return { ...prev, sheets: prev.sheets.map(s => s.id === sheetId ? { ...s, naturalWidth: w, naturalHeight: h } : s) };
    }, true); // skip history for metadata updates like dimensions
  }, [updateProject]);

  const batchAddPieces = useCallback((polygons: [number, number][][], sheetId: string) => {
    updateProject(prev => {
      const sheet = prev.sheets.find(s => s.id === sheetId);
      const s = calibratedScale(prev.patternScale, sheet?.scale ?? null) ?? 1;
      const sw = sheet?.naturalWidth ?? 800;
      const sh = sheet?.naturalHeight ?? 600;
      const crop = sheet?.crop ?? { top: 0, left: 0, bottom: 0, right: 0 };
      const cx = (crop.left + sw - crop.right) / 2;
      const cy = (crop.top + sh - crop.bottom) / 2;
      const newPieces: Piece[] = polygons.map((polygon, i) => {
        const xs = polygon.map(p => p[0]);
        const ys = polygon.map(p => p[1]);
        const box: BoundingBox = {
          x1: Math.min(...xs), y1: Math.min(...ys),
          x2: Math.max(...xs), y2: Math.max(...ys),
        };
        return {
          id: crypto.randomUUID(),
          label: `${t('piece')} ${prev.pieces.length + i + 1}`,
          polygon, glassSheetId: sheetId,
          transform: { x: cx, y: cy, rotation: 0, scale: s },
          promptBox: box, promptPoints: [],
        };
      });
      return { ...prev, pieces: [...prev.pieces, ...newPieces] };
    });
  }, [updateProject, t]);

  const updatePiecePolygon = useCallback((pieceId: string, polygon: [number, number][]) => {
    updateProject(prev => ({
      ...prev,
      pieces: prev.pieces.map(p => p.id === pieceId ? { ...p, polygon } : p)
    }));
  }, [updateProject]);

  const markPiecePending = useCallback((pieceId: string) => {
    setPendingPieceIds(s => new Set(s).add(pieceId));
  }, []);

  const unmarkPiecePending = useCallback((pieceId: string) => {
    setPendingPieceIds(s => { const n = new Set(s); n.delete(pieceId); return n; });
  }, []);

  const resetProject = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setProject(EMPTY_PROJECT);
    setSelectedPieceIds([]);
    setActiveSheetId('');
  }, []);

  const loadProjectData = useCallback((newProject: Project) => {
    setProject(persist(newProject));
    setSelectedPieceIds([]);
    setActiveSheetId(newProject.sheets[0]?.id ?? '');
  }, []);

  const updatePatternImage = useCallback((url: string, width: number, height: number) => {
    updateProject(prev => ({
      ...prev,
      patternImageUrl: url,
      patternWidth: width,
      patternHeight: height,
      patternCrop: { top: 0, left: 0, bottom: 0, right: 0 },
      patternScale: null,
    }));
  }, [updateProject]);

  const addSheetFromImage = useCallback((url: string, label: string) => {
    const id = `sheet-${Date.now()}`;
    updateProject(prev => {
      const newSheet: GlassSheet = {
        id, label, imageUrl: url,
        crop: { top: 0, left: 0, bottom: 0, right: 0 },
        scale: null,
      };
      setActiveSheetId(id);
      return { ...prev, sheets: [...prev.sheets, newSheet] };
    });
  }, [updateProject]);

  return {
    project,
    selectedPieceIds,
    activeSheetId,
    pendingPieceIds,
    setActiveSheetId,
    selectPiece,
    selectPieces,
    updatePieceTransform,
    updatePatternCrop,
    updateSheetCrop,
    deletePiece,
    updatePieceLabel,
    updatePieceSheet,
    deleteSheet,
    renameSheet,
    addSheet,
    addSheetAndAssignPiece,
    updatePatternScale,
    updateSheetScale,
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
    canUndo: undoStack.length > 0,
    canRedo: redoStack.length > 0,
    resetProject,
    loadProjectData,
    updatePatternImage,
    addSheetFromImage,
  };
}
