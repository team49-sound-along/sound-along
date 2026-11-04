import { test } from "node:test";
import assert from "node:assert/strict";
import { createEnglishSplitter, EXCEPTIONS, tidy } from "./syllablesEn.js";

const { default: Hypher } = await import("hypher");
const { default: patterns } = await import("hyphenation.en-us");
const split = createEnglishSplitter(Hypher, patterns);
const show = (w) => split(w).join("-");

const COMMON = {
  island: "is-land", because: "be-cause", water: "wa-ter", little: "lit-tle", reading: "read-ing", picture: "pic-ture", beautiful: "beau-ti-ful",
  different: "dif-fer-ent", rabbit: "rab-bit", pencil: "pen-cil", people: "peo-ple", library: "li-brary", animal: "an-i-mal", umbrella: "um-brel-la",
  happy: "hap-py", mother: "moth-er", family: "fam-i-ly",
};
for (const [word, expected] of Object.entries(COMMON)) {
  test(`pattern split ${word}`, () => assert.equal(show(word), expected));
}

// Words the patterns get wrong or leave whole; they are fixed by the exceptions list.
const IRREGULAR = {
  away: "a-way", again: "a-gain", tiger: "ti-ger", elephant: "el-e-phant", any: "an-y", idea: "i-de-a", area: "ar-e-a", giant: "gi-ant",
  scary: "scar-y", okay: "o-kay", bear: "bear", people2: "peo-ple", every: "ev-ery", vegetable: "veg-e-ta-ble", chocolate: "choc-o-late",
  favorite: "fa-vor-ite", beautiful2: "beau-ti-ful", interesting: "in-ter-est-ing", wednesday: "wednes-day", february: "feb-ru-ar-y",
};
for (const [word, expected] of Object.entries(IRREGULAR)) {
  test(`irregular ${word}`, () => assert.equal(show(word.replace(/\d$/, "")), expected));
}

test("one-syllable words are never cut", () => {
  for (const w of ["friend", "through", "cat", "the", "play", "jumped", "world", "bear", "light"]) assert.equal(show(w), w);
});

test("keeps capital letters and the original spelling", () => {
  assert.equal(show("Island"), "Is-land");
  assert.equal(show("ISLAND"), "IS-LAND");
});

test("every exception is lower case, joins back to a plain word, and is not empty", () => {
  for (const [word, parts] of Object.entries(EXCEPTIONS)) {
    assert.equal(word, word.toLowerCase());
    assert.equal(parts.replaceAll("-", ""), word, word);
    assert.ok(!parts.startsWith("-") && !parts.endsWith("-") && !parts.includes("--"), word);
  }
});

test("a piece without a vowel is joined to its neighbour", () => {
  assert.deepEqual(tidy(["d", "if", "fer", "ent"]), ["dif", "fer", "ent"]);
  assert.deepEqual(tidy(["ele", "phan", "t"]), ["ele", "phant"]);
  assert.deepEqual(tidy(["be", "cause"]), ["be", "cause"]);
  assert.deepEqual(tidy([]), []);
});

test("contractions and hyphenated words", () => {
  assert.equal(show("don't"), "don't");
  assert.equal(show("it's"), "it's");
  assert.equal(show("well-known"), "well-known");
  assert.equal(show("ice-cream"), "ice-cream");
});

test("empty and odd input never throws", () => {
  assert.deepEqual(split(""), []);
  assert.deepEqual(split(null), []);
  assert.deepEqual(split(undefined), []);
  assert.deepEqual(split("42"), ["42"]);
  assert.deepEqual(split("!?"), ["!?"]);
  assert.deepEqual(split("a"), ["a"]);
  assert.deepEqual(split("x".repeat(80)).join(""), "x".repeat(80));
});
