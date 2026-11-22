import polygonClipping from 'polygon-clipping';
import type { CurvePoint, Scale, ScaleUnit } from '../types';
import { flattenCurves } from './geometry';

export type SvgImportMode = 'shapes' | 'lines';

export interface SvgImportedPiece {
  polygon: [number, number][];
  curvePoints?: CurvePoint[];
  label?: string;
}

export interface SvgDimensions {
  viewBox: { x: number; y: number; width: number; height: number };
  physicalScale: { pxPerUnit: number; unit: ScaleUnit } | null;
}

export interface SvgAnalysisStats {
  closedCount: number;
  openCount: number;
  openLengthRatio: number;
  anyHasFill: boolean;
  overlapRatio: number;
  isLeadWeb: boolean;
}

export interface SvgCanvasTarget {
  /** Target canvas width/height in Vitrai pattern pixels. */
  width: number;
  height: number;
  /** Optional placement box inside target canvas (used when appending onto an existing canvas). */
  fitBox?: { x: number; y: number; width: number; height: number };
}

export interface SvgVectorParseResult {
  dimensions: SvgDimensions;
  canvasWidth: number;
  canvasHeight: number;
  scale: Scale;
  pieces: SvgImportedPiece[];
  stats: SvgAnalysisStats;
  recommendedMode: SvgImportMode;
}

type Matrix = [number, number, number, number, number, number]; // [a, b, c, d, e, f]
type Pt = [number, number];

const IDENTITY: Matrix = [1, 0, 0, 1, 0, 0];

function mulMatrix(m1: Matrix, m2: Matrix): Matrix {
  const [a1, b1, c1, d1, e1, f1] = m1;
  const [a2, b2, c2, d2, e2, f2] = m2;
  return [
    a1 * a2 + c1 * b2,
    b1 * a2 + d1 * b2,
    a1 * c2 + c1 * d2,
    b1 * c2 + d1 * d2,
    a1 * e2 + c1 * f2 + e1,
    b1 * e2 + d1 * f2 + f1,
  ];
}

function applyMatrix(m: Matrix, x: number, y: number): Pt {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

export function parseTransform(str: string | undefined): Matrix {
  if (!str) return IDENTITY;
  let m: Matrix = IDENTITY;
  const re = /([a-zA-Z]+)\s*\(([^)]*)\)/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(str)) !== null) {
    const fn = match[1].toLowerCase();
    const nums = match[2]
      .trim()
      .split(/[\s,]+/)
      .filter(Boolean)
      .map(Number)
      .filter(n => Number.isFinite(n));
    let next: Matrix = IDENTITY;
    if (fn === 'matrix' && nums.length >= 6) {
      next = [nums[0], nums[1], nums[2], nums[3], nums[4], nums[5]];
    } else if (fn === 'translate' && nums.length >= 1) {
      next = [1, 0, 0, 1, nums[0], nums[1] ?? 0];
    } else if (fn === 'scale' && nums.length >= 1) {
      const sx = nums[0];
      const sy = nums[1] ?? sx;
      next = [sx, 0, 0, sy, 0, 0];
    } else if (fn === 'rotate' && nums.length >= 1) {
      const rad = (nums[0] * Math.PI) / 180;
      const cos = Math.cos(rad);
      const sin = Math.sin(rad);
      if (nums.length >= 3) {
        const cx = nums[1], cy = nums[2];
        next = mulMatrix([1, 0, 0, 1, cx, cy], mulMatrix([cos, sin, -sin, cos, 0, 0], [1, 0, 0, 1, -cx, -cy]));
      } else {
        next = [cos, sin, -sin, cos, 0, 0];
      }
    } else if (fn === 'skewx' && nums.length >= 1) {
      next = [1, 0, Math.tan((nums[0] * Math.PI) / 180), 1, 0, 0];
    } else if (fn === 'skewy' && nums.length >= 1) {
      next = [1, Math.tan((nums[0] * Math.PI) / 180), 0, 1, 0, 0];
    }
    m = mulMatrix(m, next);
  }
  return m;
}

// ── Lightweight XML/SVG DOM parser (works identically in Browser & Node) ────

interface SvgNode {
  tag: string;
  attrs: Record<string, string>;
  children: SvgNode[];
}

function parseAttributes(attrStr: string): Record<string, string> {
  const attrs: Record<string, string> = {};
  const re = /([a-zA-Z_:][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(attrStr)) !== null) {
    attrs[m[1].toLowerCase()] = m[2] ?? m[3] ?? '';
  }
  return attrs;
}

function parseSvgXml(svgText: string): SvgNode | null {
  // Strip XML declarations, DOCTYPE, comments, CDATA
  const cleaned = svgText
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<\?[\s\S]*?\?>/g, '')
    .replace(/<!DOCTYPE[\s\S]*?>/gi, '')
    .replace(/<!\[CDATA\[[\s\S]*?\]\]>/g, '');

  const stack: SvgNode[] = [];
  let root: SvgNode | null = null;
  const tagRe = /<(\/?)([a-zA-Z_:][\w:.-]*)([^>]*?)(\/?)>/g;
  let m: RegExpExecArray | null;

  while ((m = tagRe.exec(cleaned)) !== null) {
    const isClose = m[1] === '/';
    const rawTag = m[2].toLowerCase();
    const tag = rawTag.includes(':') ? rawTag.split(':').pop()! : rawTag;
    const attrStr = m[3];
    const isSelfClosing = m[4] === '/';

    if (isClose) {
      // Pop until matching tag
      for (let i = stack.length - 1; i >= 0; i--) {
        if (stack[i].tag === tag) {
          stack.length = i;
          break;
        }
      }
      continue;
    }

    const node: SvgNode = {
      tag,
      attrs: parseAttributes(attrStr),
      children: [],
    };

    if (stack.length > 0) {
      stack[stack.length - 1].children.push(node);
    }
    if (tag === 'svg' && !root) {
      root = node;
    }
    if (!isSelfClosing) {
      stack.push(node);
    }
  }

  return root;
}

function parseStyleMap(styleStr: string | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  if (!styleStr) return out;
  for (const part of styleStr.split(';')) {
    const idx = part.indexOf(':');
    if (idx === -1) continue;
    const k = part.slice(0, idx).trim().toLowerCase();
    const v = part.slice(idx + 1).trim();
    if (k) out[k] = v;
  }
  return out;
}

function parseLengthWithUnit(val: string | undefined): { value: number; unit: string } | null {
  if (!val) return null;
  const m = /^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)\s*([a-z%]*)\s*$/i.exec(val);
  if (!m) return null;
  const value = parseFloat(m[1]);
  if (!Number.isFinite(value) || value <= 0) return null;
  return { value, unit: (m[2] || 'px').toLowerCase() };
}

