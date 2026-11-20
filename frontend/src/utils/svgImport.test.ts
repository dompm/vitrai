import { describe, expect, it } from 'vitest';
import {
  extractRegionsFromMask,
  parseSvgDimensions,
  parseSvgVectors,
  parseTransform,
} from './svgImport';

describe('svgImport', () => {
  it('derives physical scale from mm and in root dimensions', () => {
    const svgMm = `<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="100mm" viewBox="0 0 200 100"></svg>`;
    const dims = parseSvgDimensions(svgMm);
    expect(dims.viewBox.width).toBe(200);
    expect(dims.viewBox.height).toBe(100);
    expect(dims.physicalScale).toEqual({ pxPerUnit: 1, unit: 'mm' });

    const parsed = parseSvgVectors(svgMm);
    expect(parsed.canvasWidth).toBe(1200);
    expect(parsed.canvasHeight).toBe(600);
    expect(parsed.scale.unit).toBe('mm');
    expect(parsed.scale.pxPerUnit).toBeCloseTo(6, 5);

    const svgIn = `<svg xmlns="http://www.w3.org/2000/svg" width="10in" height="10in" viewBox="0 0 1000 1000"></svg>`;
    const parsedIn = parseSvgVectors(svgIn);
    expect(parsedIn.scale.unit).toBe('in');
    expect(parsedIn.scale.pxPerUnit).toBeCloseTo(120, 5);
  });

  it('composes SVG transform matrices', () => {
    expect(parseTransform('translate(10, 20) scale(2)')).toEqual([2, 0, 0, 2, 10, 20]);
  });

  it('extracts closed vector shapes with native quadratic curves and filters white backgrounds', () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
        <rect x="0" y="0" width="200" height="200" fill="#ffffff" stroke="none" />
        <rect id="top-left" x="10" y="10" width="80" height="80" fill="#d97706" stroke="#111" />
        <circle id="sun" cx="150" cy="50" r="35" fill="#f59e0b" />
        <g transform="translate(10, 110)">
          <path id="petal-q" d="M 0 0 Q 40 -20 80 0 L 80 70 L 0 70 Z" fill="#2563eb" />
        </g>
        <path id="petal-c" d="M 110 110 C 130 90 170 90 190 110 L 190 180 L 110 180 Z" fill="#10b981" />
      </svg>
    `;
    const res = parseSvgVectors(svg);
    expect(res.recommendedMode).toBe('shapes');
    expect(res.pieces).toHaveLength(4);

    const rectPiece = res.pieces.find(p => p.label === 'top-left');
    expect(rectPiece?.polygon).toHaveLength(4);
    expect(rectPiece?.curvePoints).toBeUndefined();

    const circlePiece = res.pieces.find(p => p.label === 'sun');
    expect(circlePiece?.polygon).toHaveLength(8);
    expect(circlePiece?.curvePoints).toHaveLength(8);

    const quadPiece = res.pieces.find(p => p.label === 'petal-q');
    expect(quadPiece?.curvePoints).toHaveLength(1);

    const cubicPiece = res.pieces.find(p => p.label === 'petal-c');
    expect(cubicPiece?.curvePoints).toHaveLength(2);
  });

  it('classifies open linework, unfilled overlapping shapes, and expanded lead webs as lines', () => {
    const openSvg = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
        <rect x="10" y="10" width="180" height="180" fill="none" stroke="#000" stroke-width="3" />
        <line x1="100" y1="10" x2="100" y2="190" stroke="#000" stroke-width="3" />
        <line x1="10" y1="100" x2="190" y2="100" stroke="#000" stroke-width="3" />
      </svg>
    `;
    const openRes = parseSvgVectors(openSvg);
    expect(openRes.recommendedMode).toBe('lines');
    expect(openRes.stats.openCount).toBe(2);

    const overlapSvg = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
        <circle cx="80" cy="100" r="60" fill="none" stroke="#000" stroke-width="2" />
        <circle cx="120" cy="100" r="60" fill="none" stroke="#000" stroke-width="2" />
        <circle cx="100" cy="70" r="60" fill="none" stroke="#000" stroke-width="2" />
      </svg>
    `;
    const overlapRes = parseSvgVectors(overlapSvg);
    expect(overlapRes.stats.anyHasFill).toBe(false);
    expect(overlapRes.stats.overlapRatio).toBeGreaterThan(1.3);
    expect(overlapRes.recommendedMode).toBe('lines');

    const leadWebSvg = `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
        <path fill="#000" fill-rule="evenodd" d="
          M 10 10 L 190 10 L 190 190 L 10 190 Z
          M 20 20 L 95 20 L 95 95 L 20 95 Z
          M 105 20 L 180 20 L 180 95 L 105 95 Z
          M 20 105 L 95 105 L 95 180 L 20 180 Z
          M 105 105 L 180 105 L 180 180 L 105 180 Z
        " />
      </svg>
    `;
    const leadWebRes = parseSvgVectors(leadWebSvg);
    expect(leadWebRes.stats.isLeadWeb).toBe(true);
    expect(leadWebRes.recommendedMode).toBe('lines');
  });

  it('extracts enclosed window panes from a binary linework mask', () => {
    const W = 200;
    const H = 200;
    const mask = new Uint8Array(W * H);
    const drawWall = (x0: number, y0: number, x1: number, y1: number) => {
      for (let y = y0; y <= y1; y++) {
        for (let x = x0; x <= x1; x++) {
          mask[y * W + x] = 1;
        }
      }
    };
    drawWall(20, 20, 180, 23);
    drawWall(20, 177, 180, 180);
    drawWall(20, 20, 23, 180);
    drawWall(177, 20, 180, 180);
    drawWall(98, 20, 102, 180);
    drawWall(20, 98, 180, 102);

    const pieces = extractRegionsFromMask(mask, W, H, {
      targetWidth: 1000,
      targetHeight: 1000,
      simplifyEpsilon: 1.5,
    });

    expect(pieces).toHaveLength(4);
    for (const p of pieces) {
      expect(p.polygon.length).toBeGreaterThanOrEqual(4);
      expect(p.polygon.length).toBeLessThanOrEqual(8);
    }
  });
});
