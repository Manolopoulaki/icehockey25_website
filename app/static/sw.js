/* Level 1 PWA: installability — precache manifest + icons for Chrome checks. */
self.addEventListener('install', function (event) {
  var origin = self.location.origin;
  var precache = [
    origin + '/manifest.webmanifest',
    origin + '/static/icons/pwa-192.png',
    origin + '/static/icons/pwa-512.png',
  ];
  event.waitUntil(
    caches.open('sport-predictions-pwa-v1').then(function (cache) {
      return cache.addAll(precache);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', function (event) {
  if (event.request.method !== 'GET') {
    return;
  }
  var url = new URL(event.request.url);
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    return;
  }
  event.respondWith(fetch(event.request));
});
