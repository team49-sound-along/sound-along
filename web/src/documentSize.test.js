import { test } from "node:test";
import assert from "node:assert/strict";
import { DOCUMENT_WORDS_MAX, SINGLE_WORDS_MAX, countWords, describeSize } from "./documentSize.js";

const text = (n) => Array.from({ length: n }, (_, i) => `w${i}`).join(" ");

test("words are counted like the server does, dashes included", () => {
  assert.equal(countWords(""), 0);
  assert.equal(countWords("  two words "), 2);
  assert.equal(countWords("good—and fun"), 3);
});

test("up to 1,000 words is one quick run; more takes a few minutes but is still one passage; very long is refused", () => {
  assert.deepEqual(describeSize(text(SINGLE_WORDS_MAX)), { words: 1000, long: false, tooLong: false });
  assert.deepEqual(describeSize(text(1001)), { words: 1001, long: true, tooLong: false });
  assert.equal("parts" in describeSize(text(2400)), false);
  assert.equal(describeSize(text(DOCUMENT_WORDS_MAX)).tooLong, false);
  assert.equal(describeSize(text(DOCUMENT_WORDS_MAX + 1)).tooLong, true);
});
