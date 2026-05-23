import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Stage, Layer, Line, Group, Rect, Circle } from 'react-konva';
import type { KonvaEventObject } from 'konva/lib/Node';
import type { Project, Piece, CurvePoint, Scale, BoundingBox } from '../types';
import { Toolbar, SelectIcon, BoxIcon, PenIcon, PencilIcon, HandIcon } from './Toolbar';
import type { ToolId } from './Toolbar';
import { SelectAnimation, BoxAnimation, PenAnimation, PencilAnimation, PanAnimation } from './ToolTooltipAnimations';
import { useViewport } from '../hooks/useViewport';
import { toImageCoords } from '../utils/viewport';
import { CANVAS } from '../theme';

interface Props {
  project: Project;
  selectedPieceIds: string[];
  onSelectPiece: (id: string | null, multi?: boolean) => void;
  onSelectPieces: (ids: string[]) => void;
  onAddPiece: (box: BoundingBox, tierIndex: number) => void;
  onAddManualPiece: (polygon: [number, number][], tierIndex: number) => void;
  onUpdatePiecePolygon: (id: string, polygon: [number, number][]) => void;
  onUpdatePieceCurves: (id: string, curvePoints: CurvePoint[]) => void;
  onDeletePiece: (id: string) => void;
  onSmoothPiece: (id: string) => void;
  activeTool: ToolId;
  onChangeActiveTool: (tool: ToolId) => void;
  focusedPanelIdx: number | null;
  onSetFocusedPanelIdx: (idx: number | null) => void;
}

