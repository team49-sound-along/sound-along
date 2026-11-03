import { test } from "node:test";
import assert from "node:assert/strict";
import { completedLabel, emptyAnswer, getRaterId, isComplete, isUsableTrial, makeUuid, ratingErrorMessage, ratingPayload, resetSessionRaterId, trialLoadMessage } from "./listening.js";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const trial = { trialId: "t1", title: "x", prompt: "p", a: { token: "aaaaaaaaaaaaaaaa", url: "/data/ab/aaaaaaaaaaaaaaaa.mp3" }, b: { token: "bbbbbbbbbbbbbbbb", url: "/data/ab/bbbbbbbbbbbbbbbb.mp3" } };

test("uuid generator makes v4 uuids", () => {
  assert.match(makeUuid(), UUID);
  assert.notEqual(makeUuid(), makeUuid());
});
test("rater id is stored and reused", () => {
  const store = new Map();
  const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  const first = getRaterId(storage);
  assert.match(first, UUID);
  assert.equal(getRaterId(storage), first);
});
test("a malformed stored id is replaced", () => {
  const store = new Map([["soundalong.raterId", "junk"]]);
  const storage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  assert.match(getRaterId(storage), UUID);
});
test("falls back to one id per session when storage throws", () => {
  resetSessionRaterId();
  const storage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  const id = getRaterId(storage);
  assert.match(id, UUID);
  assert.equal(getRaterId(storage), id);
  assert.match(getRaterId(undefined), UUID);
});
test("submit needs both ratings and a preference", () => {
  assert.equal(isComplete(emptyAnswer()), false);
  assert.equal(isComplete({ ratingA: 3, ratingB: 4, preferred: null }), false);
  assert.equal(isComplete({ ratingA: 3, ratingB: 0, preferred: "a" }), false);
  assert.equal(isComplete({ ratingA: 3, ratingB: 4, preferred: "x" }), false);
  assert.equal(isComplete({ ratingA: 3, ratingB: 4, preferred: "tie" }), true);
});
test("payload uses trial tokens only", () => {
  assert.deepEqual(ratingPayload(trial, { ratingA: 2, ratingB: 5, preferred: "b" }, "rid"), {
    trialId: "t1", aToken: "aaaaaaaaaaaaaaaa", bToken: "bbbbbbbbbbbbbbbb", preferred: "b", ratingA: 2, ratingB: 5, raterId: "rid",
  });
});
test("usable trial check", () => {
  assert.equal(isUsableTrial(trial), true);
  assert.equal(isUsableTrial(null), false);
  assert.equal(isUsableTrial({ ...trial, b: { token: "x" } }), false);
});
test("friendly errors by status", () => {
  assert.match(ratingErrorMessage(429), /wait/i);
  assert.match(ratingErrorMessage(503), /turned off/i);
  assert.equal(ratingErrorMessage(400, "Tokens do not match"), "Tokens do not match");
  assert.match(ratingErrorMessage(400), /next clip/);
  assert.match(trialLoadMessage(503), /turned off/);
  assert.equal(trialLoadMessage(500, "boom"), "boom");
});
test("counter label", () => {
  assert.equal(completedLabel(1), "1 trial completed this session");
  assert.equal(completedLabel(3), "3 trials completed this session");
});
