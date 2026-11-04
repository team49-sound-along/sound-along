import { test } from "node:test";
import assert from "node:assert/strict";
import {
  approvedPayload, canPublish, counts, describeChecks, emptyReview, loadReview, reviewKey, saveReview, sentenceText, setEdit, setStatus, validateEdit,
} from "./questionReview.js";

const mem = () => {
  const data = new Map();
  return { getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => void data.set(k, String(v)), removeItem: (k) => void data.delete(k) };
};
const broken = { getItem() { throw new Error("x"); }, setItem() { throw new Error("x"); }, removeItem() { throw new Error("x"); } };
const q = (n) => ({ id: `q${n}`, question: `Question ${n}?`, choices: ["A", "B", "C"], answerIndex: 1, evidenceSentence: n, checks: {}, status: "pending" });
const view = { passageId: "p", questions: [q(1), q(2), q(3)] };

test("every question starts pending and nothing can be published", () => {
  const r = emptyReview();
  assert.deepEqual(counts(view, r), { approved: 0, rejected: 0, pending: 3 });
  assert.equal(canPublish(view, r), false);
});

test("approving and rejecting returns a new review and leaves the old one alone", () => {
  const r0 = emptyReview();
  const r1 = setStatus(r0, "q1", "approved");
  const r2 = setStatus(r1, "q2", "rejected");
  assert.deepEqual(r0, emptyReview());
  assert.deepEqual(counts(view, r2), { approved: 1, rejected: 1, pending: 1 });
  assert.equal(canPublish(view, r2), true);
  assert.deepEqual(counts(view, setStatus(r2, "q1", "pending")), { approved: 0, rejected: 1, pending: 2 });
  assert.equal(canPublish(view, setStatus(r2, "q1", "pending")), false);
});

test("an unknown status is ignored", () => {
  assert.deepEqual(setStatus(emptyReview(), "q1", "maybe"), emptyReview());
});

test("only approved questions are in the publish request, with edited text when there is some", () => {
  let r = setStatus(emptyReview(), "q1", "approved");
  r = setStatus(r, "q2", "rejected");
  r = setStatus(r, "q3", "approved");
  r = setEdit(r, "q3", { question: "Better?", choices: ["x", "y", "z"] });
  assert.deepEqual(approvedPayload(view, r), { approved: [{ id: "q1", question: "Question 1?", choices: ["A", "B", "C"] }, { id: "q3", question: "Better?", choices: ["x", "y", "z"] }] });
  assert.deepEqual(approvedPayload(view, emptyReview()), { approved: [] });
});

test("a decision for a question that is not in the draft is ignored", () => {
  const r = setStatus(emptyReview(), "gone", "approved");
  assert.deepEqual(counts(view, r), { approved: 0, rejected: 0, pending: 3 });
  assert.deepEqual(approvedPayload(view, r), { approved: [] });
});

test("edits are checked the way the server checks them", () => {
  const original = q(1);
  assert.equal(validateEdit(original, { question: "Fine?", choices: ["a", "b", "c"] }), "");
  assert.match(validateEdit(original, { question: " ", choices: ["a", "b", "c"] }), /question/i);
  assert.match(validateEdit(original, { question: "x".repeat(301), choices: ["a", "b", "c"] }), /300/);
  assert.match(validateEdit(original, { question: "Q?", choices: ["a", "b", ""] }), /answer/i);
  assert.match(validateEdit(original, { question: "Q?", choices: ["a", "A", "c"] }), /different/i);
  assert.match(validateEdit(original, { question: "Q?", choices: ["a", "b", "x".repeat(161)] }), /160/);
  assert.match(validateEdit(original, { question: "Q?", choices: ["a", "b", "None of the above"] }), /above/i);
});

test("automatic checks are described in plain words and are never called a review", () => {
  assert.deepEqual(describeChecks({}), []);
  const flagged = describeChecks({ answeredFromPassage: true, guessableWithoutPassage: true });
  assert.equal(flagged.length, 2);
  assert.equal(flagged[0].tone, "ok");
  assert.equal(flagged[1].tone, "warn");
  assert.match(flagged[1].text, /without (reading|the passage)/i);
  const failed = describeChecks({ answeredFromPassage: false, guessableWithoutPassage: false });
  assert.equal(failed[0].tone, "warn");
  assert.equal(failed[1].tone, "ok");
  for (const item of [...flagged, ...failed]) assert.doesNotMatch(item.text, /\b(AI|model|reviewed by|approved by)\b/i);
});

test("the evidence sentence text is rebuilt from the timing words", () => {
  const words = [
    { text: "Hello", sentence: 0 }, { text: "there.", sentence: 0 }, { text: "We", sentence: 1 }, { text: "met", sentence: 1 }, { text: ",", sentence: 1, join: true }, { text: "again.", sentence: 1 },
  ];
  assert.equal(sentenceText(words, 1), "We met, again.");
  assert.equal(sentenceText(words, 9), "");
  assert.equal(sentenceText(null, 0), "");
});

test("a teacher's choices are kept on this device per passage and survive a reload", () => {
  const s = mem();
  const r = setEdit(setStatus(setStatus(emptyReview(), "q1", "approved"), "q2", "rejected"), "q1", { question: "New?", choices: ["a", "b", "c"] });
  assert.equal(reviewKey("p"), "soundalong.questionReview.v1.p");
  assert.equal(saveReview("p", r, s), true);
  assert.deepEqual(loadReview("p", s, view), r);
  assert.deepEqual(loadReview("other", s, view), emptyReview());
});

test("saved choices for questions that no longer exist or have a bad shape are dropped; broken storage never throws", () => {
  const s = mem();
  s.setItem(reviewKey("p"), JSON.stringify({ status: { q1: "approved", gone: "approved", q2: "weird" }, edits: { q1: { question: 5, choices: [] }, q3: { question: "ok?", choices: ["a", "b", "c"] } } }));
  assert.deepEqual(loadReview("p", s, view), { status: { q1: "approved" }, edits: { q3: { question: "ok?", choices: ["a", "b", "c"] } } });
  s.setItem(reviewKey("p"), "{nope");
  assert.deepEqual(loadReview("p", s, view), emptyReview());
  assert.deepEqual(loadReview("p", broken, view), emptyReview());
  assert.equal(saveReview("p", emptyReview(), broken), false);
  assert.equal(saveReview("p", emptyReview(), null), false);
});
