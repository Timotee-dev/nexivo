const CACHE = 'nexivo-v1';
const OFFLINE_URL = '/offline/';

const PRECACHE = [
  '/',
  '/events/',
  '/static/css/nexivo.css',
  '/static/js/nexivo.js',
  '/static/js/dashboard.js',
  '/static/img/nexivo_favicon.svg',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
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
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  // Skip API calls — always fetch fresh
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/')) return;

  e.respondWith(
    caches.match(e.request).then(cached => {
      const fetchFresh = fetch(e.request).then(res => {
        if (res.ok && url.origin === location.origin) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      });
      // Return cached immediately, update in background (stale-while-revalidate)
      return cached || fetchFresh;
    }).catch(() => {
      // Offline fallback for navigation requests
      if (e.request.mode === 'navigate') {
        return caches.match('/') || new Response('You are offline', { headers: { 'Content-Type': 'text/html' } });
      }
    })
  );
});
