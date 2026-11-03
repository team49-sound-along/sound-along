import assert from "node:assert/strict";
import { test } from "node:test";
import { createRateLimiter } from "../src/rateLimit.js";
import { textToHtml } from "../src/validate.js";

test("rate limiter blocks after max inside the window and recovers", () => {
  let now = 0;
  const allow = createRateLimiter({ max: 2, windowMs: 1000, now: () => now });
  assert.equal(allow("a"), true);
  assert.equal(allow("a"), true);
  assert.equal(allow("a"), false);
  assert.equal(allow("b"), true);
  now = 1001;
  assert.equal(allow("a"), true);
});

test("textToHtml escapes markup and splits paragraphs", () => {
  assert.equal(textToHtml("One <b>two</b>.\n\nThree & four."), "<p>One &lt;b&gt;two&lt;/b&gt;.</p>\n<p>Three &amp; four.</p>");
});

import { buildInsights } from "../src/insights.js";
import { summarizePassage } from "../src/passageSummary.js";

test("human-narrated variants count for quality but never double-count text, cost or speed", () => {
  const ai = { engine: "kokoro", metrics: { characters: 1000, words: 200, audioSeconds: 60, generateSeconds: 6, unalignedWords: 0, estimatedLambdaUsd: 0.01 } };
  const human = { engine: "human", metrics: { characters: 1000, words: 200, audioSeconds: 70, generateSeconds: 30, unalignedWords: 4, estimatedLambdaUsd: 0 } };
  const d = buildInsights({ timings: [ai, human], assignments: [], events: { plays: 0, wordTaps: 0, completions: 0 } });
  assert.equal(d.catalog.passages, 1);
  assert.equal(d.catalog.humanNarrated, 1);
  assert.equal(d.catalog.characters, 1000);
  assert.equal(d.cost.pollyNeuralUsd, 0.016);
  assert.equal(d.speed.avgRealTimeFactor, 0.1);
  assert.equal(d.quality.unalignedWords, 4);
  assert.equal(d.quality.alignedPercent, 99);
  assert.equal(d.catalog.audioMinutes, 2.2);
});

test("insights expose the measured quality report only when one exists", () => {
  const base = { timings: [], assignments: [], events: { plays: 0, wordTaps: 0, completions: 0 } };
  assert.equal(buildInsights(base).quality.timingAgreement, null);
  const report = { generatedAt: "2026-11-03", asr: { method: "m", pooled: { wer: 0.02, medianErrorMs: 40, p95ErrorMs: 200 } }, naturalness: { scores: { a: 1 } } };
  const q = buildInsights({ ...base, qualityReport: report }).quality;
  assert.equal(q.timingAgreement.medianErrorMs, 40);
  assert.equal(q.timingAgreement.generatedAt, "2026-11-03");
  assert.deepEqual(q.naturalness, { scores: { a: 1 } });
});

test("vocabCount counts distinct words, not senses: two senses of 'tax' are one word", () => {
  const timing = {
    title: "Tea",
    vocab: {
      4217601: { word: "tax", partOfSpeech: "noun" },
      4217603: { word: "Tax", partOfSpeech: "verb" },
      813901: { word: "colonist" },
      1179703: { word: "disguise" },
      3277401: { word: "principle" },
    },
  };
  assert.equal(summarizePassage({ id: "x", timing, mtimeMs: 0, source: "sample" }).vocabCount, 4);
});

test("vocabCount ignores empty or missing vocabulary and entries without a word", () => {
  const count = (vocab) => summarizePassage({ id: "x", timing: { vocab }, mtimeMs: 0 }).vocabCount;
  assert.equal(count(undefined), 0);
  assert.equal(count({}), 0);
  assert.equal(count({ 1: { word: "nature" }, 2: { definition: "no word here" }, 3: { word: "  " } }), 1);
});

test("summaries carry the translation links so the reader can offer a language switch without another request", () => {
  const timing = { title: "Park", translations: { es: { id: "T1", sentenceMap: [[0]] } }, translationOf: undefined };
  const s = summarizePassage({ id: "x", timing, mtimeMs: 0, source: "sample" });
  assert.deepEqual(s.translations, { es: "T1" });
  assert.equal(s.translationOf, null);
  const back = summarizePassage({ id: "T1", timing: { title: "Parque", language: "es", translationOf: { id: "x", lang: "en", sentenceMap: [0] } }, mtimeMs: 0 });
  assert.equal(back.translationOf, "x");
  assert.deepEqual(back.translations, {});
  assert.deepEqual(summarizePassage({ id: "z", timing: { title: "T", translations: { es: {}, fr: null } }, mtimeMs: 0 }).translations, {});
});

test("a passage over the word limit is refused with advice to split it", async () => {
  const { parseGenerateInput, LIMITS } = await import("../src/validate.js");
  const ok = parseGenerateInput({ title: "T", text: "go ".repeat(LIMITS.wordsMax).trim() });
  assert.equal(ok.title, "T");
  assert.throws(() => parseGenerateInput({ title: "T", text: "go ".repeat(LIMITS.wordsMax + 1).trim() }), (err) => err.status === 400 && /Split it into parts/.test(err.message));
});
