import { HttpError } from "../http.js";

// Question drafts are written by an automatic step and are never served. A person approves them, and only then is the served
// document (docs/QUESTIONS.md, "Approved document") written. Everything here is pure: it returns new objects and never changes its input.

export const QUESTION_LIMITS = { questionMax: 300, choiceMax: 160, quoteMax: 400, titleMax: 120, publishMax: 20, choicesMin: 2, choicesMax: 4 };

const QUESTION_ID = /^[A-Za-z0-9_-]{1,40}$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const SKILLS = new Set(["literal", "inferential"]);
const CHECK_KEYS = ["answeredFromPassage", "guessableWithoutPassage"];
const NO_ABOVE = /\b(?:all|none) of the above\b/i;
const MAX_SENTENCE = 100000;

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const squash = (value) => (typeof value === "string" ? value.replace(/\s+/g, " ").trim() : "");
const text = (value, max) => {
  const clean = squash(value);
  return clean.length >= 1 && clean.length <= max ? clean : null;
};

/** Clean choices, or null: 2 to 4 non-empty strings of limited length, all different (ignoring case). */
function cleanChoices(value) {
  if (!Array.isArray(value) || value.length < QUESTION_LIMITS.choicesMin || value.length > QUESTION_LIMITS.choicesMax) return null;
  const choices = value.map((c) => text(c, QUESTION_LIMITS.choiceMax));
  if (choices.includes(null)) return null;
  if (new Set(choices.map((c) => c.toLowerCase())).size !== choices.length) return null;
  return choices;
}

function cleanChecks(value) {
  if (!isObject(value)) return {};
  return Object.fromEntries(CHECK_KEYS.filter((key) => typeof value[key] === "boolean").map((key) => [key, value[key]]));
}

/** One draft question as a safe view (always pending), or null when it is malformed. */
function cleanQuestion(raw) {
  if (!isObject(raw) || typeof raw.id !== "string" || !QUESTION_ID.test(raw.id) || !SKILLS.has(raw.skill)) return null;
  const question = text(raw.question, QUESTION_LIMITS.questionMax);
  const choices = cleanChoices(raw.choices);
  if (!question || !choices) return null;
  if (!Number.isInteger(raw.answerIndex) || raw.answerIndex < 0 || raw.answerIndex >= choices.length) return null;
  if (!Number.isInteger(raw.evidenceSentence) || raw.evidenceSentence < 0 || raw.evidenceSentence > MAX_SENTENCE) return null;
  const quote = squash(raw.evidenceQuote);
  return {
    id: raw.id,
    skill: raw.skill,
    question,
    choices,
    answerIndex: raw.answerIndex,
    evidenceSentence: raw.evidenceSentence,
    evidenceQuote: quote.length <= QUESTION_LIMITS.quoteMax ? quote : "",
    checks: cleanChecks(raw.checks),
    status: "pending",
  };
}

const cleanGeneratedWith = (value) =>
  Object.fromEntries(
    ["model", "promptVersion", "date"].filter((key) => isObject(value) && typeof value[key] === "string" && value[key].length <= 80).map((key) => [key, value[key]]),
  );

/**
 * A stored draft as the review screen sees it: only well-formed questions, each starting pending whatever the file says
 * (old "review" or "status" fields are ignored). null when it is not a draft for this passage.
 */
export function cleanDraft(raw, passageId) {
  if (!isObject(raw) || raw.passageId !== passageId || !Array.isArray(raw.questions)) return null;
  const seen = new Set();
  const questions = raw.questions.map(cleanQuestion).filter((q) => q && !seen.has(q.id) && seen.add(q.id));
  return {
    passageId,
    title: text(raw.title, QUESTION_LIMITS.titleMax) ?? "Untitled passage",
    generatedWith: cleanGeneratedWith(raw.generatedWith),
    questions,
    skipped: raw.questions.length - questions.length,
  };
}

/** Local demo drafts: the same draft without any review fields, so a person starts from nothing approved. */
export function resetReview(draft) {
  const { reviewed, reviewedAt, ...rest } = draft;
  return {
    ...rest,
    status: "draft",
    questions: (draft.questions ?? []).map(({ review, status, ...question }) => question),
  };
}

export function summarizeDraft(view) {
  const date = view.generatedWith.date;
  return {
    passageId: view.passageId,
    title: view.title,
    questionCount: view.questions.length,
    flaggedCount: view.questions.filter((q) => q.checks.guessableWithoutPassage === true).length,
    generatedOn: typeof date === "string" && DATE.test(date) ? date : "",
  };
}

const bad = (message) => {
  throw new HttpError(400, message);
};

/** The approved questions from a publish request: only an id and the (possibly edited) text. Everything else comes from the draft. */
export function parsePublishInput(body, view) {
  if (!isObject(body) || Object.keys(body).some((key) => key !== "approved")) bad("Send only the approved questions.");
  const { approved } = body;
  if (!Array.isArray(approved) || approved.length < 1) bad("Approve at least one question before publishing.");
  if (approved.length > QUESTION_LIMITS.publishMax) bad(`At most ${QUESTION_LIMITS.publishMax} questions can be published at once.`);
  const byId = new Map(view.questions.map((q) => [q.id, q]));
  const seen = new Set();
  return approved.map((item) => {
    if (!isObject(item) || Object.keys(item).some((key) => !["id", "question", "choices"].includes(key))) bad("Each approved question needs only an id, the question and its choices.");
    const original = byId.get(item.id);
    if (!original) bad("One of the approved questions is not in this draft.");
    if (seen.has(item.id)) bad("A question was approved twice.");
    seen.add(item.id);
    const question = text(item.question, QUESTION_LIMITS.questionMax);
    if (!question) bad(`Each question must be 1 to ${QUESTION_LIMITS.questionMax} characters.`);
    const choices = cleanChoices(item.choices);
    if (!choices) bad(`Each question needs ${QUESTION_LIMITS.choicesMin} to ${QUESTION_LIMITS.choicesMax} different answers of 1 to ${QUESTION_LIMITS.choiceMax} characters.`);
    if (choices.length !== original.choices.length) bad("The number of answers cannot be changed. Reject the question and keep the others.");
    if (choices.some((c) => NO_ABOVE.test(c))) bad('Answers cannot say "all of the above" or "none of the above".');
    return { id: item.id, question, choices };
  });
}

/** The served document: only approved questions, in the draft's order, with the correct answer and evidence taken from the draft. */
export function buildApprovedDocument(view, approved, now = new Date()) {
  const edits = new Map(approved.map((a) => [a.id, a]));
  return {
    version: 1,
    passageId: view.passageId,
    title: view.title,
    generatedWith: { ...view.generatedWith },
    reviewed: true,
    reviewedAt: now.toISOString().slice(0, 10),
    questions: view.questions
      .filter((q) => edits.has(q.id))
      .map((q) => ({
        id: q.id,
        skill: q.skill,
        question: edits.get(q.id).question,
        choices: [...edits.get(q.id).choices],
        answerIndex: q.answerIndex,
        evidenceSentence: q.evidenceSentence,
      })),
  };
}