function toPhysicalUnit(value: number, unit: string): { value: number; unit: ScaleUnit } | null {
  switch (unit) {
    case 'mm': return { value, unit: 'mm' };
    case 'cm': return { value, unit: 'cm' };
    case 'in': return { value, unit: 'in' };
    case 'pt': return { value: value / 72, unit: 'in' };
    case 'pc': return { value: value / 6, unit: 'in' };
    default: return null;
  }
}

export function parseSvgDimensions(svgText: string): SvgDimensions {
  const root = parseSvgXml(svgText);
  if (!root) {
    return { viewBox: { x: 0, y: 0, width: 1000, height: 1000 }, physicalScale: null };
  }

  const wParsed = parseLengthWithUnit(root.attrs.width);
  const hParsed = parseLengthWithUnit(root.attrs.height);

  let vx = 0, vy = 0, vw = 0, vh = 0;
  if (root.attrs.viewbox) {
    const nums = root.attrs.viewbox
      .trim()
      .split(/[\s,]+/)
      .map(Number)
      .filter(Number.isFinite);
    if (nums.length >= 4 && nums[2] > 0 && nums[3] > 0) {
      [vx, vy, vw, vh] = nums;
    }
  }

  if (vw <= 0 || vh <= 0) {
    // Fallback to width/height attributes in user units (96dpi CSS px)
    const toPx = (p: { value: number; unit: string } | null) => {
      if (!p || p.unit === '%') return 0;
      if (p.unit === 'in') return p.value * 96;
      if (p.unit === 'cm') return (p.value * 96) / 2.54;
      if (p.unit === 'mm') return (p.value * 96) / 25.4;
      if (p.unit === 'pt') return (p.value * 96) / 72;
      if (p.unit === 'pc') return p.value * 16;
      return p.value;
    };
    vw = toPx(wParsed) || 1000;
    vh = toPx(hParsed) || 1000;
  }

  // Derive physical scale if root width/height carry real-world units (mm, cm, in, pt, pc)
  let physicalScale: { pxPerUnit: number; unit: ScaleUnit } | null = null;
  const wPhys = wParsed ? toPhysicalUnit(wParsed.value, wParsed.unit) : null;
  const hPhys = hParsed ? toPhysicalUnit(hParsed.value, hParsed.unit) : null;
  if (wPhys && wPhys.value > 0) {
    physicalScale = { pxPerUnit: vw / wPhys.value, unit: wPhys.unit };
  } else if (hPhys && hPhys.value > 0) {
    physicalScale = { pxPerUnit: vh / hPhys.value, unit: hPhys.unit };
  }

  return { viewBox: { x: vx, y: vy, width: vw, height: vh }, physicalScale };
}

// ── SVG Path Data Parser & Curve Conversion ─────────────────────────────────

interface QuadEdge {
  to: Pt;
  ctrl?: Pt; // quadratic bezier control point; undefined = straight line
}

interface RawSubpath {
  start: Pt;
  edges: QuadEdge[];
  closed: boolean;
}

/**
 * Split a cubic Bézier (p0, c1, c2, p3) into 2 quadratic Béziers.
 * Subdividing at t=0.5 keeps error negligible for stained-glass curves while
 * staying native to Vitrai's quadratic CurvePoint representation.
 */
function cubicToQuads(p0: Pt, c1: Pt, c2: Pt, p3: Pt): QuadEdge[] {
  // De Casteljau split at t = 0.5
  const m01: Pt = [(p0[0] + c1[0]) / 2, (p0[1] + c1[1]) / 2];
  const m12: Pt = [(c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2];
  const m23: Pt = [(c2[0] + p3[0]) / 2, (c2[1] + p3[1]) / 2];
  const m012: Pt = [(m01[0] + m12[0]) / 2, (m01[1] + m12[1]) / 2];
  const m123: Pt = [(m12[0] + m23[0]) / 2, (m12[1] + m23[1]) / 2];
  const mid: Pt = [(m012[0] + m123[0]) / 2, (m012[1] + m123[1]) / 2];

  // Best-fit quadratic control point for each half-cubic (a, b, c, d):
  // Q = (3b + 3c - a - d) / 4
  const q1: Pt = [
    (3 * m01[0] + 3 * m012[0] - p0[0] - mid[0]) / 4,
    (3 * m01[1] + 3 * m012[1] - p0[1] - mid[1]) / 4,
  ];
  const q2: Pt = [
    (3 * m123[0] + 3 * m23[0] - mid[0] - p3[0]) / 4,
    (3 * m123[1] + 3 * m23[1] - mid[1] - p3[1]) / 4,
  ];

  return [
    { to: mid, ctrl: q1 },
    { to: p3, ctrl: q2 },
  ];
}

/**
 * Convert an SVG elliptical arc command into quadratic Bézier segments.
 * Implements SVG 1.1 F.6.5/F.6.6 endpoint-to-center parameterization.
 */
function arcToQuads(
  x1: number, y1: number,
  rxIn: number, ryIn: number,
  xAxisRotationDeg: number,
  largeArcFlag: number,
  sweepFlag: number,
  x2: number, y2: number,
): QuadEdge[] {
  if (Math.hypot(x2 - x1, y2 - y1) < 1e-6) return [];
  let rx = Math.abs(rxIn);
  let ry = Math.abs(ryIn);
  if (rx < 1e-6 || ry < 1e-6) return [{ to: [x2, y2] }];

  const phi = (xAxisRotationDeg * Math.PI) / 180;
  const cosPhi = Math.cos(phi);
  const sinPhi = Math.sin(phi);

  const dx2 = (x1 - x2) / 2;
  const dy2 = (y1 - y2) / 2;
  const x1p = cosPhi * dx2 + sinPhi * dy2;
  const y1p = -sinPhi * dx2 + cosPhi * dy2;

  const lambda = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry);
  if (lambda > 1) {
    const scale = Math.sqrt(lambda);
    rx *= scale;
    ry *= scale;
  }

  const rx2 = rx * rx;
  const ry2 = ry * ry;
  const x1p2 = x1p * x1p;
  const y1p2 = y1p * y1p;
  const num = Math.max(0, rx2 * ry2 - rx2 * y1p2 - ry2 * x1p2);
  const den = rx2 * y1p2 + ry2 * x1p2;
  const sign = largeArcFlag === sweepFlag ? -1 : 1;
  const coef = den > 1e-12 ? sign * Math.sqrt(num / den) : 0;

  const cxp = (coef * rx * y1p) / ry;
  const cyp = (-coef * ry * x1p) / rx;

  const cx = cosPhi * cxp - sinPhi * cyp + (x1 + x2) / 2;
  const cy = sinPhi * cxp + cosPhi * cyp + (y1 + y2) / 2;

  const angleBetween = (ux: number, uy: number, vx: number, vy: number) => {
    const dot = ux * vx + uy * vy;
    const len = Math.hypot(ux, uy) * Math.hypot(vx, vy);
    const ratio = len > 1e-12 ? Math.max(-1, Math.min(1, dot / len)) : 1;
    const ang = Math.acos(ratio);
    return ux * vy - uy * vx < 0 ? -ang : ang;
  };

  const theta1 = angleBetween(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry);
  let dTheta = angleBetween(
    (x1p - cxp) / rx, (y1p - cyp) / ry,
    (-x1p - cxp) / rx, (-y1p - cyp) / ry,
  );
  if (sweepFlag === 0 && dTheta > 0) dTheta -= 2 * Math.PI;
  if (sweepFlag === 1 && dTheta < 0) dTheta += 2 * Math.PI;

  // Split arc into <= 45-degree segments so each quadratic Bezier is accurate
  const segCount = Math.max(1, Math.ceil(Math.abs(dTheta) / (Math.PI / 4)));
  const step = dTheta / segCount;
  const edges: QuadEdge[] = [];

  const evalEllipse = (theta: number): Pt => {
    const ex = rx * Math.cos(theta);
    const ey = ry * Math.sin(theta);
    return [cx + cosPhi * ex - sinPhi * ey, cy + sinPhi * ex + cosPhi * ey];
  };

  for (let i = 0; i < segCount; i++) {
    const t1 = theta1 + i * step;
    const t2 = theta1 + (i + 1) * step;
    const tMid = (t1 + t2) / 2;
    const endPt = i === segCount - 1 ? ([x2, y2] as Pt) : evalEllipse(t2);
    // Tangent intersection on unit circle for angle step is at radius 1/cos(step/2)
    const sec = 1 / Math.cos(step / 2);
    const cxLocal = rx * sec * Math.cos(tMid);
    const cyLocal = ry * sec * Math.sin(tMid);
    const ctrl: Pt = [
      cx + cosPhi * cxLocal - sinPhi * cyLocal,
      cy + sinPhi * cxLocal + cosPhi * cyLocal,
    ];
    edges.push({ to: endPt, ctrl });
  }

  return edges;
}

