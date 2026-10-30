import { afterAll, beforeAll, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { Miniflare } from 'miniflare';

const source = readFileSync('functions/glass/[[path]].js', 'utf8');
const script = `${source}\nexport default { fetch(request, env, ctx) {
  return onRequest({ request, env, waitUntil: ctx.waitUntil.bind(ctx) });
} };`;
const mf = new Miniflare({ modules: true, script, compatibilityDate: '2026-07-30', r2Buckets: ['GLASS_BUCKET'] });
const unbound = new Miniflare({ modules: true, script, compatibilityDate: '2026-07-30' });
const prefix = 'releases/8ad3855dc24cbcfc';
const paths = ['assets/catalog_images/test.jpg', 'assets/catalog_images/shipping_clean/test-final.png'];
// Store bytes and metadata in the actual local R2 runtime, not a mocked bucket.
const bytes = Uint8Array.from(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lH8AAAAASUVORK5CYII=', 'base64'));
const url = (path = paths[0]) => `https://vitrai.example/glass/${prefix}/${path}`;

beforeAll(async () => {
  const bucket = await mf.getR2Bucket('GLASS_BUCKET');
  for (const path of paths) await bucket.put(`${prefix}/${path}`, bytes, { httpMetadata: { contentType: 'image/png' } });
  await bucket.put('private.txt', 'not public');
});
afterAll(async () => { await Promise.all([mf.dispose(), unbound.dispose()]); });

test('serves R2 bytes and image metadata for original and cleaned paths', async () => {
  for (const path of paths) {
    const response = await mf.dispatchFetch(url(path));
    expect(response.status).toBe(200);
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(bytes);
    expect(response.headers.get('Content-Type')).toBe('image/png');
    expect(response.headers.get('Content-Length')).toBe(String(bytes.length));
    expect(response.headers.get('Cache-Control')).toContain('immutable');
    expect(response.headers.get('Access-Control-Allow-Origin')).toBe('*');
    expect(response.headers.get('Cross-Origin-Resource-Policy')).toBe('cross-origin');
  }
});

test('HEAD has the same metadata without a body; ETags permit revalidation', async () => {
  const response = await mf.dispatchFetch(url());
  await response.arrayBuffer();
  const head = await mf.dispatchFetch(url(), { method: 'HEAD' });
  expect(head.status).toBe(200);
  expect(await head.text()).toBe('');
  expect(head.headers.get('Content-Length')).toBe(String(bytes.length));
  const etag = response.headers.get('ETag')!;
  expect(head.headers.get('ETag')).toBe(etag);
  const conditional = await mf.dispatchFetch(url(), { headers: { 'If-None-Match': `W/${etag}` } });
  expect(conditional.status).toBe(304);
  expect(await conditional.text()).toBe('');
});

test('does not expose other bucket paths, releases or write methods', async () => {
  for (const path of ['private.txt', `${prefix}/assets/glass_swatch_registry.json`, `releases/0000000000000000/${paths[0]}`, `${prefix}/assets/catalog_images/missing.jpg`]) {
    const response = await mf.dispatchFetch(`https://vitrai.example/glass/${path}`);
    expect(response.status).toBe(404);
  }
  const write = await mf.dispatchFetch(url(), { method: 'PUT', body: 'replace' });
  expect(write.status).toBe(405);
  expect(write.headers.get('Allow')).toBe('GET, HEAD');
});

test('serves cached bytes without rereading R2 and ignores query parameters', async () => {
  const path = 'assets/catalog_images/cache-test.png';
  const bucket = await mf.getR2Bucket('GLASS_BUCKET');
  await bucket.put(`${prefix}/${path}`, bytes, { httpMetadata: { contentType: 'image/png' } });
  const first = await mf.dispatchFetch(url(path));
  await first.arrayBuffer();
  const storage = await mf.getCaches();
  await expect.poll(async () => Boolean(await storage.default.match(url(path)))).toBe(true);
  await bucket.delete(`${prefix}/${path}`);
  const cached = await mf.dispatchFetch(url(path) + '?tracking=ignored');
  expect(cached.status).toBe(200);
  expect(new Uint8Array(await cached.arrayBuffer())).toEqual(bytes);
});

test('reports a missing binding without caching the error', async () => {
  const response = await unbound.dispatchFetch(url());
  expect(response.status).toBe(503);
  expect(response.headers.get('Cache-Control')).toBe('no-store');
});

test('production routes only glass requests through the function', () => {
  const routes = JSON.parse(readFileSync('public/_routes.json', 'utf8'));
  expect(routes.include).toEqual(['/glass/*']);
  expect(routes.exclude).toEqual([]);
  expect(readFileSync('.env.production', 'utf8').trim()).toBe(`VITE_SWATCH_CDN_URL=/glass/${prefix}`);
});
