import { test } from "node:test";
import assert from "node:assert/strict";
import { createReadAlong, feed, restartFrom } from "./readAloud.js";
import { calloutText, marksFor, marksSignature, sentenceAround } from "./readAloudMarks.js";

const words = "I like it because it is fun. We play all day.".split(" ").map((text, i) => ({ i, text, sentence: i < 7 ? 0 : 1 }));
const start = () => createReadAlong(words, { language: "en" });

test("read words are marked and the next word is marked", () => {
  const { state } = feed(start(), { id: 0, transcript: "I like", isFinal: true });
  assert.deepEqual(marksFor(state, null), { 0: "read", 1: "read", 2: "next" });
});

test("a skipped word is marked skipped and the next word mark is dropped", () => {
  const { state, events } = feed(start(), { id: 0, transcript: "I like it it is fun", isFinal: true });
  const marks = marksFor(state, events.find((e) => e.type === "skipped"));
  assert.equal(marks[3], "skipped");
  assert.equal(Object.values(marks).includes("next"), false);
});

test("a word heard differently has its own mark", () => {
  const { state, events } = feed(start(), { id: 0, transcript: "I like it becoz it is fun", isFinal: true });
  assert.equal(marksFor(state, events.find((e) => e.type === "differs"))[3], "differs");
});

test("restarting clears the marks from that word on", () => {
  const { state } = feed(start(), { id: 0, transcript: "I like it it is fun", isFinal: true });
  const marks = marksFor(restartFrom(state, 0), null);
  assert.deepEqual(marks, { 0: "next" });
});

test("sentenceAround returns the start and words of the sentence", () => {
  const s = sentenceAround(words, 9);
  assert.equal(s.start, 7);
  assert.equal(s.words.length, 4);
  assert.equal(sentenceAround([], 0).start, 0);
});

test("callout copy is plain and names the word", () => {
  assert.equal(calloutText({ type: "skipped", index: 3, indexes: [3] }, words), "You skipped “because”. Read from here again.");
  assert.match(calloutText({ type: "skipped", index: 3, indexes: [3, 4] }, words), /“because” and “it”/);
  assert.match(calloutText({ type: "differs", index: 3, heard: "becoz" }, words), /heard “becoz” where the text says “because”/);
  assert.equal(calloutText(null, words), "");
});

test("the marks fingerprint only changes when what is shown changes", () => {
  const first = feed(start(), { id: 0, transcript: "I like", isFinal: false });
  const again = feed(first.state, { id: 0, transcript: "I like", isFinal: false }); // the same interim text again
  assert.equal(marksSignature(first.state, null), marksSignature(again.state, null));
  const more = feed(again.state, { id: 0, transcript: "I like it", isFinal: true });
  assert.notEqual(marksSignature(again.state, null), marksSignature(more.state, null));
});

test("a callout changes the fingerprint, and restarting changes it back", () => {
  const { state } = feed(start(), { id: 0, transcript: "I like because it", isFinal: true });
  const stop = { type: "skipped", index: 2, indexes: [2] };
  assert.notEqual(marksSignature(state, null), marksSignature(state, stop));
  const restarted = restartFrom(state, 2);
  assert.notEqual(marksSignature(state, stop), marksSignature(restarted, null));
});

test("a long skip is described as a count with where it starts and ends", () => {
  const w = Array.from({ length: 30 }, (_, i) => ({ i, text: `word${i}`, sentence: Math.floor(i / 10) }));
  const text = calloutText({ type: "skipped", index: 2, indexes: Array.from({ length: 20 }, (_, k) => k + 2) }, w);
  assert.match(text, /skipped 20 words/);
  assert.match(text, /“word2” to “word21”/);
});
