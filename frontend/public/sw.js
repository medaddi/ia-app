// LiquidityDissection service worker: shows the trade notifications and opens the app on the pair when one is clicked.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

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
    await self.clients.openWindow(`/?symbol=${encodeURIComponent(symbol)}`);
  })());
});
