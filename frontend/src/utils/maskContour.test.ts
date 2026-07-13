import { describe, expect, it } from 'vitest';
import { maskToPolygon } from './maskContour';

type Point = [number, number];

function logits(
  width: number,
  height: number,
  signedDistance: (x: number, y: number) => number,
): Float32Array {
  const data = new Float32Array(width * height);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) data[y * width + x] = signedDistance(x, y);
  }
  return data;
}

function area(polygon: Point[]): number {
  let sum = 0;
  for (let i = 0; i < polygon.length; i++) {
    const a = polygon[i];
    const b = polygon[(i + 1) % polygon.length];
    sum += a[0] * b[1] - b[0] * a[1];
  }
  return Math.abs(sum / 2);
}

function polygonFrom(data: Float32Array, width: number, height: number): Point[] {
  return maskToPolygon(data, width, height, {
    inputSize: width,
    scale: 1,
    padX: 0,
    padY: 0,
    origW: width,
    origH: height,
    minSimplifyPx: 0.75,
  });
}

describe('SAM mask contour extraction', () => {
  it('reduces a rectangle to a few accurate vertices', () => {
    const size = 80;
    const rectangle = logits(size, size, (x, y) =>
      Math.min(x - 12, 66 - x, y - 10, 52 - y)
    );
    const polygon = polygonFrom(rectangle, size, size);

    expect(polygon.length).toBeGreaterThanOrEqual(4);
    expect(polygon.length).toBeLessThanOrEqual(8);
    expect(Math.abs(area(polygon) - 54 * 42) / (54 * 42)).toBeLessThan(0.04);
  });

  it('preserves a smooth curved mask without excessive vertices', () => {
    const size = 128;
    const ellipse = logits(size, size, (x, y) =>
      1 - ((x - 64) / 42) ** 2 - ((y - 63) / 27) ** 2
    );
    const polygon = polygonFrom(ellipse, size, size);
    const expectedArea = Math.PI * 42 * 27;

    expect(polygon.length).toBeGreaterThanOrEqual(8);
    expect(polygon.length).toBeLessThanOrEqual(32);
    expect(Math.abs(area(polygon) - expectedArea) / expectedArea).toBeLessThan(0.04);
  });

  it('removes small logit ripples instead of turning them into visible corners', () => {
    const size = 120;
    const rippled = logits(size, size, (x, y) => {
      const wobble = 0.55 * Math.sin(y * 0.9);
      return Math.min(x - 18 - wobble, 101 - x + wobble, y - 14, 75 - y);
    });
    const polygon = polygonFrom(rippled, size, size);

    expect(polygon.length).toBeLessThanOrEqual(12);
    expect(area(polygon)).toBeGreaterThan(4700);
  });

  it('closes and clamps masks that touch a source-image edge', () => {
    const size = 96;
    const edgeTouching = logits(size, size, (x, y) =>
      Math.min(36 - x, x + 8, y - 20, 74 - y)
    );
    const polygon = polygonFrom(edgeTouching, size, size);

    expect(polygon.length).toBeGreaterThanOrEqual(4);
    expect(polygon.every(([x, y]) => x >= 0 && y >= 0)).toBe(true);
  });

  it('selects the largest closed region by area', () => {
    const size = 128;
    const twoIslands = logits(size, size, (x, y) => {
      const large = Math.min(x - 10, 72 - x, y - 12, 92 - y);
      const small = 12 - Math.hypot(x - 108, y - 30);
      return Math.max(large, small);
    });
    const polygon = polygonFrom(twoIslands, size, size);

    expect(area(polygon)).toBeGreaterThan(4500);
  });
});
