// Only the immutable public glass release is exposed, never arbitrary bucket keys.
const imagePath = /^\/glass\/(releases\/8ad3855dc24cbcfc\/assets\/catalog_images\/(?:[a-zA-Z0-9_-]+\/)*[a-zA-Z0-9_.-]+\.(?:jpg|jpeg|png|gif|webp))$/;

function notModified(request, etag) {
  return (request.headers.get('If-None-Match') || '').split(',')
    .some(value => value.trim() === '*' || value.trim().replace(/^W\//, '') === etag);
}

export async function onRequest({ request, env, waitUntil }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response('Method not allowed', { status: 405, headers: { Allow: 'GET, HEAD' } });
  }
  const url = new URL(request.url);
  const match = imagePath.exec(url.pathname);
  if (!match) return new Response('Not found', { status: 404 });
  if (!env.GLASS_BUCKET) {
    return new Response('Glass storage is not configured', { status: 503, headers: { 'Cache-Control': 'no-store' } });
  }

  // Ignore query strings so tracking parameters do not fragment immutable assets.
  const cacheKey = new Request(url.origin + url.pathname);
  const cached = await caches.default.match(cacheKey);
  if (cached) {
    if (notModified(request, cached.headers.get('ETag'))) {
      return new Response(null, { status: 304, headers: cached.headers });
    }
    return request.method === 'HEAD' ? new Response(null, cached) : cached;
  }

  const object = request.method === 'HEAD'
    ? await env.GLASS_BUCKET.head(match[1])
    : await env.GLASS_BUCKET.get(match[1]);
  if (!object) return new Response('Not found', { status: 404 });
  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set('ETag', object.httpEtag);
  headers.set('Content-Length', String(object.size));
  headers.set('Cache-Control', 'public, max-age=31536000, immutable');
  headers.set('X-Content-Type-Options', 'nosniff');
  // Pages' _headers does not apply to Function responses. Anonymous CORS also
  // keeps saved glass URLs readable by canvas on previews and local development.
  headers.set('Access-Control-Allow-Origin', '*');
  headers.set('Cross-Origin-Resource-Policy', 'cross-origin');
  if (notModified(request, object.httpEtag)) return new Response(null, { status: 304, headers });

  const response = new Response(request.method === 'HEAD' ? null : object.body, { headers });
  if (request.method === 'GET') waitUntil(caches.default.put(cacheKey, response.clone()));
  return response;
}
