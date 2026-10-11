import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
test('Untrusted registration names and verification errors cannot become HTML', () => {
 const source=fs.readFileSync('src/pages/verif/index.astro','utf8');
 const helper=source.slice(source.indexOf('  function escapeHTML'), source.indexOf('  function renderOK'));
 const context={};vm.createContext(context);vm.runInContext(helper,context);
 for (const payload of ['<img src=x onerror="alert(1)">', '<script>alert(1)</script>', "<svg/onload='alert(1)'>"])
  assert.ok(!context.escapeHTML(payload).includes('<'));
 assert.equal(context.escapeHTML('A & B'),'A &amp; B');
 for (const field of ['j.user.prenom','j.user.nom','j.periode','j.code','msg'])
  assert.ok(source.includes('${escapeHTML('+field+')}'));
 assert.ok(source.includes('TEST DEV'));
});
