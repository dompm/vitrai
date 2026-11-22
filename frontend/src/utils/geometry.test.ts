import { describe, expect, it } from 'vitest';
import {
  arePolygonsEqual,
  bendEdgeMidpointToCubic,
  computeCentroid,
  computeLabelPoint,
  computePolygonArea,
  constrainEditedPiece,
  curveToCubicControls,
  deletePieceVertex,
  evaluateCubicBezier,
  evaluateQuadraticBezier,
  findInteriorPoint,
  fitSmoothPieceCurves,
  flattenCurves,
  insetPolygon,
  isCubicCurvePoint,
  makeCubicCurvePoint,
  pieceToSvgPath,
  quadraticToCubicControls,
  resplitHoledSource,
  retractPieceHandle,
  smoothPieceGeometry,
  smoothPieceVertex,
  snapPolygonToNeighbors,
  splitCubicBezier,
  subtractPolygons,
  subtractPolygonsWithSplit,
} from './geometry';

describe('curve compatibility', () => {
  it('keeps legacy quadratic curves equivalent when converted to cubic controls', () => {
    const start: [number, number] = [0, 0];
    const control: [number, number] = [50, 80];
    const end: [number, number] = [100, 0];
    const [ctrl1, ctrl2] = quadraticToCubicControls(start, control, end);

    for (const t of [0, 0.1, 0.25, 0.5, 0.9, 1]) {
      const quadratic = evaluateQuadraticBezier(start, control, end, t);
      const cubic = evaluateCubicBezier(start, ctrl1, ctrl2, end, t);
      expect(cubic[0]).toBeCloseTo(quadratic[0], 8);
      expect(cubic[1]).toBeCloseTo(quadratic[1], 8);
    }
  });

  it('distinguishes saved cubic metadata from legacy quadratic metadata', () => {
    const cubic = makeCubicCurvePoint(0, [20, 40], [80, 40]);
    expect(isCubicCurvePoint(cubic)).toBe(true);
    expect(isCubicCurvePoint({ edgeIdx: 0, ctrl: [50, 50] })).toBe(false);
    expect(curveToCubicControls([0, 0], [100, 0], cubic)).toEqual([[20, 40], [80, 40]]);
  });

  it('splits cubic curves without a discontinuity', () => {
    const source = { start: [0, 0] as [number, number], ctrl1: [25, 80] as [number, number], ctrl2: [75, -20] as [number, number], end: [100, 0] as [number, number] };
    const [left, right] = splitCubicBezier(source, 0.37);
    expect(left.end[0]).toBeCloseTo(right.start[0], 10);
    expect(left.end[1]).toBeCloseTo(right.start[1], 10);
    const expected = evaluateCubicBezier(source.start, source.ctrl1, source.ctrl2, source.end, 0.37);
    expect(left.end[0]).toBeCloseTo(expected[0], 10);
    expect(left.end[1]).toBeCloseTo(expected[1], 10);
  });

  it('adaptively flattens a cubic while preserving polygon anchors', () => {
    const polygon: [number, number][] = [[0, 0], [100, 0], [100, 100]];
    const flattened = flattenCurves(polygon, [makeCubicCurvePoint(0, [20, 80], [80, 80])], 0.25);
    expect(flattened[0]).toEqual(polygon[0]);
    expect(flattened).toContainEqual(polygon[1]);
    expect(flattened.length).toBeGreaterThan(polygon.length);
  });

  it('clips an edited polygon against the visible boundary of a curved neighbor', () => {
    const neighbor = flattenCurves(
      [[0, 0], [100, 0], [100, 100], [0, 100]],
      [makeCubicCurvePoint(1, [130, 20], [130, 80])],
      0.25,
    );
    const crossingEdit: [number, number][] = [[90, 20], [160, 50], [90, 80]];
    const clipped = subtractPolygons(crossingEdit, [neighbor]);

    expect(clipped.length).toBeGreaterThanOrEqual(3);
    expect(clipped.every(([x]) => x >= 99.9)).toBe(true);
  });

  it('preserves exact vertex order when touching a neighbor along a shared edge', () => {
    const neighbor: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    const touching: [number, number][] = [[100, 10], [200, 10], [200, 90], [100, 90]];
    const clipped = subtractPolygons(touching, [neighbor]);
    expect(arePolygonsEqual(touching, clipped, 0.1)).toBe(true);
  });
});

