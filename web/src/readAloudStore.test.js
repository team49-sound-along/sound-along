import { test } from "node:test";
import assert from "node:assert/strict";
import { addResult, clearResults, loadResults, resultsKey } from "./readAloudStore.js";

const memory = () => {
  const data = new Map();
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)), removeItem: (k) => data.delete(k), data };
};
const blocked = { getItem: () => { throw new Error("x"); }, setItem: () => { throw new Error("x"); }, removeItem: () => { throw new Error("x"); } };
const summary = { total: 20, read: 18, skipped: 2, retried: 1, heardDifferently: 0 };

test("a saved session is read back with counts only", () => {
  const s = memory();
  const saved = addResult("p1", { ...summary, heard: "secret words" }, 1000, s);
  assert.deepEqual(saved, [{ at: 1000, total: 20, read: 18, skipped: 2, retried: 1 }]);
  assert.deepEqual(loadResults("p1", s), saved);
  assert.equal(s.data.get(resultsKey("p1")).includes("secret"), false);
});

test("only the last ten sessions are kept, and passages are separate", () => {
  const s = memory();
  for (let i = 0; i < 12; i += 1) addResult("p1", summary, i, s);
  assert.equal(loadResults("p1", s).length, 10);
  assert.equal(loadResults("p1", s)[0].at, 2);
  assert.deepEqual(loadResults("p2", s), []);
});

test("clearing removes the results", () => {
  const s = memory();
  addResult("p1", summary, 1, s);
  assert.equal(clearResults("p1", s), true);
  assert.deepEqual(loadResults("p1", s), []);
});

test("corrupt or blocked storage gives an empty list and never throws", () => {
  const s = memory();
  s.setItem(resultsKey("p1"), "{not json");
  assert.deepEqual(loadResults("p1", s), []);
  s.setItem(resultsKey("p1"), JSON.stringify({ sessions: [{ at: 1, total: -4 }, "x"] }));
  assert.deepEqual(loadResults("p1", s), []);
  assert.deepEqual(loadResults("p1", blocked), []);
  assert.deepEqual(addResult("p1", summary, 1, blocked), []);
  assert.equal(clearResults("p1", blocked), false);
  assert.deepEqual(addResult("p1", { total: "x" }, 1, s), []);
});
