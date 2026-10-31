// LiquidityDissection service worker: shows the trade notifications (Web Push from the server, so they arrive with the
// app closed) and opens the app on the pair when one is clicked.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('push', e => {
  let m = {};
  try { m = e.data ? e.data.json() : {}; } catch { m = { body: e.data ? e.data.text() : '' }; }
  e.waitUntil(self.registration.showNotification(m.title || 'LiquidityDissection', {
    body: m.body || '', tag: m.tag || 'ld', renotify: true, requireInteraction: true,
    icon: '/brand/icon-192.png', badge: '/brand/favicon-64.png', data: { symbol: m.symbol || '' },
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const symbol = (e.notification.data && e.notification.data.symbol) || '';
  e.waitUntil((async () => {
    const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    const win = all.find(c => new URL(c.url).origin === self.location.origin);
    if (win) {
      await win.focus();
      win.postMessage({ type: 'ld-open-symbol', symbol });
      return;
    }
    await self.clients.openWindow(symbol ? `/?symbol=${encodeURIComponent(symbol)}` : '/');
  })());
});