const PATH_TOKEN_RE = /([a-zA-Z])|([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)/g;

export function parsePathData(d: string): RawSubpath[] {
  const tokens: string[] = [];
  let m: RegExpExecArray | null;
  PATH_TOKEN_RE.lastIndex = 0;
  while ((m = PATH_TOKEN_RE.exec(d)) !== null) {
    tokens.push(m[0]);
  }

  const subpaths: RawSubpath[] = [];
  let current: RawSubpath | null = null;
  let cx = 0, cy = 0;
  let sx = 0, sy = 0;
  let lastCmd = '';
  let lastCubicCtrl: Pt | null = null;
  let lastQuadCtrl: Pt | null = null;

  let i = 0;
  let cmd = '';

  const nextNum = () => parseFloat(tokens[i++]);
  const hasNum = () => i < tokens.length && !/^[a-zA-Z]$/.test(tokens[i]);

  while (i < tokens.length) {
    if (/^[a-zA-Z]$/.test(tokens[i])) {
      cmd = tokens[i++];
    } else if (!cmd) {
      i++;
      continue;
    }

    const isRel = cmd === cmd.toLowerCase();
    const upper = cmd.toUpperCase();

    if (upper === 'Z') {
      if (current) {
        current.closed = true;
        if (Math.hypot(cx - sx, cy - sy) > 1e-4) {
          current.edges.push({ to: [sx, sy] });
        }
        cx = sx;
        cy = sy;
      }
      lastCubicCtrl = null;
      lastQuadCtrl = null;
      lastCmd = upper;
      cmd = '';
      continue;
    }

    if (upper === 'M') {
      if (!hasNum()) break;
      const x = nextNum() + (isRel ? cx : 0);
      const y = nextNum() + (isRel ? cy : 0);
      cx = x; cy = y; sx = x; sy = y;
      current = { start: [x, y], edges: [], closed: false };
      subpaths.push(current);
      lastCubicCtrl = null;
      lastQuadCtrl = null;
      lastCmd = upper;
      // Subsequent coordinate pairs after M/m are treated as implicit L/l
      cmd = isRel ? 'l' : 'L';
      continue;
    }

    if (!current) {
      current = { start: [cx, cy], edges: [], closed: false };
      subpaths.push(current);
    }

    if (upper === 'L') {
      if (!hasNum()) break;
      const x = nextNum() + (isRel ? cx : 0);
      const y = nextNum() + (isRel ? cy : 0);
      current.edges.push({ to: [x, y] });
      cx = x; cy = y;
      lastCubicCtrl = null;
      lastQuadCtrl = null;
    } else if (upper === 'H') {
      if (!hasNum()) break;
      const x = nextNum() + (isRel ? cx : 0);
      current.edges.push({ to: [x, cy] });
      cx = x;
      lastCubicCtrl = null;
      lastQuadCtrl = null;
    } else if (upper === 'V') {
      if (!hasNum()) break;
      const y = nextNum() + (isRel ? cy : 0);
      current.edges.push({ to: [cx, y] });
      cy = y;
      lastCubicCtrl = null;
      lastQuadCtrl = null;
    } else if (upper === 'Q') {
      if (!hasNum()) break;
      const qx = nextNum() + (isRel ? cx : 0);
      const qy = nextNum() + (isRel ? cy : 0);
      const x = nextNum() + (isRel ? cx : 0);
      const y = nextNum() + (isRel ? cy : 0);
      current.edges.push({ to: [x, y], ctrl: [qx, qy] });
      lastQuadCtrl = [qx, qy];
      lastCubicCtrl = null;
      cx = x; cy = y;
    } else if (upper === 'T') {
      if (!hasNum()) break;
      const qx: number = (lastCmd === 'Q' || lastCmd === 'T') && lastQuadCtrl ? 2 * cx - lastQuadCtrl[0] : cx;
      const qy: number = (lastCmd === 'Q' || lastCmd === 'T') && lastQuadCtrl ? 2 * cy - lastQuadCtrl[1] : cy;
      const x = nextNum() + (isRel ? cx : 0);
      const y = nextNum() + (isRel ? cy : 0);
      current.edges.push({ to: [x, y], ctrl: [qx, qy] });
      lastQuadCtrl = [qx, qy];
      lastCubicCtrl = null;
      cx = x; cy = y;
    } else if (upper === 'C') {
      if (!hasNum()) break;
      const c1x = nextNum() + (isRel ? cx : 0);
      const c1y = nextNum() + (isRel ? cy : 0);
      const c2x = nextNum() + (isRel ? cx : 0);
      const c2y = nextNum() + (isRel ? cy : 0);
      const x = nextNum() + (isRel ? cx : 0);
      const y = nextNum() + (isRel ? cy : 0);
      current.edges.push(...cubicToQuads([cx, cy], [c1x, c1y], [c2x, c2y], [x, y]));
      lastCubicCtrl = [c2x, c2y];
      lastQuadCtrl = null;
      cx = x; cy = y;
    } else if (upper === 'S') {
      if (!hasNum()) break;
      const c1x: number = (lastCmd === 'C' || lastCmd === 'S') && lastCubicCtrl ? 2 * cx - lastCubicCtrl[0] : cx;
      const c1y: number = (lastCmd === 'C' || lastCmd === 'S') && lastCubicCtrl ? 2 * cy - lastCubicCtrl[1] : cy;
      const c2x = nextNum() + (isRel ? cx : 0);
      const c2y = nextNum() + (isRel ? cy : 0);
      const x = nextNum() + (isRel ? cx : 0);
      const y = nextNum() + (isRel ? cy : 0);
      current.edges.push(...cubicToQuads([cx, cy], [c1x, c1y], [c2x, c2y], [x, y]));
      lastCubicCtrl = [c2x, c2y];
      lastQuadCtrl = null;
      cx = x; cy = y;
    } else if (upper === 'A') {
      if (!hasNum()) break;
      const rx = nextNum();
      const ry = nextNum();
      const rot = nextNum();
      const largeArc = nextNum();
      const sweep = nextNum();
      const x = nextNum() + (isRel ? cx : 0);
      const y = nextNum() + (isRel ? cy : 0);
      current.edges.push(...arcToQuads(cx, cy, rx, ry, rot, largeArc, sweep, x, y));
      lastCubicCtrl = null;
      lastQuadCtrl = null;
      cx = x; cy = y;
    } else {
      break;
    }

    lastCmd = upper;
  }

  return subpaths;
}

function ellipseSubpath(cx: number, cy: number, rx: number, ry: number): RawSubpath {
  // 8 quadratic Bezier segments around the ellipse for high accuracy
  const n = 8;
  const step = (2 * Math.PI) / n;
  const sec = 1 / Math.cos(step / 2);
  const start: Pt = [cx + rx, cy];
  const edges: QuadEdge[] = [];
  for (let i = 0; i < n; i++) {
    const t2 = (i + 1) * step;
    const tMid = (i + 0.5) * step;
    const to: Pt = i === n - 1 ? start : [cx + rx * Math.cos(t2), cy + ry * Math.sin(t2)];
    const ctrl: Pt = [cx + rx * sec * Math.cos(tMid), cy + ry * sec * Math.sin(tMid)];
    edges.push({ to, ctrl });
  }
  return { start, edges, closed: true };
}

function rectSubpath(x: number, y: number, w: number, h: number, rxIn: number, ryIn: number): RawSubpath {
  const rx = Math.min(Math.max(0, rxIn), w / 2);
  const ry = Math.min(Math.max(0, ryIn), h / 2);
  if (rx < 1e-4 && ry < 1e-4) {
    return {
      start: [x, y],
      edges: [
        { to: [x + w, y] },
        { to: [x + w, y + h] },
        { to: [x, y + h] },
        { to: [x, y] },
      ],
      closed: true,
    };
  }
  const start: Pt = [x + rx, y];
  const edges: QuadEdge[] = [
    { to: [x + w - rx, y] },
    { to: [x + w, y + ry], ctrl: [x + w, y] },
    { to: [x + w, y + h - ry] },
    { to: [x + w - rx, y + h], ctrl: [x + w, y + h] },
    { to: [x + rx, y + h] },
    { to: [x, y + h - ry], ctrl: [x, y + h] },
    { to: [x, y + ry] },
    { to: [x + rx, y], ctrl: [x, y] },
  ];
  return { start, edges, closed: true };
}

function parsePointsAttr(str: string | undefined): Pt[] {
  if (!str) return [];
  const nums = str.trim().split(/[\s,]+/).filter(Boolean).map(Number).filter(Number.isFinite);
  const pts: Pt[] = [];
  for (let i = 0; i + 1 < nums.length; i += 2) {
    pts.push([nums[i], nums[i + 1]]);
  }
  return pts;
}

// ── Element Extraction & Classification ─────────────────────────────────────

interface ExtractedElementSubpath {
  subpath: RawSubpath;
  matrix: Matrix;
  hasFill: boolean;
  fillColor: string;
  hasStroke: boolean;
  elementId: number;
  label?: string;
}

interface InheritedStyle {
  fill: string;
  stroke: string;
  fillOpacity: number;
  opacity: number;
}

const DEFAULT_STYLE: InheritedStyle = {
  fill: '#000000', // SVG default fill is black
  stroke: 'none',
  fillOpacity: 1,
  opacity: 1,
};

function resolveStyle(node: SvgNode, parent: InheritedStyle): InheritedStyle {
  const inline = parseStyleMap(node.attrs.style);
  const fill = inline.fill ?? node.attrs.fill ?? parent.fill;
  const stroke = inline.stroke ?? node.attrs.stroke ?? parent.stroke;
  const fillOpacityRaw = inline['fill-opacity'] ?? node.attrs['fill-opacity'];
  const opacityRaw = inline.opacity ?? node.attrs.opacity;
  const fillOpacity = fillOpacityRaw !== undefined ? parseFloat(fillOpacityRaw) : parent.fillOpacity;
  const opacity = opacityRaw !== undefined ? parseFloat(opacityRaw) : parent.opacity;
  return {
    fill: fill.trim().toLowerCase(),
    stroke: stroke.trim().toLowerCase(),
    fillOpacity: Number.isFinite(fillOpacity) ? fillOpacity : parent.fillOpacity,
    opacity: Number.isFinite(opacity) ? opacity : parent.opacity,
  };
}

function isVisiblePaint(paint: string, opacity: number): boolean {
  if (opacity <= 0.01) return false;
  if (!paint || paint === 'none' || paint === 'transparent') return false;
  return true;
}

function isNearWhite(fill: string): boolean {
  const f = fill.replace(/\s+/g, '').toLowerCase();
  return f === '#fff' || f === '#ffffff' || f === 'white' || f === 'rgb(255,255,255)';
}

function subpathLength(sp: RawSubpath, m: Matrix): number {
  let len = 0;
  let prev = applyMatrix(m, sp.start[0], sp.start[1]);
  for (const e of sp.edges) {
    const cur = applyMatrix(m, e.to[0], e.to[1]);
    if (e.ctrl) {
      const c = applyMatrix(m, e.ctrl[0], e.ctrl[1]);
      // Approximate quadratic length by chord + control polygon average
      const chord = Math.hypot(cur[0] - prev[0], cur[1] - prev[1]);
      const poly = Math.hypot(c[0] - prev[0], c[1] - prev[1]) + Math.hypot(cur[0] - c[0], cur[1] - c[1]);
      len += (chord + poly) / 2;
    } else {
      len += Math.hypot(cur[0] - prev[0], cur[1] - prev[1]);
    }
    prev = cur;
  }
  return len;
}

function polygonSignedArea(poly: Pt[]): number {
  let a = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % poly.length];
    a += x1 * y2 - x2 * y1;
  }
  return a / 2;
}

