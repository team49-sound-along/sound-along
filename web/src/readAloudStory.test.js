import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { defaultPassage, finishSplit, finishWords, hardWords, headline, suggestions } from "./readAloudStory.js";

const w = (word, missed, sessions = 14) => ({ word, skipped: missed, differs: 0, missed, sessions, share: missed / sessions });
const totals = (sessions, finished, retried = 0) => ({ sessions, finished, retried, finishRate: sessions ? finished / sessions : null, retryRate: sessions ? retried / sessions : null });
const okWords = (items) => ({ state: "ok", items });

describe("finishWords", () => {
  test("plain bands for the share that finished", () => {
    assert.equal(finishWords(1), "Almost everyone");
    assert.equal(finishWords(0.9), "Almost everyone");
    assert.equal(finishWords(0.7), "Most");
    assert.equal(finishWords(0.5), "About half");
    assert.equal(finishWords(0.2), "Fewer than half");
    assert.equal(finishWords(null), "");
  });
});

describe("hardWords", () => {
  test("only words that many readers missed, at least twice and a quarter of the reads", () => {
    const list = hardWords([w("island", 6), w("quiet", 1), w("because", 4), w("there", 2)]);
    assert.deepEqual(list.map((x) => x.word), ["island", "because"]);
  });
});

describe("headline", () => {
  const base = { who: "Period 2 Reading", title: "The Red Kite", totals: totals(14, 11), words: okWords([w("a", 6), w("b", 5), w("c", 4)]) };
  test("a sentence about finishing and one about hard words", () => {
    assert.equal(headline(base), "Most of Period 2 Reading finished “The Red Kite”. 3 words tripped up many readers.");
  });
  test("one word is singular, none says so", () => {
    assert.match(headline({ ...base, words: okWords([w("a", 6)]) }), /1 word tripped up many readers\.$/);
    assert.match(headline({ ...base, words: okWords([w("a", 1)]) }), /No word tripped up many readers\.$/);
  });
  test("the finishing sentence changes with the data", () => {
    assert.match(headline({ ...base, totals: totals(14, 14) }), /^Almost all of Period 2 Reading finished/);
    assert.match(headline({ ...base, totals: totals(14, 7) }), /^About half of Period 2 Reading finished/);
    assert.match(headline({ ...base, totals: totals(14, 3) }), /^Fewer than half of Period 2 Reading finished/);
  });
  test("without a class it speaks about your students", () => {
    assert.match(headline({ ...base, who: "" }), /^Most of your students finished/);
  });
  test("too little data says what is missing, never a rate", () => {
    const text = headline({ ...base, totals: totals(0, 0), words: { state: "small", items: [] } });
    assert.match(text, /Not enough reads yet/);
    assert.doesNotMatch(text, /%/);
  });
  test("word list not ready: only the finishing sentence", () => {
    assert.equal(headline({ ...base, words: { state: "small", items: [] } }), "Most of Period 2 Reading finished “The Red Kite”.");
  });
});

describe("finishSplit", () => {
  test("finished and stopped part-way, with percentages that add to 100", () => {
    assert.deepEqual(finishSplit(totals(14, 10)), { finished: 10, stopped: 4, total: 14, finishedPercent: 71, stoppedPercent: 29 });
    assert.equal(finishSplit(totals(0, 0)), null);
  });
});

describe("defaultPassage", () => {
  test("the passage with the most reads that can be shown, else the first listed, else none", () => {
    assert.equal(defaultPassage([{ id: "a", sessions: 0 }, { id: "b", sessions: 5 }]), "b");
    assert.equal(defaultPassage([{ id: "a", sessions: 0 }]), "a");
    assert.equal(defaultPassage([]), "");
  });
});

describe("suggestions", () => {
  const heat = (perParagraph) => ({ sessions: 14, tokens: perParagraph.flatMap((list, p) => list.map((missed, k) => ({ i: p * 10 + k, text: "x", paragraph: p, missed }))) });
  const strong = { totals: totals(14, 11, 2), words: okWords([w("island", 6), w("because", 5), w("quiet", 4), w("there", 1)]), heat: heat([[0, 0], [6, 5, 4, 0]]) };

  test("practice the hard words (at most three) and re-read the paragraph where most stumbles are", () => {
    const cards = suggestions(strong);
    assert.deepEqual(cards.map((c) => c.id), ["words", "paragraph"]);
    assert.equal(cards[0].title, "Practice these 3 words together");
    assert.deepEqual(cards[0].words, ["island", "because", "quiet"]);
    assert.equal(cards[1].title, "Re-read paragraph 2 as a class");
  });
  test("one word reads in the singular", () => {
    const cards = suggestions({ ...strong, words: okWords([w("island", 6)]), heat: null });
    assert.equal(cards[0].title, "Practice this word together");
  });
  test("a passage most readers stopped early is flagged first", () => {
    const cards = suggestions({ ...strong, totals: totals(14, 5, 2) });
    assert.equal(cards[0].id, "tooHard");
    assert.equal(cards[0].title, "This passage may be too hard");
    assert.match(cards[0].detail, /^9 of 14 readers stopped before the end/);
  });
  test("many going back adds a gentle suggestion, and no more than three cards are shown", () => {
    const cards = suggestions({ ...strong, totals: totals(14, 5, 10) });
    assert.equal(cards.length, 3);
    assert.deepEqual(cards.map((c) => c.id), ["tooHard", "words", "paragraph"]);
    const retry = suggestions({ totals: totals(14, 12, 10), words: okWords([]), heat: null });
    assert.deepEqual(retry.map((c) => c.id), ["retry"]);
  });
  test("a single paragraph never gets a re-read card", () => {
    const cards = suggestions({ ...strong, heat: heat([[6, 5, 4]]) });
    assert.deepEqual(cards.map((c) => c.id), ["words"]);
  });
  test("when nothing stands out and most finished: nothing to fix", () => {
    const cards = suggestions({ totals: totals(14, 13, 1), words: okWords([w("x", 1)]), heat: null });
    assert.deepEqual(cards.map((c) => c.id), ["fine"]);
  });
  test("hidden when the data is too thin", () => {
    assert.deepEqual(suggestions({ totals: totals(0, 0), words: { state: "small", items: [] }, heat: null }), []);
    assert.deepEqual(suggestions({ totals: totals(14, 5), words: { state: "small", items: [] }, heat: null }), []);
  });
});
