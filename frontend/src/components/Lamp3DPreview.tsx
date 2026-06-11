import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import type { Project, LampConfig, GlassSheet } from '../types';
import { computeUnrolledLamp, patternToSurface } from '../utils/lampGeometry';
import { computeCentroid, flattenCurves } from '../utils/geometry';
import { getSheetMaterial, toRenderParams } from '../utils/glassMaterial';

interface Props {
  project: Project;
  selectedPieceIds: string[];
  onSelectPiece: (id: string | null) => void;
  onUpdateLampConfig: (config: Partial<LampConfig>, skipHistory?: boolean) => void;
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

// Bulb uses physical (decay-2) falloff over pattern-pixel distances, so its
// intensity is scaled by the lamp radius squared to stay stable across sizes.
const BULB_SCALE = 2.5;

export function Lamp3DPreview({ project, onUpdateLampConfig }: Props) {
  const { t } = useTranslation();
  const config = project.lampConfig ?? DEFAULT_CONFIG;
  const unrolledLamp = useMemo(() => computeUnrolledLamp(config), [config]);

  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const lampGroupRef = useRef<THREE.Group | null>(null);
  const bulbRef = useRef<THREE.PointLight | null>(null);

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

    // Use a massive far plane (100000) so large pixel-scale coordinates never clip
    const camera = new THREE.PerspectiveCamera(35, 1, 1, 100000);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
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

    // Soft studio environment for PBR reflections (no HDRI asset needed).
    const pmrem = new THREE.PMREMGenerator(renderer);
    const envRT = pmrem.fromScene(new RoomEnvironment());
    pmrem.dispose();
    scene.environment = envRT.texture;

    // Ambient stays low — the environment map carries most of the fill light.
    scene.add(new THREE.AmbientLight(0xffffff, 0.35));
    const dir = new THREE.DirectionalLight(0xffffff, 0.35);
    dir.position.set(-1, 1.5, 1.2);
    scene.add(dir);

    // The bulb inside the lamp; position/intensity follow the lamp profile.
    const bulb = new THREE.PointLight(0xfff1d6, 0, 0, 2);
    scene.add(bulb);
    bulbRef.current = bulb;

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
      envRT.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
      // Cached textures stay alive across mounts.
    };
  }, []);

  // ── Bulb light follows the lamp profile and brightness setting ────────
  useEffect(() => {
    const bulb = bulbRef.current;
    const renderer = rendererRef.current;
    if (!bulb || !renderer) return;
    const { profilePoints } = config;
    if (profilePoints.length === 0) return;
    const maxR = Math.max(...profilePoints.map(p => p.r));
    const minY = Math.min(...profilePoints.map(p => p.y));
    const maxY = Math.max(...profilePoints.map(p => p.y));
    bulb.position.set(0, (minY + maxY) / 2, 0);
    bulb.intensity = (config.bulbIntensity ?? 1) * maxR * maxR * BULB_SCALE;
    (renderer as unknown as { _render?: () => void })._render?.();
  }, [config]);

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

    // Map a piece vertex (in pattern coords) to its 3D position on the lamp.
    const vertexTo3D = (
      px: number,
      py: number,
      preferredFacetIdx?: number,
      preferredTierIdx?: number
    ): [number, number, number] | null => {
      let surf: any = null;

      if (preferredFacetIdx !== undefined && unrolledLamp && unrolledLamp.mode === 'faceted') {
        const strip = unrolledLamp.strips[preferredFacetIdx];
        if (strip) {
          const cx = strip.centerX;
          const tiers = preferredTierIdx !== undefined ? [strip.tiers[preferredTierIdx]] : strip.tiers;
          for (const tier of tiers) {
            if (!tier) continue;
            if (preferredTierIdx === undefined) {
              if (py < tier.topY - 1.0 || py > tier.botY + 1.0) continue;
            }
            const tierH = Math.max(1e-6, tier.botY - tier.topY);
            const vy = Math.max(0, Math.min(1, (py - tier.topY) / tierH));
            const widthAtV = tier.topChord * (1 - vy) + tier.botChord * vy;
            const leftAtV = cx - widthAtV / 2;
            const u = (px - leftAtV) / Math.max(1e-6, widthAtV);
            const uClamped = Math.max(0, Math.min(1, u));
            surf = { mode: 'faceted', tierIdx: tier.tierIdx, facetIdx: strip.facetIdx, u: uClamped, v: vy };
            break;
          }
        }
      } else if (preferredTierIdx !== undefined && unrolledLamp && unrolledLamp.mode === 'smooth') {
        const tier = unrolledLamp.tiers[preferredTierIdx];
        if (tier) {
          const m = tier.meta;
          if (m.type === 'cylinder') {
            const theta01 = Math.max(0, Math.min(1, (px - m.leftX) / m.width));
            const v = Math.max(0, Math.min(1, (py - m.topY) / m.height));
            surf = { mode: 'smooth', tierIdx: tier.tierIdx, theta01, v };
          } else {
            const dx = px - m.apexX;
            const dy = py - m.apexY;
            const d = Math.hypot(dx, dy);
            const v = Math.max(0, Math.min(1, (d - m.L_top) / Math.max(1e-6, m.L_bot - m.L_top)));
            const angleRel = Math.atan2(m.bisectorSign * dx, m.bisectorSign * dy);
            const theta01 = Math.max(0, Math.min(1, (angleRel + m.theta / 2) / m.theta));
            surf = { mode: 'smooth', tierIdx: tier.tierIdx, theta01, v };
          }
        }
      }

      if (!surf) {
        surf = patternToSurface(px, py, unrolledLamp);
      }

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

    const allVertices: THREE.Vector3[] = [];
    const allEdges: { p1: THREE.Vector3, p2: THREE.Vector3 }[] = [];

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
        const pos = vertexTo3D(px, py, piece.facetIndex, piece.tierIndex);
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
      const matParams = getSheetMaterial(sheet);
      const rp = toRenderParams(matParams, config.bulbIntensity ?? 1, project.patternScale);
      const material = new THREE.MeshPhysicalMaterial({
        map: texture,
        side: THREE.DoubleSide,
        transmission: rp.transmission,
        roughness: rp.roughness,
        thickness: rp.thickness,
        ior: rp.ior,
        // The glass glows with its own texture colors when the bulb is on —
        // a cheap stand-in for light transmitted through the sheet.
        emissive: new THREE.Color(matParams.glowTint ?? '#ffffff'),
        emissiveMap: texture,
        emissiveIntensity: rp.emissiveIntensity,
      });
      const mesh = new THREE.Mesh(geom, material);
      // Render after the shell so the glass pixels show through cleanly.
      mesh.renderOrder = 1;
      group.add(mesh);

      // Collect piece perimeter segments for 3D solder lines
      for (let i = 0; i < positions.length; i += 3) {
        const p1 = new THREE.Vector3(positions[i], positions[i + 1], positions[i + 2]);
        allVertices.push(p1);
        const nextI = (i + 3) % positions.length;
        const p2 = new THREE.Vector3(positions[nextI], positions[nextI + 1], positions[nextI + 2]);
        allEdges.push({ p1, p2 });
      }
    }

    // Render true 3D solder thickness
    if (allEdges.length > 0) {
      let solderRawRadius = 1;
      const solderWidthMM = project.solderWidthMM || 2;
      if (project.patternScale) {
        const { pxPerUnit, unit } = project.patternScale;
        if (unit === 'in') {
          solderRawRadius = (solderWidthMM / 25.4) * pxPerUnit / 2;
        } else if (unit === 'cm') {
          solderRawRadius = (solderWidthMM / 10) * pxPerUnit / 2;
        } else {
          solderRawRadius = solderWidthMM * pxPerUnit / 2;
        }
      } else {
        solderRawRadius = solderWidthMM; // fallback
      }

      const solderColorStr = project.solderColor || 'black';
      const colorHex = solderColorStr === 'silver' ? 0xbbbbbb : (solderColorStr === 'copper' ? 0xc87333 : 0x222222);
      const metalness = solderColorStr === 'black' ? 0.4 : 0.8;
      const roughness = solderColorStr === 'black' ? 0.7 : 0.3;

      const solderMat = new THREE.MeshStandardMaterial({ 
        color: colorHex, 
        metalness, 
        roughness,
      });

      const cylGeom = new THREE.CylinderGeometry(1, 1, 1, 6);
      cylGeom.rotateX(Math.PI / 2); // align with Z axis for lookAt
      const cylMesh = new THREE.InstancedMesh(cylGeom, solderMat, allEdges.length);
      const dummy = new THREE.Object3D();

      allEdges.forEach((edge, i) => {
        const dist = edge.p1.distanceTo(edge.p2);
        dummy.position.copy(edge.p1).lerp(edge.p2, 0.5);
        dummy.scale.set(solderRawRadius, solderRawRadius, dist);
        dummy.lookAt(edge.p2);
        dummy.updateMatrix();
        cylMesh.setMatrixAt(i, dummy.matrix);
      });
      cylMesh.renderOrder = 2;
      group.add(cylMesh);

      const sphGeom = new THREE.SphereGeometry(1, 6, 6);
      const sphMesh = new THREE.InstancedMesh(sphGeom, solderMat, allVertices.length);
      allVertices.forEach((v, i) => {
        dummy.position.copy(v);
        dummy.quaternion.identity();
        dummy.scale.setScalar(solderRawRadius);
        dummy.updateMatrix();
        sphMesh.setMatrixAt(i, dummy.matrix);
      });
      sphMesh.renderOrder = 2;
      group.add(sphMesh);
    }

    requestRender();
  }, [config, project.pieces, project.sheets, project.patternScale, unrolledLamp]);

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
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', minHeight: 0 }}>
      <div className="panel-header">
        <div className="panel-title">
          <span className="panel-title-eyebrow">3D PREVIEW (DRAG TO SPIN)</span>
        </div>
        <label
          title={t('bulbBrightness', 'Bulb brightness')}
          style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto', cursor: 'pointer' }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M9 18h6" /><path d="M10 22h4" />
            <path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />
          </svg>
          <input
            type="range"
            min={0}
            max={2}
            step={0.05}
            value={config.bulbIntensity ?? 1}
            onChange={e => onUpdateLampConfig({ bulbIntensity: Number(e.target.value) }, true)}
            onPointerUp={e => onUpdateLampConfig({ bulbIntensity: Number((e.target as HTMLInputElement).value) })}
            style={{ width: 90 }}
            aria-label={t('bulbBrightness', 'Bulb brightness')}
          />
        </label>
      </div>
      <div
        className="canvas-well"
        ref={containerRef}
        style={{ flex: 1, minHeight: 0, position: 'relative', touchAction: 'none', overscrollBehavior: 'none' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      />
    </div>
  );
}