describe('seam snapping and curve fitting for fabrication', () => {
  it('snaps directly to neighbor corners at T-junctions and bridges single-vertex seam gaps', () => {
    const neighbor: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    // Piece shares x=100 edge with neighbor: top vertex near [100, 0], middle vertex slightly pulled back at x=91, bottom vertex near [100, 100]
    const raw: [number, number][] = [[103, 2], [200, 0], [200, 100], [102, 98], [91, 50]];
    const snapped = snapPolygonToNeighbors(raw, [neighbor], 8);

    // Top and bottom corners snap directly to [100, 0] and [100, 100], and the mid-seam gap at x=91 is closed onto x=100
    expect(snapped).toContainEqual([100, 0]);
    expect(snapped).toContainEqual([100, 100]);
    expect(snapped.every(([x]) => x >= 100)).toBe(true);
  });

  it('converts a faceted leaf contour into smooth cubic Béziers while keeping sharp tips and shared seams locked', () => {
    const neighbor: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    // Leaf sharing the vertical seam from (100, 20) to (100, 80) and arching out to a sharp tip at (220, 50)
    const upperArc: [number, number][] = [
      [100, 20],
      [125, 8],
      [155, 4],
      [185, 14],
      [220, 50], // sharp tip
      [185, 86],
      [155, 96],
      [125, 92],
      [100, 80],
    ];
    const fitted = fitSmoothPieceCurves(upperArc, [neighbor], { seamTolerancePx: 2.5 });

    // Should simplify the 9 faceted points into structural anchors with cubic curves on the two free arcs
    expect(fitted.polygon.length).toBeLessThan(upperArc.length);
    expect(fitted.curvePoints.length).toBeGreaterThanOrEqual(2);
    // Sharp tip at [220, 50] and seam endpoints [100, 20], [100, 80] are preserved as corner anchors
    expect(fitted.polygon).toContainEqual([220, 50]);
    expect(fitted.polygon).toContainEqual([100, 20]);
    expect(fitted.polygon).toContainEqual([100, 80]);

    // The locked seam edge from [100, 80] -> [100, 20] must remain a straight un-curved segment
    const seamStartIdx = fitted.polygon.findIndex(p => p[0] === 100 && p[1] === 80);
    expect(seamStartIdx).toBeGreaterThanOrEqual(0);
    expect(fitted.curvePoints.some(cp => cp.edgeIdx === seamStartIdx)).toBe(false);
  });

  it('smoothPieceGeometry rounds moderate kinks while pinning neighbor-shared seams', () => {
    const neighbor: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    const kinked: [number, number][] = [
      [100, 20],
      [150, 5],
      [200, 50],
      [150, 95],
      [100, 80],
    ];
    const smoothed = smoothPieceGeometry(kinked, [], [neighbor], 2.5);
    expect(smoothed.polygon).toContainEqual([100, 20]);
    expect(smoothed.polygon).toContainEqual([100, 80]);
    expect(smoothed.curvePoints.length).toBeGreaterThan(0);
  });

  it('insets a polygon inward by exact physical allowance for foil/came pattern shears', () => {
    const square: [number, number][] = [[0, 0], [100, 0], [100, 80], [0, 80]];
    const inset = insetPolygon(square, 2.5);
    expect(inset).toHaveLength(4);
    expect(inset[0][0]).toBeCloseTo(2.5, 4);
    expect(inset[0][1]).toBeCloseTo(2.5, 4);
    expect(inset[2][0]).toBeCloseTo(97.5, 4);
    expect(inset[2][1]).toBeCloseTo(77.5, 4);
  });

  it('serializes curved pieces to native SVG cubic Bézier path commands', () => {
    const poly: [number, number][] = [[0, 0], [100, 0], [50, 80]];
    const curves = [makeCubicCurvePoint(0, [30, -20], [70, -20])];
    const d = pieceToSvgPath(poly, curves);
    expect(d).toContain('M 0 0');
    expect(d).toContain('C 30 -20, 70 -20, 100 0');
    expect(d).toContain('L 50 80');
    expect(d.endsWith('Z')).toBe(true);
  });

  it('reconstructs all 4 crisp corners and keeps straight sides straight on a SAM2-beveled rectangle', () => {
    // A 120x80 rectangle [0..120, 0..80] where SAM2 rounded all 4 90° corners into 3-vertex
    // chamfers (~30° turn at each individual vertex, so every single vertex turn is < 40°)
    // and added slight ~1.5px wobble along the straight sides.
    const samBeveledRect: [number, number][] = [
      [14, 0],
      [60, 1.2],   // slight top-edge wobble
      [106, 0],    // top-right bevel start (~30°)
      [115, 5],    // top-right bevel mid (~30°)
      [120, 14],   // top-right bevel end (~30°)
      [119, 42],   // slight right-edge wobble
      [120, 66],   // bottom-right bevel start (~30°)
      [115, 75],   // bottom-right bevel mid (~30°)
      [106, 80],   // bottom-right bevel end (~30°)
      [62, 78.8],  // slight bottom-edge wobble
      [14, 80],    // bottom-left bevel start (~30°)
      [5, 75],     // bottom-left bevel mid (~30°)
      [0, 66],     // bottom-left bevel end (~30°)
      [1.1, 40],   // slight left-edge wobble
      [0, 14],     // top-left bevel start (~30°)
      [5, 5],      // top-left bevel mid (~30°)
    ];

    const fitted = fitSmoothPieceCurves(samBeveledRect, [], { cornerAngleDeg: 40 });

    // Must preserve all 4 corners as a 4-vertex rectangle with zero curved edges
    expect(fitted.polygon).toHaveLength(4);
    expect(fitted.curvePoints).toHaveLength(0);
    expect(fitted.anchorTypes).toEqual(['corner', 'corner', 'corner', 'corner']);

    // Check that each of the 4 true rectangle corners (0,0), (120,0), (120,80), (0,80) is reconstructed
    const expectedCorners: [number, number][] = [[0, 0], [120, 0], [120, 80], [0, 80]];
    for (const [ex, ey] of expectedCorners) {
      const match = fitted.polygon.some(([px, py]) => Math.hypot(px - ex, py - ey) < 2.5);
      expect(match).toBe(true);
    }
  });

  it('preserves all 4 corners and straight sides on a narrow border rectangle adjacent to a neighbor pane', () => {
    const topLeftNeighbor: [number, number][] = [[0, 0], [70, 0], [70, 60], [0, 60]];
    // Adjacent horizontal border pane [70..200, 0..60] whose left edge shares x=70 with topLeftNeighbor
    // and whose right corners at (200,0) and (200,60) were beveled by SAM2 into <38° steps
    const rawAdjacentBorderPane: [number, number][] = [
      [70, 0],
      [135, 1.0],
      [186, 0],
      [195, 5],
      [200, 14],
      [200, 46],
      [195, 55],
      [186, 60],
      [130, 59.1],
      [70, 60],
    ];

    const fitted = fitSmoothPieceCurves(rawAdjacentBorderPane, [topLeftNeighbor], { cornerAngleDeg: 40 });
    expect(fitted.polygon).toHaveLength(4);
    expect(fitted.curvePoints).toHaveLength(0);
    expect(fitted.polygon).toContainEqual([70, 0]);
    expect(fitted.polygon).toContainEqual([70, 60]);
    expect(fitted.polygon.some(([px, py]) => Math.hypot(px - 200, py - 0) < 2.5)).toBe(true);
    expect(fitted.polygon.some(([px, py]) => Math.hypot(px - 200, py - 60) < 2.5)).toBe(true);
  });

  it('hugs a concave edge without bowing outward when a SAM2 corner bevel reverses the endpoint step', () => {
    // Reproduces the orange body piece (piece 1): top-right edge from top apex (200, 50)
    // to right corner (450, 220) is concave (bows inward/downward below the chord),
    // except the final short SAM2 corner-rounding step from (442, 210) to (450, 220)
    // which slopes more steeply downward than the chord.
    const topApex: [number, number] = [200, 50];
    const rightCorner: [number, number] = [450, 220];
    const concaveEdgePts: [number, number][] = [
      topApex,
      [240, 92],
      [290, 134],
      [345, 168],
      [400, 195],
      [442, 210], // short corner-rounding bevel step before rightCorner
      rightCorner,
    ];
    const orangeBodyPoly: [number, number][] = [
      ...concaveEdgePts,
      [410, 340],
      [320, 410],
      [200, 420],
      [110, 350],
      [80, 240],
      [130, 95],
    ];

    const fitted = fitSmoothPieceCurves(orangeBodyPoly, [], { cornerAngleDeg: 40 });
    const dense = flattenCurves(fitted.polygon, fitted.curvePoints, 0.5);

    // Every sampled point along the top-right span (x in [210, 440], y < 230) must stay
    // on the concave (inward/below-chord) side of the line from topApex to rightCorner,
    // and within 3.5px of the original concave polyline.
    const topRightSamples = dense.filter(([x, y]) => x >= 210 && x <= 440 && y <= 225);
    expect(topRightSamples.length).toBeGreaterThan(5);

    for (const [x, y] of topRightSamples) {
      const t = (x - topApex[0]) / (rightCorner[0] - topApex[0]);
      const chordY = topApex[1] + t * (rightCorner[1] - topApex[1]);
      // In screen coordinates (+y down), inward/concave is y >= chordY (never bowing above chord into leaf 2)
      expect(y).toBeGreaterThanOrEqual(chordY - 1.0);
    }
  });

  it('bridges multi-vertex solder-width variations along a shared seam in snapPolygonToNeighbors', () => {
    const neighbor: [number, number][] = [
      [0, 0],
      [100, 0],
      [100, 30],
      [100, 60],
      [100, 90],
      [100, 120],
      [0, 120],
    ];
    // Piece to the right of x=100 where ends of the seam are 11px away (within radius=14)
    // and 3 interior vertices bulge out to 19–22px where the solder line widened.
    const piece: [number, number][] = [
      [111, 5],
      [119, 32],
      [122, 60],
      [118, 88],
      [112, 115],
      [200, 115],
      [200, 5],
    ];
    const snapped = snapPolygonToNeighbors(piece, [neighbor], 14);
    const leftSeamPts = snapped.filter(([x]) => x < 150);
    expect(leftSeamPts.length).toBeGreaterThanOrEqual(3);
    for (const [x] of leftSeamPts) {
      expect(Math.abs(x - 100)).toBeLessThan(0.5);
    }
  });

  it('prunes solder-line contour blisters without turning curve subdivisions into sharp corners', () => {
    // Smooth crescent leaf with two sharp tips at (0, 100) and (200, 100) plus a 6px Z-jog blister on the top arc
    const pts: [number, number][] = [];
    for (let i = 0; i <= 20; i++) {
      const t = i / 20;
      const x = 200 * t;
      const y = 100 - 70 * Math.sin(Math.PI * t);
      pts.push([x, y]);
      if (i === 10) {
        // Inject a narrow 6px blister detour
        pts.push([x + 2, y - 6], [x + 5, y - 5], [x + 3, y]);
      }
    }
    for (let i = 19; i >= 1; i--) {
      const t = i / 20;
      const x = 200 * t;
      const y = 100 + 35 * Math.sin(Math.PI * t);
      pts.push([x, y]);
    }

    const fitted = fitSmoothPieceCurves(pts, [], { cornerAngleDeg: 40 });
    const cornerCount = fitted.anchorTypes.filter(t => t === 'corner').length;
    expect(cornerCount).toBe(2);
    // Newton-Raphson reparameterization should fit each leaf arc with at most 1 interior smooth anchor (<= 4 total anchors)
    expect(fitted.polygon.length).toBeLessThanOrEqual(4);
    expect(fitted.curvePoints.length).toBeGreaterThanOrEqual(2);
  });
});


