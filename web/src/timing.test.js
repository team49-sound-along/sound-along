import { test } from "node:test";
import assert from "node:assert/strict";
import { findActiveIndex, seekSeconds, validateTiming } from "./timing.js";

const words = [
  { i: 0, text: "Hello", start_ms: 100, end_ms: 400 },
  { i: 1, text: "bright", start_ms: 450, end_ms: 800 },
  { i: 2, text: "world.", start_ms: 900, end_ms: 1300 },
];

test("before first word returns -1", () => assert.equal(findActiveIndex(words, 50), -1));
test("exact start selects word", () => assert.equal(findActiveIndex(words, 450), 1));
test("pause keeps earlier word active", () => assert.equal(findActiveIndex(words, 850), 1));
test("after last word keeps last", () => assert.equal(findActiveIndex(words, 99999), 2));
test("empty list is safe", () => assert.equal(findActiveIndex([], 10), -1));
test("seek converts to seconds and clamps", () => {
  assert.equal(seekSeconds(words, 2), 0.9);
  assert.equal(seekSeconds(words, 99), 0);
  assert.equal(seekSeconds(words, -1), 0);
});
test("validateTiming flags bad data", () => {
  assert.deepEqual(validateTiming(words), []);
  assert.equal(validateTiming([{ i: 0, start_ms: 5, end_ms: 1 }]).length, 1);
});
