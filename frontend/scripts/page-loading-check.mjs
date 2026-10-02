// Serve frontend/dist at BASE_URL, then run with PLAYWRIGHT_MODULE and CHROMIUM_PATH.
import assert from "node:assert/strict";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const base = process.env.BASE_URL || "http://127.0.0.1:4322";
const browser = await chromium.launch({ headless: true,
  ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
const errors = [];

try {
  const page = await browser.newPage({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, serviceWorkers: "block" });
  page.on("pageerror", error => errors.push(error.message));
  // Keep this check independent of Google Fonts availability.
  await page.route("https://fonts.gstatic.com/**", route => route.abort());
  await page.route("**/api/me", route => route.fulfill({ status: 401, json: {} }));
  const html = await (await page.goto(base)).text();
  assert.equal((html.match(/rel="preload"[^>]*type="font/g) || []).length, 0);
  assert.ok(html.includes("Ouvrir le menu"), "Navigation must be present in the initial HTML");
  assert.ok(!html.includes("/_vercel/"), "Self-hosted builds must not request Vercel-only endpoints");
  const hero = page.locator("main img");
  await hero.evaluate(image => image.decode());
  assert.equal(await hero.getAttribute("loading"), "eager");
  assert.equal(await hero.getAttribute("fetchpriority"), "high");
  const mobileImage = await hero.evaluate(image => ({ src: image.currentSrc, width: image.naturalWidth }));
  const mobileBytes = (await (await page.request.get(mobileImage.src)).body()).length;
  assert.ok((await hero.getAttribute("srcset")).includes("768w"));
  await page.setViewportSize({ width: 1440, height: 900 });
  await hero.evaluate(image => image.decode());
  await page.waitForFunction(src => document.querySelector("main img").currentSrc !== src, mobileImage.src);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

  let sessionChecks = 0;
  await page.unroute("**/api/me");
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/me") {
      sessionChecks += 1;
      await new Promise(resolve => setTimeout(resolve, 200));
      return route.fulfill({ json: { role: "admin", identifiant: "999999" } });
    }
    if (path === "/api/admin/users") return route.fulfill({ json: [] });
    if (path === "/api/admin/requests") return route.fulfill({ json: { registrations: [], cards: [] } });
    return route.abort();
  });
  await page.goto(`${base}/admin/users/`);
  await page.getByText("Aucun utilisateur pour le moment.").waitFor();
  await page.getByText("Aucune demande en attente.").waitFor();
  assert.equal(sessionChecks, 1, "Menu and page must share their concurrent session check");
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ forcedFontPreloads: 0, mobileHeroBytes: mobileBytes, adminSessionRequests: sessionChecks }));
} finally {
  await browser.close();
}
