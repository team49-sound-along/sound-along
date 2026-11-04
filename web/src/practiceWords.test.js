import { test } from "node:test";
import assert from "node:assert/strict";
import { wordsToPractice, addAllToMyWords, countNew } from "./practiceWords.js";
import { createReadAlong, feed } from "./readAloud.js";
import { emptyState, toggleStar } from "./practice.js";

const words = "I like it because it is fun today.".split(" ").map((text, i) => ({ i, text }));

function skippedBecause() {
  const out = feed(createReadAlong(words), { id: 1, transcript: "I like it it is fun today", isFinal: true });
  return out.state;
}

test("lists the flagged words once, in passage order, as practice keys", () => {
  assert.deepEqual(wordsToPractice(skippedBecause(), words), [{ index: 3, text: "because", key: "because" }]);
});

test("a word flagged twice, or the same word at two places, is listed once", () => {
  const state = { skippedEver: [3, 3, 7], differsEver: [3, 4], targets: [] };
  const list = wordsToPractice(state, [...words.slice(0, 7), { i: 7, text: "Because," }]);
  assert.deepEqual(list.map((w) => w.key), ["because", "it"]);
});

test("nothing flagged, or odd input, gives an empty list", () => {
  assert.deepEqual(wordsToPractice(createReadAlong(words), words), []);
  assert.deepEqual(wordsToPractice(null, words), []);
  assert.deepEqual(wordsToPractice({ skippedEver: [99, -1, "x"], differsEver: [] }, words), []);
  assert.deepEqual(wordsToPractice({ skippedEver: [0], differsEver: [] }, null), []);
  assert.deepEqual(wordsToPractice({ skippedEver: [0] }, [{ i: 0, text: "..." }]), []);
});

test("add all stars every word and never un-stars one already there", () => {
  const start = toggleStar(emptyState(), "because", 1000);
  const next = addAllToMyWords(start, [{ key: "because" }, { key: "island" }], 5000);
  assert.deepEqual(Object.keys(next.words).sort(), ["because", "island"]);
  assert.deepEqual(next.words.because, start.words.because); // untouched: keeps its place in the review schedule
  assert.deepEqual(next.words.island, { box: 0, due: 5000 });
  assert.equal(start.words.island, undefined); // the old state is not changed
});

test("add all with nothing, or odd entries, returns the same words", () => {
  const start = toggleStar(emptyState(), "a", 1);
  assert.deepEqual(addAllToMyWords(start, [], 2), start);
  assert.deepEqual(addAllToMyWords(start, [null, {}, { key: "" }], 2), start);
  assert.deepEqual(addAllToMyWords(null, [{ key: "x" }], 2).words, { x: { box: 0, due: 2 } });
});

test("countNew counts only words not yet in My words", () => {
  const start = toggleStar(emptyState(), "because", 1);
  assert.equal(countNew(start, [{ key: "because" }, { key: "island" }]), 1);
  assert.equal(countNew(start, []), 0);
  assert.equal(countNew(null, [{ key: "x" }]), 1);
});
