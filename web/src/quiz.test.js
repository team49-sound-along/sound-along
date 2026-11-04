import { test } from "node:test";
import assert from "node:assert/strict";
import {
  approvedQuestions, chooseQuestions, clearResult, evidenceHref, loadResult, prepareAttempt, questionSources, recordResult, resultKey, scoreAttempt,
} from "./quiz.js";

const mem = () => {
  const data = new Map();
  return { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => void data.set(k, String(v)), removeItem: (k) => void data.delete(k), data };
};
const broken = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("full"); }, removeItem() { throw new Error("blocked"); } };
const q = (n, extra = {}) => ({ id: `q${n}`, skill: "literal", question: `Question ${n}?`, choices: ["A", "B", "C"], answerIndex: 1, evidenceSentence: n, ...extra });
const doc = (questions = [q(1), q(2)], extra = {}) => ({ reviewed: true, questions, ...extra });

test("only questions from a document a person approved are offered, and only well-formed ones", () => {
  assert.equal(approvedQuestions(doc()).length, 2);
  for (const bad of [null, undefined, {}, "x", { reviewed: false, questions: [q(1)] }, { reviewed: "true", questions: [q(1)] }, { reviewed: true, questions: "x" }]) {
    assert.deepEqual(approvedQuestions(bad), []);
  }
  const malformed = [
    null, "x", { id: "q" }, q(3, { choices: ["only"] }), q(4, { choices: ["a", 2, "c"] }), q(5, { answerIndex: 3 }), q(6, { answerIndex: -1 }), q(7, { answerIndex: 1.5 }),
    q(8, { question: "" }), q(9, { id: 9 }), q(10, { choices: ["a", "a"] }), q(11, { evidenceSentence: -2 }), q(12, { evidenceSentence: "3" }),
  ];
  assert.deepEqual(approvedQuestions(doc([q(1), ...malformed])).map((x) => x.id), ["q1"]);
});

test("a duplicate question id keeps the first one", () => {
  assert.deepEqual(approvedQuestions(doc([q(1), q(1, { question: "Other?" })])).map((x) => x.question), ["Question 1?"]);
});

test("a question without an evidence sentence is kept but has none", () => {
  const [one] = approvedQuestions(doc([q(1, { evidenceSentence: undefined })]));
  assert.equal(one.evidenceSentence, null);
});

test("the questions never carry fields the document should not have", () => {
  const [one] = approvedQuestions(doc([q(1, { review: { by: "x" }, checks: { a: 1 }, extra: 1 })]));
  assert.deepEqual(Object.keys(one).sort(), ["answerIndex", "choices", "evidenceSentence", "id", "question", "skill"]);
});

test("sources go own passage, then its pair, then the other language", () => {
  const timing = { language: "es", pairId: "pair", translationOf: { id: "en", lang: "en", sentenceMap: [0] } };
  assert.deepEqual(questionSources("me", timing), [
    { id: "me", kind: "own", lang: "es" }, { id: "pair", kind: "pair", lang: "es" }, { id: "en", kind: "other", lang: "en" },
  ]);
  const forward = { language: "en", translations: { es: { id: "es-id", sentenceMap: [[0]] } } };
  assert.deepEqual(questionSources("me", forward), [{ id: "me", kind: "own", lang: "en" }, { id: "es-id", kind: "other", lang: "es" }]);
  assert.deepEqual(questionSources("me", {}), [{ id: "me", kind: "own", lang: "en" }]);
  assert.deepEqual(questionSources("me", null), [{ id: "me", kind: "own", lang: "en" }]);
});

test("a Spanish passage uses its own questions first and says so when it falls back to English", () => {
  const sources = questionSources("es1", { language: "es", translationOf: { id: "en1", lang: "en", sentenceMap: [0] } });
  const own = chooseQuestions(sources, { es1: doc([q(1)]), en1: doc([q(1), q(2)]) });
  assert.equal(own.questions.length, 1);
  assert.equal(own.otherLanguage, null);
  assert.equal(own.docId, "es1");
  assert.equal(own.readerId, "es1");
  const fallback = chooseQuestions(sources, { en1: doc([q(1), q(2)]) });
  assert.equal(fallback.questions.length, 2);
  assert.equal(fallback.otherLanguage, "en");
  assert.equal(fallback.docId, "en1");
  assert.equal(fallback.readerId, "en1", "evidence sentences belong to the passage the questions were written for");
});

test("questions found through the voice pair keep the reader on the current passage", () => {
  const sources = questionSources("human", { language: "en", pairId: "ai" });
  const chosen = chooseQuestions(sources, { ai: doc([q(1)]) });
  assert.equal(chosen.docId, "ai");
  assert.equal(chosen.readerId, "human");
  assert.equal(chosen.otherLanguage, null);
});

