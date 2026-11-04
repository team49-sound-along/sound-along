import { test } from "node:test";
import assert from "node:assert/strict";
import { attemptFor, restartAttempt, signatureOf } from "./quizSession.js";

test("the same questions resume the same attempt", () => {
  const a = attemptFor("d1", ["q1", "q2", "q3"]);
  a.index = 2;
  assert.equal(attemptFor("d1", ["q1", "q2", "q3"]).index, 2);
});

test("when the published question ids change, the saved attempt is reset", () => {
  const a = attemptFor("d2", ["q1", "q2", "q3"]);
  a.index = 2;
  a.answers = { q1: 0 };
  a.finished = true;
  const b = attemptFor("d2", ["q1", "q2"]);
  assert.notEqual(b, a);
  assert.deepEqual([b.index, b.finished, b.answers], [0, false, {}]);
});

test("a different count or a replaced id also resets; order alone does not", () => {
  attemptFor("d3", ["a", "b"]).index = 1;
  assert.equal(attemptFor("d3", ["b", "a"]).index, 1);
  assert.equal(attemptFor("d3", ["a", "c"]).index, 0);
  attemptFor("d3", ["a", "c"]).index = 1;
  assert.equal(attemptFor("d3", ["a", "c", "d"]).index, 0);
});

test("an index past the end is never kept", () => {
  const a = attemptFor("d4", ["a", "b", "c"]);
  a.index = 5;
  assert.equal(attemptFor("d4", ["a", "b", "c"]).index, 0);
});

test("restart keeps the signature so the next resume works", () => {
  attemptFor("d5", ["a", "b"]);
  const r = restartAttempt("d5", ["a", "b"]);
  r.index = 1;
  assert.equal(attemptFor("d5", ["a", "b"]).index, 1);
  assert.equal(signatureOf(["b", "a"]), signatureOf(["a", "b"]));
});
