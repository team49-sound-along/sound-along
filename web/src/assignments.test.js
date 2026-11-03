import { test } from "node:test";
import assert from "node:assert/strict";
import { soundAlongAllowed, replaceAssignment, removeAssignment, prependAssignment, filterPassages } from "./assignments.js";

const list = [
  { id: "a", passageId: "p1", soundAlong: false },
  { id: "b", passageId: "p2", soundAlong: true },
];
test("student text-only when all assignments off", () => {
  assert.equal(soundAlongAllowed(list, "p1", "student"), false);
  assert.equal(soundAlongAllowed(list, "p2", "student"), true);
  assert.equal(soundAlongAllowed(list, "p3", "student"), true);
});
test("teacher always allowed", () => assert.equal(soundAlongAllowed(list, "p1", "teacher"), true));
test("updates are immutable", () => {
  const next = replaceAssignment(list, { id: "a", passageId: "p1", soundAlong: true });
  assert.equal(list[0].soundAlong, false);
  assert.equal(next[0].soundAlong, true);
  assert.equal(removeAssignment(list, "a").length, 1);
  assert.equal(prependAssignment(list, { id: "c" })[0].id, "c");
  assert.equal(list.length, 2);
});
test("filterPassages is case-insensitive", () => {
  const ps = [{ title: "Ocean Life" }, { title: "Space" }];
  assert.equal(filterPassages(ps, " ocean ").length, 1);
  assert.equal(filterPassages(ps, "").length, 2);
});
