import type {
  Project,
  Piece,
  GlassSheet,
  LampConfig,
  LampProfilePoint,
  Crop,
  Scale,
  ScaleUnit,
  TextureTransform,
  BoundingBox,
  PromptPoint,
  CurvePoint,
  SolderColor,
} from '../types';

/** Bump this whenever `Project`'s shape changes and add a migration below. */
export const PROJECT_SCHEMA_VERSION = 1;

const NO_CROP: Crop = { top: 0, left: 0, bottom: 0, right: 0 };
const SCALE_UNITS: ScaleUnit[] = ['mm', 'cm', 'in'];

/** A piece/sheet/section that was dropped or reset while repairing a project file. */
export interface RepairNote {
  /** Diagnostic path into the source JSON, e.g. "pieces[3].polygon". */
  path: string;
  /** i18next key describing why; interpolate with {{path}}. */
  reasonKey: string;
}

export interface ParsedProject {
  ok: true;
  project: Project;
  /** Empty when the file loaded clean; otherwise what was dropped/reset and why. */
  repairs: RepairNote[];
}

export interface RefusedProject {
  ok: false;
  /** i18next key for the refusal message; no interpolation needed. */
  reasonKey: string;
}

export type ParseProjectResult = ParsedProject | RefusedProject;

type RawProject = Record<string, unknown>;

// ---- migration ladder ---------------------------------------------------
// One entry per source version, keyed by the version being migrated FROM.
// Each step returns a raw object shaped for `version + 1`.
const MIGRATIONS: Record<number, (raw: RawProject) => RawProject> = {
  // v0 (unversioned legacy) -> v1: today's shape. Early exports predate a
  // couple of now-required top-level fields; fill them with the defaults
  // those fields always had before they existed.
  0: (raw) => ({
    ...raw,
    patternCrop: isValidCrop(raw.patternCrop) ? raw.patternCrop : NO_CROP,
    patternWidth: isFiniteNumber(raw.patternWidth) ? raw.patternWidth : 800,
    patternHeight: isFiniteNumber(raw.patternHeight) ? raw.patternHeight : 600,
  }),
};

function migrate(raw: RawProject, fromVersion: number): RawProject {
  let current = raw;
  for (let v = fromVersion; v < PROJECT_SCHEMA_VERSION; v++) {
    const step = MIGRATIONS[v];
    if (step) current = step(current);
  }
  return current;
}

