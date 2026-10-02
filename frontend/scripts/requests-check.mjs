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
  await register.route("**/api/card-payment", route => route.fulfill({ json: { annee: year, beneficiary: "Fédé", iban: "BE68539007547034", bic: "", amount: "12.50", communication_prefix: "Carte Fédé" } }));
  await register.route("**/api/card-payment/qr", route => route.fulfill({ contentType: "image/png", body: Buffer.from("89504e470d0a1a0a", "hex") }));
  await register.goto(`${base}/register/`);
  assert.ok(await register.getByRole("heading", { name: "Demander la création d’un compte" }).isVisible());
  assert.ok(await register.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await register.getByLabel("Nom", { exact: true }).fill("Dupont");
  await register.getByLabel("Prénom", { exact: true }).fill("Élodie");
  await register.getByText(`DUPONT Élodie – Carte Fédé ${year}-${year + 1}`).waitFor();
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

  registration = null;
  await register.reload();
  await register.getByLabel("Inscription non-UMONS").check();
  assert.ok(await register.getByLabel("Adresse email").isVisible());
  assert.equal(await register.getByLabel("Matricule UMONS (6 chiffres)").isVisible(), false);
  await register.getByLabel("Nom", { exact: true }).fill("Bernard");
  await register.getByLabel("Prénom", { exact: true }).fill("Alice");
  await register.getByLabel("Adresse email").fill("alice@example.org");
  await register.getByLabel("Je suis étudiant·e en BAC1 Polytech").check();
  await register.getByText("Aucun paiement immédiat n’est demandé.", { exact: false }).waitFor();
  await register.getByLabel("Mot de passe (8 caractères minimum)").fill("secret-1234");
  await register.getByLabel("Confirmer le mot de passe").fill("secret-1234");
  await register.getByRole("button", { name: "Envoyer ma demande" }).click();
  await register.getByText("Demande envoyée. Un administrateur doit la valider avant votre première connexion.").waitFor();
  assert.equal(registration.email, "alice@example.org");
  assert.equal(registration.free_card_requested, true);
  assert.equal("member_id" in registration, false);
  assert.ok(await register.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

  const admin = await browser.newPage({ viewport: { width: 390, height: 800 }, serviceWorkers: "block" });
  admin.on("pageerror", error => errors.push(error.message));
  const decisions = [];
  const queue = { registrations: [
    { id: "r1", nom: "Dupont", prenom: "Élodie", member_id: "123456", email: null, expires_at: "2026-10-30T00:00:00" },
    { id: "r2", nom: "Bernard", prenom: "Alice", member_id: null, email: "alice@example.org", expires_at: "2026-10-30T00:00:00" },
  ],
    cards: [{ id: "c1", nom: "Martin", prenom: "Anne", identifiant: "654321", annee: year, status: "payment_required", free_card: false }] };
  await admin.route("**/api/**", route => {
    const url = new URL(route.request().url()).pathname;
    if (url === "/api/me") return route.fulfill({ json: { role: "admin", identifiant: "999999" } });
    if (url === "/api/admin/users") return route.fulfill({ json: [] });
    if (url === "/api/admin/requests") return route.fulfill({ json: queue });
    if (url.startsWith("/api/admin/registrations/") || url.startsWith("/api/admin/card-requests/")) {
      decisions.push({ url, body: route.request().postDataJSON() });
      if (url.includes("/registrations/")) queue.registrations = queue.registrations.filter(item => item.id !== url.split("/").at(-2));
      else if (url.endsWith("/payment-received")) queue.cards[0].status = "pending";
      else queue.cards = [];
      return route.fulfill({ json: { ok: true } });
    }
    return route.abort();
  });
  await admin.goto(`${base}/admin/users/`);
  await admin.getByRole("heading", { name: "Demandes à valider" }).waitFor();
  await admin.getByText("Email alice@example.org", { exact: false }).waitFor();
  assert.ok(await admin.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await admin.getByRole("button", { name: "Valider le compte" }).first().click();
  await admin.getByText("Demande validée.").first().waitFor();
  assert.equal(decisions[0].url, "/api/admin/registrations/r1/approve");
  assert.equal(decisions[0].url, "/api/admin/registrations/r1/approve");
  await admin.getByRole("button", { name: "Valider le compte" }).click();
  await admin.getByText("Email alice@example.org", { exact: false }).waitFor({ state: "hidden" });
  assert.equal(decisions[1].url, "/api/admin/registrations/r2/approve");
  assert.equal(decisions[1].url, "/api/admin/registrations/r2/approve");
  assert.ok(await admin.getByRole("button", { name: "Attribuer la carte" }).isDisabled());
  await admin.getByRole("button", { name: "Paiement reçu" }).click();
  await admin.getByRole("button", { name: "Attribuer la carte" }).click();
  await admin.getByText("Aucune demande en attente.").waitFor();
  assert.equal(decisions[2].url, "/api/admin/card-requests/c1/payment-received");
  assert.equal(decisions[3].url, "/api/admin/card-requests/c1/approve");
  assert.equal(decisions[3].body.prefix, "A");

  const settingsPage = await browser.newPage({ viewport: { width: 320, height: 700 }, serviceWorkers: "block" });
  settingsPage.on("pageerror", error => errors.push(error.message));
  let savedSettings = null;
  await settingsPage.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/me") return route.fulfill({ json: { role: "admin" } });
    if (path === "/api/admin/card-payment" && route.request().method() === "PUT") {
      savedSettings = route.request().postDataJSON();
      return route.fulfill({ json: { ...savedSettings, annee: year } });
    }
    if (path === "/api/admin/card-payment") return route.fulfill({ json: { annee: year, beneficiary: "", iban: "", bic: "", amount: "", communication_prefix: "Carte Fédé" } });
    return route.abort();
  });
  await settingsPage.goto(`${base}/admin/settings/`);
  await settingsPage.getByLabel("Nom du bénéficiaire").fill("Fédé Polytech");
  await settingsPage.getByLabel("IBAN").fill("BE68539007547034");
  await settingsPage.getByLabel("Montant de la carte Fédé (€)").fill("12.50");
  await settingsPage.getByRole("button", { name: "Enregistrer les paramètres" }).click();
  await settingsPage.getByText("Paramètres enregistrés.").waitFor();
  assert.equal(savedSettings.iban, "BE68539007547034");
  assert.ok(await settingsPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth));

  const member = await browser.newPage({ viewport: { width: 375, height: 700 }, serviceWorkers: "block" });
  member.on("pageerror", error => errors.push(error.message));
  let requestedYear = null;
  let failRequests = false;
  let releaseCards;
  const requestsStarted = new Promise(resolve => { releaseCards = resolve; });
  await member.route("**/api/**", async route => {
    const url = new URL(route.request().url()).pathname;
    if (url === "/api/me") return route.fulfill({ json: { role: "member", identifiant: "654321", nom: "Martin", prenom: "Anne" } });
    if (url === "/api/card-payment") return route.fulfill({ json: { annee: year, beneficiary: "Fédé", iban: "BE68539007547034", bic: "", amount: "12.50", communication_prefix: "Carte Fédé" } });
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
  await member.getByText("Demande envoyée : paiement requis, puis validation par un administrateur.").waitFor();
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