describe('subtractPolygonsWithSplit', () => {
  const outerSquare: [number, number][] = [
    [0, 0], [200, 0], [200, 200], [0, 200],
  ];
  const innerSquare: [number, number][] = [
    [70, 70], [130, 70], [130, 130], [70, 130],
  ];

  it('auto-splits a ring enclosing an existing piece into 2 non-overlapping halves with exact area', () => {
    const res = subtractPolygonsWithSplit(outerSquare, [innerSquare], 0);
    expect(res.hadHoles).toBe(true);
    expect(res.holedSource).not.toBeNull();
    expect(res.polygons).toHaveLength(2);

    const expectedArea = 200 * 200 - 60 * 60;
    const totalArea = res.polygons.reduce((s, p) => s + computePolygonArea(p), 0);
    expect(totalArea).toBeCloseTo(expectedArea, 1);

    // Neither half should overlap the inner piece
    for (const half of res.polygons) {
      const clipped = subtractPolygons(half, [innerSquare]);
      expect(computePolygonArea(clipped)).toBeCloseTo(computePolygonArea(half), 1);
    }
  });

  it('re-splits the cached holed source cleanly at arbitrary angles (0, 45, 90, 135)', () => {
    const res = subtractPolygonsWithSplit(outerSquare, [innerSquare], 0);
    expect(res.holedSource).not.toBeNull();
    const expectedArea = 200 * 200 - 60 * 60;

    for (const angle of [0, 45, 90, 135, 162]) {
      const halves = resplitHoledSource(res.holedSource!, angle);
      expect(halves).toHaveLength(2);
      const totalArea = halves.reduce((s, p) => s + computePolygonArea(p), 0);
      expect(totalArea).toBeCloseTo(expectedArea, 1);
    }
  });

  it('handles non-convex C-shaped enclosed pieces via scanline interior point', () => {
    const cShape: [number, number][] = [
      [60, 60], [140, 60], [140, 80], [80, 80],
      [80, 120], [140, 120], [140, 140], [60, 140],
    ];
    const [ix, iy] = findInteriorPoint(cShape);
    expect(ix).toBeGreaterThan(60);
    expect(ix).toBeLessThan(140);
    expect(iy).toBeGreaterThan(60);
    expect(iy).toBeLessThan(140);

    const res = subtractPolygonsWithSplit(outerSquare, [cShape], 90);
    expect(res.hadHoles).toBe(true);
    expect(res.polygons.length).toBeGreaterThanOrEqual(2);
    const expectedArea = 200 * 200 - computePolygonArea(cShape);
    const totalArea = res.polygons.reduce((s, p) => s + computePolygonArea(p), 0);
    expect(totalArea).toBeCloseTo(expectedArea, 1);
  });

  it('recursively splits a polygon enclosing two separate pieces', () => {
    const holeA: [number, number][] = [[40, 80], [80, 80], [80, 120], [40, 120]];
    const holeB: [number, number][] = [[120, 80], [160, 80], [160, 120], [120, 120]];
    const res = subtractPolygonsWithSplit(outerSquare, [holeA, holeB], 90);
    expect(res.hadHoles).toBe(true);
    expect(res.polygons.length).toBeGreaterThanOrEqual(3);
    const expectedArea = 200 * 200 - 40 * 40 - 40 * 40;
    const totalArea = res.polygons.reduce((s, p) => s + computePolygonArea(p), 0);
    expect(totalArea).toBeCloseTo(expectedArea, 1);
  });

  it('returns hadHoles=false for normal partial overlap', () => {
    const sideNeighbor: [number, number][] = [[150, -10], [250, -10], [250, 210], [150, 210]];
    const res = subtractPolygonsWithSplit(outerSquare, [sideNeighbor], 0);
    expect(res.hadHoles).toBe(false);
    expect(res.holedSource).toBeNull();
    expect(res.polygons).toHaveLength(1);
    expect(computePolygonArea(res.polygons[0])).toBeCloseTo(150 * 200, 1);
  });
});

