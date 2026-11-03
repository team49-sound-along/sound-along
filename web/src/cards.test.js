import { test } from "node:test";
import assert from "node:assert/strict";
import { cardFromVocab, findWordCard, placeAt, wordKey } from "./cards.js";

const w = (i, text) => ({ i, text });
const words = [w(0, "In"), w(1, "Atlanta,"), w(2, "there's"), w(3, "a"), w(4, "park"), w(5, "called"), w(6, "Piedmont"), w(7, "Park.")];

test("wordKey lower-cases and strips edge punctuation", () => {
  assert.equal(wordKey("Relax,"), "relax");
  assert.equal(wordKey("“Hello!”"), "hello");
  assert.equal(wordKey("there's"), "there's");
  assert.equal(wordKey("Park."), "park");
  assert.equal(wordKey("..."), "");
  assert.equal(wordKey(undefined), "");
});

test("cardFromVocab normalises the timing-file vocabulary entry", () => {
  const card = cardFromVocab({ word: "nature", definition: "Plants and animals.", partOfSpeech: "noun", examples: ["Enjoy nature."], spanish: ["naturaleza"] });
  assert.deepEqual(card, { word: "nature", syllables: null, ipa: null, partOfSpeech: "noun", definition: "Plants and animals.", example: "Enjoy nature.", spanish: ["naturaleza"] });
});

test("cardFromVocab tolerates missing fields and bad input", () => {
  assert.equal(cardFromVocab(null), null);
  assert.deepEqual(cardFromVocab({ word: "x", definition: "d" }).spanish, []);
  assert.equal(cardFromVocab({ word: "x", definition: "d" }).example, null);
});

test("findWordCard prefers the server card, then the passage vocabulary, then nothing", () => {
  const cards = { words: { relax: { word: "relax", definition: "Rest.", spanish: [] } } };
  const vocab = { v1: { word: "nature", definition: "Plants.", spanish: ["naturaleza"], examples: [] } };
  assert.equal(findWordCard(cards, vocab, "Relax,").definition, "Rest.");
  assert.equal(findWordCard(cards, vocab, "nature").spanish[0], "naturaleza");
  assert.equal(findWordCard(cards, vocab, "zebra"), null);
  assert.equal(findWordCard(null, null, "zebra"), null);
  assert.equal(findWordCard(cards, vocab, ""), null);
});

test("placeAt matches a multi-word place around the tapped word", () => {
  const places = { "Piedmont Park": { name: "Piedmont Park", summary: "A big park." } };
  assert.equal(placeAt(words, 6, places).name, "Piedmont Park");
  assert.equal(placeAt(words, 7, places).name, "Piedmont Park");
  assert.equal(placeAt(words, 4, places), null);
});

test("placeAt is case-insensitive and ignores punctuation", () => {
  const places = { "atlanta": { name: "Atlanta", summary: "A city." } };
  assert.equal(placeAt(words, 1, places).name, "Atlanta");
});

test("placeAt is safe with no places or bad indexes", () => {
  assert.equal(placeAt(words, 6, null), null);
  assert.equal(placeAt(words, 6, {}), null);
  assert.equal(placeAt(words, -1, { x: { name: "x" } }), null);
  assert.equal(placeAt([], 0, { x: { name: "x" } }), null);
});

test("findWordCard ignores inherited object properties such as constructor", () => {
  const cards = { words: {} };
  assert.equal(findWordCard(cards, null, "constructor"), null);
  assert.equal(findWordCard(cards, null, "toString"), null);
  assert.equal(findWordCard({ words: { constructor: { word: "constructor", definition: "A builder." } } }, null, "constructor").definition, "A builder.");
});
