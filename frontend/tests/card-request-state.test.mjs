import test from 'node:test';
import assert from 'node:assert/strict';
import { cardRequestState } from '../src/lib/card-request-state.mjs';
test('academic years remain independent and existing cards override old requests', () => {
  assert.equal(cardRequestState([{annee:2025}], [{annee:2026,status:'pending'}],2026),'pending');
  assert.equal(cardRequestState([{annee:2026}], [{annee:2026,status:'rejected'}],2026),'card');
  assert.equal(cardRequestState([{annee:2025}], [],2026),'absent');
});
test('only absent and explicitly rejected requests permit a new submission', () => {
  for (const [status,expected] of [['pending','pending'],['payment_required','payment'],['rejected','rejected'],['approved','blocked'],['unexpected','blocked']]) {
    assert.equal(cardRequestState([], [{annee:2026,status}],2026),expected);
  }
});
