import type { BoundingBox } from './types';

const BASE_URL = 'http://localhost:8000';

export async function encodeImage(imageUrl: string): Promise<string> {
  const res = await fetch(imageUrl);
  const blob = await res.blob();
  const form = new FormData();
  form.append('file', blob, 'image');
  const r = await fetch(`${BASE_URL}/encode`, { method: 'POST', body: form });
  if (!r.ok) throw new Error(`encode failed: ${r.status}`);
  const { image_id } = await r.json() as { image_id: string };
  return image_id;
}

export async function segment(
  imageId: string,
  box?: BoundingBox,
  points?: { x: number; y: number; label: number }[]
): Promise<[number, number][]> {
  const r = await fetch(`${BASE_URL}/segment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      image_id: imageId,
      box: box ? [box.x1, box.y1, box.x2, box.y2] : undefined,
      points: points
    }),
  });
  if (!r.ok) throw new Error(`segment failed: ${r.status}`);
  const { polygon } = await r.json() as { polygon: [number, number][] };
  return polygon;
}

export async function autoSegment(imageId: string, crop?: { top: number, bottom: number, left: number, right: number }): Promise<[number, number][][]> {
  const r = await fetch(`${BASE_URL}/auto_segment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      image_id: imageId,
      crop: crop ? [crop.top, crop.bottom, crop.left, crop.right] : undefined
    }),
  });
  if (!r.ok) throw new Error(`auto_segment failed: ${r.status}`);
  const { polygons } = await r.json() as { polygons: [number, number][][] };
  return polygons;
}
