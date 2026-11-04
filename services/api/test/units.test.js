import assert from "node:assert/strict";
import { test } from "node:test";
import { createRateLimiter } from "../src/rateLimit.js";
import { stripMarkup, textToHtml, unwrapLines } from "../src/validate.js";
import { guessLanguage, languageMismatch } from "../src/languageGuess.js";

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

test("textToHtml escapes what is left of < and & after cleaning, and splits paragraphs", () => {
  assert.equal(textToHtml("One <3 two.\n\nThree & four."), "<p>One &lt;3 two.</p>\n<p>Three &amp; four.</p>");
  assert.equal(textToHtml("One <b>two</b>.\n\nThree & four."), "<p>One two.</p>\n<p>Three &amp; four.</p>");
});

import { buildInsights } from "../src/insights.js";
import { seriesOf, summarizePassage } from "../src/passageSummary.js";

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





test("a hard-wrapped paste (PDF, Word, email) becomes whole paragraphs, not one paragraph per line", () => {
  const wrapped = "It is a truth universally acknowledged, that a single man in possession of a good\nfortune, must be in want of a wife. However little known the feelings or views\nof such a man may be, this truth is well fixed.\n\nSecond paragraph starts here and also wraps across\ntwo lines.";
  const html = textToHtml(wrapped);
  assert.equal((html.match(/<p>/g) || []).length, 2);
  assert.ok(html.includes("a good fortune, must be"));
  assert.ok(html.includes("views of such a man"));
});

test("typed paragraphs, headings and poems keep their line breaks", () => {
  assert.equal(unwrapLines("Chapter One\nIt was a dark night.\nThe wind blew."), "Chapter One\nIt was a dark night.\nThe wind blew.");
  assert.equal(unwrapLines("Roses are red\nViolets are blue\nSugar is sweet"), "Roses are red\nViolets are blue\nSugar is sweet");
  const long = "A paragraph of typed text that ends with a full stop right here at the end.";
  assert.equal(unwrapLines(`${long}\n${long}`), `${long}\n${long}`);
});

test("a word split with a hyphen at the end of a line is rejoined, but a real hyphenated word is kept", () => {
  assert.equal(unwrapLines("We looked at the first page of the book and it was a good exam-\nple that we all liked."), "We looked at the first page of the book and it was a good example that we all liked.");
  assert.equal(unwrapLines("They went to the well-known park near the old stone bridge by the very-\nPopular cafe."), "They went to the well-known park near the old stone bridge by the very-Popular cafe.");
});


test("emphasis and Markdown markers are not read aloud or shown", () => {
  assert.equal(stripMarkup("It was not so _very_ much, and *really* **great**."), "It was not so very much, and really great.");
  assert.equal(stripMarkup("# The Title\n\n> A quote\n- first item\nSee [the site](https://example.com) now."), "The Title\n\nA quote\nfirst item\nSee the site now.");
  assert.equal(stripMarkup("Use `code` here."), "Use code here.");
});

test("markup stripping leaves ordinary text alone", () => {
  for (const s of ["snake_case_name and file_name.txt", "2 * 3 = 6 and 4*5", "A lone * star and a lone _ mark", "Don't touch an apostrophe's or a dash-word."]) assert.equal(stripMarkup(s), s);
});


test("footnote markers, editorial tags and typed double dashes are cleaned up", () => {
  assert.equal(stripMarkup("duros cual[1] dos escarabajos."), "duros cual dos escarabajos.");
  assert.equal(stripMarkup("[Illustration: PLATERO Y YO]\nHello."), "\nHello.");
  assert.equal(stripMarkup("--Espera. ¿Qué es eso?\nHe said -- quietly -- and left."), "\u2014Espera. ¿Qué es eso?\nHe said \u2014 quietly \u2014 and left.");
  assert.equal(stripMarkup("See [1] and the array a[1] stays."), "See [1] and the array a stays.");
});


test("footnote markers after accented letters and heading markers like #TITLE# are removed", () => {
  assert.equal(stripMarkup("no sé qué[2] cascabeleo y está[12]."), "no sé qué cascabeleo y está.");
  assert.equal(stripMarkup("#I#\n\n#PLATERO#\n\nPlatero es un burro."), "I\n\nPLATERO\n\nPlatero es un burro.");
  assert.equal(stripMarkup("Item #5 and #7 stay."), "Item #5 and #7 stay.");
});


const EN_TEXT = "The red fox ran across the green field and the children watched it from the hill. It was a bright afternoon and they were all very happy that the day had come.";
const ES_TEXT = "El zorro rojo corrió por el campo verde y los niños lo miraban desde la colina. Era una tarde clara y todos estaban muy felices de que el día había llegado.";

test("the language of a text is recognised only when the evidence is clear", () => {
  assert.equal(guessLanguage(EN_TEXT), "en");
  assert.equal(guessLanguage(ES_TEXT), "es");
  assert.equal(guessLanguage("Hola"), null);
  assert.equal(guessLanguage(""), null);
  assert.equal(guessLanguage(`${EN_TEXT} ${ES_TEXT}`), null, "a mixed text is not guessed");
  assert.equal(guessLanguage("Alice Bob Carol Dave Erin Frank 12 34 56 78"), null);
});

test("Spanish text with English selected (and the reverse) is refused with a helpful message; a match is accepted", () => {
  assert.match(languageMismatch(ES_TEXT, "en"), /looks like Spanish, but English is selected/);
  assert.match(languageMismatch(EN_TEXT, "es"), /looks like English, but Spanish is selected/);
  assert.equal(languageMismatch(ES_TEXT, "es"), null);
  assert.equal(languageMismatch(EN_TEXT, "en"), null);
  assert.equal(languageMismatch("Hola", "en"), null, "too short to judge: never blocks");
});


