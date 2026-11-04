// Teacher review of question drafts: pure logic. A review is { status: { [questionId]: "approved" | "rejected" }, edits: { [questionId]: { question, choices } } };
// a question with no status is pending. Every function returns a new value. The choices are kept in this browser only (a convenience between visits).
import { safeStorage } from "./practice.js";

export const emptyReview = () => ({ status: {}, edits: {} });
const STATUSES = new Set(["approved", "rejected"]);
const LIMITS = { question: 300, choice: 160 };

export function setStatus(review, id, status) {
  if (status === "pending") {
    const { [id]: _removed, ...rest } = review.status;
    return { ...review, status: rest };
  }
  if (!STATUSES.has(status)) return review;
  return { ...review, status: { ...review.status, [id]: status } };
}

export const setEdit = (review, id, edit) => ({ ...review, edits: { ...review.edits, [id]: { question: edit.question, choices: [...edit.choices] } } });

const known = (view, review) => view.questions.map((q) => ({ q, status: STATUSES.has(review.status[q.id]) ? review.status[q.id] : "pending" }));

export function counts(view, review) {
  const items = known(view, review);
  const n = (s) => items.filter((i) => i.status === s).length;
  return { approved: n("approved"), rejected: n("rejected"), pending: n("pending") };
}

export const canPublish = (view, review) => counts(view, review).approved > 0;

/** The publish request: only approved questions, with the teacher's edited text when there is some. The answer and evidence come from the draft on the server. */
export function approvedPayload(view, review) {
  return {
    approved: known(view, review)
      .filter((i) => i.status === "approved")
      .map(({ q }) => {
        const edit = review.edits[q.id];
        return { id: q.id, question: edit?.question ?? q.question, choices: [...(edit?.choices ?? q.choices)] };
      }),
  };
}

const squash = (v) => (typeof v === "string" ? v.replace(/\s+/g, " ").trim() : "");

/** "" when the edited text is fine, else a sentence for the person. Mirrors the server's checks. */
export function validateEdit(original, edit) {
  const question = squash(edit.question);
  if (question.length < 1) return "Write the question.";
  if (question.length > LIMITS.question) return `A question can be at most ${LIMITS.question} characters.`;
  const choices = (edit.choices ?? []).map(squash);
  if (choices.length !== original.choices.length || choices.some((c) => c.length < 1)) return "Every answer needs some text.";
  if (choices.some((c) => c.length > LIMITS.choice)) return `An answer can be at most ${LIMITS.choice} characters.`;
  if (new Set(choices.map((c) => c.toLowerCase())).size !== choices.length) return "The answers must all be different.";
  if (choices.some((c) => /\b(?:all|none) of the above\b/i.test(c))) return 'Answers cannot say "all of the above" or "none of the above".';
  return "";
}

/** The automatic checks in plain words. They are hints for the person reviewing, never a review. */
export function describeChecks(checks) {
  const out = [];
  if (checks?.answeredFromPassage === true) out.push({ tone: "ok", text: "Automatic check: given the passage, the marked answer was chosen." });
  if (checks?.answeredFromPassage === false) out.push({ tone: "warn", text: "Automatic check: given the passage, a different answer was chosen. Check this question carefully." });
  if (checks?.guessableWithoutPassage === true) out.push({ tone: "warn", text: "Automatic check: the marked answer was also chosen without reading the passage, so a student might guess it. Consider rewriting or rejecting it." });
  if (checks?.guessableWithoutPassage === false) out.push({ tone: "ok", text: "Automatic check: the answer was not guessed without the passage." });
  return out;
}

/** The text of one numbered sentence, rebuilt from the timing words. "" when there is none. */
export function sentenceText(words, sentence) {
  if (!Array.isArray(words)) return "";
  return words
    .filter((w) => w?.sentence === sentence && typeof w.text === "string")
    .map((w, i) => (i === 0 || w.join ? "" : " ") + w.text)
    .join("");
}

export const reviewKey = (passageId) => `soundalong.questionReview.v1.${passageId}`;

const validEdit = (e) => e && typeof e.question === "string" && Array.isArray(e.choices) && e.choices.length >= 2 && e.choices.every((c) => typeof c === "string");

/** A short stable hash of what the teacher actually judged: the question text, the choices and the marked answer. Synchronous, not for security. */
export function fingerprintQuestion(q) {
  const text = JSON.stringify([q?.question ?? "", Array.isArray(q?.choices) ? q.choices : [], q?.answerIndex ?? null]);
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) h = Math.imul(h ^ text.charCodeAt(i), 0x01000193) >>> 0;
  return `${text.length.toString(36)}-${h.toString(36)}`;
}

const fingerprintsOf = (view) => Object.fromEntries(view.questions.map((q) => [q.id, fingerprintQuestion(q)]));

/** Saved choices for this draft. Anything for a question that is not in the draft, was changed since, or is malformed, is dropped. Never throws. */
export function loadReview(passageId, storage = safeStorage(), view) {
  try {
    const parsed = JSON.parse(storage?.getItem(reviewKey(passageId)) ?? "null");
    const saved = parsed?.fingerprints && typeof parsed.fingerprints === "object" ? parsed.fingerprints : {};
    const current = fingerprintsOf(view);
    // a choice stays only while the question it was made for is unchanged; a regenerated question starts pending again
    const ids = new Set(Object.keys(current).filter((id) => saved[id] === current[id]));
    const status = Object.fromEntries(Object.entries(parsed?.status ?? {}).filter(([id, s]) => ids.has(id) && STATUSES.has(s)));
    const edits = Object.fromEntries(Object.entries(parsed?.edits ?? {}).filter(([id, e]) => ids.has(id) && validEdit(e)).map(([id, e]) => [id, { question: e.question, choices: [...e.choices] }]));
    return { status, edits };
  } catch {
    return emptyReview();
  }
}

export function saveReview(passageId, review, storage = safeStorage(), view) {
  try {
    if (!storage) return false;
    storage.setItem(reviewKey(passageId), JSON.stringify({ ...review, fingerprints: fingerprintsOf(view) }));
    return true;
  } catch {
    return false;
  }
}

export function clearReview(passageId, storage = safeStorage()) {
  try {
    storage?.removeItem(reviewKey(passageId));
  } catch {
    /* nothing to clear */
  }
}
