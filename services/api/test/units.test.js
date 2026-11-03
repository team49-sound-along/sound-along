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