test("no approved questions anywhere gives null; an unapproved or empty document does not count", () => {
  const sources = questionSources("a", { pairId: "b" });
  assert.equal(chooseQuestions(sources, {}), null);
  assert.equal(chooseQuestions(sources, { a: { reviewed: false, questions: [q(1)] }, b: doc([]) }), null);
  assert.equal(chooseQuestions(sources, { b: doc([q(1)]) }).docId, "b");
});

test("choices are shuffled the same way for one seed and differently for another, and the answer follows its choice", () => {
  const questions = Array.from({ length: 6 }, (_, n) => q(n, { choices: ["right", "x", "y", "z"], answerIndex: 0 }));
  const one = prepareAttempt(questions, "seed-1");
  assert.deepEqual(prepareAttempt(questions, "seed-1"), one);
  assert.notDeepEqual(prepareAttempt(questions, "seed-2").map((x) => x.choices), one.map((x) => x.choices));
  for (const item of one) {
    assert.equal(item.choices[item.answerIndex], "right");
    assert.deepEqual([...item.choices].sort(), ["right", "x", "y", "z"]);
  }
  assert.ok(one.some((x) => x.answerIndex !== 0), "the answer is not always first");
});

test("question order and the input are left alone", () => {
  const questions = [q(1), q(2), q(3)];
  const copy = structuredClone(questions);
  const out = prepareAttempt(questions, 5);
  assert.deepEqual(questions, copy);
  assert.deepEqual(out.map((x) => x.id), ["q1", "q2", "q3"]);
});

test("scoring counts right answers and keeps what was picked per question", () => {
  const questions = [q(1), q(2), q(3)];
  const score = scoreAttempt(questions, { q1: 1, q2: 0 });
  assert.equal(score.correct, 1);
  assert.equal(score.total, 3);
  assert.equal(score.answered, 2);
  assert.deepEqual(score.items.map((i) => [i.id, i.picked, i.correct]), [["q1", 1, true], ["q2", 0, false], ["q3", null, false]]);
  assert.deepEqual(scoreAttempt([], {}), { correct: 0, total: 0, answered: 0, items: [] });
});

test("scoring ignores picks that are out of range or not whole numbers", () => {
  const score = scoreAttempt([q(1)], { q1: 7 });
  assert.equal(score.correct, 0);
  assert.equal(score.items[0].picked, null);
  assert.equal(scoreAttempt([q(1)], { q1: "1" }).correct, 0);
});

test("results are kept per passage on this device and keep the best score", () => {
  const s = mem();
  assert.equal(resultKey("abc"), "soundalong.quiz.v1.abc");
  assert.equal(loadResult("abc", s), null);
  assert.equal(recordResult("abc", { correct: 2, total: 4 }, 1000, s), true);
  assert.deepEqual(loadResult("abc", s), { last: { correct: 2, total: 4, at: 1000 }, best: { correct: 2, total: 4, at: 1000 }, attempts: 1 });
  recordResult("abc", { correct: 4, total: 4 }, 2000, s);
  recordResult("abc", { correct: 1, total: 4 }, 3000, s);
  const saved = loadResult("abc", s);
  assert.deepEqual(saved.best, { correct: 4, total: 4, at: 2000 });
  assert.deepEqual(saved.last, { correct: 1, total: 4, at: 3000 });
  assert.equal(saved.attempts, 3);
  assert.equal(loadResult("other", s), null);
  assert.equal(clearResult("abc", s), true);
  assert.equal(loadResult("abc", s), null);
});

test("a changed question set restarts the best score instead of comparing different quizzes", () => {
  const s = mem();
  recordResult("abc", { correct: 4, total: 4 }, 1, s);
  recordResult("abc", { correct: 1, total: 2 }, 2, s);
  assert.deepEqual(loadResult("abc", s).best, { correct: 1, total: 2, at: 2 });
});

test("blocked, full, corrupt or malformed storage never throws and is never trusted", () => {
  assert.equal(loadResult("abc", broken), null);
  assert.equal(recordResult("abc", { correct: 1, total: 2 }, 1, broken), false);
  assert.equal(clearResult("abc", broken), false);
  assert.equal(loadResult("abc", null), null);
  assert.equal(recordResult("abc", { correct: 1, total: 2 }, 1, null), false);
  const s = mem();
  for (const bad of ["{nope", "null", "[]", JSON.stringify({ last: { correct: 5, total: 2, at: 1 }, best: { correct: 1, total: 2, at: 1 }, attempts: 1 }), JSON.stringify({ last: "x" })]) {
    s.setItem(resultKey("abc"), bad);
    assert.equal(loadResult("abc", s), null, bad);
  }
});

test("Show me where links to the reader with the sentence number the reader already understands", () => {
  assert.equal(evidenceHref("abc", 4), "#/read/abc?s=4");
  assert.equal(evidenceHref("a b/c", 0), "#/read/a%20b%2Fc?s=0");
  assert.equal(evidenceHref("abc", null), null);
  assert.equal(evidenceHref("abc", -1), null);
});
