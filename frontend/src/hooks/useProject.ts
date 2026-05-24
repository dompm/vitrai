import { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { Project, TextureTransform, Crop, BoundingBox, Piece, Scale, GlassSheet, SolderColor } from '../types';
import { EMPTY_PROJECT } from '../defaultProject';
import { DEFAULT_GLASS_ASSETS } from '../assets';
import { listProjects, loadProjectFromOPFS, saveToOPFS, deleteFromOPFS } from '../storage/opfs';
import { computeUnrolledLamp, reflowLampPoints, replicatePointToFacet, patternToSurfaceRobust } from '../utils/lampGeometry';

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
  const glass = DEFAULT_GLASS_ASSETS[prev.sheets.length % DEFAULT_GLASS_ASSETS.length];
  return {
    id: `sheet-${Date.now()}`,
    label: `${t('sheet')} ${prev.sheets.length + 1}`,
    imageUrl: glass.url,
    crop: { top: 0, left: 0, bottom: 0, right: 0 },
    scale: null,
  };
}

/** Strip the last filename extension (e.g. "amber-rose.jpg" → "amber-rose"). */
function stripExtension(name: string): string {
  return name.replace(/\.[^./\\]+$/, '');
}

function sheetCenter(sheet: GlassSheet | undefined) {
  const sw = sheet?.naturalWidth ?? 800;
  const sh = sheet?.naturalHeight ?? 600;
  const crop = sheet?.crop ?? { top: 0, left: 0, bottom: 0, right: 0 };
  return {
    x: (crop.left + sw - crop.right) / 2,
    y: (crop.top + sh - crop.bottom) / 2,
  };
}

function fitScaleForPiece(polygon: [number, number][], sheet: GlassSheet | undefined): number {
  const xs = polygon.map(p => p[0]);
  const ys = polygon.map(p => p[1]);
  const pw = Math.max(...xs) - Math.min(...xs);
  const ph = Math.max(...ys) - Math.min(...ys);
  if (pw <= 0 || ph <= 0) return 1;
  const sw = (sheet?.naturalWidth ?? 800) - (sheet?.crop.left ?? 0) - (sheet?.crop.right ?? 0);
  const sh = (sheet?.naturalHeight ?? 600) - (sheet?.crop.top ?? 0) - (sheet?.crop.bottom ?? 0);
  if (sw <= 0 || sh <= 0) return 1;
  return Math.min(sw / pw, sh / ph) * 0.95;
}

