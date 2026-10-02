const CACHE_VERSION = "carte-fede-v3";
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const RUNTIME_CACHE = `${CACHE_VERSION}-runtime`;

const APP_SHELL = [
  "/",
  "/offline.html",
  "/manifest.webmanifest",
  "/favicon.svg",
  "/icon-192.png",
  "/icon-512.png",
  "/pwa-register.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== STATIC_CACHE && key !== RUNTIME_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

function fetchAndCache(request, event) {
  const response = fetch(request);
  // Persist in the background without delaying delivery or failing on a full cache.
  event.waitUntil(response.then((result) => {
    if (result.ok) {
      const copy = result.clone();
      return caches.open(RUNTIME_CACHE)
        .then((cache) => cache.put(request, copy));
    }
  }).catch(() => {}));
  return response;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(request));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetchAndCache(request, event)
        .catch(async () => {
          const cached = await caches.match(request);
          return cached || caches.match("/offline.html");
        })
    );
    return;
  }

  const cachedResponse = caches.match(request);
  const updatedResponse = cachedResponse.then((cached) => {
    // Astro fingerprints its build assets: their URL changes with their content.
    if (cached && url.pathname.startsWith("/_astro/")) return cached;
    return fetchAndCache(request, event).catch(() => cached || Response.error());
  });
  event.waitUntil(updatedResponse.then(() => {}));
  event.respondWith(cachedResponse.then((cached) => cached || updatedResponse));
});
