/* 课程表 Demo · Service Worker
   策略：应用外壳缓存优先（cache-first），保证离线可用；
   导航请求统一回退到 index.html。 */
var CACHE = 'schedule-demo-v7';
var ASSETS = [
  './',
  './index.html',
  './css/style.css',
  './js/store.js',
  './js/app.js',
  './js/particles.js',
  './assets/night-blossom.jpg',
  './manifest.webmanifest',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-512.png',
  './icons/apple-touch-icon.png'
];

self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(ASSETS);
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) {
        if (key !== CACHE) { return caches.delete(key); }
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  if (e.request.method !== 'GET') { return; }
  /* 课表快照必须实时：不缓存，避免"点了同步还是旧数据" */
  if (new URL(e.request.url).pathname.endsWith('/schedule.json')) { return; }
  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then(function (hit) {
      if (hit) { return hit; }
      return fetch(e.request).then(function (res) {
        /* 同源静态资源顺手入缓存，下次离线可用 */
        if (res && res.ok && new URL(e.request.url).origin === self.location.origin) {
          var copy = res.clone();
          caches.open(CACHE).then(function (cache) { cache.put(e.request, copy); });
        }
        return res;
      }).catch(function () {
        /* 导航请求离线回退到外壳 */
        if (e.request.mode === 'navigate') { return caches.match('./index.html'); }
      });
    })
  );
});
