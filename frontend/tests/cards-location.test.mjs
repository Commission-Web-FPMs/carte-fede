import assert from "node:assert/strict";import { readFileSync } from "node:fs";
const home=readFileSync(new URL("../src/pages/index.astro",import.meta.url),"utf8");
const request=readFileSync(new URL("../src/components/CardRequest.tsx",import.meta.url),"utf8");
const cards=readFileSync(new URL("../src/components/app/AppCartes.tsx",import.meta.url),"utf8");
assert.ok(home.includes("CardRequest"));assert.ok(!home.includes("AppCartes"));assert.ok(!request.includes("/api/qr/"));assert.ok(!request.includes("<img"));assert.ok(request.includes("Voir mes cartes"));
assert.ok(cards.includes("/api/qr/${item.annee}.png"));assert.ok(cards.includes("CardRequestPanel"));
