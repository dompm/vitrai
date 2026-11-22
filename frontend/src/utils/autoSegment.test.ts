import { describe, expect, it } from 'vitest';
import {
  classifyGlassColor,
  isValidRefinedPolygon,
  proposeStainedGlassCells,
  resolveGlassSheetForColor,
} from './autoSegment';
import { DEFAULT_PROJECT } from '../defaultProject';
import type { GlassSheet } from '../types';

describe('classifyGlassColor & resolveGlassSheetForColor', () => {
  it('classifies backlit suncatcher and window piece colors into the 9 built-in glass families', () => {
    // Orange suncatcher pieces (orange-pattern.jpg)
    expect(classifyGlassColor('#fd8402').label).toBe('Orange');
    expect(classifyGlassColor('#afcc05').label).toBe('Green');
    expect(classifyGlassColor('#afd405').label).toBe('Green');
    expect(classifyGlassColor('#99f96f').label).toBe('Green');

    // Stained-glass window photo pieces
    expect(classifyGlassColor('#ececed').label).toBe('White');
    expect(classifyGlassColor('#f0f0f3').label).toBe('White');
    expect(classifyGlassColor('#e1d0b1').label).toBe('Amber');
    expect(classifyGlassColor('#aed5b7').label).toBe('Green');

    // Remaining built-in glass families
    expect(classifyGlassColor('#159c98').label).toBe('Turquoise');
    expect(classifyGlassColor('#1e52c8').label).toBe('Cobalt Blue');
    expect(classifyGlassColor('#c41820').label).toBe('Red');
    expect(classifyGlassColor('#d85a88').label).toBe('Pink');
    expect(classifyGlassColor('#121413').label).toBe('Black');
  });

  it('reuses existing matching project sheets and creates missing sheets from DEFAULT_GLASS_ASSETS', () => {
    const sheets: GlassSheet[] = structuredClone(DEFAULT_PROJECT.sheets);
    expect(sheets.map(s => s.label)).toEqual(['Green', 'Orange']);

    // Green and Orange pieces reuse DEFAULT_PROJECT sheets without adding duplicates
    const greenRes = resolveGlassSheetForColor('#afcc05', sheets, sheets[0].id);
    expect(greenRes.newSheet).toBeUndefined();
    expect(greenRes.sheetId).toBe(sheets[0].id);

    const orangeRes = resolveGlassSheetForColor('#fd8402', sheets, sheets[0].id);
    expect(orangeRes.newSheet).toBeUndefined();
    expect(orangeRes.sheetId).toBe(sheets[1].id);

    // Amber piece creates a new Amber glass sheet from DEFAULT_GLASS_ASSETS
    const amberRes = resolveGlassSheetForColor('#e1d0b1', sheets, sheets[0].id);
    expect(amberRes.newSheet).toBeDefined();
    expect(amberRes.newSheet?.label).toBe('Amber');
    expect(amberRes.newSheet?.imageUrl).toBe('/assets/glass/amber.jpg');
    sheets.push(amberRes.newSheet!);

    // Second Amber piece reuses the newly added Amber sheet
    const amberRes2 = resolveGlassSheetForColor('#d89c2a', sheets, sheets[0].id);
    expect(amberRes2.newSheet).toBeUndefined();
    expect(amberRes2.sheetId).toBe(amberRes.sheetId);
  });
});

describe('proposeStainedGlassCells & isValidRefinedPolygon', () => {
  it('discovers enclosed stained-glass cells, rejects wrapping background, and samples accurate colors', () => {
    const W = 160;
    const H = 160;
    const data = new Uint8ClampedArray(W * H * 4);

    const setPixel = (x: number, y: number, r: number, g: number, b: number) => {
      const i = (y * W + x) * 4;
      data[i] = r;
      data[i + 1] = g;
      data[i + 2] = b;
      data[i + 3] = 255;
    };

    // 1. Fill exterior photo background (light warm gray wrapping all 4 sides)
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        setPixel(x, y, 235, 228, 222);
      }
    }

    // 2. Draw outer dark solder frame [30..130, 30..130] and vertical center divider at x = 79..81
    for (let y = 30; y <= 130; y++) {
      for (let x = 30; x <= 130; x++) {
        const onOuterBorder = x < 34 || x > 126 || y < 34 || y > 126;
        const onDivider = x >= 79 && x <= 81;
        if (onOuterBorder || onDivider) {
          setPixel(x, y, 22, 22, 24);
        } else if (x < 79) {
          // Left pane: Orange glass (#f07810)
          setPixel(x, y, 240, 120, 16);
        } else {
          // Right pane: Green glass (#20b840)
          setPixel(x, y, 32, 184, 64);
        }
      }
    }

    // Add a tiny white specular glare spot inside the left pane to verify median color robustness
    for (let y = 60; y <= 63; y++) {
      for (let x = 50; x <= 53; x++) {
        setPixel(x, y, 255, 255, 255);
      }
    }

    const cells = proposeStainedGlassCells(data, W, H, {
      cropLeft: 100,
      cropTop: 200,
      cropW: 320,
      cropH: 320,
    });

    expect(cells).toHaveLength(2);
    const [leftCell, rightCell] = cells.sort((a, b) => a.box[0] - b.box[0]);

    expect(classifyGlassColor(leftCell.color).label).toBe('Orange');
    expect(classifyGlassColor(rightCell.color).label).toBe('Green');

    // Verify coordinates are mapped into crop offset (100, 200) with 2x scale (320 / 160)
    expect(leftCell.point[0]).toBeGreaterThan(160);
    expect(leftCell.point[0]).toBeLessThan(260);
    expect(rightCell.point[0]).toBeGreaterThan(260);
    expect(rightCell.point[0]).toBeLessThan(360);

    // Adjacent cells should meet across the vertical divider near pattern x = 100 + 80 * 2 = 260
    expect(Math.abs(leftCell.box[2] - 260)).toBeLessThanOrEqual(4);
    expect(Math.abs(rightCell.box[0] - 260)).toBeLessThanOrEqual(4);

    // Validate refined polygon checks
    expect(isValidRefinedPolygon(leftCell.polygon, leftCell)).toBe(true);
    expect(
      isValidRefinedPolygon(
        [
          [0, 0],
          [10, 0],
          [10, 10],
        ],
        leftCell,
      ),
    ).toBe(false);
  });
});