export function LampCanvas({
  project,
  selectedPieceIds,
  onSelectPiece,
  onSelectPieces,
  onAddPiece,
  onAddManualPiece,
  onUpdatePiecePolygon,
  onUpdatePieceCurves,
  onDeletePiece,
  onSmoothPiece,
  activeTool,
  onChangeActiveTool,
  focusedPanelIdx,
  onSetFocusedPanelIdx,
}: Props) {
  const { t } = useTranslation();
  const [isSpaceDown, setIsSpaceDown] = useState(false);

  const config = project.lampConfig || {
    facetCount: 6,
    profilePoints: [
      { r: 40, y: 0 },
      { r: 80, y: 60 },
      { r: 100, y: 140 },
      { r: 60, y: 200 },
    ],
    activeTierIndex: 0,
  };

  const { facetCount: N, profilePoints, activeTierIndex } = config;
  const isSmooth = N === 32;

  // Retrieve Active Tier Geometry
  const Rt = profilePoints[activeTierIndex]?.r ?? 80;
  const Rb = profilePoints[activeTierIndex + 1]?.r ?? 80;
  const Yt = profilePoints[activeTierIndex]?.y ?? 0;
  const Yb = profilePoints[activeTierIndex + 1]?.y ?? 200;
  const H = Yb - Yt;
  const d_side = Math.hypot(Rb - Rt, H);
  const d_top = 2 * Rt * Math.sin(Math.PI / N);
  const d_bottom = 2 * Rb * Math.sin(Math.PI / N);

  // Compute Layout Boundaries & Panel Polygons
  const { panelPolys, totalWidth, totalHeight, fanCenter, isCylinder } = useMemo(() => {
    const polys: [number, number][][] = [];
    const isCyl = Math.abs(Rb - Rt) < 0.1;

    if (isCyl) {
      const W = d_bottom;
      const W_total = N * W;
      for (let k = 0; k < N; k++) {
        const xStart = -W_total / 2 + k * W;
        polys.push([
          [xStart, -d_side / 2],
          [xStart + W, -d_side / 2],
          [xStart + W, d_side / 2],
          [xStart, d_side / 2],
        ]);
      }
      return {
        panelPolys: polys,
        totalWidth: W_total,
        totalHeight: d_side,
        fanCenter: { x: 0, y: 0 },
        isCylinder: true,
      };
    } else {
      // Cone / Dome segment (curved fan layout)
      const phi = 2 * Math.asin(Math.abs(d_bottom - d_top) / (2 * d_side));
      const A_total = N * phi;
      const alpha_start = -A_total / 2;

      let r_top = 0;
      let r_bottom = 0;
      if (Rb > Rt) {
        r_top = d_top * d_side / (d_bottom - d_top);
        r_bottom = r_top + d_side;
      } else {
        r_bottom = d_bottom * d_side / (d_top - d_bottom);
        r_top = r_bottom + d_side;
      }

      for (let k = 0; k < N; k++) {
        const a_start = alpha_start + k * phi;
        const a_end = a_start + phi;

        polys.push([
          [r_top * Math.sin(a_start), -r_top * Math.cos(a_start)],
          [r_top * Math.sin(a_end), -r_top * Math.cos(a_end)],
          [r_bottom * Math.sin(a_end), -r_bottom * Math.cos(a_end)],
          [r_bottom * Math.sin(a_start), -r_bottom * Math.cos(a_start)],
        ]);
      }

      const outerR = Math.max(r_top, r_bottom);
      const innerR = Math.min(r_top, r_bottom);
      return {
        panelPolys: polys,
        totalWidth: 2 * outerR * Math.sin(A_total / 2),
        totalHeight: outerR - innerR * Math.cos(A_total / 2),
        fanCenter: { x: 0, y: 0 },
        isCylinder: false,
      };
    }
  }, [N, Rt, Rb, d_side, d_top, d_bottom]);

  // Viewport setup (large boundary area)
  const canvasW = Math.max(800, totalWidth * 1.5);
  const canvasH = Math.max(600, totalHeight * 1.5);
  const vp = useViewport(canvasW, canvasH);

  // Focus & Spin Target Animation State
  const [currentRotation, setCurrentRotation] = useState(0);
  const [currentOffsetX, setCurrentOffsetX] = useState(0);
  const [currentOffsetY, setCurrentOffsetY] = useState(0);

  const { targetRotation, targetOffsetX, targetOffsetY } = useMemo(() => {
    if (focusedPanelIdx === null) {
      return { targetRotation: 0, targetOffsetX: 0, targetOffsetY: 0 };
    }

    if (isCylinder) {
      const W = d_bottom;
      const W_total = N * W;
      const xMid = -W_total / 2 + (focusedPanelIdx + 0.5) * W;
      return { targetRotation: 0, targetOffsetX: -xMid, targetOffsetY: 0 };
    } else {
      const phi = 2 * Math.asin(Math.abs(d_bottom - d_top) / (2 * d_side));
      const A_total = N * phi;
      const alpha_start = -A_total / 2;
      const aMid = alpha_start + (focusedPanelIdx + 0.5) * phi;

      let r_top = 0;
      let r_bottom = 0;
      if (Rb > Rt) {
        r_top = d_top * d_side / (d_bottom - d_top);
        r_bottom = r_top + d_side;
      } else {
        r_bottom = d_bottom * d_side / (d_top - d_bottom);
        r_top = r_bottom + d_side;
      }

      const rMid = (r_top + r_bottom) / 2;
      // We rotate by -aMid (in degrees)
      const rotDeg = (-aMid * 180) / Math.PI;

      // Offset so the selected panel's center is shifted to the workspace origin
      return {
        targetRotation: rotDeg,
        targetOffsetX: 0,
        targetOffsetY: rMid,
      };
    }
  }, [focusedPanelIdx, isCylinder, N, d_top, d_bottom, d_side, Rt, Rb]);

  // Smooth rotation animation loop using simple lerp
  useEffect(() => {
    let animId: number;
    const tick = () => {
      setCurrentRotation(prev => {
        const diff = targetRotation - prev;
        if (Math.abs(diff) < 0.05) return targetRotation;
        return prev + diff * 0.16;
      });
      setCurrentOffsetX(prev => {
        const diff = targetOffsetX - prev;
        if (Math.abs(diff) < 0.1) return targetOffsetX;
        return prev + diff * 0.16;
      });
      setCurrentOffsetY(prev => {
        const diff = targetOffsetY - prev;
        if (Math.abs(diff) < 0.1) return targetOffsetY;
        return prev + diff * 0.16;
      });
      animId = requestAnimationFrame(tick);
    };
    animId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animId);
  }, [targetRotation, targetOffsetX, targetOffsetY]);

  // Drawing tools state
  const [activePolygonPoints, setActivePolygonPoints] = useState<[number, number][]>([]);
  const [hoverPoint, setHoverPoint] = useState<[number, number] | null>(null);
  const [drawingBox, setDrawingBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [marqueeBox, setMarqueeBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [pencilPoints, setPencilPoints] = useState<[number, number][]>([]);

  // Keyboard shortcut handlers
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.code === 'Space' && !e.repeat) {
        e.preventDefault();
        setIsSpaceDown(true);
        return;
      }
      if (e.key === 'v') onChangeActiveTool('select');
      else if (e.key === 'h') onChangeActiveTool('pan');
      else if (e.key === 'b') onChangeActiveTool('box');
      else if (e.key === 'p') onChangeActiveTool('pen');
      else if (e.key === 'n') onChangeActiveTool('pencil');
      else if (e.key === 'Escape') {
        if (activePolygonPoints.length > 0) {
          setActivePolygonPoints([]);
        } else {
          onChangeActiveTool('select');
          onSetFocusedPanelIdx(null);
        }
      } else if (e.key === 'Enter') {
        if (activeTool === 'pen' && activePolygonPoints.length >= 3) {
          onAddManualPiece(activePolygonPoints, activeTierIndex);
          setActivePolygonPoints([]);
        }
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        selectedPieceIds.forEach(id => onDeletePiece(id));
      }
    }

    function handleKeyUp(e: KeyboardEvent) {
      if (e.code === 'Space') setIsSpaceDown(false);
    }

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [activeTool, activePolygonPoints, selectedPieceIds, activeTierIndex]);

  // Polar coordinate panel detection on click
  const findClickedPanel = (x: number, y: number): number | null => {
    if (isCylinder) {
      const W = d_bottom;
      const W_total = N * W;
      const x_norm = x + W_total / 2;
      const y_norm = y + d_side / 2;
      if (x_norm >= 0 && x_norm <= W_total && y_norm >= 0 && y_norm <= d_side) {
        return Math.min(Math.max(Math.floor(x_norm / W), 0), N - 1);
      }
    } else {
      const phi = 2 * Math.asin(Math.abs(d_bottom - d_top) / (2 * d_side));
      const A_total = N * phi;
      const alpha_start = -A_total / 2;

      let r_top = 0;
      let r_bottom = 0;
      if (Rb > Rt) {
        r_top = d_top * d_side / (d_bottom - d_top);
        r_bottom = r_top + d_side;
      } else {
        r_bottom = d_bottom * d_side / (d_top - d_bottom);
        r_top = r_bottom + d_side;
      }

      const d = Math.hypot(x, y);
      const alpha = Math.atan2(x, -y);

      const rMin = Math.min(r_top, r_bottom);
      const rMax = Math.max(r_top, r_bottom);

      if (d >= rMin && d <= rMax && alpha >= alpha_start && alpha <= alpha_start + A_total) {
        const theta_rel = alpha + A_total / 2;
        return Math.min(Math.max(Math.floor(theta_rel / phi), 0), N - 1);
      }
    }
    return null;
  };

  // Convert client stage position to canvas coordinate space
  const getStageMousePos = (e: KonvaEventObject<PointerEvent>) => {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return { x: 0, y: 0 };

    // 1. Get raw viewport coordinates
    const { x: vx, y: vy } = toImageCoords(ptr, vp.pan, vp.effectiveScale);

    // 2. Adjust for canvas offset and rotation animation
    // Center of workspace in viewport coordinates is (canvasW / 2, canvasH / 2)
    const cx = vx - canvasW / 2;
    const cy = vy - canvasH / 2;

    // Apply inverse translation (currentOffsetX, currentOffsetY)
    const tx = cx - currentOffsetX;
    const ty = cy - currentOffsetY;

    // Apply inverse rotation (currentRotation)
    const rad = (-currentRotation * Math.PI) / 180;
    const rx = tx * Math.cos(rad) - ty * Math.sin(rad);
    const ry = tx * Math.sin(rad) + ty * Math.cos(rad);

    return { x: rx, y: ry };
  };

  const handlePointerDown = (e: KonvaEventObject<PointerEvent>) => {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;

    const isMiddleClick = e.evt && (e.evt as MouseEvent).button === 1;
    if (isMiddleClick || activeTool === 'pan' || isSpaceDown) {
      vp.startPan(ptr);
      return;
    }

    const { x, y } = getStageMousePos(e);

    if (activeTool === 'select') {
      const panel = findClickedPanel(x, y);
      if (panel !== null) {
        onSetFocusedPanelIdx(panel);
      } else {
        onSelectPiece(null);
      }
      
      // If we clicked on background, support marquee box
      if (e.target.getType() === 'Stage' || e.target.attrs.id === 'bg-stage') {
        setMarqueeBox({ x1: x, y1: y, x2: x, y2: y });
      }
      return;
    }

    if (activeTool === 'pen') {
      if (activePolygonPoints.length >= 3) {
        const [startX, startY] = activePolygonPoints[0];
        const dist = Math.hypot(x - startX, y - startY);
        if (dist < 15 / vp.effectiveScale) {
          onAddManualPiece(activePolygonPoints, activeTierIndex);
          setActivePolygonPoints([]);
          return;
        }
      }
      setActivePolygonPoints(prev => [...prev, [x, y]]);
      return;
    }

    if (activeTool === 'pencil') {
      setPencilPoints([[x, y]]);
      return;
    }

    if (activeTool === 'box') {
      setDrawingBox({ x1: x, y1: y, x2: x, y2: y });
      return;
    }
  };

  const handlePointerMove = (e: KonvaEventObject<PointerEvent>) => {
    const ptr = e.target.getStage()?.getPointerPosition();
    if (!ptr) return;

    const { x, y } = getStageMousePos(e);

    if (drawingBox) {
      setDrawingBox(b => (b ? { ...b, x2: x, y2: y } : null));
      return;
    }
    if (marqueeBox) {
      setMarqueeBox(b => (b ? { ...b, x2: x, y2: y } : null));
      return;
    }
    if (activeTool === 'pen') {
      setHoverPoint([x, y]);
      return;
    }
    if (activeTool === 'pencil' && pencilPoints.length > 0) {
      setPencilPoints(prev => [...prev, [x, y]]);
      return;
    }

    vp.movePan(ptr);
  };

  const handlePointerUp = () => {
    if (drawingBox) {
      const box: BoundingBox = {
        x1: Math.min(drawingBox.x1, drawingBox.x2),
        y1: Math.min(drawingBox.y1, drawingBox.y2),
        x2: Math.max(drawingBox.x1, drawingBox.x2),
        y2: Math.max(drawingBox.y1, drawingBox.y2),
      };
      if (box.x2 - box.x1 > 5 && box.y2 - box.y1 > 5) {
        onAddPiece(box, activeTierIndex);
      }
      setDrawingBox(null);
      return;
    }

    if (marqueeBox) {
      // Find pieces in box
      const xmin = Math.min(marqueeBox.x1, marqueeBox.x2);
      const xmax = Math.max(marqueeBox.x1, marqueeBox.x2);
      const ymin = Math.min(marqueeBox.y1, marqueeBox.y2);
      const ymax = Math.max(marqueeBox.y1, marqueeBox.y2);

      const hitIds = project.pieces
        .filter(p => p.tierIndex === activeTierIndex || (!p.tierIndex && activeTierIndex === 0))
        .filter(p => {
          const xs = p.polygon.map(pt => pt[0]);
          const ys = p.polygon.map(pt => pt[1]);
          const cx = xs.reduce((s, a) => s + a, 0) / xs.length;
          const cy = ys.reduce((s, a) => s + a, 0) / ys.length;
          return cx >= xmin && cx <= xmax && cy >= ymin && cy <= ymax;
        })
        .map(p => p.id);

      if (hitIds.length > 0) {
        onSelectPieces(hitIds);
      }
      setMarqueeBox(null);
      return;
    }

    if (activeTool === 'pencil' && pencilPoints.length >= 3) {
      onAddManualPiece(pencilPoints, activeTierIndex);
      setPencilPoints([]);
      return;
    }

    vp.endPan();
  };

  const handleDoubleClickBg = () => {
    onSetFocusedPanelIdx(null);
  };

  // Filter pieces belonging to the active tier
  const activePieces = useMemo(() => {
    return project.pieces.filter(
      p => p.tierIndex === activeTierIndex || (!p.tierIndex && activeTierIndex === 0)
    );
  }, [project.pieces, activeTierIndex]);

  // Gather sheets color map
  const sheetColorMap = useMemo(() => {
    const map = new Map<string, string>();
    project.sheets.forEach(s => {
      map.set(s.id, s.swatch || 'rgba(192, 138, 31, 0.2)');
    });
    return map;
  }, [project.sheets]);

  const TOOLS = useMemo(
    () => [
      {
        id: 'select' as ToolId,
        label: t('toolSelect'),
        icon: <SelectIcon />,
        tooltip: {
          name: t('tooltipSelectName'),
          shortcut: 'V',
          description: 'Select glass pieces and click facets to focus',
          animation: <SelectAnimation />,
        },
      },
      {
        id: 'pan' as ToolId,
        label: t('toolPan'),
        icon: <HandIcon />,
        tooltip: {
          name: t('tooltipPanName'),
          shortcut: 'H, Space',
          description: t('tooltipPanDesc'),
          animation: <PanAnimation />,
        },
      },
      {
        id: 'box' as ToolId,
        label: t('toolDrawBox'),
        icon: <BoxIcon />,
        tooltip: {
          name: t('tooltipBoxName'),
          shortcut: 'B',
          description: 'Draw a bounding box to cut a glass piece',
          animation: <BoxAnimation />,
        },
      },
      {
        id: 'pen' as ToolId,
        label: t('toolDrawPen'),
        icon: <PenIcon />,
        tooltip: {
          name: t('tooltipPenName'),
          shortcut: 'P',
          description: t('tooltipPenDesc'),
          animation: <PenAnimation />,
        },
      },
      {
        id: 'pencil' as ToolId,
        label: t('toolDrawPencil'),
        icon: <PencilIcon />,
        tooltip: {
          name: t('tooltipPencilName'),
          shortcut: 'N',
          description: t('tooltipPencilDesc'),
          animation: <PencilAnimation />,
        },
      },
    ],
    [t]
  );

  const containerCursor = isSpaceDown || activeTool === 'pan' ? (vp.isPanning ? 'grabbing' : 'grab') : 'default';

  return (
    <div className="result-panel-inner" style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      {/* Toolbar */}
      <Toolbar tools={TOOLS} activeTool={activeTool} onSelectTool={onChangeActiveTool} />

      {/* Workspace Stage */}
      <div
        ref={vp.containerRef}
        className="canvas-well"
        onDoubleClick={handleDoubleClickBg}
        style={{
          flex: 1,
          overflow: 'hidden',
          cursor: containerCursor,
          position: 'relative',
          touchAction: 'none',
        }}
      >
        <Stage
          width={vp.dims.w}
          height={vp.dims.h}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
        >
          <Layer>
            {/* Viewport Zoom & Pan Group */}
            <Group x={vp.pan.x} y={vp.pan.y} scaleX={vp.effectiveScale} scaleY={vp.effectiveScale}>
              {/* Turntable Auto-Rotate & Focus Offset Group */}
              <Group
                x={canvasW / 2 + currentOffsetX}
                y={canvasH / 2 + currentOffsetY}
                rotation={currentRotation}
              >
                {/* Background Stage boundaries */}
                <Rect
                  id="bg-stage"
                  x={-canvasW / 2}
                  y={-canvasH / 2}
                  width={canvasW}
                  height={canvasH}
                  fill="transparent"
                />

                {/* 1. Draw Panel Outlines & Separators */}
                {panelPolys.map((poly, idx) => {
                  const flatPts = poly.flat();
                  return (
                    <Line
                      key={idx}
                      points={flatPts}
                      closed
                      stroke="var(--text-dim)"
                      strokeWidth={1 / vp.effectiveScale}
                      fill="rgba(255, 255, 255, 0.4)"
                    />
                  );
                })}

                {/* 2. Draw Glass Pieces belonging to this Tier */}
                {activePieces.map(piece => {
                  const flatPts = piece.polygon.flat();
                  const isPieceSelected = selectedPieceIds.includes(piece.id);
                  const fillColor = sheetColorMap.get(piece.glassSheetId) || 'rgba(192, 138, 31, 0.2)';

                  return (
                    <Group
                      key={piece.id}
                      onClick={e => {
                        e.cancelBubble = true;
                        onSelectPiece(piece.id, e.evt.shiftKey);
                      }}
                      onTap={e => {
                        e.cancelBubble = true;
                        onSelectPiece(piece.id);
                      }}
                    >
                      <Line
                        points={flatPts}
                        closed
                        fill={fillColor}
                        stroke={isPieceSelected ? 'var(--amber)' : '#1a1a1a'}
                        strokeWidth={(isPieceSelected ? 2.5 : 1.25) / vp.effectiveScale}
                      />
                    </Group>
                  );
                })}

                {/* 3. Focus Mode Neighbor Shading Overlay */}
                {focusedPanelIdx !== null && (
                  <Group>
                    {panelPolys.map((poly, idx) => {
                      if (idx === focusedPanelIdx) return null;
                      return (
                        <Line
                          key={'overlay-' + idx}
                          points={poly.flat()}
                          closed
                          fill="rgba(235, 228, 210, 0.65)" // Workbench shade color
                          listening={false}
                        />
                      );
                    })}
                  </Group>
                )}

                {/* 4. Active drawing shapes overlays */}
                {/* Pen tool lines */}
                {activePolygonPoints.length > 0 && (
                  <Group>
                    <Line
                      points={activePolygonPoints.flat()}
                      stroke="var(--amber)"
                      strokeWidth={2 / vp.effectiveScale}
                    />
                    {activePolygonPoints.map(([px, py], i) => (
                      <Circle
                        key={i}
                        x={px}
                        y={py}
                        radius={i === 0 ? 6 / vp.effectiveScale : 4 / vp.effectiveScale}
                        fill={i === 0 ? '#10b981' : 'var(--amber)'}
                        stroke="var(--paper)"
                        strokeWidth={1.5 / vp.effectiveScale}
                      />
                    ))}
                    {hoverPoint && activePolygonPoints.length > 0 && (
                      <Line
                        points={[
                          activePolygonPoints[activePolygonPoints.length - 1][0],
                          activePolygonPoints[activePolygonPoints.length - 1][1],
                          hoverPoint[0],
                          hoverPoint[1],
                        ]}
                        stroke="var(--amber)"
                        strokeWidth={1.5 / vp.effectiveScale}
                        dash={[5, 5]}
                      />
                    )}
                  </Group>
                )}

                {/* Box tool drag box */}
                {drawingBox && (
                  <Rect
                    x={Math.min(drawingBox.x1, drawingBox.x2)}
                    y={Math.min(drawingBox.y1, drawingBox.y2)}
                    width={Math.abs(drawingBox.x2 - drawingBox.x1)}
                    height={Math.abs(drawingBox.y2 - drawingBox.y1)}
                    stroke="var(--amber)"
                    strokeWidth={1.5 / vp.effectiveScale}
                    fill="rgba(192, 138, 31, 0.15)"
                  />
                )}

                {/* Pencil tool freehand lines */}
                {pencilPoints.length > 0 && (
                  <Line
                    points={pencilPoints.flat()}
                    stroke="var(--amber)"
                    strokeWidth={2 / vp.effectiveScale}
                  />
                )}

                {/* Marquee selection box */}
                {marqueeBox && (
                  <Rect
                    x={Math.min(marqueeBox.x1, marqueeBox.x2)}
                    y={Math.min(marqueeBox.y1, marqueeBox.y2)}
                    width={Math.abs(marqueeBox.x2 - marqueeBox.x1)}
                    height={Math.abs(marqueeBox.y2 - marqueeBox.y1)}
                    stroke="var(--amber)"
                    strokeWidth={1 / vp.effectiveScale}
                    fill="rgba(192, 138, 31, 0.1)"
                  />
                )}
              </Group>
            </Group>
          </Layer>
        </Stage>

        {/* Escape Focus button overlay */}
        {focusedPanelIdx !== null && (
          <button
            onClick={() => onSetFocusedPanelIdx(null)}
            style={{
              position: 'absolute',
              bottom: 16,
              left: '50%',
              transform: 'translateX(-50%)',
              padding: '6px 16px',
              borderRadius: '999px',
              background: 'var(--paper)',
              border: '1px solid var(--hairline-2)',
              color: 'var(--text-soft)',
              fontSize: '12px',
              fontWeight: 600,
              boxShadow: '0 4px 14px rgba(40, 30, 15, 0.12)',
              cursor: 'pointer',
              zIndex: 10,
            }}
          >
            Exit Focus Mode
          </button>
        )}
      </div>
    </div>
  );
}
