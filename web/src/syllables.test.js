import { test } from "node:test";
import assert from "node:assert/strict";
import { loadSplitter, syllablesFor, displayWord } from "./syllables.js";

test("English words split with the lazy-loaded patterns", async () => {
  assert.deepEqual(await syllablesFor("island", "en"), ["is", "land"]);
  assert.deepEqual(await syllablesFor("because,", "en"), ["be", "cause"]); // punctuation around a word is ignored
});

test("Spanish words split by rule", async () => {
  assert.deepEqual(await syllablesFor("construcción", "es"), ["cons", "truc", "ción"]);
  assert.deepEqual(await syllablesFor("“niño”", "es"), ["ni", "ño"]);
});

test("unknown languages are treated as English", async () => {
  assert.deepEqual(await syllablesFor("island", "fr"), ["is", "land"]);
});

test("empty, missing and odd words give one piece or none, and never throw", async () => {
  assert.deepEqual(await syllablesFor("", "en"), []);
  assert.deepEqual(await syllablesFor(null, "en"), []);
  assert.deepEqual(await syllablesFor("...", "en"), []);
  assert.deepEqual(await syllablesFor("2024", "en"), ["2024"]);
  assert.deepEqual(await syllablesFor("I", "es"), ["I"]);
});

test("the splitter is loaded once per language", async () => {
  assert.equal(await loadSplitter("en"), await loadSplitter("en"));
});

test("displayWord trims punctuation but keeps inner apostrophes", () => {
  assert.equal(displayWord("“Don’t!”"), "Don’t");
  assert.equal(displayWord(undefined), "");
});