describe('constrainEditedPiece', () => {
  it('preserves curves when dragging a free vertex despite a pre-existing tiny overlap on an untouched seam', () => {
    // Smooth 4-anchor curved oval on the right, touching a neighbor on the left with a 2px pre-existing overlap
    const basePoly: [number, number][] = [
      [100, 50], [200, 50], [200, 150], [100, 150],
    ];
    const baseCurves = [
      makeCubicCurvePoint(0, [130, 20], [170, 20]),
      makeCubicCurvePoint(1, [230, 80], [230, 120]),
      makeCubicCurvePoint(2, [170, 180], [130, 180]),
      makeCubicCurvePoint(3, [85, 120], [85, 80]), // bulges slightly into x < 100
    ];
    const neighborOnLeft: [number, number][] = [
      [0, 0], [95, 0], [95, 200], [0, 200], // overlaps the left bulge slightly
    ];
    const prevDisplay = flattenCurves(basePoly, baseCurves);

    // Drag the far-right vertex [200, 50] outward to [230, 50] (away from the neighbor!)
    const editedPoly: [number, number][] = [
      [100, 50], [230, 50], [200, 150], [100, 150],
    ];

    const res = constrainEditedPiece({
      polygon: editedPoly,
      curvePoints: baseCurves,
      previousDisplayPolygon: prevDisplay,
      neighborPolygons: [neighborOnLeft],
      snapRadius: 12,
    });

    expect(res).not.toBeNull();
    expect(res!.clipped).toBe(false);
    expect(res!.polygon).toEqual(editedPoly);
    expect(res!.curvePoints).toEqual(baseCurves);
  });

  it('refits smooth cubic curves instead of dumping dense flattened vertices when clipping genuinely occurs', () => {
    const basePoly: [number, number][] = [
      [100, 50], [200, 50], [200, 150], [100, 150],
    ];
    const baseCurves = [
      makeCubicCurvePoint(0, [130, 20], [170, 20]),
      makeCubicCurvePoint(1, [230, 80], [230, 120]),
      makeCubicCurvePoint(2, [170, 180], [130, 180]),
      makeCubicCurvePoint(3, [70, 120], [70, 80]),
    ];
    const neighborOnRight: [number, number][] = [
      [240, 0], [340, 0], [340, 200], [240, 200],
    ];
    const prevDisplay = flattenCurves(basePoly, baseCurves);

    // Drag the right vertex deeply INTO the right neighbor (x = 290)
    const editedPoly: [number, number][] = [
      [100, 50], [290, 50], [200, 150], [100, 150],
    ];
    const res = constrainEditedPiece({
      polygon: editedPoly,
      curvePoints: baseCurves,
      previousDisplayPolygon: prevDisplay,
      neighborPolygons: [neighborOnRight],
      snapRadius: 12,
    });

    expect(res).not.toBeNull();
    expect(res!.clipped).toBe(true);
    // Should be compact refitted anchors + curves, NOT a 40+ vertex raw flattened polyline
    expect(res!.polygon.length).toBeLessThan(20);
    expect(res!.curvePoints.length).toBeGreaterThan(0);
  });
});

