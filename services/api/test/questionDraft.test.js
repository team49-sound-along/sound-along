import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { HttpError } from "../src/http.js";
import { buildApprovedDocument, cleanDraft, parsePublishInput, resetReview, summarizeDraft } from "../src/questions/draft.js";

const ID = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
const q = (n, extra = {}) => ({
  id: `q${n}`, skill: "literal", question: `Question ${n}?`, choices: ["One", "Two", "Three"], answerIndex: 1, evidenceSentence: 4,
  evidenceQuote: "a quote from the passage", checks: { answeredFromPassage: true, guessableWithoutPassage: false }, ...extra,
});
const draft = (extra = {}) => ({ version: 1, passageId: ID, title: "Park", status: "draft", generatedWith: { model: "x", promptVersion: "q2", date: "2026-11-03" }, questions: [q(1), q(2)], dropped: [], metrics: {}, ...extra });
const status = (fn) => { try { fn(); } catch (e) { return e instanceof HttpError ? e.status : e; } return null; };

describe("cleanDraft", () => {
  test("every question starts pending and old review fields are ignored", () => {
    const view = cleanDraft(draft({ questions: [q(1, { review: { status: "approved", by: "someone" }, status: "approved" })] }), ID);
    assert.equal(view.questions.length, 1);
    assert.equal(view.questions[0].status, "pending");
    assert.equal(view.questions[0].review, undefined);
    assert.deepEqual(view.questions[0].checks, { answeredFromPassage: true, guessableWithoutPassage: false });
  });
  test("malformed questions are dropped and counted, valid ones kept", () => {
    const bad = [
      q(3, { choices: ["only"] }), q(4, { answerIndex: 9 }), q(5, { skill: "trivia" }), q(6, { question: "" }), q(7, { choices: ["a", "a", "b"] }),
      q(8, { evidenceSentence: -1 }), q(9, { id: "bad id!" }), null, "x",
    ];
    const view = cleanDraft(draft({ questions: [q(1), ...bad] }), ID);
    assert.deepEqual(view.questions.map((x) => x.id), ["q1"]);
    assert.equal(view.skipped, bad.length);
  });
  test("duplicate question ids keep the first", () => {
    const view = cleanDraft(draft({ questions: [q(1), q(1, { question: "Other?" })] }), ID);
    assert.equal(view.questions.length, 1);
    assert.equal(view.questions[0].question, "Question 1?");
  });
  test("wrong passage, wrong shape or no questions give null", () => {
    assert.equal(cleanDraft(draft({ passageId: "other" }), ID), null);
    for (const bad of [null, [], "x", 5, { passageId: ID }, { passageId: ID, questions: "x" }]) assert.equal(cleanDraft(bad, ID), null);
  });
  test("unknown check keys are not passed on", () => {
    const view = cleanDraft(draft({ questions: [q(1, { checks: { guessableWithoutPassage: true, secret: 1, answeredFromPassage: "yes" } })] }), ID);
    assert.deepEqual(view.questions[0].checks, { guessableWithoutPassage: true });
  });
  test("a missing quote is allowed and long text is refused", () => {
    const { evidenceQuote, ...noQuote } = q(1);
    assert.equal(cleanDraft(draft({ questions: [noQuote] }), ID).questions[0].evidenceQuote, "");
    assert.equal(cleanDraft(draft({ questions: [q(1, { question: "x".repeat(301) })] }), ID).questions.length, 0);
  });
});

describe("resetReview", () => {
  test("removes review fields, sets drafts back to unreviewed, keeps the rest", () => {
    const out = resetReview(draft({ status: "approved", reviewed: true, reviewedAt: "2026-11-03", questions: [q(1, { review: { status: "approved", by: "x" }, status: "approved" })] }));
    assert.equal(out.status, "draft");
    assert.equal(out.reviewed, undefined);
    assert.equal(out.reviewedAt, undefined);
    assert.equal(out.questions[0].review, undefined);
    assert.equal(out.questions[0].status, undefined);
    assert.equal(out.questions[0].evidenceQuote, "a quote from the passage");
  });
  test("does not change its input", () => {
    const input = draft({ questions: [q(1, { review: { status: "approved" } })] });
    const copy = structuredClone(input);
    resetReview(input);
    assert.deepEqual(input, copy);
  });
});

