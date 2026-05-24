import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import type { Project, LampConfig, GlassSheet } from '../types';
import { computeUnrolledLamp, patternToSurface } from '../utils/lampGeometry';
import { computeCentroid, flattenCurves } from '../utils/geometry';

interface Props {
  project: Project;
  selectedPieceIds: string[];
  onSelectPiece: (id: string | null) => void;
  onUpdateLampConfig: (config: Partial<LampConfig>) => void;
  activeSheetId: string;
  onSetFocusedPanelIdx: (idx: number | null) => void;
}

const DEFAULT_CONFIG: LampConfig = {
  facetCount: 6,
  profilePoints: [
    { r: 50, y: 0 },
    { r: 100, y: 80 },
    { r: 100, y: 140 },
  ],
  activeTierIndex: 0,
};

// Module-level texture cache shared across instances — sheet image URLs rarely change.
const textureCache = new Map<string, THREE.Texture>();

function loadSheetTexture(sheet: GlassSheet, onLoad: () => void): THREE.Texture {
  const key = sheet.imageUrl;
  if (!key) {
    return new THREE.Texture();
  }
  const existing = textureCache.get(key);
  if (existing) {
    if (existing.image) onLoad();
    return existing;
  }
  const tx = new THREE.TextureLoader().load(key, () => onLoad());
  tx.colorSpace = THREE.SRGBColorSpace;
  tx.wrapS = THREE.ClampToEdgeWrapping;
  tx.wrapT = THREE.ClampToEdgeWrapping;
  textureCache.set(key, tx);
  return tx;
}