function polygonPerimeter(poly: Pt[]): number {
  let p = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % poly.length];
    p += Math.hypot(x2 - x1, y2 - y1);
  }
  return p;
}

function pointInPolygon(pt: Pt, poly: Pt[]): boolean {
  let inside = false;
  const [px, py] = pt;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi + 1e-12) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

function subpathToPiece(
  sp: RawSubpath,
  matrix: Matrix,
  label?: string,
): { piece: SvgImportedPiece; flat: Pt[]; area: number; perimeter: number } | null {
  const polygon: Pt[] = [];
  const curvePoints: CurvePoint[] = [];

  let prev = applyMatrix(matrix, sp.start[0], sp.start[1]);
  polygon.push(prev);

  for (let i = 0; i < sp.edges.length; i++) {
    const edge = sp.edges[i];
    const to = applyMatrix(matrix, edge.to[0], edge.to[1]);
    const isLast = i === sp.edges.length - 1;
    const closesToStart = isLast && Math.hypot(to[0] - polygon[0][0], to[1] - polygon[0][1]) < 0.5;

    // Skip zero-length duplicate edges
    if (Math.hypot(to[0] - prev[0], to[1] - prev[1]) < 0.25) {
      continue;
    }

    const edgeIdx = polygon.length - 1;
    if (edge.ctrl) {
      const ctrl = applyMatrix(matrix, edge.ctrl[0], edge.ctrl[1]);
      // Only store curvePoint if control point deviates meaningfully from the straight chord
      const midX = (prev[0] + to[0]) / 2;
      const midY = (prev[1] + to[1]) / 2;
      if (Math.hypot(ctrl[0] - midX, ctrl[1] - midY) > 0.35) {
        curvePoints.push({ edgeIdx, ctrl });
      }
    }

    if (!closesToStart) {
      polygon.push(to);
    }
    prev = to;
  }

  if (polygon.length < 3) return null;

  const flat = flattenCurves(polygon, curvePoints.length > 0 ? curvePoints : undefined);
  const area = Math.abs(polygonSignedArea(flat));
  if (area < 4) return null;

  const perimeter = polygonPerimeter(flat);
  return {
    piece: {
      polygon,
      ...(curvePoints.length > 0 ? { curvePoints } : {}),
      ...(label ? { label } : {}),
    },
    flat,
    area,
    perimeter,
  };
}

