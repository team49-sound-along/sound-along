import { test } from "node:test";
import assert from "node:assert/strict";
import { activeSentence, phraseLines } from "./phrases.js";

const mk = (text, sentence = 0, paragraph = 0, i = 0) => ({ i, text, sentence, paragraph });
const make = (sentences) => {
  let i = 0;
  return sentences.flatMap((s, sentence) => s.split(" ").map((text) => mk(text, sentence, 0, i++)));
};
const lines = (words) => phraseLines(words).map((line) => line.map((w) => w.text).join(" "));

test("breaks after a comma once the line has three or more words", () => {
  const words = make(["A city park is a fun place to relax, play, and enjoy nature."]);
  assert.deepEqual(lines(words), ["A city park is a fun place to relax,", "play, and enjoy nature."]);
});

test("a comma after a very short start does not break", () => {
  const words = make(["In Atlanta, Georgia, there is a big park."]);
  assert.deepEqual(lines(words), ["In Atlanta, Georgia,", "there is a big park."]);
});

test("always breaks at the end of a sentence", () => {
  const words = make(["Go now.", "Stay here."]);
  assert.deepEqual(lines(words), ["Go now.", "Stay here."]);
});

test("breaks at the sentence boundary even with no punctuation on the word", () => {
  const words = [mk("one", 0, 0, 0), mk("two", 0, 0, 1), mk("three", 1, 0, 2)];
  assert.deepEqual(lines(words), ["one two", "three"]);
});

test("a long run with no punctuation is split into balanced lines, never ten words and one", () => {
  const words = make(["one two three four five six seven eight nine ten eleven twelve"]);
  assert.deepEqual(lines(words), ["one two three four five six", "seven eight nine ten eleven twelve"]);
});

test("a long clause is split before a phrase-starting word, not before the last word", () => {
  const words = make(["Ever since tea was first imported to Great Britain from China, the English love it."]);
  assert.deepEqual(lines(words), ["Ever since tea was first imported", "to Great Britain from China,", "the English love it."]);
});

test("no line is left with fewer than three words by a split of a long clause", () => {
  const words = make(["The little brown fox jumped quickly over the very lazy sleeping dogs."]);
  for (const line of lines(words)) assert.ok(line.split(" ").length >= 3, line);
});

test("words glued by a dash are never separated by a split", () => {
  const w = make(["one two three four five six seven eight nine ten eleven twelve"]);
  const glued = w.map((x, i) => (i === 6 ? { ...x, join: true } : x));
  const out = phraseLines(glued).map((line) => line.map((x) => x.text).join(" "));
  assert.ok(!out.some((l) => l.endsWith("six")) || out.some((l) => l.startsWith("seven")) === false, JSON.stringify(out));
  assert.equal(out.join(" "), "one two three four five six seven eight nine ten eleven twelve");
});

test("colons and semicolons break like commas", () => {
  const words = make(["She packed three things: a map, a hat and water."]);
  assert.deepEqual(lines(words), ["She packed three things:", "a map, a hat and water."]);
});

test("questions and exclamations end a line", () => {
  const words = make(["Where can people go? They can go to a park!"]);
  assert.deepEqual(lines(words), ["Where can people go?", "They can go to a park!"]);
});

test("empty and missing input is safe", () => {
  assert.deepEqual(phraseLines([]), []);
  assert.deepEqual(phraseLines(undefined), []);
});

test("does not mutate its input and keeps word identity", () => {
  const words = make(["Go now."]);
  const frozen = words.map((w) => Object.freeze({ ...w }));
  const result = phraseLines(frozen);
  assert.equal(result[0][0], frozen[0]);
});

test("activeSentence finds the sentence of the active word", () => {
  const words = make(["Go now.", "Stay here."]);
  assert.equal(activeSentence(words, 3), 1);
  assert.equal(activeSentence(words, 0), 0);
  assert.equal(activeSentence(words, -1), null);
  assert.equal(activeSentence(words, 99), null);
  assert.equal(activeSentence([], 0), null);
});

import { sentenceStart } from "./phrases.js";

test("sentenceStart goes to the start of the next sentence", () => {
  const words = make(["Go now.", "Stay here please."]); // indexes 0-1, 2-4
  assert.equal(sentenceStart(words, 0, 1), 2);
  assert.equal(sentenceStart(words, 1, 1), 2);
});

test("sentenceStart forward from the last sentence stays put", () => {
  const words = make(["Go now.", "Stay here."]);
  assert.equal(sentenceStart(words, 3, 1), null);
});

test("sentenceStart back first returns to the start of the current sentence, then the previous one", () => {
  const words = make(["Go now.", "Stay here please."]);
  assert.equal(sentenceStart(words, 4, -1), 2);
  assert.equal(sentenceStart(words, 2, -1), 0);
  assert.equal(sentenceStart(words, 0, -1), 0);
});

test("sentenceStart is safe for empty input and bad indexes", () => {
  assert.equal(sentenceStart([], 0, 1), null);
  assert.equal(sentenceStart(make(["Go now."]), -1, 1), 0);
  assert.equal(sentenceStart(make(["Go now."]), 99, -1), null);
});

test("flags stored in older timing files are ignored: every passage is drawn by the same rule", () => {
  const words = make(["Ever since tea was first imported to Great Britain from China, the English love it."]).map((w, i) => ({ ...w, phraseEnd: i === 9 })); // the old rule broke "... from | China,"
  assert.deepEqual(lines(words), ["Ever since tea was first imported", "to Great Britain from China,", "the English love it."]);
});

test("sentence ends still break even when phraseEnd is missing on that word", () => {
  const words = [{ i: 0, text: "Go", sentence: 0, paragraph: 0, phraseEnd: false }, { i: 1, text: "on", sentence: 1, paragraph: 0, phraseEnd: false }];
  assert.deepEqual(lines(words), ["Go", "on"]);
});

test("a line never breaks between a dash and the word glued to it", () => {
  const w = (text, extra = {}) => ({ text, sentence: 0, ...extra });
  const lines = phraseLines([w("It"), w("was"), w("a"), w("good—"), w("and", { join: true }), w("fun."), w("Next", { sentence: 1 })]);
  assert.ok(lines.every((l) => !l[0].join), "no line starts with a glued word");
});
