import { test } from "node:test";
import assert from "node:assert/strict";
import {
  DAY, approvedQuestions, clearState, dueWords, emptyState, firstAlignedIndex, loadState, review, saveState,
  storageKey, toggleStar,
} from "./practice.js";

const mem = () => {
  const data = new Map();
  return { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => void data.set(k, String(v)), removeItem: (k) => void data.delete(k), data };
};
const broken = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("full"); }, removeItem() { throw new Error("blocked"); } };
const card = (word, hash, extra = {}) => ({ word, definition: "", imageUrl: hash ? `/data/p.word-${word}-${hash}.png` : null, imageAlt: word, ...extra });

test("progress is keyed by passage id and round-trips through storage", () => {
  const s = mem();
  assert.equal(storageKey("abc"), "soundalong.practice.v1.abc");
  const state = toggleStar(emptyState(), "cookies", 1000);
  assert.equal(saveState("abc", state, s), true);
  assert.deepEqual(loadState("abc", s), state);
  assert.deepEqual(loadState("other", s), emptyState());
});

test("storage that is blocked, full, missing or corrupt never throws and just starts empty", () => {
  assert.deepEqual(loadState("abc", broken), emptyState());
  assert.equal(saveState("abc", emptyState(), broken), false);
  assert.deepEqual(loadState("abc", null), emptyState());
  const s = mem();
  s.setItem(storageKey("abc"), "{not json");
  assert.deepEqual(loadState("abc", s), emptyState());
  s.setItem(storageKey("abc"), JSON.stringify({ words: { x: { box: 99, due: "soon" } }, evil: 1 }));
  assert.deepEqual(loadState("abc", s), emptyState()); // a malformed document is ignored, not trusted
  assert.equal(clearState("abc", broken), false);
});

test("clear my words removes only that passage's progress", () => {
  const s = mem();
  saveState("a", toggleStar(emptyState(), "x", 0), s);
  saveState("b", toggleStar(emptyState(), "y", 0), s);
  assert.equal(clearState("a", s), true);
  assert.deepEqual(loadState("a", s), emptyState());
  assert.deepEqual(Object.keys(loadState("b", s).words), ["y"]);
});

test("starring is a toggle and never mutates the old state", () => {
  const a = emptyState();
  const b = toggleStar(a, "tea", 5);
  assert.deepEqual(a, emptyState());
  assert.deepEqual(b.words.tea, { box: 0, due: 5 });
  assert.deepEqual(toggleStar(b, "tea", 6), emptyState());
});

test("knowing a word moves it up a box with growing gaps (same session, 1 day, 3 days) and not yet sends it back", () => {
  const t0 = 1_000_000;
  let s = toggleStar(emptyState(), "tea", t0);
  s = review(s, "tea", true, t0);
  assert.deepEqual(s.words.tea, { box: 1, due: t0 + 1 * DAY });
  s = review(s, "tea", true, t0 + DAY);
  assert.deepEqual(s.words.tea, { box: 2, due: t0 + DAY + 3 * DAY });
  s = review(s, "tea", true, t0 + 4 * DAY);
  assert.equal(s.words.tea.box, 2); // the top box stays
  s = review(s, "tea", false, t0 + 8 * DAY);
  assert.deepEqual(s.words.tea, { box: 0, due: t0 + 8 * DAY });
  assert.deepEqual(review(emptyState(), "unknown", true, 0), emptyState()); // only starred words are reviewed
});

test("only words that are due are offered, soonest first, and 'practise now anyway' offers every starred word", () => {
  const t = 10 * DAY;
  let s = emptyState();
  s = { words: { a: { box: 2, due: t + 2 * DAY }, b: { box: 1, due: t - DAY }, c: { box: 0, due: t } } };
  assert.deepEqual(dueWords(s, t), ["b", "c"]);
  assert.deepEqual(dueWords(s, t, true).sort(), ["a", "b", "c"]);
  assert.deepEqual(dueWords(emptyState(), t), []);
});

test("audio comes from the first word that is truly aligned, otherwise there is no audio", () => {
  const words = [{ text: "The" }, { text: "Cookies,", aligned: false }, { text: "cookies.", aligned: true }, { text: "tea", aligned: false }];
  assert.equal(firstAlignedIndex(words, "cookies"), 2);
  assert.equal(firstAlignedIndex(words, "tea"), null);
  assert.equal(firstAlignedIndex(words, "none"), null);
  assert.equal(firstAlignedIndex(undefined, "x"), null);
});

test("only questions a person has approved are ever offered", () => {
  const q = [{ id: "q1", question: "?", choices: ["a", "b"], answerIndex: 0 }];
  assert.deepEqual(approvedQuestions({ reviewed: true, questions: q }), q);
  for (const bad of [null, undefined, {}, { reviewed: false, questions: q }, { reviewed: "true", questions: q }, { reviewed: true, questions: "x" }, { reviewed: true, questions: [{ id: "q" }] }]) {
    assert.deepEqual(approvedQuestions(bad), []);
  }
});