export function classifySvgMode(stats: SvgAnalysisStats): SvgImportMode {
  if (stats.closedCount < 2) return 'lines';
  if (stats.openLengthRatio > 0.1) return 'lines';
  if (stats.isLeadWeb) return 'lines';
  if (!stats.anyHasFill && stats.overlapRatio > 1.15) return 'lines';
  return 'shapes';
}

const DEFAULT_SVG_MAX_DIM = 1200;

export function parseSvgVectors(
  svgText: string,
  target?: SvgCanvasTarget,
): SvgVectorParseResult {
  const dimensions = parseSvgDimensions(svgText);
  const { viewBox, physicalScale } = dimensions;

  // Determine canvas dimensions and viewBox -> canvas transform
  let canvasWidth: number;
  let canvasHeight: number;
  let vbScale: number;
  let offsetX: number;
  let offsetY: number;

  if (target?.fitBox) {
    canvasWidth = target.width;
    canvasHeight = target.height;
    const { x, y, width, height } = target.fitBox;
    vbScale = Math.min(width / viewBox.width, height / viewBox.height);
    offsetX = x + (width - viewBox.width * vbScale) / 2 - viewBox.x * vbScale;
    offsetY = y + (height - viewBox.height * vbScale) / 2 - viewBox.y * vbScale;
  } else if (target) {
    canvasWidth = target.width;
    canvasHeight = target.height;
    vbScale = Math.min(canvasWidth / viewBox.width, canvasHeight / viewBox.height);
    offsetX = (canvasWidth - viewBox.width * vbScale) / 2 - viewBox.x * vbScale;
    offsetY = (canvasHeight - viewBox.height * vbScale) / 2 - viewBox.y * vbScale;
  } else {
    const longest = Math.max(viewBox.width, viewBox.height);
    vbScale = DEFAULT_SVG_MAX_DIM / longest;
    canvasWidth = Math.max(1, Math.round(viewBox.width * vbScale));
    canvasHeight = Math.max(1, Math.round(viewBox.height * vbScale));
    offsetX = -viewBox.x * vbScale;
    offsetY = -viewBox.y * vbScale;
  }

  const rootMatrix: Matrix = [vbScale, 0, 0, vbScale, offsetX, offsetY];

  const scale: Scale = physicalScale
    ? {
        pxPerUnit: physicalScale.pxPerUnit * vbScale,
        unit: physicalScale.unit,
        line: { x1: 0, y1: canvasHeight / 2, x2: canvasWidth, y2: canvasHeight / 2 },
      }
    : {
        pxPerUnit: 100,
        unit: 'in',
        line: { x1: 0, y1: canvasHeight / 2, x2: canvasWidth, y2: canvasHeight / 2 },
      };

  const root = parseSvgXml(svgText);
  const extracted: ExtractedElementSubpath[] = [];
  let nextElementId = 1;

  const SKIP_TAGS = new Set(['defs', 'clippath', 'mask', 'pattern', 'symbol', 'marker', 'filter', 'lineargradient', 'radialgradient', 'title', 'desc', 'metadata', 'style']);

  function walk(node: SvgNode, parentMatrix: Matrix, parentStyle: InheritedStyle) {
    if (SKIP_TAGS.has(node.tag)) return;
    const inline = parseStyleMap(node.attrs.style);
    if (inline.display === 'none' || node.attrs.display === 'none') return;
    if (inline.visibility === 'hidden' || node.attrs.visibility === 'hidden') return;

    const matrix = mulMatrix(parentMatrix, parseTransform(node.attrs.transform));
    const style = resolveStyle(node, parentStyle);
    const hasFill = isVisiblePaint(style.fill, style.fillOpacity * style.opacity);
    const hasStroke = isVisiblePaint(style.stroke, style.opacity);
    const label = node.attrs['data-label'] || node.attrs.id || undefined;
    const elementId = nextElementId++;

    let subpaths: RawSubpath[] = [];

    if (node.tag === 'path' && node.attrs.d) {
      subpaths = parsePathData(node.attrs.d);
    } else if (node.tag === 'rect') {
      const x = parseFloat(node.attrs.x ?? '0') || 0;
      const y = parseFloat(node.attrs.y ?? '0') || 0;
      const w = parseFloat(node.attrs.width ?? '0') || 0;
      const h = parseFloat(node.attrs.height ?? '0') || 0;
      const rx = parseFloat(node.attrs.rx ?? node.attrs.ry ?? '0') || 0;
      const ry = parseFloat(node.attrs.ry ?? node.attrs.rx ?? '0') || 0;
      if (w > 0 && h > 0) subpaths = [rectSubpath(x, y, w, h, rx, ry)];
    } else if (node.tag === 'circle') {
      const cx = parseFloat(node.attrs.cx ?? '0') || 0;
      const cy = parseFloat(node.attrs.cy ?? '0') || 0;
      const r = parseFloat(node.attrs.r ?? '0') || 0;
      if (r > 0) subpaths = [ellipseSubpath(cx, cy, r, r)];
    } else if (node.tag === 'ellipse') {
      const cx = parseFloat(node.attrs.cx ?? '0') || 0;
      const cy = parseFloat(node.attrs.cy ?? '0') || 0;
      const rx = parseFloat(node.attrs.rx ?? '0') || 0;
      const ry = parseFloat(node.attrs.ry ?? '0') || 0;
      if (rx > 0 && ry > 0) subpaths = [ellipseSubpath(cx, cy, rx, ry)];
    } else if (node.tag === 'polygon' || node.tag === 'polyline') {
      const pts = parsePointsAttr(node.attrs.points);
      if (pts.length >= 2) {
        const closed = node.tag === 'polygon';
        const edges: QuadEdge[] = pts.slice(1).map(p => ({ to: p }));
        if (closed) edges.push({ to: pts[0] });
        subpaths = [{ start: pts[0], edges, closed }];
      }
    } else if (node.tag === 'line') {
      const x1 = parseFloat(node.attrs.x1 ?? '0') || 0;
      const y1 = parseFloat(node.attrs.y1 ?? '0') || 0;
      const x2 = parseFloat(node.attrs.x2 ?? '0') || 0;
      const y2 = parseFloat(node.attrs.y2 ?? '0') || 0;
      subpaths = [{ start: [x1, y1], edges: [{ to: [x2, y2] }], closed: false }];
    }

    for (const sp of subpaths) {
      if (sp.edges.length === 0) continue;
      // Treat a subpath whose end meets its start as closed even without explicit Z
      const lastPt = sp.edges[sp.edges.length - 1].to;
      const endStartDist = Math.hypot(
        applyMatrix(matrix, lastPt[0], lastPt[1])[0] - applyMatrix(matrix, sp.start[0], sp.start[1])[0],
        applyMatrix(matrix, lastPt[0], lastPt[1])[1] - applyMatrix(matrix, sp.start[0], sp.start[1])[1],
      );
      const isClosed = sp.closed || (sp.edges.length >= 2 && endStartDist < 1.5);
      extracted.push({
        subpath: { ...sp, closed: isClosed },
        matrix,
        hasFill,
        fillColor: style.fill,
        hasStroke,
        elementId,
        label,
      });
    }

    for (const child of node.children) {
      walk(child, matrix, style);
    }
  }

  if (root) {
    walk(root, rootMatrix, DEFAULT_STYLE);
  }

  // Separate closed vs open, and filter out full-canvas white background rects
  const canvasArea = canvasWidth * canvasHeight;
  let openCount = 0;
  let openLen = 0;
  let closedLen = 0;
  let anyHasFill = false;

  interface ClosedCandidate {
    piece: SvgImportedPiece;
    flat: Pt[];
    area: number;
    perimeter: number;
    hasFill: boolean;
    elementId: number;
  }

  const closedCandidates: ClosedCandidate[] = [];

  for (const item of extracted) {
    const len = subpathLength(item.subpath, item.matrix);
    if (!item.subpath.closed) {
      openCount++;
      openLen += len;
      continue;
    }

    const built = subpathToPiece(item.subpath, item.matrix, item.label);
    if (!built) continue;

    // Ignore full-canvas white/background rects
    if (built.area > canvasArea * 0.92 && item.hasFill && isNearWhite(item.fillColor) && !item.hasStroke) {
      continue;
    }

    closedLen += len;
    if (item.hasFill) anyHasFill = true;
    closedCandidates.push({
      ...built,
      hasFill: item.hasFill,
      elementId: item.elementId,
    });
  }

  // Detect expanded-stroke lead web:
  // (a) Single filled element with >= 3 subpaths where smaller subpaths sit inside a larger subpath (holes)
  // (b) Very thin ribbon shapes (low area / perimeter^2 or high perimeter relative to area)
  let isLeadWeb = false;
  const byElement = new Map<number, ClosedCandidate[]>();
  for (const c of closedCandidates) {
    const list = byElement.get(c.elementId) ?? [];
    list.push(c);
    byElement.set(c.elementId, list);
  }
  if (byElement.size === 1 && closedCandidates.length >= 3) {
    const onlyGroup = [...byElement.values()][0];
    const sorted = [...onlyGroup].sort((a, b) => b.area - a.area);
    const outer = sorted[0];
    let holesInsideOuter = 0;
    for (let i = 1; i < sorted.length; i++) {
      if (pointInPolygon(sorted[i].flat[0], outer.flat)) {
        holesInsideOuter++;
      }
    }
    if (holesInsideOuter >= 2 && outer.hasFill) {
      isLeadWeb = true;
    }
  }

  // Compute overlapRatio = sum(areas) / union(areas) using polygon-clipping
  let overlapRatio = 1;
  if (closedCandidates.length >= 2 && !isLeadWeb) {
    const sumArea = closedCandidates.reduce((s, c) => s + c.area, 0);
    try {
      const rings = closedCandidates.map(c => [c.flat] as polygonClipping.Polygon);
      const union = polygonClipping.union(rings[0], ...rings.slice(1));
      let unionArea = 0;
      for (const poly of union) {
        if (poly.length === 0) continue;
        unionArea += Math.abs(polygonSignedArea(poly[0] as Pt[]));
        for (let h = 1; h < poly.length; h++) {
          unionArea -= Math.abs(polygonSignedArea(poly[h] as Pt[]));
        }
      }
      if (unionArea > 1) {
        overlapRatio = sumArea / unionArea;
      }
    } catch {
      overlapRatio = 1;
    }
  }

  const totalLen = openLen + closedLen;
  const stats: SvgAnalysisStats = {
    closedCount: closedCandidates.length,
    openCount,
    openLengthRatio: totalLen > 0 ? openLen / totalLen : 0,
    anyHasFill,
    overlapRatio,
    isLeadWeb,
  };

  const recommendedMode = classifySvgMode(stats);

  return {
    dimensions,
    canvasWidth,
    canvasHeight,
    scale,
    pieces: closedCandidates.map(c => c.piece),
    stats,
    recommendedMode,
  };
}

