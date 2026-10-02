// Start the built site on BASE_URL first. Playwright is a test-only, external tool:
// PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs node scripts/mobile-ui-check.mjs
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE || "playwright"
);
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROMIUM_PATH
    ? { executablePath: process.env.CHROMIUM_PATH }
    : {}),
});
const baseURL = process.env.BASE_URL || "http://127.0.0.1:4322";
const page = await browser.newPage({
  serviceWorkers: "block",
  viewport: { width: 320, height: 700 },
});
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const seed = () => [
  {
    id: 2,
    nom: "Dupont",
    prenom: "Élodie",
    identifiant: "123456",
    role: "member",
    cartes: { 2026: "A-123", 2025: "MI-47" },
  },
  {
    id: 3,
    nom: "Martin",
    prenom: "Anne",
    identifiant: "anne@example.com",
    role: "en attente",
    cartes: {},
  },
  ...Array.from({ length: 316 }, (_, i) => ({
    id: i + 4,
    nom: `Utilisateur${i}`,
    prenom: "Test",
    identifiant: String(200000 + i),
    role: "verifier",
    cartes: {},
  })),
];
let users = seed();
let failRole = false,
  failLoad = false,
  failCard = false,
  role = "admin",
  unauthorized = false;
const calls = [];
await page.route("**/api/**", async (route) => {
  const req = route.request();
  const path = new URL(req.url()).pathname;
  const method = req.method();
  if (path === "/api/me")
    return route.fulfill({
      status: unauthorized ? 401 : 200,
      json: { id: 1, role, identifiant: "admin@example.com" },
    });
  if (path === "/api/admin/users")
    return route.fulfill({
      status: failLoad ? 503 : 200,
      json: failLoad ? {} : users,
    });
  if (path === "/api/admin/requests")
    return route.fulfill({ json: { registrations: [], cards: [] } });
  const match = path.match(/^\/api\/admin\/users\/(\d+)(.*)$/);
  assert.ok(match, `Unexpected endpoint ${path}`);
  const user = users.find((user) => user.id === Number(match[1]));
  const suffix = match[2];
  const body = req.postDataJSON();
  calls.push({ path, method, body });
  await new Promise((resolve) => setTimeout(resolve, 150));
  if (suffix === "/role") {
    if (failRole)
      return route.fulfill({
        status: 400,
        json: { error: "Impossible de rétrograder votre propre compte." },
      });
    user.role = body.role;
  } else if (suffix === "/annees") {
    if (failCard)
      return route.fulfill({
        status: 409,
        json: {
          error: "Ce numéro de carte est déjà utilisé pour cette année.",
        },
      });
    user.cartes[body.annee.split("-")[0]] = body.annee_code;
    return route.fulfill({ json: { ok: true, annee_code: body.annee_code } });
  } else if (suffix.startsWith("/annees/")) {
    assert.match(suffix, /^\/annees\/\d{4}$/);
    delete user.cartes[suffix.split("/")[2]];
  } else if (method === "DELETE")
    users = users.filter((item) => item.id !== user.id);
  else Object.assign(user, body);
  return route.fulfill({ json: { ok: true } });
});
const dialog = page.getByRole("dialog");
const button = (name) => dialog.getByRole("button", { name, exact: true });
async function ready() {
  await page.goto(`${baseURL}/admin/users/`);
  await page
    .getByText("318 utilisateurs affichés sur 318", { exact: true })
    .waitFor();
}
async function openFirst(width) {
  await page
    .getByRole("button", {
      name:
        width < 768
          ? "Ouvrir la fiche de Élodie Dupont"
          : "Gérer Élodie Dupont",
      exact: true,
    })
    .click();
  await dialog.waitFor();
}
async function noOverflow() {
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "Global horizontal overflow",
  );
  assert.ok(
    await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth),
    "Dialog horizontal overflow",
  );
}
async function actionVisible(name) {
  const box = await button(name).boundingBox();
  const height = await page.evaluate(() => visualViewport.height);
  assert.ok(
    box && box.height >= 44 && box.y >= 0 && box.y + box.height <= height + 1,
    `${name} must remain inside viewport with a 44px target`,
  );
}
try {
  for (const width of [320, 375, 390, 430, 768, 1440]) {
    await page.setViewportSize({ width, height: 800 });
    await ready();
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    if (width < 768) {
      await page.getByRole("button", { name: "Ouvrir le menu" }).click();
      assert.ok(
        await page
          .getByRole("link", { name: "Liste d'utilisateurs" })
          .isVisible(),
      );
      await page.keyboard.press("Escape");
      assert.equal(
        await page
          .getByRole("button", { name: "Ouvrir le menu" })
          .getAttribute("aria-expanded"),
        "false",
      );
    } else assert.equal(await page.locator("table:visible").count(), 1);
    await openFirst(width);
    await noOverflow();
    await actionVisible("Modifier le profil");
    await button("Modifier le profil").click();
    await actionVisible("Enregistrer");
    await actionVisible("Annuler");
    // Reduced height tests the same resize path used when a virtual keyboard opens.
    await page.setViewportSize({ width, height: 360 });
    await page.waitForFunction(
      () =>
        document.querySelector("dialog").getBoundingClientRect().height <= 360,
    );
    await actionVisible("Enregistrer");
    await actionVisible("Annuler");
    await noOverflow();
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press("Tab");
      assert.ok(
        await page.evaluate(() =>
          document.querySelector("dialog").contains(document.activeElement),
        ),
        "Focus escaped the dialog",
      );
    }
    await button("Annuler").click();
    await page.keyboard.press("Escape");
    assert.equal(await dialog.count(), 0);
    assert.ok(
      await page.evaluate(
        () =>
          document.activeElement?.getAttribute("aria-haspopup") === "dialog",
      ),
    );
    console.log(`PASS layout, keyboard-height simulation, focus: ${width}px`);
  }
  await page.setViewportSize({ width: 390, height: 800 });
  await ready();
  const search = page.getByRole("searchbox");
  await search.fill("dupont elodie");
  await page
    .getByText("1 utilisateurs affichés sur 318", { exact: true })
    .waitFor();
  await search.fill("123456");
  await page
    .getByText("1 utilisateurs affichés sur 318", { exact: true })
    .waitFor();
  await page.getByLabel("Rôle").selectOption("admin");
  await page
    .getByText("Aucun utilisateur ne correspond à cette recherche.")
    .waitFor();
  await page.getByRole("button", { name: "Effacer les filtres" }).click();
  await openFirst(390);
  await button("Modifier le profil").click();
  await dialog.getByLabel("Nom", { exact: true }).fill("Durand");
  await dialog.getByLabel("Rôle").selectOption("verifier");
  assert.equal(calls.length, 0, "Editing must not issue mutations");
  await button("Annuler").click();
  assert.equal(calls.length, 0, "Cancel must not save the role");
  await button("Modifier le profil").click();
  await dialog.getByLabel("Nom", { exact: true }).fill("Durand");
  await dialog.getByLabel("Rôle").selectOption("verifier");
  failRole = true;
  await button("Enregistrer").click();
  assert.ok(await button("Enregistrement…").isDisabled());
  await dialog
    .getByRole("alert")
    .filter({ hasText: "Identité enregistrée, mais rôle non modifié" })
    .waitFor();
  assert.equal(users[0].nom, "Durand");
  assert.equal(users[0].role, "member");
  failRole = false;
  await button("Enregistrer").click();
  await dialog
    .getByRole("status")
    .filter({ hasText: "Modifications enregistrées." })
    .waitFor();
  assert.equal(
    calls.filter((call) => call.path === "/api/admin/users/2").length,
    1,
    "Partial retry must only retry the role",
  );
  await button("+ Ajouter une carte").click();
  await dialog.getByLabel("Année académique").selectOption("2027");
  await dialog.getByLabel("Préfixe").selectOption("EA");
  await dialog.getByLabel("Numéro").fill("42");
  failCard = true;
  await button("Ajouter la carte").click();
  assert.ok(await button("Ajout…").isDisabled());
  await dialog.getByRole("alert").filter({ hasText: "déjà utilisé" }).waitFor();
  failCard = false;
  await button("Ajouter la carte").click();
  await dialog
    .getByRole("status")
    .filter({ hasText: "Carte EA-42 ajoutée" })
    .waitFor();
  assert.equal(users[0].cartes[2027], "EA-42");
  await dialog
    .getByRole("button", { name: "Modifier la carte EA-42 de 2027-2028" })
    .click();
  await dialog.getByLabel("Numéro").fill("43");
  await button("Mettre à jour la carte").click();
  await dialog
    .getByRole("status")
    .filter({ hasText: "Carte EA-43 mise à jour" })
    .waitFor();
  await dialog
    .getByRole("button", { name: "Supprimer la carte EA-43 de 2027-2028" })
    .click();
  await button("Annuler").click();
  assert.equal(users[0].cartes[2027], "EA-43");
  await dialog
    .getByRole("button", { name: "Supprimer la carte EA-43 de 2027-2028" })
    .click();
  await button("Supprimer").click();
  assert.ok(await button("Suppression…").isDisabled());
  await dialog
    .getByRole("status")
    .filter({ hasText: "Carte supprimée." })
    .waitFor();
  assert.equal(users[0].cartes[2027], undefined);
  await button("Fermer la fiche utilisateur").click();
  await page
    .getByRole("button", { name: "Ouvrir la fiche de Anne Martin" })
    .click();
  await button("Modifier le profil").click();
  await dialog.getByLabel("Prénom", { exact: true }).fill("Anna");
  await button("Enregistrer").click();
  await dialog.getByRole("status").waitFor();
  assert.equal(
    calls.find((call) => call.path === "/api/admin/users/3").body.identifiant,
    undefined,
    "Do not send unchanged email as member_id",
  );
  await button("Modifier le profil").click();
  await dialog.getByLabel("Identifiant", { exact: true }).fill("654321");
  await button("Enregistrer").click();
  await dialog.getByRole("status").waitFor();
  assert.equal(users[1].identifiant, "654321");
  await button("Supprimer l’utilisateur").click();
  await button("Supprimer").click();
  await page
    .getByRole("status")
    .filter({ hasText: "Utilisateur supprimé." })
    .waitFor();
  assert.equal(users.length, 317);
  await search.fill("123456");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exporter en Excel" }).click();
  const download = await downloadPromise;
  const exported = await readFile(await download.path(), "utf8");
  assert.match(download.suggestedFilename(), /^utilisateurs-.*\.xls$/);
  assert.ok(
    exported.includes("Durand") && exported.includes("Utilisateur315"),
    "Export must keep all users, not just filtered results",
  );
  console.log(
    "PASS search, filters, explicit/partial save, identifiers, cards, confirmations, deletion, export",
  );

  // PWA prompt remains in flow and survives Astro client-side navigation.
  await page.evaluate(() => {
    const event = new Event("beforeinstallprompt", { cancelable: true });
    event.prompt = async () => {};
    event.userChoice = Promise.resolve({ outcome: "dismissed" });
    window.dispatchEvent(event);
  });
  assert.equal(
    await page
      .locator(".pwa-install")
      .evaluate((el) => getComputedStyle(el).position),
    "static",
  );
  await page
    .getByRole("button", { name: "Ouvrir la fiche de Élodie Durand" })
    .click();
  assert.equal(await page.locator(".pwa-install").isVisible(), false);
  await button("Fermer la fiche utilisateur").click();
  await page.getByRole("button", { name: "Plus tard" }).click();
  assert.equal(await page.locator(".pwa-install").isVisible(), false);
  await page.getByRole("button", { name: "Ouvrir le menu" }).click();
  await page.getByRole("link", { name: "Admin", exact: true }).click();
  await page
    .getByRole("link", { name: "Voir la liste des utilisateurs" })
    .click();
  await page.getByText("317 utilisateurs affichés sur 317").waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Ouvrir le menu" })
      .getAttribute("aria-expanded"),
    "false",
  );
  assert.equal(await page.locator(".pwa-install").isVisible(), false);
  failLoad = true;
  await page.reload();
  await page.getByRole("alert").waitFor();
  failLoad = false;
  await page.getByRole("button", { name: "Réessayer" }).click();
  await page.getByText("317 utilisateurs affichés sur 317").waitFor();
  users = [];
  await page.reload();
  await page.getByText("Aucun utilisateur pour le moment.").waitFor();
  role = "member";
  await page.goto(`${baseURL}/admin/users/`);
  await page.waitForURL((url) => url.pathname === "/");
  unauthorized = true;
  await page.goto(`${baseURL}/admin/users/`);
  await page.waitForURL((url) => url.pathname.startsWith("/login"));
  assert.deepEqual(errors, [], "Browser runtime errors");
  console.log(
    "PASS PWA, navigation, retry, empty state, admin guard; no browser runtime errors",
  );
} finally {
  await browser.close();
}
