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

import { wordSlice } from "./timing.js";
test("wordSlice pads the word and converts to seconds", () => {
  assert.deepEqual(wordSlice(words, 1), { startSec: 0.41, endSec: 0.88 });
  assert.deepEqual(wordSlice(words, 1, { padBeforeMs: 0, padAfterMs: 0 }), { startSec: 0.45, endSec: 0.8 });
});
test("wordSlice clamps the start at zero", () => {
  assert.equal(wordSlice([{ i: 0, start_ms: 10, end_ms: 200 }], 0).startSec, 0);
});
test("wordSlice rejects bad index and unaligned words", () => {
  assert.equal(wordSlice(words, -1), null);
  assert.equal(wordSlice(words, 3), null);
  assert.equal(wordSlice(words, 1.5), null);
  assert.equal(wordSlice([{ i: 0, start_ms: 100, end_ms: 200, aligned: false }], 0), null);
  assert.notEqual(wordSlice([{ i: 0, start_ms: 100, end_ms: 200, aligned: true }], 0), null);
});
