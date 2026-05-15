import { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { Project, TextureTransform, Crop, BoundingBox, Piece, Scale, GlassSheet } from '../types';
import { DEFAULT_PROJECT, EMPTY_PROJECT } from '../defaultProject';
import { GLASS_ASSETS } from '../assets';
import { listProjects, loadProjectFromOPFS, saveToOPFS, deleteFromOPFS } from '../storage/opfs';

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
  const [project, setProject] = useState<Project>(EMPTY_PROJECT);
  const [isLoaded, setIsLoaded] = useState(false);
  const [selectedPieceIds, setSelectedPieceIds] = useState<string[]>([]);
  const [activeSheetId, setActiveSheetId] = useState<string>('');
  const [pendingPieceIds, setPendingPieceIds] = useState<ReadonlySet<string>>(new Set());
  const [undoStack, setUndoStack] = useState<Project[]>([]);
  const [redoStack, setRedoStack] = useState<Project[]>([]);
  const [availableProjects, setAvailableProjects] = useState<string[]>([]);
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'error'>('saved');
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>(null);
  const savingIndicatorTimerRef = useRef<ReturnType<typeof setTimeout>>(null);
  const latestProjectRef = useRef(project);
  latestProjectRef.current = project;

  const persist = useCallback(async (p: Project, name: string) => {
    if (savingIndicatorTimerRef.current) clearTimeout(savingIndicatorTimerRef.current);
    savingIndicatorTimerRef.current = setTimeout(() => {
      setSaveStatus(s => (s === 'saved' || s === 'error' ? 'saving' : s));
    }, 200);
    try {
      await saveToOPFS(p, name);
      if (savingIndicatorTimerRef.current) clearTimeout(savingIndicatorTimerRef.current);
      setSaveStatus('saved');
    } catch (err) {
      if (savingIndicatorTimerRef.current) clearTimeout(savingIndicatorTimerRef.current);
      console.error('[useProject] save failed', err);
      setSaveStatus('error');
    }
  }, []);

  const retrySave = useCallback(() => {
    const p = latestProjectRef.current;
    void persist(p, p.name);
  }, [persist]);

  const refreshProjectList = useCallback(async () => {
    const names = await listProjects();
    setAvailableProjects(names);
  }, []);

  const flushSave = useCallback(() => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const p = latestProjectRef.current;
    return persist(p, p.name);
  }, [persist]);

  useEffect(() => {
    const last = localStorage.getItem('vitraux-last-project') ?? 'default';
    loadProjectFromOPFS(last).then(async p => {
      if (p) {
        setProject(p);
        setActiveSheetId(p.sheets[0]?.id ?? '');
      } else {
        const fresh = { ...EMPTY_PROJECT, name: last };
        setProject(fresh);
        await saveToOPFS(fresh, last);
      }
      setIsLoaded(true);
      refreshProjectList();
    });
  }, [refreshProjectList]);

  // Keep activeSheetId valid if the active sheet is ever deleted
  useEffect(() => {
    if (project.sheets.length > 0 && !project.sheets.find(s => s.id === activeSheetId)) {
      setActiveSheetId(project.sheets[0].id);
    }
  }, [project.sheets, activeSheetId]);

  const updateProject = useCallback((updater: (p: Project) => Project, skipHistory = false) => {
    setProject(prev => {
      const next = updater(prev);
      if (!skipHistory) {
        setUndoStack(u => [...u.slice(-49), prev]);
        setRedoStack([]);
      }
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        void persist(next, next.name);
        refreshProjectList();
      }, 500);
      return next;
    });
  }, [refreshProjectList, persist]);

  const undo = useCallback(() => {
    setUndoStack(u => {
      if (u.length === 0) return u;
      const prev = u[u.length - 1];
      const newStack = u.slice(0, -1);
      setProject(current => {
        setRedoStack(r => [...r, current]);
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        saveTimerRef.current = setTimeout(() => { void persist(prev, prev.name); }, 500);
        return prev;
      });
      return newStack;
    });
  }, [persist]);

  const redo = useCallback(() => {
    setRedoStack(r => {
      if (r.length === 0) return r;
      const next = r[r.length - 1];
      const newStack = r.slice(0, -1);
      setProject(current => {
        setUndoStack(u => [...u, current]);
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        saveTimerRef.current = setTimeout(() => { void persist(next, next.name); }, 500);
        return next;
      });
      return newStack;
    });
  }, [persist]);

  const setProjectName = useCallback((name: string) => {
    const oldName = project.name;
    updateProject(prev => ({ ...prev, name }));
    void deleteFromOPFS(oldName);
    localStorage.setItem('vitraux-last-project', name);
  }, [project.name, updateProject]);

  const createNewProject = useCallback(async (name: string) => {
    await flushSave();
    const newProject = { ...EMPTY_PROJECT, name };
    setProject(newProject);
    setUndoStack([]);
    setRedoStack([]);
    setActiveSheetId('');
    setSelectedPieceIds([]);
    localStorage.setItem('vitraux-last-project', name);
    await saveToOPFS(newProject, name);
    await refreshProjectList();
  }, [flushSave, refreshProjectList]);

  const switchProject = useCallback(async (name: string) => {
    await flushSave();
    const p = await loadProjectFromOPFS(name);
    if (p) {
      setProject(p);
      setUndoStack([]);
      setRedoStack([]);
      setActiveSheetId(p.sheets[0]?.id ?? '');
      setSelectedPieceIds([]);
      localStorage.setItem('vitraux-last-project', name);
    }
  }, [flushSave]);

  const deleteProject = useCallback(async (name: string) => {
    await deleteFromOPFS(name);
    if (project.name === name) {
      // Cancel any pending save — don't flush, the project is being deleted
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
      const others = availableProjects.filter(n => n !== name);
      if (others.length > 0) {
        const p = await loadProjectFromOPFS(others[0]);
        if (p) {
          setProject(p);
          setUndoStack([]);
          setRedoStack([]);
          setActiveSheetId(p.sheets[0]?.id ?? '');
          setSelectedPieceIds([]);
          localStorage.setItem('vitraux-last-project', p.name);
        }
      } else {
        const fresh = { ...EMPTY_PROJECT, name: 'default' };
        setProject(fresh);
        setUndoStack([]);
        setRedoStack([]);
        setActiveSheetId('');
        setSelectedPieceIds([]);
        localStorage.setItem('vitraux-last-project', 'default');
        await saveToOPFS(fresh, 'default');
      }
    }
    await refreshProjectList();
  }, [project.name, availableProjects, refreshProjectList]);

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

  const updateSheetSwatch = useCallback((sheetId: string, swatch: string) => {
    updateProject(prev => ({
      ...prev,
      sheets: prev.sheets.map(s => s.id === sheetId ? { ...s, swatch } : s)
    }), true);
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
      const remaining = prev.sheets.filter(s => s.id !== sheetId);
      const fallbackId = remaining[0]?.id ?? '';
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

  const addSheetAndAssignPiece = useCallback((pieceId: string, url?: string, label?: string) => {
    updateProject(prev => {
      const newSheet = makeNewSheet(prev, t);
      if (url) newSheet.imageUrl = url;
      if (label) newSheet.label = label;
      
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
    }), true);
  }, [updateProject]);

  const markPiecePending = useCallback((pieceId: string) => {
    setPendingPieceIds(s => new Set(s).add(pieceId));
  }, []);

  const unmarkPiecePending = useCallback((pieceId: string) => {
    setPendingPieceIds(s => { const n = new Set(s); n.delete(pieceId); return n; });
  }, []);

  const loadProjectData = useCallback((newProject: Project) => {
    setProject(newProject);
    void saveToOPFS(newProject, newProject.name);
    localStorage.setItem('vitraux-last-project', newProject.name);
    setSelectedPieceIds([]);
    setActiveSheetId(newProject.sheets[0]?.id ?? '');
    refreshProjectList();
  }, [refreshProjectList]);

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
    isLoaded,
    availableProjects,
    selectedPieceIds,
    activeSheetId,
    pendingPieceIds,
    setActiveSheetId,
    setProjectName,
    createNewProject,
    switchProject,
    deleteProject,
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
    updateSheetSwatch,
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
    saveStatus,
    retrySave,
    loadProjectData,
    updatePatternImage,
    addSheetFromImage,
  };
}
