import { useState, useCallback, useEffect } from 'react';
import type { Project, TextureTransform, Crop, BoundingBox, Piece, Scale, GlassSheet } from '../types';
import { DEFAULT_PROJECT } from '../defaultProject';
import { GLASS_ASSETS } from '../assets';

const STORAGE_KEY = 'vitraux-project';

function loadProject(): Project {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return JSON.parse(saved) as Project;
  } catch {
    // ignore
  }
  return DEFAULT_PROJECT;
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

function makeNewSheet(prev: Project): GlassSheet {
  const glass = GLASS_ASSETS[prev.sheets.length % GLASS_ASSETS.length];
  return {
    id: `sheet-${Date.now()}`,
    label: `Sheet ${prev.sheets.length + 1}`,
    imageUrl: glass.url,
    crop: { top: 0, left: 0, bottom: 0, right: 0 },
    scale: null,
  };
}

export function useProject() {
  const [project, setProject] = useState<Project>(loadProject);
  const [selectedPieceId, setSelectedPieceId] = useState<string | null>(null);
  const [activeSheetId, setActiveSheetId] = useState<string>(
    () => loadProject().sheets[0]?.id ?? ''
  );
  const [pendingPieceIds, setPendingPieceIds] = useState<ReadonlySet<string>>(new Set());

  // Keep activeSheetId valid if the active sheet is ever deleted
  useEffect(() => {
    if (project.sheets.length > 0 && !project.sheets.find(s => s.id === activeSheetId)) {
      setActiveSheetId(project.sheets[0].id);
    }
  }, [project.sheets, activeSheetId]);

  function persist(next: Project) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // ignore quota errors
    }
    return next;
  }

  const updatePieceTransform = useCallback(
    (pieceId: string, transform: Partial<TextureTransform>) => {
      setProject(prev =>
        persist({
          ...prev,
          pieces: prev.pieces.map(p =>
            p.id === pieceId ? { ...p, transform: { ...p.transform, ...transform } } : p
          ),
        })
      );
    },
    []
  );

  const updatePatternCrop = useCallback((crop: Partial<Crop>) => {
    setProject(prev =>
      persist({ ...prev, patternCrop: { ...prev.patternCrop, ...crop } })
    );
  }, []);

  const updateSheetCrop = useCallback((sheetId: string, crop: Partial<Crop>) => {
    setProject(prev =>
      persist({
        ...prev,
        sheets: prev.sheets.map(s =>
          s.id === sheetId ? { ...s, crop: { ...s.crop, ...crop } } : s
        ),
      })
    );
  }, []);

  const selectPiece = useCallback((id: string | null) => {
    setSelectedPieceId(id);
    if (id) {
      setProject(prev => {
        const piece = prev.pieces.find(p => p.id === id);
        if (piece) setActiveSheetId(piece.glassSheetId);
        return prev;
      });
    }
  }, []);

  const deletePiece = useCallback((pieceId: string) => {
    setProject(prev => persist({ ...prev, pieces: prev.pieces.filter(p => p.id !== pieceId) }));
    setSelectedPieceId(id => id === pieceId ? null : id);
  }, []);

  const updatePieceLabel = useCallback((pieceId: string, label: string) => {
    setProject(prev =>
      persist({ ...prev, pieces: prev.pieces.map(p => p.id === pieceId ? { ...p, label } : p) })
    );
  }, []);

  const updatePieceSheet = useCallback((pieceId: string, sheetId: string) => {
    setProject(prev => {
      const next = { ...prev, pieces: prev.pieces.map(p => p.id === pieceId ? { ...p, glassSheetId: sheetId } : p) };
      return persist(applyScales(next, sheetId));
    });
    setActiveSheetId(sheetId);
  }, []);

  const deleteSheet = useCallback((sheetId: string) => {
    setProject(prev => {
      if (prev.sheets.length <= 1) return prev;
      const remaining = prev.sheets.filter(s => s.id !== sheetId);
      const fallbackId = remaining[0].id;
      return persist({
        ...prev,
        sheets: remaining,
        pieces: prev.pieces.map(p => p.glassSheetId === sheetId ? { ...p, glassSheetId: fallbackId } : p),
      });
    });
    // activeSheetId correction handled by the useEffect above
  }, []);

  const renameSheet = useCallback((sheetId: string, label: string) => {
    setProject(prev =>
      persist({ ...prev, sheets: prev.sheets.map(s => s.id === sheetId ? { ...s, label } : s) })
    );
  }, []);

  const addSheet = useCallback(() => {
    setProject(prev => {
      const newSheet = makeNewSheet(prev);
      setActiveSheetId(newSheet.id);
      return persist({ ...prev, sheets: [...prev.sheets, newSheet] });
    });
  }, []);

  const addSheetAndAssignPiece = useCallback((pieceId: string) => {
    setProject(prev => {
      const newSheet = makeNewSheet(prev);
      setActiveSheetId(newSheet.id);
      return persist({
        ...prev,
        sheets: [...prev.sheets, newSheet],
        pieces: prev.pieces.map(p => p.id === pieceId ? { ...p, glassSheetId: newSheet.id } : p),
      });
    });
  }, []);

  const updatePatternScale = useCallback((scale: Scale | null) => {
    setProject(prev => persist(applyScales({ ...prev, patternScale: scale })));
  }, []);

  const updateSheetScale = useCallback((sheetId: string, scale: Scale | null) => {
    setProject(prev => {
      const sheets = prev.sheets.map(s => s.id === sheetId ? { ...s, scale } : s);
      return persist(applyScales({ ...prev, sheets }, sheetId));
    });
  }, []);

  const addPieceFromBox = useCallback((box: BoundingBox, sheetId: string): string => {
    const { x1, y1, x2, y2 } = box;
    const polygon: Piece['polygon'] = [
      [x1, y1], [x2, y1], [x2, y2], [x1, y2],
    ];
    const id = `piece-${Date.now()}`;
    setProject(prev => {
      const label = `Piece ${prev.pieces.length + 1}`;
      const sheet = prev.sheets.find(s => s.id === sheetId);
      const s = calibratedScale(prev.patternScale, sheet?.scale ?? null) ?? 1;
      const newPiece: Piece = {
        id,
        label,
        polygon,
        glassSheetId: sheetId,
        transform: { x: 400, y: 300, rotation: 0, scale: s },
      };
      setSelectedPieceId(newPiece.id);
      return persist({ ...prev, pieces: [...prev.pieces, newPiece] });
    });
    return id;
  }, []);

  const updatePiecePolygon = useCallback((pieceId: string, polygon: [number, number][]) => {
    setProject(prev =>
      persist({ ...prev, pieces: prev.pieces.map(p => p.id === pieceId ? { ...p, polygon } : p) })
    );
  }, []);

  const markPiecePending = useCallback((pieceId: string) => {
    setPendingPieceIds(s => new Set(s).add(pieceId));
  }, []);

  const unmarkPiecePending = useCallback((pieceId: string) => {
    setPendingPieceIds(s => { const n = new Set(s); n.delete(pieceId); return n; });
  }, []);

  const resetProject = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setProject(DEFAULT_PROJECT);
    setSelectedPieceId(null);
    setActiveSheetId(DEFAULT_PROJECT.sheets[0]?.id ?? '');
  }, []);

  const loadProjectData = useCallback((newProject: Project) => {
    setProject(persist(newProject));
    setSelectedPieceId(null);
    setActiveSheetId(newProject.sheets[0]?.id ?? '');
  }, []);

  const updatePatternImage = useCallback((url: string, width: number, height: number) => {
    setProject(prev => persist({ ...prev, patternImageUrl: url, patternWidth: width, patternHeight: height }));
  }, []);

  const addSheetFromImage = useCallback((url: string, label: string) => {
    setProject(prev => {
      const newSheet: GlassSheet = {
        id: `sheet-${Date.now()}`,
        label,
        imageUrl: url,
        crop: { top: 0, left: 0, bottom: 0, right: 0 },
        scale: null,
      };
      setActiveSheetId(newSheet.id);
      return persist({ ...prev, sheets: [...prev.sheets, newSheet] });
    });
  }, []);

  return {
    project,
    selectedPieceId,
    activeSheetId,
    pendingPieceIds,
    setActiveSheetId,
    selectPiece,
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
    updatePiecePolygon,
    markPiecePending,
    unmarkPiecePending,
    resetProject,
    loadProjectData,
    updatePatternImage,
    addSheetFromImage,
  };
}
