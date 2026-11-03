// Self-learning practice: "My words" flashcards with spaced review, and a picture-match quiz. Pure logic, no network.
//
// PRIVACY: everything is kept in this browser's localStorage, keyed by passage id. No accounts, nothing is sent anywhere (not even anonymous
// events). Limit: on a shared classroom device the next student sees the last student's stars, so the screen has a "Clear my words" button.
// Method (see docs/PRACTICE.md): retrieval practice (answer first, then reveal) and spaced review. The evidence for children is thinner than
// for adults, so nothing here claims an effect.
import { wordKey } from "./cards.js";

export const DAY = 86_400_000;
const STEPS_DAYS = [0, 1, 3]; // box 0: again this session, box 1: after a day, box 2: after three days (the top box)
const TOP_BOX = STEPS_DAYS.length - 1;

export const storageKey = (passageId) => `soundalong.practice.v1.${passageId}`;
export const emptyState = () => ({ words: {} });

/** localStorage, or null when the browser blocks it (private mode, disabled storage). Every use below tolerates null. */
export function safeStorage() {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
}

const validEntry = (e) => e && Number.isInteger(e.box) && e.box >= 0 && e.box <= TOP_BOX && Number.isFinite(e.due);

/** Saved progress for a passage. Blocked, missing, corrupt or malformed storage gives an empty state: it never throws and is never trusted. */
export function loadState(passageId, storage = safeStorage()) {
  try {
    const parsed = JSON.parse(storage?.getItem(storageKey(passageId)) ?? "null");
    const words = parsed?.words;
    if (!words || typeof words !== "object" || Array.isArray(words)) return emptyState();
    const entries = Object.entries(words);
    if (!entries.every(([, e]) => validEntry(e))) return emptyState();
    return { words: Object.fromEntries(entries.map(([k, e]) => [k, { box: e.box, due: e.due }])) };
  } catch {
    return emptyState();
  }
}

export function saveState(passageId, state, storage = safeStorage()) {
  try {
    if (!storage) return false;
    storage.setItem(storageKey(passageId), JSON.stringify(state));
    return true;
  } catch {
    return false;
  }
}

/** "Clear my words": removes this passage's progress. Returns false when storage is unavailable. */
export function clearState(passageId, storage = safeStorage()) {
  try {
    if (!storage) return false;
    storage.removeItem(storageKey(passageId));
    return true;
  } catch {
    return false;
  }
}

/** Star or un-star a word. Returns a new state. */
export function toggleStar(state, key, now) {
  if (state.words[key]) {
    const { [key]: _removed, ...rest } = state.words;
    return { words: rest };
  }
  return { words: { ...state.words, [key]: { box: 0, due: now } } };
}

/** After the student answers: "I knew it" moves the word up a box (the gap grows); "Not yet" sends it back to box 0, due now. */
export function review(state, key, knew, now) {
  const entry = state.words[key];
  if (!entry) return state;
  const box = knew ? Math.min(entry.box + 1, TOP_BOX) : 0;
  return { words: { ...state.words, [key]: { box, due: now + STEPS_DAYS[box] * DAY } } };
}

/** Starred words that are due, soonest first. `anyway` ("practise now") offers every starred word. */
export function dueWords(state, now, anyway = false) {
  return Object.entries(state.words)
    .filter(([, e]) => anyway || e.due <= now)
    .sort((a, b) => a[1].due - b[1].due)
    .map(([key]) => key);
}

/** Index of the first word with this key that has trustworthy timing (aligned), or null: then there is no audio button. */
export function firstAlignedIndex(words, key) {
  const index = Array.isArray(words) ? words.findIndex((w) => w?.aligned === true && wordKey(w.text) === key) : -1;
  return index >= 0 ? index : null;
}

/** Practice questions, only from a document a person has marked reviewed, and only well-formed ones. */
export function approvedQuestions(doc) {
  if (doc?.reviewed !== true || !Array.isArray(doc.questions)) return [];
  return doc.questions.filter(
    (q) => typeof q?.id === "string" && typeof q.question === "string" && Array.isArray(q.choices) && q.choices.length >= 2
      && Number.isInteger(q.answerIndex) && q.answerIndex >= 0 && q.answerIndex < q.choices.length,
  );
}
