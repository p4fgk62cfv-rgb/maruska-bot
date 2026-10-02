// Service worker of the installed app «Арена». It caches nothing: the game is live and always
// comes from the server. Its fetch handler only makes the app installable and shows a friendly
// page when there is no network at all.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (event) => {
  if (event.request.mode !== 'navigate') return;
  event.respondWith(
    fetch(event.request).catch(
      () =>
        new Response(
          '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Арена</title>' +
            '<body style="margin:0;display:grid;place-items:center;height:100vh;background:#06301f;color:#fff;font-family:sans-serif;text-align:center">' +
            '<div><h2>Нет интернета</h2><p>Арене нужна сеть. Проверьте подключение и откройте снова.</p></div>',
          { headers: { 'content-type': 'text/html; charset=utf-8' } },
        ),
    ),
  );
});
