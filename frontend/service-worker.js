const CACHE_NAME = 'mindmate-v1';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './about.html',
  './admin-dashboard.html',
  './ai-chat.html',
  './assessment.html',
  './booking.html',
  './chat-room.html',
  './choose-support.html',
  './contact.html',
  './dashboard.html',
  './faq.html',
  './login.html',
  './privacy.html',
  './specialist-console.html',
  './specialist-dashboard.html',
  './specialist-profile.html',
  './specialists.html',
  './store.html',
  './terms.html',
  './video-call.html',
  './404.html',
  './static/css/main.css',
  './static/css/components.css',
  './static/js/utils.js',
  './static/icon-192.png',
  './static/icon-512.png',
  './manifest.json'
];

// Install Event
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

// Activate Event
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch Event
self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);

  // Bypass API calls or non-GET requests
  if (event.request.method !== 'GET' || requestUrl.pathname.includes('/api')) {
    return;
  }

  // Network-First, Cache-Fallback for navigate / HTML pages
  if (event.request.mode === 'navigate' || requestUrl.pathname.endsWith('.html')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const clonedResponse = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clonedResponse);
          });
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Cache-First, Network-Fallback for static assets (CSS, JS, icons)
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).then((response) => {
        const clonedResponse = response.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, clonedResponse);
        });
        return response;
      });
    })
  );
});
