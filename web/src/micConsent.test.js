import { test } from "node:test";
import assert from "node:assert/strict";
import { CONSENT_KEY, giveMicConsent, hasMicConsent, withdrawMicConsent } from "./micConsent.js";

const memory = () => {
  const data = new Map();
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)), removeItem: (k) => data.delete(k), data };
};
const blocked = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }, removeItem: () => { throw new Error("blocked"); } };

test("no consent until it is given, and only the exact value counts", () => {
  const s = memory();
  assert.equal(hasMicConsent(s), false);
  s.setItem(CONSENT_KEY, "true");
  assert.equal(hasMicConsent(s), false);
  assert.equal(giveMicConsent(s), true);
  assert.equal(hasMicConsent(s), true);
});

test("consent can be withdrawn", () => {
  const s = memory();
  giveMicConsent(s);
  assert.equal(withdrawMicConsent(s), true);
  assert.equal(hasMicConsent(s), false);
});

test("blocked storage never throws and never reports consent", () => {
  assert.equal(hasMicConsent(blocked), false);
  assert.equal(giveMicConsent(blocked), false);
  assert.equal(withdrawMicConsent(blocked), false);
  assert.equal(giveMicConsent(null), false);
  assert.equal(hasMicConsent(null), false);
});