describe('computeLabelPoint (Pole of Inaccessibility)', () => {
  it('places the label at the center of a convex square with exact inscribed radius', () => {
    const sq: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    const pt = computeLabelPoint(sq, 0.5);
    expect(pt.x).toBeCloseTo(50, 0);
    expect(pt.y).toBeCloseTo(50, 0);
    expect(pt.radius).toBeCloseTo(50, 0);
  });

  it('places the label strictly inside a C-shaped piece where computeCentroid falls outside', () => {
    // Deep C-shape opening to the right: spine x in [0, 24], top/bottom arms y in [0, 24] and [176, 200]
    const cShape: [number, number][] = [
      [0, 0], [160, 0], [160, 24], [24, 24],
      [24, 176], [160, 176], [160, 200], [0, 200],
    ];
    const naive = computeCentroid(cShape);
    // Naive centroid lands inside the empty bay (x > 24, 24 < y < 176)
    expect(naive.x).toBeGreaterThan(24);
    expect(naive.y).toBeGreaterThan(24);
    expect(naive.y).toBeLessThan(176);

    const pt = computeLabelPoint(cShape, 0.5);
    expect(pt.radius).toBeGreaterThan(10);
    // Must lie inside one of the solid arms/spine of width 24
    const inSpine = pt.x >= 0 && pt.x <= 24 && pt.y >= 0 && pt.y <= 200;
    const inTopArm = pt.x >= 0 && pt.x <= 160 && pt.y >= 0 && pt.y <= 24;
    const inBotArm = pt.x >= 0 && pt.x <= 160 && pt.y >= 176 && pt.y <= 200;
    expect(inSpine || inTopArm || inBotArm).toBe(true);
  });

  it('places the label inside the widest part of a semicircular half-ring', () => {
    // Half-annulus: outer r=100, inner r=65 on the right (+x) side of center (100, 100)
    const halfRing: [number, number][] = [];
    for (let i = 0; i <= 20; i++) {
      const a = -Math.PI / 2 + (Math.PI * i) / 20;
      halfRing.push([100 + 100 * Math.cos(a), 100 + 100 * Math.sin(a)]);
    }
    for (let i = 20; i >= 0; i--) {
      const a = -Math.PI / 2 + (Math.PI * i) / 20;
      halfRing.push([100 + 65 * Math.cos(a), 100 + 65 * Math.sin(a)]);
    }
    const naive = computeCentroid(halfRing);
    // Naive centroid lands inside the inner hole (distance from (100,100) < 65)
    expect(Math.hypot(naive.x - 100, naive.y - 100)).toBeLessThan(65);

    const pt = computeLabelPoint(halfRing, 0.5);
    const distFromCenter = Math.hypot(pt.x - 100, pt.y - 100);
    // Must land squarely inside the solid band r in [65, 100], near midpoint r ≈ 82.5
    expect(distFromCenter).toBeGreaterThan(75);
    expect(distFromCenter).toBeLessThan(90);
    expect(pt.radius).toBeGreaterThan(15);
    expect(pt.radius).toBeLessThan(20);
  });
});

