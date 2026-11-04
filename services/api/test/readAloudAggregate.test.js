import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { MIN_SESSIONS, buildReadAloudInsights, rankWords, totalsOf } from "../src/readAloud/aggregate.js";
import { suggestSteps } from "../src/readAloud/suggest.js";

const TEXT = ["the", "island", "because", "Because,", "dog"];
const textOf = (i) => TEXT[i];
const passages = [{ id: "p1", title: "Island Story" }, { id: "p2", title: "Other" }];
const group = (classId, sessions, finished, retried, words = {}, passageId = "p1") => ({ passageId, classId, sessions, finished, retried, words });
const base = { passages, textOf };

describe("totals and ranking", () => {
  test("rates come from the counts and are null with no sessions", () => {
    assert.deepEqual(totalsOf([group("a", 4, 3, 1), group("b", 6, 3, 2)]), { sessions: 10, finished: 6, retried: 3, finishRate: 0.6, retryRate: 0.3 });
    assert.equal(totalsOf([]).finishRate, null);
  });
  test("words are merged by their letters, capped at the session count and ranked", () => {
    const ranked = rankWords([group("a", 5, 0, 0, { 2: { s: 3, d: 0 }, 3: { s: 2, d: 1 }, 1: { s: 0, d: 2 } })], textOf, 5);
    assert.deepEqual(ranked.map((w) => [w.word, w.missed, w.share]), [["because", 5, 1], ["island", 2, 0.4]]);
  });
  test("positions that resolve to no letters are dropped and at most ten are listed", () => {
    const many = Object.fromEntries(Array.from({ length: 30 }, (_, i) => [i, { s: 1, d: 0 }]));
    const ranked = rankWords([group("a", 5, 0, 0, many)], (i) => (i === 0 ? "..." : `w${i}`), 5);
    assert.equal(ranked.length, 10);
    assert.ok(!ranked.some((w) => w.word === "..."));
  });
});

describe("buildReadAloudInsights", () => {
  const filters = { passageId: "p1", classId: null };
  const big = group("a", 22, 15, 6, { 2: { s: 14, d: 0 }, 1: { s: 4, d: 3 } });

  test("shows words with the count out of the sessions", () => {
    const out = buildReadAloudInsights({ ...base, summaries: [big], wordGroups: [big], filters });
    assert.equal(out.words.state, "ok");
    assert.deepEqual(out.words.items[0], { word: "because", skipped: 14, differs: 0, missed: 14, sessions: 22, share: 14 / 22 });
    assert.equal(out.totals.sessions, 22);
    assert.ok(out.steps.some((s) => s.includes('Add "because"')));
  });
  test("fewer than the minimum shows no numbers and no words", () => {
    const small = group("a", MIN_SESSIONS - 1, 1, 0, { 2: { s: 2, d: 0 } });
    const out = buildReadAloudInsights({ ...base, summaries: [small], wordGroups: [small], filters });
    assert.equal(out.words.state, "small");
    assert.deepEqual(out.words.items, []);
    assert.equal(out.totals.sessions, 0);
    assert.equal(out.totals.finishRate, null);
    assert.equal(out.hiddenSessions, 2);
    assert.deepEqual(out.steps, []);
    assert.equal(JSON.stringify(out).includes("because"), false);
  });
  test("all classes is built only from classes that pass on their own, so subtraction reveals nothing", () => {
    const tiny = group("b", 1, 1, 0, { 1: { s: 1, d: 0 } });
    const all = buildReadAloudInsights({ ...base, summaries: [big, tiny], wordGroups: [big, tiny], filters });
    assert.equal(all.totals.sessions, 22);
    assert.equal(all.words.items.find((w) => w.word === "island").missed, 7);
    assert.equal(all.hiddenSessions, 1);
  });
  test("a class filter narrows to that class", () => {
    const other = group("b", 3, 3, 0, { 4: { s: 3, d: 0 } });
    const out = buildReadAloudInsights({ ...base, summaries: [big, other], wordGroups: [big, other], filters: { passageId: "p1", classId: "b" } });
    assert.deepEqual(out.words.items.map((w) => w.word), ["dog"]);
    assert.equal(out.totals.sessions, 3);
  });
  test("no passage chosen: tiles and a passage list but no words", () => {
    const p2 = group("a", 3, 1, 3, {}, "p2");
    const out = buildReadAloudInsights({ ...base, summaries: [big, p2], filters: { passageId: null, classId: null } });
    assert.equal(out.words.state, "choose");
    assert.deepEqual(out.passages.map((p) => [p.id, p.sessions]), [["p1", 22], ["p2", 3]]);
    assert.equal(out.totals.sessions, 25);
  });
  test("a passage with no data says so", () => {
    const out = buildReadAloudInsights({ ...base, summaries: [], wordGroups: [], filters });
    assert.equal(out.words.state, "none");
  });
});

describe("suggestSteps", () => {
  const w = (word, skipped, differs, sessions = 10) => ({ word, skipped, differs, missed: skipped + differs, sessions, share: (skipped + differs) / sessions });
  test("word practice for skipped words, a spoken warm-up for words heard differently", () => {
    const steps = suggestSteps({ totals: { sessions: 10, finishRate: 0.9, retryRate: 0.1 }, words: [w("island", 5, 0), w("though", 1, 4)] });
    assert.deepEqual(steps, ["Add \"island\" to this class's word practice.", 'Say "though" aloud together before reading: it is often heard as a different word.']);
  });
  test("words missed once or rarely are not suggested", () => {
    const steps = suggestSteps({ totals: { sessions: 10, finishRate: 0.9, retryRate: 0.1 }, words: [w("island", 1, 0)] });
    assert.deepEqual(steps, ["No word stands out. Keep this passage as it is."]);
  });
  test("low finish and high retry rates each add a step", () => {
    const steps = suggestSteps({ totals: { sessions: 10, finishRate: 0.3, retryRate: 0.6 }, words: [] });
    assert.equal(steps.length, 2);
  });
});
