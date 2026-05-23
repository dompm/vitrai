import React, { useState, useEffect, useRef, useMemo } from 'react';
import type { Project, LampConfig, LampProfilePoint, Piece, GlassSheet } from '../types';

interface Props {
  project: Project;
  selectedPieceIds: string[];
  onSelectPiece: (id: string | null) => void;
  onUpdateLampConfig: (config: Partial<LampConfig>) => void;
  activeSheetId: string;
  onSetFocusedPanelIdx: (idx: number | null) => void;
}

export function Lamp3DPreview({
  project,
  selectedPieceIds,
  onSelectPiece,
  onUpdateLampConfig,
  activeSheetId,
  onSetFocusedPanelIdx,
}: Props) {
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

  const { facetCount, profilePoints, activeTierIndex } = config;
  const N = facetCount;

  // 3D rotation state
  const [yaw, setYaw] = useState<number>(0.6); // angle in radians
  const [pitch, setPitch] = useState<number>(0.3); // angle in radians
  const isDragging = useRef<boolean>(false);
  const dragStart = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const rotStart = useRef<{ yaw: number; pitch: number }>({ yaw: 0, pitch: 0 });

  // Selected control point in Profile Editor
  const [selectedPointIdx, setSelectedPointIdx] = useState<number | null>(0);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Generate presets
  const handleLoadPreset = (preset: 'cylinder' | 'cone' | 'dome' | 'pyramid') => {
    let newN = 24;
    let newPoints: LampProfilePoint[] = [];

    if (preset === 'cylinder') {
      newN = 24; // Labeled as Smooth if slider goes to 32, but 24 is fine for flat approximation
      newPoints = [
        { r: 80, y: 0 },
        { r: 80, y: 200 },
      ];
    } else if (preset === 'cone') {
      newN = 16;
      newPoints = [
        { r: 20, y: 0 },
        { r: 120, y: 180 },
      ];
    } else if (preset === 'dome') {
      newN = 24;
      newPoints = [
        { r: 0, y: 0 },
        { r: 60, y: 30 },
        { r: 100, y: 80 },
        { r: 100, y: 160 },
      ];
    } else if (preset === 'pyramid') {
      newN = 4;
      newPoints = [
        { r: 30, y: 0 },
        { r: 100, y: 120 },
      ];
    }

    onUpdateLampConfig({
      facetCount: newN,
      profilePoints: newPoints,
      activeTierIndex: 0,
    });
    setSelectedPointIdx(0);
  };

  // Math: map unrolled 2D coordinates to 3D
  const get3DCoords = useMemo(() => {
    return (x: number, y: number, tierIndex: number, panelIdx: number): [number, number, number] => {
      if (tierIndex >= profilePoints.length - 1) return [0, 0, 0];
      const Rt = profilePoints[tierIndex].r;
      const Yt = profilePoints[tierIndex].y;
      const Rb = profilePoints[tierIndex + 1].r;
      const Yb = profilePoints[tierIndex + 1].y;

      const H = Yb - Yt;
      const d_side = Math.hypot(Rb - Rt, H);
      const d_top = 2 * Rt * Math.sin(Math.PI / N);
      const d_bottom = 2 * Rb * Math.sin(Math.PI / N);

      let u = 0;
      let v = 0;

      if (Math.abs(Rb - Rt) < 0.1) {
        // Cylinder
        const W = d_bottom;
        const W_total = N * W;
        const x_norm = x + W_total / 2;
        const y_norm = y + d_side / 2;
        const k = Math.min(Math.max(Math.floor(x_norm / W), 0), N - 1);
        u = (x_norm - k * W) / W;
        v = y_norm / d_side;
      } else {
        // Cone / Dome Segment
        const phi = 2 * Math.asin(Math.abs(d_bottom - d_top) / (2 * d_side));
        const A_total = N * phi;
        const d = Math.hypot(x, y);
        const alpha = Math.atan2(x, -y);
        const theta_rel = alpha + A_total / 2;
        const k = Math.min(Math.max(Math.floor(theta_rel / phi), 0), N - 1);
        u = (theta_rel - k * phi) / phi;

        if (Rb > Rt) {
          const r_top = d_top * d_side / (d_bottom - d_top);
          const r_bottom = r_top + d_side;
          v = (d - r_top) / (r_bottom - r_top);
        } else {
          const r_bottom = d_bottom * d_side / (d_top - d_bottom);
          const r_top = r_bottom + d_side;
          v = (r_top - d) / (r_top - r_bottom);
        }
      }

      u = Math.min(Math.max(u, 0), 1);
      v = Math.min(Math.max(v, 0), 1);

      // Now map to 3D space on the specific panelIdx
      const theta_start = panelIdx * (2 * Math.PI / N);
      const theta_end = (panelIdx + 1) * (2 * Math.PI / N);

      // Top-Left, Top-Right, Bottom-Right, Bottom-Left vertices
      const v_tl: [number, number, number] = [Rt * Math.cos(theta_start), Yt, Rt * Math.sin(theta_start)];
      const v_tr: [number, number, number] = [Rt * Math.cos(theta_end), Yt, Rt * Math.sin(theta_end)];
      const v_br: [number, number, number] = [Rb * Math.cos(theta_end), Yb, Rb * Math.sin(theta_end)];
      const v_bl: [number, number, number] = [Rb * Math.cos(theta_start), Yb, Rb * Math.sin(theta_start)];

      // Bilinear interpolation
      const p_top = [
        (1 - u) * v_tl[0] + u * v_tr[0],
        (1 - u) * v_tl[1] + u * v_tr[1],
        (1 - u) * v_tl[2] + u * v_tr[2],
      ];
      const p_bottom = [
        (1 - u) * v_bl[0] + u * v_br[0],
        (1 - u) * v_bl[1] + u * v_br[1],
        (1 - u) * v_bl[2] + u * v_br[2],
      ];

      return [
        (1 - v) * p_top[0] + v * p_bottom[0],
        (1 - v) * p_top[1] + v * p_bottom[1],
        (1 - v) * p_top[2] + v * p_bottom[2],
      ];
    };
  }, [N, profilePoints]);

  // Project 3D coordinate to 2D Screen Space
  const projectPoint = (
    p: [number, number, number],
    width: number,
    height: number
  ): { x: number; y: number; depth: number } => {
    // Re-center the lamp on the world origin so rotation + auto-fit are stable.
    const yMid = (profilePoints[0].y + profilePoints[profilePoints.length - 1].y) / 2;
    const py = p[1] - yMid;

    // 1. Rotation yaw (around Y axis)
    const x1 = p[0] * Math.cos(yaw) - p[2] * Math.sin(yaw);
    const z1 = p[0] * Math.sin(yaw) + p[2] * Math.cos(yaw);

    // 2. Rotation pitch (around X axis)
    const y2 = py * Math.cos(pitch) - z1 * Math.sin(pitch);
    const z2 = py * Math.sin(pitch) + z1 * Math.cos(pitch);

    // Auto-fit scale: bound the projected lamp extents to the canvas with padding.
    const PAD = 24;
    const totalH = profilePoints[profilePoints.length - 1].y - profilePoints[0].y;
    const maxR = Math.max(...profilePoints.map(pt => pt.r));
    const projW = 2 * maxR;
    const projH = totalH * Math.cos(pitch) + 2 * maxR * Math.sin(Math.abs(pitch));
    const fitScale = Math.min((width - 2 * PAD) / projW, (height - 2 * PAD) / projH);

    // 3. Perspective Projection
    const d_cam = 450;
    const factor = d_cam / (d_cam + z2);

    return {
      x: x1 * factor * fitScale + width / 2,
      y: y2 * factor * fitScale + height / 2,
      depth: z2,
    };
  };

  // Render 3D preview loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Handle high DPI
    const width = containerRef.current?.clientWidth ?? 400;
    const height = containerRef.current?.clientHeight ?? 300;
    canvas.width = width * window.devicePixelRatio;
    canvas.height = height * window.devicePixelRatio;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    ctx.clearRect(0, 0, width, height);

    // Gather sheets color map
    const sheetColorMap = new Map<string, string>();
    project.sheets.forEach(s => {
      sheetColorMap.set(s.id, s.swatch || 'var(--text-dim)');
    });

    // We build the list of all 3D faces (panels) to render
    const faces: {
      tierIdx: number;
      panelIdx: number;
      depth: number;
      poly2d: { x: number; y: number }[];
      pieces: {
        piece: Piece;
        poly2d: { x: number; y: number }[];
        color: string;
      }[];
    }[] = [];

    const isSmooth = N === 32;

    for (let t = 0; t < profilePoints.length - 1; t++) {
      const Rt = profilePoints[t].r;
      const Yt = profilePoints[t].y;
      const Rb = profilePoints[t + 1].r;
      const Yb = profilePoints[t + 1].y;

      for (let i = 0; i < N; i++) {
        const theta_start = i * (2 * Math.PI / N);
        const theta_end = (i + 1) * (2 * Math.PI / N);

        // Quad corner vertices in 3D
        const p_tl: [number, number, number] = [Rt * Math.cos(theta_start), Yt, Rt * Math.sin(theta_start)];
        const p_tr: [number, number, number] = [Rt * Math.cos(theta_end), Yt, Rt * Math.sin(theta_end)];
        const p_br: [number, number, number] = [Rb * Math.cos(theta_end), Yb, Rb * Math.sin(theta_end)];
        const p_bl: [number, number, number] = [Rb * Math.cos(theta_start), Yb, Rb * Math.sin(theta_start)];

        const s_tl = projectPoint(p_tl, width, height);
        const s_tr = projectPoint(p_tr, width, height);
        const s_br = projectPoint(p_br, width, height);
        const s_bl = projectPoint(p_bl, width, height);

        const avgDepth = (s_tl.depth + s_tr.depth + s_br.depth + s_bl.depth) / 4;

        // Gather all pieces belonging to this tier and project them to this panel
        const tierPieces = project.pieces.filter(
          p => (p.tierIndex === t || (!p.tierIndex && t === 0))
        );

        const projectedPieces = tierPieces.map(piece => {
          // Wrap the 2D polygon of this piece to 3D and project to screen
          const poly3d = piece.polygon.map(([px, py]) => get3DCoords(px, py, t, i));
          const poly2d = poly3d.map(pt => projectPoint(pt, width, height));
          const color = sheetColorMap.get(piece.glassSheetId) || '#cccccc';

          return {
            piece,
            poly2d,
            color,
          };
        });

        faces.push({
          tierIdx: t,
          panelIdx: i,
          depth: avgDepth,
          poly2d: [s_tl, s_tr, s_br, s_bl],
          pieces: projectedPieces,
        });
      }
    }

    // Depth Sorting (Painter's Algorithm) — Back-to-Front
    faces.sort((a, b) => b.depth - a.depth);

    // Render faces
    faces.forEach(({ tierIdx, panelIdx, poly2d, pieces }) => {
      // Backface test
      // Vector AB and AC in screen coords
      const ax = poly2d[1].x - poly2d[0].x;
      const ay = poly2d[1].y - poly2d[0].y;
      const bx = poly2d[3].x - poly2d[0].x;
      const by = poly2d[3].y - poly2d[0].y;
      const crossProduct = ax * by - ay * bx;

      const isFront = crossProduct > 0;
      
      // Calculate normal and light shading
      // Light vector from front-top-left
      const normalZ = isFront ? 1 : -0.7;
      let lightShading = isFront ? 0.8 : 0.45; // Default ambient

      // Add simple flat shading based on face normal rotation
      const theta = (panelIdx + 0.5) * (2 * Math.PI / N) + yaw;
      const cosTheta = Math.cos(theta);
      if (isFront) {
        // Bright light source from front-left
        lightShading += cosTheta * 0.15;
      }

      // Draw the panel background (frame)
      ctx.beginPath();
      ctx.moveTo(poly2d[0].x, poly2d[0].y);
      poly2d.slice(1).forEach(pt => ctx.lineTo(pt.x, pt.y));
      ctx.closePath();

      // Translucent parchment color for the blank frame, darker if active tier is different
      const isActiveTier = tierIdx === activeTierIndex;
      const baseFill = isActiveTier
        ? `rgba(247, 241, 227, ${lightShading * 0.9})`
        : `rgba(220, 215, 200, ${lightShading * 0.6})`;

      ctx.fillStyle = baseFill;
      ctx.fill();

      // Draw pieces inside this panel
      pieces.forEach(({ piece, poly2d: piecePoly, color }) => {
        if (piecePoly.length < 3) return;
        ctx.beginPath();
        ctx.moveTo(piecePoly[0].x, piecePoly[0].y);
        piecePoly.slice(1).forEach(pt => ctx.lineTo(pt.x, pt.y));
        ctx.closePath();

        // Apply light shading to the glass color
        ctx.fillStyle = color;
        ctx.fill();

        // Overlay flat shading tint for depth
        ctx.fillStyle = isFront
          ? `rgba(255, 255, 255, ${Math.max(0, (lightShading - 0.7) * 0.5)})`
          : `rgba(0, 0, 0, 0.35)`;
        ctx.fill();

        // Highlight selected piece
        const isPieceSelected = selectedPieceIds.includes(piece.id);
        ctx.strokeStyle = isPieceSelected ? '#c08a1f' : '#1a1a1a';
        ctx.lineWidth = isPieceSelected ? 2.5 : 1.25;
        ctx.stroke();
      });

      // Draw panel boundaries (structural lead wire)
      // Only draw dividers if N < 32 (not Smooth)
      if (!isSmooth || (tierIdx === 0 && !isFront)) {
        ctx.beginPath();
        ctx.moveTo(poly2d[0].x, poly2d[0].y);
        poly2d.slice(1).forEach(pt => ctx.lineTo(pt.x, pt.y));
        ctx.closePath();
        
        ctx.strokeStyle = isActiveTier && isFront ? 'rgba(90, 81, 66, 0.4)' : 'rgba(90, 81, 66, 0.18)';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    });

  }, [yaw, pitch, project, selectedPieceIds, activeTierIndex, N, profilePoints]);

  // Handlers for dragging to rotate 3D preview
  // Handlers for dragging to rotate 3D preview
  const handleCanvasClick = (e: React.PointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    const width = rect.width;
    const height = rect.height;

    // Helper: Point in polygon
    const isPointInPolygon = (px: number, py: number, polygon: { x: number; y: number }[]): boolean => {
      let inside = false;
      for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
        const xi = polygon[i].x, yi = polygon[i].y;
        const xj = polygon[j].x, yj = polygon[j].y;
        const intersect = ((yi > py) !== (yj > py)) &&
          (px < (xj - xi) * (py - yi) / (yj - yi) + xi);
        if (intersect) inside = !inside;
      }
      return inside;
    };

    // Calculate all faces
    const faces: {
      tierIdx: number;
      panelIdx: number;
      depth: number;
      poly2d: { x: number; y: number }[];
    }[] = [];

    for (let t = 0; t < profilePoints.length - 1; t++) {
      const Rt = profilePoints[t].r;
      const Yt = profilePoints[t].y;
      const Rb = profilePoints[t + 1].r;
      const Yb = profilePoints[t + 1].y;

      for (let i = 0; i < N; i++) {
        const theta_start = i * (2 * Math.PI / N);
        const theta_end = (i + 1) * (2 * Math.PI / N);

        const p_tl: [number, number, number] = [Rt * Math.cos(theta_start), Yt, Rt * Math.sin(theta_start)];
        const p_tr: [number, number, number] = [Rt * Math.cos(theta_end), Yt, Rt * Math.sin(theta_end)];
        const p_br: [number, number, number] = [Rb * Math.cos(theta_end), Yb, Rb * Math.sin(theta_end)];
        const p_bl: [number, number, number] = [Rb * Math.cos(theta_start), Yb, Rb * Math.sin(theta_start)];

        const s_tl = projectPoint(p_tl, width, height);
        const s_tr = projectPoint(p_tr, width, height);
        const s_br = projectPoint(p_br, width, height);
        const s_bl = projectPoint(p_bl, width, height);

        const avgDepth = (s_tl.depth + s_tr.depth + s_br.depth + s_bl.depth) / 4;

        faces.push({
          tierIdx: t,
          panelIdx: i,
          depth: avgDepth,
          poly2d: [s_tl, s_tr, s_br, s_bl],
        });
      }
    }

    // Filter only front-facing and matching click
    const clickedFaces = faces
      .filter(f => {
        const ax = f.poly2d[1].x - f.poly2d[0].x;
        const ay = f.poly2d[1].y - f.poly2d[0].y;
        const bx = f.poly2d[3].x - f.poly2d[0].x;
        const by = f.poly2d[3].y - f.poly2d[0].y;
        const cross = ax * by - ay * bx;
        return cross > 0; // Front facing in screen projection
      })
      .filter(f => isPointInPolygon(clickX, clickY, f.poly2d));

    if (clickedFaces.length > 0) {
      // Find the one with the smallest depth (i.e. closest to camera)
      clickedFaces.sort((a, b) => a.depth - b.depth);
      const target = clickedFaces[0];
      onUpdateLampConfig({ activeTierIndex: target.tierIdx });
      onSetFocusedPanelIdx(target.panelIdx);
    }
  };

  const handlePointerDown = (e: React.PointerEvent) => {
    isDragging.current = true;
    dragStart.current = { x: e.clientX, y: e.clientY };
    rotStart.current = { yaw, pitch };
    (e.currentTarget as HTMLCanvasElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging.current) return;
    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;
    setYaw(rotStart.current.yaw - dx * 0.015);
    setPitch(Math.max(-Math.PI / 3, Math.min(Math.PI / 3, rotStart.current.pitch - dy * 0.015)));
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    isDragging.current = false;
    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;
    if (Math.hypot(dx, dy) < 3) {
      handleCanvasClick(e);
    }
  };

  // Profile Editor Drag logic
  const handleProfilePointDrag = (idx: number, dx: number, dy: number) => {
    const updated = [...profilePoints];
    const pt = updated[idx];

    // Scale delta (let's say 1px drag = 1px coordinate change)
    let newR = Math.max(0, pt.r + dx);
    let newY = pt.y + dy;

    // Top point fixed at Y=0
    if (idx === 0) {
      newY = 0;
    } else {
      // Y constraints based on neighbors
      const minY = updated[idx - 1].y + 15;
      const maxY = idx < updated.length - 1 ? updated[idx + 1].y - 15 : 400; // clamp bottom height
      newY = Math.min(Math.max(newY, minY), maxY);
    }

    updated[idx] = { r: Math.round(newR), y: Math.round(newY) };
    onUpdateLampConfig({ profilePoints: updated });
  };

  const handleAddProfilePoint = (y: number, r: number) => {
    // Find where to insert the new point based on its Y coordinate
    const updated = [...profilePoints];
    let insertIdx = -1;
    for (let i = 0; i < updated.length; i++) {
      if (y < updated[i].y) {
        insertIdx = i;
        break;
      }
    }

    const newPt = { r: Math.round(r), y: Math.round(y) };
    if (insertIdx === -1) {
      updated.push(newPt);
      insertIdx = updated.length - 1;
    } else {
      updated.splice(insertIdx, 0, newPt);
    }

    onUpdateLampConfig({ profilePoints: updated });
    setSelectedPointIdx(insertIdx);
  };

  const handleDeleteProfilePoint = (idx: number) => {
    if (profilePoints.length <= 2) return; // Keep at least 1 segment
    const updated = profilePoints.filter((_, i) => i !== idx);
    const newActiveTier = Math.min(activeTierIndex, updated.length - 2);

    onUpdateLampConfig({
      profilePoints: updated,
      activeTierIndex: newActiveTier,
    });
    setSelectedPointIdx(Math.max(0, idx - 1));
  };

  // Convert client SVG coordinates to Graph space
  const svgRef = useRef<SVGSVGElement>(null);
  const activeDragPointIdx = useRef<number | null>(null);
  const dragStartCoords = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  const handleSvgPointerDown = (e: React.PointerEvent, idx: number) => {
    e.stopPropagation();
    activeDragPointIdx.current = idx;
    setSelectedPointIdx(idx);
    dragStartCoords.current = { x: e.clientX, y: e.clientY };
    (e.currentTarget as SVGElement).setPointerCapture(e.pointerId);
  };

  const handleSvgPointerMove = (e: React.PointerEvent) => {
    if (activeDragPointIdx.current === null) return;
    const dx = e.clientX - dragStartCoords.current.x;
    const dy = e.clientY - dragStartCoords.current.y;
    handleProfilePointDrag(activeDragPointIdx.current, dx * 0.8, dy * 0.8);
    dragStartCoords.current = { x: e.clientX, y: e.clientY };
  };

  const handleSvgPointerUp = () => {
    activeDragPointIdx.current = null;
  };

  const handleSvgBgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // Convert SVG local pixel space to graph space:
    // graph x = (x - 20) / 0.8
    // graph y = (y - 15) / 0.8
    const rVal = (x - 20) / 0.8;
    const yVal = (y - 15) / 0.8;

    if (rVal >= 0 && yVal >= 0 && yVal <= 260) {
      handleAddProfilePoint(yVal, rVal);
    }
  };

  // Profile Editor SVG size & scale
  // Margins: left=20, top=15
  // Scale factor: 0.8 (graph pixels per actual pixel)
  const profileLinePath = useMemo(() => {
    return profilePoints
      .map((pt, i) => `${i === 0 ? 'M' : 'L'} ${20 + pt.r * 0.8} ${15 + pt.y * 0.8}`)
      .join(' ');
  }, [profilePoints]);

  return (
    <div
      ref={containerRef}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--chrome-800)',
      }}
    >
      {/* 3D Passive Viewport */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        <canvas
          ref={canvasRef}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          style={{ cursor: isDragging.current ? 'grabbing' : 'grab', display: 'block', width: '100%', height: '100%' }}
        />
        <div style={{ position: 'absolute', top: 8, left: 10, pointerEvents: 'none' }}>
          <span style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-dim)' }}>
            3D Preview (Drag to Spin)
          </span>
        </div>
      </div>
    </div>
  );
}