describe('deletePieceVertex', () => {
  it('refuses to delete a vertex from a triangle', () => {
    const tri: [number, number][] = [[0, 0], [100, 0], [50, 100]];
    expect(deletePieceVertex(tri, [], ['corner', 'corner', 'corner'], 1)).toBeNull();
  });

  it('merges adjacent cubic curves using outer handles instead of flattening to a straight line', () => {
    const quad: [number, number][] = [[0, 0], [50, 0], [100, 0], [100, 100], [0, 100]];
    const curves = [
      makeCubicCurvePoint(0, [15, -25], [35, -25]),
      makeCubicCurvePoint(1, [65, -25], [85, -25]),
      makeCubicCurvePoint(3, [50, 125], [20, 125]),
    ];
    const anchorTypes: ('corner' | 'smooth')[] = ['corner', 'smooth', 'corner', 'corner', 'corner'];

    const res = deletePieceVertex(quad, curves, anchorTypes, 1);
    expect(res).not.toBeNull();
    expect(res!.polygon).toEqual([[0, 0], [100, 0], [100, 100], [0, 100]]);
    expect(res!.anchorTypes).toEqual(['corner', 'corner', 'corner', 'corner']);
    // Edge 0 merged from old edge 0 (cp1=[15,-25]) and old edge 1 (cp2=[85,-25])
    const merged = res!.curvePoints.find(c => c.edgeIdx === 0);
    expect(merged).toBeDefined();
    expect(isCubicCurvePoint(merged!)).toBe(true);
    if (merged && isCubicCurvePoint(merged)) {
      expect(merged.ctrl).toEqual([15, -25]);
      expect(merged.ctrl2).toEqual([85, -25]);
    }
    // Old edge 3 re-indexed to edge 2
    expect(res!.curvePoints.find(c => c.edgeIdx === 2)).toBeDefined();
  });

  it('handles deleting vertex 0 by merging wrap-around edge to new last edge index', () => {
    const quad: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    const curves = [makeCubicCurvePoint(3, [-20, 70], [-20, 30])];
    const res = deletePieceVertex(quad, curves, undefined, 0);
    expect(res).not.toBeNull();
    expect(res!.polygon).toHaveLength(3);
    expect(res!.curvePoints.find(c => c.edgeIdx === 2)).toBeDefined();
  });
});

