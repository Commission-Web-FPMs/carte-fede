// Run from frontend: node scripts/current-user-check.mjs
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { transpileModule, ModuleKind } from "typescript";

const source = await readFile(new URL("../src/lib/current-user.ts", import.meta.url), "utf8");
const { outputText } = transpileModule(source, { compilerOptions: { module: ModuleKind.ESNext } });
const { fetchCurrentUser } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
const originalFetch = globalThis.fetch;
let calls = 0;
let finish;
let fail;
globalThis.fetch = (url, options) => {
  assert.equal(url, "/api/me");
  assert.equal(options.credentials, "include");
  calls += 1;
  return new Promise((resolve, reject) => { finish = resolve; fail = reject; });
};

try {
  const first = fetchCurrentUser();
  const second = fetchCurrentUser();
  assert.equal(calls, 1, "Concurrent consumers share a request");
  finish(new Response(JSON.stringify({ role: "admin" })));
  const responses = await Promise.all([first, second]);
  assert.deepEqual(await Promise.all(responses.map(response => response.json())), [
    { role: "admin" }, { role: "admin" },
  ], "Each consumer can read its response body");

  const fresh = fetchCurrentUser();
  assert.equal(calls, 2, "Completed responses are never cached");
  finish(new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 }));
  const unauthorized = await fresh;
  assert.equal(unauthorized.status, 401);
  assert.equal(unauthorized.ok, false);
  assert.deepEqual(await unauthorized.json(), { error: "Unauthorized" });

  const errors = Promise.allSettled([fetchCurrentUser(), fetchCurrentUser()]);
  assert.equal(calls, 3);
  fail(new TypeError("Network unavailable"));
  for (const result of await errors) {
    assert.equal(result.status, "rejected");
    assert.equal(result.reason.message, "Network unavailable");
  }

  const retry = fetchCurrentUser();
  assert.equal(calls, 4, "Network failures do not poison subsequent requests");
  finish(new Response(JSON.stringify({ role: "member" })));
  assert.deepEqual(await (await retry).json(), { role: "member" });
  console.log("Current-user concurrency, independent bodies, statuses and retries passed.");
} finally {
  globalThis.fetch = originalFetch;
}
