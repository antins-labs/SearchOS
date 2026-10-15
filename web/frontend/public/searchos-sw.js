// Only notifications: private reports and authenticated responses are never cached.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('push', event => {
  let data = {};
  try { data = event.data?.json() || {}; } catch { /* Show a generic reminder. */ }
  event.waitUntil(self.registration.showNotification('SearchOS', {
    body: data.body || '你有一条新的任务消息。', icon: '/mobile-icon-192.png',
    tag: String(data.tag || 'searchos'), data: { url: safeTarget(data.url) },
  }));
});
function safeTarget(value) {
  try { const url = new URL(value || '/m?view=inbox', self.location.origin); if (url.origin === self.location.origin && url.pathname === '/m') return url.href; } catch {}
  return self.location.origin + '/m?view=inbox';
}
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = safeTarget(event.notification.data?.url);
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async clients => {
    for (const client of clients) {
      if (new URL(client.url).origin === self.location.origin && new URL(client.url).pathname.startsWith('/m')) {
        await client.navigate(url); return client.focus();
      }
    }
    return self.clients.openWindow(url);
  }));
});
