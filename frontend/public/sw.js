const CACHE_NAME = 'apu-mkt-v5';
const PRECACHE = [
    '/',
    '/assets/app.js',
    '/assets/app.css',
    '/icon.svg',
];

self.addEventListener('install', (e) => {
    e.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(PRECACHE))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (e) => {
    const url = new URL(e.request.url);

    // API requests: network only
    if (url.pathname.startsWith('/api/')) {
        e.respondWith(fetch(e.request));
        return;
    }

    // App assets (JS/CSS/HTML): network first, fall back to cache
    // This ensures users always get the latest version after deploy
    if (url.pathname === '/' || url.pathname.startsWith('/assets/')) {
        e.respondWith(
            fetch(e.request).then(response => {
                if (response.ok) {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(e.request, clone));
                }
                return response;
            }).catch(() => caches.match(e.request).then(cached => cached || caches.match('/')))
        );
        return;
    }

    // Other static assets (icons, images): cache first
    e.respondWith(
        caches.match(e.request).then(cached => {
            if (cached) return cached;
            return fetch(e.request).then(response => {
                if (response.ok && response.type === 'basic') {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(e.request, clone));
                }
                return response;
            });
        }).catch(() => caches.match('/'))
    );
});
