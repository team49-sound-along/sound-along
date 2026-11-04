import assert from "node:assert/strict";
import { test } from "node:test";
import { PART_MAX_WORDS, isHeading, splitIntoParts, splitSentences } from "../src/splitDocument.js";
import { countWords } from "../src/wordCount.js";

const sentence = (n) => `Sentence ${n} has exactly eight plain words in it.`; // 9 words
const paragraph = (start, sentences) => Array.from({ length: sentences }, (_, i) => sentence(start + i)).join(" ");
const doc = (paragraphs) => paragraphs.join("\n");

test("a short text is one part", () => {
  const parts = splitIntoParts(doc([paragraph(0, 5), paragraph(5, 5)]));
  assert.equal(parts.length, 1);
});

test("a long text is cut at paragraph ends into parts of about 800 words, none over the maximum, and nothing is lost or reordered", () => {
  const paragraphs = Array.from({ length: 60 }, (_, i) => paragraph(i * 5, 5)); // 60 paragraphs of 45 words
  const text = doc(paragraphs);
  const parts = splitIntoParts(text);
  assert.ok(parts.length >= 3 && parts.length <= 4, `parts: ${parts.length}`);
  for (const p of parts) assert.ok(countWords(p) <= PART_MAX_WORDS);
  assert.equal(parts.join("\n"), text, "the parts joined are the original text");
  for (const p of parts) assert.ok(p.split("\n").every((line) => paragraphs.includes(line)), "no paragraph is cut");
});

test("a chapter heading starts a new part once the current one has enough text", () => {
  const first = Array.from({ length: 10 }, (_, i) => paragraph(i * 5, 5)); // 450 words
  const second = Array.from({ length: 6 }, (_, i) => paragraph(100 + i * 5, 5)); // 270 words
  const parts = splitIntoParts(doc([...first, "CHAPTER II", ...second]));
  assert.equal(parts.length, 2);
  assert.ok(parts[1].startsWith("CHAPTER II"));
});

test("a heading near the start does not leave a tiny part", () => {
  const parts = splitIntoParts(doc(["CHAPTER I", paragraph(0, 5), "CHAPTER II", paragraph(5, 5)]));
  assert.equal(parts.length, 1);
});

test("a very short last part is joined to the part before it", () => {
  const body = Array.from({ length: 18 }, (_, i) => paragraph(i * 5, 5)); // 810 words
  const parts = splitIntoParts(doc([...body, paragraph(1000, 3)])); // plus 27 words
  assert.equal(parts.length, 1, "27 extra words are not worth a part of their own when they fit");
});

test("one giant paragraph is split between sentences, never in the middle of one", () => {
  const giant = paragraph(0, 300); // 2,700 words, no paragraph breaks
  const parts = splitIntoParts(giant);
  assert.ok(parts.length >= 3);
  for (const p of parts) {
    assert.ok(countWords(p) <= PART_MAX_WORDS);
    assert.ok(/\.$/.test(p.trim()), "each part ends at the end of a sentence");
  }
  assert.equal(parts.join(" "), giant);
});

test("a run-on with no sentence end is cut by words as a last resort", () => {
  const run = Array.from({ length: 2500 }, (_, i) => `w${i}`).join(" ");
  const parts = splitIntoParts(run);
  assert.ok(parts.length >= 3 && parts.every((p) => countWords(p) <= PART_MAX_WORDS));
  assert.equal(parts.join(" ").split(/\s+/).length, 2500);
});

test("headings are recognised and ordinary lines are not", () => {
  for (const h of ["CHAPTER II", "Capítulo 3", "IV", "12", "THE RABBIT HOLE", "Part One", "PRÓLOGO"]) assert.equal(isHeading(h), true, h);
  for (const p of ["It was a dark night.", "Chapter two ended badly, they said.", "He said hello", "a very long line that goes on and on and on and on and on and on and on and on"]) assert.equal(isHeading(p), false, p);
});

test("sentence splitting respects abbreviations, initials and closing quotes", () => {
  assert.deepEqual(splitSentences('Mr. Bennet met Dr. Lee. "Hello!" said J. K. Rowling. Then they left.'), ['Mr. Bennet met Dr. Lee.', '"Hello!" said J. K. Rowling.', "Then they left."]);
});

test("empty text gives no parts", () => {
  assert.deepEqual(splitIntoParts(""), []);
  assert.deepEqual(splitIntoParts("\n\n  \n"), []);
});
