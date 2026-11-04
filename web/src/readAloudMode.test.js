import { test } from "node:test";
import assert from "node:assert/strict";
import { loadMode, saveMode, MODE_KEY } from "./readAloudMode.js";

const memory = (initial = {}) => {
  const data = { ...initial };
  return { getItem: (k) => data[k] ?? null, setItem: (k, v) => { data[k] = v; }, data };
};

test("keep going is the default, and odd saved values are ignored", () => {
  assert.equal(loadMode(memory()), "keepGoing");
  assert.equal(loadMode(memory({ [MODE_KEY]: "banana" })), "keepGoing");
  assert.equal(loadMode(null), "keepGoing");
});

test("a saved choice is remembered, and only known modes are saved", () => {
  const s = memory();
  assert.equal(saveMode("stop", s), true);
  assert.equal(loadMode(s), "stop");
  assert.equal(saveMode("nope", s), false);
  assert.equal(loadMode(s), "stop");
});

test("blocked storage never throws", () => {
  const blocked = { getItem() { throw new Error("no"); }, setItem() { throw new Error("no"); } };
  assert.equal(loadMode(blocked), "keepGoing");
  assert.equal(saveMode("stop", blocked), false);
});