function syncSymmetricPieces(
  pieces: Piece[],
  targetPieceId: string,
  newPolygon: [number, number][] | undefined,
  newCurvePoints: import('../types').CurvePoint[] | undefined,
  lampConfig: import('../types').LampConfig | undefined | null,
  isSymmetryEnabled: boolean
): Piece[] {
  if (!lampConfig || !isSymmetryEnabled) return pieces;
  const target = pieces.find(p => p.id === targetPieceId);
  if (!target || !target.symmetryGroupId || target.facetIndex === undefined) return pieces;

  const N = lampConfig.facetCount;
  const unrolled = computeUnrolledLamp(lampConfig);
  const k = target.facetIndex;

  return pieces.map(p => {
    if (p.symmetryGroupId !== target.symmetryGroupId || p.id === targetPieceId || p.facetIndex === undefined) {
      return p;
    }

    const j = p.facetIndex;
    let updatedPoly = p.polygon;
    if (newPolygon) {
      updatedPoly = newPolygon.map(([px, py]) =>
        replicatePointToFacet(px, py, k, j, unrolled, N)
      );
    }

    let updatedCurves = p.curvePoints;
    if (newCurvePoints) {
      updatedCurves = newCurvePoints.map(cp => {
        const newCtrl = replicatePointToFacet(cp.ctrl[0], cp.ctrl[1], k, j, unrolled, N);
        return { ...cp, ctrl: newCtrl };
      });
    }

    return {
      ...p,
      polygon: updatedPoly,
      curvePoints: updatedCurves,
    };
  });
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
  const [isSymmetryEnabled, setIsSymmetryEnabled] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'error'>('saved');
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savingIndicatorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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

  const createNewProject = useCallback(async (name: string, type: 'flat' | 'lamp' = 'flat') => {
    await flushSave();
    const newProject: Project = { ...EMPTY_PROJECT, name, projectType: type };
    if (type === 'lamp') {
      // Classic tapered lampshade: narrow top, widens to a short cylindrical skirt.
      const lampConfig = {
        facetCount: 6,
        profilePoints: [
          { r: 50, y: 0 },
          { r: 100, y: 80 },
          { r: 100, y: 140 },
        ],
        activeTierIndex: 0
      };
      const { width, height } = computeUnrolledLamp(lampConfig);
      newProject.lampConfig = lampConfig;
      newProject.patternWidth = width;
      newProject.patternHeight = height;
      newProject.patternScale = {
        pxPerUnit: 10, // 10 px = 1 cm (profile points are in mm)
        unit: 'cm',
        line: { x1: 0, y1: height / 2, x2: width, y2: height / 2 },
      };
    }
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
        setActiveSheetId(fresh.sheets[0]?.id ?? '');
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
    updateProject(prev => {
      const piece = prev.pieces.find(p => p.id === pieceId);
      if (piece?.symmetryGroupId && isSymmetryEnabled) {
        const deletedIds = prev.pieces.filter(p => p.symmetryGroupId === piece.symmetryGroupId).map(p => p.id);
        setSelectedPieceIds(ids => ids.filter(id => !deletedIds.includes(id)));
        return {
          ...prev,
          pieces: prev.pieces.filter(p => p.symmetryGroupId !== piece.symmetryGroupId)
        };
      }
      setSelectedPieceIds(ids => ids.filter(id => id !== pieceId));
      return { ...prev, pieces: prev.pieces.filter(p => p.id !== pieceId) };
    });
  }, [updateProject, isSymmetryEnabled]);

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
      const targetPiece = prev.pieces.find(p => p.id === pieceId);
      const targetSymmetryGroupId = targetPiece?.symmetryGroupId;

      const sheet = prev.sheets.find(s => s.id === sheetId);
      const sw = sheet?.naturalWidth ?? 800;
      const sh = sheet?.naturalHeight ?? 600;
      const crop = sheet?.crop ?? { top: 0, left: 0, bottom: 0, right: 0 };
      const cx = (crop.left + sw - crop.right) / 2;
      const cy = (crop.top + sh - crop.bottom) / 2;

      const next = {
        ...prev,
        pieces: prev.pieces.map(p => {
          if (p.id === pieceId || (isSymmetryEnabled && targetSymmetryGroupId && p.symmetryGroupId === targetSymmetryGroupId)) {
            return { ...p, glassSheetId: sheetId, transform: { ...p.transform, x: cx, y: cy } };
          }
          return p;
        })
      };
      return applyScales(next, sheetId);
    });
    setActiveSheetId(sheetId);
  }, [updateProject, isSymmetryEnabled]);

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
      if (label) newSheet.label = stripExtension(label);
      
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

  const addPieceFromBox = useCallback((box: BoundingBox, sheetId: string, tierIndex?: number): string => {
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

      const isLamp = prev.projectType === 'lamp' && prev.lampConfig;
      if (isLamp && isSymmetryEnabled) {
        const lampConfig = prev.lampConfig!;
        const N = lampConfig.facetCount;
        const unrolled = computeUnrolledLamp(lampConfig);
        
        const xs = polygon.map(p => p[0]);
        const ys = polygon.map(p => p[1]);
        const cxCentroid = xs.reduce((sum, a) => sum + a, 0) / xs.length;
        const cyCentroid = ys.reduce((sum, a) => sum + a, 0) / ys.length;
        const norm = patternToSurfaceRobust(cxCentroid, cyCentroid, unrolled, N);
        const k = norm.facetIdx;
        
        const symmetryGroupId = crypto.randomUUID();
        const basePiece: Piece = {
          id, label, polygon, glassSheetId: sheetId,
          transform: { x: cx, y: cy, rotation: 0, scale: s },
          promptBox: box, promptPoints: [],
          tierIndex,
          facetIndex: k,
          symmetryGroupId,
        };
        
        const copies: Piece[] = [];
        for (let j = 0; j < N; j++) {
          if (j === k) continue;
          
          const newPoly = polygon.map(([px, py]) =>
            replicatePointToFacet(px, py, k, j, unrolled, N)
          );
          
          let newPromptBox = box;
          if (box) {
            const [p1, p2] = [
              replicatePointToFacet(box.x1, box.y1, k, j, unrolled, N),
              replicatePointToFacet(box.x2, box.y2, k, j, unrolled, N)
            ];
            newPromptBox = {
              x1: Math.min(p1[0], p2[0]),
              y1: Math.min(p1[1], p2[1]),
              x2: Math.max(p1[0], p2[0]),
              y2: Math.max(p1[1], p2[1]),
            };
          }
          
          copies.push({
            id: crypto.randomUUID(),
            label: `${t('piece')} ${prev.pieces.length + copies.length + 2}`,
            polygon: newPoly,
            glassSheetId: sheetId,
            transform: { x: cx, y: cy, rotation: 0, scale: s },
            promptBox: newPromptBox,
            promptPoints: [],
            tierIndex,
            facetIndex: j,
            symmetryGroupId,
          });
        }
        
        setSelectedPieceIds([basePiece.id]);
        return { ...prev, pieces: [...prev.pieces, basePiece, ...copies] };
      }

      const newPiece: Piece = {
        id, label, polygon, glassSheetId: sheetId,
        transform: { x: cx, y: cy, rotation: 0, scale: s },
        promptBox: box, promptPoints: [],
        tierIndex
      };
      setSelectedPieceIds([newPiece.id]);
      return { ...prev, pieces: [...prev.pieces, newPiece] };
    });
    return id;
  }, [updateProject, t, isSymmetryEnabled]);

  const addManualPiece = useCallback((polygon: [number, number][], sheetId: string, tierIndex?: number): string => {
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
      const xs = polygon.map(p => p[0]);
      const ys = polygon.map(p => p[1]);
      const box: BoundingBox = {
        x1: Math.min(...xs), y1: Math.min(...ys),
        x2: Math.max(...xs), y2: Math.max(...ys),
      };

      const isLamp = prev.projectType === 'lamp' && prev.lampConfig;
      if (isLamp && isSymmetryEnabled) {
        const lampConfig = prev.lampConfig!;
        const N = lampConfig.facetCount;
        const unrolled = computeUnrolledLamp(lampConfig);
        
        const cxCentroid = xs.reduce((sum, a) => sum + a, 0) / xs.length;
        const cyCentroid = ys.reduce((sum, a) => sum + a, 0) / ys.length;
        const norm = patternToSurfaceRobust(cxCentroid, cyCentroid, unrolled, N);
        const k = norm.facetIdx;
        
        const symmetryGroupId = crypto.randomUUID();
        const basePiece: Piece = {
          id, label, polygon, glassSheetId: sheetId,
          transform: { x: cx, y: cy, rotation: 0, scale: s },
          promptBox: box, promptPoints: [],
          tierIndex,
          facetIndex: k,
          symmetryGroupId,
        };
        
        const copies: Piece[] = [];
        for (let j = 0; j < N; j++) {
          if (j === k) continue;
          
          const newPoly = polygon.map(([px, py]) =>
            replicatePointToFacet(px, py, k, j, unrolled, N)
          );
          
          let newPromptBox = box;
          if (box) {
            const [p1, p2] = [
              replicatePointToFacet(box.x1, box.y1, k, j, unrolled, N),
              replicatePointToFacet(box.x2, box.y2, k, j, unrolled, N)
            ];
            newPromptBox = {
              x1: Math.min(p1[0], p2[0]),
              y1: Math.min(p1[1], p2[1]),
              x2: Math.max(p1[0], p2[0]),
              y2: Math.max(p1[1], p2[1]),
            };
          }
          
          copies.push({
            id: crypto.randomUUID(),
            label: `${t('piece')} ${prev.pieces.length + copies.length + 2}`,
            polygon: newPoly,
            glassSheetId: sheetId,
            transform: { x: cx, y: cy, rotation: 0, scale: s },
            promptBox: newPromptBox,
            promptPoints: [],
            tierIndex,
            facetIndex: j,
            symmetryGroupId,
          });
        }
        
        setSelectedPieceIds([basePiece.id]);
        return { ...prev, pieces: [...prev.pieces, basePiece, ...copies] };
      }

      const newPiece: Piece = {
        id, label, polygon, glassSheetId: sheetId,
        transform: { x: cx, y: cy, rotation: 0, scale: s },
        promptBox: box, promptPoints: [],
        tierIndex
      };
      setSelectedPieceIds([newPiece.id]);
      return { ...prev, pieces: [...prev.pieces, newPiece] };
    });
    return id;
  }, [updateProject, t, isSymmetryEnabled]);

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

  const updatePiecePolygon = useCallback((pieceId: string, polygon: [number, number][], skipHistory = false) => {
    updateProject(prev => {
      const updatedPieces = prev.pieces.map(p => p.id === pieceId ? { ...p, polygon } : p);
      const syncedPieces = syncSymmetricPieces(updatedPieces, pieceId, polygon, undefined, prev.lampConfig, isSymmetryEnabled);
      return { ...prev, pieces: syncedPieces };
    }, skipHistory);
  }, [updateProject, isSymmetryEnabled]);

  const updatePieceCurves = useCallback((pieceId: string, curvePoints: import('../types').CurvePoint[], skipHistory = false) => {
    updateProject(prev => {
      const updatedPieces = prev.pieces.map(p => p.id === pieceId ? { ...p, curvePoints } : p);
      const syncedPieces = syncSymmetricPieces(updatedPieces, pieceId, undefined, curvePoints, prev.lampConfig, isSymmetryEnabled);
      return { ...prev, pieces: syncedPieces };
    }, skipHistory);
  }, [updateProject, isSymmetryEnabled]);

  const updatePiecePolygonAndCurves = useCallback((pieceId: string, polygon: [number, number][], curvePoints: import('../types').CurvePoint[], skipHistory = false) => {
    updateProject(prev => {
      const updatedPieces = prev.pieces.map(p => p.id === pieceId ? { ...p, polygon, curvePoints } : p);
      const syncedPieces = syncSymmetricPieces(updatedPieces, pieceId, polygon, curvePoints, prev.lampConfig, isSymmetryEnabled);
      return { ...prev, pieces: syncedPieces };
    }, skipHistory);
  }, [updateProject, isSymmetryEnabled]);

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

  const updateSolderWidthMM = useCallback((width: number) => {
    updateProject(prev => ({ ...prev, solderWidthMM: width }));
  }, [updateProject]);

  const updateSolderColor = useCallback((color: SolderColor) => {
    updateProject(prev => ({ ...prev, solderColor: color }));
  }, [updateProject]);
  const startBlankCanvas = useCallback(() => {
    const W = 1200;
    const H = 1200;
    updateProject(prev => ({
      ...prev,
      patternImageUrl: '',
      patternWidth: W,
      patternHeight: H,
      patternCrop: { top: 0, left: 0, bottom: 0, right: 0 },
      patternScale: {
        pxPerUnit: 100,
        unit: 'in',
        line: { x1: 0, y1: H / 2, x2: W, y2: H / 2 },
      },
    }));
  }, [updateProject]);

  const addSheetFromImage = useCallback((url: string, label: string, scale: Scale | null = null) => {
    const id = `sheet-${Date.now()}`;
    const cleanLabel = stripExtension(label);
    updateProject(prev => {
      const newSheet: GlassSheet = {
        id, label: cleanLabel, imageUrl: url,
        crop: { top: 0, left: 0, bottom: 0, right: 0 },
        scale,
      };
      setActiveSheetId(id);
      return applyScales({ ...prev, sheets: [...prev.sheets, newSheet] }, id);
    });
  }, [updateProject]);

  const moveAllPiecesBetweenSheets = useCallback((srcSheetId: string, destSheetId: string) => {
    if (srcSheetId === destSheetId) return;
    updateProject(prev => {
      const dest = prev.sheets.find(s => s.id === destSheetId);
      if (!dest) return prev;
      const { x: cx, y: cy } = sheetCenter(dest);
      const calibrated = calibratedScale(prev.patternScale, dest.scale ?? null);
      return {
        ...prev,
        pieces: prev.pieces.map(p => {
          if (p.glassSheetId !== srcSheetId) return p;
          const s = calibrated ?? fitScaleForPiece(p.polygon, dest);
          return {
            ...p,
            glassSheetId: destSheetId,
            transform: { x: cx, y: cy, rotation: 0, scale: s },
          };
        }),
      };
    });
    setActiveSheetId(destSheetId);
  }, [updateProject]);

  const addSheetFromImageAndMovePieces = useCallback((url: string, label: string, srcSheetId: string) => {
    const id = `sheet-${Date.now()}`;
    const cleanLabel = stripExtension(label);
    updateProject(prev => {
      const newSheet: GlassSheet = {
        id, label: cleanLabel, imageUrl: url,
        crop: { top: 0, left: 0, bottom: 0, right: 0 },
        scale: null,
      };
      // naturalWidth/Height are unknown until the image loads, so sheetCenter
      // falls back to defaults; the user re-positions on the new sheet, which
      // is the whole point of trying a new material.
      const { x: cx, y: cy } = sheetCenter(newSheet);
      return {
        ...prev,
        sheets: [...prev.sheets, newSheet],
        pieces: prev.pieces.map(p => {
          if (p.glassSheetId !== srcSheetId) return p;
          const s = fitScaleForPiece(p.polygon, newSheet);
          return {
            ...p,
            glassSheetId: id,
            transform: { x: cx, y: cy, rotation: 0, scale: s },
          };
        }),
      };
    });
    setActiveSheetId(id);
  }, [updateProject]);

  const updateLampConfig = useCallback((config: Partial<import('../types').LampConfig>) => {
    updateProject(prev => {
      if (!prev.lampConfig) return prev;
      const merged = { ...prev.lampConfig, ...config };
      // Reflow pattern dimensions whenever the lamp's footprint changes.
      const geometryChanged =
        config.facetCount !== undefined || config.profilePoints !== undefined || config.smooth !== undefined;
      if (!geometryChanged) {
        return { ...prev, lampConfig: merged };
      }
      const oldConfig = prev.lampConfig;
      const oldN = oldConfig.facetCount;
      const newN = merged.facetCount;
      const oldUnrolled = computeUnrolledLamp(oldConfig);
      const newUnrolled = computeUnrolledLamp(merged);

      const reflowedPieces = prev.pieces.map(piece => {
        const newPolygon = reflowLampPoints(piece.polygon, oldUnrolled, newUnrolled, oldN, newN);

        const newCurvePoints = piece.curvePoints?.map(cp => {
          const [newCtrl] = reflowLampPoints([cp.ctrl], oldUnrolled, newUnrolled, oldN, newN);
          return { ...cp, ctrl: newCtrl };
        });

        const newPromptPoints = piece.promptPoints?.map(pt => {
          const [newPt] = reflowLampPoints([[pt.x, pt.y]], oldUnrolled, newUnrolled, oldN, newN);
          return { ...pt, x: newPt[0], y: newPt[1] };
        });

        let newPromptBox = piece.promptBox;
        if (piece.promptBox) {
          const [p1, p2] = reflowLampPoints(
            [[piece.promptBox.x1, piece.promptBox.y1], [piece.promptBox.x2, piece.promptBox.y2]],
            oldUnrolled,
            newUnrolled,
            oldN,
            newN
          );
          newPromptBox = {
            x1: Math.min(p1[0], p2[0]),
            y1: Math.min(p1[1], p2[1]),
            x2: Math.max(p1[0], p2[0]),
            y2: Math.max(p1[1], p2[1]),
          };
        }

        return {
          ...piece,
          polygon: newPolygon,
          curvePoints: newCurvePoints,
          promptPoints: newPromptPoints,
          promptBox: newPromptBox,
        };
      });

      const { width, height } = computeUnrolledLamp(merged);
      return {
        ...prev,
        lampConfig: merged,
        patternWidth: width,
        patternHeight: height,
        pieces: reflowedPieces,
      };
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
    addManualPiece,
    updateSheetDimensions,
    batchAddPieces,
    updatePiecePolygon,
    updatePieceCurves,
    updatePiecePolygonAndCurves,
    updatePiecePrompt,
    addPiecePromptPoint,
    markPiecePending,
    unmarkPiecePending,
    updateSolderWidthMM,
    updateSolderColor,
    undo,
    redo,
    canUndo: undoStack.length > 0,
    canRedo: redoStack.length > 0,
    saveStatus,
    retrySave,
    loadProjectData,
    updatePatternImage,
    startBlankCanvas,
    addSheetFromImage,
    moveAllPiecesBetweenSheets,
    addSheetFromImageAndMovePieces,
    updateLampConfig,
    isSymmetryEnabled,
    setIsSymmetryEnabled,
  };
}
