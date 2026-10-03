// Service worker of the installed app «Арена» (outside Telegram only).
//
// The app shell opens at once from the phone: index.html comes from the cache and is refreshed
// in the background (the next launch gets a new release), the hashed bundles in /assets/ never
// change and are kept. The game's pictures (smiles, cards, backs, tables) are kept too: an
// installed app on iPhone hardly keeps its HTTP cache, so without this every smile picker and
// every launch downloaded them again and they showed up blank for a moment. Avatars come from
// the phone at once and are refreshed in the background. /api and /ws always go to the server.
// Without any network the app shows a friendly page instead of the browser's error.
const SHELL = 'arena-shell-v1';
const MEDIA = 'arena-media-v1';
const AVATARS = 'arena-avatars-v1';
const KEEP = [SHELL, MEDIA, AVATARS];
/** Pictures that never change at the same address (a changed one gets a new ?v=). */
const MEDIA_PATH = /^\/(emoji|cards|backs|table|icons)\//;
const MAX_MEDIA = 400;
const MAX_AVATARS = 300;
const PAGE = '/';
/** Old bundles from past releases are dropped beyond this many files. */
const MAX_ASSETS = 120;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) =>
  event.waitUntil(
    (async () => {
      for (const key of await caches.keys()) if (!KEEP.includes(key)) await caches.delete(key);
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

async function trim(cache, max) {
  const keys = await cache.keys();
  for (const old of keys.slice(0, Math.max(0, keys.length - max))) await cache.delete(old);
}

/** Smiles, cards, backs, tables: from the phone once fetched. */
async function media(request) {
  const cache = await caches.open(MEDIA);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok && res.status === 200) {
    await cache.put(request, res.clone());
    void trim(cache, MAX_MEDIA);
  }
  return res;
}

/** Avatars (ours and Telegram's): the kept one at once, a fresh one for next time. */
async function avatar(event) {
  const { request } = event;
  const cache = await caches.open(AVATARS);
  const hit = await cache.match(request);
  const fresh = fetch(request).then(async (res) => {
    // Telegram's pictures come «opaque» (another site): kept as they are.
    if (res.ok || res.type === 'opaque') {
      await cache.put(request, res.clone());
      void trim(cache, MAX_AVATARS);
    }
    return res;
  });
  if (hit) {
    event.waitUntil(fresh.catch(() => undefined));
    return hit;
  }
  return fresh;
}

const isTelegramPicture = (url) => url.hostname === 't.me' || url.hostname.endsWith('.telegram.org') || url.hostname.endsWith('.telesco.pe');

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    if (request.destination === 'image' && isTelegramPicture(url)) event.respondWith(avatar(event));
    return;
  }
  if (url.pathname.startsWith('/api/avatars/')) return event.respondWith(avatar(event));
  if (MEDIA_PATH.test(url.pathname)) return event.respondWith(media(request));
  if (request.mode === 'navigate') event.respondWith(page(event));
  else if (url.pathname.startsWith('/assets/')) event.respondWith(asset(request));
});