// ── Pure Mask Watershed & Topology-Preserving Crack-Edge Tracer (Case 2) ────

function rdpSimplifyOpen(pts: Pt[], epsilon: number): Pt[] {
  if (pts.length <= 2) return pts;
  const eps2 = epsilon * epsilon;
  const out: Pt[] = [pts[0]];

  function recurse(start: number, end: number) {
    let maxD2 = -1;
    let maxIdx = start;
    const [ax, ay] = pts[start];
    const [bx, by] = pts[end];
    const dx = bx - ax;
    const dy = by - ay;
    const len2 = dx * dx + dy * dy;

    for (let i = start + 1; i < end; i++) {
      const [px, py] = pts[i];
      let d2: number;
      if (len2 < 1e-9) {
        d2 = (px - ax) * (px - ax) + (py - ay) * (py - ay);
      } else {
        const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
        const cx = ax + t * dx;
        const cy = ay + t * dy;
        d2 = (px - cx) * (px - cx) + (py - cy) * (py - cy);
      }
      if (d2 > maxD2) {
        maxD2 = d2;
        maxIdx = i;
      }
    }

    if (maxD2 > eps2 && maxIdx !== start && maxIdx !== end) {
      recurse(start, maxIdx);
      out.push(pts[maxIdx]);
      recurse(maxIdx, end);
    }
  }

  recurse(0, pts.length - 1);
  out.push(pts[pts.length - 1]);
  return out;
}

