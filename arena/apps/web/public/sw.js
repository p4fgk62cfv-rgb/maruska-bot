// Service worker of the installed app «Арена» (outside Telegram only).
//
// The app shell opens at once from the phone: index.html comes from the cache and is refreshed
// in the background (the next launch gets a new release), the hashed bundles in /assets/ never
// change and are kept. Everything live — /api, /ws, pictures — always goes to the server.
// Without any network the app shows a friendly page instead of the browser's error.
const SHELL = 'arena-shell-v1';
const PAGE = '/';
/** Old bundles from past releases are dropped beyond this many files. */
const MAX_ASSETS = 120;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) =>
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys()) if (key !== SHELL) await caches.delete(key);
      await self.clients.claim();
    })(),
  ),
);

const offline = () =>
  new Response(
    '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Арена</title>' +
      '<body style="margin:0;display:grid;place-items:center;height:100vh;background:#06301f;color:#fff;font-family:sans-serif;text-align:center">' +
      '<div><h2>Нет интернета</h2><p>Арене нужна сеть. Проверьте подключение и откройте снова.</p></div>',
    { headers: { 'content-type': 'text/html; charset=utf-8' } },
  );

async function page(event) {
  const cache = await caches.open(SHELL);
  const cached = await cache.match(PAGE);
  const before = cached ? await cached.clone().text() : null;
  const fresh = fetch(event.request).then(async (res) => {
    if (res.ok && res.headers.get('content-type')?.includes('text/html')) {
      await cache.put(PAGE, res.clone());
      // A new release came out since the cached shell: the page just opened may switch to it.
      if (before !== null && (await res.clone().text()) !== before) {
        for (const client of await self.clients.matchAll({ type: 'window' })) client.postMessage({ type: 'shell-updated' });
      }
    }
    return res;
  });
  if (cached) {
    // The cached shell now, the new one for the next launch.
    event.waitUntil(fresh.catch(() => undefined));
    return cached;
  }
  return fresh.catch(offline);
}

async function asset(request) {
  const cache = await caches.open(SHELL);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok) {
    await cache.put(request, res.clone());
    const keys = (await cache.keys()).filter((r) => new URL(r.url).pathname.startsWith('/assets/'));
    for (const old of keys.slice(0, Math.max(0, keys.length - MAX_ASSETS))) await cache.delete(old);
  }
  return res;
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.mode === 'navigate') event.respondWith(page(event));
  else if (url.pathname.startsWith('/assets/')) event.respondWith(asset(request));
});
