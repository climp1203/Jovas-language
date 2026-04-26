// Jovas Language — Service Worker
// Caches playground for offline use

const CACHE = 'jovas-v1';
const PRECACHE = [
  '/Jovas-language/playground.html',
  '/Jovas-language/index.html',
  '/Jovas-language/manifest.json',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(PRECACHE.map(u => new Request(u, {cache: 'reload'}))))
      .catch(() => {}) // don't fail install if assets unavailable
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  // Only cache GET requests to our own origin
  if (e.request.method !== 'GET') return;
  if (!e.request.url.includes('climp1203.github.io') && !e.request.url.includes('localhost')) return;

  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(response => {
        if (!response || response.status !== 200) return response;
        const clone = response.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return response;
      }).catch(() => caches.match('/Jovas-language/playground.html'));
    })
  );
});
