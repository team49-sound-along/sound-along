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

test("caps a run of words with no punctuation", () => {
  const words = make(["one two three four five six seven eight nine ten eleven twelve"]);
  assert.deepEqual(lines(words), ["one two three four five six seven eight nine ten", "eleven twelve"]);
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

test("phraseLines uses phraseEnd flags from the data when present, so the browser only draws them", () => {
  const words = make(["one two three four five six seven"]).map((w, i) => ({ ...w, phraseEnd: i === 2 || i === 6 }));
  assert.deepEqual(lines(words), ["one two three", "four five six seven"]);
});

test("phraseEnd false everywhere gives one line per sentence, ignoring commas", () => {
  const words = make(["one, two, three, four."]).map((w) => ({ ...w, phraseEnd: false }));
  assert.deepEqual(lines(words), ["one, two, three, four."]);
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