test("an italic phrase that wraps across lines is cleaned too", () => {
  const html = textToHtml("The Rabbit actually _took a watch out of its waistcoat-pocket_, and looked at it, and then hurried on.");
  assert.ok(!html.includes("_"));
  const wrapped = textToHtml("She saw the Rabbit actually _took a watch out\nof its waistcoat-pocket_, and looked at it, and then hurried on.");
  assert.ok(!wrapped.includes("_") && wrapped.includes("watch out of its waistcoat-pocket"), wrapped);
});


const words = (n) => Array.from({ length: n }, (_, i) => `w${i}`).join(" ");
const longEnglish = (n) => Array.from({ length: Math.ceil(n / 9) }, (_, i) => `The red fox ran across the green field number ${i}.`).join(" ");

test("up to 1,000 words is a single passage; more becomes parts that each carry their own title", async () => {
  const { parseGenerateInput, LIMITS, partTitle } = await import("../src/validate.js");
  const single = parseGenerateInput({ title: "T", text: longEnglish(900) });
  assert.equal(single.parts, null);
  const long = parseGenerateInput({ title: "The Story", text: longEnglish(2500) });
  assert.ok(long.parts.length >= 3);
  assert.equal(long.parts[0].title, `The Story (Part 1 of ${long.parts.length})`);
  assert.equal(partTitle("x".repeat(200), 2, 10).length <= LIMITS.titleMax, true);
});

test("a document over the overall cap is refused with a friendly message", async () => {
  const { parseGenerateInput, LIMITS } = await import("../src/validate.js");
  assert.throws(() => parseGenerateInput({ title: "T", text: longEnglish(LIMITS.documentWordsMax + 500) }), (err) => err.status === 400 && /most that can be turned into audio at once/.test(err.message));
});

test("the cap counts dash-joined words and U+0085 separators the way the tokenizer does", async () => {
  const { parseGenerateInput, LIMITS } = await import("../src/validate.js");
  const dashed = "a\u2014b ".repeat(Math.floor(LIMITS.documentWordsMax / 2) + 1); // few spaces, but each chunk is two spoken words
  assert.throws(() => parseGenerateInput({ title: "T", text: `The red fox ran across the field and the children watched it. ${dashed}` }), (err) => err.status === 400);
  assert.throws(() => parseGenerateInput({ title: "T", text: "go\u0085".repeat(LIMITS.documentWordsMax + 1) }), (err) => err.status === 400);
});

test("a recording cannot be attached to a document that is split into parts", async () => {
  const { parseGenerateInput } = await import("../src/validate.js");
  assert.throws(() => parseGenerateInput({ title: "T", text: longEnglish(2500), recordingId: "123e4567-e89b-42d3-a456-426614174000" }), (err) => err.status === 400 && /recording can only be added/.test(err.message));
});


const SERIES = { id: "5af24980-4d6d-41c1-87fa-4f21cb2d169d", index: 2, total: 3, title: "The Story", partIds: ["2b781dab-4521-40d2-a9b6-ad5f2bb0ba90", "2b781dab-4521-40d2-a9b6-ad5f2bb0ba91", "2b781dab-4521-40d2-a9b6-ad5f2bb0ba92"] };

test("a part of a long document exposes its series in the passage summary; anything malformed is dropped", () => {
  assert.deepEqual(seriesOf(SERIES), SERIES);
  assert.equal(seriesOf({ ...SERIES, total: 2 }), null);
  assert.equal(seriesOf({ ...SERIES, index: 4 }), null);
  assert.equal(seriesOf({ ...SERIES, partIds: ["nope", "nope"] }), null);
  assert.equal(seriesOf(null), null);
  const s = summarizePassage({ id: "x", timing: { title: "T", words: [], series: SERIES }, mtimeMs: 0, source: "generated" });
  assert.deepEqual(s.series, SERIES);
  assert.equal(summarizePassage({ id: "x", timing: { title: "T", words: [] }, mtimeMs: 0 }).series, null);
});

test("pasted HTML becomes plain text: tags removed, blocks become paragraphs, entities decoded, scripts dropped", () => {
  const html = "<h1>Space</h1><p>The <b>moon</b> circles the Earth &amp; reflects sunlight.</p><p>It takes 27 days.</p><script>alert('x')</script><style>p{color:red}</style>";
  assert.equal(stripMarkup(html), "Space\nThe moon circles the Earth & reflects sunlight.\nIt takes 27 days.");
  assert.equal(stripMarkup("Tom&nbsp;and&nbsp;Ann said &quot;hi&quot; &#8217;bye&#8217;<br>Next line<br/>end"), "Tom and Ann said \"hi\" ’bye’\nNext line\nend");
});

test("text that only looks a little like HTML is left alone", () => {
  assert.equal(stripMarkup("If a < b and c > d then 3 < 5."), "If a < b and c > d then 3 < 5.");
  assert.equal(stripMarkup("I <3 you and 2<3."), "I <3 you and 2<3.");
});

test("a missing space after a full stop is added between two sentences, but abbreviations and initials are left alone", () => {
  assert.equal(stripMarkup("They went home happy.The next day was sunny!Then it rained."), "They went home happy. The next day was sunny! Then it rained.");
  assert.equal(stripMarkup("The U.S.A team met Dr.Smith and Mr.Brown at example.com today."), "The U.S.A team met Dr.Smith and Mr.Brown at example.com today.");
});
