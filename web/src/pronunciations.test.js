import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeWord, removePronunciation, upsertPronunciation, validatePronunciation } from "./pronunciations.js";

test("accepts plain and phoneme respellings", () => {
  assert.equal(validatePronunciation({ word: "Gaieties", respelling: "gay-uh-teez" }).valid, true);
  assert.equal(validatePronunciation({ word: "o'clock", respelling: "/ɡˈAɪtˌiz/" }).valid, true);
});
test("rejects bad words and respellings", () => {
  assert.ok(validatePronunciation({ word: "two words", respelling: "x" }).errors.word);
  assert.ok(validatePronunciation({ word: "a1", respelling: "x" }).errors.word);
  assert.ok(validatePronunciation({ word: "ok", respelling: "" }).errors.respelling);
  assert.ok(validatePronunciation({ word: "ok", respelling: "a".repeat(61) }).errors.respelling);
  assert.ok(validatePronunciation({ word: "ok", respelling: "gay3" }).errors.respelling);
});
test("upsert and remove stay sorted and immutable", () => {
  const a = [{ word: "b", respelling: "1" }];
  const b = upsertPronunciation(a, { word: "a", respelling: "2" });
  assert.deepEqual(b.map((p) => p.word), ["a", "b"]);
  assert.equal(a.length, 1);
  assert.equal(upsertPronunciation(b, { word: "a", respelling: "3" }).find((p) => p.word === "a").respelling, "3");
  assert.deepEqual(removePronunciation(b, "a").map((p) => p.word), ["b"]);
  assert.equal(normalizeWord("  ABC "), "abc");
});