describe('retractPieceHandle', () => {
  it('retracts only the selected handle and keeps the opposite handle intact', () => {
    const poly: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    const curves = [makeCubicCurvePoint(0, [25, -40], [75, -40])];
    const types: ('corner' | 'smooth')[] = ['smooth', 'smooth', 'corner', 'corner'];

    const res = retractPieceHandle(poly, curves, types, 0, 'ctrl');
    expect(res.curvePoints).toHaveLength(1);
    const updated = res.curvePoints[0];
    expect(isCubicCurvePoint(updated)).toBe(true);
    if (isCubicCurvePoint(updated)) {
      expect(updated.ctrl).toEqual([0, 0]);
      expect(updated.ctrl2).toEqual([75, -40]);
    }
    expect(res.anchorTypes).toEqual(['corner', 'smooth', 'corner', 'corner']);
  });

  it('removes the CurvePoint completely once both handles are retracted', () => {
    const poly: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    const curves = [makeCubicCurvePoint(0, [0, 0], [75, -40])];
    const res = retractPieceHandle(poly, curves, undefined, 0, 'ctrl2');
    expect(res.curvePoints).toHaveLength(0);
  });
});

describe('bendEdgeMidpointToCubic', () => {
  it('promotes a straight edge midpoint drag to a cubic Bezier passing through targetMidpoint', () => {
    const A: [number, number] = [0, 0];
    const B: [number, number] = [100, 0];
    const target: [number, number] = [50, -30];
    const curve = bendEdgeMidpointToCubic(0, A, B, undefined, target);
    expect(isCubicCurvePoint(curve)).toBe(true);
    const [cp1, cp2] = curveToCubicControls(A, B, curve);
    const mid = evaluateCubicBezier(A, cp1, cp2, B, 0.5);
    expect(mid[0]).toBeCloseTo(50, 4);
    expect(mid[1]).toBeCloseTo(-30, 4);
  });

  it('bends an existing asymmetric cubic curve so its midpoint lands exactly on targetMidpoint', () => {
    const A: [number, number] = [0, 0];
    const B: [number, number] = [100, 0];
    const existing = makeCubicCurvePoint(0, [10, -20], [80, -40]);
    const target: [number, number] = [55, -50];
    const updated = bendEdgeMidpointToCubic(0, A, B, existing, target);
    expect(isCubicCurvePoint(updated)).toBe(true);
    const [cp1, cp2] = curveToCubicControls(A, B, updated);
    const mid = evaluateCubicBezier(A, cp1, cp2, B, 0.5);
    expect(mid[0]).toBeCloseTo(55, 4);
    expect(mid[1]).toBeCloseTo(-50, 4);
    // Relative vector between cp1 and cp2 is preserved (asymmetry intact)
    expect(cp2[0] - cp1[0]).toBeCloseTo(70, 4);
    expect(cp2[1] - cp1[1]).toBeCloseTo(-20, 4);
  });
});

