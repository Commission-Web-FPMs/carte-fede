import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";

const origin = "https://carte.test";
const stored = new Map();
const handlers = {};
let calls = 0;
let offline = false;
let status = 200;
let cacheUnavailable = false;
let cacheOpenGate;
const key = (request) => new URL(request.url || request, origin).href;
const cache = {
  async put(request, response) {
    await new Promise((resolve) => setImmediate(resolve));
    if (cacheUnavailable) throw new Error("Cache quota exceeded");
    stored.set(key(request), response);
  },
};

runInNewContext(await readFile(new URL("../public/sw.js", import.meta.url), "utf8"), {
  URL, Response,
  self: { location: { origin }, addEventListener: (name, handler) => { handlers[name] = handler; } },
  caches: {
    open: async () => { await cacheOpenGate; return cache; },
    match: async (request) => stored.get(key(request))?.clone(),
  },
  fetch: async () => {
    calls += 1;
    if (offline) throw new Error("Offline");
    return new Response("network", { status });
  },
});

async function request(path, mode = "cors", consumeResponse) {
  let response;
  const pending = [];
  handlers.fetch({
    request: { url: key(path), method: "GET", mode },
    respondWith: (promise) => { response = promise; },
    waitUntil: (promise) => pending.push(promise),
  });
  const result = await response;
  await consumeResponse?.(result);
  await Promise.all(pending);
  return result;
}

stored.set(key("/_astro/app.abc123.js"), new Response("cached"));
assert.equal(await (await request("/_astro/app.abc123.js")).text(), "cached");
assert.equal(calls, 0, "Fingerprinted assets must not revalidate on a cache hit");

assert.equal(await (await request("/_astro/app.new456.js")).text(), "network");
assert.equal(calls, 1);
assert.equal(await stored.get(key("/_astro/app.new456.js")).clone().text(), "network");
await request("/_astro/app.new456.js");
assert.equal(calls, 1, "Cache writes must finish before the worker becomes idle");

let releaseCacheOpen;
cacheOpenGate = new Promise((resolve) => { releaseCacheOpen = resolve; });
await request("/_astro/delayed-cache.js", "cors", async (response) => {
  assert.equal(await response.text(), "network");
  releaseCacheOpen();
});
assert.equal(await stored.get(key("/_astro/delayed-cache.js"))?.clone().text(), "network",
  "Cache writes must survive the browser consuming the response before caches.open resolves");
cacheOpenGate = undefined;

status = 404;
assert.equal((await request("/_astro/missing.js")).status, 404);
assert.equal(stored.has(key("/_astro/missing.js")), false);
status = 200;

stored.set(key("/api/me"), new Response("stale user"));
assert.equal(await (await request("/api/me")).text(), "network");
assert.equal(await stored.get(key("/api/me")).clone().text(), "stale user");
offline = true;
await assert.rejects(request("/api/me"), /Offline/);
offline = false;

stored.set(key("/app"), new Response("old page"));
assert.equal(await (await request("/app", "navigate")).text(), "network");
status = 503;
assert.equal((await request("/app", "navigate")).status, 503);
assert.equal(await stored.get(key("/app")).clone().text(), "network");
status = 200;
offline = true;
assert.equal(await (await request("/app", "navigate")).text(), "network");
stored.set(key("/offline.html"), new Response("offline page"));
assert.equal(await (await request("/unvisited", "navigate")).text(), "offline page");
offline = false;

stored.set(key("/manifest.webmanifest"), new Response("old manifest"));
assert.equal(await (await request("/manifest.webmanifest")).text(), "old manifest");
assert.equal(await stored.get(key("/manifest.webmanifest")).clone().text(), "network");

cacheUnavailable = true;
assert.equal(await (await request("/_astro/quota.js")).text(), "network");
assert.equal(stored.has(key("/_astro/quota.js")), false);
console.log("Service worker checks passed: immutable assets, cache persistence, errors, API, navigation, offline fallback.");