describe("summarizeDraft", () => {
  test("counts questions and the ones an automatic check flagged", () => {
    const view = cleanDraft(draft({ questions: [q(1), q(2, { checks: { guessableWithoutPassage: true } })] }), ID);
    assert.deepEqual(summarizeDraft(view), { passageId: ID, title: "Park", questionCount: 2, flaggedCount: 1, generatedOn: "2026-11-03" });
  });
});

describe("parsePublishInput", () => {
  const view = cleanDraft(draft(), ID);
  const item = (n, extra = {}) => ({ id: `q${n}`, question: `Question ${n}?`, choices: ["One", "Two", "Three"], ...extra });
  test("accepts approved questions with their text", () => {
    assert.deepEqual(parsePublishInput({ approved: [item(2)] }, view), [item(2)]);
  });
  test("edited text is trimmed and spaces collapsed", () => {
    const [out] = parsePublishInput({ approved: [item(1, { question: "  Where   is it? ", choices: [" A ", "B", "C"] })] }, view);
    assert.equal(out.question, "Where is it?");
    assert.deepEqual(out.choices, ["A", "B", "C"]);
  });
  test("rejects with a 400 and a readable message", () => {
    const cases = [
      null, [], {}, { approved: [] }, { approved: "x" }, { approved: [item(1)], extra: 1 }, { approved: [item(1, { answerIndex: 0 })] },
      { approved: [item(1, { skill: "x" })] }, { approved: [item(1), item(1)] }, { approved: [item(9)] }, { approved: [item(1, { question: "" })] },
      { approved: [item(1, { question: "x".repeat(301) })] }, { approved: [item(1, { choices: ["a", "b"] })] },
      { approved: [item(1, { choices: ["a", "A", "c"] })] }, { approved: [item(1, { choices: ["a", "b", ""] })] }, { approved: [item(1, { choices: ["a", "b", 3] })] },
      { approved: [item(1, { choices: ["a", "b", "x".repeat(161)] })] }, { approved: [item(1, { choices: ["a", "b", "None of the above"] })] },
      { approved: [null] }, { approved: Array.from({ length: 21 }, (_, i) => item(i)) },
    ];
    for (const body of cases) assert.equal(status(() => parsePublishInput(body, view)), 400, JSON.stringify(body)?.slice(0, 90));
  });
});

describe("buildApprovedDocument", () => {
  const view = cleanDraft(draft({ questions: [q(1), q(2, { skill: "inferential", evidenceSentence: 7 }), q(3)] }), ID);
  test("has only approved questions in the documented shape, with the correct answer taken from the draft", () => {
    const doc = buildApprovedDocument(view, [{ id: "q2", question: "Edited?", choices: ["A", "B", "C"] }], new Date("2026-11-04T10:00:00Z"));
    assert.deepEqual(doc, {
      version: 1, passageId: ID, title: "Park", generatedWith: { model: "x", promptVersion: "q2", date: "2026-11-03" }, reviewed: true, reviewedAt: "2026-11-04",
      questions: [{ id: "q2", skill: "inferential", question: "Edited?", choices: ["A", "B", "C"], answerIndex: 1, evidenceSentence: 7 }],
    });
    assert.ok(!JSON.stringify(doc).includes("evidenceQuote"));
    assert.ok(!JSON.stringify(doc).includes("checks"));
  });
  test("keeps the draft order whatever order the request lists them in", () => {
    const doc = buildApprovedDocument(view, [{ id: "q3", question: "Z?", choices: ["a", "b", "c"] }, { id: "q1", question: "A?", choices: ["a", "b", "c"] }], new Date());
    assert.deepEqual(doc.questions.map((x) => x.id), ["q1", "q3"]);
  });
});