describe('smoothPieceVertex', () => {
  it('synthesizes colinear cubic handles on a sharp corner without disturbing far corners', () => {
    const sq: [number, number][] = [[0, 0], [100, 0], [100, 100], [0, 100]];
    const res = smoothPieceVertex(sq, [], ['corner', 'corner', 'corner', 'corner'], 1);
    expect(res.anchorTypes[1]).toBe('smooth');
    const inEdge = res.curvePoints.find(c => c.edgeIdx === 0);
    const outEdge = res.curvePoints.find(c => c.edgeIdx === 1);
    expect(inEdge && isCubicCurvePoint(inEdge)).toBe(true);
    expect(outEdge && isCubicCurvePoint(outEdge)).toBe(true);
    if (inEdge && isCubicCurvePoint(inEdge) && outEdge && isCubicCurvePoint(outEdge)) {
      // Far ends remain collapsed at neighboring corners [0,0] and [100,100]
      expect(inEdge.ctrl).toEqual([0, 0]);
      expect(outEdge.ctrl2).toEqual([100, 100]);
      // Handles around [100,0] are strictly opposite along the (100,100)-(0,0) = (1,1) direction
      const vIn = [inEdge.ctrl2[0] - 100, inEdge.ctrl2[1] - 0];
      const vOut = [outEdge.ctrl[0] - 100, outEdge.ctrl[1] - 0];
      expect(vIn[0]).toBeCloseTo(-vOut[0], 4);
      expect(vIn[1]).toBeCloseTo(-vOut[1], 4);
      expect(Math.hypot(vOut[0], vOut[1])).toBeGreaterThan(20);
    }
  });
});
