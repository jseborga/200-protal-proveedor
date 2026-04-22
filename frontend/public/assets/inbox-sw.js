// Service Worker minimal para Web Push del Inbox (5.5).
// Recibe eventos push y muestra una Notification nativa; en click navega al inbox.

self.addEventListener('push', (event) => {
    let payload = {};
    try {
        payload = event.data ? event.data.json() : {};
    } catch (_) {
        payload = { title: 'Inbox', body: (event.data && event.data.text()) || 'Nuevo mensaje' };
    }
    const title = payload.title || 'Inbox — Nuevo mensaje';
    const options = {
        body: payload.body || '',
        icon: '/assets/icon-192.png',
        badge: '/assets/icon-192.png',
        tag: payload.session_id ? `inbox-${payload.session_id}` : 'inbox',
        data: {
            url: payload.url || '/#inbox',
            session_id: payload.session_id || null,
        },
        renotify: true,
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const target = (event.notification.data && event.notification.data.url) || '/#inbox';
    event.waitUntil((async () => {
        const allClients = await self.clients.matchAll({
            type: 'window', includeUncontrolled: true,
        });
        // Enfocar una pestana existente si la hay
        for (const c of allClients) {
            if ('focus' in c) {
                try { await c.focus(); } catch (_) {}
                try { c.postMessage({ type: 'inbox-open-session', session_id: event.notification.data?.session_id || null }); } catch (_) {}
                return;
            }
        }
        // Si no hay pestana, abrir una nueva
        if (self.clients.openWindow) {
            await self.clients.openWindow(target);
        }
    })());
});