function rdpSimplifyClosed(pts: Pt[], epsilon: number): Pt[] {
  if (pts.length <= 3) return pts;
  let farIdx = 1;
  let farD2 = -1;
  for (let i = 1; i < pts.length; i++) {
    const d2 = (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2;
    if (d2 > farD2) {
      farD2 = d2;
      farIdx = i;
    }
  }
  const first = rdpSimplifyOpen(pts.slice(0, farIdx + 1), epsilon);
  const second = rdpSimplifyOpen([...pts.slice(farIdx), pts[0]], epsilon);
  return [...first.slice(0, -1), ...second.slice(0, -1)];
}

/**
 * Expand all labeled regions (`labels >= 1`) into wall pixels (`labels === -1`)
 * using a Chamfer 10/14 (Euclidean-approximated) multi-source Dijkstra watershed.
 * Adjacent pieces meet along the exact stroke centerline regardless of SVG stroke width.
 */
function expandRegionsToCenterline(labels: Int32Array, w: number, h: number): void {
  const total = w * h;
  const dist = new Int32Array(total);
  dist.fill(0x3fffffff);

  // 16-slot ring buffer of buckets suffices since max step cost is 14
  const buckets: number[][] = Array.from({ length: 16 }, () => []);
  let queued = 0;

  // Seed non-wall pixels that touch at least one wall pixel
  for (let y = 0; y < h; y++) {
    const row = y * w;
    for (let x = 0; x < w; x++) {
      const idx = row + x;
      if (labels[idx] < 1) continue;
      const touchesWall =
        (x > 0 && labels[idx - 1] === -1) ||
        (x + 1 < w && labels[idx + 1] === -1) ||
        (y > 0 && labels[idx - w] === -1) ||
        (y + 1 < h && labels[idx + w] === -1);
      if (touchesWall) {
        dist[idx] = 0;
        buckets[0].push(idx);
        queued++;
      }
    }
  }

  const nxOff = [-1, 1, 0, 0, -1, 1, -1, 1];
  const nyOff = [0, 0, -1, 1, -1, -1, 1, 1];
  const stepCost = [10, 10, 10, 10, 14, 14, 14, 14];

  let curDist = 0;
  while (queued > 0) {
    const bucket = buckets[curDist & 15];
    if (bucket.length === 0) {
      curDist++;
      continue;
    }
    const idx = bucket.pop()!;
    queued--;
    if (dist[idx] !== curDist) continue;

    const lab = labels[idx];
    const x = idx % w;
    const y = (idx - x) / w;

    for (let k = 0; k < 8; k++) {
      const nx = x + nxOff[k];
      const ny = y + nyOff[k];
      if (nx < 0 || nx >= w || ny < 0 || ny >= h) continue;
      const nIdx = ny * w + nx;
      // Only expand into pixels that were originally walls (dist > 0)
      if (dist[nIdx] === 0) continue;
      const nd = curDist + stepCost[k];
      if (nd < dist[nIdx]) {
        dist[nIdx] = nd;
        labels[nIdx] = lab;
        buckets[nd & 15].push(nIdx);
        queued++;
      }
    }
  }
}

/**
 * Trace the clockwise outer inter-pixel crack boundary of `targetLabel` on the `(w+1) x (h+1)`
 * grid, starting from the top edge of its topmost-leftmost pixel `(startX, startY)`.
 * Returns grid-integer vertices so adjacent regions share exact coordinates.
 */
function traceCrackBoundary(
  labels: Int32Array,
  w: number,
  h: number,
  targetLabel: number,
  startX: number,
  startY: number,
): Pt[] {
  const isIn = (x: number, y: number) =>
    x >= 0 && x < w && y >= 0 && y < h && labels[y * w + x] === targetLabel;

  // Directions: 0=East(+1,0), 1=South(0,+1), 2=West(-1,0), 3=North(0,-1)
  const dx = [1, 0, -1, 0];
  const dy = [0, 1, 0, -1];
  // Pixel to the RIGHT (inside) and LEFT (outside) of a directed edge starting at (vx, vy)
  const rightPx = (vx: number, vy: number, dir: number): [number, number] => {
    if (dir === 0) return [vx, vy];         // East: pixel below-right
    if (dir === 1) return [vx - 1, vy];     // South: pixel below-left
    if (dir === 2) return [vx - 1, vy - 1]; // West: pixel above-left
    return [vx, vy - 1];                    // North: pixel above-right
  };
  const leftPx = (vx: number, vy: number, dir: number): [number, number] => {
    if (dir === 0) return [vx, vy - 1];
    if (dir === 1) return [vx, vy];
    if (dir === 2) return [vx - 1, vy];
    return [vx - 1, vy - 1];
  };

  const boundary: Pt[] = [];
  let vx = startX;
  let vy = startY;
  let dir = 0; // top edge of (startX, startY) goes East
  const maxSteps = (w + 1) * (h + 1) * 4;

  for (let step = 0; step < maxSteps; step++) {
    boundary.push([vx, vy]);
    vx += dx[dir];
    vy += dy[dir];
    if (vx === startX && vy === startY) break;

    // Prefer turning left (keeping outer perimeter tight), then straight, then right
    const candidates = [(dir + 3) & 3, dir, (dir + 1) & 3];
    let nextDir = dir;
    for (const c of candidates) {
      const [rx, ry] = rightPx(vx, vy, c);
      const [lx, ly] = leftPx(vx, vy, c);
      if (isIn(rx, ry) && !isIn(lx, ly)) {
        nextDir = c;
        break;
      }
    }
    dir = nextDir;
  }

  return boundary;
}

function isJunctionVertex(labels: Int32Array, w: number, h: number, gx: number, gy: number): boolean {
  const get = (x: number, y: number) => (x < 0 || x >= w || y < 0 || y >= h ? 1 : labels[y * w + x]);
  const a = get(gx - 1, gy - 1);
  const b = get(gx, gy - 1);
  const c = get(gx - 1, gy);
  const d = get(gx, gy);
  // Count distinct labels among the 4 pixels meeting at (gx, gy)
  let distinct = 1;
  if (b !== a) distinct++;
  if (c !== a && c !== b) distinct++;
  if (d !== a && d !== b && d !== c) distinct++;
  return distinct >= 3;
}

/**
 * Given a binary wall mask (`1` = dark line/wall, `0` = open region),
 * flood-fills the exterior and interior regions, expands them to the exact stroke
 * centerline via Chamfer watershed, traces inter-pixel crack boundaries, and
 * simplifies shared edges canonically so adjacent pieces share bit-for-bit identical vertices.
 */
export function extractRegionsFromMask(
  wallMask: Uint8Array,
  w: number,
  h: number,
  options?: {
    targetWidth?: number;
    targetHeight?: number;
    offsetX?: number;
    offsetY?: number;
    minAreaPx?: number;
    simplifyEpsilon?: number;
  },
): SvgImportedPiece[] {
  const total = w * h;
  // labels: -1 = wall, 0 = unvisited, 1 = exterior, >= 2 = interior region id
  const labels = new Int32Array(total);
  for (let i = 0; i < total; i++) {
    if (wallMask[i]) labels[i] = -1;
  }

  const queue = new Int32Array(total);

  const floodFill = (seedIdx: number, labelId: number) => {
    let head = 0;
    let tail = 0;
    labels[seedIdx] = labelId;
    queue[tail++] = seedIdx;
    let count = 0;
    while (head < tail) {
      const idx = queue[head++];
      count++;
      const x = idx % w;
      const y = (idx - x) / w;
      if (x > 0 && labels[idx - 1] === 0) { labels[idx - 1] = labelId; queue[tail++] = idx - 1; }
      if (x + 1 < w && labels[idx + 1] === 0) { labels[idx + 1] = labelId; queue[tail++] = idx + 1; }
      if (y > 0 && labels[idx - w] === 0) { labels[idx - w] = labelId; queue[tail++] = idx - w; }
      if (y + 1 < h && labels[idx + w] === 0) { labels[idx + w] = labelId; queue[tail++] = idx + w; }
    }
    return count;
  };

  // 1. Mark exterior by flood-filling from all 4 borders
  for (let x = 0; x < w; x++) {
    if (labels[x] === 0) floodFill(x, 1);
    const bot = (h - 1) * w + x;
    if (labels[bot] === 0) floodFill(bot, 1);
  }
  for (let y = 0; y < h; y++) {
    const left = y * w;
    if (labels[left] === 0) floodFill(left, 1);
    const right = y * w + (w - 1);
    if (labels[right] === 0) floodFill(right, 1);
  }

  // 2. Flood-fill interior regions; absorb tiny noise specks back into walls
  const minAreaPx = options?.minAreaPx ?? Math.max(36, Math.round(total * 0.0003));
  const epsilon = options?.simplifyEpsilon ?? 1.8;
  const sx = (options?.targetWidth ?? w) / w;
  const sy = (options?.targetHeight ?? h) / h;
  const ox = options?.offsetX ?? 0;
  const oy = options?.offsetY ?? 0;

  let nextLabel = 2;
  const validLabels = new Set<number>();

  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const idx = y * w + x;
      if (labels[idx] !== 0) continue;
      const labelId = nextLabel++;
      const area = floodFill(idx, labelId);
      if (area < minAreaPx) {
        // Re-mark tiny noise as wall so watershed absorbs it cleanly
        for (let k = 0; k < area; k++) {
          labels[queue[k]] = -1;
        }
      } else {
        validLabels.add(labelId);
      }
    }
  }

  if (validLabels.size === 0) return [];

  // 3. Expand all valid regions + exterior into walls until they meet at the exact centerline
  expandRegionsToCenterline(labels, w, h);

  // Find topmost-leftmost pixel for each valid label after expansion
  const firstPixel = new Map<number, [number, number]>();
  for (let y = 0; y < h; y++) {
    const row = y * w;
    for (let x = 0; x < w; x++) {
      const lab = labels[row + x];
      if (lab >= 2 && validLabels.has(lab) && !firstPixel.has(lab)) {
        firstPixel.set(lab, [x, y]);
      }
    }
  }

  // 4. Trace crack boundaries & simplify shared chains canonically between junction vertices
  const chainCache = new Map<string, Pt[]>();
  const simplifySharedChain = (chain: Pt[]): Pt[] => {
    if (chain.length <= 2) return chain;
    const a = chain[0];
    const b = chain[chain.length - 1];
    const mid = chain[Math.floor(chain.length / 2)];
    const forward = a[0] < b[0] || (a[0] === b[0] && a[1] <= b[1]);
    const ordered = forward ? chain : [...chain].reverse();
    const s = ordered[0];
    const e = ordered[ordered.length - 1];
    // Include chain length + midpoint in key to disambiguate parallel chains sharing endpoints
    const key = `${s[0]},${s[1]}->${e[0]},${e[1]}:${ordered.length}:${mid[0]},${mid[1]}`;
    let simplified = chainCache.get(key);
    if (!simplified) {
      simplified = rdpSimplifyOpen(ordered, epsilon);
      chainCache.set(key, simplified);
    }
    return forward ? simplified : [...simplified].reverse();
  };

  const pieces: SvgImportedPiece[] = [];
  for (const [labelId, [startX, startY]] of firstPixel.entries()) {
    const boundary = traceCrackBoundary(labels, w, h, labelId, startX, startY);
    if (boundary.length < 4) continue;

    const junctionIndices: number[] = [];
    for (let i = 0; i < boundary.length; i++) {
      if (isJunctionVertex(labels, w, h, boundary[i][0], boundary[i][1])) {
        junctionIndices.push(i);
      }
    }

    let simplified: Pt[];
    if (junctionIndices.length >= 2) {
      simplified = [];
      for (let j = 0; j < junctionIndices.length; j++) {
        const i0 = junctionIndices[j];
        const i1 = junctionIndices[(j + 1) % junctionIndices.length];
        const chain: Pt[] = [];
        let k = i0;
        while (true) {
          chain.push(boundary[k]);
          if (k === i1) break;
          k = (k + 1) % boundary.length;
        }
        const simpChain = simplifySharedChain(chain);
        // Append all except the last vertex (which is the start of the next chain)
        for (let m = 0; m < simpChain.length - 1; m++) {
          simplified.push(simpChain[m]);
        }
      }
    } else {
      simplified = rdpSimplifyClosed(boundary, epsilon);
    }

    if (simplified.length < 3) continue;

    const scaled: Pt[] = simplified.map(([bx, by]) => [bx * sx + ox, by * sy + oy]);
    if (Math.abs(polygonSignedArea(scaled)) < 9) continue;

    pieces.push({ polygon: scaled });
  }

  return pieces;
}
