import assert from "node:assert/strict";
import { test } from "node:test";
import { passageSummary } from "./libraryMeta.js";

test("builds the full line from real fields", () => {
  assert.equal(
    passageSummary({ words: 360, vocabCount: 3, engine: "polly", humanId: "h" }),
    "360 words · 3 vocabulary words · Recording available",
  );
});

test("uses singular forms", () => {
  assert.equal(passageSummary({ words: 1, vocabCount: 1, engine: "polly" }), "1 word · 1 vocabulary word");
});

test("human-only passage", () => {
  assert.equal(passageSummary({ words: 20, engine: "human" }), "20 words · Recording available");
});

test("omits missing or invalid fields, including zero vocabulary", () => {
  assert.equal(passageSummary({ words: 1200, vocabCount: 0, engine: "polly" }), "1,200 words");
  assert.equal(passageSummary({ words: "x", vocabCount: null }), "");
  assert.equal(passageSummary(null), "");
});
