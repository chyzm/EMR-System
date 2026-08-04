const STATIC_CACHE = 'durielmedic-static-v4';
const PAGE_CACHE_PREFIX = 'durielmedic-pages-v4-';
const CONTEXT_CACHE = 'durielmedic-worker-context-v1';
const CONTEXT_URL = '/__durielmedic_worker_context__';
const CORE_ASSETS = [
  '/static/manifest.json',
  '/static/images/icon.svg',
  '/static/offline-app.js',
  '/static/offline-patient-workflow.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys
        .filter((key) => key.startsWith('durielmedic-offline-') || (key.startsWith('durielmedic-static-') && key !== STATIC_CACHE) || (key.startsWith('durielmedic-pages-') && !key.startsWith(PAGE_CACHE_PREFIX)))
        .map((key) => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

async function setContext(contextKey) {
  const cache = await caches.open(CONTEXT_CACHE);
  await cache.put(CONTEXT_URL, new Response(contextKey || ''));
}

async function getContext() {
  const response = await caches.match(CONTEXT_URL, { cacheName: CONTEXT_CACHE });
  return response ? response.text() : '';
}

async function pageCacheName() {
  const context = await getContext();
  return context ? `${PAGE_CACHE_PREFIX}${context}` : '';
}

self.addEventListener('message', (event) => {
  const message = event.data || {};
  if (message.type === 'SET_CONTEXT') {
    event.waitUntil(setContext(message.contextKey));
  } else if (message.type === 'CLEAR_CONTEXT') {
    event.waitUntil(setContext(''));
  } else if (message.type === 'WARM_PAGES') {
    event.waitUntil((async () => {
      const cacheName = await pageCacheName();
      if (!cacheName) return;
      const cache = await caches.open(cacheName);
      for (const url of message.urls || []) {
        try {
          const response = await fetch(url, { credentials: 'same-origin' });
          if (response.ok && !response.redirected) await cache.put(url, response);
        } catch (error) {
          // A later visit can populate this page.
        }
      }
    })());
  }
});

function isCacheablePage(url) {
  return url.pathname === '/patients/'
    || url.pathname === '/patients/add/'
    || url.pathname.startsWith('/patients/')
    || url.pathname.startsWith('/DurielMedicApp')
    || url.pathname.startsWith('/billing/');
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET' || !event.request.url.startsWith(self.location.origin)) return;
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/') || url.pathname.includes('/login') || url.pathname.includes('/logout')) return;

  if (url.pathname.startsWith('/static/')) {
    event.respondWith(caches.match(event.request).then((cached) => cached || fetch(event.request).then((response) => {
      if (response.ok) caches.open(STATIC_CACHE).then((cache) => cache.put(event.request, response.clone()));
      return response;
    })));
    return;
  }

  if (event.request.mode === 'navigate' && isCacheablePage(url)) {
    event.respondWith((async () => {
      const cacheName = await pageCacheName();
      try {
        const response = await fetch(event.request);
        if (response.ok && cacheName && !response.redirected) {
          const cache = await caches.open(cacheName);
          await cache.put(event.request, response.clone());
        }
        return response;
      } catch (error) {
        if (cacheName) {
          const cache = await caches.open(cacheName);
          const exact = await cache.match(event.request, { ignoreSearch: true });
          if (exact) return exact;
          const patientList = await cache.match('/patients/');
          if (patientList) return patientList;
        }
        return new Response(
          '<!doctype html><meta name="viewport" content="width=device-width"><title>Offline</title><main style="font-family:system-ui;padding:2rem"><h1>Page unavailable offline</h1><p>Return to a clinic page that was opened while online.</p></main>',
          { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        );
      }
    })());
  }
});
