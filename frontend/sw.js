// Minimal service worker so the phone page can be installed (PWA).
// It caches the page shell only. Live data always comes from the backend.
const CACHE = 'wattwise-v1';
const SHELL = ['app.html', 'css/app.css', 'js/common.js', 'js/app.js', 'icon.svg', 'manifest.webmanifest'];

self.addEventListener('install', e => e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL))));
self.addEventListener('activate', e => e.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))));
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/')) return; // never cache live data or approvals
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
