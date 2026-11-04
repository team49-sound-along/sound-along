import { test } from "node:test";
import assert from "node:assert/strict";
import { groupVariants, isHuman, readTarget, resumeIndex, voiceLabel } from "./voices.js";

const ai = { id: "a", engine: "kokoro", pairId: "h" };
const human = { id: "h", engine: "human", pairId: "a" };
const lone = { id: "x", engine: "kokoro", pairId: null };

test("grouping hides the human variant and records it on the AI passage", () => {
  const out = groupVariants([ai, human, lone]);
  assert.deepEqual(out.map((p) => p.id), ["a", "x"]);
  assert.equal(out[0].humanId, "h");
  assert.equal(out[1].humanId, undefined);
});

test("a human variant whose pair is missing stays visible", () => {
  assert.deepEqual(groupVariants([human]).map((p) => p.id), ["h"]);
});

test("grouping does not mutate its input", () => {
  const input = [ai, human];
  const snapshot = JSON.stringify(input);
  groupVariants(input);
  assert.equal(JSON.stringify(input), snapshot);
});

test("read target prefers the human narration", () => {
  assert.equal(readTarget({ id: "a", humanId: "h" }), "h");
  assert.equal(readTarget({ id: "x" }), "x");
});

test("labels and detection", () => {
  assert.equal(voiceLabel("human"), "Human narration");
  assert.equal(voiceLabel("kokoro"), "Read-aloud voice");
  assert.equal(isHuman(human), true);
  assert.equal(isHuman(undefined), false);
});

test("resume index validates the query", () => {
  assert.equal(resumeIndex({ at: "12" }, 100), 12);
  assert.equal(resumeIndex({ at: "100" }, 100), null);
  assert.equal(resumeIndex({ at: "-1" }, 100), null);
  assert.equal(resumeIndex({ at: "abc" }, 100), null);
  assert.equal(resumeIndex({}, 100), null);
});

import { firstWordOfSentence, languageSwitch, resumeSentence, targetSentence } from "./voices.js";

const sourceTiming = { id: "a", language: "en", translations: { es: { id: "t", sentenceMap: [[0], [1, 2], [3]] } } };
const translatedTiming = { id: "t", language: "es", translationOf: { id: "a", lang: "en", sentenceMap: [0, 1, 1, 2] } };

test("a text with a translation offers the other language, and so does the translation", () => {
  assert.deepEqual(languageSwitch(sourceTiming), { lang: "es", id: "t", map: [[0], [1, 2], [3]], direction: "forward" });
  assert.deepEqual(languageSwitch(translatedTiming), { lang: "en", id: "a", map: [0, 1, 1, 2], direction: "back" });
  assert.equal(languageSwitch({ id: "x" }), null);
  assert.equal(languageSwitch(null), null);
  assert.equal(languageSwitch({ translations: { es: {} } }), null);
});

test("the reader's place maps through the sentence map in both directions", () => {
  const forward = languageSwitch(sourceTiming);
  assert.equal(targetSentence(forward, 1), 1); // a source sentence that became two starts at the first
  assert.equal(targetSentence(forward, 2), 3);
  const back = languageSwitch(translatedTiming);
  assert.equal(targetSentence(back, 2), 1); // either half of a split sentence returns to the same source sentence
  assert.equal(targetSentence(back, 3), 2);
  assert.equal(targetSentence(forward, 99), 0); // out of range falls back to the start
});

test("a sentence number finds its first word, and bad input is safe", () => {
  const words = [{ sentence: 0 }, { sentence: 0 }, { sentence: 1 }, { sentence: 2 }];
  assert.equal(firstWordOfSentence(words, 1), 2);
  assert.equal(firstWordOfSentence(words, 0), 0);
  assert.equal(firstWordOfSentence(words, 9), null);
  assert.equal(firstWordOfSentence([], 0), null);
  assert.equal(firstWordOfSentence(undefined, 0), null);
});

test("the route's sentence number is read safely", () => {
  assert.equal(resumeSentence({ s: "3" }), 3);
  assert.equal(resumeSentence({ s: "0" }), 0);
  for (const bad of [{ s: "-1" }, { s: "x" }, { s: "1.5" }, {}, undefined]) assert.equal(resumeSentence(bad), null);
});

test("grouping hides a translation behind its source and records the languages on the source", () => {
  const en = { id: "a", engine: "kokoro", pairId: "h", translations: { es: "t" } };
  const hu = { id: "h", engine: "human", pairId: "a", translations: { es: "t" } };
  const es = { id: "t", engine: "kokoro", pairId: null, language: "es", translationOf: "a", translations: {} };
  const out = groupVariants([en, hu, es]);
  assert.deepEqual(out.map((p) => p.id), ["a"]);
  assert.deepEqual(out[0].translationLangs, ["es"]);
  assert.deepEqual(groupVariants([es]).map((p) => p.id), ["t"]); // a translation whose source is missing stays visible
  assert.equal(groupVariants([{ id: "x", pairId: null }])[0].translationLangs, undefined);
});
