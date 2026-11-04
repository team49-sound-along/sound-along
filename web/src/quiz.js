// Passage quiz: pure logic, no network. Questions come from a document a person approved (docs/QUESTIONS.md); results stay in this
// browser's localStorage, keyed by the passage the questions belong to. Nothing is sent anywhere.
import { safeStorage } from "./practice.js";

const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const nonEmpty = (v) => typeof v === "string" && v.trim().length > 0;

function cleanQuestion(q) {
  if (!isObject(q) || !nonEmpty(q.id) || !nonEmpty(q.question)) return null;
  if (!Array.isArray(q.choices) || q.choices.length < 2 || !q.choices.every(nonEmpty)) return null;
  if (new Set(q.choices.map((c) => c.trim().toLowerCase())).size !== q.choices.length) return null;
  if (!Number.isInteger(q.answerIndex) || q.answerIndex < 0 || q.answerIndex >= q.choices.length) return null;
  if (q.evidenceSentence !== undefined && q.evidenceSentence !== null && !(Number.isInteger(q.evidenceSentence) && q.evidenceSentence >= 0)) return null;
  return {
    id: q.id,
    skill: q.skill === "inferential" ? "inferential" : "literal",
    question: q.question,
    choices: [...q.choices],
    answerIndex: q.answerIndex,
    evidenceSentence: Number.isInteger(q.evidenceSentence) ? q.evidenceSentence : null,
  };
}

/** Questions from a document a person marked reviewed, and only well-formed ones (a duplicate id keeps the first). */
export function approvedQuestions(doc) {
  if (doc?.reviewed !== true || !Array.isArray(doc.questions)) return [];
  const seen = new Set();
  return doc.questions.map(cleanQuestion).filter((q) => q && !seen.has(q.id) && seen.add(q.id));
}

/** Where questions may be found for a passage, best first: its own file, its voice pair's, then the other language's. */
export function questionSources(id, timing) {
  const lang = timing?.language || "en";
  const found = [{ id, kind: "own", lang }];
  if (timing?.pairId) found.push({ id: timing.pairId, kind: "pair", lang });
  if (timing?.translationOf?.id) found.push({ id: timing.translationOf.id, kind: "other", lang: timing.translationOf.lang || (lang === "es" ? "en" : "es") });
  for (const [otherLang, t] of Object.entries(timing?.translations ?? {})) if (t?.id) found.push({ id: t.id, kind: "other", lang: otherLang });
  const seen = new Set();
  return found.filter((s) => !seen.has(s.id) && seen.add(s.id));
}

/**
 * The first source with approved questions. `docs` maps passage id to the fetched document (or nothing).
 * readerId is the passage "Show me where" opens: the current one, unless the questions are from the other language's passage
 * (their sentence numbers belong to that text). otherLanguage is the language of the questions when it differs, else null.
 */
export function chooseQuestions(sources, docs, currentId = sources[0]?.id) {
  for (const source of sources) {
    const questions = approvedQuestions(docs?.[source.id]);
    if (questions.length === 0) continue;
    return { questions, docId: source.id, readerId: source.kind === "other" ? source.id : currentId, otherLanguage: source.kind === "other" ? source.lang : null };
  }
  return null;
}

function seeded(seed) {
  let h = 2166136261;
  for (const ch of String(seed)) h = Math.imul(h ^ ch.codePointAt(0), 16777619);
  let a = h >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** The same questions in the same order with the choices shuffled for this attempt (same seed, same shuffle). The answer index follows its choice. */
export function prepareAttempt(questions, seed) {
  const random = seeded(seed);
  return questions.map((q) => {
    const order = q.choices.map((_, i) => i);
    for (let i = order.length - 1; i > 0; i -= 1) {
      const j = Math.floor(random() * (i + 1));
      [order[i], order[j]] = [order[j], order[i]];
    }
    return { ...q, choices: order.map((i) => q.choices[i]), answerIndex: order.indexOf(q.answerIndex) };
  });
}

/** answers: { questionId: pickedIndex }. Picks that are not a valid choice count as unanswered. */
export function scoreAttempt(questions, answers) {
  const items = questions.map((q) => {
    const pick = answers?.[q.id];
    const picked = Number.isInteger(pick) && pick >= 0 && pick < q.choices.length ? pick : null;
    return { id: q.id, picked, correct: picked === q.answerIndex };
  });
  return { correct: items.filter((i) => i.correct).length, total: items.length, answered: items.filter((i) => i.picked !== null).length, items };
}

export const resultKey = (passageId) => `soundalong.quiz.v1.${passageId}`;

const validScore = (s) => isObject(s) && Number.isInteger(s.correct) && Number.isInteger(s.total) && s.total >= 1 && s.correct >= 0 && s.correct <= s.total && Number.isFinite(s.at);
const pickScore = (s) => ({ correct: s.correct, total: s.total, at: s.at });

/** Saved results for a passage ({ last, best, attempts }), or null. Blocked, missing, corrupt or malformed storage gives null: it never throws. */
export function loadResult(passageId, storage = safeStorage()) {
  try {
    const parsed = JSON.parse(storage?.getItem(resultKey(passageId)) ?? "null");
    if (!isObject(parsed) || !validScore(parsed.last) || !validScore(parsed.best) || !Number.isInteger(parsed.attempts) || parsed.attempts < 1) return null;
    return { last: pickScore(parsed.last), best: pickScore(parsed.best), attempts: parsed.attempts };
  } catch {
    return null;
  }
}

/** Remember a finished attempt. The best score only compares attempts of the same length. Returns false when storage is unavailable. */
export function recordResult(passageId, score, now, storage = safeStorage()) {
  try {
    if (!storage) return false;
    const entry = { correct: score.correct, total: score.total, at: now };
    const before = loadResult(passageId, storage);
    const best = before && before.best.total === entry.total && before.best.correct >= entry.correct ? before.best : entry;
    storage.setItem(resultKey(passageId), JSON.stringify({ last: entry, best, attempts: (before?.attempts ?? 0) + 1 }));
    return true;
  } catch {
    return false;
  }
}

export function clearResult(passageId, storage = safeStorage()) {
  try {
    if (!storage) return false;
    storage.removeItem(resultKey(passageId));
    return true;
  } catch {
    return false;
  }
}

/** Link back to the reader, which lights the sentence from ?s=<n>. null when the question has no evidence sentence. */
export function evidenceHref(passageId, sentence) {
  return Number.isInteger(sentence) && sentence >= 0 ? `#/read/${encodeURIComponent(passageId)}?s=${sentence}` : null;
}