// ---- primitive guards -----------------------------------------------------

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function isFiniteNumber(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

function isString(v: unknown): v is string {
  return typeof v === 'string';
}

function isValidCrop(v: unknown): v is Crop {
  return isPlainObject(v)
    && isFiniteNumber(v.top) && isFiniteNumber(v.left)
    && isFiniteNumber(v.bottom) && isFiniteNumber(v.right);
}

function isValidScale(v: unknown): v is Scale {
  if (!isPlainObject(v)) return false;
  if (!isFiniteNumber(v.pxPerUnit)) return false;
  if (!SCALE_UNITS.includes(v.unit as ScaleUnit)) return false;
  const line = v.line;
  return isPlainObject(line)
    && isFiniteNumber(line.x1) && isFiniteNumber(line.y1)
    && isFiniteNumber(line.x2) && isFiniteNumber(line.y2);
}

function isValidTransform(v: unknown): v is TextureTransform {
  return isPlainObject(v)
    && isFiniteNumber(v.x) && isFiniteNumber(v.y)
    && isFiniteNumber(v.rotation) && isFiniteNumber(v.scale);
}

function isValidBoundingBox(v: unknown): v is BoundingBox {
  return isPlainObject(v)
    && isFiniteNumber(v.x1) && isFiniteNumber(v.y1)
    && isFiniteNumber(v.x2) && isFiniteNumber(v.y2);
}

function isValidPolygon(v: unknown): v is [number, number][] {
  return Array.isArray(v) && v.length >= 3
    && v.every(p => Array.isArray(p) && p.length === 2 && isFiniteNumber(p[0]) && isFiniteNumber(p[1]));
}

function isValidCurvePoints(v: unknown): v is CurvePoint[] {
  return Array.isArray(v) && v.every(cp =>
    isPlainObject(cp) && Number.isInteger(cp.edgeIdx) && (cp.edgeIdx as number) >= 0
    && Array.isArray(cp.ctrl) && cp.ctrl.length === 2
    && isFiniteNumber(cp.ctrl[0]) && isFiniteNumber(cp.ctrl[1])
    && (cp.kind === undefined || cp.kind === 'quadratic' || cp.kind === 'cubic')
    && (cp.ctrl2 === undefined || (
      Array.isArray(cp.ctrl2) && cp.ctrl2.length === 2
      && isFiniteNumber(cp.ctrl2[0]) && isFiniteNumber(cp.ctrl2[1])
    ))
    && (cp.kind !== 'cubic' || (
      Array.isArray(cp.ctrl2) && cp.ctrl2.length === 2
      && isFiniteNumber(cp.ctrl2[0]) && isFiniteNumber(cp.ctrl2[1])
    ))
  );
}

function validCurvePointsForPolygon(v: unknown, vertexCount: number): CurvePoint[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const valid = v.filter((curve): curve is CurvePoint =>
    isValidCurvePoints([curve]) && curve.edgeIdx < vertexCount
  );
  return valid.length > 0 ? valid : undefined;
}

function validAnchorTypes(v: unknown, vertexCount: number): ('corner' | 'smooth')[] | undefined {
  if (!Array.isArray(v) || v.length !== vertexCount) return undefined;
  return v.every(type => type === 'corner' || type === 'smooth') ? v : undefined;
}

function isValidPromptPoints(v: unknown): v is PromptPoint[] {
  return Array.isArray(v) && v.every(p =>
    isPlainObject(p) && isFiniteNumber(p.x) && isFiniteNumber(p.y) && (p.label === 0 || p.label === 1)
  );
}

// ---- per-item validation ---------------------------------------------------

function validateSheet(raw: unknown, index: number, repairs: RepairNote[]): GlassSheet | null {
  const path = `sheets[${index}]`;
  if (!isPlainObject(raw)) {
    repairs.push({ path, reasonKey: 'schemaDropSheetNotObject' });
    return null;
  }
  const { id, label, imageUrl, crop, scale, naturalWidth, naturalHeight, swatch, ...rest } = raw;
  if (!isString(id) || !id) {
    repairs.push({ path, reasonKey: 'schemaDropSheetMissingId' });
    return null;
  }
  if (!isString(imageUrl) || !imageUrl) {
    repairs.push({ path: `${path}.imageUrl`, reasonKey: 'schemaDropSheetBadImage' });
    return null;
  }
  const sheet: GlassSheet = {
    ...rest,
    id,
    label: isString(label) ? label : `Sheet ${index + 1}`,
    imageUrl,
    crop: isValidCrop(crop) ? crop : NO_CROP,
    scale: isValidScale(scale) ? scale : null,
  };
  if (isFiniteNumber(naturalWidth)) sheet.naturalWidth = naturalWidth;
  if (isFiniteNumber(naturalHeight)) sheet.naturalHeight = naturalHeight;
  if (isString(swatch)) sheet.swatch = swatch;
  return sheet;
}

function validatePiece(raw: unknown, index: number, validSheetIds: Set<string>, repairs: RepairNote[]): Piece | null {
  const path = `pieces[${index}]`;
  if (!isPlainObject(raw)) {
    repairs.push({ path, reasonKey: 'schemaDropPieceNotObject' });
    return null;
  }
  const {
    id, label, polygon, curvePoints, anchorTypes, glassSheetId, transform,
    promptBox, promptPoints, tierIndex, facetIndex, symmetryGroupId,
    ...rest
  } = raw;
  if (!isString(id) || !id) {
    repairs.push({ path, reasonKey: 'schemaDropPieceMissingId' });
    return null;
  }
  if (!isValidPolygon(polygon)) {
    repairs.push({ path: `${path}.polygon`, reasonKey: 'schemaDropPieceBadPolygon' });
    return null;
  }
  if (!isString(glassSheetId) || !validSheetIds.has(glassSheetId)) {
    repairs.push({ path: `${path}.glassSheetId`, reasonKey: 'schemaDropPieceBadSheetRef' });
    return null;
  }
  if (!isValidTransform(transform)) {
    repairs.push({ path: `${path}.transform`, reasonKey: 'schemaDropPieceBadTransform' });
    return null;
  }
  const piece: Piece = {
    ...rest,
    id,
    label: isString(label) ? label : `Piece ${index + 1}`,
    polygon,
    glassSheetId,
    transform,
  };
  const validCurves = validCurvePointsForPolygon(curvePoints, polygon.length);
  if (validCurves) piece.curvePoints = validCurves;
  const validAnchors = validAnchorTypes(anchorTypes, polygon.length);
  if (validAnchors) piece.anchorTypes = validAnchors;
  if (isValidBoundingBox(promptBox)) piece.promptBox = promptBox;
  if (isValidPromptPoints(promptPoints)) piece.promptPoints = promptPoints;
  if (isFiniteNumber(tierIndex)) piece.tierIndex = tierIndex;
  if (isFiniteNumber(facetIndex)) piece.facetIndex = facetIndex;
  if (isString(symmetryGroupId)) piece.symmetryGroupId = symmetryGroupId;
  return piece;
}

function validateLampConfig(raw: unknown, repairs: RepairNote[]): LampConfig | undefined {
  if (raw === undefined) return undefined;
  if (!isPlainObject(raw)) {
    repairs.push({ path: 'lampConfig', reasonKey: 'schemaDropLampConfig' });
    return undefined;
  }
  const { facetCount, profilePoints, activeTierIndex, smooth, ...rest } = raw;
  const validPoints: LampProfilePoint[] = Array.isArray(profilePoints)
    ? profilePoints.filter((p): p is LampProfilePoint => isPlainObject(p) && isFiniteNumber(p.r) && isFiniteNumber(p.y))
    : [];
  // A lamp needs at least two profile points to define one tier.
  if (validPoints.length < 2) {
    repairs.push({ path: 'lampConfig.profilePoints', reasonKey: 'schemaDropLampConfig' });
    return undefined;
  }
  const tierCount = validPoints.length - 1;
  const rawTier = isFiniteNumber(activeTierIndex) ? Math.round(activeTierIndex) : 0;
  const config: LampConfig = {
    ...rest,
    facetCount: isFiniteNumber(facetCount) && facetCount > 0 ? facetCount : 6,
    profilePoints: validPoints,
    activeTierIndex: Math.min(Math.max(rawTier, 0), tierCount - 1),
  };
  if (typeof smooth === 'boolean') config.smooth = smooth;
  return config;
}

// ---- entry point ------------------------------------------------------------

/**
 * Validate, migrate, and normalize a raw JSON value into a `Project`.
 *
 * Repair-and-load: malformed pieces/sheets are dropped individually (see
 * `repairs`) and everything else loads. Only genuinely unusable input is
 * refused outright — not an object, no usable pieces/sheets arrays at all,
 * or a `version` newer than this app understands.
 */
export function parseProject(raw: unknown): ParseProjectResult {
  if (!isPlainObject(raw)) {
    return { ok: false, reasonKey: 'schemaRefuseNotObject' };
  }

  const rawVersion = isFiniteNumber(raw.version) ? raw.version : 0;
  if (rawVersion > PROJECT_SCHEMA_VERSION) {
    return { ok: false, reasonKey: 'schemaRefuseNewerVersion' };
  }

  const piecesPresent = Array.isArray(raw.pieces);
  const sheetsPresent = Array.isArray(raw.sheets);
  if (!piecesPresent && !sheetsPresent) {
    return { ok: false, reasonKey: 'schemaRefuseNoUsableData' };
  }

  const repairs: RepairNote[] = [];
  if (raw.pieces !== undefined && !piecesPresent) repairs.push({ path: 'pieces', reasonKey: 'schemaDropPiecesField' });
  if (raw.sheets !== undefined && !sheetsPresent) repairs.push({ path: 'sheets', reasonKey: 'schemaDropSheetsField' });

  const migrated = migrate(raw, rawVersion);

  const sheetsIn = Array.isArray(migrated.sheets) ? migrated.sheets : [];
  const sheets = sheetsIn
    .map((s, i) => validateSheet(s, i, repairs))
    .filter((s): s is GlassSheet => s !== null);
  const validSheetIds = new Set(sheets.map(s => s.id));

  const piecesIn = Array.isArray(migrated.pieces) ? migrated.pieces : [];
  const pieces = piecesIn
    .map((p, i) => validatePiece(p, i, validSheetIds, repairs))
    .filter((p): p is Piece => p !== null);

  const lampConfig = validateLampConfig(migrated.lampConfig, repairs);

  const {
    name, patternImageUrl, patternWidth, patternHeight, patternCrop, patternScale,
    solderWidthMM, solderColor, projectType,
    pieces: _pieces, sheets: _sheets, lampConfig: _lampConfig, version: _version,
    ...rest
  } = migrated;

  const project: Project = {
    ...rest,
    version: PROJECT_SCHEMA_VERSION,
    name: isString(name) ? name : 'Untitled Project',
    patternImageUrl: isString(patternImageUrl) ? patternImageUrl : '',
    patternWidth: isFiniteNumber(patternWidth) ? patternWidth : 800,
    patternHeight: isFiniteNumber(patternHeight) ? patternHeight : 600,
    patternCrop: isValidCrop(patternCrop) ? patternCrop : NO_CROP,
    patternScale: isValidScale(patternScale) ? patternScale : null,
    pieces,
    sheets,
  };
  if (isFiniteNumber(solderWidthMM)) project.solderWidthMM = solderWidthMM;
  if (solderColor === 'black' || solderColor === 'silver' || solderColor === 'copper') {
    project.solderColor = solderColor as SolderColor;
  }
  if (projectType === 'flat' || projectType === 'lamp') project.projectType = projectType;
  if (lampConfig) project.lampConfig = lampConfig;

  return { ok: true, project, repairs };
}
