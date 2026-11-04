// Keeps the app shell available offline so the window opens instantly. Never caches /api: your data
// is always fetched fresh and never stored by the browser.
const SHELL = "claudebot-shell-v1";
const FILES = ["/", "/static/app.js", "/static/app.css", "/static/icon.svg", "/manifest.webmanifest"];

self.addEventListener("install", e => e.waitUntil(caches.open(SHELL).then(c => c.addAll(FILES)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(k => k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || !FILES.includes(url.pathname)) return;
  // Network first, so updates show up right away; the cached copy only when offline.
  e.respondWith(fetch(e.request).then(res => {
    const copy = res.clone();
    caches.open(SHELL).then(c => c.put(e.request, copy));
    return res;
  }).catch(() => caches.match(e.request)));
});