export function Lamp3DPreview({ project }: Props) {
  const config = project.lampConfig ?? DEFAULT_CONFIG;
  const unrolledLamp = useMemo(() => computeUnrolledLamp(config), [config]);

  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const lampGroupRef = useRef<THREE.Group | null>(null);

  const [yaw, setYaw] = useState(0.6);
  const [pitch, setPitch] = useState(0.3);
  const [zoom, setZoom] = useState(1.0);
  const yawRef = useRef(yaw);
  yawRef.current = yaw;
  const pitchRef = useRef(pitch);
  pitchRef.current = pitch;

  const dragRef = useRef<{ x: number; y: number; yaw: number; pitch: number } | null>(null);

  // ── One-time scene setup ──────────────────────────────────────────────
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(35, 1, 1, 5000);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    rendererRef.current = renderer;
    container.appendChild(renderer.domElement);
    renderer.domElement.style.display = 'block';
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    renderer.domElement.style.cursor = 'grab';
    renderer.domElement.style.touchAction = 'none';

    const group = new THREE.Group();
    scene.add(group);
    lampGroupRef.current = group;

    scene.add(new THREE.AmbientLight(0xffffff, 0.85));
    const dir = new THREE.DirectionalLight(0xffffff, 0.35);
    dir.position.set(-1, 1.5, 1.2);
    scene.add(dir);

    const render = () => {
      renderer.render(scene, camera);
    };
    (renderer as unknown as { _render: () => void })._render = render;

    function resize() {
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w === 0 || h === 0) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      render();
    }
    const ro = new ResizeObserver(resize);
    ro.observe(container);
    resize();

    return () => {
      ro.disconnect();
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
      // Cached textures stay alive across mounts.
    };
  }, []);

  // ── Rebuild lamp meshes when config / pieces / sheets change ──────────
  useEffect(() => {
    const group = lampGroupRef.current;
    const renderer = rendererRef.current;
    if (!group || !renderer) return;

    for (let i = group.children.length - 1; i >= 0; i--) {
      const obj = group.children[i];
      group.remove(obj);
      if (obj instanceof THREE.Mesh) {
        obj.geometry?.dispose();
        const mat = obj.material;
        if (Array.isArray(mat)) mat.forEach(m => m.dispose());
        else (mat as THREE.Material).dispose();
      } else if (obj instanceof THREE.LineSegments) {
        obj.geometry?.dispose();
        (obj.material as THREE.Material).dispose();
      }
    }

    const { profilePoints } = config;
    // Use a high segment count when smooth so the lamp reads as curved.
    const N = config.smooth ? 48 : config.facetCount;
    const sheetById = new Map<string, GlassSheet>();
    project.sheets.forEach(s => sheetById.set(s.id, s));

    const requestRender = () =>
      (renderer as unknown as { _render?: () => void })._render?.();

    // ── Lamp shell (parchment quads per segment around) ─────────────────
    const shellPositions: number[] = [];
    const shellIndices: number[] = [];
    let nextIdx = 0;
    for (let t = 0; t < profilePoints.length - 1; t++) {
      const Rt = profilePoints[t].r;
      const Yt = profilePoints[t].y;
      const Rb = profilePoints[t + 1].r;
      const Yb = profilePoints[t + 1].y;
      for (let i = 0; i < N; i++) {
        const a0 = i * (2 * Math.PI / N);
        const a1 = (i + 1) * (2 * Math.PI / N);
        const tl = [Rt * Math.cos(a0), Yt, Rt * Math.sin(a0)];
        const tr = [Rt * Math.cos(a1), Yt, Rt * Math.sin(a1)];
        const br = [Rb * Math.cos(a1), Yb, Rb * Math.sin(a1)];
        const bl = [Rb * Math.cos(a0), Yb, Rb * Math.sin(a0)];
        const base = nextIdx;
        shellPositions.push(...tl, ...tr, ...br, ...bl);
        shellIndices.push(base, base + 1, base + 2, base, base + 2, base + 3);
        nextIdx += 4;
      }
    }
    const shellGeom = new THREE.BufferGeometry();
    shellGeom.setAttribute('position', new THREE.Float32BufferAttribute(shellPositions, 3));
    shellGeom.setIndex(shellIndices);
    shellGeom.computeVertexNormals();
    const shellMat = new THREE.MeshLambertMaterial({
      color: 0xf7f1e3,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.18,
      depthWrite: false,
    });
    const shell = new THREE.Mesh(shellGeom, shellMat);
    group.add(shell);

    // Wireframe edges — skip in smooth mode where we don't want individual segment lines.
    if (!config.smooth) {
      const edges = new THREE.EdgesGeometry(shellGeom, 1);
      const wireMat = new THREE.LineBasicMaterial({ color: 0x5a5142, transparent: true, opacity: 0.32 });
      group.add(new THREE.LineSegments(edges, wireMat));
    }

    // ── Pieces, textured with their glass sheet ────────────────────────
    // Map a piece vertex (in pattern coords) to its 3D position on the lamp.
    const vertexTo3D = (px: number, py: number): [number, number, number] | null => {
      const surf = patternToSurface(px, py, unrolledLamp);
      if (!surf) return null;
      if (surf.tierIdx >= profilePoints.length - 1) return null;
      const Rt = profilePoints[surf.tierIdx].r;
      const Yt = profilePoints[surf.tierIdx].y;
      const Rb = profilePoints[surf.tierIdx + 1].r;
      const Yb = profilePoints[surf.tierIdx + 1].y;
      if (surf.mode === 'faceted') {
        const a0 = surf.facetIdx * (2 * Math.PI / N);
        const a1 = (surf.facetIdx + 1) * (2 * Math.PI / N);
        const v_tl = [Rt * Math.cos(a0), Yt, Rt * Math.sin(a0)];
        const v_tr = [Rt * Math.cos(a1), Yt, Rt * Math.sin(a1)];
        const v_br = [Rb * Math.cos(a1), Yb, Rb * Math.sin(a1)];
        const v_bl = [Rb * Math.cos(a0), Yb, Rb * Math.sin(a0)];
        const { u, v } = surf;
        return [
          (1 - v) * ((1 - u) * v_tl[0] + u * v_tr[0]) + v * ((1 - u) * v_bl[0] + u * v_br[0]),
          (1 - v) * ((1 - u) * v_tl[1] + u * v_tr[1]) + v * ((1 - u) * v_bl[1] + u * v_br[1]),
          (1 - v) * ((1 - u) * v_tl[2] + u * v_tr[2]) + v * ((1 - u) * v_bl[2] + u * v_br[2]),
        ];
      }
      // smooth: direct parametric mapping on the lamp surface.
      const theta = surf.theta01 * 2 * Math.PI;
      const radius = Rt * (1 - surf.v) + Rb * surf.v;
      const yLamp = Yt * (1 - surf.v) + Yb * surf.v;
      return [radius * Math.cos(theta), yLamp, radius * Math.sin(theta)];
    };

    for (const piece of project.pieces) {
      const flat = flattenCurves(piece.polygon, piece.curvePoints);
      if (flat.length < 3) continue;

      const sheet = sheetById.get(piece.glassSheetId);
      if (!sheet) continue;

      const centroid2D = computeCentroid(piece.polygon);
      const { x: tx, y: ty, rotation, scale } = piece.transform;
      const cosR = Math.cos(rotation);
      const sinR = Math.sin(rotation);
      const sheetW = sheet.naturalWidth ?? 800;
      const sheetH = sheet.naturalHeight ?? 600;

      const positions: number[] = [];
      const uvs: number[] = [];
      let skip = false;
      for (const [px, py] of flat) {
        const pos = vertexTo3D(px, py);
        if (!pos) { skip = true; break; }
        positions.push(...pos);

        // Pattern → sheet via the piece transform, then sheet → UV.
        // V is flipped because three.js samples textures bottom-up.
        const rx = px - centroid2D.x;
        const ry = py - centroid2D.y;
        const sx = rx * cosR - ry * sinR;
        const sy = rx * sinR + ry * cosR;
        const sheetX = sx * scale + tx;
        const sheetY = sy * scale + ty;
        uvs.push(sheetX / sheetW, 1 - sheetY / sheetH);
      }
      if (skip) continue;

      // Fan triangulation from vertex 0 — fine for convex pieces (the common case).
      const indices: number[] = [];
      for (let i = 1; i < flat.length - 1; i++) {
        indices.push(0, i, i + 1);
      }

      const geom = new THREE.BufferGeometry();
      geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      geom.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
      geom.setIndex(indices);
      geom.computeVertexNormals();

      const texture = loadSheetTexture(sheet, requestRender);
      const material = new THREE.MeshBasicMaterial({
        map: texture,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 1,
      });
      const mesh = new THREE.Mesh(geom, material);
      // Render after the shell so the glass pixels show through cleanly.
      mesh.renderOrder = 1;
      group.add(mesh);
    }

    requestRender();
  }, [config, project.pieces, project.sheets, unrolledLamp]);

  // ── Camera from yaw / pitch + auto-frame ─────────────────────────────
  useEffect(() => {
    const camera = cameraRef.current;
    const renderer = rendererRef.current;
    if (!camera || !renderer) return;

    const { profilePoints } = config;
    if (profilePoints.length === 0) return;

    const maxR = Math.max(...profilePoints.map(p => p.r));
    const minY = Math.min(...profilePoints.map(p => p.y));
    const maxY = Math.max(...profilePoints.map(p => p.y));
    const centerY = (minY + maxY) / 2;
    const totalH = maxY - minY;
    const fitDist = (Math.max(maxR, totalH) * 4.2) / zoom;

    const cx = fitDist * Math.cos(pitch) * Math.sin(yaw);
    const cy = centerY - fitDist * Math.sin(pitch);
    const cz = fitDist * Math.cos(pitch) * Math.cos(yaw);

    camera.position.set(cx, cy, cz);
    // Lamp's profile uses +y downward, so flip "up" to render right-side-up.
    camera.up.set(0, -1, 0);
    camera.lookAt(0, centerY, 0);

    (renderer as unknown as { _render?: () => void })._render?.();
  }, [yaw, pitch, zoom, config]);

  function onPointerDown(e: React.PointerEvent) {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    dragRef.current = { x: e.clientX, y: e.clientY, yaw: yawRef.current, pitch: pitchRef.current };
    if (rendererRef.current) rendererRef.current.domElement.style.cursor = 'grabbing';
  }
  function onPointerMove(e: React.PointerEvent) {
    const drag = dragRef.current;
    if (!drag) return;
    const dx = e.clientX - drag.x;
    const dy = e.clientY - drag.y;
    setYaw(drag.yaw + dx * 0.01);
    setPitch(Math.max(-Math.PI / 2 + 0.1, Math.min(Math.PI / 2 - 0.1, drag.pitch + dy * 0.01)));
  }
  function onPointerUp() {
    dragRef.current = null;
    if (rendererRef.current) rendererRef.current.domElement.style.cursor = 'grab';
  }

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    function handleWheel(e: WheelEvent) {
      e.preventDefault();
      setZoom(z => Math.max(0.1, Math.min(10.0, z * (1 - e.deltaY * 0.001))));
    }
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => el.removeEventListener('wheel', handleWheel);
  }, []);

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%', position: 'relative', touchAction: 'none', overscrollBehavior: 'none' }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div style={{ position: 'absolute', top: 8, left: 10, pointerEvents: 'none', zIndex: 1 }}>
        <span style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-dim)' }}>
          3D Preview (Drag to Spin)
        </span>
      </div>
    </div>
  );
}
