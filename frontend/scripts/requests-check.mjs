// Serve frontend/dist at BASE_URL, then run with PLAYWRIGHT_MODULE and CHROMIUM_PATH.
import assert from "node:assert/strict";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const browser = await chromium.launch({ headless: true,
  ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
const base = process.env.BASE_URL || "http://127.0.0.1:4322";
const year = new Date().getFullYear() - (new Date().getMonth() < 7 ? 1 : 0);
const errors = [];

try {
  const register = await browser.newPage({ viewport: { width: 320, height: 700 }, serviceWorkers: "block" });
  register.on("pageerror", error => errors.push(error.message));
  let registration = null;
  await register.route("**/api/auth/register", route => {
    registration = route.request().postDataJSON();
    return route.fulfill({ status: 202, json: { ok: true } });
  });
  await register.goto(`${base}/register/`);
  assert.ok(await register.getByRole("heading", { name: "Demander la création d’un compte" }).isVisible());
  assert.ok(await register.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await register.getByLabel("Nom", { exact: true }).fill("Dupont");
  await register.getByLabel("Prénom", { exact: true }).fill("Élodie");
  await register.getByLabel("Matricule UMONS (6 chiffres)").fill("123456");
  await register.getByLabel("Mot de passe (8 caractères minimum)").fill("secret-1234");
  await register.getByLabel("Confirmer le mot de passe").fill("wrong-1234");
  await register.getByRole("button", { name: "Envoyer ma demande" }).click();
  assert.equal(registration, null);
  await register.getByLabel("Confirmer le mot de passe").fill("secret-1234");
  await register.getByRole("button", { name: "Envoyer ma demande" }).click();
  await register.getByText("Demande envoyée. Un administrateur doit la valider avant votre première connexion.").waitFor();
  assert.equal(registration.member_id, "123456");
  assert.equal(await register.locator("#signupForm").isVisible(), false);

  const admin = await browser.newPage({ viewport: { width: 390, height: 800 }, serviceWorkers: "block" });
  admin.on("pageerror", error => errors.push(error.message));
  const decisions = [];
  const queue = { registrations: [{ id: "r1", nom: "Dupont", prenom: "Élodie", member_id: "123456", expires_at: "2026-10-30T00:00:00" }],
    cards: [{ id: "c1", nom: "Martin", prenom: "Anne", identifiant: "654321", annee: year }] };
  await admin.route("**/api/**", route => {
    const url = new URL(route.request().url()).pathname;
    if (url === "/api/me") return route.fulfill({ json: { role: "admin", identifiant: "999999" } });
    if (url === "/api/admin/users") return route.fulfill({ json: [] });
    if (url === "/api/admin/requests") return route.fulfill({ json: queue });
    if (url.startsWith("/api/admin/registrations/") || url.startsWith("/api/admin/card-requests/")) {
      decisions.push({ url, body: route.request().postDataJSON() });
      if (url.includes("/registrations/")) queue.registrations = [];
      else queue.cards = [];
      return route.fulfill({ json: { ok: true } });
    }
    return route.abort();
  });
  await admin.goto(`${base}/admin/users/`);
  await admin.getByRole("heading", { name: "Demandes à valider" }).waitFor();
  assert.ok(await admin.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await admin.getByLabel("Ajouter une carte lors de la validation").check();
  await admin.getByRole("button", { name: "Valider le compte" }).click();
  await admin.getByText("Demande validée.").first().waitFor();
  assert.equal(decisions[0].url, "/api/admin/registrations/r1/approve");
  assert.equal(decisions[0].body.add_card, true);
  await admin.getByRole("button", { name: "Attribuer la carte" }).click();
  await admin.getByText("Aucune demande en attente.").waitFor();
  assert.equal(decisions[1].url, "/api/admin/card-requests/c1/approve");
  assert.equal(decisions[1].body.prefix, "A");

  const member = await browser.newPage({ viewport: { width: 375, height: 700 }, serviceWorkers: "block" });
  member.on("pageerror", error => errors.push(error.message));
  let requestedYear = null;
  let failRequests = false;
  let releaseCards;
  const requestsStarted = new Promise(resolve => { releaseCards = resolve; });
  await member.route("**/api/**", async route => {
    const url = new URL(route.request().url()).pathname;
    if (url === "/api/me") return route.fulfill({ json: { role: "member", identifiant: "654321" } });
    if (failRequests && url === "/api/memberships") {
      // Cards cannot finish before the independent requests endpoint has started.
      await requestsStarted;
      return route.fulfill({ json: [{ annee: year, annee_code: "A-123" }] });
    }
    if (failRequests && url === "/api/memberships/requests") {
      releaseCards();
      return route.abort();
    }
    if (url === "/api/memberships" || url === "/api/memberships/requests" && route.request().method() === "GET") return route.fulfill({ json: [] });
    if (url === "/api/memberships/requests") {
      requestedYear = route.request().postDataJSON().annee;
      return route.fulfill({ status: 202, json: { ok: true } });
    }
    return route.abort();
  });
  await member.goto(`${base}/cartes/`);
  await member.getByRole("button", { name: "Demander cette carte" }).click();
  await member.getByText("Demande envoyée : un administrateur doit la valider.").waitFor();
  assert.equal(requestedYear, year);
  assert.ok(await member.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  failRequests = true;
  await member.reload();
  await member.getByText("A - 123", { exact: true }).waitFor();
  await member.getByText("Impossible de charger vos demandes de carte. Réessayez en rechargeant la page.").waitFor();
  assert.deepEqual(errors, []);
  console.log("PASS inscription, validations admin, demande de carte et chargement parallèle résilient");
} finally {
  await browser.close();
}
